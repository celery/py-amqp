from __future__ import absolute_import, unicode_literals

import errno
import socket

from struct import pack

from amqp import transport
from amqp.exceptions import UnexpectedFrame

from .case import Case, Mock, patch


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


class SocketOptions(Case):

    def setUp(self):
        super(SocketOptions, self).setUp()
        self.host = '127.0.0.1'
        self.connect_timeout = 3
        self.socket = MockSocket()
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            self.patch('fcntl.fcntl')
        socket = self.patch('socket.socket')
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

        self.patch('amqp.transport.TCPTransport._write')
        self.patch('amqp.transport.TCPTransport._setup_transport')
        self.patch('amqp.transport.SSLTransport._write')
        self.patch('amqp.transport.SSLTransport._setup_transport')

    def test_backward_compatibility_tcp_transport(self):
        self.transp = transport.Transport(
            self.host, self.connect_timeout, ssl=False,
        )
        self.transp.connect()
        expected = 1
        result = self.socket.getsockopt(socket.SOL_TCP, socket.TCP_NODELAY)
        self.assertEqual(result, expected)

    def test_backward_compatibility_SSL_transport(self):
        self.transp = transport.Transport(
            self.host, self.connect_timeout, ssl=True,
        )
        self.assertIsNotNone(self.transp.sslopts)
        self.transp.connect()
        self.assertIsNotNone(self.transp.sock)

    def test_use_default_sock_tcp_opts(self):
        self.transp = transport.Transport(
            self.host, self.connect_timeout, socket_settings={},
        )
        self.transp.connect()
        self.assertIn(
            socket.TCP_NODELAY,
            self.transp._get_tcp_socket_defaults(self.transp.sock),
        )

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
        self.assertEqual(result, expected)

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
        self.assertEqual(result, expected)

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
        self.assertEqual(result, expected)

    def test_passing_wrong_options(self):
        socket_settings = object()
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        with self.assertRaises(TypeError):
            self.transp.connect()

    def test_passing_wrong_value_options(self):
        socket_settings = {TCP_KEEPINTVL: 'a'.encode()}
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        with self.assertRaises(socket.error):
            self.transp.connect()

    def test_passing_value_as_string(self):
        socket_settings = {TCP_KEEPIDLE: '5'.encode()}
        self.transp = transport.Transport(
            self.host, self.connect_timeout,
            socket_settings=socket_settings,
        )
        with self.assertRaises(socket.error):
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
        self.assertEqual(result, expected)


class test_AbstractTransport(Case):

    class Transport(transport._AbstractTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

    def setup(self):
        self.t = self.Transport('localhost:5672', 10)
        self.t.connect()

    def test_port(self):
        assert self.Transport('localhost').port == 5672
        assert self.Transport('localhost:5672').port == 5672
        assert self.Transport('[fe80::1]:5432').port == 5432

    def test_read(self):
        with self.assertRaises(NotImplementedError):
            self.t._read(1024)

    def test_setup_transport(self):
        self.t._setup_transport()

    def test_shutdown_transport(self):
        self.t._shutdown_transport()

    def test_write(self):
        with self.assertRaises(NotImplementedError):
            self.t._write('foo')

    def test_close(self):
        sock = self.t.sock = Mock()
        self.t.close()
        sock.shutdown.assert_called_with(socket.SHUT_RDWR)
        sock.close.assert_called_with()
        self.assertIsNone(self.t.sock)
        self.t.close()

    def test_read_frame__timeout(self):
        self.t._read = Mock()
        self.t._read.side_effect = socket.timeout()
        with self.assertRaises(socket.timeout):
            self.t.read_frame()

    def test_read_frame__SSLError(self):
        self.t._read = Mock()
        self.t._read.side_effect = transport.SSLError('timed out')
        with self.assertRaises(socket.timeout):
            self.t.read_frame()

    def test_read_frame__EINTR(self):
        self.t._read = Mock()
        self.t.connected = True
        exc = OSError()
        exc.errno = errno.EINTR
        self.t._read.side_effect = exc
        with self.assertRaises(OSError):
            self.t.read_frame()
        self.assertTrue(self.t.connected)

    def test_read_frame__EBADF(self):
        self.t._read = Mock()
        self.t.connected = True
        exc = OSError()
        exc.errno = errno.EBADF
        self.t._read.side_effect = exc
        with self.assertRaises(OSError):
            self.t.read_frame()
        self.assertFalse(self.t.connected)

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
        with self.assertRaises(UnexpectedFrame):
            self.t.read_frame()

    def test_write__success(self):
        self.t._write = Mock()
        self.t.write('foo')
        self.t._write.assert_called_with('foo')

    def test_write__socket_timeout(self):
        self.t._write = Mock()
        self.t._write.side_effect = socket.timeout
        with self.assertRaises(socket.timeout):
            self.t.write('foo')

    def test_write__EINTR(self):
        self.t.connected = True
        self.t._write = Mock()
        exc = OSError()
        exc.errno = errno.EINTR
        self.t._write.side_effect = exc
        with self.assertRaises(OSError):
            self.t.write('foo')
        self.assertTrue(self.t.connected)
        exc.errno = errno.EBADF
        with self.assertRaises(OSError):
            self.t.write('foo')
        self.assertFalse(self.t.connected)


class test_SSLTransport(Case):

    class Transport(transport.SSLTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

    def setup(self):
        self.t = self.Transport(
            'fe80::9a5a:ebff::fecb::ad1c:30', 3, ssl={'foo': 30},
        )

    def test_setup_transport(self):
        sock = self.t.sock = Mock()
        self.t._wrap_socket = Mock()
        self.t._setup_transport()
        self.t._wrap_socket.assert_called_with(sock, foo=30)
        self.t.sock.do_handshake.assert_called_with()
        self.assertIs(self.t._quick_recv, self.t.sock.read)

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
        self.assertTrue(ctx.check_hostname)
        ctx.wrap_socket.assert_called_with(sock, f=1)

    def test_shutdown_transport(self):
        self.t.sock = None
        self.t._shutdown_transport()
        self.t.sock = object()
        self.t._shutdown_transport()
        sock = self.t.sock = Mock()
        self.t._shutdown_transport()
        self.assertIs(self.t.sock, sock.unwrap())


class test_TCPTransport(Case):

    class Transport(transport.TCPTransport):

        def _connect(self, *args):
            pass

        def _init_socket(self, *args):
            pass

    def setup(self):
        self.t = self.Transport('host', 3)

    def test_setup_transport(self):
        self.t.sock = Mock()
        self.t._setup_transport()
        self.assertIs(self.t._write, self.t.sock.sendall)
        self.assertIsNotNone(self.t._read_buffer)
        self.assertIs(self.t._quick_recv, self.t.sock.recv)
