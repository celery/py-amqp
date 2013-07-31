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

from collections import defaultdict, deque
from struct import pack, unpack

try:
    bytes
except NameError:
    # Python 2.5 and lower
    bytes = str

from .basic_message import Message
from .exceptions import AMQPError, UnexpectedFrame
from .five import range, string
from .serialization import AMQPReader

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


def _partial_message(msg, method_sig, args):
    body_parts = []
    add_part = body_parts.append
    received = 0

    header = (yield)
    class_id, weight, body_size = unpack('>HHQ', header[:12])
    msg._load_properties(header[12:])
    if body_size != 0:
        while 1:
            part = (yield)
            add_part(part)
            received += len(part)

            if received >= body_size:
                if len(body_parts) > 1:
                    msg.body = bytes().join(body_parts)
                else:
                    msg.body = body_parts[0]
                break
    msg.complete = True


def PartialMessage(method_sig, args):
    msg = Message()
    it = _partial_message(msg, method_sig, args)
    next(it)
    return msg, it, method_sig, args


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
        parts = self.body_parts
        parts.append(payload)
        self.body_received += len(payload)

        if self.body_received == self.body_size:
            if len(parts) > 1:
                self.msg.body = bytes().join(parts)
            else:
                self.msg.body = parts[0]
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
        self.queue = deque()
        self.running = False
        self.partial_messages = {}
        self.heartbeats = 0
        # For each channel, which type is expected next
        self.expected_types = defaultdict(lambda: 1)
        # not an actual byte count, just incremented whenever we receive
        self.bytes_recv = 0
        self._quick_put = self.queue.append
        self._quick_get = self.queue.popleft
        self.it = self.iter()

    def iter(self, unpack=unpack):
        read_frame = self.source.read_frame
        partials = self.partial_messages
        expected_types = self.expected_types
        ITEM = None
        while 1:
            while ITEM is None:
                frame_type, channel, payload = read_frame()
                self.bytes_recv += 1

                if frame_type not in (expected_types[channel], 8):
                    raise UnexpectedFrame(
                        'Received frame {0} while expecting type: {1}'.format(
                            frame_type, expected_types[channel]),
                    )
                elif frame_type == 1:
                    method_sig = unpack('>HH', payload[:4])
                    args = AMQPReader(payload[4:])
                    if method_sig in _CONTENT_METHODS:
                        # Save what we've got so far and wait for the content-header
                        partials[channel] = PartialMessage(method_sig, args)
                        expected_types[channel] = 2
                    else:
                        ITEM = channel, method_sig, args, None
                elif frame_type == 2:
                    msg, it, msig, margs = partials[channel]
                    it.send(payload)

                    if msg.complete:
                        # a bodyless message, we're done
                        ITEM = channel, msig, margs, msg
                        partials.pop(channel, None)
                        expected_types[channel] = 1
                    else:
                        # wait for the content-body
                        expected_types[channel] = 3
                elif frame_type == 3:
                    msg, it, msig, margs = partials[channel]
                    try:
                        it.send(payload)
                    except StopIteration:
                        pass
                    if msg.complete:
                        #
                        # Stick the message in the queue and go back to
                        # waiting for method frames
                        #
                        ITEM = channel, msig, margs, msg
                        partials.pop(channel, None)
                        expected_types[channel] = 1
                elif frame_type == 8:
                    self.heartbeats += 1
            yield ITEM
            ITEM = None


    def _next_method(self):
        """Read the next method from the source, once one complete method has
        been assembled it is placed in the internal queue."""
        return next(self.it)

    def read_method(self):
        """Read a method from the peer."""
        try:
            X = next(self.it)
        except StopIteration:
            self.it = self.iter()
        except Exception:
            self.it = self.iter()
            raise
        return X


class MethodWriter(object):
    """Convert AMQP methods into AMQP frames and send them out
    to the peer."""

    def __init__(self, dest, frame_max):
        self.dest = dest
        self.frame_max = frame_max
        self.bytes_sent = 0

    def write_method(self, channel, method_sig, args, content=None):
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

        write_frame(1, channel, payload)

        if content:
            payload = pack('>HHQ', method_sig[0], 0, len(body)) + properties

            write_frame(2, channel, payload)

            chunk_size = self.frame_max - 8
            for i in range(0, len(body), chunk_size):
                write_frame(3, channel, body[i:i + chunk_size])
        self.bytes_sent += 1
