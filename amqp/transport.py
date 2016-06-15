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

import errno
import re
import struct
import socket
import ssl

from collections import namedtuple
from contextlib import contextmanager
from struct import unpack

from .exceptions import UnexpectedFrame
from .five import items
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

from .types import SSLArg, MaybeDict, Timeout


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


class BaseTransport(object):
    """Common superclass for TCP and SSL transports"""
    connected = False

    def __init__(self, host, connect_timeout=None,
                 read_timeout=None, write_timeout=None,
                 socket_settings=None, raise_on_initial_eintr=True, **kwargs):
        # type: (str, Timeout, Timeout, Timeout, MaybeDict, bool, **Any) -> None
        self.connected = True                      # type: bool
        self.sock = None                           # type: Socket
        self._read_buffer = EMPTY_BUFFER           # type: ByteString
        self.host, self.port = to_host_port(host)  # type: str, int
        self.connect_timeout = connect_timeout     # type: Timeout
        self.read_timeout = read_timeout           # type: Timeout
        self.write_timeout = write_timeout         # type: Timeout
        self.socket_settings = socket_settings     # type: MaybeDict
        self.raise_on_initial_eintr = raise_on_initial_eintr  # type: bool

    def connect(self):
        # type: () -> None
        self._connect(self.host, self.port, self.connect_timeout)
        self._init_socket(
            self.socket_settings, self.read_timeout, self.write_timeout,
        )

    @contextmanager
    def having_timeout(self, timeout):
        # type: (Timeout) -> ContextManager
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

    def _connect(self, host, port, timeout):
        # type: (str, int, Timeout) -> None
        entries = socket.getaddrinfo(
            host, port, 0, socket.SOCK_STREAM, SOL_TCP,
        )
        for i, res in enumerate(entries):
            af, socktype, proto, canonname, sa = res
            try:
                self.sock = socket.socket(af, socktype, proto)
                try:
                    set_cloexec(self.sock, True)
                except NotImplementedError:
                    pass
                self.sock.settimeout(timeout)
                self.sock.connect(sa)
            except socket.error:
                self.sock.close()
                self.sock = None
                if i + 1 >= len(entries):
                    raise
            else:
                break

    def _init_socket(self, socket_settings, read_timeout, write_timeout):
        # type: (MaybeDict, Timeout, Timeout) -> None
        try:
            self.sock.settimeout(None)  # set socket back to blocking mode
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

    def _get_tcp_socket_defaults(self, sock):
        # type: (Socket) -> Mapping[AnyStr, Any]
        return {
            opt: sock.getsockopt(SOL_TCP, opt) for opt in TCP_OPTS
        }

    def _set_socket_options(self, socket_settings):
        # type: (MaybeDict) -> None
        if not socket_settings:
            self.sock.setsockopt(SOL_TCP, socket.TCP_NODELAY, 1)
            return

        tcp_opts = self._get_tcp_socket_defaults(self.sock)
        tcp_opts.setdefault(socket.TCP_NODELAY, 1)
        tcp_opts.update(socket_settings)

        for opt, val in items(tcp_opts):
            self.sock.setsockopt(SOL_TCP, opt, val)

    def _read(self, n, initial=False):
        # type: (int, bool) -> ByteString
        """Read exactly n BytesString from the peer"""
        raise NotImplementedError('Must be overriden in subclass')

    def _setup_transport(self):
        # type: () -> None
        """Do any additional initialization of the class (used
        by the subclasses)."""
        pass

    def _shutdown_transport(self):
        # type: () -> None
        """Do any preliminary work in shutting down the connection."""
        pass

    def _write(self, s):
        # type: (ByteString) -> int
        """Completely write a string to the peer."""
        raise NotImplementedError('Must be overriden in subclass')

    def close(self):
        # type: () -> None
        if self.sock is not None:
            self._shutdown_transport()
            # Call shutdown first to make sure that pending messages
            # reach the AMQP broker if the program exits after
            # calling this method.
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()
            self.sock = None
        self.connected = False

    def read_frame(self, unpack=unpack):
        # type: (Callable[AnyStr, ByteString]) -> Frame
        read = self._read
        read_frame_buffer = EMPTY_BUFFER
        try:
            frame_header = read(7, True)
            read_frame_buffer += frame_header
            frame_type, channel, size = unpack('>BHI', frame_header)
            # >I is an unsigned int, but the argument to sock.recv is signed,
            # so we know the size can be at most 2 * SIGNED_INT_MAX
            if size > SIGNED_INT_MAX:
                part1 = read(SIGNED_INT_MAX)
                part2 = read(size - SIGNED_INT_MAX)
                payload = ''.join([part1, part2])
            else:
                payload = read(size)
            read_frame_buffer += payload
            ch = ord(read(1))
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

    def write(self, s):
        # type: (ByteString) -> None
        try:
            self._write(s)
        except socket.timeout:
            raise
        except (OSError, IOError, socket.error) as exc:
            if get_errno(exc) not in _UNAVAIL:
                self.connected = False
            raise


class SSLTransport(BaseTransport):
    """Transport that works over SSL"""

    def __init__(self, host, connect_timeout=None, ssl=None, **kwargs):
        # type: (str, float, Optional[SSLArg], **Any) -> None
        if isinstance(ssl, dict):
            self.sslopts = ssl            # type: Dict[AnyStr, Any]
        self._read_buffer = EMPTY_BUFFER  # type: ByteString
        super(SSLTransport, self).__init__(
            host, connect_timeout=connect_timeout, **kwargs)

    def _setup_transport(self):
        # type: () -> None
        """Wrap the socket in an SSL object."""
        self.sock = self._wrap_socket(self.sock, **self.sslopts or {})
        self.sock.do_handshake()
        self._quick_recv = self.sock.read

    def _wrap_socket(self, sock, context=None, **sslopts):
        # type: (Socket, MaybeDict, **Any) -> Socket
        if context:
            return self._wrap_context(sock, sslopts, **context)
        return ssl.wrap_socket(sock, **sslopts)

    def _wrap_context(self, sock, sslopts, check_hostname=None, **ctx_options):
        # type: (Socket, Dict[AnyStr, Any], bool, **Any) -> Socket
        ctx = ssl.create_default_context(**ctx_options)
        ctx.check_hostname = check_hostname
        return ctx.wrap_socket(sock, **sslopts)

    def _shutdown_transport(self):
        # type: () -> None
        """Unwrap a Python 2.6 SSL socket, so we can call shutdown()"""
        if self.sock is not None:
            try:
                unwrap = self.sock.unwrap  # type: Callable[[], Socket]
            except AttributeError:
                return
            self.sock = unwrap()

    def _read(self, n, initial=False,
              _errnos=(errno.ENOENT, errno.EAGAIN, errno.EINTR)):
        # type: (int, bool, Set[int]) -> ByteString

        # According to SSL_read(3), it can at most return 16kb of data.
        # Thus, we use an internal read buffer like TCPTransport._read
        # to get the exact number of ByteString wanted.
        recv = self._quick_recv
        rbuf = self._read_buffer
        try:
            while len(rbuf) < n:
                try:
                    s = recv(n - len(rbuf))  # type: ByteString
                except socket.error as exc:
                    # ssl.sock.read may cause ENOENT if the
                    # operation couldn't be performed (Issue celery#1414).
                    if exc.errno in _errnos:
                        if initial and self.raise_on_initial_eintr:
                            raise socket.timeout()
                        continue
                    raise
                if not s:
                    raise IOError('Socket closed')
                rbuf += s
        except:
            self._read_buffer = rbuf
            raise
        result, self._read_buffer = rbuf[:n], rbuf[n:]
        return result

    def _write(self, s):
        # type: (str) -> None
        """Write a string out to the SSL socket fully."""
        write = self.sock.write  # type: Callable[[ByteString], int]
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


class TCPTransport(BaseTransport):
    """Transport that deals directly with TCP socket."""

    def _setup_transport(self):
        # type: () -> None
        """Setup to _write() directly to the socket, and
        do our own buffered reads."""
        self._write = self.sock.sendall    # type: Callable[[ByteString], int]
        self._read_buffer = EMPTY_BUFFER   # type: ByteString
        self._quick_recv = self.sock.recv  # type: Callable[[int], ByteString]

    def _read(self, n, initial=False, _errnos={errno.EAGAIN, errno.EINTR}):
        # type: (int, bool, Set[int]) -> ByteString
        """Read exactly n bytes from the socket"""
        recv = self._quick_recv
        rbuf = self._read_buffer
        try:
            while len(rbuf) < n:
                try:
                    s = recv(n - len(rbuf))
                except socket.error as exc:
                    if exc.errno in _errnos:
                        if initial and self.raise_on_initial_eintr:
                            raise socket.timeout()
                        continue
                    raise
                if not s:
                    raise IOError('Socket closed')
                rbuf += s
        except:
            self._read_buffer = rbuf
            raise

        result, self._read_buffer = rbuf[:n], rbuf[n:]
        return result


def Transport(host, connect_timeout=None, ssl=False, **kwargs):
    # type: (str, Timeout, Optional[SSLArg], **Any) -> BaseTransport
    """Given a few parameters from the Connection constructor,
    select and create a subclass of BaseTransport."""
    transport = SSLTransport if ssl else TCPTransport
    return transport(host, connect_timeout=connect_timeout, ssl=ssl, **kwargs)
