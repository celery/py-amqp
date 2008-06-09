#!/usr/bin/env python
"""
Test AMQP library.

Repeatedly receive messages from the demo_send.py
script, until it receives a message with 'quit' as the body.

2007-11-11 Barry Pederson <bp@barryp.org>

"""
from optparse import OptionParser

import amqplib.nbclient_0_8 as amqp
import time

INTERVAL = 5.0
MAX_ALARMS = 4


def callback(msg):
    for key, val in msg.properties.items():
        print '%s: %s' % (key, str(val))
    for key, val in msg.delivery_info.items():
        print '> %s: %s' % (key, str(val))

    print ''
    print msg.body
    print '-------'
    msg.channel.basic_ack(msg.delivery_tag)

    #
    # Cancel this callback
    #
    if msg.body == 'quit':
        msg.channel.basic_cancel(msg.consumer_tag)

class NoActivityException(Exception):
    def __init__(self, ch):
        self.ch = ch

def my_nb_callback(ch):
    sock = ch.connection.sock

    # initialize next_alarm
    try: ch.next_alarm
    except:
        ch.next_alarm = sock.last_recv + INTERVAL
        ch.alarms = 0

    if ch.next_alarm < sock.last_recv + INTERVAL:
        # last_recv changed since last time we set next_alarm
        # reset alarm counter
        ch.next_alarm = sock.last_recv + INTERVAL
        ch.alarms = 0
        return

    if time.time() > ch.next_alarm:
        ch.alarms += 1
        print time.asctime(), id(ch), 'no activity alarm #', ch.alarms
        if ch.alarms > MAX_ALARMS:
            raise NoActivityException, ch
        ch.next_alarm += INTERVAL

def start_conn_and_consumer_channel(options, nb_callback):
    conn = amqp.NonBlockingConnection(options.host,
         userid=options.userid, password=options.password, ssl=options.ssl,
         nb_callback=my_nb_callback, insist=True)

    ch = conn.channel()
    ch.access_request('/data', active=True, read=True)

    ch.exchange_declare('myfan', 'fanout', auto_delete=True)
    qname, _, _ = ch.queue_declare()
    ch.queue_bind(qname, 'myfan')
    ch.consumer_tag = ch.basic_consume(qname, callback=callback)

    return (conn,ch,)


def main():
    parser = OptionParser()
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

    conn,ch = start_conn_and_consumer_channel(options, my_nb_callback)
    conn1,ch1 = start_conn_and_consumer_channel(options, my_nb_callback)

    channels = [ch, ch1]

    while channels:
        try:
            amqp.nbloop(channels)
        except NoActivityException, e:
            print 'Removing due to no activity:', ch
            e.ch.basic_cancel(e.ch.consumer_tag)
            channels.remove(e.ch)
            # reset alarms on remaining channels
            for c in channels: c.alarms = 0

    print 'No more consumers. Shutting down'

    ch1.close()
    ch.close()

    conn.close()
    conn1.close()

if __name__ == '__main__':
    main()
