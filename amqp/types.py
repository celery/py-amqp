import abc
import asyncio
import socket
from datetime import datetime
from typing import (
    Any, Awaitable, ByteString, Callable, IO, Mapping,
    MutableMapping, NamedTuple, Optional, Sequence, SupportsInt,
    TypeVar, Tuple, Union,
)
from .protocol import queue_declare_ok_t
from .spec import method_sig_t
from vine import Thenable

Fd = TypeVar('Fd', int, IO)
Int = TypeVar('Int', SupportsInt, str)

ConnectionBlockedCallback = Callable[[str], Optional[Awaitable]]
ConnectionUnblockedCallback = Callable[[], Optional[Awaitable]]
ConnectionInboundMethodHandler = Callable[
    [int, Tuple[Any], ByteString, ByteString], Any,
]
ConnectionFrameHandler = Callable[
    ['ConnectionT', ConnectionInboundMethodHandler],
    Callable,
]
ConnectionFrameWriter = Callable[
    [int, int, Optional[method_sig_t], Optional[bytes], Optional['MessageT']],
    Awaitable,
]

WaitMethodT = Union[method_sig_t, Sequence[method_sig_t]]

Frame = NamedTuple('Frame', [
    ('type', int),
    ('channel', int),
    ('data', bytes),
])


class TransportT(metaclass=abc.ABCMeta):

    rstream: asyncio.StreamReader = None
    wstream: asyncio.StreamWriter = None

    connected: bool = False
    host: str = None
    port: int = None
    ssl: Any = None
    connect_timeout: float = None
    read_timeout: float = None
    write_timeout: float = None
    socket_settings: Mapping = None
    sock: socket.socket = None

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

    CLASS_ID: int = None
    PROPERTIES: Sequence[Tuple[str, str]] = None

    properties: MutableMapping = None
    body_received: int = 0
    body_size: int = 0
    ready: bool = False

    frame_method: method_sig_t = None
    frame_args: str = None

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

    body: bytes = None
    children: Any = None  # unsupported
    channel: 'ChannelT' = None
    delivery_info: Mapping[str, Any] = None

    content_type: str = None
    content_encoding: str = None
    application_headers: MutableMapping = None
    delivery_mode: int = None
    priority: int = None
    correlation_id: str = None
    reply_to: str = None
    expiration: str = None
    message_id: str = None
    timestamp: datetime = None
    type: str = None
    user_id: str = None
    app_id: str = None
    cluster_id: str = None

    @abc.abstractmethod
    def __init__(self,
                 body: bytes=b'',
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

    connection: 'ConnectionT' = None
    channel_id: int = None
    auto_decode: bool = None

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
    async def send_method(self, sig: method_sig_t,
                          format: str = None,
                          args: Sequence = None,
                          content: bytes = None,
                          wait: WaitMethodT = None,
                          callback: Callable = None,
                          returns_tuple: bool = False) -> Thenable:
        ...

    @abc.abstractmethod
    async def close(self,
                    reply_code: int = 0,
                    reply_text: str = '',
                    method_sig: method_sig_t = method_sig_t(0, 0),
                    argsig: str = 'BsBB') -> None:
        ...

    @abc.abstractmethod
    def collect(self) -> None:
        ...

    @abc.abstractmethod
    async def wait(self,
                   method: WaitMethodT,
                   callback: Callable = None,
                   timeout: float = None,
                   returns_tuple: bool = False) -> Any:
        ...

    async def dispatch_method(self,
                              method_sig: method_sig_t,
                              payload: bytes,
                              content: MessageT) -> None:
        ...


class ConnectionT(AbstractChannelT, Thenable):

    Channel: type = None
    Transport: type = None

    host: str = None
    userid: str = None
    password: str = None
    login_method: str = None
    login_response: Any = None
    virtual_host: str = None
    locale: str = None
    client_properties: MutableMapping = None
    ssl: Any = None
    connect_timeout: float = None
    channel_max: int = None
    frame_max: int = None
    on_open: Thenable = None
    confirm_publish: bool = None
    read_timeout: float = None
    write_timeout: float = None
    socket_settings: Mapping = None
    loop: Any = None

    negotiate_capabilities: Mapping[str, bool] = None
    library_properties: Mapping[str, Any] = None
    heartbeat: float = None
    client_heartbeat: float = None
    server_heartbeat: float = None
    last_heartbeat_sent: float = None
    last_heartbeat_received: float = None
    bytes_sent: int = 0
    bytes_recv: int = 0
    prev_sent: int = None
    prev_recv: int = None

    connection_errors: Tuple[type, ...] = None
    channel_errors: Tuple[type, ...] = None
    recoverable_connection_errors: Tuple[type, ...] = None
    recoverable_channel_errors: Tuple[type, ...] = None

    transport: TransportT = None

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
    async def on_inbound_method(self,
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


class ChannelT(metaclass=abc.ABCMeta):

    @abc.abstractmethod
    async def flow(self, active: bool) -> None:
        ...

    @abc.abstractmethod
    async def open(self) -> None:
        ...

    @abc.abstractmethod
    async def exchange_declare(
            self, exchange: str, type: str,
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
            if_unused: bool = False,
            nowait: bool = False,
            argsig: str = 'Bsbb') -> None:
        ...

    @abc.abstractmethod
    async def exchange_bind(
            self, destination: str,
            source: str = '',
            routing_key: str = '',
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsssbF') -> None:
        ...

    @abc.abstractmethod
    async def exchange_unbind(
            self, destination: str,
            source: str = '',
            routing_key: str = '',
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsssbF') -> None:
        ...

    @abc.abstractmethod
    async def queue_bind(
            self, queue: str,
            exchange: str = '',
            routing_key: str = '',
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsssbF') -> None:
        ...

    @abc.abstractmethod
    async def queue_unbind(
            self, queue: str, exchange: str,
            routing_key: str = '',
            nowait: bool = False,
            arguments: Mapping[str, Any] = None,
            argsig: str = 'BsssF') -> None:
        ...

    @abc.abstractmethod
    async def queue_declare(
            self,
            queue: str = '',
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
            if_unused: bool = False,
            if_empty: bool = False,
            nowait: bool = False,
            argsig: str = 'Bsbbb') -> None:
        ...

    @abc.abstractmethod
    async def queue_purge(
            self,
            queue: str = '',
            nowait: bool = False,
            argsig: str = 'Bsb') -> Optional[int]:
        ...

    @abc.abstractmethod
    async def basic_ack(
            self, delivery_tag: str,
            multiple: bool = False,
            argsig: str = 'Lb') -> None:
        ...

    @abc.abstractmethod
    async def basic_cancel(
            self, consumer_tag: str,
            nowait: bool = False,
            argsig: str = 'sb') -> None:
        ...

    @abc.abstractmethod
    async def basic_consume(
            self,
            queue: str = '',
            consumer_tag: str = '',
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
            no_ack: bool = False,
            argsig: str = 'Bsb') -> Optional[MessageT]:
        ...

    @abc.abstractmethod
    async def basic_publish(
            self, msg: MessageT,
            exchange: str = '',
            routing_key: str = '',
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
    async def basic_recover(self, requeue: bool = False) -> None:
        ...

    @abc.abstractmethod
    async def basic_recover_async(self, requeue: bool = False) -> None:
        ...

    @abc.abstractmethod
    async def basic_reject(self, delivery_tag: str, requeue: bool,
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
    async def confirm_select(self, nowait: bool = False) -> None:
        ...
