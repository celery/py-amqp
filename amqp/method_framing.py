"""Convert between frames and higher-level AMQP methods."""
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
from collections import defaultdict
from struct import pack, unpack_from, pack_into
from typing import Callable, FrozenSet, cast
from typing import MutableMapping  # noqa: F401
from . import spec
from .basic_message import Message
from .exceptions import UnexpectedFrame
from .spec import method_sig_t
from .types import (
    AbstractChannelT, ConnectionT,
    ConnectionFrameHandlerT, ConnectionFrameWriterT,
    MessageT, TransportT,
)
from .utils import want_bytes

__all__ = ['frame_handler', 'frame_writer']

#: Set of methods that require both a content frame and a body frame.
_CONTENT_METHODS: FrozenSet[method_sig_t] = frozenset([
    spec.Basic.Return,
    spec.Basic.Deliver,
    spec.Basic.GetOk,
])


#: Number of bytes reserved for protocol in a content frame.
#: We use this to calculate when a frame exceeeds the max frame size,
#: and if it does not the message will fit into the preallocated buffer.
FRAME_OVERHEAD = 40

FrameHandlerCallback = Callable[[AbstractChannelT, int, str, bytes], None]


def frame_handler(
        connection: ConnectionT,
        callback: FrameHandlerCallback,
        content_methods: FrozenSet[spec.method_sig_t] = _CONTENT_METHODS,
        unpack_from: Callable = unpack_from) -> ConnectionFrameHandlerT:
    """Create closure that reads frames."""
    expected_types: MutableMapping[int, int] = defaultdict(lambda: 1)
    partial_messages = {}

    async def on_frame(frame):
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
                await callback(channel, method_sig, buf, None)

        elif frame_type == 2:
            msg = partial_messages[channel]
            msg.inbound_header(buf)

            if msg.ready:
                # bodyless message, we're done
                expected_types[channel] = 1
                partial_messages.pop(channel, None)
                await callback(
                    channel, msg.frame_method, msg.frame_args, msg)
            else:
                # wait for the content-body
                expected_types[channel] = 3
        elif frame_type == 3:
            msg = partial_messages[channel]
            msg.inbound_body(buf)
            if msg.ready:
                expected_types[channel] = 1
                partial_messages.pop(channel, None)
                await callback(
                    channel, msg.frame_method, msg.frame_args, msg)
        elif frame_type == 8:
            # bytes_recv already updated
            pass

    return on_frame


def frame_writer(connection: ConnectionT,
                 transport: TransportT,
                 pack: Callable = pack,
                 pack_into: Callable = pack_into,
                 range: Callable = range,
                 len: Callable = len,
                 want_bytes: Callable = want_bytes) -> ConnectionFrameWriterT:
    """Create closure that writes frames."""
    write = transport.write

    # memoryview first supported in Python 2.7
    # Initial support was very shaky, so could be we have to
    # check for a bugfix release.
    buf = bytearray(connection.frame_max - 8)
    view = memoryview(buf)

    async def write_frame(type_: int,
                          channel: int,
                          method_sig: method_sig_t = None,
                          args: bytes = None,
                          content: MessageT = None,
                          timeout: float = None) -> None:
        chunk_size = connection.frame_max - 8
        offset = 0
        properties = None  # type: bytes
        args = want_bytes(args)
        if content:
            properties = content._serialize_properties()
            body = content.body
            bodylen = len(body)
            framelen = (
                len(args) +
                (len(properties) or 0) +
                bodylen +
                FRAME_OVERHEAD
            )
            bigbody = framelen > chunk_size
        else:
            body, bodylen, bigbody = None, 0, 0

        if bigbody:
            # ## SLOW: string copy and write for every frame
            frame = (b''.join([pack('>HH', *method_sig), args])
                     if type_ == 1 else b'')  # encode method frame
            framelen = len(frame)
            write(pack('>BHI%dsB' % framelen,
                       type_, channel, framelen, frame, 0xce), timeout=timeout)
            if body:
                frame = b''.join([
                    pack('>HHQ', method_sig[0], 0, len(body)),
                    properties,
                ])
                framelen = len(frame)
                write(pack('>BHI%dsB' % framelen,
                           2, channel, framelen, frame, 0xce), timeout=timeout)

                for i in range(0, bodylen, chunk_size):
                    frame = body[i:i + chunk_size]
                    framelen = len(frame)
                    write(pack('>BHI%dsB' % framelen,
                               3, channel, framelen,
                               want_bytes(frame), 0xce), timeout=timeout)

        else:
            # ## FAST: pack into buffer and single write
            frame = (b''.join([pack('>HH', *method_sig), args])
                     if type_ == 1 else b'')
            framelen = len(frame)
            pack_into('>BHI%dsB' % framelen, buf, offset,
                      type_, channel, framelen, frame, 0xce)
            offset += 8 + framelen
            if body:
                frame = b''.join([
                    pack('>HHQ', method_sig[0], 0, len(body)),
                    properties,
                ])
                framelen = len(frame)

                pack_into('>BHI%dsB' % framelen, buf, offset,
                          2, channel, framelen, frame, 0xce)
                offset += 8 + framelen

                framelen = len(body)
                pack_into('>BHI%dsB' % framelen, buf, offset,
                          3, channel, framelen, want_bytes(body), 0xce)
                offset += 8 + framelen

            await write(cast(bytes, view[:offset]), timeout=timeout)

        connection.bytes_sent += 1
    return write_frame
