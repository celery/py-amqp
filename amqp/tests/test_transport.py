import mock
import socket

from nose import SkipTest  # noqa

from amqp import transport
try:
    import unittest
    unittest.skip
except AttributeError:
    import unittest2 as unittest  # noqa


class SocketOptions(unittest.TestCase):
    def setUp(self):
        super(SocketOptions, self).setUp()
        self.host = '127.0.0.1'
        self.connect_timeout = 3
        s = socket.socket()
        self.tcp_keepidle = s.getsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE)
        self.tcp_keepintvl = s.getsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL)
        self.tcp_keepcnt = s.getsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT)

        # We don't need an actual connection so we mock a bunch of stuff
        socket.socket.connect = mock.MagicMock()
        transport.TCPTransport._write = mock.MagicMock()
        transport.TCPTransport._setup_transport = mock.MagicMock()
        transport.SSLTransport._write = mock.MagicMock()
        transport.SSLTransport._setup_transport = mock.MagicMock()

    def _get_tcp_default_options(self, soc):
        socket_tcp_opt = {}
        for opt in transport.TCP_OPTS:
            socket_tcp_opt[opt] = soc.getsockopt(socket.SOL_TCP, opt)

        return socket_tcp_opt

    def test_backward_compatibility_tcp_transport(self):
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 False)
        expected = 1
        result = self.transp.sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_NODELAY)
        self.assertEqual(result, expected)

    def test_backward_compatibility_SSL_transport(self):
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 True)
        self.assertNotEqual(self.transp.sock, None)

    def test_use_default_sock_tcp_opts(self):
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 socket_settings={})

        expected = self.transp._get_tcp_socket_default()
        result = self._get_tcp_default_options(self.transp.sock)
        self.assertEqual(result, expected)

    def test_set_single_sock_tcp_opt_tcp_transport(self):
        tcp_keepidle = self.tcp_keepidle + 5
        socket_settings = {socket.TCP_KEEPIDLE: tcp_keepidle}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 False,
                                                 socket_settings)
        expected = tcp_keepidle
        result = self.transp.sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_KEEPIDLE)
        self.assertEqual(result, expected)

    def test_set_single_sock_tcp_opt_SSL_transport(self):
        tcp_keepidle = self.tcp_keepidle + 5
        socket_settings = {socket.TCP_KEEPIDLE: tcp_keepidle}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 True,
                                                 socket_settings)
        expected = tcp_keepidle
        result = self.transp.sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_KEEPIDLE)
        self.assertEqual(result, expected)

    def test_values_are_set(self):
        socket_settings = {
            socket.TCP_KEEPIDLE: 10,
            socket.TCP_KEEPINTVL: 4,
            socket.TCP_KEEPCNT: 2
        }

        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 socket_settings=
                                                 socket_settings)
        expected = socket_settings
        tcp_keepidle = self.transp.sock.getsockopt(socket.SOL_TCP,
                                                   socket.TCP_KEEPIDLE)
        tcp_keepintvl = self.transp.sock.getsockopt(socket.SOL_TCP,
                                                    socket.TCP_KEEPINTVL)
        tcp_keepcnt = self.transp.sock.getsockopt(socket.SOL_TCP,
                                                  socket.TCP_KEEPCNT)
        result = {
            socket.TCP_KEEPIDLE: tcp_keepidle,
            socket.TCP_KEEPINTVL: tcp_keepintvl,
            socket.TCP_KEEPCNT: tcp_keepcnt
        }
        self.assertEqual(result, expected)

    def test_passing_wrong_options(self):
        socket_settings = object()
        with self.assertRaises(TypeError):
            self.transp = transport.create_transport(self.host,
                                                     self.connect_timeout,
                                                     socket_settings=
                                                     socket_settings)

    def test_passing_wrong_protocol_options(self):
        socket_settings = {898989: 5}
        with self.assertRaises(socket.error):
            self.transp = transport.create_transport(self.host,
                                                     self.connect_timeout,
                                                     socket_settings=
                                                     socket_settings)

    def test_passing_wrong_value_options(self):
        socket_settings = {socket.TCP_KEEPINTVL: 'a'.encode()}
        with self.assertRaises(socket.error):
            self.transp = transport.create_transport(self.host,
                                                     self.connect_timeout,
                                                     socket_settings=
                                                     socket_settings)

    def test_passing_value_as_string(self):
        socket_settings = {socket.TCP_KEEPIDLE: '5'.encode()}
        with self.assertRaises(socket.error):
            self.transp = transport.create_transport(self.host,
                                                     self.connect_timeout,
                                                     socket_settings=
                                                     socket_settings)

    def test_passing_tcp_nodelay(self):
        socket_settings = {socket.TCP_NODELAY: 0}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 socket_settings=
                                                 socket_settings)
        expected = 0
        result = self.transp.sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_NODELAY)
        self.assertEqual(result, expected)
