import abc
from typing import _Protocol, Any, Mapping, SupportsInt, TypeVar


class SupportsFileno(_Protocol):
    __slots__ = ()

    @abc.abstractmethod
    def __fileno__(self) -> int:
        ...


Fd = TypeVar('Fd', SupportsFileno, int)
Int = TypeVar('Int', SupportsInt, str)
SSLArg = TypeVar('SSLArg', Mapping[str, Any], bool)


class AbstractChannel(metaclass=abc.ABCMeta):
    ...


class AbstractConnection(AbstractChannel):
    ...


class TransportT(metaclass=abc.ABCMeta):
    ...


class AbstractMessage(metaclass=abc.ABCMeta):
    ...
