#!/usr/bin/env python
"""
Test AMQP library.

"""
import amqp.client_0_8 as amqp


def callback(channel, msg):
    print 'received:', msg.body, msg.properties
    channel.basic_ack(msg.delivery_tag)
    if msg.body == 'quit':
        channel.basic_cancel(consumer_tag)


def main():
    conn = amqp.Connection('10.66.0.8')
    ch = conn.channel()
    ch.access_request('/data', active=True, write=True, read=True)

    ch.exchange_declare('myfan', 'fanout', auto_delete=True)
    qname, _, _ = ch.queue_declare()
    ch.queue_bind(qname, 'myfan')
    ch.basic_consume(qname, callback=callback)

    while ch.callbacks:
        ch.wait()

    ch.close()
    conn.close()

if __name__ == '__main__':
    main()
