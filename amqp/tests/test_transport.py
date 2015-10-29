from __future__ import absolute_import

import asyncio
import socket

from amqp import transport
from amqp.tests.case import Case, Mock, patch


class MockSocket(object):
    options = {}

    def setsockopt(self, family, key, value):
        if not isinstance(value, int):
            raise socket.error()
        self.options[key] = value

    def getsockopt(self, family, key):
        return self.options.get(key, 0)

def run(coro):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)

TCP_KEEPIDLE = 4
TCP_KEEPINTVL = 5
TCP_KEEPCNT = 6


class SocketOptions(Case):

    def setUp(self):
        super(SocketOptions, self).setUp()
        self.host = '127.0.0.1'
        self.socket = MockSocket()
        fcntl_ctx = patch('fcntl.fcntl')
        fcntl_ctx.start()
        self.addCleanup(fcntl_ctx.stop)
        socket_ctx = patch('socket.socket')
        socket = socket_ctx.start()
        self.addCleanup(socket_ctx.stop)
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

        # We don't need an actual connection so we mock a bunch of stuff
        def get_mock_coro(return_value):
            @asyncio.coroutine
            def mock_coro(*args, **kwargs):
                return return_value

            return Mock(wraps=mock_coro)
        transport.AMQPTransport._write = Mock()
        transport.AMQPTransport.connect = get_mock_coro("CONNECT")

    def test_backward_compatibility_tcp_transport(self):
        self.transp = run(transport.create_transport(
            self.host, ssl=False,
        ))
        expected = 1
        result = self.socket.getsockopt(socket.SOL_TCP, socket.TCP_NODELAY)
        self.assertEqual(result, expected)

    def test_backward_compatibility_SSL_transport(self):
        self.transp = run(transport.create_transport(
            self.host, ssl=True,
        ))
        self.assertIsNotNone(self.transp.sock)

    def test_use_default_sock_tcp_opts(self):
        self.transp = run(transport.create_transport(
            self.host, socket_settings={},
        ))
        self.assertIn(
            socket.TCP_NODELAY,
            self.transp._get_tcp_socket_defaults(self.transp.sock),
        )

    def test_set_single_sock_tcp_opt_tcp_transport(self):
        tcp_keepidle = self.tcp_keepidle + 5
        socket_settings = {TCP_KEEPIDLE: tcp_keepidle}
        self.transp = run(transport.create_transport(
            self.host,
            ssl=False, socket_settings=socket_settings,
        ))
        expected = tcp_keepidle
        result = self.socket.getsockopt(socket.SOL_TCP, TCP_KEEPIDLE)
        self.assertEqual(result, expected)

    def test_set_single_sock_tcp_opt_SSL_transport(self):
        self.tcp_keepidle += 5
        socket_settings = {TCP_KEEPIDLE: self.tcp_keepidle}
        self.transp = run(transport.create_transport(
            self.host,
            ssl=True, socket_settings=socket_settings,
        ))
        expected = self.tcp_keepidle
        result = self.socket.getsockopt(socket.SOL_TCP, TCP_KEEPIDLE)
        self.assertEqual(result, expected)

    def test_values_are_set(self):
        import pdb;pdb.set_trace()
        socket_settings = {
            TCP_KEEPIDLE: 10,
            TCP_KEEPINTVL: 4,
            TCP_KEEPCNT: 2
        }

        self.transp = run(transport.create_transport(
            self.host,
            socket_settings=socket_settings,
        ))
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
        with self.assertRaises(TypeError):
            self.transp = run(transport.create_transport(
                self.host,
                socket_settings=socket_settings,
            ))

    def test_passing_wrong_value_options(self):
        socket_settings = {TCP_KEEPINTVL: 'a'.encode()}
        with self.assertRaises(socket.error):
            self.transp = run(transport.create_transport(
                self.host,
                socket_settings=socket_settings,
            ))

    def test_passing_value_as_string(self):
        socket_settings = {TCP_KEEPIDLE: '5'.encode()}
        with self.assertRaises(socket.error):
            self.transp = run(transport.create_transport(
                self.host,
                socket_settings=socket_settings,
            ))

    def test_passing_tcp_nodelay(self):
        import pdb;pdb.set_trace()
        socket_settings = {socket.TCP_NODELAY: 0}
        self.transp = run(transport.create_transport(
            self.host,
            socket_settings=socket_settings,
        ))
        expected = 0
        result = self.socket.getsockopt(socket.SOL_TCP, socket.TCP_NODELAY)
        self.assertEqual(result, expected)

