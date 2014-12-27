"""AMQP Connections"""
# Copyright (C) 2007-2008 Barry Pederson <bp@barryp.org>
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

import logging
import socket

from array import array
from io import BytesIO
try:
    from ssl import SSLError
except ImportError:
    class SSLError(Exception):  # noqa
        pass

from . import __version__
from . import spec
from .abstract_channel import AbstractChannel
from .channel import Channel
from .exceptions import (
    ChannelError, ResourceError,
    ConnectionForced, ConnectionError, error_for_code,
    RecoverableConnectionError, RecoverableChannelError,
)
from .five import range, values, monotonic
from .method_framing import frame_handler, frame_writer
from .promise import ensure_promise
from .serialization import _write_table
from .transport import create_transport

START_DEBUG_FMT = """
Start from server, version: %d.%d, properties: %s, mechanisms: %s, locales: %s
""".strip()

__all__ = ['Connection']

#
# Client property info that gets sent to the server on connection startup
#
LIBRARY_PROPERTIES = {
    'product': 'py-amqp',
    'product_version': __version__,
    'capabilities': {},
}

AMQP_LOGGER = logging.getLogger('amqp')


class Connection(AbstractChannel):
    """The connection class provides methods for a client to establish a
    network connection to a server, and for both peers to operate the
    connection thereafter.

    GRAMMAR::

        connection          = open-connection *use-connection close-connection
        open-connection     = C:protocol-header
                              S:START C:START-OK
                              *challenge
                              S:TUNE C:TUNE-OK
                              C:OPEN S:OPEN-OK
        challenge           = S:SECURE C:SECURE-OK
        use-connection      = *channel
        close-connection    = C:CLOSE S:CLOSE-OK
                            / S:CLOSE C:CLOSE-OK

    """
    Channel = Channel

    #: Final heartbeat interval value (in float seconds) after negotiation
    heartbeat = None

    #: Original heartbeat interval value proposed by client.
    client_heartbeat = None

    #: Original heartbeat interval proposed by server.
    server_heartbeat = None

    #: Time of last heartbeat sent (in monotonic time, if available).
    last_heartbeat_sent = 0

    #: Time of last heartbeat received (in monotonic time, if available).
    last_heartbeat_received = 0

    #: Number of successful writes to socket.
    bytes_sent = 0

    #: Number of successful reads from socket.
    bytes_recv = 0

    #: Number of bytes sent to socket at the last heartbeat check.
    prev_sent = None

    #: Number of bytes received from socket at the last heartbeat check.
    prev_recv = None

    _METHODS = set([
        spec.method(spec.Connection.Start, 'ooFSS'),
        spec.method(spec.Connection.OpenOk),
        spec.method(spec.Connection.Secure, 's'),
        spec.method(spec.Connection.Tune, 'BlB'),
        spec.method(spec.Connection.Close, 'BsBB'),
        spec.method(spec.Connection.Blocked),
        spec.method(spec.Connection.Unblocked),
        spec.method(spec.Connection.CloseOk),
    ])
    _METHODS = dict((m.method_sig, m) for m in _METHODS)

    connection_errors = (
        ConnectionError,
        socket.error,
        IOError,
        OSError,
    )
    channel_errors = (ChannelError, )
    recoverable_connection_errors = (
        RecoverableConnectionError,
        socket.error,
        IOError,
        OSError,
    )
    recoverable_channel_errors = (
        RecoverableChannelError,
    )

    def __init__(self, host='localhost', userid='guest', password='guest',
                 login_method='AMQPLAIN', login_response=None,
                 virtual_host='/', locale='en_US', client_properties=None,
                 ssl=False, connect_timeout=None, channel_max=None,
                 frame_max=None, heartbeat=0, on_open=None, on_blocked=None,
                 on_unblocked=None, confirm_publish=False,
                 on_tune_ok=None, **kwargs):
        """Create a connection to the specified host, which should be
        a 'host[:port]', such as 'localhost', or '1.2.3.4:5672'
        (defaults to 'localhost', if a port is not specified then
        5672 is used)

        If login_response is not specified, one is built up for you from
        userid and password if they are present.

        The 'ssl' parameter may be simply True/False, or for Python >= 2.6
        a dictionary of options to pass to ssl.wrap_socket() such as
        requiring certain certificates.

        """
        channel_max = channel_max or 65535
        frame_max = frame_max or 131072
        if (login_response is None) \
                and (userid is not None) \
                and (password is not None):
            login_response = BytesIO()
            _write_table({'LOGIN': userid, 'PASSWORD': password},
                         login_response.write, [])
            # Skip the length at the beginning
            login_response = login_response.getvalue()[4:]

        self.client_properties = dict(
            LIBRARY_PROPERTIES, **client_properties or {}
        )
        self.login_method = login_method
        self.login_response = login_response
        self.locale = locale
        self.virtual_host = virtual_host
        self.on_tune_ok = ensure_promise(on_tune_ok)

        self._handshake_complete = False

        self.channels = {}
        # The connection object itself is treated as channel 0
        super(Connection, self).__init__(self, 0)

        self.transport = None

        # Properties set in the Tune method
        self.channel_max = channel_max
        self.frame_max = frame_max
        self.client_heartbeat = heartbeat

        self.confirm_publish = confirm_publish

        # Callbacks
        self.on_blocked = on_blocked
        self.on_unblocked = on_unblocked
        self.on_open = ensure_promise(on_open)

        self._avail_channel_ids = array('H', range(self.channel_max, 0, -1))

        # Properties set in the Start method
        self.version_major = 0
        self.version_minor = 0
        self.server_properties = {}
        self.mechanisms = []
        self.locales = []

        # Let the transport.py module setup the actual
        # socket connection to the broker.
        #
        self.transport = self.Transport(host, connect_timeout, ssl)
        self.on_inbound_frame = frame_handler(self, self.on_inbound_method)
        self._frame_writer = frame_writer(self, self.transport)

        self.connect_timeout = connect_timeout
        self.connect()

    def then(self, on_success, on_error=None):
        return self.on_open.then(on_success, on_error)

    def _setup_listeners(self):
        self._callbacks.update({
            spec.Connection.Start: self._on_start,
            spec.Connection.OpenOk: self._on_open_ok,
            spec.Connection.Secure: self._on_secure,
            spec.Connection.Tune: self._on_tune,
            spec.Connection.Close: self._on_close,
            spec.Connection.Blocked: self._on_blocked,
            spec.Connection.Unblocked: self._on_unblocked,
            spec.Connection.CloseOk: self._on_close_ok,
        })

    def connect(self, callback=None):
        while not self._handshake_complete:
            self.drain_events(timeout=self.connect_timeout)

    def _on_start(self, version_major, version_minor, server_properties,
                  mechanisms, locales, argsig='FsSs'):
        client_properties = self.client_properties
        self.version_major = version_major
        self.version_minor = version_minor
        self.server_properties = server_properties
        self.mechanisms = mechanisms.split(' ')
        self.locales = locales.split(' ')
        AMQP_LOGGER.debug(
            START_DEBUG_FMT,
            self.version_major, self.version_minor,
            self.server_properties, self.mechanisms, self.locales,
        )

        scap = server_properties.get('capabilities') or {}

        if scap.get('consumer_cancel_notify'):
            cap = client_properties.setdefault('capabilities', {})
            cap['consumer_cancel_notify'] = True
        if scap.get('connection.blocked'):
            cap = client_properties.setdefault('capabilities', {})
            cap['connection.blocked'] = True

        self.send_method(
            spec.Connection.StartOk, argsig,
            (client_properties, self.login_method,
             self.login_response, self.locale),
        )

    def _on_secure(self, challenge):
        pass

    def _on_tune(self, channel_max, frame_max, server_heartbeat, argsig='BlB'):
        client_heartbeat = self.client_heartbeat or 0
        self.channel_max = channel_max or self.channel_max
        self.frame_max = frame_max or self.frame_max
        self.server_heartbeat = server_heartbeat or 0

        # negotiate the heartbeat interval to the smaller of the
        # specified values
        if self.server_heartbeat == 0 or client_heartbeat == 0:
            self.heartbeat = max(self.server_heartbeat, client_heartbeat)
        else:
            self.heartbeat = min(self.server_heartbeat, client_heartbeat)

        # Ignore server heartbeat if client_heartbeat is disabled
        if not self.client_heartbeat:
            self.heartbeat = 0

        self.send_method(
            spec.Connection.TuneOk, argsig,
            (self.channel_max, self.frame_max, self.heartbeat),
            callback=self._on_tune_sent,
        )

    def _on_tune_sent(self, argsig='ssb'):
        self.send_method(
            spec.Connection.Open, argsig, (self.virtual_host, '', False),
        )

    def _on_open_ok(self):
        self._handshake_complete = True
        self.on_open(self)

    def FIXME(self, *args, **kwargs):
        pass

    def Transport(self, host, connect_timeout, ssl=False):
        return create_transport(host, connect_timeout, ssl)

    def Transport(self, host, connect_timeout, ssl=False):
        return create_transport(host, connect_timeout, ssl)

    @property
    def connected(self):
        return self.transport and self.transport.connected

    def collect(self):
        try:
            self.transport.close()

            temp_list = [x for x in values(self.channels) if x is not self]
            for ch in temp_list:
                ch.collect()
        except socket.error:
            pass  # connection already closed on the other end
        finally:
            self.transport = self.connection = self.channels = None

    def _get_free_channel_id(self):
        try:
            return self._avail_channel_ids.pop()
        except IndexError:
            raise ResourceError(
                'No free channel ids, current={0}, channel_max={1}'.format(
                    len(self.channels), self.channel_max), spec.Channel.open)

    def _claim_channel_id(self, channel_id):
        try:
            return self._avail_channel_ids.remove(channel_id)
        except ValueError:
            raise ConnectionError(
                'Channel %r already open' % (channel_id, ))

    def channel(self, channel_id=None, callback=None):
        """Fetch a Channel object identified by the numeric channel_id, or
        create that object if it doesn't already exist."""
        try:
            return self.channels[channel_id]
        except KeyError:
            return self.Channel(self, channel_id, on_open=callback)

    def is_alive(self):
        raise NotImplementedError('Use AMQP heartbeats')

    def inbound_method(self, channel_id, method_sig, payload, content):
        self.channels[channel_id].dispatch_method(method_sig, payload, content)

    def drain_events(self, timeout=None):
        return self.blocking_read(timeout)

    def blocking_read(self, timeout=None):
        read_frame = self.transport.read_frame
        if timeout is None:
            return self.on_inbound_frame(read_frame())

        # XXX use select
        sock = self.sock
        prev = sock.gettimeout()
        if prev != timeout:
            sock.settimeout(timeout)
        try:
            try:
                frame = read_frame()
            except SSLError as exc:
                # http://bugs.python.org/issue10272
                if 'timed out' in str(exc):
                    raise socket.timeout()
                # Non-blocking SSL sockets can throw SSLError
                if 'The operation did not complete' in str(exc):
                    raise socket.timeout()
                raise
            else:
                self.on_inbound_frame(frame)
        finally:
            if prev != timeout:
                sock.settimeout(prev)

    def on_inbound_method(self, channel_id, method_sig, payload, content):
        return self.channels[channel_id].dispatch_method(
            method_sig, payload, content,
        )

    def read_timeout(self, timeout=None):
        if timeout is None:
            return self.method_reader.read_method()

    def close(self, reply_code=0, reply_text='', method_sig=(0, 0),
              argsig='BssBB'):

        """Request a connection close

        This method indicates that the sender wants to close the
        connection. This may be due to internal conditions (e.g. a
        forced shut-down) or due to an error handling a specific
        method, i.e. an exception.  When a close is due to an
        exception, the sender provides the class and method id of the
        method which caused the exception.

        RULE:

            After sending this method any received method except the
            Close-OK method MUST be discarded.

        RULE:

            The peer sending this method MAY use a counter or timeout
            to detect failure of the other peer to respond correctly
            with the Close-OK method.

        RULE:

            When a server receives the Close method from a client it
            MUST delete all server-side resources associated with the
            client's context.  A client CANNOT reconnect to a context
            after sending or receiving a Close method.

        PARAMETERS:
            reply_code: short

                The reply code. The AMQ reply codes are defined in AMQ
                RFC 011.

            reply_text: shortstr

                The localised reply text.  This text can be logged as an
                aid to resolving issues.

            class_id: short

                failing method class

                When the close is provoked by a method exception, this
                is the class of the method.

            method_id: short

                failing method ID

                When the close is provoked by a method exception, this
                is the ID of the method.

        """
        if self.transport is None:
            # already closed
            return

        return self.send_method(
            spec.Connection.Close, argsig,
            (reply_code, reply_text, method_sig[0], method_sig[1]),
            wait=spec.Connection.CloseOk,
        )

    def _on_close(self, reply_code, reply_text, class_id, method_id):
        """Request a connection close

        This method indicates that the sender wants to close the
        connection. This may be due to internal conditions (e.g. a
        forced shut-down) or due to an error handling a specific
        method, i.e. an exception.  When a close is due to an
        exception, the sender provides the class and method id of the
        method which caused the exception.

        RULE:

            After sending this method any received method except the
            Close-OK method MUST be discarded.

        RULE:

            The peer sending this method MAY use a counter or timeout
            to detect failure of the other peer to respond correctly
            with the Close-OK method.

        RULE:

            When a server receives the Close method from a client it
            MUST delete all server-side resources associated with the
            client's context.  A client CANNOT reconnect to a context
            after sending or receiving a Close method.

        PARAMETERS:
            reply_code: short

                The reply code. The AMQ reply codes are defined in AMQ
                RFC 011.

            reply_text: shortstr

                The localised reply text.  This text can be logged as an
                aid to resolving issues.

            class_id: short

                failing method class

                When the close is provoked by a method exception, this
                is the class of the method.

            method_id: short

                failing method ID

                When the close is provoked by a method exception, this
                is the ID of the method.

        """
        self._x_close_ok()
        raise error_for_code(reply_code, reply_text,
                             (class_id, method_id), ConnectionError)

    def _on_blocked(self):
        """RabbitMQ Extension."""
        reason = 'connection blocked, see broker logs'
        if self.on_blocked:
            return self.on_blocked(reason)

    def _on_unblocked(self):
        if self.on_unblocked:
            return self.on_unblocked()

    def _x_close_ok(self):
        """Confirm a connection close

        This method confirms a Connection.Close method and tells the
        recipient that it is safe to release resources for the
        connection and close the socket.

        RULE:

            A peer that detects a socket closure without having
            received a Close-Ok handshake method SHOULD log the error.

        """
        self.send_method(spec.Connection.CloseOk, callback=self.collect)

    def _on_close_ok(self):
        """Confirm a connection close

        This method confirms a Connection.Close method and tells the
        recipient that it is safe to release resources for the
        connection and close the socket.

        RULE:

            A peer that detects a socket closure without having
            received a Close-Ok handshake method SHOULD log the error.

        """
        self.collect()

    def send_heartbeat(self):
        try:
            self._frame_writer.send((8, 0, None, None, None))
        except StopIteration:
            raise RecoverableConnectionError('connection already closed')

    def heartbeat_tick(self, rate=2):
        """Send heartbeat packets, if necessary, and fail if none have been
        received recently.  This should be called frequently, on the order of
        once per second.

        :keyword rate: Ignored
        """
        if not self.heartbeat:
            return

        # treat actual data exchange in either direction as a heartbeat
        sent_now = self.bytes_sent
        recv_now = self.bytes_recv
        if self.prev_sent is None or self.prev_sent != sent_now:
            self.last_heartbeat_sent = monotonic()
        if self.prev_recv is None or self.prev_recv != recv_now:
            self.last_heartbeat_received = monotonic()
        self.prev_sent, self.prev_recv = sent_now, recv_now

        # send a heartbeat if it's time to do so
        if monotonic() > self.last_heartbeat_sent + self.heartbeat:
            self.send_heartbeat()
            self.last_heartbeat_sent = monotonic()

        # if we've missed two intervals' heartbeats, fail; this gives the
        # server enough time to send heartbeats a little late
        if (self.last_heartbeat_received and
                self.last_heartbeat_received + 2 *
                self.heartbeat < monotonic()):
            raise ConnectionForced('Too many heartbeats missed')

    @property
    def sock(self):
        return self.transport.sock

    @property
    def server_capabilities(self):
        return self.server_properties.get('capabilities') or {}
