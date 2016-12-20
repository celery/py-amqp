"""Transport implementation."""
# Copyright (C) 2009 Barry Pederson <bp@barryp.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
import asyncio
import re
import socket

from contextlib import contextmanager, suppress
from ssl import SSLError
from struct import pack, unpack
from typing import (
    Any, Callable, Dict, Mapping, NamedTuple, Tuple, Union, cast,
)

from .exceptions import UnexpectedFrame
from .types import SSLArg
from .platform import SOL_TCP, TCP_USER_TIMEOUT, HAS_TCP_USER_TIMEOUT
from .utils import set_cloexec

AMQP_PORT = 5672

EMPTY_BUFFER = bytes()

SIGNED_INT_MAX = 0x7FFFFFFF

# Yes, Advanced Message Queuing Protocol Protocol is redundant
AMQP_PROTOCOL_HEADER = 'AMQP\x01\x01\x00\x09'.encode('latin_1')

# Match things like: [fe80::1]:5432, from RFC 2732
IPV6_LITERAL = re.compile(r'\[([\.0-9a-f:]+)\](?::(\d+))?')

Frame = NamedTuple('Frame', [
    ('type', int),
    ('channel', int),
    ('data', bytes),
])

# available socket options for TCP level
KNOWN_TCP_OPTS = {  # type: Set[str]
    'TCP_CORK', 'TCP_DEFER_ACCEPT', 'TCP_KEEPCNT',
    'TCP_KEEPIDLE', 'TCP_KEEPINTVL', 'TCP_LINGER2',
    'TCP_MAXSEG', 'TCP_NODELAY', 'TCP_QUICKACK',
    'TCP_SYNCNT', 'TCP_WINDOW_CLAMP',
}

TCP_OPTS = {
    getattr(socket, opt) for opt in KNOWN_TCP_OPTS if hasattr(socket, opt)
}
DEFAULT_SOCKET_SETTINGS = {
    socket.TCP_NODELAY: 1,
}

StructUnpackT = Callable[
    [Union[bytes, str], bytes], Tuple[Any]
]

if HAS_TCP_USER_TIMEOUT:
    KNOWN_TCP_OPTS += ('TCP_USER_TIMEOUT',)
    TCP_OPTS.add(TCP_USER_TIMEOUT)
    DEFAULT_SOCKET_SETTINGS[TCP_USER_TIMEOUT] = 1000

try:
    from socket import TCP_KEEPIDLE, TCP_KEEPINTVL, TCP_KEEPCNT # noqa
except ImportError:
    pass
else:
    DEFAULT_SOCKET_SETTINGS.update({
        TCP_KEEPIDLE: 60,
        TCP_KEEPINTVL: 10,
        TCP_KEEPCNT: 9,
    })


def to_host_port(host: str, default: int = AMQP_PORT) -> Tuple[str, int]:
    """Convert hostname:port string to host, port tuple."""
    port = default
    m = IPV6_LITERAL.match(host)
    if m:
        host = m.group(1)
        if m.group(2):
            port = int(m.group(2))
    else:
        if ':' in host:
            host, port = host.rsplit(':', 1)
            port = int(port)
    return host, port


class Transport:
    """Common superclass for TCP and SSL transports"""

    connected = False
    rstream = None
    wstream = None

    def __init__(self, host: str,
                 connect_timeout: float = None,
                 read_timeout: float = None,
                 write_timeout: float = None,
                 socket_settings: Mapping = None,
                 raise_on_initial_eintr: bool = True,
                 ssl: SSLArg = None,
                 **kwargs) -> None:
        self.connected = True                      # type: bool
        self.sock = None                           # type: socket.socket
        self._read_buffer = EMPTY_BUFFER           # type: bytes
        self.host, self.port = to_host_port(host)  # type: str, int
        self.connect_timeout = connect_timeout     # type: float
        self.read_timeout = read_timeout           # type: float
        self.write_timeout = write_timeout         # type: float
        self.socket_settings = socket_settings     # type: Mapping
        self.ssl = ssl                             # type: SSLArg
        self.raise_on_initial_eintr = raise_on_initial_eintr  # type: bool

    async def connect(self) -> None:
        self.rstream, self.wstream = await asyncio.open_connection(
            host=self.host, port=self.port, ssl=self.ssl,
        )
        self.sock = self.wstream.transport._sock
        self._init_socket(
            self.socket_settings, self.read_timeout, self.write_timeout,
        )
        self._read = self.rstream.readexactly
        self._write = self.wstream.write
        self.flush_write_buffer = self.wstream.drain
        self.wstream.write(AMQP_PROTOCOL_HEADER)
        await self.wstream.drain()

    @contextmanager
    def having_timeout(self, timeout: float) -> Any:
        if timeout is None:
            yield self.sock
        else:
            sock = self.sock
            prev = sock.gettimeout()
            if prev != timeout:
                sock.settimeout(timeout)
            try:
                yield self.sock
            except SSLError as exc:
                if 'timed out' in str(exc):
                    # http://bugs.python.org/issue10272
                    raise socket.timeout()
                elif 'The operation did not complete' in str(exc):
                    # Non-blocking SSL sockets can throw SSLError
                    raise socket.timeout()
                raise
            finally:
                if timeout != prev:
                    sock.settimeout(prev)


    def _init_socket(self, socket_settings: Mapping,
                     read_timeout: float, write_timeout: float) -> None:
        sock = self.sock
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self._set_socket_options(socket_settings)
            with suppress(NotImplementedError):
                set_cloexec(self.sock, True)

            # set socket timeouts
            for timeout, interval in ((socket.SO_SNDTIMEO, write_timeout),
                                      (socket.SO_RCVTIMEO, read_timeout)):
                if interval is not None:
                    sock.setsockopt(
                        socket.SOL_SOCKET, timeout,
                        pack('ll', interval, 0),
                    )
            self._setup_transport()
        except (OSError, IOError, socket.error):
            self.connected = False
            raise

    def _get_tcp_socket_defaults(
            self, sock: socket.socket) -> Dict[int, int]:
        return {
            opt: sock.getsockopt(SOL_TCP, opt) for opt in TCP_OPTS
        }

    def _set_socket_options(self, socket_settings: Mapping) -> None:
        tcp_opts = self._get_tcp_socket_defaults(self.sock)
        final_socket_settings = dict(DEFAULT_SOCKET_SETTINGS)
        if socket_settings:
            final_socket_settings.update(socket_settings)
        tcp_opts.update(final_socket_settings)
        for opt, val in tcp_opts.items():
            self.sock.setsockopt(SOL_TCP, opt, val)

    def _read(self, n, initial=False):
        """Read exactly n bytes from the peer."""
        raise NotImplementedError('Must be overriden in subclass')

    def _setup_transport(self):
        """Do any additional initialization of the class."""
        ...

    def _shutdown_transport(self) -> None:
        """Do any preliminary work in shutting down the connection."""
        ...

    def close(self) -> None:
        if self.wstream is not None:
            self.wstream.close()
        self.wstream = None
        self.rstream = None
        self.flush_write_buffer = None
        self.connected = False

    async def read_frame(self, unpack: Callable = unpack) -> Frame:
        read = self._read
        read_frame_buffer = EMPTY_BUFFER
        try:
            frame_header = await read(7)
            read_frame_buffer += frame_header
            frame_type, channel, size = unpack('>BHI', frame_header)
            # >I is an unsigned int, but the argument to sock.recv is signed,
            # so we know the size can be at most 2 * SIGNED_INT_MAX
            if size > SIGNED_INT_MAX:
                part1 = await read(SIGNED_INT_MAX)
                part2 = await read(size - SIGNED_INT_MAX)
                payload = ''.join([part1, part2])
            else:
                payload = await read(size)
            read_frame_buffer += payload
            ch = ord(await read(1))
        except socket.timeout:
            self._read_buffer = read_frame_buffer + self._read_buffer
            raise
        except SSLError as exc:
            if 'timed out' in str(exc):
                raise socket.timeout()
        except (OSError, IOError, socket.error):
            self.connected = False
            raise
        if ch == 206:  # '\xce'
            return Frame(frame_type, channel, payload)
        else:
            raise UnexpectedFrame(
                'Received {0:#04x} while expecting 0xce'.format(ch))

    def write(self, s: bytes) -> None:
        try:
            self._write(s)
        except socket.timeout:
            raise
        except (OSError, IOError, socket.error):
            self.connected = False
            raise


async def connect(host: str,
                  connect_timeout: float=None,
                  ssl: SSLArg=False, **kwargs) -> Transport:
    """Given a few parameters from the Connection constructor,
    select and create a subclass of Transport."""
    t = Transport(host, connect_timeout=connect_timeout, ssl=ssl, **kwargs)
    await t.connect()
    return t
