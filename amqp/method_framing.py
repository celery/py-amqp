"""Convert between frames and higher-level AMQP methods"""
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

from collections import defaultdict
from struct import pack, unpack

try:
    bytes
except NameError:
    # Python 2.5 and lower
    bytes = str

from .basic_message import Message
from .exceptions import AMQPError, UnexpectedFrame
from .five import Queue, range, string
from .serialization import AMQPReader
from .utils import noop, promise

__all__ = ['MethodReader']

#
# MethodReader needs to know which methods are supposed
# to be followed by content headers and bodies.
#
_CONTENT_METHODS = [
    (60, 50),  # Basic.return
    (60, 60),  # Basic.deliver
    (60, 71),  # Basic.get_ok
]


class _PartialMessage(object):
    """Helper class to build up a multi-frame method."""

    def __init__(self, method_sig, args):
        self.method_sig = method_sig
        self.args = args
        self.msg = Message()
        self.body_parts = []
        self.body_received = 0
        self.body_size = None
        self.complete = False

    def add_header(self, payload):
        class_id, weight, self.body_size = unpack('>HHQ', payload[:12])
        self.msg._load_properties(payload[12:])
        self.complete = (self.body_size == 0)

    def add_payload(self, payload):
        self.body_parts.append(payload)
        self.body_received += len(payload)

        if self.body_received == self.body_size:
            self.msg.body = bytes().join(self.body_parts)
            self.complete = True


class MethodReader(object):
    """Helper class to receive frames from the broker, combine them if
    necessary with content-headers and content-bodies into complete methods.

    Normally a method is represented as a tuple containing
    (channel, method_sig, args, content).

    In the case of a framing error, an :exc:`ConnectionError` is placed
    in the queue.

    In the case of unexpected frames, a tuple made up of
    ``(channel, ChannelError)`` is placed in the queue.

    """

    def __init__(self, source):
        self.source = source
        self.queue = Queue()
        self.running = False
        self.partial_messages = {}
        self.heartbeats = 0
        # For each channel, which type is expected next
        self.expected_types = defaultdict(lambda: 1)
        # not an actual byte count, just incremented whenever we receive
        self.bytes_recv = 0
        self.read_frame = self.source.read_frame
        self.put_method = self.queue.put

    def on_method_error(self, exc):
        self.put_message(exc)

    def on_method_received(self, frame_type, channel, payload):
        self.bytes_recv += 1

        if frame_type not in (self.expected_types[channel], 8):
            self.put_method((
                channel,
                UnexpectedFrame(
                    'Received frame {0} while expecting type: {1}'.format(
                        frame_type, self.expected_types[channel]),
                )
            ))
        elif frame_type == 1:
            self._process_method_frame(channel, payload)
        elif frame_type == 2:
            self._process_content_header(channel, payload)
        elif frame_type == 3:
            self._process_content_body(channel, payload)
        elif frame_type == 8:
            self._process_heartbeat(channel, payload)

    def _next_method(self):
        """Read the next method from the source, once one complete method has
        been assembled it is placed in the internal queue."""
        empty = self.queue.empty
        read_frame = self.read_frame
        while empty():
            read_frame(promise(self.on_method_received,
                               on_error=self.on_method_error))

    def _process_heartbeat(self, channel, payload):
        self.heartbeats += 1

    def _process_method_frame(self, channel, payload):
        """Process Method frames"""
        method_sig = unpack('>HH', payload[:4])
        args = AMQPReader(payload[4:])

        if method_sig in _CONTENT_METHODS:
            #
            # Save what we've got so far and wait for the content-header
            #
            self.partial_messages[channel] = _PartialMessage(method_sig, args)
            self.expected_types[channel] = 2
        else:
            self.queue.put((channel, method_sig, args, None))

    def _process_content_header(self, channel, payload):
        """Process Content Header frames"""
        partial = self.partial_messages[channel]
        partial.add_header(payload)

        if partial.complete:
            #
            # a bodyless message, we're done
            #
            self.queue.put((channel, partial.method_sig,
                            partial.args, partial.msg))
            self.partial_messages.pop(channel, None)
            self.expected_types[channel] = 1
        else:
            #
            # wait for the content-body
            #
            self.expected_types[channel] = 3

    def _process_content_body(self, channel, payload):
        """Process Content Body frames"""
        partial = self.partial_messages[channel]
        partial.add_payload(payload)
        if partial.complete:
            #
            # Stick the message in the queue and go back to
            # waiting for method frames
            #
            self.queue.put((channel, partial.method_sig,
                            partial.args, partial.msg))
            self.partial_messages.pop(channel, None)
            self.expected_types[channel] = 1

    def read_method(self):
        """Read a method from the peer."""
        self._next_method()
        m = self.queue.get()
        if isinstance(m, Exception):
            raise m
        if isinstance(m, tuple) and isinstance(m[1], AMQPError):
            raise m[1]
        return m


class MethodWriter(object):
    """Convert AMQP methods into AMQP frames and send them out
    to the peer."""

    def __init__(self, dest, frame_max):
        self.dest = dest
        self.frame_max = frame_max
        self.bytes_sent = 0
        self.write_frame = self.dest.write_frame
        self.chunk_size = self.frame_max - 8

    def on_header_frame_sent(self, channel, method_sig, body, properties,
            on_complete):
        print('HEADER FRAME SENT: %r' % (on_complete, ))
        body_size = len(body)
        payload = pack('>HHQ', method_sig[0], 0, len(body)) + properties
        if body:
            callback = promise(self.write_body, (channel, buffer(body),
                0, body_size, on_complete))
        else:
            callback = None
        self.write_frame(1, channel, payload, callback)
        if not body:
            on_complete()

    def on_bytes_sent(self):
        self.bytes_sent += 1

    def write_body(self, channel, buf, offset, size, on_complete=None):
        chunk_size = self.chunk_size
        offset = offset or 0
        print('SIZE: %r OFFSET: %r' % (size, offset))
        if offset >= size:
            print('BUF COMPLETE')
            return on_complete()

        callback = promise(self.write_body,
                           (channel, buf, offset + self.chunk_size, size,
                               on_complete))
        self.write_frame(3, channel, buf[offset:offset + chunk_size],
                         callback)

    def write_method(self, channel, method_sig, args,
                     content=None, on_complete=None):
        on_complete = on_complete or noop()
        write_frame = self.dest.write_frame
        payload = pack('>HH', method_sig[0], method_sig[1]) + args

        if content:
            # do this early, so we can raise an exception if there's a
            # problem with the content properties, before sending the
            # first frame
            body = content.body
            if isinstance(body, string):
                coding = content.properties.get('content_encoding', None)
                if coding is None:
                    coding = content.properties['content_encoding'] = 'UTF-8'

                body = body.encode(coding)
            properties = content._serialize_properties()

        if content:
            callback = promise(
                self.on_header_frame_sent,
                (channel, method_sig, body, properties, on_complete),
            )
        else:
            callback = promise(self.on_bytes_sent).then(on_complete)
        write_frame(1, channel, payload, callback)

