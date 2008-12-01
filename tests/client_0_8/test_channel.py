#!/usr/bin/env python
"""
Test amqplib.client_0_8.channel module

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

import settings


from amqplib.client_0_8 import AMQPException, Connection, Message, TimeoutException


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
        self.ch.access_request('/data', active=True, write=True, read=True)

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
        self.ch.access_request('/data', active=True, write=True, read=True)

        my_routing_key = 'unittest.test_queue'

        qname, _, _ = self.ch.queue_declare()
        self.ch.queue_bind(qname, 'amq.direct', routing_key=my_routing_key)

        #
        # No encoding, body passed through unchanged
        #
        msg = Message('hello world')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
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
        # Explicit latin1 encoding, still comes back as unicode
        #
        msg = Message(u'hello world', content_encoding='latin1')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'latin1')
        self.assertTrue(isinstance(msg2.body, unicode))
        self.assertEqual(msg2.body, u'hello world')

        #
        # Plain string with specified encoding comes back as unicode
        #
        msg = Message('hello w\xf6rld', content_encoding='latin1')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'latin1')
        self.assertTrue(isinstance(msg2.body, unicode))
        self.assertEqual(msg2.body, u'hello w\u00f6rld')

        #
        # Plain string with bogus encoding
        #
        msg = Message('hello w\xf6rld', content_encoding='I made this up')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'I made this up')
        self.assertTrue(isinstance(msg2.body, str))
        self.assertEqual(msg2.body, 'hello w\xf6rld')

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
        self.assertTrue(isinstance(msg2.body, str))
        self.assertEqual(msg2.body, 'hello w\xc3\xb6rld')

        #
        # Plain string with specified encoding stays plain string
        #
        msg = Message('hello w\xf6rld', content_encoding='latin1')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'latin1')
        self.assertTrue(isinstance(msg2.body, str))
        self.assertEqual(msg2.body, 'hello w\xf6rld')

        #
        # Explicit latin1 encoding, comes back as str
        #
        msg = Message(u'hello w\u00f6rld', content_encoding='latin1')
        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)
        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg2.content_encoding, 'latin1')
        self.assertTrue(isinstance(msg2.body, str))
        self.assertEqual(msg2.body, 'hello w\xf6rld')


    def test_publish(self):
        tkt = self.ch.access_request('/data', active=True, write=True)
        self.assertEqual(tkt, self.ch.default_ticket)

        self.ch.exchange_declare('unittest.fanout', 'fanout', auto_delete=True)

        msg = Message('unittest message',
            content_type='text/plain',
            application_headers={'foo': 7, 'bar': 'baz'})

        self.ch.basic_publish(msg, 'unittest.fanout')


    def test_queue(self):
        self.ch.access_request('/data', active=True, write=True, read=True)

        my_routing_key = 'unittest.test_queue'
        msg = Message('unittest message',
            content_type='text/plain',
            application_headers={'foo': 7, 'bar': 'baz'})

        qname, _, _ = self.ch.queue_declare()
        self.ch.queue_bind(qname, 'amq.direct', routing_key=my_routing_key)

        self.ch.basic_publish(msg, 'amq.direct', routing_key=my_routing_key)

        msg2 = self.ch.basic_get(qname, no_ack=True)
        self.assertEqual(msg, msg2)


    def test_return(self):
        if not settings.connect_args['use_threading']:
            return

        self.ch.access_request('/data', active=True, write=True, read=True)

        my_routing_key = 'unittest.test_return'
        msg = Message('unittest message',
            content_type='text/plain',
            application_headers={'foo': 7, 'bar': 'baz'})

        #
        # Publish to a routing key that shouldn't
        # correspond to any queue, and make delivery
        # mandatory - which should cause a return
        #
        self.ch.basic_publish(msg, 'amq.direct',
            routing_key=my_routing_key,
            mandatory=True)

        # Wait for a basic.return
        self.ch.wait(allowed_methods=[(60, 50)], timeout=10)

        #
        # See that a returned message was put in the queue
        #
        self.assertEqual(self.ch.returned_messages.qsize(), 1)

        #
        # Check if the returned message matches what we just sent
        #
        reply_code, reply_text, exchange, routing_key2, msg2 = \
            self.ch.returned_messages.get()

        self.assertEqual(exchange, 'amq.direct')
        self.assertEqual(my_routing_key, routing_key2)
        self.assertEqual(msg, msg2)


    def noop_callback(self, msg):
        pass


    def test_wait_timeout(self):
        """
        Test the timeout option of Channel.wait().  When running
        in threaded mode, it should timeout in about 5 seconds.  In
        non-threaded mode an exception should be thrown because that
        feature is not available.

        """
        my_routing_key = 'unittest.test_wait_timeout'
        self.ch.access_request('/data', active=True, write=True, read=True)
        qname, _, _ = self.ch.queue_declare()
        self.ch.queue_bind(qname, 'amq.direct', routing_key=my_routing_key)
        self.ch.basic_consume(qname, callback=self.noop_callback, no_ack=True)

        timeout = 5 # seconds
        start = time.time()
        if settings.connect_args['use_threading']:
            self.assertRaises(TimeoutException, self.ch.wait, None, timeout)
            end = time.time()
            self.assertTrue(abs((end - start) - timeout) < 0.5)
        else:
            self.assertRaises(Exception, self.ch.wait, None, timeout)
            end = time.time()
            self.assertTrue((end - start) < 0.5)


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestChannel)
    unittest.TextTestRunner(**settings.test_args).run(suite)


if __name__ == '__main__':
    main()
