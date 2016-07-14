import abc

from typing import _Protocol, Any, Dict, Optional, TypeVar


class SupportsFileno(_Protocol):
    __slots__ = ()

    @abc.abstractmethod
    def __fileno__(self) -> int:
        ...

Fd = TypeVar('Fd', SupportsFileno, int)
Int = TypeVar('Int', SupportsInt, str)
SSLArg = TypeVar('SSLArg', Dict[str, Any], bool)


class AbstractChannel(abc.ABCMeta):
    ...


class AbstractConnection(Channel):
    ...


class TransportT(abc.ABCMeta):
    ...


class AbstractMessage(abc.ABCMeta):
    ...
