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
from __future__ import absolute_import, print_function

import logging
import socket
import sys

from collections import defaultdict, deque
from struct import pack, unpack_from, pack_into

from . import spec
from .basic_message import Message
from .exceptions import METHOD_NAME_MAP, ConnectionError, UnexpectedFrame
from .five import range
from .transport import _UNAVAIL
from .utils import coro, get_logger

__all__ = ['frame_handler', 'frame_writer']

logger = get_logger(__name__)
debug = logger.debug


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
            #if debug:
            #    print('<< method: %s', METHOD_NAME_MAP[method_sig])

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


@coro
def frame_writer(connection, transport, outbound,
                 pack=pack, pack_into=pack_into, range=range, len=len,
                 max_buffers=10):
    write = outbound.append
    outbound_ready = connection._outbound_ready

    # memoryview first supported in Python 2.7
    # Initial support was very shaky, so could be we have to
    # check for a bugfix release.
    if sys.version_info >= (2, 7):
        no_pybuf = 1
        #buf = bytearray(connection.frame_max - 8)
        #view = memoryview(buf)
    else:
        no_pyfuf = 1
        #no_pybuf, buf, view = 1, None, None

    buffers = connection.buffers = deque(
        bytearray(connection.frame_max - 8) for _ in range(max_buffers)
    )

    while 1:
        chunk_size = connection.frame_max - 8
        offset = 0
        type_, channel, method_sig, args, content, callback = yield
        if debug:
            debug('>> frame %r for channel %r: %s',
                  type_, channel, METHOD_NAME_MAP[method_sig])

        if content:
            body = content.body
            bodylen = len(body)
            bigbody = bodylen > chunk_size
        else:
            body, bodylen, bigbody = None, 0, 0

        if no_pybuf or bigbody:
            # ## SLOW: string copy and write for every frame
            frame = (''.join([pack('>HH', *method_sig), args])
                     if type_ == 1 else '')  # encode method frame
            framelen = len(frame)
            if body:
                write((pack('>BHI%dsB' % framelen,
                            1, channel, framelen, frame, 0xce), 0, None))
                properties = content._serialize_properties()
                frame = b''.join([
                    pack('>HHQ', method_sig[0], 0, len(body)),
                    properties,
                ])
                framelen = len(frame)
                write((pack('>BHI%dsB' % framelen,
                            2, channel, framelen, frame, 0xce), 0, None))

                pieces = []
                for i in range(0, bodylen, chunk_size):
                    frame = body[i:i + chunk_size]
                    this_size = len(frame)
                    pieces.append(pack('>BHI%dsB' % this_size,
                                  3, channel, this_size, frame, 0xce))
                outbound.extend((piece, 0, None) for piece in pieces[:-1])
                outbound.append((pieces[-1], 0, callback))
            else:
                write((pack('>BHI%dsB' % framelen,
                       type_, channel, framelen, frame, 0xce), 0, callback))

        else:
            frame = (''.join([pack('>HH', *method_sig), args])
                     if type_ == 1 else '')
            framelen = len(frame)
            if body:
                try:
                    buf, borrowed = buffers.popleft(), 1
                except IndexError:
                    buf, borrowed = bytearray(8 + framelen), 0
            else:
                buf, borrowed = bytearray(8 + framelen), 0

            buf = bytearray(connection.frame_max - 8)
            view = memoryview(buf)
            # ## FAST: pack into buffer and single write
            pack_into('>BHI%dsB' % framelen, buf, offset,
                      type_, channel, framelen, frame, 0xce)
            offset += 8 + framelen
            if body:
                properties = content._serialize_properties()
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
                          3, channel, framelen, body, 0xce)
                offset += 8 + framelen

            #print('FRAME: %r' % (view[:offset].tobytes(), ))
            write((view[:offset], borrowed, callback))
        outbound_ready()

        connection.bytes_sent += 1


from io import BytesIO
import os

class Buffer(object):

    def __init__(self, maxsize):
        self.maxsize = maxsize
        self.buf = BytesIO()
        self.size = 0
        self.offset = 0

    def write(self, data):
        self.buf.write(data)
        self.size += len(data)

    def read(self):
        self.buf.seek(self.offset)
        try:
            return self.buf.read()
        finally:
            self.buf.seek(0, os.SEEK_END)

    def consume(self, size):
        self.offset += size
        self.size -= size

        if not self.size and self.offset >= self.maxsize:
            self.buf.close()
            self.buf = BytesIO()
            self.offset = 0

    def flush(self):
        self.consume(self.size)

    def __len__(self):
        return self.size


@coro
def inbound_handler(conn, frames, bufsize=2 ** 19, readsize=2 ** 17,
                    error=socket.error, unpack_from=unpack_from):
    recv_into = conn.sock.recv_into
    recv = conn.sock.recv
    need = 8

    buffer = Buffer(bufsize)

    while 1:
        _ = (yield)  # noqa
        try:
            R = recv(readsize)
            bytes_read = len(R)
        except error as exc:
            if exc.errno not in _UNAVAIL:
                raise

        if bytes_read == 0:
            raise ConnectionError('Connection broken')

        buffer.write(R)
        data = buffer.read()
        bytes_have = len(data)
        if bytes_have >= need:
            frame_offset = 0
            while bytes_have - frame_offset >= need:
                frame_start_offset = frame_offset
                frame_type, channel, size = unpack_from(
                    '>BHI', data, frame_offset,
                )
                frame_offset += 7
                if bytes_have - frame_start_offset < size + 8:
                    need, frame_offset = 8 + size, frame_start_offset
                    break
                print('FRAME OFFSET + SIZE: %r' % (frame_offset + size, ))
                print('OFFSET: %r SIZE: %r DATA: %r' % (buffer.offset,
                    buffer.size, len(data)))
                assert data[frame_offset + size] == '\xCE'
                need = 8
                frames.append((
                    frame_type, channel,
                    data[frame_offset:frame_offset + size],
                ))
                frame_offset += size + 1
                assert frame_offset == frame_start_offset + 8 + size
            buffer.consume(frame_offset)
