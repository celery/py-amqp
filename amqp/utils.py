"""Compatibility utilities."""
import logging
import os
from asyncio import coroutine
from functools import wraps
from typing import Any, AnyStr, Callable, Optional, Union, cast
from .types import Fd

__all__ = [
    'get_errno', 'set_cloexec', 'want_bytes', 'want_str', 'get_logger',
]


def get_errno(exc: Any) -> int:
    """Get exception errno (if set).

    Notes:
        :exc:`socket.error` and :exc:`IOError` first got
        the ``.errno`` attribute in Py2.7.
    """
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


def set_cloexec(fd: Fd, cloexec: bool) -> None:
    if not isinstance(fd, int):
        fd = cast(Fd, fd.fileno())
    os.set_inheritable(fd, cloexec)  # type: ignore


def want_bytes(s: AnyStr) -> bytes:
    if isinstance(s, str):
        return cast(str, s).encode()
    return s


def want_str(s: AnyStr) -> str:
    if isinstance(s, bytes):
        return cast(bytes, s).decode()
    return s


def get_logger(logger: Union[logging.Logger, str] = None) -> logging.Logger:
    """Get logger by name."""
    if isinstance(logger, str):
        logger = logging.getLogger(logger)
    if not logger.hasHandlers():
        logger.addHandler(logging.NullHandler())
    return logger



def toggle_blocking(meth: Callable) -> Callable:

    @wraps(meth)
    def _maybe_block(self, *args, **kwargs) -> Any:
        p = meth(self, *args, **kwargs)
        if not self.async:
            pass
        return p

    return _maybe_block


class AsyncToggle(object):
    async = True

