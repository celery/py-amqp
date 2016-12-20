"""Compatibility utilities."""
import logging
import os
from typing import AnyStr, Optional, Union, cast
from .types import Fd

__all__ = [
    'get_errno', 'set_cloexec',
    'str_to_bytes', 'bytes_to_str', 'get_logger',
]


def get_errno(exc: Exception):
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
        fd = fd.fileno()
    os.set_inheritable(fd, cloexec)


def str_to_bytes(s: AnyStr) -> bytes:
    if isinstance(s, str):
        return cast(str, s).encode()
    return s


def bytes_to_str(s: AnyStr) -> str:
    if isinstance(s, bytes):
        return cast(bytes, s).decode()
    return s


def get_logger(logger: Optional[Union[logging.Logger, str]]) -> logging.Logger:
    """Get logger by name."""
    if isinstance(logger, str):
        logger = logging.getLogger(logger)
    if not logger.hasHandlers():
        logger.addHandler(logging.NullHandler())
    return logger
