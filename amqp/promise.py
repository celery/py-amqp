from __future__ import absolute_import

import abc
import sys
import logging

from collections import Callable, deque

from .five import with_metaclass

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


class promise(object):
    """Future evaluation.

    This is a special implementation of promises in that it can
    be used both for "promise of a value" and lazy evaluation.
    The biggest upside for this is that everything in a promise can also be
    a promise, e.g. filters callbacks and errbacks can all be promises.

    Usage examples:

    .. code-block:: python

        >>> from __future__ import print_statement  # noqa
        >>> p = promise()
        >>> p.then(promise(print, ('OK', )))  # noqa
        >>> p.on_error = promise(print, ('ERROR', ))  # noqa
        >>> p(20)
        OK, 20
        >>> p.then(promise(print, ('hello', )))  # noqa
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
        __slots__ = ('fun', 'args', 'kwargs', 'ready', 'failed',
                     'value', 'reason', '_svpending', '_lvpending',
                     'on_error', 'cancelled')

    def __init__(self, fun=None, args=None, kwargs=None,
                 callback=None, on_error=None):
        self.fun = fun
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.ready = False
        self.failed = False
        self.value = None
        self.reason = None
        self._svpending = None
        self._lvpending = None
        self.on_error = on_error
        self.cancelled = False

        if callback is not None:
            self.then(callback)

    def __repr__(self):
        if self.fun:
            return '<promise@0x{0:x}: {1!r}>'.format(id(self), self.fun)
        return '<promise@0x{0:x}>'.format(id(self))

    def cancel(self):
        self.cancelled = True
        try:
            if self._svpending is not None:
                self._svpending.cancel()
            if self._lvpending is not None:
                for pending in self._lvpending:
                    pending.cancel()
            if isinstance(self.on_error, Thenable):
                self.on_error.cancel()
        finally:
            self._svpending = self._lvpending = self.on_error = None

    def __call__(self, *args, **kwargs):
        retval = None
        if self.cancelled:
            return
        if self.fun:
            try:
                retval = self.fun(
                    *(self.args + args if args else self.args),
                    **(dict(self.kwargs, **kwargs) if kwargs else self.kwargs)
                )
                self.value = (ca, ck) = (retval, ), {}
            except Exception:
                return self.set_error_state()
        else:
            self.value = (ca, ck) = (args, kwargs)
        self.ready = True
        svpending = self._svpending
        if svpending is not None:
            try:
                svpending(*ca, **ck)
            finally:
                self._svpending = None
        else:
            lvpending = self._lvpending
            try:
                while lvpending:
                    p = lvpending.popleft()
                    p(*ca, **ck)
            finally:
                self._lvpending = None
        return retval

    def then(self, callback, on_error=None):
        if not isinstance(callback, Thenable):
            callback = promise(callback, on_error=on_error)
        if self.cancelled:
            callback.cancel()
            return callback
        if self.failed:
            callback.throw(self.reason)
        elif self.ready:
            args, kwargs = self.value
            callback(*args, **kwargs)
        if self._lvpending is None:
            svpending = self._svpending
            if svpending is not None:
                self._svpending, self._lvpending = None, deque([svpending])
            else:
                self._svpending = callback
                return callback
        self._lvpending.append(callback)
        return callback

    def throw1(self, exc):
        if self.cancelled:
            return
        self.failed, self.reason = True, exc
        if self.on_error:
            self.on_error(exc)

    def set_error_state(self, exc=None):
        if self.cancelled:
            return
        _exc = sys.exc_info()[1] if exc is None else exc
        try:
            self.throw1(_exc)
            svpending = self._svpending
            if svpending is not None:
                try:
                    svpending.throw1(_exc)
                finally:
                    self._svpending = None
            else:
                lvpending = self._lvpending
                try:
                    while lvpending:
                        lvpending.popleft().throw1(_exc)
                finally:
                    self._lvpending = None
        finally:
            if self.on_error is None:
                if exc is None:
                    raise
                raise exc

    def throw(self, exc=None):
        if exc is None:
            return self.set_error_state()
        try:
            raise exc
        except exc.__class__ as with_cause:
            self.set_error_state(with_cause)
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
        ret = filter_(*args + (ret, ), **kwargs)
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
