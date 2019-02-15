from __future__ import absolute_import, unicode_literals

from case import Mock, ANY
import pytest
import amqp


@pytest.mark.env('rabbitmq')
def test_connect():
    connection = amqp.Connection()
    connection.connect()
    connection.close()


@pytest.mark.env('rabbitmq')
class test_rabbitmq_operations():

    @pytest.fixture(autouse=True)
    def setup_conn(self):
        self.connection = amqp.Connection()
        self.connection.connect()
        self.channel = self.connection.channel()
        yield
        self.connection.close()

    @pytest.mark.parametrize(
        "publish_method", ('basic_publish', 'basic_publish_confirm')
    )
    def test_publish_consume(self, publish_method):
        callback = Mock()
        self.channel.queue_declare(
            queue='py-amqp-unittest', durable=False, exclusive=True
        )
        getattr(self.channel, publish_method)(
            amqp.Message('Unittest'), routing_key='py-amqp-unittest'
        )
        self.channel.basic_consume(
            queue='py-amqp-unittest',
            callback=callback,
            consumer_tag='amq.ctag-PCmzXGkhCw_v0Zq7jXyvkg'
        )
        self.connection.drain_events()
        callback.assert_called_once_with(ANY)
        msg = callback.call_args[0][0]
        assert isinstance(msg, amqp.Message)
        assert msg.body_size == len('Unittest')
        assert msg.body == 'Unittest'
        assert msg.frame_method == amqp.spec.Basic.Deliver
        assert msg.delivery_tag == 1
        assert msg.ready is True
        assert msg.delivery_info == {
            'consumer_tag': 'amq.ctag-PCmzXGkhCw_v0Zq7jXyvkg',
            'delivery_tag': 1,
            'redelivered': False,
            'exchange': '',
            'routing_key': 'py-amqp-unittest'
        }
        assert msg.properties == {'content_encoding': 'utf-8'}

        self.channel.basic_ack(msg.delivery_tag)

    def test_publish_get(self):
        self.channel.queue_declare(
            queue='py-amqp-unittest', durable=False, exclusive=True
        )
        self.channel.basic_publish(
            amqp.Message('Unittest'), routing_key='py-amqp-unittest'
        )
        msg = self.channel.basic_get(
            queue='py-amqp-unittest',
        )
        assert msg.body_size == 8
        assert msg.body == 'Unittest'
        assert msg.frame_method == amqp.spec.Basic.GetOk
        assert msg.delivery_tag == 1
        assert msg.ready is True
        assert msg.delivery_info == {
            'delivery_tag': 1, 'redelivered': False,
            'exchange': '',
            'routing_key': 'py-amqp-unittest', 'message_count': 0
        }
        assert msg.properties == {
            'content_encoding': 'utf-8'
        }

        self.channel.basic_ack(msg.delivery_tag)

        msg = self.channel.basic_get(
            queue='py-amqp-unittest',
        )
        assert msg is None
