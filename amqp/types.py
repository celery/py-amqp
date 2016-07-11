import abc

from typing import _Protocol, Any, Dict, Optional, TypeVar


class SupportsFileno(_Protocol):
    __slots__ = ()

    @abc.abstractmethod
    def __fileno__(self) -> int:
        ...

Fd = TypeVar('Fd', SupportsFileno, int)
SSLArg = TypeVar('SSLArg', Dict[str, Any], bool)
MaybeDict = TypeVar('MaybeDict', Optional[Dict[str, Any]])
Timeout = TypeVar('Timeout', Optional[float])


class AbstractChannel(abc.ABCMeta):
    ...


class AbstractConnection(Channel):
    ...


class AbstractTransport(abc.ABCMeta):
    ...


class AbstractMessage(abc.ABCMeta):
    ...
