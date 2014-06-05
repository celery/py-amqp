from __future__ import absolute_import

from functools import wraps

from .promise import promise   # noqa

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
