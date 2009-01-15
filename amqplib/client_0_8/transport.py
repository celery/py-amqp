"""
Read/Write AMQP frames over network transports.

2009-01-14 Barry Pederson <bp@barryp.org>

"""
# Copyright (C) 2009 Barry Pederson <bp@barryp.org>
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
from struct import pack, unpack

AMQP_PORT = 5672

# Yes, Advanced Message Queuing Protocol Protocol is redundant
AMQP_PROTOCOL_HEADER = 'AMQP\x01\x01\x09\x01'


class _AbstractTransport(object):
    """
    Common superclass for TCP and SSL transports

    """
    def __init__(self, host, connect_timeout):
        if ':' in host:
            host, port = host.split(':', 1)
            port = int(port)
        else:
            port = AMQP_PORT

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.sock.settimeout(connect_timeout)
        self.sock.connect((host, port))
        self.sock.settimeout(None)

        self._setup_transport()

        self.sock.sendall(AMQP_PROTOCOL_HEADER)


    def __del__(self):
        self.close()


    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None


    def read_frame(self):
        """
        Read an AMQP frame.

        """
        frame_type, channel, size = unpack('>BHI', self._read(7))
        payload = self._read(size)
        ch = self._read(1)
        if ch == '\xce':
            return frame_type, channel, payload
        else:
            raise Exception('Framing Error')


    def write_frame(self, frame_type, channel, payload):
        """
        Write out an AMQP frame.

        """
        size = len(payload)
        self._write(pack('>BHI', frame_type, channel, size))
        self._write(payload)
        self._write('\xce')


class SSLTransport(_AbstractTransport):
    def _setup_transport(self):
        self.sslobj = socket.ssl(self.sock)

        self._read = self.sslobj.read
        self._write = self.sslobj.write


class TCPTransport(_AbstractTransport):
    def _setup_transport(self):
        self._read_buffer = ''

        #
        # Make the _write() function a direct call to socket.sendall
        #
        self._write = self.sock.sendall


    def _read(self, n):
        """
        Read exactly n bytes from the socket

        """
        while len(self._read_buffer) < n:
            self._read_buffer += self.sock.recv(4096)
        result, self._read_buffer = self._read_buffer[:n], self._read_buffer[n:]
        return result
