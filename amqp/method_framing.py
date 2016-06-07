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
from __future__ import absolute_import, unicode_literals

from collections import defaultdict
from struct import pack, unpack_from, pack_into

from . import spec
from .basic_message import Message
from .exceptions import UnexpectedFrame
from .five import range
from .utils import coro, str_to_bytes

__all__ = ['frame_handler', 'frame_writer']

#
# set of methods that require both a content frame and a body frame.
#
_CONTENT_METHODS = frozenset([
    spec.Basic.Return,
    spec.Basic.Deliver,
    spec.Basic.GetOk,
])


def frame_handler(connection, callback,
                  unpack_from=unpack_from, content_methods=_CONTENT_METHODS):
    expected_types = defaultdict(lambda: 1)
    partial_messages = {}

    def on_frame(frame):
        frame_type, channel, buf = frame
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

    return on_frame


@coro
def frame_writer(connection, transport,
                 pack=pack, pack_into=pack_into, range=range, len=len,
                 bytes=bytes, str_to_bytes=str_to_bytes):
    write = transport.write

    # memoryview first supported in Python 2.7
    # Initial support was very shaky, so could be we have to
    # check for a bugfix release.
    buf = bytearray(connection.frame_max - 8)
    view = memoryview(buf)

    while 1:
        chunk_size = connection.frame_max - 8
        offset = 0
        type_, channel, method_sig, args, content = yield
        if content:
            body = content.body
            bodylen = len(body)
            bigbody = bodylen > chunk_size
        else:
            body, bodylen, bigbody = None, 0, 0

        if bigbody:
            # ## SLOW: string copy and write for every frame
            frame = (b''.join([pack(b'>HH', *method_sig),
                               str_to_bytes(args)])
                     if type_ == 1 else b'')  # encode method frame
            framelen = len(frame)
            write(pack((u'>BHI%dsB' % framelen).encode(),
                       type_, channel, framelen, frame, 0xce))
            if body:
                properties = content._serialize_properties()
                frame = b''.join([
                    pack(b'>HHQ', method_sig[0], 0, len(body)),
                    properties,
                ])
                framelen = len(frame)
                write(pack((u'>BHI%dsB' % framelen).encode(),
                           2, channel, framelen, frame, 0xce))

                for i in range(0, bodylen, chunk_size):
                    frame = body[i:i + chunk_size]
                    framelen = len(frame)
                    write(pack((u'>BHI%dsB' % framelen).encode(),
                               3, channel, framelen,
                               str_to_bytes(frame), 0xce))

        else:
            # ## FAST: pack into buffer and single write
            frame = (b''.join([pack(b'>HH', *method_sig),
                               str_to_bytes(args)])
                     if type_ == 1 else b'')
            framelen = len(frame)
            pack_into((u'>BHI%dsB' % framelen).encode(), buf, offset,
                      type_, channel, framelen, frame, 0xce)
            offset += 8 + framelen
            if body:
                properties = content._serialize_properties()
                frame = b''.join([
                    pack(b'>HHQ', method_sig[0], 0, len(body)),
                    properties,
                ])
                framelen = len(frame)

                pack_into((u'>BHI%dsB' % framelen).encode(), buf, offset,
                          2, channel, framelen, frame, 0xce)
                offset += 8 + framelen

                framelen = len(body)
                pack_into((u'>BHI%dsB' % framelen).encode(), buf, offset,
                          3, channel, framelen, str_to_bytes(body), 0xce)
                offset += 8 + framelen

            write(view[:offset])

        connection.bytes_sent += 1
