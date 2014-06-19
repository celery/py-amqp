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


@coro
def inbound_handler(conn, frames, bufsize=2 ** 17, readsize=2 ** 10,
                    error=socket.error, unpack_from=unpack_from):
    print('HELLO')
    recv_into = conn.sock.recv_into

    buf = bytearray(bufsize)
    view = memoryview(buf)
    need = 8
    offset = 0
    boundary = 0

    while 1:
        print('START')
        _ = (yield)  # noqa
        print('OFFSET: %r' % (offset, ))
        slice = None
        slice = view[offset:]
        if bufsize > 2 ** 17:
            raise Exception('WTF WTF')
        if not len(slice):
            print('EXTEND: %r' %(readsize, ))
            view = slice = None
            del(view)
            del(slice)
            del(data)
            buf.extend(bytearray(readsize))
            bufsize += readsize
            view = memoryview(buf)
            print('BUFSIZE: %r OFFSET: %r X: %r' % (bufsize, offset,
                len(view[offset:]), ))
            slice = view[offset:]
        print("SLICE: %r BUF: %r" % (len(slice), len(buf)))
        print('@@@ BOUND: %r OFFSET: %r LEFT: %r' % (boundary, offset,
            len(slice)))
        try:
            print('+ BYTES READ!')
            bytes_read = recv_into(slice)
            print('- BYTES READ: %r' % (bytes_read, ))
        except error as exc:
            if exc.errno not in _UNAVAIL:
                raise

        if bytes_read == 0:
            raise ConnectionError('Connection broken')

        frame_offset = 0
        data = view[boundary:boundary + bytes_read + (offset - boundary)]
        bytes_have = len(data)
        while bytes_have - frame_offset >= need:
            frame_start_offset = frame_offset
            frame_type, channel, size = unpack_from(
                '>BHI', data, frame_offset,
            )
            frame_offset += 7
            if bytes_have - frame_start_offset < size + 8:
                if offset + size > bufsize:
                    rest = data[frame_start_offset:].tobytes()
                    buf[0:len(rest)] = rest
                    boundary, offset = 0, len(rest)
                else:
                    boundary, need, offset = (
                        offset + frame_start_offset, 8 + size, bytes_read,
                    )
                print('!!!!!!!!!!!BREAKING!!!!!!!!!!!')
                break
            assert data[frame_offset + size] == '\xCE'
            need = 8
            frames.append((
                frame_type, channel,
                data[frame_offset:frame_offset + size].tobytes(),
            ))
            frame_offset += size + 1
            assert frame_offset == frame_start_offset + 8 + size
        else:
            rest = bytes_have - frame_offset
            if rest:
                print('************* REST *************')
                offset += bytes_read
                boundary += bytes_read
                if offset >= bufsize:
                    buf[0:rest] = data[frame_offset:].tobytes()
                    boundary, offset = 0, rest
            else:
                boundary = offset = 0
