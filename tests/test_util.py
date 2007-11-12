#!/usr/bin/env python
from datetime import datetime
from decimal import Decimal
from random import randint
import unittest

import amqp.client_0_8
import amqp.util
from amqp.util import _AMQPReader, _AMQPWriter
from amqp.client_0_8 import BASIC_CONTENT_PROPERTIES

class TestAMQPSerialization(unittest.TestCase):
    def test_empty_writer(self):
        w = _AMQPWriter()
        self.assertEqual(w.getvalue(), '')

    #
    # Bits
    #
    def test_single_bit(self):
        for val, check in [(True, '\x01'), (False, '\x00')]:
            w = _AMQPWriter()
            w.write_bit(val)
            s = w.getvalue()

            self.assertEqual(s, check)

            r = _AMQPReader(s)
            self.assertEqual(r.read_bit(), val)

    def test_multiple_bits(self):
        w = _AMQPWriter()
        w.write_bit(True)
        w.write_bit(True)
        w.write_bit(False)
        w.write_bit(True)
        s = w.getvalue()

        self.assertEqual(s, '\x0b')

        r = _AMQPReader(s)
        self.assertEqual(r.read_bit(), True)
        self.assertEqual(r.read_bit(), True)
        self.assertEqual(r.read_bit(), False)
        self.assertEqual(r.read_bit(), True)


    def test_multiple_bits2(self):
        """
        Check bits mixed with non-bits
        """
        w = _AMQPWriter()
        w.write_bit(True)
        w.write_bit(True)
        w.write_bit(False)
        w.write_octet(10)
        w.write_bit(True)
        s = w.getvalue()

        self.assertEqual(s, '\x03\x0a\x01')

        r = _AMQPReader(s)
        self.assertEqual(r.read_bit(), True)
        self.assertEqual(r.read_bit(), True)
        self.assertEqual(r.read_bit(), False)
        self.assertEqual(r.read_octet(), 10)
        self.assertEqual(r.read_bit(), True)

    def test_multiple_bits3(self):
        """
        Check bit groups that span multiple bytes
        """
        w = _AMQPWriter()

        # Spit out 20 bits
        for i in range(10):
            w.write_bit(True)
            w.write_bit(False)

        s = w.getvalue()

        self.assertEquals(s, '\x55\x55\x05')

        r = _AMQPReader(s)
        for i in range(10):
            self.assertEqual(r.read_bit(), True)
            self.assertEqual(r.read_bit(), False)

    #
    # Octets
    #
    def test_octet(self):
        for val in range(256):
            w = _AMQPWriter()
            w.write_octet(val)
            s = w.getvalue()
            self.assertEqual(s, chr(val))

            r = _AMQPReader(s)
            self.assertEqual(r.read_octet(), val)

    def test_octet_invalid(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_octet, -1)

    def test_octet_invalid2(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_octet, 256)

    #
    # Shorts
    #
    def test_short(self):
        for i in range(256):
            val = randint(0, 65535)
            w = _AMQPWriter()
            w.write_short(val)
            s = w.getvalue()

            r = _AMQPReader(s)
            self.assertEqual(r.read_short(), val)

    def test_short_invalid(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_short, -1)

    def test_short_invalid2(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_short, 65536)

    #
    # Longs
    #
    def test_long(self):
        for i in range(256):
            val = randint(0, (2**32) - 1)
            w = _AMQPWriter()
            w.write_long(val)
            s = w.getvalue()

            r = _AMQPReader(s)
            self.assertEqual(r.read_long(), val)

    def test_long_invalid(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_long, -1)

    def test_long_invalid2(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_long, 2**32)

    #
    # LongLongs
    #
    def test_longlong(self):
        for i in range(256):
            val = randint(0, (2**64) - 1)
            w = _AMQPWriter()
            w.write_longlong(val)
            s = w.getvalue()

            r = _AMQPReader(s)
            self.assertEqual(r.read_longlong(), val)

    def test_longlong_invalid(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_longlong, -1)

    def test_longlong_invalid2(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_longlong, 2**64)

    #
    # Shortstr
    #
    def test_empty_shortstr(self):
        w = _AMQPWriter()
        w.write_shortstr('')
        s = w.getvalue()

        self.assertEqual(s, '\x00')

        r = _AMQPReader(s)
        self.assertEqual(r.read_shortstr(), '')

    def test_shortstr(self):
        w = _AMQPWriter()
        w.write_shortstr('hello')
        s = w.getvalue()
        self.assertEqual(s, '\x05hello')

        r = _AMQPReader(s)
        self.assertEqual(r.read_shortstr(), 'hello')

    def test_shortstr_unicode(self):
        w = _AMQPWriter()
        w.write_shortstr(u'hello')
        s = w.getvalue()
        self.assertEqual(s, '\x05hello')

        r = _AMQPReader(s)
        self.assertEqual(r.read_shortstr(), u'hello')

    def test_long_shortstr(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_shortstr, 'x' * 256)

    def test_long_shortstr_unicode(self):
        w = _AMQPWriter()
        self.assertRaises(ValueError, w.write_shortstr, u'\u0100' * 128)


    #
    # Longstr
    #
    def test_empty_longstr(self):
        w = _AMQPWriter()
        w.write_longstr('')
        s = w.getvalue()

        self.assertEqual(s, '\x00\x00\x00\x00')

        r = _AMQPReader(s)
        self.assertEqual(r.read_longstr(), '')

    def test_longstr(self):
        val = 'a' * 512
        w = _AMQPWriter()
        w.write_longstr(val)
        s = w.getvalue()

        self.assertEqual(s, '\x00\x00\x02\x00' + ('a' * 512))

        r = _AMQPReader(s)
        self.assertEqual(r.read_longstr(), val)

    def test_longstr_unicode(self):
        val = u'a' * 512
        w = _AMQPWriter()
        w.write_longstr(val)
        s = w.getvalue()

        self.assertEqual(s, '\x00\x00\x02\x00' + ('a' * 512))

        r = _AMQPReader(s)
        self.assertEqual(r.read_longstr(), val)

    #
    # Table
    #
    def test_table_empty(self):
        val = {}
        w = _AMQPWriter()
        w.write_table(val)
        s = w.getvalue()

        self.assertEqual(s, '\x00\x00\x00\x00')

        r = _AMQPReader(s)
        self.assertEqual(r.read_table(), val)

    def test_table(self):
        val = {'foo': 7}
        w = _AMQPWriter()
        w.write_table(val)
        s = w.getvalue()

        self.assertEqual(s, '\x00\x00\x00\x09\x03fooI\x00\x00\x00\x07')

        r = _AMQPReader(s)
        self.assertEqual(r.read_table(), val)


    def test_table_multi(self):
        val = {
            'foo': 7,
            'bar': Decimal('123345.1234'),
            'baz': 'this is some random string I typed',
            'ubaz': u'And something in unicode',
            'dday_aniv': datetime(1994, 6, 6),
            'more': {
                        'abc': -123,
                        'def': 'hello world',
                        'now': datetime(2007, 11, 11, 21, 14, 31),
                        'qty': Decimal('-123.45'),
                        'blank': {},
                        'extra':
                            {
                            'deeper': 'more strings',
                            'nums': -12345678,
                            },
                    }
            }

        w = _AMQPWriter()
        w.write_table(val)
        s = w.getvalue()

        r = _AMQPReader(s)
        self.assertEqual(r.read_table(), val)



class TestContentProperties(unittest.TestCase):

    def check_proplist(self, d):
        """
        Check roundtrip processing of a single dictionary.

        """
        raw = BASIC_CONTENT_PROPERTIES.serialize(d)
        d2 = BASIC_CONTENT_PROPERTIES.parse(raw)

        self.assertEqual(d, d2)


    def test_roundtrip(self):
        """
        Check round-trip processing of content-properties.

        """
        self.check_proplist({})

        self.check_proplist({
            'content_type': 'text/plain',
            })

        self.check_proplist({
            'content_type': 'text/plain',
            'content_encoding': 'utf-8',
            'headers': {'foo': 7, 'bar': 'baz', 'd2': {'foo2': 'xxx', 'foo3': -1}},
            'delivery_mode': 1,
            'priority': 7,
            })

        self.check_proplist({
            'headers': {
                'regular': datetime(2007, 11, 12, 12, 34, 56),
                'dst': datetime(2007, 7, 12, 12, 34, 56),
                },
            })

        n = datetime.now()
        n = n.replace(microsecond=0) # AMQP only does timestamps to 1-second resolution
        self.check_proplist({
            'headers': {'foo': n},
            })

        self.check_proplist({
            'headers': {'foo': Decimal('10.1')},
            })

        self.check_proplist({
            'headers': {'foo': Decimal('-1987654.193')},
            })

    def test_empty_proplist(self):
        raw = BASIC_CONTENT_PROPERTIES.serialize({})
        self.assertEqual(raw, '\x00\x00')


if __name__ == '__main__':
    unittest.main()
