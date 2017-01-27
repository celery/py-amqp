import abc
from typing import Any, IO, Mapping, SupportsInt, TypeVar

Fd = TypeVar('Fd', int, IO)
Int = TypeVar('Int', SupportsInt, str)
SSLArg = TypeVar('SSLArg', Mapping[str, Any], bool)


class ChannelT(metaclass=abc.ABCMeta):
    ...


class ConnectionT(ChannelT):
    ...


class TransportT(metaclass=abc.ABCMeta):
    ...


class MessageT(metaclass=abc.ABCMeta):
    ...
