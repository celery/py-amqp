from __future__ import absolute_import, unicode_literals

import errno
import socket
import pytest

from struct import pack

from case import Mock, patch

from amqp import transport
from amqp.exceptions import UnexpectedFrame


class MockSocket(object):
    options = {}

    def setsockopt(self, family, key, value):
        if not isinstance(value, int):
            raise socket.error()
        self.options[key] = value

    def getsockopt(self, family, key):
        return self.options.get(key, 0)


TCP_KEEPIDLE = 4
TCP_KEEPINTVL = 5
TCP_KEEPCNT = 6


class test_socket_options:

    @pytest.fixture(autouse=True)
    def setup_self(self, patching):
        self.host = '127.0.0.1'
        self.connect_timeout = 3
        self.socket = MockSocket()
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            patching('fcntl.fcntl')
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
        socket_settings = {TCP_KEEPINTVL: 'a'.encode()}
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        with pytest.raises(socket.error):
            self.transp.connect()

    def test_passing_value_as_string(self):
        socket_settings = {TCP_KEEPIDLE: '5'.encode()}
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


class test_AbstractTransport:

    class Transport(transport._AbstractTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

    @pytest.fixture(autouse=True)
    def setup_transport(self):
        self.t = self.Transport('localhost:5672', 10)
        self.t.connect()

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
        assert self.t.sock is None
        self.t.close()

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
        self.t._read.return_value = pack(b'>BHI', 1, 1, 16)
        self.t._read.side_effect = on_read1

        self.t.read_frame()
        self.t._read.return_value = pack(b'>BHI', 1, 1, 16)
        self.t._read.side_effect = on_read1
        checksum[0] = b'\x13'
        with pytest.raises(UnexpectedFrame):
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


class test_SSLTransport:

    class Transport(transport.SSLTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

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

    @patch('ssl.wrap_socket', create=True)
    def test_wrap_socket(self, wrap_socket):
        sock = Mock()
        self.t._wrap_context = Mock()
        self.t._wrap_socket(sock, foo=1)
        wrap_socket.assert_called_with(sock, foo=1)

        self.t._wrap_socket(sock, {'c': 2}, foo=1)
        self.t._wrap_context.assert_called_with(sock, {'foo': 1}, c=2)

    @patch('ssl.create_default_context', create=True)
    def test_wrap_context(self, create_default_context):
        sock = Mock()
        self.t._wrap_context(sock, {'f': 1}, check_hostname=True, bar=3)
        create_default_context.assert_called_with(bar=3)
        ctx = create_default_context()
        assert ctx.check_hostname
        ctx.wrap_socket.assert_called_with(sock, f=1)

    def test_shutdown_transport(self):
        self.t.sock = None
        self.t._shutdown_transport()
        self.t.sock = object()
        self.t._shutdown_transport()
        sock = self.t.sock = Mock()
        self.t._shutdown_transport()
        assert self.t.sock is sock.unwrap()


class test_TCPTransport:

    class Transport(transport.TCPTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

    @pytest.fixture(autouse=True)
    def setup_transport(self):
        self.t = self.Transport('host', 3)

    def test_setup_transport(self):
        self.t.sock = Mock()
        self.t._setup_transport()
        assert self.t._write is self.t.sock.sendall
        assert self.t._read_buffer is not None
        assert self.t._quick_recv is self.t.sock.recv
