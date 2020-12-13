"""Abstract types."""
import abc
import asyncio
import socket
from array import array
from datetime import datetime
from typing import (
    Any, Awaitable, Callable, IO, List, Mapping,
    MutableMapping, NamedTuple, Optional, Sequence, SupportsInt,
    TypeVar, Tuple, Union,
)
from .protocol import queue_declare_ok_t
from .spec import method_sig_t
from vine import Thenable

Fd = TypeVar('Fd', int, IO)
Int = TypeVar('Int', SupportsInt, str)


class Frame(NamedTuple):
    type: int
    channel: int
    data: bytes


ConnectionBlockedCallbackT = Callable[[str], Optional[Awaitable]]
ConnectionUnblockedCallbackT = Callable[[], Optional[Awaitable]]
ConnectionFrameHandlerT = Callable[[Frame], Awaitable]
ConnectionFrameWriterT = Callable[
    [int,
     int,
     Optional[method_sig_t],
     Optional[bytes],
     Optional['MessageT'],
     Optional[float]],
    Awaitable,
]

WaitMethodT = Union[method_sig_t, Sequence[method_sig_t]]


class TransportT(metaclass=abc.ABCMeta):
    """Transport type."""

    rstream: asyncio.StreamReader
    wstream: asyncio.StreamWriter

    connected: bool = False
    host: str
    port: int
    ssl: Any
    connect_timeout: float
    read_timeout: float
    write_timeout: float
    socket_settings: Mapping
    sock: socket.socket

    @abc.abstractmethod
    async def connect(self) -> None:
        ...

    @abc.abstractmethod
    def close(self) -> None:
        ...

    @abc.abstractmethod
    async def read_frame(self, timeout: float = None) -> Frame:
        ...

    @abc.abstractmethod
    async def write(self, s: bytes, timeout: float = None) -> None:
        ...


class ContentT(metaclass=abc.ABCMeta):
    """Generic content type."""

    CLASS_ID: int
    PROPERTIES: Sequence[Tuple[str, str]]

    properties: MutableMapping
    body_received: int = 0
    body_size: int = 0
    ready: bool = False

    frame_method: method_sig_t
    frame_args: str

    @abc.abstractmethod
    def _load_properties(
            self,
            class_id: int,
            buf: bytes,
            offset: int = 0,
            classes: Mapping = None,
            unpack_from: Callable = None) -> int:
        ...

    @abc.abstractmethod
    def _serialize_properties(self) -> bytes:
        ...

    @abc.abstractmethod
    def inbound_header(self, buf: bytes, offset: int = 0) -> int:
        ...

    @abc.abstractmethod
    def inbound_body(self, buf: bytes):
        ...


class MessageT(ContentT, metaclass=abc.ABCMeta):
    """Basic message type."""

    body: bytes
    children: Any
    channel: 'ChannelT'
    delivery_info: Mapping[str, Any]

    content_type: str
    content_encoding: str
    application_headers: MutableMapping
    delivery_mode: int
    priority: int
    correlation_id: str
    reply_to: str
    expiration: str
    message_id: str
    timestamp: datetime
    type: str
    user_id: str
    app_id: str
    cluster_id: str

    @abc.abstractmethod
    def __init__(self,
                 body: bytes=b'',
                 *,
                 children: Any = None,
                 channel: 'ChannelT' = None) -> None:
        ...

    @property
    @abc.abstractmethod
    def headers(self) -> MutableMapping:
        ...

    @property
    @abc.abstractmethod
    def delivery_tag(self) -> str:
        ...


class AbstractChannelT(metaclass=abc.ABCMeta):
    """Abstract channel type."""

    connection: 'ConnectionT'
    channel_id: int
    auto_decode: bool = False
    is_open: bool = False

    @abc.abstractmethod
    def __enter__(self) -> 'AbstractChannelT':
        ...

    @abc.abstractmethod
    def __exit__(self, *exc_info) -> None:
        ...

    @abc.abstractmethod
    async def __aenter__(self) -> 'AbstractChannelT':
        ...

    @abc.abstractmethod
    async def __aexit__(self, *exc_info) -> None:
        ...

    @abc.abstractmethod
    def _setup_listeners(self):
        ...

    @abc.abstractmethod
    async def send_method(
            self, sig: method_sig_t,
            format: str = None,
            args: Sequence = None,
            *,
            content: MessageT = None,
            wait: WaitMethodT = None,
            callback: Callable = None,
            returns_tuple: bool = False) -> Thenable:
        ...

    @abc.abstractmethod
    async def close(
            self,
            *,
            reply_code: int = 0,
            reply_text: str = '',
            method_sig: method_sig_t = method_sig_t(0, 0),
            argsig: str = 'BsBB') -> None:
        ...

    @abc.abstractmethod
    def collect(self) -> None:
        ...

    @abc.abstractmethod
    async def wait(
            self,
            method: WaitMethodT,
            *,
            callback: Callable = None,
            timeout: float = None,
            returns_tuple: bool = False) -> Any:
        ...

    async def dispatch_method(
            self,
            method_sig: method_sig_t,
            payload: bytes,
            content: MessageT) -> None:
        ...


class ConnectionT(AbstractChannelT):
    """Connection channel type."""

    Channel: type
    Transport: type

    host: str
    userid: str
    password: str
    login_method: str
    login_response: Any
    virtual_host: str
    locale: str
    client_properties: MutableMapping
    ssl: Any
    channel_max: int
    frame_max: int
    on_open: Thenable
    on_tune_ok: Thenable
    confirm_publish: bool
    connect_timeout: float
    read_timeout: float
    write_timeout: float
    socket_settings: Mapping

    negotiate_capabilities: Mapping[str, bool]
    library_properties: Mapping[str, Any]
    heartbeat: float
    client_heartbeat: float
    server_heartbeat: float
    last_heartbeat_sent: float
    last_heartbeat_received: float
    bytes_sent: int = 0
    bytes_recv: int = 0
    prev_sent: int
    prev_recv: int

    connection_errors: Tuple[type, ...]
    channel_errors: Tuple[type, ...]
    recoverable_connection_errors: Tuple[type, ...]
    recoverable_channel_errors: Tuple[type, ...]

    transport: TransportT
    channels: MutableMapping[int, AbstractChannelT]
    loop: asyncio.AbstractEventLoop

    mechanisms: List[str]
    locales: List[str]

    _avail_channel_ids: array

    def __init__(
            self,
            host: str = 'localhost:5672',
            userid: str = 'guest',
            password: str = 'guest',
            *,
            login_method: str = 'AMQPLAIN',
            login_response: Any = None,
            virtual_host: str = '/',
            locale: str = 'en_US',
            client_properties: Mapping = None,
            ssl: Any = False,
            connect_timeout: float = None,
            channel_max: int = None,
            frame_max: int = None,
            heartbeat: float = 0.0,
            on_open: Thenable = None,
            on_blocked: ConnectionBlockedCallbackT = None,
            on_unblocked: ConnectionUnblockedCallbackT = None,
            confirm_publish: bool = False,
            on_tune_ok: Callable = None,
            read_timeout: float = None,
            write_timeout: float = None,
            socket_settings: Mapping = None,
            frame_handler: ConnectionFrameHandlerT = None,
            frame_writer: ConnectionFrameWriterT = None,
            loop: asyncio.AbstractEventLoop = None,
            transport: TransportT = None,
            **kwargs) -> None:
        self.frame_writer = frame_writer
        self.frame_handler = frame_handler

    @property
    @abc.abstractmethod
    def server_capabilities(self) -> Mapping:
        ...

    @property
    @abc.abstractmethod
    def sock(self) -> socket.socket:
        pass

    @abc.abstractmethod
    async def connect(self, callback: Callable[[], None] = None) -> None:
        ...

    @property
    @abc.abstractmethod
    def connected(self) -> bool:
        ...

    @abc.abstractmethod
    def channel(self, channel_id: int,
                callback: Callable = None) -> 'AbstractChannelT':
        ...

    @abc.abstractmethod
    def is_alive(self) -> bool:
        ...

    @abc.abstractmethod
    async def drain_events(self, timeout: float = None) -> None:
        ...

    @abc.abstractmethod
    async def on_inbound_method(
            self,
            channel_id: int,
            method_sig: method_sig_t,
            payload: bytes,
            content: MessageT) -> None:
        ...

    @abc.abstractmethod
    async def send_heartbeat(self) -> None:
        ...

    @abc.abstractmethod
    async def heartbeat_tick(self, rate: int = 2) -> None:
        ...

    def _get_free_channel_id(self) -> int:
        ...

    @abc.abstractmethod
    def _claim_channel_id(self, channel_id: int) -> None:
        ...


class ChannelT(AbstractChannelT, metaclass=abc.ABCMeta):
    """Channel type."""

    @abc.abstractmethod
    async def flow(self, active: bool) -> None:
        ...

    @abc.abstractmethod
    async def open(self) -> None:
        ...

    @abc.abstractmethod
    async def exchange_declare(
            self, exchange: str, type: str,
            *,
            passive: bool = False,
            durable: bool = False,
            auto_delete: bool = True,
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BssbbbbbF') -> None:
        ...

    @abc.abstractmethod
    async def exchange_delete(
            self, exchange: str,
            *,
            if_unused: bool = False,
            nowait: bool = False,
            argsig: str = 'Bsbb') -> None:
        ...

    @abc.abstractmethod
    async def exchange_bind(
            self, destination: str,
            source: str = '',
            routing_key: str = '',
            *,
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsssbF') -> None:
        ...

    @abc.abstractmethod
    async def exchange_unbind(
            self, destination: str,
            source: str = '',
            routing_key: str = '',
            *,
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsssbF') -> None:
        ...

    @abc.abstractmethod
    async def queue_bind(
            self, queue: str,
            exchange: str = '',
            routing_key: str = '',
            *,
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsssbF') -> None:
        ...

    @abc.abstractmethod
    async def queue_unbind(
            self, queue: str, exchange: str,
            routing_key: str = '',
            *,
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsssF') -> None:
        ...

    @abc.abstractmethod
    async def queue_declare(
            self,
            queue: str = '',
            *,
            passive: bool = False,
            durable: bool = False,
            exclusive: bool = False,
            auto_delete: bool = True,
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsbbbbbF') -> queue_declare_ok_t:
        ...

    @abc.abstractmethod
    async def queue_delete(
            self,
            queue: str = '',
            *,
            if_unused: bool = False,
            if_empty: bool = False,
            nowait: bool = False,
            argsig: str = 'Bsbbb') -> None:
        ...

    @abc.abstractmethod
    async def queue_purge(
            self,
            queue: str = '',
            *,
            nowait: bool = False,
            argsig: str = 'Bsb') -> Optional[int]:
        ...

    @abc.abstractmethod
    async def basic_ack(
            self, delivery_tag: str,
            *,
            multiple: bool = False,
            argsig: str = 'Lb') -> None:
        ...

    @abc.abstractmethod
    async def basic_cancel(
            self, consumer_tag: str,
            *,
            nowait: bool = False,
            argsig: str = 'sb') -> None:
        ...

    @abc.abstractmethod
    async def basic_consume(
            self,
            queue: str = '',
            consumer_tag: str = '',
            *,
            no_local: bool = False,
            no_ack: bool = False,
            exclusive: bool = False,
            nowait: bool = False,
            callback: Callable = None,
            arguments: Mapping[str, Any] = None,
            on_cancel: Callable = None,
            argsig: str = 'BssbbbbF') -> None:
        ...

    @abc.abstractmethod
    async def basic_get(
            self,
            queue: str = '',
            *,
            no_ack: bool = False,
            argsig: str = 'Bsb') -> Optional[MessageT]:
        ...

    @abc.abstractmethod
    async def basic_publish(
            self, msg: MessageT,
            exchange: str = '',
            routing_key: str = '',
            *,
            mandatory: bool = False,
            immediate: bool = False,
            timeout: float = None,
            argsig: str = 'Bssbb') -> None:
        ...

    @abc.abstractmethod
    async def basic_qos(
            self,
            prefetch_size: int,
            prefetch_count: int,
            a_global: bool,
            argsig: str = 'lBb') -> None:
        ...

    @abc.abstractmethod
    async def basic_recover(self, *, requeue: bool = False) -> None:
        ...

    @abc.abstractmethod
    async def basic_recover_async(self, *, requeue: bool = False) -> None:
        ...

    @abc.abstractmethod
    async def basic_reject(self, delivery_tag: str,
                           *,
                           requeue: bool = False,
                           argsig: str = 'Lb') -> None:
        ...

    @abc.abstractmethod
    async def tx_commit(self) -> None:
        ...

    @abc.abstractmethod
    async def tx_rollback(self) -> None:
        ...

    @abc.abstractmethod
    async def tx_select(self) -> None:
        ...

    @abc.abstractmethod
    async def confirm_select(self, *, nowait: bool = False) -> None:
        ...