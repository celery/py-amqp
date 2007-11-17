#!/usr/bin/env python
import sys
import unittest
from optparse import OptionParser

connect_args = {}

from amqplib.client_0_8 import Connection

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

    def test_ticket(self):
        tkt = self.ch.access_request('/data', active=True, write=True)
        self.assertEqual(tkt, self.ch.default_ticket)


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
