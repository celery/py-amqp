"""
AMQP 0-8 Client Library
Non-Blocking Sockets Implementation

"""
# Copyright (C) 2007-2008 Barry Pederson <bp@barryp.org>
# Copyright (C) 2008 LShift Ltd., Cohesive Financial Technologies LLC.,
#                    and Rabbit Technologies Ltd.
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

import socket
from errno import *
from time import sleep, time

from client_0_8 import Connection
from util_0_8 import AMQPReader

__all__ =  [
            'NonBlockingConnection',
            'nbloop',
           ]


class NonBlockingException(Exception):
    pass


class NonBlockingSocket(object):
    """
    Wrap a socket so that its read() and write() methods
    raise a NonBlockingException if they would block.  Also
    keep track of the time it last receives data.

    """
    def __init__(self, sock, **kwargs):
        self.sock = sock
        self.sock.setblocking(0)

        self.nb_sleep = kwargs.get('nb_sleep', 0.1)

        self.write_buf = ''
        self.read_buf = ''
        self.read_p = 0     # pointer to current postion in read buffer
        self.last_recv = time()

        self.with_nb_exc = False

    def close(self):
        self.sock.close()

    def flush(self):
        pass

    def write(self, data):
        # detect a potential deadlock.
        # This might happen if we get a request to write from high-level
        # (i.e., not from read() via __do_write), while not all data
        # have been written yet.
        if data and self.read_p < len(self.read_buf):
            raise Exception("Deadlock: data=%r read_buf=%r read_p=%d" %
                (data, self.read_buf, self.read_p))
        assert self.read_p == len(self.read_buf)

        self.write_buf += data
        self.read_buf = ''
        self.read_p = 0
        self.__do_write()

    def __do_write(self):
        while self.write_buf:
            try:
                sent = self.sock.send(self.write_buf)
                self.write_buf = self.write_buf[sent:]
            except socket.error, (err, _):
                if err in (EAGAIN,):
                    sleep(self.nb_sleep)
                    if self.with_nb_exc:
                        raise NonBlockingException
                else:
                    raise


    def read(self, n):
        # do not proceed to next read until all data from
        # write buffer are sent to server
        if self.write_buf:
            self.__do_write()

        # read data from socket into buffer if buffer is not long enough
        while len(self.read_buf) < self.read_p + n:
            try:
                # try to read as much as we can
                self.read_buf += self.sock.recv(1024)
                self.last_recv = time()
            except socket.error, (err, _):
                if err in (EAGAIN,):
                    sleep(self.nb_sleep)
                    if self.with_nb_exc:
                        self.read_p = 0
                        raise NonBlockingException
                else:
                    raise

        # redundant assert, but just in case
        assert len(self.read_buf) >= self.read_p + n
        self.read_p += n
        return self.read_buf[self.read_p-n:self.read_p]


#---------------------------------------------------


class NonBlockingConnection(Connection):
    """
    An AMQP connection that uses non-blocking sockets
    that raise NonBlockingException when they would block.

    """
    def __init__(self, *args, **kwargs):
        """
        Wrap the client_0_8.Connection.__init__ method
        to turn the socket into a Non-blocking socket.

        """
        if kwargs.get('ssl', False):
            raise ValueError, "NonBlockingConnection does not yet support SSL"

        assert 'nb_callback' in kwargs, 'nb_callback is required'
        self.nb_callback = kwargs['nb_callback']
        assert callable(self.nb_callback)

        if 'connect_timeout' not in kwargs:
            kwargs['connect_timeout'] = kwargs.get('nb_connect_timeout', 15.0)

        Connection.__init__(self, *args, **kwargs)

        self.sock = NonBlockingSocket(self.sock, **kwargs)
        self.out = self.sock
        self.input = AMQPReader(self.out)

#-------------------------------------------


def nbloop(channels):
    if not channels:
        return

    # make sure we have at most 1 channel per connection
    s2ch = { }  # socket -> channel mapping
    for ch in channels:
        if ch.connection.sock in s2ch:
            raise Exception("nbloop: at most 1 channel per connection")
        else:
            s2ch[ch.connection.sock] = ch

    try:
        for s in s2ch:
            s.with_nb_exc = True
        while True:
            for sock,ch in s2ch.items():
                try:
                    if ch.callbacks:
                        ch.wait()
                except NonBlockingException:
                    ch.connection.nb_callback(ch)
    finally:
        # make sure all data from sockets' buffers have been read and
        # processed
        while s2ch:
            for sock,ch in s2ch.items():
                try:
                    ch.wait()
                except Exception, e:
                    pass
                if len(sock.read_buf) == sock.read_p:
                    del(s2ch[sock])
                    sock.with_nb_exc = False

### EOF ###
