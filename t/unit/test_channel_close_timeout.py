"""A received channel error must survive bounded protocol cleanup."""
import socket
from struct import unpack_from
from unittest.mock import Mock

import pytest

from amqp import OperationTimeout, operation_timeout, spec
from amqp.channel import Channel
from amqp.exceptions import NotFound, PreconditionFailed, ResourceLocked
from amqp.serialization import dumps
from t.unit.test_blocked_connection import method_frame, peer  # noqa: F401


@pytest.fixture
def subject(peer, monkeypatch):  # noqa: F811
    conn, channel, sock, clock = peer
    monkeypatch.setattr('amqp.utils.monotonic', lambda: clock[0])
    channel.is_open = True
    return conn, channel, sock, clock


def close_frame(code=406, reason='queue declaration mismatch'):
    return method_frame(
        spec.Channel.Close, dumps('BsBB', (code, reason, 50, 10)), 1)


def respond_to_open(sock):
    written = []

    def write(data):
        method = unpack_from('>HH', data, 7)
        written.append(method)
        if method == spec.Channel.Open:
            sock.incoming += method_frame(spec.Channel.OpenOk, channel=1)
        return len(data)

    sock.sendall.side_effect = sock.write.side_effect = write
    return written


def assert_error(exc, code=406, reason='queue declaration mismatch'):
    assert exc.reply_code == code
    assert exc.reply_text == reason
    assert exc.method_sig == spec.Queue.Declare


def assert_disposed(conn, channel, sock):
    assert not conn.connected
    assert conn.channels is None
    assert channel.connection is None
    assert sock.closed
    sock.unwrap.assert_not_called()


@pytest.mark.parametrize('code,error', [
    (404, NotFound), (405, ResourceLocked), (406, PreconditionFailed),
])
@pytest.mark.parametrize('budget', [None, .05])
def test_known_blocked_channel_error_is_immediate(
        subject, code, error, budget):
    conn, channel, sock, clock = subject
    sibling = Channel(conn, 2)
    sock.incoming = (
        method_frame(spec.Connection.Blocked, b'\x00') + close_frame(code))
    with pytest.raises(error) as info, operation_timeout(budget):
        conn.drain_events()
        conn.drain_events()
    assert_error(info.value, code)
    assert info.value.connection_usable is False
    assert clock[0] == 0
    assert_disposed(conn, channel, sock)
    assert sibling.connection is None
    sock.sendall.assert_not_called()
    sock.write.assert_not_called()


def test_known_blocked_channel_error_does_not_wait_for_queued_unblock(subject):
    conn, channel, sock, clock = subject
    conn._on_blocked()
    unblock = method_frame(spec.Connection.Unblocked)
    sock.incoming = close_frame() + unblock
    with pytest.raises(PreconditionFailed) as info:
        conn.drain_events()
    assert_error(info.value)
    assert info.value.connection_usable is False
    assert sock.incoming == unblock
    assert clock[0] == 0
    assert_disposed(conn, channel, sock)
    sock.sendall.assert_not_called()
    sock.write.assert_not_called()


@pytest.mark.parametrize('unblocked', [False, True])
@pytest.mark.parametrize('budget', [None, .05])
@pytest.mark.parametrize('code,error', [
    (405, ResourceLocked), (406, PreconditionFailed),
])
def test_nonblocked_channel_error_still_acknowledges_and_revives(
        subject, unblocked, budget, code, error):
    conn, channel, sock, clock = subject
    if unblocked:
        conn._on_blocked()
        sock.incoming = method_frame(spec.Connection.Unblocked)
        conn.drain_events()
    else:
        conn.blocked_connection_timeout = None
        conn._on_blocked()
    sock.incoming = close_frame(code)
    written = respond_to_open(sock)
    with pytest.raises(error) as info, operation_timeout(budget):
        conn.drain_events()
    assert_error(info.value, code)
    assert not hasattr(info.value, 'connection_usable')
    assert conn.connected
    assert channel.is_open
    assert clock[0] == 0
    assert written == [
        spec.Channel.CloseOk, spec.Channel.Open,
    ]
    sock.close.assert_not_called()


@pytest.mark.parametrize('channel_closing,connection_closing', [
    (True, False), (False, True), (True, True),
])
def test_known_blocked_channel_error_during_close_is_not_raised(
        subject, channel_closing, connection_closing):
    conn, channel, sock, clock = subject
    conn._on_blocked()
    channel.is_closing = channel_closing
    conn.is_closing = connection_closing
    sock.incoming = close_frame()
    conn.drain_events()
    assert clock[0] == 0
    assert_disposed(conn, channel, sock)
    sock.sendall.assert_not_called()
    sock.write.assert_not_called()


@pytest.mark.parametrize('unblocked', [False, True])
@pytest.mark.parametrize('stall', ['close_ok', 'revival'])
@pytest.mark.parametrize('code,error', [
    (405, ResourceLocked), (406, PreconditionFailed),
])
def test_operation_timeout_during_channel_error_cleanup_preserves_error(
        subject, unblocked, stall, code, error):
    conn, channel, sock, clock = subject
    if unblocked:
        conn._on_blocked()
        sock.incoming = method_frame(spec.Connection.Unblocked)
        conn.drain_events()
    else:
        conn.blocked_connection_timeout = None
    if stall == 'close_ok':
        def write(data):
            clock[0] += sock.gettimeout()
            raise socket.timeout()

        sock.sendall.side_effect = sock.write.side_effect = write
    sock.incoming = close_frame(code)
    with pytest.raises(error) as info, operation_timeout(.05):
        conn.drain_events()
    assert_error(info.value, code)
    assert info.value.connection_usable is False
    assert isinstance(info.value.__cause__, OperationTimeout)
    assert clock[0] == pytest.approx(.05)
    assert_disposed(conn, channel, sock)


@pytest.mark.parametrize('mode', ['disabled', 'blocked_option', 'operation'])
def test_shorter_socket_timeout_error_precedence_requires_opt_in(
        subject, mode):
    conn, channel, sock, clock = subject
    if mode != 'blocked_option':
        conn.blocked_connection_timeout = None
    conn.transport.write_timeout = .02

    def write(data):
        clock[0] += .02
        raise socket.timeout('shorter socket timeout')

    sock.sendall.side_effect = sock.write.side_effect = write
    sock.incoming = close_frame()
    expected = socket.timeout if mode == 'disabled' else PreconditionFailed
    budget = .05 if mode == 'operation' else None
    with pytest.raises(expected) as info, operation_timeout(budget):
        conn.drain_events()
    assert clock[0] == pytest.approx(.02)
    if mode == 'disabled':
        assert conn.connected
        sock.close.assert_not_called()
    else:
        assert_error(info.value)
        assert info.value.connection_usable is False
        assert isinstance(info.value.__cause__, socket.timeout)
        assert_disposed(conn, channel, sock)


@pytest.mark.parametrize('raise_timeout', [False, True])
def test_received_channel_error_precedes_deadline_during_disposal(
        subject, raise_timeout):
    conn, channel, sock, clock = subject
    conn._on_blocked()
    collect = conn.collect

    def dispose(*, force):
        collect(force=force)
        clock[0] = .1
        if raise_timeout:
            raise OperationTimeout('cleanup deadline')

    conn.collect = Mock(side_effect=dispose)
    sock.incoming = close_frame()
    with pytest.raises(PreconditionFailed) as info, operation_timeout(.05):
        conn.drain_events()
    assert_error(info.value)
    assert info.value.connection_usable is False
    assert_disposed(conn, channel, sock)
    assert all(call.kwargs == {'force': True}
               for call in conn.collect.call_args_list)


@pytest.mark.parametrize('failure', [
    RuntimeError, KeyboardInterrupt, SystemExit,
])
def test_channel_error_does_not_hide_unexpected_disposal_failures(
        subject, failure):
    conn, channel, sock, clock = subject
    conn._on_blocked()
    collect = conn.collect
    error = failure('disposal interrupted')

    def dispose(*, force):
        collect(force=force)
        raise error

    conn.collect = Mock(side_effect=dispose)
    sock.incoming = close_frame()
    with pytest.raises(failure) as info:
        conn.drain_events()
    assert info.value is error
    assert_disposed(conn, channel, sock)


def test_closing_channel_does_not_hide_disposal_timeout(subject):
    conn, channel, sock, clock = subject
    conn._on_blocked()
    channel.is_closing = True
    collect = conn.collect
    error = OperationTimeout('disposal interrupted')

    def dispose(*, force):
        collect(force=force)
        raise error

    conn.collect = Mock(side_effect=dispose)
    sock.incoming = close_frame()
    with pytest.raises(OperationTimeout) as info:
        conn.drain_events()
    assert info.value is error
    assert_disposed(conn, channel, sock)
