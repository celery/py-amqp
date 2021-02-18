import errno
import os
import re
import ssl
import socket
import struct
from struct import pack
from unittest.mock import ANY, MagicMock, Mock, call, patch, sentinel

import pytest

from amqp import transport
from amqp.exceptions import UnexpectedFrame
from amqp.transport import _AbstractTransport

SIGNED_INT_MAX = 0x7FFFFFFF


class DummyException(Exception):
    pass


class MockSocket:
    options = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connected = False
        self.sa = None

    def setsockopt(self, family, key, value):
        is_sol_socket = family == socket.SOL_SOCKET
        is_receive_or_send_timeout = key in (socket.SO_RCVTIMEO,
                                             socket.SO_SNDTIMEO)
        if is_sol_socket and is_receive_or_send_timeout:
            self.options[key] = value
        elif not isinstance(value, int):
            raise OSError()
        self.options[key] = value

    def getsockopt(self, family, key):
        return self.options.get(key, 0)

    def settimeout(self, timeout):
        self.timeout = timeout

    def fileno(self):
        return 10

    def connect(self, sa):
        self.connected = True
        self.sa = sa

    def close(self):
        self.connected = False
        self.sa = None

    def getsockname(self):
        return ('127.0.0.1', 1234)

    def getpeername(self):
        return ('1.2.3.4', 5671)


TCP_KEEPIDLE = 4
TCP_KEEPINTVL = 5
TCP_KEEPCNT = 6


class test_socket_options:

    @pytest.fixture(autouse=True)
    def setup_self(self, patching):
        self.host = '127.0.0.1'
        self.connect_timeout = 3
        self.socket = MockSocket()
        socket = patching('socket.socket')
        socket().getsockopt = self.socket.getsockopt
        socket().setsockopt = self.socket.setsockopt

        self.tcp_keepidle = 20
        self.tcp_keepintvl = 30
        self.tcp_keepcnt = 40
        self.socket.setsockopt(
            socket.SOL_TCP, socket.TCP_NODELAY, 1,
        )
        self.socket.setsockopt(
            socket.SOL_TCP, TCP_KEEPIDLE, self.tcp_keepidle,
        )
        self.socket.setsockopt(
            socket.SOL_TCP, TCP_KEEPINTVL, self.tcp_keepintvl,
        )
        self.socket.setsockopt(
            socket.SOL_TCP, TCP_KEEPCNT, self.tcp_keepcnt,
        )

        patching('amqp.transport.TCPTransport._write')
        patching('amqp.transport.TCPTransport._setup_transport')
        patching('amqp.transport.SSLTransport._write')
        patching('amqp.transport.SSLTransport._setup_transport')
        patching('amqp.transport.set_cloexec')

    def test_backward_compatibility_tcp_transport(self):
        self.transp = transport.Transport(
            self.host, self.connect_timeout, ssl=False,
        )
        self.transp.connect()
        expected = 1
        result = self.socket.getsockopt(socket.SOL_TCP, socket.TCP_NODELAY)
        assert result == expected

    def test_backward_compatibility_SSL_transport(self):
        self.transp = transport.Transport(
            self.host, self.connect_timeout, ssl=True,
        )
        assert self.transp.sslopts is not None
        self.transp.connect()
        assert self.transp.sock is not None

    def test_use_default_sock_tcp_opts(self):
        self.transp = transport.Transport(
            self.host, self.connect_timeout, socket_settings={},
        )
        self.transp.connect()
        assert (socket.TCP_NODELAY in
                self.transp._get_tcp_socket_defaults(self.transp.sock))

    def test_set_single_sock_tcp_opt_tcp_transport(self):
        tcp_keepidle = self.tcp_keepidle + 5
        socket_settings = {TCP_KEEPIDLE: tcp_keepidle}
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            ssl=False, socket_settings=socket_settings,
        )
        self.transp.connect()
        expected = tcp_keepidle
        result = self.socket.getsockopt(socket.SOL_TCP, TCP_KEEPIDLE)
        assert result == expected

    def test_set_single_sock_tcp_opt_SSL_transport(self):
        self.tcp_keepidle += 5
        socket_settings = {TCP_KEEPIDLE: self.tcp_keepidle}
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            ssl=True, socket_settings=socket_settings,
        )
        self.transp.connect()
        expected = self.tcp_keepidle
        result = self.socket.getsockopt(socket.SOL_TCP, TCP_KEEPIDLE)
        assert result == expected

    def test_values_are_set(self):
        socket_settings = {
            TCP_KEEPIDLE: 10,
            TCP_KEEPINTVL: 4,
            TCP_KEEPCNT: 2
        }

        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        self.transp.connect()
        expected = socket_settings
        tcp_keepidle = self.socket.getsockopt(socket.SOL_TCP, TCP_KEEPIDLE)
        tcp_keepintvl = self.socket.getsockopt(socket.SOL_TCP, TCP_KEEPINTVL)
        tcp_keepcnt = self.socket.getsockopt(socket.SOL_TCP, TCP_KEEPCNT)
        result = {
            TCP_KEEPIDLE: tcp_keepidle,
            TCP_KEEPINTVL: tcp_keepintvl,
            TCP_KEEPCNT: tcp_keepcnt
        }
        assert result == expected

    def test_passing_wrong_options(self):
        socket_settings = object()
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        with pytest.raises(TypeError):
            self.transp.connect()

    def test_passing_wrong_value_options(self):
        socket_settings = {TCP_KEEPINTVL: b'a'}
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        with pytest.raises(socket.error):
            self.transp.connect()

    def test_passing_value_as_string(self):
        socket_settings = {TCP_KEEPIDLE: b'5'}
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        with pytest.raises(socket.error):
            self.transp.connect()

    def test_passing_tcp_nodelay(self):
        socket_settings = {socket.TCP_NODELAY: 0}
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        self.transp.connect()
        expected = 0
        result = self.socket.getsockopt(socket.SOL_TCP, socket.TCP_NODELAY)
        assert result == expected

    def test_platform_socket_opts(self):
        s = socket.socket()
        opts = _AbstractTransport(self.host)._get_tcp_socket_defaults(s)

        assert opts

    def test_set_sockopt_opts_timeout(self):
        # tests socket options SO_RCVTIMEO and SO_SNDTIMEO
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
        )
        read_timeout_sec, read_timeout_usec = 0xdead, 0xbeef
        write_timeout_sec = 0x42

        read_timeout = read_timeout_sec + read_timeout_usec * 0.000001
        self.transp.read_timeout = read_timeout
        self.transp.write_timeout = write_timeout_sec
        self.transp.connect()

        expected_rcvtimeo = struct.pack('ll', read_timeout_sec,
                                        read_timeout_usec)
        expected_sndtimeo = struct.pack('ll', write_timeout_sec, 0)
        assert expected_rcvtimeo == self.socket.getsockopt(socket.SOL_TCP,
                                                           socket.SO_RCVTIMEO)
        assert expected_sndtimeo == self.socket.getsockopt(socket.SOL_TCP,
                                                           socket.SO_SNDTIMEO)


class test_AbstractTransport:
    class Transport(transport._AbstractTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

    @pytest.fixture(autouse=True)
    def setup_transport(self, patching):
        self.t = self.Transport('localhost:5672', 10)
        self.t.connect()

        patching('amqp.transport.set_cloexec')

    def test_port(self):
        assert self.Transport('localhost').port == 5672
        assert self.Transport('localhost:5672').port == 5672
        assert self.Transport('[fe80::1]:5432').port == 5432

    def test_read(self):
        with pytest.raises(NotImplementedError):
            self.t._read(1024)

    def test_setup_transport(self):
        self.t._setup_transport()

    def test_shutdown_transport(self):
        self.t._shutdown_transport()

    def test_write(self):
        with pytest.raises(NotImplementedError):
            self.t._write('foo')

    def test_close(self):
        sock = self.t.sock = Mock()
        self.t.close()
        sock.shutdown.assert_called_with(socket.SHUT_RDWR)
        sock.close.assert_called_with()
        assert self.t.sock is None and self.t.connected is False
        self.t.close()
        assert self.t.sock is None and self.t.connected is False

    def test_read_frame__timeout(self):
        self.t._read = Mock()
        self.t._read.side_effect = socket.timeout()
        with pytest.raises(socket.timeout):
            self.t.read_frame()

    def test_read_frame__SSLError(self):
        self.t._read = Mock()
        self.t._read.side_effect = transport.SSLError('timed out')
        with pytest.raises(socket.timeout):
            self.t.read_frame()

    def test_read_frame__EINTR(self):
        self.t._read = Mock()
        self.t.connected = True
        exc = OSError()
        exc.errno = errno.EINTR
        self.t._read.side_effect = exc
        with pytest.raises(OSError):
            self.t.read_frame()
        assert self.t.connected

    def test_read_frame__EBADF(self):
        self.t._read = Mock()
        self.t.connected = True
        exc = OSError()
        exc.errno = errno.EBADF
        self.t._read.side_effect = exc
        with pytest.raises(OSError):
            self.t.read_frame()
        assert not self.t.connected

    def test_read_frame__simple(self):
        self.t._read = Mock()
        checksum = [b'\xce']

        def on_read2(size, *args):
            return checksum[0]

        def on_read1(size, *args):
            ret = self.t._read.return_value
            self.t._read.return_value = b'thequickbrownfox'
            self.t._read.side_effect = on_read2
            return ret

        self.t._read.return_value = pack('>BHI', 1, 1, 16)
        self.t._read.side_effect = on_read1

        self.t.read_frame()
        self.t._read.return_value = pack('>BHI', 1, 1, 16)
        self.t._read.side_effect = on_read1
        checksum[0] = b'\x13'
        with pytest.raises(UnexpectedFrame) as ex:
            self.t.read_frame()
        assert ex.value.code == 505
        assert ex.value.message == \
            'Received frame_end 0x13 while expecting 0xce'

    def test_read_frame__long(self):
        self.t._read = Mock()
        self.t._read.side_effect = [pack('>BHI', 1, 1, SIGNED_INT_MAX + 16),
                                    b'read1', b'read2', b'\xce']
        frame_type, channel, payload = self.t.read_frame()
        assert frame_type == 1
        assert channel == 1
        assert payload == b'read1read2'

    def transport_read_EOF(self):
        for host, is_ssl in (('localhost:5672', False),
                             ('localhost:5671', True),):
            self.t = transport.Transport(host, is_ssl)
            self.t.sock = Mock(name='socket')
            self.t.connected = True
            self.t._quick_recv = Mock(name='recv', return_value='')
            with pytest.raises(
                IOError,
                match=r'.*Server unexpectedly closed connection.*'
            ):
                self.t.read_frame()

    def test_write__success(self):
        self.t._write = Mock()
        self.t.write('foo')
        self.t._write.assert_called_with('foo')

    def test_write__socket_timeout(self):
        self.t._write = Mock()
        self.t._write.side_effect = socket.timeout
        with pytest.raises(socket.timeout):
            self.t.write('foo')

    def test_write__EINTR(self):
        self.t.connected = True
        self.t._write = Mock()
        exc = OSError()
        exc.errno = errno.EINTR
        self.t._write.side_effect = exc
        with pytest.raises(OSError):
            self.t.write('foo')
        assert self.t.connected
        exc.errno = errno.EBADF
        with pytest.raises(OSError):
            self.t.write('foo')
        assert not self.t.connected

    def test_having_timeout_none(self):
        # Checks that context manager does nothing when no timeout is provided
        with self.t.having_timeout(None) as actual_sock:
            assert actual_sock == self.t.sock

    def test_set_timeout(self):
        # Checks that context manager sets and reverts timeout properly
        with patch.object(self.t, 'sock') as sock_mock:
            sock_mock.gettimeout.return_value = 3
            with self.t.having_timeout(5) as actual_sock:
                assert actual_sock == self.t.sock
            sock_mock.gettimeout.assert_called_with()
            sock_mock.settimeout.assert_has_calls(
                [
                    call(5),
                    call(3),
                ]
            )

    def test_set_timeout_exception_raised(self):
        # Checks that context manager sets and reverts timeout properly
        # when exception is raised.
        with patch.object(self.t, 'sock') as sock_mock:
            sock_mock.gettimeout.return_value = 3
            with pytest.raises(DummyException):
                with self.t.having_timeout(5) as actual_sock:
                    assert actual_sock == self.t.sock
                    raise DummyException()
            sock_mock.gettimeout.assert_called_with()
            sock_mock.settimeout.assert_has_calls(
                [
                    call(5),
                    call(3),
                ]
            )

    def test_set_same_timeout(self):
        # Checks that context manager does not set timeout when
        # it is same as currently set.
        with patch.object(self.t, 'sock') as sock_mock:
            sock_mock.gettimeout.return_value = 5
            with self.t.having_timeout(5) as actual_sock:
                assert actual_sock == self.t.sock
            sock_mock.gettimeout.assert_called_with()
            sock_mock.settimeout.assert_not_called()

    def test_set_timeout_ewouldblock_exc(self):
        # We expect EWOULDBLOCK to be handled as a timeout.
        with patch.object(self.t, 'sock') as sock_mock:
            sock_mock.gettimeout.return_value = 3
            with pytest.raises(socket.timeout):
                with self.t.having_timeout(5):
                    err = socket.error()
                    err.errno = errno.EWOULDBLOCK
                    raise err

            class DummySocketError(socket.error):
                pass

            # Other socket errors shouldn't be converted.
            with pytest.raises(DummySocketError):
                with self.t.having_timeout(5):
                    raise DummySocketError()


class test_AbstractTransport_connect:
    class Transport(transport._AbstractTransport):

        def _init_socket(self, *args):
            pass

    @pytest.fixture(autouse=True)
    def setup_transport(self, patching):
        self.t = self.Transport('localhost:5672', 10)
        patching('amqp.transport.set_cloexec')

    def test_connect_socket_fails(self):
        with patch('socket.socket', side_effect=socket.error):
            with pytest.raises(socket.error):
                self.t.connect()
        assert self.t.sock is None and self.t.connected is False

    def test_connect_socket_initialization_fails(self):
        with patch('socket.socket', side_effect=socket.error), \
            patch('socket.getaddrinfo',
                  return_value=[
                      (socket.AF_INET, 1, socket.IPPROTO_TCP,
                       '', ('127.0.0.1', 5672)),
                      (socket.AF_INET, 1, socket.IPPROTO_TCP,
                       '', ('127.0.0.2', 5672))
                  ]):
            with pytest.raises(socket.error):
                self.t.connect()
            assert self.t.sock is None and self.t.connected is False

    def test_connect_multiple_addr_entries_fails(self):
        with patch('socket.socket', return_value=MockSocket()) as sock_mock, \
            patch('socket.getaddrinfo',
                  return_value=[
                      (socket.AF_INET, 1, socket.IPPROTO_TCP,
                       '', ('127.0.0.1', 5672)),
                      (socket.AF_INET, 1, socket.IPPROTO_TCP,
                       '', ('127.0.0.2', 5672))
                  ]):
            self.t.sock = Mock()
            self.t.close()
            with patch.object(sock_mock.return_value, 'connect',
                              side_effect=socket.error):
                with pytest.raises(socket.error):
                    self.t.connect()

    def test_connect_multiple_addr_entries_succeed(self):
        with patch('socket.socket', return_value=MockSocket()) as sock_mock, \
            patch('socket.getaddrinfo',
                  return_value=[
                      (socket.AF_INET, 1, socket.IPPROTO_TCP,
                       '', ('127.0.0.1', 5672)),
                      (socket.AF_INET, 1, socket.IPPROTO_TCP,
                       '', ('127.0.0.2', 5672))
                  ]):
            self.t.sock = Mock()
            self.t.close()
            with patch.object(sock_mock.return_value, 'connect',
                              side_effect=(socket.error, None)):
                self.t.connect()

    def test_connect_short_curcuit_on_INET_succeed(self):
        with patch('socket.socket', return_value=MockSocket()), \
            patch('socket.getaddrinfo',
                  side_effect=[
                      [(socket.AF_INET, 1, socket.IPPROTO_TCP,
                        '', ('127.0.0.1', 5672))],
                      [(socket.AF_INET6, 1, socket.IPPROTO_TCP,
                        '', ('::1', 5672))]
                  ]) as getaddrinfo:
            self.t.sock = Mock()
            self.t.close()
            self.t.connect()
            getaddrinfo.assert_called_with(
                'localhost', 5672, socket.AF_INET, ANY, ANY)

    def test_connect_short_curcuit_on_INET_fails(self):
        with patch('socket.socket', return_value=MockSocket()) as sock_mock, \
            patch('socket.getaddrinfo',
                  side_effect=[
                      [(socket.AF_INET, 1, socket.IPPROTO_TCP,
                        '', ('127.0.0.1', 5672))],
                      [(socket.AF_INET6, 1, socket.IPPROTO_TCP,
                        '', ('::1', 5672))]
                  ]) as getaddrinfo:
            self.t.sock = Mock()
            self.t.close()
            with patch.object(sock_mock.return_value, 'connect',
                              side_effect=(socket.error, None)):
                self.t.connect()
            getaddrinfo.assert_has_calls(
                [call('localhost', 5672, addr_type, ANY, ANY)
                 for addr_type in (socket.AF_INET, socket.AF_INET6)])

    def test_connect_getaddrinfo_raises_gaierror(self):
        with patch('socket.getaddrinfo', side_effect=socket.gaierror):
            with pytest.raises(socket.error):
                self.t.connect()

    def test_connect_getaddrinfo_raises_gaierror_once_recovers(self):
        with patch('socket.socket', return_value=MockSocket()), \
            patch('socket.getaddrinfo',
                  side_effect=[
                      socket.gaierror,
                      [(socket.AF_INET6, 1, socket.IPPROTO_TCP,
                        '', ('::1', 5672))]
                  ]):
            self.t.connect()

    def test_connect_survives_not_implemented_set_cloexec(self):
        with patch('socket.socket', return_value=MockSocket()), \
            patch('socket.getaddrinfo',
                  return_value=[(socket.AF_INET, 1, socket.IPPROTO_TCP,
                                 '', ('127.0.0.1', 5672))]):
            with patch('amqp.transport.set_cloexec',
                       side_effect=NotImplementedError) as cloexec_mock:
                self.t.connect()
            assert cloexec_mock.called

    def test_connect_already_connected(self):
        assert not self.t.connected
        with patch('socket.socket', return_value=MockSocket()):
            self.t.connect()
        assert self.t.connected
        sock_obj = self.t.sock
        self.t.connect()
        assert self.t.connected and self.t.sock is sock_obj


class test_SSLTransport:
    class Transport(transport.SSLTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

    def test_repr_disconnected(self):
        assert re.fullmatch(
            r'<SSLTransport: \(disconnected\) at 0x.*>',
            repr(transport.SSLTransport('host', 3))
        )

    def test_repr_connected(self):
        t = transport.SSLTransport('host', 3)
        t.sock = MockSocket()
        re.fullmatch(
            '<SSLTransport: 127.0.0.1:1234 -> 1.2.3.4:5671 at 0x.*>',
            repr(t)
        )

    @pytest.fixture(autouse=True)
    def setup_transport(self):
        self.t = self.Transport(
            'fe80::9a5a:ebff::fecb::ad1c:30', 3, ssl={'foo': 30},
        )

    def test_setup_transport(self):
        sock = self.t.sock = Mock()
        self.t._wrap_socket = Mock()
        self.t._setup_transport()
        self.t._wrap_socket.assert_called_with(sock, foo=30)
        self.t.sock.do_handshake.assert_called_with()
        assert self.t._quick_recv is self.t.sock.read

    def test_wrap_socket(self):
        sock = Mock()
        self.t._wrap_context = Mock()
        self.t._wrap_socket_sni = Mock()
        self.t._wrap_socket(sock, foo=1)
        self.t._wrap_socket_sni.assert_called_with(sock, foo=1)

        self.t._wrap_socket(sock, {'c': 2}, foo=1)
        self.t._wrap_context.assert_called_with(sock, {'foo': 1}, c=2)

    def test_wrap_context(self):
        with patch('ssl.create_default_context',
                   create=True) as create_default_context:
            sock = Mock()
            self.t._wrap_context(sock, {'f': 1}, check_hostname=True, bar=3)
            create_default_context.assert_called_with(bar=3)
            ctx = create_default_context()
            assert ctx.check_hostname
            ctx.wrap_socket.assert_called_with(sock, f=1)

    def test_wrap_socket_sni(self):
        # testing default values of _wrap_socket_sni()
        with patch('ssl.SSLContext') as mock_ssl_context_class:
            sock = Mock()
            context = mock_ssl_context_class()
            context.wrap_socket.return_value = sentinel.WRAPPED_SOCKET
            ret = self.t._wrap_socket_sni(sock)

            context.load_cert_chain.assert_not_called()
            context.load_verify_locations.assert_not_called()
            context.set_ciphers.assert_not_called()
            context.verify_mode.assert_not_called()

            context.load_default_certs.assert_called_with(
                ssl.Purpose.SERVER_AUTH
            )
            context.wrap_socket.assert_called_with(
                sock=sock,
                server_side=False,
                do_handshake_on_connect=False,
                suppress_ragged_eofs=True,
                server_hostname=None
            )
            assert ret == sentinel.WRAPPED_SOCKET

    def test_wrap_socket_sni_certfile(self):
        # testing _wrap_socket_sni() with parameters certfile and keyfile
        with patch('ssl.SSLContext') as mock_ssl_context_class:
            sock = Mock()
            context = mock_ssl_context_class()
            self.t._wrap_socket_sni(
                sock, keyfile=sentinel.KEYFILE, certfile=sentinel.CERTFILE
            )

            context.load_default_certs.assert_called_with(
                ssl.Purpose.SERVER_AUTH
            )
            context.load_cert_chain.assert_called_with(
                sentinel.CERTFILE, sentinel.KEYFILE
            )

    def test_wrap_socket_ca_certs(self):
        # testing _wrap_socket_sni() with parameter ca_certs
        with patch('ssl.SSLContext') as mock_ssl_context_class:
            sock = Mock()
            context = mock_ssl_context_class()
            self.t._wrap_socket_sni(sock, ca_certs=sentinel.CA_CERTS)

            context.load_default_certs.assert_not_called()
            context.load_verify_locations.assert_called_with(sentinel.CA_CERTS)

    def test_wrap_socket_ciphers(self):
        # testing _wrap_socket_sni() with parameter ciphers
        with patch('ssl.SSLContext') as mock_ssl_context_class:
            sock = Mock()
            context = mock_ssl_context_class()
            set_ciphers_method_mock = context.set_ciphers
            self.t._wrap_socket_sni(sock, ciphers=sentinel.CIPHERS)

            set_ciphers_method_mock.assert_called_with(sentinel.CIPHERS)

    def test_wrap_socket_sni_cert_reqs(self):
        with patch('ssl.SSLContext') as mock_ssl_context_class:
            sock = Mock()
            context = mock_ssl_context_class()
            self.t._wrap_socket_sni(sock, cert_reqs=ssl.CERT_NONE)

            context.load_default_certs.assert_not_called()
            assert context.verify_mode == ssl.CERT_NONE

        # testing _wrap_socket_sni() with parameter cert_reqs != ssl.CERT_NONE
        with patch('ssl.SSLContext') as mock_ssl_context_class:
            sock = Mock()
            context = mock_ssl_context_class()
            self.t._wrap_socket_sni(sock, cert_reqs=sentinel.CERT_REQS)

            context.load_default_certs.assert_called_with(
                ssl.Purpose.SERVER_AUTH
            )
            assert context.verify_mode == sentinel.CERT_REQS

        # testing context creation inside _wrap_socket_sni() with parameter 
        # cert_reqs == ssl.CERT_NONE. Previously raised ValueError because
        # code path attempted to set context.verify_mode=ssl.CERT_NONE before
        # setting context.check_hostname = False which raised a ValueError
        with patch('ssl.SSLContext.wrap_socket') as mock_wrap_socket:
            with patch('ssl.SSLContext.load_default_certs') as mock_load_default_certs:
                sock = Mock()
                self.t._wrap_socket_sni(
                    sock, server_side=True, cert_reqs=ssl.CERT_NONE
                )
                mock_load_default_certs.assert_not_called()
                mock_wrap_socket.assert_called_once()

        with patch('ssl.SSLContext.wrap_socket') as mock_wrap_socket:
            with patch('ssl.SSLContext.load_default_certs') as mock_load_default_certs:
                sock = Mock()
                self.t._wrap_socket_sni(
                    sock, server_side=False, cert_reqs=ssl.CERT_NONE
                )
                mock_load_default_certs.assert_not_called()
                mock_wrap_socket.assert_called_once()
        
        with patch('ssl.SSLContext.wrap_socket') as mock_wrap_socket:
            with patch('ssl.SSLContext.load_default_certs') as mock_load_default_certs:
                sock = Mock()
                self.t._wrap_socket_sni(
                    sock, server_side=True, cert_reqs=ssl.CERT_REQUIRED
                )
                mock_load_default_certs.assert_called_with(ssl.Purpose.CLIENT_AUTH)
                mock_wrap_socket.assert_called_once()

        with patch('ssl.SSLContext.wrap_socket') as mock_wrap_socket:
            with patch('ssl.SSLContext.load_default_certs') as mock_load_default_certs:
                sock = Mock()
                self.t._wrap_socket_sni(
                    sock, server_side=False, cert_reqs=ssl.CERT_REQUIRED
                )
                mock_load_default_certs.assert_called_once_with(
                    ssl.Purpose.SERVER_AUTH
                )
                mock_wrap_socket.assert_called_once()

    def test_wrap_socket_sni_setting_sni_header(self):
        # testing _wrap_socket_sni() without parameter server_hostname

        # SSL module supports SNI
        with patch('ssl.SSLContext') as mock_ssl_context_class, \
                patch('ssl.HAS_SNI', new=True):
            sock = Mock()
            context = mock_ssl_context_class()
            self.t._wrap_socket_sni(sock)

            assert context.check_hostname is False

        # SSL module does not support SNI
        with patch('ssl.SSLContext') as mock_ssl_context_class, \
                patch('ssl.HAS_SNI', new=False):
            sock = Mock()
            context = mock_ssl_context_class()
            self.t._wrap_socket_sni(sock)

            assert context.check_hostname is False

        # testing _wrap_socket_sni() with parameter server_hostname

        # SSL module supports SNI
        with patch('ssl.SSLContext') as mock_ssl_context_class, \
                patch('ssl.HAS_SNI', new=True):
            sock = Mock()
            context = mock_ssl_context_class()
            self.t._wrap_socket_sni(
                sock, server_hostname=sentinel.SERVER_HOSTNAME
            )

            context.wrap_socket.assert_called_with(
                sock=sock,
                server_side=False,
                do_handshake_on_connect=False,
                suppress_ragged_eofs=True,
                server_hostname=sentinel.SERVER_HOSTNAME
            )
            assert context.check_hostname is True

        # SSL module does not support SNI
        with patch('ssl.SSLContext') as mock_ssl_context_class, \
                patch('ssl.HAS_SNI', new=False):
            sock = Mock()
            context = mock_ssl_context_class()
            self.t._wrap_socket_sni(
                sock, server_hostname=sentinel.SERVER_HOSTNAME
            )

            context.wrap_socket.assert_called_with(
                sock=sock,
                server_side=False,
                do_handshake_on_connect=False,
                suppress_ragged_eofs=True,
                server_hostname=sentinel.SERVER_HOSTNAME
            )
            assert context.check_hostname is False

    def test_shutdown_transport(self):
        self.t.sock = None
        self.t._shutdown_transport()

        sock = self.t.sock = Mock()
        self.t._shutdown_transport()
        assert self.t.sock is sock.unwrap()

    def test_read_EOF(self):
        self.t.sock = Mock(name='SSLSocket')
        self.t.connected = True
        self.t._quick_recv = Mock(name='recv', return_value='')
        with pytest.raises(IOError,
                           match=r'.*Server unexpectedly closed connection.*'):
            self.t._read(64)

    def test_write_success(self):
        self.t.sock = Mock(name='SSLSocket')
        self.t.sock.write.return_value = 2
        self.t._write('foo')
        self.t.sock.write.assert_called_with(ANY)

    def test_write_socket_closed(self):
        self.t.sock = Mock(name='SSLSocket')
        self.t.sock.write.return_value = ''
        with pytest.raises(IOError,
                           match=r'.*Socket closed.*'):
            self.t._write('foo')

    def test_write_ValueError(self):
        self.t.sock = Mock(name='SSLSocket')
        self.t.sock.write.return_value = 2
        self.t.sock.write.side_effect = ValueError("Some error")
        with pytest.raises(IOError,
                           match=r'.*Socket closed.*'):
            self.t._write('foo')

    def test_read_timeout(self):
        self.t.sock = Mock(name='SSLSocket')
        self.t._quick_recv = Mock(name='recv', return_value='4')
        self.t._quick_recv.side_effect = socket.timeout()
        self.t._read_buffer = MagicMock(return_value='AA')
        with pytest.raises(socket.timeout):
            self.t._read(64)

    def test_read_SSLError(self):
        self.t.sock = Mock(name='SSLSocket')
        self.t._quick_recv = Mock(name='recv', return_value='4')
        self.t._quick_recv.side_effect = socket.timeout()
        self.t._read_buffer = MagicMock(return_value='AA')
        with pytest.raises(socket.timeout):
            self.t._read(64)


class test_TCPTransport:
    class Transport(transport.TCPTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

    def test_repr_disconnected(self):
        assert re.fullmatch(
            r'<TCPTransport: \(disconnected\) at 0x.*>',
            repr(transport.TCPTransport('host', 3))
        )

    def test_repr_connected(self):
        t = transport.SSLTransport('host', 3)
        t.sock = MockSocket()
        re.fullmatch(
            '<TCPTransport: 127.0.0.1:1234 -> 1.2.3.4:5671 at 0x.*>',
            repr(t)
        )

    @pytest.fixture(autouse=True)
    def setup_transport(self):
        self.t = self.Transport('host', 3)

    def test_setup_transport(self):
        self.t.sock = Mock()
        self.t._setup_transport()
        assert self.t._write is self.t.sock.sendall
        assert self.t._read_buffer is not None
        assert self.t._quick_recv is self.t.sock.recv

    def test_read_EOF(self):
        self.t.sock = Mock(name='socket')
        self.t.connected = True
        self.t._quick_recv = Mock(name='recv', return_value='')
        with pytest.raises(IOError,
                           match=r'.*Server unexpectedly closed connection.*'):
            self.t._read(64)

    def test_read_frame__windowstimeout(self, monkeypatch):
        """Make sure BlockingIOError on Windows properly saves off partial reads.

        See https://github.com/celery/py-amqp/issues/320
        """

        self.t._quick_recv = Mock()

        self.t._quick_recv.side_effect = [
            pack('>BHI', 1, 1, 16),
            socket.error(
                10035,
                "A non-blocking socket operation could "
                "not be completed immediately"
            ),
            b'thequickbrownfox',
            b'\xce'
        ]

        monkeypatch.setattr(os, 'name', 'nt')
        monkeypatch.setattr(errno, 'EWOULDBLOCK', 10035)

        assert len(self.t._read_buffer) == 0

        with pytest.raises(socket.timeout):
            self.t.read_frame()

        assert len(self.t._read_buffer) == 7

        frame_type, channel, payload = self.t.read_frame()

        assert len(self.t._read_buffer) == 0
        assert frame_type == 1
        assert channel == 1
        assert payload == b'thequickbrownfox'
