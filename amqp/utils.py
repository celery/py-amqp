"""Compatibility utilities."""
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from logging import NullHandler
from math import isfinite
from threading import TIMEOUT_MAX
from time import monotonic

# enables celery 3.1.23 to start again
from vine import promise  # noqa
from vine.utils import wraps

from .exceptions import OperationTimeout

_operation_deadline = ContextVar('amqp_operation_deadline', default=None)


def operation_deadline():
    """Return the absolute deadline for this execution context, if any."""
    return _operation_deadline.get()


def remaining_operation_time(limit=None):
    """Cap an existing timeout without turning expiry into nonblocking I/O."""
    deadline = operation_deadline()
    if deadline is None:
        return limit
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise OperationTimeout('Operation deadline exceeded')
    remaining = min(remaining, TIMEOUT_MAX)
    return remaining if limit is None else min(limit, remaining)


@contextmanager
def operation_timeout(timeout=None, *, deadline=None):
    """Share a monotonic budget across AMQP operations in this context.

    Nested scopes can shorten but cannot extend an existing deadline. DNS
    and application callbacks are checked cooperatively, not interrupted.
    """
    if timeout is not None:
        if deadline is not None:
            raise ValueError('Specify timeout or deadline, not both')
        try:
            valid = isinstance(timeout, (int, float)) and \
                not isinstance(timeout, bool) and \
                isfinite(timeout) and 0 <= timeout <= TIMEOUT_MAX
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(
                'timeout must be a finite non-negative number '
                '<= threading.TIMEOUT_MAX')
        deadline = monotonic() + timeout
    if deadline is not None and not isfinite(deadline):
        raise ValueError('deadline must be finite')
    previous = operation_deadline()
    if previous is not None:
        deadline = previous if deadline is None else min(previous, deadline)
    token = _operation_deadline.set(deadline)
    try:
        remaining_operation_time()
        yield
        remaining_operation_time()
    finally:
        _operation_deadline.reset(token)


try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # noqa


def set_cloexec(fd, cloexec):
    """Set flag to close fd after exec."""
    if fcntl is None:
        return
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


def coro(gen):
    """Decorator to mark generator as a co-routine."""
    @wraps(gen)
    def _boot(*args, **kwargs):
        co = gen(*args, **kwargs)
        next(co)
        return co

    return _boot


def str_to_bytes(s):
    """Convert str to bytes."""
    if isinstance(s, str):
        return s.encode('utf-8', 'surrogatepass')
    return s


def bytes_to_str(s):
    """Convert bytes to str."""
    if isinstance(s, bytes):
        return s.decode('utf-8', 'surrogatepass')
    return s


def get_logger(logger):
    """Get logger by name."""
    if isinstance(logger, str):
        logger = logging.getLogger(logger)
    if not logger.handlers:
        logger.addHandler(NullHandler())
    return logger
