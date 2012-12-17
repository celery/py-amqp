#!/usr/bin/env python
"""
Test amqp.channel module

"""
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

import sys
import time
import unittest
from pipes import SOURCE

try:
    bytes
except NameError:
    # Python 2.5 and lower
    bytes = str

import settings


from amqp import ChannelError, AMQPError, Connection, Message, FrameSyntaxError


class TestChannel(unittest.TestCase):
    def setUp(self):
        self.conn = Connection(**settings.connect_args)
        self.ch = self.conn.channel()


    def tearDown(self):
        self.ch.close()
        self.conn.close()


    def test_defaults(self):
        """
        Test how a queue defaults to being bound to an AMQP default
        exchange, and how publishing defaults to the default exchange, and
        basic_get defaults to getting from the most recently declared queue,
        and queue_delete defaults to deleting the most recently declared
        queue.

        """
        msg = Message('unittest message',
            content_type='text/plain',
            application_headers={'foo': 7, 'bar': 'baz'})

        qname, _, _ = self.ch.queue_declare()
        self.ch.basic_publish(msg, routing_key=qname)

        msg2 = self.ch.basic_get(no_ack=True)
        self.assertEqual(msg, msg2)

        n = self.ch.queue_purge()
        self.assertEqual(n, 0)

        n = self.ch.queue_delete()
        self.assertEqual(n, 0)

    def test_encoding(self):
        my_routing_key = 'unittest.test_queue'

        qname, _, _ = self.ch.queue_declare()
        self.ch.queue_bind(qname, 'amq.direct', routing_key=my_routing_key)

        #
        # No encoding, body passed through unchanged
        #
        msg = Message('hello world')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        if sys.version_info[0] < 3:
            self.assertFalse(hasattr(msg2, 'content_encoding'))
        self.assertTrue(isinstance(msg2.body, str))
        self.assertEqual(msg2.body, 'hello world')

        #
        # Default UTF-8 encoding of unicode body, returned as unicode
        #
        msg = Message(u'hello world')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'UTF-8')
        self.assertTrue(isinstance(msg2.body, unicode))
        self.assertEqual(msg2.body, u'hello world')

        #
        # Explicit latin_1 encoding, still comes back as unicode
        #
        msg = Message(u'hello world', content_encoding='latin_1')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'latin_1')
        self.assertTrue(isinstance(msg2.body, unicode))
        self.assertEqual(msg2.body, u'hello world')

        #
        # Plain string with specified encoding comes back as unicode
        #
        msg = Message('hello w\xf6rld', content_encoding='latin_1')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'latin_1')
        self.assertTrue(isinstance(msg2.body, unicode))
        self.assertEqual(msg2.body, u'hello w\u00f6rld')

        #
        # Plain string (bytes in Python 3.x) with bogus encoding
        #

        # don't really care about latin_1, just want bytes
        test_bytes = u'hello w\xd6rld'.encode('latin_1')
        msg = Message(test_bytes, content_encoding='I made this up')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'I made this up')
        self.assertTrue(isinstance(msg2.body, bytes))
        self.assertEqual(msg2.body, test_bytes)

        #
        # Turn off auto_decode for remaining tests
        #
        self.ch.auto_decode = False

        #
        # Unicode body comes back as utf-8 encoded str
        #
        msg = Message(u'hello w\u00f6rld')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'UTF-8')
        self.assertTrue(isinstance(msg2.body, bytes))
        self.assertEqual(msg2.body, u'hello w\xc3\xb6rld'.encode('latin_1'))

        #
        # Plain string with specified encoding stays plain string
        #
        msg = Message('hello w\xf6rld', content_encoding='latin_1')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'latin_1')
        self.assertTrue(isinstance(msg2.body, bytes))
        self.assertEqual(msg2.body, u'hello w\xf6rld'.encode('latin_1'))

        #
        # Explicit latin_1 encoding, comes back as str
        #
        msg = Message(u'hello w\u00f6rld', content_encoding='latin_1')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'latin_1')
        self.assertTrue(isinstance(msg2.body, bytes))
        self.assertEqual(msg2.body, u'hello w\xf6rld'.encode('latin_1'))


    def test_exception(self):
        """
        Check that Channel exceptions are actually raised as Python
        exceptions.

        """
        with self.assertRaises(ChannelError):
            self.ch.queue_delete('bogus_queue_that_does_not_exist')

    def test_invalid_header(self):
        """
        Test sending a message with an unserializable object in the header

        http://code.google.com/p/py-amqplib/issues/detail?id=17

        """
        qname, _, _ = self.ch.queue_declare()

        msg = Message(application_headers={'test': None})

        self.assertRaises(FrameSyntaxError, self.ch.basic_publish, msg, routing_key=qname)


    def test_large(self):
        """
        Test sending some extra large messages.

        """
        qname, _, _ = self.ch.queue_declare()

        for multiplier in [100, 1000, 10000]:
            msg = Message('unittest message' * multiplier,
                content_type='text/plain',
                application_headers={'foo': 7, 'bar': 'baz'})

            self.ch.basic_publish(msg, routing_key=qname)

            msg2 = self.ch.basic_get(no_ack=True)
            self.assertEqual(msg, msg2)


    def test_publish(self):
        self.ch.exchange_declare('unittest.fanout', 'fanout', auto_delete=True)

        msg = Message('unittest message',
            content_type='text/plain',
            application_headers={'foo': 7, 'bar': 'baz'})

        self.ch.basic_publish(msg, 'unittest.fanout')


    def test_queue(self):
        my_routing_key = 'unittest.test_queue'
        msg = Message('unittest message',
            content_type='text/plain',
            application_headers={'foo': 7, 'bar': 'baz'})

        qname, _, _ = self.ch.queue_declare()
        self.ch.queue_bind(qname, 'amq.direct', routing_key=my_routing_key)

        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)

        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg, msg2)


    def test_unbind(self):
        my_routing_key = 'unittest.test_queue'

        qname, _, _ = self.ch.queue_declare()
        self.ch.queue_bind(qname, 'amq.direct', routing_key=my_routing_key)
        self.ch.queue_unbind(qname, 'amq.direct', routing_key=my_routing_key)


    def test_basic_return(self):
        self.ch.exchange_declare('unittest.fanout', 'fanout', auto_delete=True)

        msg = Message('unittest message',
            content_type='text/plain',
            application_headers={'foo': 7, 'bar': 'baz'})

        self.ch.basic_publish(msg, 'unittest.fanout')
        self.ch.basic_publish(msg, 'unittest.fanout', immediate=True)
        self.ch.basic_publish(msg, 'unittest.fanout', mandatory=True)
        self.ch.basic_publish(msg, 'unittest.fanout', immediate=True, mandatory=True)
        self.ch.close()

        #
        # 3 of the 4 messages we sent should have been returned
        #
        self.assertEqual(self.ch.returned_messages.qsize(), 3)

    def test_exchange_bind(self):
        """Test exchange binding.
        Network configuration is as follows (-> is forwards to :
        source_exchange -> dest_exchange -> queue
        The test checks that once the message is publish to the
        destination exchange(unittest.topic_dest) it is delivered to the queue.
        """

        test_routing_key = 'unit_test__key'
        dest_exchange = 'unittest.topic_dest_bind'
        source_exchange = 'unittest.topic_source_bind'

        self.ch.exchange_declare(dest_exchange, 'topic', auto_delete=True)
        self.ch.exchange_declare(source_exchange, 'topic', auto_delete=True)

        qname, _, _ = self.ch.queue_declare()
        self.ch.exchange_bind(destination = dest_exchange,
                              source = source_exchange,
                              routing_key = test_routing_key)

        self.ch.queue_bind(qname, dest_exchange,
                           routing_key=test_routing_key)

        msg = Message('unittest message',
                      content_type='text/plain',
                      application_headers={'foo': 7, 'bar': 'baz'})


        self.ch.basic_publish(msg, source_exchange,
                              routing_key = test_routing_key)

        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg, msg2)

    def test_exchange_unbind(self):
        dest_exchange = 'unittest.topic_dest_unbind'
        source_exchange = 'unittest.topic_source_unbind'
        test_routing_key = 'unit_test__key'

        self.ch.exchange_declare(dest_exchange,
                                  'topic', auto_delete=True)
        self.ch.exchange_declare(source_exchange,
                                  'topic', auto_delete=True)

        self.ch.exchange_bind(destination = dest_exchange,
                              source = source_exchange,
                              routing_key = test_routing_key)

        self.ch.exchange_unbind(destination = dest_exchange,
                                source = source_exchange,
                                routing_key = test_routing_key)


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestChannel)
    unittest.TextTestRunner(**settings.test_args).run(suite)

if __name__ == '__main__':
    main()
