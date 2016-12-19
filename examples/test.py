import asyncio

from amqp import Connection, Channel, Message


class Driver:

    received_messages: int = 0

    def __init__(self, loop=None) -> None:
        self.loop = loop or asyncio.get_event_loop()

    async def connect(self) -> Connection:
        self.connection = Connection()
        await self.connection.connect()
        return self.connection

    async def new_channel(self) -> Channel:
        return await self.connection.channel()

    async def start(self) -> None:
        await self.connect()
        channel = await self.new_channel()
        await self.declare_queues(channel)
        for i in range(100):
            await self.publish(channel, str(i))
        await self.consume(channel, 100)

    async def declare_queues(self, channel):
        print('DECLARING FOO')
        name, message_count, consumers = await channel.queue_declare('foo')
        print('DONE: %r %r %r' % (name, message_count, consumers))
        await channel.exchange_declare('foo', 'direct')
        print('EXCHANGE DECLARED: foo')
        await channel.queue_bind('foo', 'foo', 'foo')
        print('QUEUE BOUND: foo foo foo')

    async def publish(self, channel, msg):
        message = Message(body=msg)
        print('PUBLISH: %r' % (msg,))
        await channel.basic_publish(message, exchange='foo', routing_key='foo')

    async def consume(self, channel, n):
        await channel.basic_consume('foo', callback=self.on_message)
        while self.received_messages < n:
            await channel.connection.drain_events()

    async def on_message(self, message):
        print('RECEIVED MESSAGE: %r' % (message.body,))
        self.received_messages += 1
        await message.channel.basic_ack(message.delivery_tag)


driver = Driver()
driver.loop.run_until_complete(asyncio.wait_for(driver.start(), timeout=10.0))
