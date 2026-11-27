"""Publication budgets across framing and blocking transport operations."""
import socket
from unittest.mock import Mock

import pytest

from amqp import Connection, Message, OperationTimeout, operation_timeout, spec
from amqp.exceptions import (ConnectionBlockedTimeout,
                             RecoverableConnectionError)
from amqp.utils import operation_deadline
from t.unit.test_blocked_connection import method_frame, peer  # noqa: F401


@pytest.fixture
def timed_peer(peer, monkeypatch):  # noqa: F811
    conn, channel, sock, clock = peer
    conn.blocked_connection_timeout = None
    monkeypatch.setattr('amqp.utils.monotonic', lambda: clock[0])
    return peer


@pytest.mark.parametrize('operation', [
    lambda c: c.queue_declare('q'),
    lambda c: c.exchange_declare('e', 'direct'),
    lambda c: c.queue_bind('q', 'e', 'key'),
    lambda c: c.confirm_select(),
    lambda c: c.open(),
])
def test_rpc_without_blocked_notification_is_bounded(timed_peer, operation):
    conn, channel, sock, clock = timed_peer
    with pytest.raises(OperationTimeout), operation_timeout(.2):
        operation(channel)
    assert clock[0] == pytest.approx(.2)
    assert not conn.connected
    assert channel.connection is None
    sock.unwrap.assert_not_called()


@pytest.mark.parametrize('blocked, expected', [
    (.05, ConnectionBlockedTimeout), (.5, OperationTimeout),
])
def test_earlier_deadline_wins(timed_peer, blocked, expected):
    conn, channel, sock, clock = timed_peer
    conn.blocked_connection_timeout = blocked
    conn._on_blocked()
    with pytest.raises(expected), operation_timeout(.2):
        channel.queue_declare('q')
    assert clock[0] == pytest.approx(min(blocked, .2))


def test_partial_reads_cannot_reset_budget(timed_peer):
    conn, channel, sock, clock = timed_peer
    sock.incoming = method_frame(spec.Connection.Unblocked)
    sock.fragment_size = 1
    sock.recv_delay = .06
    with pytest.raises(OperationTimeout), operation_timeout(.2):
        channel.queue_declare('q')
    assert clock[0] == pytest.approx(.2)
    assert not conn.connected


def test_multiframe_write_uses_remaining_budget(timed_peer):
    conn, channel, sock, clock = timed_peer

    def write(data):
        timeout = sock.gettimeout()
        assert timeout is not None
        clock[0] += min(.06, timeout)
        if timeout < .06:
            raise socket.timeout()
        return len(data)

    sock.sendall.side_effect = sock.write.side_effect = write
    with pytest.raises(OperationTimeout), operation_timeout(.1):
        channel.basic_publish(Message(b'x' * (conn.frame_max * 3)))
    assert clock[0] == pytest.approx(.1)
    assert not conn.connected
    sock.unwrap.assert_not_called()


def test_shorter_write_timeout_is_preserved(timed_peer):
    conn, channel, sock, clock = timed_peer
    conn.transport.write_timeout = .03

    def write(data):
        assert sock.gettimeout() == pytest.approx(.03)
        clock[0] += .03
        raise socket.timeout()

    sock.sendall.side_effect = sock.write.side_effect = write
    with pytest.raises(RecoverableConnectionError) as info:
        with operation_timeout(.2):
            channel.basic_publish(Message(b'body'))
    assert not isinstance(info.value, OperationTimeout)
    assert clock[0] == pytest.approx(.03)
    assert not conn.connected


def test_success_restores_timeout_and_does_not_discard(timed_peer):
    conn, channel, sock, clock = timed_peer
    sock.timeout = 9
    with operation_timeout(.2):
        channel.basic_publish(Message(b'body'))
    assert sock.timeout == 9
    assert operation_deadline() is None
    assert conn.connected


def test_expiry_precedes_lazy_connection(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('amqp.utils.monotonic', lambda: clock[0])
    conn = Connection()
    conn.Transport = Mock()
    with pytest.raises(OperationTimeout), operation_timeout(.1):
        clock[0] = .2
        conn.drain_events()
    conn.Transport.assert_not_called()


def test_dns_return_after_deadline_does_not_connect(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('amqp.utils.monotonic', lambda: clock[0])

    def resolve(*args):
        clock[0] = .2
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '',
                 ('127.0.0.1', 5672))]

    monkeypatch.setattr('amqp.transport.socket.getaddrinfo', resolve)
    factory = Mock()
    monkeypatch.setattr('amqp.transport.socket.socket', factory)
    conn = Connection('broker.example')
    with pytest.raises(OperationTimeout), operation_timeout(.1):
        conn.connect()
    factory.assert_not_called()
    assert not conn.connected
    assert clock[0] == .2


def test_connect_addresses_share_the_budget(monkeypatch):
    clock = [0.0]
    observed = []
    sockets = []
    monkeypatch.setattr('amqp.utils.monotonic', lambda: clock[0])
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', p))
                 for p in [5672, 5673, 5674]]
    monkeypatch.setattr(
        'amqp.transport.socket.getaddrinfo', lambda *a: addresses)
    monkeypatch.setattr('amqp.transport.set_cloexec', lambda *a: None)

    def make_socket(*args):
        sock = Mock()
        sock.settimeout.side_effect = lambda value: observed.append(value)

        def connect(address):
            remaining = observed[-1]
            clock[0] += min(remaining, .06)
            raise socket.timeout()

        sock.connect.side_effect = connect
        sockets.append(sock)
        return sock

    monkeypatch.setattr('amqp.transport.socket.socket', make_socket)
    conn = Connection('broker.example', connect_timeout=5)
    with pytest.raises(OperationTimeout), operation_timeout(.1):
        conn.connect()
    assert observed == pytest.approx([.1, .04])
    assert clock[0] == pytest.approx(.1)
    assert not conn.connected
    assert all(sock.close.called for sock in sockets)


@pytest.mark.parametrize('context_options', [False, True])
@pytest.mark.parametrize('setup_elapsed', [.04, .15])
def test_tls_setup_consumes_budget_before_implicit_handshake(
        monkeypatch, context_options, setup_elapsed):
    from amqp.transport import SSLTransport

    clock = [0.0]
    monkeypatch.setattr('amqp.utils.monotonic', lambda: clock[0])
    sock = Mock()
    sock.gettimeout.return_value = 1
    context = Mock()

    def configure(*args, **kwargs):
        clock[0] += setup_elapsed
        return context

    monkeypatch.setattr('amqp.transport.ssl.create_default_context', configure)
    monkeypatch.setattr(
        'amqp.transport.ssl.SSLContext', Mock(return_value=context))
    context.load_cert_chain.side_effect = configure
    transport = SSLTransport('localhost')

    def wrap():
        if context_options:
            return transport._wrap_context(
                sock, {'do_handshake_on_connect': True}, check_hostname=False)
        return transport._wrap_socket_sni(
            sock, certfile='cert.pem',
            do_handshake_on_connect=True, cert_reqs=0)

    if setup_elapsed > .1:
        with pytest.raises(OperationTimeout), operation_timeout(.1):
            wrap()
        context.wrap_socket.assert_not_called()
    else:
        with operation_timeout(.1):
            wrap()
        context.wrap_socket.assert_called_once()
        sock.settimeout.assert_called_once_with(
            pytest.approx(.1 - setup_elapsed))
