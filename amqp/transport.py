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
from __future__ import absolute_import, unicode_literals

import asyncio
import errno
import re
import struct
import socket
import ssl

from collections import namedtuple
from contextlib import contextmanager
from struct import unpack
from typing import (
    Any, AnyStr, ByteString, Callable, Mapping, Optional, Set, Tuple,
)

from .exceptions import UnexpectedFrame
from .types import SSLArg, Timeout
from .utils import get_errno, set_cloexec

# Jython does not have this attribute
try:
    from socket import SOL_TCP
except ImportError:  # pragma: no cover
    from socket import IPPROTO_TCP as SOL_TCP  # noqa

try:
    from ssl import SSLError
except ImportError:  # pragma: no cover
    class SSLError(Exception):  # noqa
        pass

_UNAVAIL = {errno.EAGAIN, errno.EINTR, errno.ENOENT, errno.EWOULDBLOCK}

AMQP_PORT = 5672

EMPTY_BUFFER = bytes()

SIGNED_INT_MAX = 0x7FFFFFFF  # type: int

# Yes, Advanced Message Queuing Protocol Protocol is redundant
AMQP_PROTOCOL_HEADER = 'AMQP\x01\x01\x00\x09'.encode('latin_1')

# Match things like: [fe80::1]:5432, from RFC 2732
IPV6_LITERAL = re.compile(r'\[([\.0-9a-f:]+)\](?::(\d+))?')

# available socket options for TCP level
KNOWN_TCP_OPTS = (
    'TCP_CORK', 'TCP_DEFER_ACCEPT', 'TCP_KEEPCNT',
    'TCP_KEEPIDLE', 'TCP_KEEPINTVL', 'TCP_LINGER2',
    'TCP_MAXSEG', 'TCP_NODELAY', 'TCP_QUICKACK',
    'TCP_SYNCNT', 'TCP_WINDOW_CLAMP',
)
TCP_OPTS = [getattr(socket, opt)
            for opt in KNOWN_TCP_OPTS if hasattr(socket, opt)]

Frame = namedtuple('Frame', ('tuple', 'channel', 'data'))


def to_host_port(host, default=AMQP_PORT):
    # type: (str, int) -> (str, int)
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


class BaseTransport:
    """Common superclass for TCP and SSL transports"""
    connected = False
    rstream = None
    wstream = None

    def __init__(self, host: str,
                 connect_timeout: Timeout = None,
                 read_timeout: Timeout = None,
                 write_timeout: Timeout = None,
                 socket_settings: Mapping = None,
                 raise_on_initial_eintr: bool = True,
                 ssl: SSLArg = None,
                 **kwargs) -> None:
        self.connected = True                      # type: bool
        self.sock = None                           # type: Socket
        self._read_buffer = EMPTY_BUFFER           # type: ByteString
        self.host, self.port = to_host_port(host)  # type: str, int
        self.connect_timeout = connect_timeout     # type: Timeout
        self.read_timeout = read_timeout           # type: Timeout
        self.write_timeout = write_timeout         # type: Timeout
        self.socket_settings = socket_settings     # type: Mapping
        self.ssl = ssl                             # type: SSLArg
        self.raise_on_initial_eintr = raise_on_initial_eintr  # type: bool

    async def connect(self) -> None:
        await self._connect(self.host, self.port, self.connect_timeout)
        await self._init_socket(
            self.socket_settings, self.read_timeout, self.write_timeout,
        )

    @contextmanager
    def having_timeout(self, timeout: Timeout) -> Any:
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

    async def _connect(self, host: str, port: int, timeout: Timeout) -> None:
        self.rstream, self.wstream = await asyncio.open_connection(
            host=host, port=port, ssl=self.ssl,
        )
        self._read = self.rstream.readexactly
        self._write = self.wstream.write
        self.sock = self.wstream.transport._sock
        await self._write(AMQP_PROTOCOL_HEADER)
        try:
            set_cloexec(self.sock, True)
        except NotImplementedError:
            pass
        self.connected = True

    def _init_socket(self, socket_settings: Mapping,
                     read_timeout: Timeout, write_timeout: Timeout) -> None:
        sock = self.wstream.transport.socket
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self._set_socket_options(socket_settings)

            # set socket timeouts
            for timeout, interval in ((socket.SO_SNDTIMEO, write_timeout),
                                      (socket.SO_RCVTIMEO, read_timeout)):
                if interval is not None:
                    sock.setsockopt(
                        socket.SOL_SOCKET, timeout,
                        struct.pack('ll', interval, 0),
                    )
            self._setup_transport()
        except (OSError, IOError, socket.error) as exc:
            if get_errno(exc) not in _UNAVAIL:
                self.connected = False
            raise

    def _get_tcp_socket_defaults(
            self, sock: socket.socket) -> Mapping[AnyStr, Any]:
        return {
            opt: sock.getsockopt(SOL_TCP, opt) for opt in TCP_OPTS
        }

    def _set_socket_options(self, socket_settings: Mapping) -> None:
        if not socket_settings:
            self.sock.setsockopt(SOL_TCP, socket.TCP_NODELAY, 1)
            return

        tcp_opts = self._get_tcp_socket_defaults(self.sock)
        tcp_opts.setdefault(socket.TCP_NODELAY, 1)
        tcp_opts.update(socket_settings)

        for opt, val in tcp_opts.items():
            self.sock.setsockopt(SOL_TCP, opt, val)

    def _setup_transport(self) -> None:
        """Do any additional initialization of the class (used
        by the subclasses)."""
        pass

    def _shutdown_transport(self) -> None:
        """Do any preliminary work in shutting down the connection."""
        pass

    def close(self) -> None:
        if self.wstream is not None:
            self.wstream.close()
        self.wstream = None
        self.rstream = None
        self.connected = False

    async def read_frame(self, unpack: Callable = unpack) -> Frame:
        read = self._read
        read_frame_buffer = EMPTY_BUFFER
        try:
            frame_header = await read(7, True)
            read_frame_buffer += frame_header
            frame_type, channel, size = unpack(u'>BHI', frame_header)
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
        except (OSError, IOError, SSLError, socket.error) as exc:
            # Don't disconnect for ssl read time outs
            # http://bugs.python.org/issue10272
            if isinstance(exc, SSLError) and 'timed out' in str(exc):
                raise socket.timeout()
            if get_errno(exc) not in _UNAVAIL:
                self.connected = False
            raise
        if ch == 206:  # '\xce'
            return Frame(frame_type, channel, payload)
        else:
            raise UnexpectedFrame(
                'Received {0:#04x} while expecting 0xce'.format(ch))

    async def write(self, s: ByteString) -> None:
        try:
            await self._write(s)
        except socket.timeout:
            raise
        except (OSError, IOError, socket.error) as exc:
            if get_errno(exc) not in _UNAVAIL:
                self.connected = False
            raise


async def connect(host: str,
                  connect_timeout: Timeout=None,
                  ssl: SSLArg=False, **kwargs) -> BaseTransport:
    """Given a few parameters from the Connection constructor,
    select and create a subclass of BaseTransport."""
    t = Transport(host, connect_timeout=connect_timeout, ssl=ssl, **kwargs)
    await t.connect()
    return t
