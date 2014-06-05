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
from struct import pack, unpack_from

from . import spec
from .basic_message import Message
from .exceptions import AMQPError, UnexpectedFrame
from .five import range, string
from .utils import coro

__all__ = ['MethodWriter', 'frame_handler']

#
# set of methods that require both a content frame and a body frame.
#
_CONTENT_METHODS = frozenset([
    spec.Basic.Return,
    spec.Basic.Deliver,
    spec.Basic.GetOk,
])


@coro
def frame_handler(connection, callback,
                  unpack_from=unpack_from, content_methods=_CONTENT_METHODS):
    expected_types = defaultdict(lambda: 1)
    partial_messages = {}
    while 1:
        frame_type, channel, buf = yield
        connection.bytes_recv += 1
        if frame_type not in (expected_types[channel], 8):
            raise UnexpectedFrame(
                'Received frame {0} while expecting type: {1}'.format(
                    frame_type, expected_types[channel]),
            )
        elif frame_type == 1:
            method_sig = unpack_from('>HH', buf, 0)

            if method_sig in content_methods:
                # Save what we've got so far and wait for the content-header
                partial_messages[channel] = Message(
                    frame_method=method_sig, frame_args=buf,
                )
                expected_types[channel] = 2
            else:
                callback(channel, method_sig, buf, None)

        elif frame_type == 2:
            msg = partial_messages[channel]
            msg.inbound_header(buf)

            if msg.ready:
                # bodyless message, we're done
                expected_types[channel] = 1
                partial_messages.pop(channel, None)
                callback(channel, msg.frame_method, msg.frame_args, msg)
            else:
                # wait for the content-body
                expected_types[channel] = 3
        elif frame_type == 3:
            msg = partial_messages[channel]
            msg.inbound_body(buf)
            if msg.ready:
                expected_types[channel] = 1
                partial_messages.pop(channel, None)
                callback(channel, msg.frame_method, msg.frame_args, msg)
        elif frame_type == 8:
            # bytes_recv already updated
            pass


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
