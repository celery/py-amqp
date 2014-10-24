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
from __future__ import absolute_import

from .exceptions import AMQPNotImplementedError, RecoverableConnectionError
from .promise import ensure_promise, promise
from .serialization import dumps, loads

__all__ = ['AbstractChannel']


class AbstractChannel(object):
    """Superclass for both the Connection, which is treated
    as channel 0, and other user-created Channel objects.

    The subclasses must have a _METHOD_MAP class property, mapping
    between AMQP method signatures and Python methods.

    """
    def __init__(self, connection, channel_id):
        self.connection = connection
        self.channel_id = channel_id
        connection.channels[channel_id] = self
        self.method_queue = []  # Higher level queue for methods
        self.auto_decode = False
        self._pending = {}
        self._callbacks = {}

        self._setup_listeners()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    def send_method(self, sig,
                    format=None, args=None, content=None,
                    wait=None, callback=None):
        p = promise()
        conn = self.connection
        if conn is None:
            raise RecoverableConnectionError('connection already closed')
        args = dumps(format, args) if format else ''
        try:
            conn._frame_writer.send((1, self.channel_id, sig, args, content))
        except StopIteration:
            raise RecoverableConnectionError('connection already closed')

        # TODO temp: callback should be after write_method ... ;)
        if callback:
            p.then(callback)
        p()
        if wait:
            return self.wait(wait)
        return p

    def close(self):
        """Close this Channel or Connection"""
        raise NotImplementedError('Must be overriden in subclass')

    def wait(self, method, callback=None, returns_tuple=False):
        p = ensure_promise(callback)
        pending = self._pending
        prev_p, pending[method] = pending.get(method), p
        self._pending[method] = p

        try:
            while not p.ready:
                self.connection.drain_events()

            if p.value:
                args, kwargs = p.value
                return args if returns_tuple else (args and args[0])
        finally:
            if prev_p is not None:
                pending[method] = prev_p
            else:
                pending.pop(method, None)

    def dispatch_method(self, method_sig, payload, content):
        if content and \
                self.auto_decode and \
                hasattr(content, 'content_encoding'):
            try:
                content.body = content.body.decode(content.content_encoding)
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
        else:
            if listeners is None:
                listeners = [one_shot]
            else:
                listeners.append(one_shot)


        args = []
        if amqp_method.args:
            args, _ = loads(amqp_method.args, payload, 4)
        if amqp_method.content:
            args.append(content)

        for listener in listeners:
            listener(*args)

    #: Placeholder, the concrete implementations will have to
    #: supply their own versions of _METHOD_MAP
    _METHODS = {}
