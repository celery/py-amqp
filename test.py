#!/usr/bin/env python
"""
Test AMQP library.

"""
from amqp import Connection, Content

def main():
    conn = Connection('10.66.0.8')
    ch = conn.channel(1)
    ticket = ch.access_request('/data', active=True, write=True)

    ch.exchange_declare(ticket, 'myfan', 'fanout', auto_delete=True)

    msg = Content('hello from py-amqp', content_type='text/plain', headers={'foo': 7, 'bar': 'baz'})
    ch.basic_publish(msg, ticket, 'myfan')

    print ch.queue_declare(ticket)

    ch.close()
    conn.close()

if __name__ == '__main__':
    main()
