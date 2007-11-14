#!/usr/bin/env python
"""
Test AMQP library.

Send a message to the corresponding test_receive.py script, any
arguments to this program are joined together and sent as a message
body.  If no arguments, just send 'Hello from Python'

2007-11-11 Barry Pederson <bp@barryp.org>

"""
import sys
import time
import amqplib.client_0_8 as amqp

def main():
    if len(sys.argv) > 1:
        msg_body = ' '.join(sys.argv[1:])
    else:
        msg_body = 'Hello from Python'

    conn = amqp.Connection('10.66.0.8', userid='guest', password='guest')
    ch = conn.channel()
    ch.access_request('/data', active=True, write=True)

    ch.exchange_declare('myfan', 'fanout', auto_delete=True)

    msg = amqp.BasicContent(msg_body, content_type='text/plain', headers={'foo': 7, 'bar': 'baz'})

    ch.basic_publish(msg, 'myfan')

    ch.close()
    conn.close()

if __name__ == '__main__':
    main()
