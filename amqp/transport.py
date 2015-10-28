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
from .five import items
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


class _AbstractTransport(object):
    """Common superclass for TCP and SSL transports"""
    connected = False
    _read_buffer = EMPTY_BUFFER

    def __init__(self, host, connect_timeout,
                 read_timeout=None, write_timeout=None,
                 ssl=None, socket_settings=None):
        self.connected = True
        msg = None
        port = AMQP_PORT

        m = IPV6_LITERAL.match(host)
        if m:
            host = m.group(1)
            if m.group(2):
                port = int(m.group(2))
        else:
            if ':' in host:
                host, port = host.rsplit(':', 1)
                port = int(port)

        self.sock = None
        last_err = None
        for res in socket.getaddrinfo(host, port, 0,
                                      socket.SOCK_STREAM, SOL_TCP):
            af, socktype, proto, canonname, sa = res
            try:
                self.sock = socket.socket(af, socktype, proto)
                try:
                    set_cloexec(self.sock, True)
                except NotImplementedError:
                    pass
                self.sock.settimeout(connect_timeout)
                self.sock.connect(sa)
            except socket.error as exc:
                msg = exc
                self.sock.close()
                self.sock = None
                last_err = msg
                continue
            break

        if not self.sock:
            # Didn't connect, return the most recent error message
            raise socket.error(last_err)

        try:
            self.sock.settimeout(None)
            self.sock.setblocking(False)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self._set_socket_options(socket_settings)

            # set socket timeouts
            for timeout, interval in ((socket.SO_SNDTIMEO, write_timeout),
                                      (socket.SO_RCVTIMEO, read_timeout)):
                if interval is not None:
                    self.sock.setsockopt(
                        socket.SOL_SOCKET, timeout,
                        struct.pack('ll', interval, 0),
                    )
            self._setup_transport()

            self._write(AMQP_PROTOCOL_HEADER)
        except (OSError, IOError, socket.error) as exc:
            if get_errno(exc) not in _UNAVAIL:
                self.connected = False
            raise

    def __del__(self):
        try:
            # socket module may have been collected by gc
            # if this is called by a thread at shutdown.
            if socket is not None:
                try:
                    self.close()
                except socket.error:
                    pass
        finally:
            self.sock = None

    def fileno(self):
        return self.sock.fileno()

    def _get_tcp_socket_defaults(self, sock):
        return {
            opt: sock.getsockopt(SOL_TCP, opt) for opt in TCP_OPTS
        }

    def _set_socket_options(self, socket_settings):
        if not socket_settings:
            self.sock.setsockopt(SOL_TCP, socket.TCP_NODELAY, 1)
            return

        tcp_opts = self._get_tcp_socket_defaults(self.sock)
        tcp_opts.setdefault(socket.TCP_NODELAY, 1)
        tcp_opts.update(socket_settings)

        for opt, val in items(tcp_opts):
            self.sock.setsockopt(SOL_TCP, opt, val)

    def _setup_transport(self):
        """Do any additional initialization of the class (used
        by the subclasses)."""
        pass

    def _shutdown_transport(self):
        """Do any preliminary work in shutting down the connection."""
        pass

    def _write(self, s):
        """Completely write a string to the peer."""
        raise NotImplementedError('Must be overriden in subclass')

    def close(self):
        if self.sock is not None:
            self._shutdown_transport()
            # Call shutdown first to make sure that pending messages
            # reach the AMQP broker if the program exits after
            # calling this method.
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()
            self.sock = None
        self.connected = False

    @asyncio.coroutine
    def read_frame(self, unpack=unpack):
        read = self._read
        read_frame_buffer = EMPTY_BUFFER
        try:
            frame_header = yield from read(7, True)
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

    def write(self, s):
        try:
            self._write(s)
        except socket.timeout:
            raise
        except (OSError, IOError, socket.error) as exc:
            if get_errno(exc) not in _UNAVAIL:
                self.connected = False
            raise

    @asyncio.coroutine
    def _read(self, n, initial=False, _errnos=(errno.EAGAIN, errno.EINTR)):
        """Read exactly n bytes from the socket"""
        loop = asyncio.get_event_loop()
        rbuf = self._read_buffer
        try:
            while len(rbuf) < n:
                s = yield from loop.sock_recv(self.sock, max(32768,n - len(rbuf)))
                rbuf += s
        except:
            self._read_buffer = rbuf
            raise

        result, self._read_buffer = rbuf[:n], rbuf[n:]
        return result


class SSLTransport(_AbstractTransport):
    """Transport that works over SSL"""

    def __init__(self, host, connect_timeout,
                 read_timeout=None, write_timeout=None,
                 ssl=None, socket_settings=None):
        if isinstance(ssl, dict):
            self.sslopts = ssl
        self._read_buffer = EMPTY_BUFFER
        super(SSLTransport, self).__init__(
            host, connect_timeout, read_timeout=read_timeout,
            write_timeout=write_timeout, socket_settings=socket_settings,
        )

    def _setup_transport(self):
        """Wrap the socket in an SSL object."""
        self.sock = self._wrap_socket(self.sock, **self.sslopts or {})
        self.sock.do_handshake()

    def _wrap_socket(self, sock, context=None, **sslopts):
        if context:
            return self._wrap_context(sock, sslopts, **context)
        return ssl.wrap_socket(self.sock, **sslopts)

    def _wrap_context(self, sock, sslopts, check_hostname=None, **ctx_options):
        ctx = ssl.create_default_context(**ctx_options)
        ctx.check_hostname = check_hostname
        return ctx.wrap_socket(sock, **sslopts)

    def _shutdown_transport(self):
        """Unwrap a Python 2.6 SSL socket, so we can call shutdown()"""
        if self.sock is not None:
            try:
                unwrap = self.sock.unwrap
            except AttributeError:
                return
            self.sock = unwrap()

    def _write(self, s):
        """Write a string out to the SSL socket fully."""
        write = self.sock.write
        while s:
            try:
                n = write(s)
            except (ValueError, AttributeError):
                # AG: sock._sslobj might become null in the meantime if the
                # remote connection has hung up.
                # In python 3.2, an AttributeError is raised because the SSL
                # module tries to access self._sslobj.write (w/ self._sslobj ==
                # None)
                # In python 3.4, a ValueError is raised is self._sslobj is
                # None. So much for portability... :/
                n = 0
            if not n:
                raise IOError('Socket closed')
            s = s[n:]


class TCPTransport(_AbstractTransport):
    """Transport that deals directly with TCP socket."""

    def _setup_transport(self):
        """Setup to _write() directly to the socket, and
        do our own buffered reads."""
        self._write = self.sock.sendall


def create_transport(host, connect_timeout,
                     read_timeout=None, write_timeout=None,
                     ssl=False, socket_settings=None):
    """Given a few parameters from the Connection constructor,
    select and create a subclass of _AbstractTransport."""
    transport = SSLTransport if ssl else TCPTransport
    return transport(host, connect_timeout, ssl=ssl,
                     read_timeout=read_timeout,
                     write_timeout=write_timeout,
                     socket_settings=socket_settings)
