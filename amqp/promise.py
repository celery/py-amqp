from __future__ import absolute_import

import abc
import logging
import socket
import sys

from collections import Callable, deque

from .five import with_metaclass
import asyncio
from asyncio.futures import Future

__all__ = ['Thenable', 'promise', 'barrier', 'wrap',
           'maybe_promise', 'ensure_promise']

logger = logging.getLogger(__name__)


@with_metaclass(abc.ABCMeta)
class Thenable(Callable):  # pragma: no cover
    __slots__ = ()

    @abc.abstractmethod
    def then(self, on_success, on_error=None):
        raise NotImplementedError()

    @abc.abstractmethod
    def throw(self, exc=None):
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel(self):
        raise NotImplementedError()

    @classmethod
    def __subclasshook__(cls, C):
        if cls is Thenable:
            if any('then' in B.__dict__ for B in C.__mro__):
                return True
        return NotImplemented


class barrier(object):
    """Synchronization primitive to call a callback after all promises
    fulfilled.

    Example:

    .. code-block:: python

        # Request supports the .then() method.
        p1 = http.Request('http://a')
        p2 = http.Request('http://b')
        p3 = http.Request('http://c')
        requests = [p1, p2, p3]

        def all_done():
            pass  # all requests complete

        b = barrier(requests).then(all_done)

        # oops, we forgot we want another request
        b.add(http.Request('http://d'))

    Note that you cannot add new promises to a barrier after
    the barrier is fulfilled.

    """
    def __init__(self, promises=None, callback=None):
        self.p = promise()
        self.promises = []
        self._value = 0
        self.ready = self.failed = False
        self.value = self.reason = None
        self.cancelled = False
        [self.add(p) for p in promises or []]
        if callback:
            self.then(callback)

    def __call__(self, *args, **kwargs):
        if not self.ready and not self.cancelled:
            self._value += 1
            if self._value >= len(self.promises):
                self.ready = True
                self.p()

    def cancel(self):
        self.cancelled = True
        self.p.cancel()

    def add(self, p):
        if not self.cancelled:
            if self.ready:
                raise ValueError('Cannot add promise to full barrier')
            p.then(self)
            self.promises.append(p)

    def then(self, callback, errback=None):
        self.p.then(callback, errback)

    def throw(self, *args, **kwargs):
        if not self.cancelled:
            self.p.throw(*args, **kwargs)
    throw1 = throw
Thenable.register(barrier)


class promise(Future, Thenable):
    """Future evaluation.

    This is a special implementation of promises in that it can
    be used both for "promise of a value" and lazy evaluation.
    The biggest upside for this is that everything in a promise can also be
    a promise, e.g. filters callbacks and errbacks can all be promises.

    Usage examples:

    .. code-block:: python

        >>> from __future__ import print_statement  # noqa
        >>> p = promise()
        >>> p.then(promise(print, ('OK',)))  # noqa
        >>> p.on_error = promise(print, ('ERROR',))  # noqa
        >>> p(20)
        OK, 20
        >>> p.then(promise(print, ('hello',)))  # noqa
        hello, 20


        >>> p.throw(KeyError('foo'))
        ERROR, KeyError('foo')


        >>> p2 = promise()
        >>> p2.then(print)  # noqa
        >>> p2.cancel()
        >>> p(30)

    Example:

    .. code-block:: python

        from amqp import promise, wrap

        class Protocol(object):

            def __init__(self):
                self.buffer = []

            def receive_message(self):
                return self.read_header().then(
                    self.read_body).then(
                        wrap(self.prepare_body))

            def read(self, size, callback=None):
                callback = callback or promise()
                tell_eventloop_to_read(size, callback)
                return callback

            def read_header(self, callback=None):
                return self.read(4, callback)

            def read_body(self, header, callback=None):
                body_size, = unpack('>L', header)
                return self.read(body_size, callback)

            def prepare_body(self, value):
                self.buffer.append(value)

    """
    if not hasattr(sys, 'pypy_version_info'):  # pragma: no cover
        __slots__ = ('fun', 'args', 'kwargs', 'on_error')

    def __init__(self, fun=None, args=None, kwargs=None,
                 callback=None, on_error=None):
        super(promise,self).__init__()
        self.fun = fun
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.on_error = on_error

        if callback is not None:
            self.then(callback)

    def __repr__(self):
        if self.fun:
            return '<promise@0x{0:x}: {1!r}>'.format(id(self), self.fun)
        return '<promise@0x{0:x}>'.format(id(self))

    def wait(self, timeout=None):
        loop = asyncio.get_event_loop()
        if timeout:
            t = asyncio.wait_for(self,timeout)
        else:
            #t = self
            t = asyncio.wait_for(self,5)
        loop.run_until_complete(t)
        if not self.done():
            assert(timeout)
            raise socket.timeout(timeout)

    def cancel(self):
        super(promise,self).cancel()
        try:
            if isinstance(self.on_error, Thenable):
                self.on_error.cancel()
        finally:
            self.on_error = None

    def __call__(self, *args, **kwargs):
        if self.done():
            try:
                return self.result()
            except Exception:
                return
        if self.fun:
            try:
                retval = self.fun(
                    *(self.args + args if args else self.args),
                    **(dict(self.kwargs, **kwargs) if kwargs else self.kwargs)
                )
                if isinstance(retval, Future):
                    self.fun = None
                    retval.add_done_callback(self.set_result_f)
                    return retval
                if isinstance(retval, Exception):
                    raise retval
            except Exception as exc:
                self.set_error_state(exc)
                if self.on_error:
                    self.on_error(self.exception())
                return

        else:
            assert not kwargs
            if not args:
                retval = None
            elif len(args) == 1:
                retval = args[0]
            else:
                retval = args
        self.set_result(retval)
        return retval

    def set_result_f(self, future):
        """set_result, called with a future"""
        try:
            self.set_result(future.result())
        except Exception as exc:
            self.set_error_state(exc)
            if self.on_error:
                self.on_error(self.exception())

    def then(self, callback, on_error=None):
        if isinstance(callback, Thenable):
            assert on_error is None
            on_error = callback.on_error
            on_cancel = callback.cancel
        else:
            callback = promise(callback, on_error=on_error)
            on_cancel = None
        if self.cancelled():
            callback.cancel()
            return callback

        def take_future(f):
            try:
                r = f.result()
                if isinstance(r, tuple):
                    callback(*r)
                else:
                    callback(r)
            except asyncio.CancelledError:
                if on_cancel:
                    on_cancel()
                else:
                    raise
            except Exception as exc:
                if on_error:
                    on_error(exc)
                else:
                    raise
        self.add_done_callback(take_future)
        return callback

    def throw1(self, exc):
        if self.cancelled():
            return
        self.failed, self.reason = True, exc
        if self.on_error:
            self.on_error(exc)

    def set_error_state(self, exc=None):
        if self.cancelled():
            return
        self.set_exception(exc)

    def throw(self, exc=None):
        self.set_error_state(exc)
Thenable.register(promise)


def wrap(p):
    """Wrap promise so that if the promise is called with a promise as
    argument, we attach ourselves to that promise instead."""

    def on_call(*args, **kwargs):
        if len(args) == 1 and isinstance(args[0], promise):
            return args[0].then(p)
        else:
            return p(*args, **kwargs)

    return on_call


def _transback(filter_, callback, args, kwargs, ret):
    try:
        ret = filter_(*args + (ret,), **kwargs)
    except Exception:
        callback.throw()
    else:
        return callback(ret)


def transform(filter_, callback, *filter_args, **filter_kwargs):
    """Filter final argument to a promise.

    E.g. to coerce callback argument to :class:`int`::

        transform(int, callback)

    or a more complex example extracting something from a dict
    and coercing the value to :class:`float`::

        def filter_key_value(key, filter_, mapping):
            return filter_(mapping[key])

        def get_page_expires(self, url, callback=None):
            return self.request(
                'GET', url,
                callback=transform(get_key, callback, 'PageExpireValue', int),
            )

    """
    callback = ensure_promise(callback)
    P = promise(_transback, (filter_, callback, filter_args, filter_kwargs))
    P.then(promise(), callback.throw)
    return P


def maybe_promise(p):
    if p:
        if not isinstance(p, Thenable):
            return promise(p)
    return p


def ensure_promise(p):
    if p is None:
        return promise()
    return maybe_promise(p)
