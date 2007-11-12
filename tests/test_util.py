#!/usr/bin/env python
from datetime import datetime
from decimal import Decimal
import unittest

import amqp.client_0_8
import amqp.util
from amqp.util import _AMQPReader, _AMQPWriter
from amqp.util import parse_content_properties, serialize_content_properties
from amqp.client_0_8 import _BASIC_PROPERTIES

class TestAMQPSerialization(unittest.TestCase):
    def test_empty_writer(self):
        w = _AMQPWriter()
        self.assertEqual(w.getvalue(), '')

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


    def test_empty_shortstr(self):
        w = _AMQPWriter()
        w.write_shortstr('')
        s = w.getvalue()

        self.assertEqual(s, '\x00')

        r = _AMQPReader(s)
        self.assertEqual(r.read_shortstr(), '')


    def test_octet(self):
        for val in range(256):
            w = _AMQPWriter()
            w.write_octet(val)
            s = w.getvalue()
            self.assertEqual(s, chr(val))

            r = _AMQPReader(s)
            self.assertEqual(r.read_octet(), val)

class TestContentProperties(unittest.TestCase):

    def check_proplist(self, d):
        """
        Check roundtrip processing of a single dictionary.

        """
        raw = serialize_content_properties(_BASIC_PROPERTIES, d)
        d2 = parse_content_properties(_BASIC_PROPERTIES, raw)

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
        raw = serialize_content_properties(_BASIC_PROPERTIES, {})
        self.assertEqual(raw, '\x00\x00')


if __name__ == '__main__':
    unittest.main()
