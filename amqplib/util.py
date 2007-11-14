"""
AMQP Helper Library

2007-11-05 Barry Pederson <bp@barryp.org>

"""
# Copyright (C) 2007 Barry Pederson <bp@barryp.org>
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

from calendar import timegm
from datetime import datetime
from decimal import Decimal
from struct import pack, unpack
from time import gmtime

try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO


AMQP_PORT = 5672
AMQP_PROTOCOL_HEADER = 'AMQP\x01\x01\x09\x01'


def hexdump(s):
    while s:
        x, s = s[:16], s[16:]
        for ch in x:
            print '0x%02x ' % ord(ch),
        print ''


class _AMQPReader(object):
    """
    Parse data from AMQP

    """
    def __init__(self, source):
        """
        source should be either a file-like object with a read() method, or
        a plain (non-unicode) string.

        """
        if isinstance(source, str):
            self.input = StringIO(source)
        elif hasattr(source, 'read'):
            self.input = source
        else:
            raise ValueError('_AMQPReader needs a file-like object or plain string')

        self.bitcount = self.bits = 0

    def close(self):
        self.input.close()

    def read(self, n):
        self.bitcount = self.bits = 0
        return self.input.read(n)

    def read_bit(self):
        if not self.bitcount:
            self.bits = ord(self.input.read(1))
            self.bitcount = 8
        result = (self.bits & 1) == 1
        self.bits >>= 1
        self.bitcount -= 1
        return result

    def read_octet(self):
        self.bitcount = self.bits = 0
        return unpack('B', self.input.read(1))[0]

    def read_short(self):
        self.bitcount = self.bits = 0
        return unpack('>H', self.input.read(2))[0]

    def read_long(self):
        self.bitcount = self.bits = 0
        return unpack('>I', self.input.read(4))[0]

    def read_longlong(self):
        self.bitcount = self.bits = 0
        return unpack('>Q', self.input.read(8))[0]

    def read_shortstr(self):
        self.bitcount = self.bits = 0
        len = unpack('B', self.input.read(1))[0]
        return self.input.read(len).decode('utf-8')

    def read_longstr(self):
        self.bitcount = self.bits = 0
        len = unpack('>I', self.input.read(4))[0]
        return self.input.read(len)

    def read_table(self):
        self.bitcount = self.bits = 0
        len = unpack('>I', self.input.read(4))[0]
        table_data = _AMQPReader(self.input.read(len))
        result = {}
        while table_data.input.tell() < len:
            name = table_data.read_shortstr()
            ftype = table_data.input.read(1)
            if ftype == 'S':
                val = table_data.read_longstr()
            elif ftype == 'I':
                val = unpack('>i', table_data.input.read(4))[0]
            elif ftype == 'D':
                d = table_data.read_octet()
                n = unpack('>i', table_data.input.read(4))[0]
                val = Decimal(n) / Decimal(10 ** d)
            elif ftype == 'T':
                val = gmtime(table_data.read_longlong())[:6]
                val = datetime(*val)
            elif ftype == 'F':
                val = table_data.read_table() # recurse
            result[name] = val
        return result


class _AMQPWriter(object):
    def __init__(self):
        self.out = StringIO()
        self.bits = []
        self.bitcount = 0

    def _flushbits(self):
        if self.bits:
            for b in self.bits:
                self.out.write(pack('B', b))
            self.bits = []
            self.bitcount = 0

    def getvalue(self):
        self._flushbits()
        return self.out.getvalue()

    def write(self, s):
        self._flushbits()
        self.out.write(s)

    def write_bit(self, b):
        b = 1 if b else 0
        shift = self.bitcount %8
        if shift == 0:
            self.bits.append(0)
        self.bits[-1] |= (b << shift)
        self.bitcount += 1

    def write_octet(self, n):
        if (n < 0) or (n > 255):
            raise ValueError('Octet out of range 0..255')
        self._flushbits()
        self.out.write(pack('B', n))

    def write_short(self, n):
        if (n < 0) or (n > 65535):
            raise ValueError('Octet out of range 0..65535')
        self._flushbits()
        self.out.write(pack('>H', n))

    def write_long(self, n):
        if (n < 0) or (n >= (2**32)):
            raise ValueError('Octet out of range 0..2**31-1')
        self._flushbits()
        self.out.write(pack('>I', n))

    def write_longlong(self, n):
        if (n < 0) or (n >= (2**64)):
            raise ValueError('Octet out of range 0..2**64-1')
        self._flushbits()
        self.out.write(pack('>Q', n))

    def write_shortstr(self, s):
        self._flushbits()
        if isinstance(s, unicode):
            s = s.encode('utf-8')
        if len(s) > 255:
            raise ValueError('String too long')
        self.write_octet(len(s))
        self.out.write(s)

    def write_longstr(self, s):
        self._flushbits()
        if isinstance(s, unicode):
            s = s.encode('utf-8')
        self.write_long(len(s))
        self.out.write(s)

    def write_table(self, d):
        self._flushbits()
        table_data = _AMQPWriter()
        for k, v in d.items():
            table_data.write_shortstr(k)
            if isinstance(v, basestring):
                if isinstance(v, unicode):
                    v = v.encode('utf-8')
                table_data.write('S')
                table_data.write_longstr(v)
            elif isinstance(v, (int, long)):
                table_data.write('I')
                table_data.write(pack('>i', v))
            elif isinstance(v, Decimal):
                table_data.write('D')
                sign, digits, exponent = v.as_tuple()
                v = 0
                for d in digits:
                    v = (v * 10) + d
                if sign:
                    v = -v
                table_data.write_octet(-exponent)
                table_data.write(pack('>i', v))
            elif isinstance(v, datetime):
                table_data.write('T')
                table_data.write(pack('>q', long(timegm(v.timetuple()))))
                ## FIXME: timezone ?
            elif isinstance(v, dict):
                table_data.write('F')
                table_data.write_table(v)
        table_data = table_data.getvalue()
        self.write_long(len(table_data))
        self.out.write(table_data)


class ContentProperties(object):
    """
    Helper class for parsing and serializing content properties.

    """
    def __init__(self, properties):
        """
        Create a helper object based on a list of content properties.
        The list should be of (property-name, property-type) tuples.

        """
        self.properties = properties


    def parse(self, raw_bytes):
        """
        Given the raw bytes containing the property-flags and property-list
        from a content-frame-header, parse and return as a dictionary.

        """
        r = _AMQPReader(raw_bytes)

        #
        # Read 16-bit shorts until we get one with a low bit set to zero
        #
        flags = []
        while True:
            flag_bits = r.read_short()
            flags.append(flag_bits)
            if flag_bits & 1 == 0:
                break

        result = {}
        shift = 0
        for key, proptype in self.properties:
            if shift == 0:
                if not flags:
                    break
                flag_bits, flags = flags[0], flags[1:]
                shift = 15
            if flag_bits & (1 << shift):
                result[key] = getattr(r, 'read_' + proptype)()
            shift -= 1

        return result


    def serialize(self, d):
        """
        Given a dictionary of content properties, serialize into
        the raw bytes making up a set of property flags and a property
        list, suitable for putting into a content frame header.

        """
        shift = 15
        flag_bits = 0
        flags = []
        raw_bytes = _AMQPWriter()
        for key, proptype in self.properties:
            if key in d:
                if shift == 0:
                    flags.append(flag_bits)
                    flag_bits = 0
                    shift = 15

                flag_bits |= (1 << shift)
                if proptype != 'bit':
                    getattr(raw_bytes, 'write_' + proptype)(d[key])

            shift -= 1

        flags.append(flag_bits)
        result = _AMQPWriter()
        for flag_bits in flags:
            result.write_short(flag_bits)
        result.write(raw_bytes.getvalue())

        return result.getvalue()
