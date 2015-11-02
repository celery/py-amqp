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
from __future__ import absolute_import

import errno
import re
import struct
import socket
import ssl

import asyncio

# Jython does not have this attribute
try:
    from socket import SOL_TCP
except ImportError:  # pragma: no cover
    from socket import IPPROTO_TCP as SOL_TCP  # noqa

try:
    from ssl import SSLError
except ImportError:
    class SSLError(Exception):  # noqa
        pass

from struct import unpack

from .exceptions import UnexpectedFrame
from .utils import get_errno, set_cloexec

_UNAVAIL = errno.EAGAIN, errno.EINTR, errno.ENOENT

AMQP_PORT = 5672

EMPTY_BUFFER = bytes()

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
TCP_OPTS = [getattr(socket, opt) for opt in KNOWN_TCP_OPTS
            if hasattr(socket, opt)]


class AMQPTransport(object):
    """Common superclass for TCP and SSL transports"""
    connected = False
    rstream = None
    wstream = None

    def __init__(self):
        self.connected = False
        msg = None
        port = AMQP_PORT

        self.sock = None

    @asyncio.coroutine
    def connect(self, host, ssl=None, socket_settings=None):
        assert not self.connected
        msg = None
        last_err = None
        port=AMQP_PORT

        m = IPV6_LITERAL.match(host)
        if m:
            host = m.group(1)
            if m.group(2):
                port = int(m.group(2))
        else:
            if ':' in host:
                host, port = host.rsplit(':', 1)
                port = int(port)

        self.rstream,self.wstream = (
            yield from asyncio.open_connection(
                host=host, port=port, ssl=ssl,
            ))
        self._write = self.wstream.write
        self._read = self.rstream.readexactly
        self.sock = self.wstream.transport._sock

        self._write(AMQP_PROTOCOL_HEADER)
        self.connected = True

    def __del__(self):
        self._write = None
        if self.wstream is not None:
            self.wstream.close()

    def _get_tcp_socket_defaults(self, sock):
        return {
            opt: sock.getsockopt(SOL_TCP, opt) for opt in TCP_OPTS
        }

    def _set_socket_options(self, socket_settings):
        sock = self.wstream.transport.socket
        if not socket_settings:
            sock.setsockopt(SOL_TCP, socket.TCP_NODELAY, 1)
            return

        tcp_opts = self._get_tcp_socket_defaults(sock)
        tcp_opts.setdefault(socket.TCP_NODELAY, 1)
        tcp_opts.update(socket_settings)

        for opt, val in tcp_opts.items():
            sock.setsockopt(SOL_TCP, opt, val)

    def close(self):
        if self.wstream is not None:
            self.wstream.close()
        self.wstream = None
        self.rstream = None
        self.connected = False

    @asyncio.coroutine
    def read_frame(self, unpack=unpack):
        read = self._read
        read_frame_buffer = EMPTY_BUFFER
        try:
            frame_header = yield from read(7)
            read_frame_buffer += frame_header
            frame_type, channel, size = unpack('>BHI', frame_header)
            payload = yield from read(size)
            read_frame_buffer += payload
            ch = ord((yield from read(1)))
        except socket.timeout:
            self._read_buffer = read_frame_buffer + self._read_buffer
            raise
        except (OSError, IOError, socket.error) as exc:
            # Don't disconnect for ssl read time outs
            # http://bugs.python.org/issue10272
            if isinstance(exc, SSLError) and 'timed out' in str(exc):
                raise socket.timeout()
            if get_errno(exc) not in _UNAVAIL:
                self.connected = False
            raise
        if ch == 206:  # '\xce'
            return frame_type, channel, payload
        else:
            raise UnexpectedFrame(
                'Received {0:#04x} while expecting 0xce'.format(ch))

@asyncio.coroutine
def create_transport(host, ssl=False, socket_settings=None):
    """Given a few parameters from the Connection constructor,
    select and create a subclass of _AbstractTransport."""
    t = AMQPTransport()
    yield from t.connect(host, ssl=ssl, socket_settings=socket_settings)
    return t
