from __future__ import absolute_import

from collections import MutableMapping
from contextlib import contextmanager

from .promise import ensure_promise
from .exceptions import AMQPNotImplementedError
from .serialization import loads


class Events(object):

    def __init__(self, channel):
        self.channel = channel
        self._listeners = {}
        self._pending = {}
        self._quick_set_pending = self._pending.__setitem__
        self.dispatch_method = self.create_dispatcher(self.channel)

    def cleanup(self):
        self._listeners = None
        self._pending = None
        self._quick_set_pending = None

    def __getitem__(self, method):
        return self._listeners[method]

    def __setitem__(self, method, p):
        self._listeners[method] = p

    def __delitem__(self, method):
        self._listeners.pop(method)

    def pop(self, method, *args):
        self._listeners.pop(method, *args)

    def update(self, d, **kw):
        self._listeners.update(d, **kw)

    def call_on(self, method, p):
        self._quick_set_pending(method, p)
        return p

    @contextmanager
    def save_and_set_pending_for(self, method, p):
        pending = self._pending
        prev_p, pending[method] = pending.get(method), p
        try:
            yield
        finally:
            if prev_p is not None:
                pending[method] = p
            else:
                pending.pop(method, None)

    def create_dispatcher(self, channel):
        get_method = channel._METHODS.__getitem__
        get_listener = self._listeners.__getitem__
        reserve_pending = self._pending.pop

        def dispatch(method_sig, payload, content):
            try:
                amqp_method = get_method(method_sig)
            except KeyError:
                AMQPNotImplementedError(
                    'Unknown AMQP method: {0!r}'.format(method_sig))

            try:
                callbacks = [get_listener(method_sig)]
            except KeyError:
                callbacks = []

            try:
                callbacks.append(reserve_pending(method_sig))
            except KeyError:
                if not callbacks:
                    return

            args = []
            if amqp_method.args:
                args, _ = loads(amqp_method.args, payload, 4)
            if amqp_method.content:
                args.append(content)

            for callback in callbacks:
                print('CALLING: %r' % (callback, ))
                callback(*args)
        return dispatch

    def dispatch_method(self, channel, method_sig, payload, content):
        raise NotImplementedError('defined by constructor')


MutableMapping.register(Events)
