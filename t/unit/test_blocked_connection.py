"""Exercise blocked deadlines through framing, RPCs and TCP/TLS reads."""
import socket
from struct import pack
from unittest.mock import Mock

import pytest

from amqp import Connection, Message, spec
from amqp.channel import Channel
from amqp.exceptions import (ConnectionBlockedTimeout, ConnectionForced,
                             RecoverableConnectionError)
from amqp.method_framing import frame_handler, frame_writer
from amqp.serialization import dumps
from amqp.transport import SSLTransport, TCPTransport


def method_frame(method, arguments=b'', channel=0):
    payload = pack('>HH', *method) + arguments
    return pack('>BHI', 1, channel, len(payload)) + payload + b'\xce'


class ScriptedSocket:
    """A deterministic peer; an unbounded read without data fails the test."""

    def __init__(self, clock):
        self.clock = clock
        self.incoming = b''
        self.timeout = None
        self.closed = False
        self.recv_delay = 0
        self.fragment_size = None
        self.sendall = Mock()
        self.write = Mock(side_effect=len)
        self.shutdown = Mock()
        self.close = Mock(side_effect=lambda: setattr(self, 'closed', True))
        self.unwrap = Mock(side_effect=AssertionError('SSL unwrap would wait'))

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        if self.closed:
            raise OSError('Socket already closed')
        self.timeout = value

    def recv(self, n):
        if self.timeout is not None and self.recv_delay > self.timeout:
            self.clock[0] += self.timeout
            raise socket.timeout()
        self.clock[0] += self.recv_delay
        if self.incoming:
            n = min(n, self.fragment_size or n)
            data, self.incoming = self.incoming[:n], self.incoming[n:]
            return data
        assert self.timeout is not None, 'unbounded read without peer data'
        self.clock[0] += self.timeout
        raise socket.timeout()


@pytest.fixture(params=[TCPTransport, SSLTransport], ids=['tcp', 'tls'])
def peer(request, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('amqp.connection.monotonic', lambda: clock[0])
    monkeypatch.setattr('amqp.transport.monotonic', lambda: clock[0])
    conn = Connection(blocked_connection_timeout=0.75)
    transport = request.param('localhost')
    transport.connected = True
    sock = transport.sock = ScriptedSocket(clock)
    transport._quick_recv = sock.recv
    if request.param is TCPTransport:
        transport._write = sock.sendall
    conn.transport = transport
    conn.frame_writer = frame_writer(conn, transport)
    conn.on_inbound_frame = frame_handler(conn, conn.on_inbound_method)
    channel = Channel(conn, 1)
    return conn, channel, sock, clock


@pytest.mark.parametrize('value', [-1, float('inf'), float('nan'), '1', True])
def test_invalid_timeout(value):
    with pytest.raises(ValueError, match='blocked_connection_timeout'):
        Connection(blocked_connection_timeout=value)


def test_disabled_by_default():
    conn = Connection()
    conn._on_blocked()
    assert conn._blocked_deadline is None


@pytest.mark.parametrize('operation', [
    lambda channel: channel.queue_declare('example'),
    lambda channel: channel.exchange_declare('example', 'direct'),
    lambda channel: channel.confirm_select(),
    lambda channel: channel.open(),
])
def test_rpc_is_bounded_after_receiving_blocked(peer, operation):
    conn, channel, sock, clock = peer
    conn.on_blocked = Mock()
    sock.incoming = method_frame(spec.Connection.Blocked, b'\x00')

    with pytest.raises(ConnectionBlockedTimeout):
        operation(channel)

    assert clock[0] == pytest.approx(0.75)
    conn.on_blocked.assert_called_once()
    sock.unwrap.assert_not_called()
    sock.close.assert_called_once()
    assert not conn.connected
    assert channel.connection is None


def test_unblocked_before_deadline_finishes_rpc(peer):
    conn, channel, sock, clock = peer
    conn.on_unblocked = Mock()
    sock.incoming = b''.join([
        method_frame(spec.Connection.Blocked, b'\x00'),
        method_frame(spec.Connection.Unblocked),
        method_frame(spec.Queue.DeclareOk, b'\x01q' + pack('>LL', 0, 0), 1),
    ])
    result = channel.queue_declare('q')
    assert result.queue == 'q'
    conn.on_unblocked.assert_called_once()
    assert conn._blocked_deadline is None
    assert conn.connected
    sock.close.assert_not_called()


def test_repeated_blocked_does_not_extend_deadline(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    clock[0] = 0.5
    sock.incoming = method_frame(spec.Connection.Blocked, b'\x00')
    conn.drain_events()
    with pytest.raises(ConnectionBlockedTimeout):
        conn.drain_events()
    assert clock[0] == pytest.approx(0.75)


def test_unblock_then_block_starts_new_deadline(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    clock[0] = 0.5
    conn._on_unblocked()
    clock[0] = 1.0
    conn._on_blocked()
    with pytest.raises(ConnectionBlockedTimeout):
        conn.drain_events()
    assert clock[0] == pytest.approx(1.75)


def test_shorter_read_timeout_preserves_blocked_deadline(peer):
    conn, channel, sock, clock = peer
    sock.timeout = 3
    conn._on_blocked()
    with pytest.raises(socket.timeout):
        conn.drain_events(timeout=0.1)
    assert clock[0] == pytest.approx(0.1)
    assert sock.timeout == 3
    assert conn.connected
    with pytest.raises(ConnectionBlockedTimeout):
        conn.drain_events(timeout=2)
    assert clock[0] == pytest.approx(0.75)


def test_nonblocking_poll_does_not_cancel_deadline(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    with pytest.raises(socket.timeout):
        conn.drain_events(timeout=0)
    assert clock[0] == 0
    assert conn._blocked_deadline == 0.75


def test_shorter_transport_read_timeout_is_preserved(peer):
    conn, channel, sock, clock = peer
    conn.transport.read_timeout = 0.1
    conn._on_blocked()
    with pytest.raises(socket.timeout):
        conn.drain_events()
    assert clock[0] == pytest.approx(0.1)
    assert conn.connected


def test_expired_deadline_rejects_even_buffered_unblocked(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    clock[0] = 1
    sock.incoming = method_frame(spec.Connection.Unblocked)
    with pytest.raises(ConnectionBlockedTimeout):
        conn.drain_events()


def test_partial_frame_cannot_extend_deadline(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    sock.incoming = method_frame(spec.Connection.Unblocked)
    sock.fragment_size = 1
    sock.recv_delay = 0.2
    with pytest.raises(ConnectionBlockedTimeout):
        conn.drain_events()
    assert clock[0] == pytest.approx(0.75)


def test_publish_waits_before_writing_on_known_blocked_connection(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    with pytest.raises(ConnectionBlockedTimeout):
        channel.basic_publish(Message(b'body'))
    sock.sendall.assert_not_called()
    sock.write.assert_not_called()


def test_publish_resumes_after_unblocked(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    sock.incoming = method_frame(spec.Connection.Unblocked)
    channel.basic_publish(Message(b'body'))
    assert sock.sendall.called or sock.write.called
    assert conn.connected


def test_publish_timeout_context_does_not_mask_abort(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    with pytest.raises(ConnectionBlockedTimeout):
        channel.basic_publish(Message(b'body'), timeout=1)
    assert clock[0] == pytest.approx(0.75)
    assert sock.closed


def test_collect_known_blocked_connection_skips_ssl_shutdown(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    conn.collect()
    sock.unwrap.assert_not_called()
    sock.close.assert_called_once()
    assert clock[0] == 0
    assert channel.connection is None


@pytest.mark.parametrize('enabled', [False, True])
def test_write_timeout_discards_partial_frames_without_ssl_shutdown(
        peer, enabled):
    conn, channel, sock, clock = peer
    if not enabled:
        conn.blocked_connection_timeout = None
    sock.sendall.side_effect = socket.timeout()
    sock.write.side_effect = socket.timeout()
    with pytest.raises(RecoverableConnectionError, match='publish: timed out'):
        channel.basic_publish(Message(b'body'), timeout=.1)
    sock.unwrap.assert_not_called()
    assert not conn.connected
    assert channel.connection is None


def test_zero_timeout_fails_before_next_write(peer):
    conn, channel, sock, clock = peer
    conn.blocked_connection_timeout = 0
    conn._on_blocked()
    with pytest.raises(ConnectionBlockedTimeout):
        channel.queue_declare('q')
    assert clock[0] == 0
    sock.sendall.assert_not_called()
    sock.write.assert_not_called()


def test_callback_exception_does_not_disarm_deadline(peer):
    conn, channel, sock, clock = peer
    conn.on_blocked = Mock(side_effect=RuntimeError('application callback'))
    with pytest.raises(RuntimeError):
        conn._on_blocked()
    with pytest.raises(ConnectionBlockedTimeout):
        conn.drain_events()
    assert clock[0] == pytest.approx(0.75)


def test_explicit_close_of_blocked_connection_does_not_wait(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    sock.incoming = method_frame(spec.Connection.Unblocked)
    conn.close()
    assert clock[0] == 0
    assert not conn.connected
    sock.unwrap.assert_not_called()


def test_close_processes_a_new_blocked_notification(peer):
    conn, channel, sock, clock = peer
    sock.incoming = method_frame(spec.Connection.Blocked, b'\x00')
    with pytest.raises(ConnectionBlockedTimeout):
        conn.close()
    assert clock[0] == pytest.approx(.75)
    assert not conn.connected


def test_broker_close_preserves_reason_while_blocked(peer):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    sock.incoming = method_frame(
        spec.Connection.Close, dumps('BsBB', (320, 'maintenance', 0, 0)))
    with pytest.raises(ConnectionForced, match='maintenance'):
        conn.drain_events()
    assert clock[0] == 0
    assert not conn.connected
    sock.unwrap.assert_not_called()


@pytest.mark.parametrize('close_connection', [False, True])
def test_unblocked_callback_disposal_is_recoverable(peer, close_connection):
    conn, channel, sock, clock = peer
    conn._on_blocked()
    conn.on_unblocked = ((lambda: conn.collect(force=True))
                         if close_connection else channel.collect)
    sock.incoming = method_frame(spec.Connection.Unblocked)
    with pytest.raises(RecoverableConnectionError, match='already closed'):
        channel.basic_publish(Message(b'body'))
    sock.sendall.assert_not_called()
    sock.write.assert_not_called()


@pytest.mark.parametrize('close_connection', [False, True])
def test_publish_probe_callback_disposal_is_recoverable(
        peer, close_connection):
    conn, channel, sock, clock = peer
    conn.client_properties['capabilities'] = {'connection.blocked': True}
    conn._on_blocked()
    conn.on_unblocked = ((lambda: conn.collect(force=True))
                         if close_connection else channel.collect)
    sock.incoming = method_frame(spec.Connection.Unblocked)
    with pytest.raises(RecoverableConnectionError, match='connection closed'):
        channel.basic_publish(Message(b'body'))
    sock.sendall.assert_not_called()
    sock.write.assert_not_called()
