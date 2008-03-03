"""
AMQP 0-8 Client Library
Non-Blocking Sockets Implementation

"""
# Copyright (C) 2007 Barry Pederson <bp@barryp.org>
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


import client_0_8
from util_0_8 import AMQPReader, AMQPWriter
from Queue import Queue
from struct import unpack
import socket, time
from errno import *

__all__ =  [
            'NonBlockingConnection',
            'nbloop'
           ]


class NonBlockingException(Exception): pass

class NonBlockingSocket:
    def __init__(self, host, port, **kwargs):
        if kwargs.has_key('ssl') and kwargs['ssl']:
            raise ValueError, "NonBlockingSocket does not yet support SSL"

        try: self.connect_timeout = kwargs['nb_connect_timeout']
        except KeyError: self.connect_timeout = 15.0

        try: self.nb_sleep = kwargs['nb_sleep']
        except KeyError: self.nb_sleep = 0.1

        self.host = host
        self.port = port
        self.write_buf = ""
        self.read_buf = ""
        self.read_p = 0     # pointer to current postion in read buffer
        self.last_recv = time.time()

        self.with_nb_exc = False

    def close(self):
        self.sock.close()

    def connect(self):
        # based on implementation in asyncore.py
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(0)

        first = time.time()
        while True:
            err = self.sock.connect_ex((self.host, self.port))
            if err in (EINPROGRESS, EALREADY, EWOULDBLOCK):
                time.sleep(self.nb_sleep)
            elif err in (0, EISCONN):
                return self
            else:
                raise socket.error, (err, errorcode[err])
            if time.time() - first > self.connect_timeout:
                raise socket.error, (ETIMEDOUT, errorcode[ETIMEDOUT])


    def flush(self): pass

    def write(self, data):
        # detect a potential deadlock.
        # This might happen if we get a request to write from high-level
        # (i.e., not from read() via __do_write), while not all data
        # have been written yet.
        if data and self.read_p < len(self.read_buf):
            raise Exception("Deadlock: data='%s' read_buf='%s' read_p='%d'" %
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
                    time.sleep(self.nb_sleep)
                    if self.with_nb_exc:
                        raise NonBlockingException
                else:
                    raise


    def read(self, n):
        # do not proceed to next read until all data from
        # write buffer are sent to server
        if self.write_buf: self.__do_write()

        # read data from socket into buffer if buffer is not long enough
        while len(self.read_buf) < self.read_p + n:
            try:
                # try to read as much as we can
                self.read_buf += self.sock.recv(1024)
                self.last_recv = time.time()
            except socket.error, (err, _):
                if err in (EAGAIN,):
                    time.sleep(self.nb_sleep)
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


class NonBlockingConnection(client_0_8.Connection):

    def __init__(self, host, userid=None, password=None,
        login_method='AMQPLAIN', login_response=None,
        virtual_host='/', locale='en_US', client_properties={},
        ssl=False, insist=False, **kwargs):
        """ This method closely resembles Connection.__init__ but
        there are some differences to support non blocking sockets
        """

        assert 'nb_callback' in kwargs, 'nb_callback is required'
        self.nb_callback = kwargs['nb_callback']
        assert callable(self.nb_callback)

        if (userid is not None) and (password is not None):
            login_response = AMQPWriter()
            login_response.write_table({'LOGIN': userid, 'PASSWORD': password})
            login_response = login_response.getvalue()[4:]  #Skip the length
                                                            #at the beginning

        d = {}
        d.update(client_0_8.LIBRARY_PROPERTIES)
        d.update(client_properties)

        self.known_hosts = ''

        while True:
            self.channels = {}
            self.frame_queue = Queue()
            self.input = self.out = None

            if ':' in host:
                host, port = host.split(':', 1)
                port = int(port)
            else:
                port = client_0_8.AMQP_PORT

            nb_kwargs = dict([ k for k in kwargs.items()
                            if k[0].startswith('nb_') ])
            self.sock = NonBlockingSocket(host, port, **nb_kwargs).connect()

            self.out = self.sock
            self.input = AMQPReader(self.sock)

            self.out.write(client_0_8.AMQP_PROTOCOL_HEADER)
            self.out.flush()

            self.wait(allowed_methods=[
                        (10, 10), # start
                     ])

            self._x_start_ok(d, login_method, login_response, locale)

            self._wait_tune_ok = True
            while self._wait_tune_ok:
                self.wait(allowed_methods=[
                        (10, 20), # secure
                        (10, 30), # tune
                    ])

            host = self._x_open(virtual_host, insist=insist)
            if host is None:
                # we weren't redirected
                return

            # we were redirected, close the socket, loop and try again
            self.close()


#-------------------------------------------


def nbloop(channels):
    if not channels: return

    # make sure we have at most 1 channel per connection
    s2ch = { }  # socket -> channel mapping
    for ch in channels:
        if ch.connection.sock in s2ch:
            raise Exception("nbloop: at most 1 channel per connection")
        else:
            s2ch[ch.connection.sock] = ch

    try:
        for s in s2ch: s.with_nb_exc = True
        while True:
            for sock,ch in s2ch.items():
                try:
                    if ch.callbacks: ch.wait()
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

# client_0_8.DEBUG = True

