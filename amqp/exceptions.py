"""Exceptions used by amqp."""
# Copyright (C) 2007-2008 Barry Pederson <bp@barryp.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
from typing import Any, Mapping, MutableMapping, Union
from struct import pack, unpack
from . import spec

__all__ = [
    'AMQPError',
    'ConnectionError', 'ChannelError',
    'RecoverableConnectionError', 'IrrecoverableConnectionError',
    'RecoverableChannelError', 'IrrecoverableChannelError',
    'ConsumerCancelled', 'ContentTooLarge', 'NoConsumers',
    'ConnectionForced', 'InvalidPath', 'AccessRefused', 'NotFound',
    'ResourceLocked', 'PreconditionFailed', 'FrameError', 'FrameSyntaxError',
    'InvalidCommand', 'ChannelNotOpen', 'UnexpectedFrame', 'ResourceError',
    'NotAllowed', 'AMQPNotImplementedError', 'InternalError',

    'AMQPDeprecationWarning',
]


class AMQPDeprecationWarning(UserWarning):
    """Warning for deprecated things."""


class AMQPError(Exception):
    """Base class for all AMQP exceptions."""

    code = 0

    def __init__(self,
                 reply_text: str = None,
                 method_sig: spec.method_sig_t = None,
                 method_name: str = None,
                 reply_code: int = None) -> None:
        self.message = reply_text
        self.reply_code = reply_code or self.code
        self.reply_text = reply_text
        self.method_sig = method_sig
        self.method_name = method_name or ''
        if method_sig and not self.method_name:
            self.method_name = METHOD_NAME_MAP.get(method_sig, '')
        Exception.__init__(self, reply_code,
                           reply_text, method_sig, self.method_name)

    def __str__(self) -> str:
        if self.method:
            return '{0.method}: ({0.reply_code}) {0.reply_text}'.format(self)
        return self.reply_text or '<AMQPError: unknown error>'

    @property
    def method(self) -> Any:
        return self.method_name or self.method_sig


class ConnectionError(AMQPError):
    """AMQP Connection Error."""


class ChannelError(AMQPError):
    """AMQP Channel Error."""


class RecoverableChannelError(ChannelError):
    """Exception class for recoverable channel errors."""


class IrrecoverableChannelError(ChannelError):
    """Exception class for irrecoverable channel errors."""


class RecoverableConnectionError(ConnectionError):
    """Exception class for recoverable connection errors."""


class IrrecoverableConnectionError(ConnectionError):
    """Exception class for irrecoverable connection errors."""


class Blocked(RecoverableConnectionError):
    """AMQP Connection Blocked Predicate."""


class ConsumerCancelled(RecoverableConnectionError):
    """AMQP Consumer Cancelled Predicate."""


class ContentTooLarge(RecoverableChannelError):
    """AMQP Content Too Large Error."""

    code = 311


class NoConsumers(RecoverableChannelError):
    """AMQP No Consumers Error."""

    code = 313


class ConnectionForced(RecoverableConnectionError):
    """AMQP Connection Forced Error."""

    code = 320


class InvalidPath(IrrecoverableConnectionError):
    """AMQP Invalid Path Error."""

    code = 402


class AccessRefused(IrrecoverableChannelError):
    """AMQP Access Refused Error."""

    code = 403


class NotFound(IrrecoverableChannelError):
    """AMQP Not Found Error."""

    code = 404


class ResourceLocked(RecoverableChannelError):
    """AMQP Resource Locked Error."""

    code = 405


class PreconditionFailed(IrrecoverableChannelError):
    """AMQP Precondition Failed Error."""

    code = 406


class FrameError(IrrecoverableConnectionError):
    """AMQP Frame Error."""

    code = 501


class FrameSyntaxError(IrrecoverableConnectionError):
    """AMQP Frame Syntax Error."""

    code = 502


class InvalidCommand(IrrecoverableConnectionError):
    """AMQP Invalid Command Error."""

    code = 503


class ChannelNotOpen(IrrecoverableConnectionError):
    """AMQP Channel Not Open Error."""

    code = 504


class UnexpectedFrame(IrrecoverableConnectionError):
    """AMQP Unexpected Frame."""

    code = 505


class ResourceError(RecoverableConnectionError):
    """AMQP Resource Error."""

    code = 506


class NotAllowed(IrrecoverableConnectionError):
    """AMQP Not Allowed Error."""

    code = 530


class AMQPNotImplementedError(IrrecoverableConnectionError):
    """AMQP Not Implemented Error."""

    code = 540


class InternalError(IrrecoverableConnectionError):
    """AMQP Internal Error."""

    code = 541


ERROR_MAP: Mapping[int, type] = {
    311: ContentTooLarge,
    313: NoConsumers,
    320: ConnectionForced,
    402: InvalidPath,
    403: AccessRefused,
    404: NotFound,
    405: ResourceLocked,
    406: PreconditionFailed,
    501: FrameError,
    502: FrameSyntaxError,
    503: InvalidCommand,
    504: ChannelNotOpen,
    505: UnexpectedFrame,
    506: ResourceError,
    530: NotAllowed,
    540: AMQPNotImplementedError,
    541: InternalError,
}


def error_for_code(code: int, text: str, method: Any, default: type):
    try:
        return ERROR_MAP[code](text, method, reply_code=code)
    except KeyError:
        return default(text, method, reply_code=code)


_METHOD_NAME_MAP: Mapping[spec.method_sig_t, str] = {
    spec.Connection.Start: 'Connection.start',
    spec.Connection.StartOk: 'Connection.start_ok',
    spec.Connection.Secure: 'Connection.secure',
    spec.Connection.SecureOk: 'Connection.secure_ok',
    spec.Connection.Tune: 'Connection.tune',
    spec.Connection.TuneOk: 'Connection.tune_ok',
    spec.Connection.Open: 'Connection.open',
    spec.Connection.OpenOk: 'Connection.open_ok',
    spec.Connection.Close: 'Connection.close',
    spec.Connection.CloseOk: 'Connection.close_ok',
    spec.Channel.Open: 'Channel.open',
    spec.Channel.OpenOk: 'Channel.open_ok',
    spec.Channel.Flow: 'Channel.flow',
    spec.Channel.FlowOk: 'Channel.flow_ok',
    spec.Channel.Close: 'Channel.close',
    spec.Channel.CloseOk: 'Channel.close_ok',
    spec.Access.Request: 'Access.request',
    spec.Access.RequestOk: 'Access.request_ok',
    spec.Exchange.Declare: 'Exchange.declare',
    spec.Exchange.DeclareOk: 'Exchange.declare_ok',
    spec.Exchange.Delete: 'Exchange.delete',
    spec.Exchange.DeleteOk: 'Exchange.delete_ok',
    spec.Exchange.Bind: 'Exchange.bind',
    spec.Exchange.BindOk: 'Exchange.bind_ok',
    spec.Exchange.Unbind: 'Exchange.unbind',
    spec.Exchange.UnbindOk: 'Exchange.unbind_ok',
    spec.Queue.Declare: 'Queue.declare',
    spec.Queue.DeclareOk: 'Queue.declare_ok',
    spec.Queue.Bind: 'Queue.bind',
    spec.Queue.BindOk: 'Queue.bind_ok',
    spec.Queue.Purge: 'Queue.purge',
    spec.Queue.PurgeOk: 'Queue.purge_ok',
    spec.Queue.Delete: 'Queue.delete',
    spec.Queue.DeleteOk: 'Queue.delete_ok',
    spec.Queue.Unbind: 'Queue.unbind',
    spec.Queue.UnbindOk: 'Queue.unbind_ok',
    spec.Basic.Qos: 'Basic.qos',
    spec.Basic.QosOk: 'Basic.qos_ok',
    spec.Basic.Consume: 'Basic.consume',
    spec.Basic.ConsumeOk: 'Basic.consume_ok',
    spec.Basic.Cancel: 'Basic.cancel',
    spec.Basic.CancelOk: 'Basic.cancel_ok',
    spec.Basic.Publish: 'Basic.publish',
    spec.Basic.Return: 'Basic.return',
    spec.Basic.Deliver: 'Basic.deliver',
    spec.Basic.Get: 'Basic.get',
    spec.Basic.GetOk: 'Basic.get_ok',
    spec.Basic.GetEmpty: 'Basic.get_empty',
    spec.Basic.Ack: 'Basic.ack',
    spec.Basic.Nack: 'Basic.nack',
    spec.Basic.Reject: 'Basic.reject',
    spec.Basic.RecoverAsync: 'Basic.recover_async',
    spec.Basic.Recover: 'Basic.recover',
    spec.Basic.RecoverOk: 'Basic.recover_ok',
    spec.Tx.Select: 'Tx.select',
    spec.Tx.SelectOk: 'Tx.select_ok',
    spec.Tx.Commit: 'Tx.commit',
    spec.Tx.CommitOk: 'Tx.commit_ok',
    spec.Tx.Rollback: 'Tx.rollback',
    spec.Tx.RollbackOk: 'Tx.rollback_ok',
    spec.Confirm.Select: 'Confirm.select',
    spec.Confirm.SelectOk: 'Confirm.select_ok',
}

_BIN_METHOD_NAME_MAP: Mapping[str, str] = {
    unpack('>I', pack('>HH', *_method_id))[0]: _method_name
    for _method_id, _method_name in _METHOD_NAME_MAP.items()
}


_M: MutableMapping[Any, str] = dict(_METHOD_NAME_MAP)
_M.update(_BIN_METHOD_NAME_MAP)

METHOD_NAME_MAP: Mapping[Union[spec.method_sig_t, str], str] = dict(_M)
del(_METHOD_NAME_MAP)
del(_BIN_METHOD_NAME_MAP)
del(_M)
