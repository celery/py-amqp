import asyncio
from amqp import Connection, Channel, Message
from typing import Any


class Driver:

    messages_received: int = 0
    messages_sent: int = 0

    def __init__(self, loop: Any = None) -> None:
        self.loop = loop or asyncio.get_event_loop()

    async def start(self, n: int = 10_000) -> None:
        await self.connect()
        channel = await self.new_channel()
        await self.declare_queues(channel)
        for i in range(n):
            await self.publish(channel, str(i))
        await self.consume(channel, n)

    async def connect(self) -> Connection:
        self.connection = Connection()
        await self.connection.connect()
        return self.connection

    async def new_channel(self) -> Channel:
        return await self.connection.channel()

    async def declare_queues(self, channel: Channel) -> None:
        print('DECLARING FOO')
        name, message_count, consumers = await channel.queue_declare('foo')
        print('DONE: %r %r %r' % (name, message_count, consumers))
        await channel.exchange_declare('foo', 'direct')
        print('EXCHANGE DECLARED: foo')
        await channel.queue_bind('foo', 'foo', 'foo')
        print('QUEUE BOUND: foo foo foo')

    async def publish(self, channel: Channel, msg: str) -> None:
        message = Message(body=msg)
        if not self.messages_sent % 1000:
            print('PUBLISH: %r' % (msg,))
        await channel.basic_publish(message, exchange='foo', routing_key='foo')
        self.messages_sent += 1

    async def consume(self, channel: Channel, n: int) -> None:
        await channel.basic_consume('foo', callback=self.on_message)
        while self.messages_received < n:
            await channel.connection.drain_events()

    async def on_message(self, message: Message) -> None:
        if not self.messages_received % 1000:
            print('RECEIVED MESSAGE: %r' % (message.body,))
        self.messages_received += 1
        await message.channel.basic_ack(message.delivery_tag)


if __name__ == '__main__':
    driver = Driver()
    driver.loop.run_until_complete(asyncio.wait_for(driver.start(), timeout=10.0))
