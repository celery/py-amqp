import asyncio
import os
import pytest
from amqp import Connection, Message
from amqp.exceptions import NotFound, PreconditionFailed
from amqp.protocol import queue_declare_ok_t

BROKER_HOST = os.environ.get('BROKER_HOST', 'localhost')
BROKER_PORT = os.environ.get('BROKER_PORT', 5672)
TESTEX1 = 'amqpt303'
TESTEX2 = 'amqp2304'
TESTQ = 'amqptworker1'


@pytest.fixture
def connection():
    return Connection('{0}:{1}'.format(BROKER_HOST, BROKER_PORT))


@pytest.mark.asyncio
async def test_channels(connection):
    async with connection:
        async with connection.channel() as channel1:
            assert channel1.channel_id == 1
            async with connection.channel() as channel2:
                assert channel2.channel_id == 2
                async with connection.channel() as channel3:
                    assert channel3.channel_id == 3
                    await channel2.close()
                    async with connection.channel() as channel4:
                        assert channel4.channel_id == 2


@pytest.mark.asyncio
async def test_declaring_queues(connection):
    async with connection:
        async with connection.channel() as c:
            await c.exchange_declare(TESTEX1, 'direct', durable=False)
            ret = await c.queue_declare(
                TESTEX1, durable=False, passive=False)
            await c.queue_bind(TESTEX1, TESTEX1, TESTEX1)

            assert isinstance(ret, queue_declare_ok_t)
            assert ret.queue == TESTEX1

            p2 = await c.queue_declare(
                TESTEX1, durable=False, passive=True)
            assert p2

            with pytest.raises(PreconditionFailed):
                await c.queue_declare(
                    TESTEX1, durable=True, passive=False)

            with pytest.raises(NotFound):
                await c.queue_declare(
                    TESTEX2, durable=False, passive=True)


class Worker:
    messages_received = 0
    messages_sent = 0

    def __init__(self, connection, confirm_publish=False):
        self.connection = connection
        self.w_connection = Connection(
            connection.host,
            confirm_publish=confirm_publish,
        )

    async def start(self, n):
        async with self.connection, self.w_connection:
            async with self.connection.channel() as r_channel:
                async with self.w_connection.channel() as w_channel:
                    await self.declare_queues(r_channel)
                    for i in range(n):
                        await self.publish(w_channel, str(i))
                    await self.consume(r_channel, n)

    async def declare_queues(self, channel):
        name, message_count, consumers = await channel.queue_declare(TESTQ)
        await channel.exchange_declare(TESTQ, 'direct')
        await channel.queue_bind(TESTQ, TESTQ, TESTQ)

    async def publish(self, channel, msg):
        message = Message(body=msg)
        await channel.basic_publish(
            message,
            exchange=TESTQ,
            routing_key=TESTQ,
        )
        self.messages_sent += 1

    async def consume(self, channel, n):
        await channel.basic_consume(TESTQ, callback=self.on_message)
        while self.messages_received < n:
            await channel.connection.drain_events()

    async def on_message(self, message):
        self.messages_received += 1
        await message.channel.basic_ack(message.delivery_tag)


@pytest.mark.parametrize('confirm_publish,n', [
    (False, 10000),
    (True, 10000),
])
@pytest.mark.asyncio
async def test_producing_consuming(confirm_publish, n, connection):
    w = Worker(connection, confirm_publish=confirm_publish)
    ret = await w.start(n)
