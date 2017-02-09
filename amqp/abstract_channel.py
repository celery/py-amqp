"""Code common to Connection and Channel objects."""
# Copyright (C) 2007-2008 Barry Pederson <bp@barryp.org>)
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
from typing import Any, Callable, Coroutine, Mapping, Sequence, Union, cast
from typing import List, MutableMapping  # noqa: F401
from vine import Thenable, ensure_promise, promise
from .exceptions import AMQPNotImplementedError, RecoverableConnectionError
from .serialization import dumps, loads
from .types import AbstractChannelT, ConnectionT, MessageT, WaitMethodT
from .spec import method_t, method_sig_t
from .utils import AsyncToggle, toggle_blocking

__all__ = ['ChannelBase']


class ChannelBase(AsyncToggle, AbstractChannelT):
    """Superclass for Connection and Channel.

    The connection is treated as channel 0, then comes
    user-created channel objects.

    The subclasses must have a _METHOD_MAP class property, mapping
    between AMQP method signatures and Python methods.
    """

    connection: ConnectionT = None
    channel_id: int = None

    def __init__(self, connection: ConnectionT, channel_id: int) -> None:
        self.connection = connection
        self.channel_id = channel_id
        connection.channels[channel_id] = self
        self.auto_decode = False
        self._pending: MutableMapping[method_sig_t, Callable] = {}
        self._callbacks: MutableMapping[method_sig_t, Callable] = {}

        self._setup_listeners()

    def __enter__(self) -> AbstractChannelT:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @toggle_blocking
    async def send_method(self, sig: method_sig_t,
                          format: str = None,
                          args: Sequence = None,
                          content: bytes = None,
                          wait: WaitMethodT = None,
                          callback: Callable = None,
                          returns_tuple: bool = False) -> Thenable:
        p = promise()
        conn = self.connection
        if conn is None:
            raise RecoverableConnectionError('connection already closed')
        argsb = dumps(format, args) if format else b''
        try:
            await conn.frame_writer(
                1, self.channel_id, sig, argsb, content)
        except StopIteration:
            raise RecoverableConnectionError('connection already closed')

        # TODO temp: callback should be after write_method ... ;)
        p()
        if callback:
            cbret = callback()
            if isinstance(cbret, Coroutine):
                await cbret
        if wait:
            return await self.wait(wait, returns_tuple=returns_tuple)
        return p

    @toggle_blocking
    async def wait(self,
                   method: WaitMethodT,
                   callback: Callable = None,
                   timeout: float = None,
                   returns_tuple: bool = False) -> Any:
        p = ensure_promise(callback)
        pending = self._pending
        prev_p = []
        methods: Sequence[method_sig_t] = None
        if isinstance(method, method_sig_t):
            methods = [method]
        else:
            methods = method

        for m in methods:
            prev_p.append(pending.get(m))
            pending[m] = p

        try:
            while not p.ready:
                await self.connection.drain_events(timeout=timeout)

            if p.value:
                args, kwargs = p.value
                return args if returns_tuple else (args and args[0])
        finally:
            for i, m in enumerate(methods):
                if prev_p[i] is not None:
                    pending[m] = prev_p[i]
                else:
                    pending.pop(m, None)

    @toggle_blocking
    async def dispatch_method(self,
                              method_sig: method_sig_t,
                              payload: bytes,
                              content: MessageT) -> None:
        if content and \
                self.auto_decode and \
                hasattr(content, 'content_encoding'):
            try:
                content.body = content.body.decode(  # type: ignore
                    content.content_encoding)
            except Exception:
                pass

        try:
            amqp_method = self._METHODS[method_sig]
        except KeyError:
            raise AMQPNotImplementedError(
                'Unknown AMQP method {0!r}'.format(method_sig))

        try:
            listeners = [self._callbacks[method_sig]]
        except KeyError:
            listeners = None
        try:
            one_shot = self._pending.pop(method_sig)
        except KeyError:
            if not listeners:
                return

        args: Sequence[Any] = None
        final_args: Sequence[Any] = []
        if amqp_method.args:
            args, _ = loads(amqp_method.args, payload, 4)
        if amqp_method.content:
            final_args = cast(List, args) + [content]
        else:
            final_args = args

        for listener in listeners:
            lisret = cast(Callable, listener)(*final_args)
            if isinstance(lisret, Coroutine):
                await lisret
        if one_shot:
            osret = one_shot(*final_args)
            if isinstance(osret, Coroutine):
                await osret

    #: Placeholder, the concrete implementations will have to
    #: supply their own versions of _METHOD_MAP
    _METHODS: Mapping[method_sig_t, method_t] = {}
