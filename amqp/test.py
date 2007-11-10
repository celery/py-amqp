#!/usr/bin/env python
"""
Test AMQP library.

"""
from client import Connection, Content

def main():
    conn = Connection('10.66.0.8')
    ch = conn.channel(1)
    msg = Content('hello from py-amqp')
    ticket = ch.access_request('/data', write=True)
    ch.basic_publish(msg, ticket, 'amq.fanout')
    ch.close()
    conn.close()

if __name__ == '__main__':
    main()
