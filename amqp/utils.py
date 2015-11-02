from __future__ import absolute_import

import asyncio
import sys

from functools import wraps

from .promise import promise   # noqa

is_py3k = sys.version_info[0] == 3

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None   # noqa

try:
    from os import set_cloexec  # Python 3.4?
except ImportError:
    def set_cloexec(fd, cloexec):  # noqa
        try:
            FD_CLOEXEC = fcntl.FD_CLOEXEC
        except AttributeError:
            raise NotImplementedError(
                'close-on-exec flag not supported on this platform',
            )
        flags = fcntl.fcntl(fd, fcntl.F_GETFD)
        if cloexec:
            flags |= FD_CLOEXEC
        else:
            flags &= ~FD_CLOEXEC
        return fcntl.fcntl(fd, fcntl.F_SETFD, flags)


def get_errno(exc):
    """:exc:`socket.error` and :exc:`IOError` first got
    the ``.errno`` attribute in Py2.7"""
    try:
        return exc.errno
    except AttributeError:
        try:
            # e.args = (errno, reason)
            if isinstance(exc.args, tuple) and len(exc.args) == 2:
                return exc.args[0]
        except AttributeError:
            pass
    return 0


def coro(gen):

    @wraps(gen)
    def _boot(*args, **kwargs):
        co = gen(*args, **kwargs)
        next(co)
        return co

    return _boot


if is_py3k:  # pragma: no cover

    def str_to_bytes(s):
        if isinstance(s, str):
            return s.encode()
        return s

    def bytes_to_str(s):
        if isinstance(s, bytes):
            return s.decode()
        return s
else:

    def str_to_bytes(s):                # noqa
        if isinstance(s, unicode):
            return s.encode()
        return s

    def bytes_to_str(s):                # noqa
        return s

class RLock(asyncio.Lock):
    _rcount = 0
    _self = None

    @asyncio.coroutine
    def acquire(self):
        me = asyncio.Task.current_task(self._loop)
        if self._self is me:
            self._rcount += 1
            return
        yield from super(RLock,self).acquire()
        assert self._rcount == 0, self._rcount
        self._self = me
        self._rcount += 1

    def release(self):
        assert self._rcount
        self._rcount -= 1
        if not self._rcount:
            self._self = None
            super(RLock,self).release()

    def locked(self):
        if self._self is asyncio.Task.current_task(self._loop):
            return False
        return super(RLock,self).locked()

