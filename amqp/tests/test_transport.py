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
        self.host = '127.0.0.1:80'
        self.connect_timeout = 3
        s = socket.socket()
        self.default_tcp_val = self._get_tcp_options_from_a_socket(s)

    def _get_tcp_options_from_a_socket(self, soc):
        socket_tcp_opts = {}

        socket_tcp_opts['TCP_KEEPIDLE'] = \
            soc.getsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE)
        socket_tcp_opts['TCP_KEEPINTVL'] = \
            soc.getsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL)
        socket_tcp_opts['TCP_KEEPCNT'] = \
            soc.getsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT)

        return socket_tcp_opts

    def test_backward_compatibility_tcp_transport(self):
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 False)
        expected = 1
        result = self.transp.sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_NODELAY)
        self.assertEqual(result, expected)
        self.transp.close()

    def test_backward_compatibility_SSL_transport(self):
        transport.SSLTransport._write = mock.MagicMock()
        transport.SSLTransport._setup_transport = mock.MagicMock()
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 True)
        self.assertNotEqual(self.transp.sock, None)
        self.transp.close()

    def test_use_default_sock_tcp_opts(self):
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 keepalive_settings={})

        result = self._get_tcp_options_from_a_socket(self.transp.sock)
        expected = self.default_tcp_val
        self.assertEqual(result, expected)
        self.transp.close()

    def test_set_single_sock_tcp_opt_tcp_transport(self):
        tcp_keepidle = self.default_tcp_val['TCP_KEEPIDLE'] + 5
        keepalive_settings = {'TCP_KEEPIDLE': tcp_keepidle}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 False,
                                                 keepalive_settings)
        expected = tcp_keepidle
        result = self.transp.sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_KEEPIDLE)
        self.assertEqual(result, expected)
        self.transp.close()

    def test_set_single_sock_tcp_opt_SSL_transport(self):
        transport.SSLTransport._write = mock.MagicMock()
        transport.SSLTransport._setup_transport = mock.MagicMock()
        tcp_keepidle = self.default_tcp_val['TCP_KEEPIDLE'] + 5
        keepalive_settings = {'TCP_KEEPIDLE': tcp_keepidle}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 True,
                                                 keepalive_settings)
        expected = tcp_keepidle
        result = self.transp.sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_KEEPIDLE)
        self.assertEqual(result, expected)
        self.transp.close()

    def test_all_values_are_set(self):
        keepalive_settings = {'TCP_KEEPIDLE': 10,
                              'TCP_KEEPINTVL': 4,
                              'TCP_KEEPCNT': 2}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 keepalive_settings=
                                                 keepalive_settings)
        expected = keepalive_settings
        result = self._get_tcp_options_from_a_socket(self.transp.sock)
        self.assertEqual(result, expected)
        self.transp.close()

    def test_pasing_wrong_options_and_values(self):
        keepalive_settings = object()
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 keepalive_settings=
                                                 keepalive_settings)
        expected = self.default_tcp_val
        result = self._get_tcp_options_from_a_socket(self.transp.sock)
        self.assertEqual(result, expected)
        self.transp.close()

        keepalive_settings = {'TCP_KEEPIDLE': 'aa'}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 keepalive_settings=
                                                 keepalive_settings)
        result = self._get_tcp_options_from_a_socket(self.transp.sock)
        self.assertEqual(result, expected)
        self.transp.close()

        keepalive_settings = {'TCP_FAKEIDLE': 5}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 keepalive_settings=
                                                 keepalive_settings)
        result = self._get_tcp_options_from_a_socket(self.transp.sock)
        self.assertEqual(result, expected)
        self.transp.close()

    def test_passing_value_as_string(self):

        keepalive_settings = {'TCP_KEEPIDLE': '5'}
        self.transp = transport.create_transport(self.host,
                                                 self.connect_timeout,
                                                 keepalive_settings=
                                                 keepalive_settings)
        expected = 5
        result = self.transp.sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_KEEPIDLE)
        self.assertEqual(result, expected)
        self.transp.close()
