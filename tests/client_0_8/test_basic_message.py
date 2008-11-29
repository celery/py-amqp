#!/usr/bin/env python
from datetime import datetime
from decimal import Decimal
import unittest

from amqplib.client_0_8.basic_message import Message


class TestBasicMessage(unittest.TestCase):

    def check_proplist(self, msg):
        """
        Check roundtrip processing of a single object

        """
        raw_properties = msg._serialize_properties()

        new_msg = Message()
        new_msg._load_properties(raw_properties)
        new_msg.body = msg.body

        self.assertEqual(msg, new_msg)


    def test_roundtrip(self):
        """
        Check round-trip processing of content-properties.

        """
        self.check_proplist(Message())

        self.check_proplist(Message(content_type='text/plain'))

        self.check_proplist(Message(
            content_type='text/plain',
            content_encoding='utf-8',
            application_headers={'foo': 7, 'bar': 'baz', 'd2': {'foo2': 'xxx', 'foo3': -1}},
            delivery_mode=1,
            priority=7))

        self.check_proplist(Message(
            application_headers={
                'regular': datetime(2007, 11, 12, 12, 34, 56),
                'dst': datetime(2007, 7, 12, 12, 34, 56),
                }))

        n = datetime.now()
        n = n.replace(microsecond=0) # AMQP only does timestamps to 1-second resolution
        self.check_proplist(Message(
            application_headers={'foo': n}))

        self.check_proplist(Message(
            application_headers={'foo': Decimal('10.1')}))

        self.check_proplist(Message(
            application_headers={'foo': Decimal('-1987654.193')}))

        self.check_proplist(Message(timestamp=datetime(1980, 1, 2, 3, 4, 6)))


if __name__ == '__main__':
    unittest.main()
