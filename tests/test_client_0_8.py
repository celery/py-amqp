#!/usr/bin/env python
import sys
import unittest
from optparse import OptionParser

connect_args = {}

from amqplib.client_0_8 import Connection, Message

class TestConnection(unittest.TestCase):
    def setUp(self):
        self.conn = Connection(**connect_args)

    def tearDown(self):
        self.conn.close()

    def test_channel(self):
        ch = self.conn.channel(1)
        self.assertEqual(ch.channel_id, 1)

        ch2 = self.conn.channel()
        self.assertNotEqual(ch2.channel_id, 1)

        ch.close()
        ch2.close()


class TestChannel(unittest.TestCase):
    def setUp(self):
        self.conn = Connection(**connect_args)
        self.ch = self.conn.channel()


    def tearDown(self):
        self.ch.close()
        self.conn.close()

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


def main():
    parser = OptionParser(usage='usage: %prog [options] message\nexample: %prog hello world')
    parser.add_option('--host', dest='host',
                        help='AMQP server to connect to (default: %default)',
                        default='localhost')
    parser.add_option('-u', '--userid', dest='userid',
                        help='userid to authenticate as (default: %default)',
                        default='guest')
    parser.add_option('-p', '--password', dest='password',
                        help='password to authenticate with (default: %default)',
                        default='guest')
    parser.add_option('--ssl', dest='ssl', action='store_true',
                        help='Enable SSL (default: not enabled)',
                        default=False)

    options, args = parser.parse_args()

    connect_args['host'] = options.host
    connect_args['userid'] = options.userid
    connect_args['password'] = options.password
    connect_args['ssl'] = options.ssl

    sys.argv = sys.argv[:1]
    unittest.main()


if __name__ == '__main__':
    main()
