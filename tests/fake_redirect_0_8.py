#!/usr/bin/env python
"""
Fake AMQP Redirect - simulate an AMQP server that redirects connections to
another server.  A bit ugly, but it's just to test that the client library
actually handles a redirect, without having to have an unbalanced cluster
of real AMQP servers.

2007-12-08 Barry Pederson <bp@barryp.org>

"""
import socket
import sys
from optparse import OptionParser
from Queue import Queue

import amqplib.client_0_8 as amqp
amqp.DEBUG = True
from amqplib.util_0_8 import AMQPReader, AMQPWriter

class FakeRedirectConnection(amqp.Connection):
    def __init__(self, sock):
        self.out = sock.makefile('w')
        self.input = AMQPReader(sock.makefile('r'))
        self.frame_queue = Queue()


    def do_redirect(self, dest):
        if self.input.read(8) != amqp.AMQP_PROTOCOL_HEADER:
            print "Didn't receive AMQP 0-8 header"
            return

        # major, minor seems backwards, but that's what RabbitMQ sends
        self.start(8, 0,
            {'product': 'fake_redirect_0_8.py'},
            ['AMQPLAIN'],
            ['en_US'])

        self.wait(allowed_methods=[
                (10, 11), # start_ok
                ])

        self.tune(0, 0, 0)

        self.wait(allowed_methods=[
                (10, 31), # tune_ok
                ])

        self.wait(allowed_methods=[
                (10, 40), # open
                ])

        if self.insist:
            self.close(reply_text="Can't redirect, insist was set to True")
        else:
            self.redirect(dest, '')
            try:
                self.wait(allowed_methods=[
                        (10, 60), # close
                        ])
            except amqp.AMQPConnectionException:
                pass

        print 'Redirect finished'


    def fake_op(self, args):
        """
        We're not really much interested in what the client sends for
        start_ok, tune_ok

        """
        pass

    ##############

    def _open(self, args):
        virtual_host = args.read_shortstr()
        capabilities = args.read_shortstr()
        self.insist = args.read_bit()


    def redirect(self, host, known_hosts):
        args = AMQPWriter()
        args.write_shortstr(host)
        args.write_shortstr(known_hosts)
        self._send_method_frame(0, (10, 50), args)


    def start(self, version_major, version_minor, server_properties,
                mechanisms, locales):
        args = AMQPWriter()
        args.write_octet(version_major)
        args.write_octet(version_minor)
        args.write_table(server_properties)
        args.write_longstr(' '.join(mechanisms))
        args.write_longstr(' '.join(locales))
        self._send_method_frame(0, (10, 10), args)


    def tune(self, channel_max, frame_max, heartbeat):
        args = AMQPWriter()
        args.write_short(channel_max)
        args.write_long(frame_max)
        args.write_short(heartbeat)
        self._send_method_frame(0, (10, 30), args)

#
# Monkeypatch the amqplib.client_0_8 _METHOD_MAP dict to
# work with our FakeRedirectConnection
#
amqp._METHOD_MAP[(10, 11)] = (amqp.Connection, FakeRedirectConnection.fake_op)
amqp._METHOD_MAP[(10, 31)] = (amqp.Connection, FakeRedirectConnection.fake_op)
amqp._METHOD_MAP[(10, 40)] = (amqp.Connection, FakeRedirectConnection._open)


def main():
    parser = OptionParser(usage='usage: %prog [options]\nexample: %prog --listen=127.0.0.1:5000 --redirect=127.0.0.1:5672')
    parser.add_option('--listen', dest='listen',
                        help='ip:port to listen for an AMQP connection on',
                        default=None)
    parser.add_option('--redirect', dest='redirect',
                        help='ip:port to redirect AMQP connection to',
                        default=None)

    options, args = parser.parse_args()

    if not options.listen or not options.redirect:
        parser.print_help()
        sys.exit(1)

    listen_ip, listen_port = options.listen.split(':', 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((listen_ip, int(listen_port)))
    print 'listening for connection...'
    s.listen(1)

    while True:
        sock, addr = s.accept()
        print 'Accepted connection from', addr

        conn = FakeRedirectConnection(sock)
        conn.do_redirect(options.redirect)


if __name__ == '__main__':
    main()

