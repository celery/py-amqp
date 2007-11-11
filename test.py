#!/usr/bin/env python
"""
Test AMQP library.

"""
import sys
import time
import amqp.client_0_8 as amqp

def main():
    if len(sys.argv) > 1:
        msg = sys.argv[1]
    else:
        msg = 'Hello from Python'

    conn = amqp.Connection('10.66.0.8')
    ch = conn.channel()
    ch.access_request('/data', active=True, write=True, read=True)

    ch.exchange_declare('myfan', 'fanout', auto_delete=True)
    qname, _, _ = ch.queue_declare()
    ch.queue_bind(qname, 'myfan')

    msg = amqp.Content(msg, content_type='text/plain', headers={'foo': 7, 'bar': 'baz'})
    ch.basic_publish(msg, 'myfan')

    msg2 = ch.basic_get(qname, no_ack=True)
    if 'content_encoding' in msg2.properties:
        msg2.body = msg2.body.decode(msg2.properties['content_encoding'])
    print 'received', msg2.body, type(msg2.body), msg2.properties, dir(msg2)

    ch.close()
    conn.close()

if __name__ == '__main__':
    main()
