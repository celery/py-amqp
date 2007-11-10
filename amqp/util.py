"""
AMQP Helper Library

2007-11-05 Barry Pederson <bp@barryp.org>

"""
from calendar import timegm
from datetime import datetime
from struct import pack, unpack
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

    def read(self, n):
        return self.input.read(n)

    def read_octet(self):
        return unpack('B', self.input.read(1))[0]

    def read_short(self):
        return unpack('>H', self.input.read(2))[0]

    def read_long(self):
        return unpack('>I', self.input.read(4))[0]

    def read_longlong(self):
        return unpack('>Q', self.input.read(8))[0]

    def read_shortstr(self):
        len = unpack('B', self.input.read(1))[0]
        return self.input.read(len).decode('utf-8')

    def read_longstr(self):
        len = unpack('>I', self.input.read(4))[0]
        return self.input.read(len)

    def read_table(self):
        len = unpack('>I', self.input.read(4))[0]
        table_data = _AMQPReader(self.input.read(len))
        result = {}
        while table_data.input.tell() < len:
            name = table_data.read_shortstr()
            ftype = table_data.input.read(1)
            if ftype == 'S':
                val = table_data.read_longstr()
            elif ftype == 'I':
                val = unpack('i', table_data.input.read(4))[0]
            elif ftype == 'D':
                d = table_data.read_octet()
                n = table_data.read_long()
                val = decimal(n) / decimal(10 ** d)
            elif ftype == 'T':
                val = datetime.fromtimestamp(table_data.read_longlong())
                ## FIXME: timezone ?
            elif ftype == 'F':
                val = table_data.read_table() # recurse
            result[name] = val
        return result


class _AMQPWriter(object):
    def __init__(self):
        self.out = StringIO()
        self.bits = []
        self.bitcount = 0

    def flushbits(self):
        if self.bits:
            for b in self.bits:
                self.out.write(pack('B', b))
            self.bits = []
            self.bitcount = 0

    def getvalue(self):
        self.flushbits()
        return self.out.getvalue()

    def write(self, s):
        self.flushbits()
        self.out.write(s)

    def write_boolean(self, b):
        b = 1 if b else 0
        shift = self.bitcount %8
        if shift == 0:
            self.bits.append(0)
        self.bits[-1] |= (b << shift)
        self.bitcount += 1

    def write_octet(self, n):
        self.flushbits()
        self.out.write(pack('B', n))

    def write_short(self, n):
        self.flushbits()
        self.out.write(pack('>H', n))

    def write_long(self, n):
        self.flushbits()
        self.out.write(pack('>I', n))

    def write_longlong(self, n):
        self.flushbits()
        self.out.write(pack('>Q', n))

    def write_shortstr(self, s):
        self.flushbits()
        if isinstance(s, unicode):
            s = s.encode('utf-8')
        if len(s) > 255:
            raise ValueError('String too long')
        self.write_octet(len(s))
        self.out.write(s)

    def write_longstr(self, s):
        self.flushbits()
        if isinstance(s, unicode):
            s = s.encode('utf-8')
        self.write_long(len(s))
        self.out.write(s)

    def write_table(self, d):
        self.flushbits()
        table_data = _AMQPWriter()
        for k, v in d.items():
            table_data.write_shortstr(k)
            if isinstance(v, basestring):
                if isinstance(v, unicode):
                    v = v.encode('utf-8')
                table_data.write('S')
                table_data.write_longstr(v)
            elif isinstance(v, [int, long]):
                table_data.write('I')
                table_data.write(pack('>i', v))
            elif isinstance(v, decimal):
                table_data.write('D')
                table_data.write_octet(4)
                table_data.write_long(int(v * 10))
            elif isinstance(v, datetime):
                table_data.write('T')
                table_data.write_longlong(v, long(timegm(v.timetuple)))
                ## FIXME: timezone ?
            elif isinstance(v, dict):
                table_data.write('F')
                table_data.write_table(v)
        table_data = table_data.getvalue()
        self.write_long(len(table_data))
        self.out.write(table_data)
