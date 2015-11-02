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

import asyncio
import logging

from collections import deque, defaultdict
from functools import wraps

from .exceptions import AMQPNotImplementedError, RecoverableConnectionError
from .method_framing import frame_writer
from .promise import ensure_promise, promise
from .serialization import dumps, loads
from .five import with_metaclass
from .utils import RLock

__all__ = ['AbstractChannel']

logger = logging.getLogger(__name__)

class AsyncHelper(type):
    """This metaclass renames all methods marked with "add_async" to
    NAME_async, and creates a helper that makes the original NAME
    synchronous."""
    def __new__(meta, name, bases, dct):
        for k,v in tuple(dct.items()):
            if getattr(v,'add_async',False):
                def make_sync(fn):
                    @wraps(fn)
                    def sync_call(self,*a,**k):
                        p = fn(self,*a,**k)
                        if asyncio.iscoroutine(p):
                            p = asyncio.ensure_future(p)
                        elif not isinstance(p, asyncio.Future):
                            return p
                        loop = asyncio.get_event_loop()
                        loop.run_until_complete(p)
                        val = p.result()
                        return val
                    return sync_call
                dct[k] = make_sync(v)
                k += '_async'
                if k not in dct:
                    dct[k] = v
        return super(AsyncHelper, meta).__new__(meta, name, bases, dct)

def with_async(fn):
    """Mark a method with an "add_async" attribute
    so that it'll get wrapped by the async_helper metaclass."""
    fn.add_async = True
    return fn

@with_metaclass(AsyncHelper)
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
        self._pending = defaultdict(deque)
        self._callbacks = {}

        self._setup_listeners()
        self._lock = RLock()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

    @asyncio.coroutine
    def send_method(self, sig,
                    format=None, args=None, content=None,
                    wait=None, returns_tuple=False):
        """Send a message.
        Optionally waits for a reply and returns its output.
        """
        conn = self.connection
        if conn is None:
            raise RecoverableConnectionError('connection already closed')
        args = dumps(format, args) if format else ''
        if wait:
            p = promise()
        try:
            # If two threads try to write to the same channel,
            # make sure data won't get interleaved and the results
            # will be processed in the correct order.
            with (yield from self._lock):
                if wait:
                    self._pending[wait].append(p)
                logger.debug("SEND %d: %s %s %s", self.channel_id, sig, args, content)
                try:
                    conn._frame_writer.send((1, self.channel_id, sig, args, content))
                except Exception:
                    # the frame writer coroutine has terminated due to throwing the
                    # exception (e.g. a codec error). Restart it.
                    conn._frame_writer = frame_writer(conn)
                    raise
            if not wait:
                return None
            res = (yield from p)
            if res and not returns_tuple:
                res = res[0]
            return res
        except StopIteration:
            err = RecoverableConnectionError('connection already closed')
            cleanup(err)
            raise

        finally:
            if wait:
                try:
                    self._pending[wait].remove(p)
                except ValueError:
                    pass

    def close(self):
        """Close this Channel or Connection"""
        raise NotImplementedError('Must be overriden in subclass')

    def wait(self, callback):
        """Wait for a method to be called.
        This just drains events until the callback fires;
        all the real work has been done in send_method()."""
        callback.wait()

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
            one_shot = self._pending[method_sig].popleft()
        except (KeyError,IndexError):
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
