from __future__ import absolute_import, unicode_literals

import os
import ssl

import pytest

import amqp
from case import ANY, Mock


def get_connection(
        hostname, port, vhost, use_tls=False, keyfile=None, certfile=None):
    host = '%s:%s' % (hostname, port)
    if use_tls:
        return amqp.Connection(host=host, vhost=vhost, ssl={
            'keyfile': keyfile,
            'certfile': certfile
        }
        )
    else:
        return amqp.Connection(host=host, vhost=vhost)


@pytest.fixture(params=['plain', 'tls'])
def connection(request):
    # this fixture yields plain connections to broker and TLS encrypted
    if request.param == 'plain':
        return get_connection(
            hostname=os.environ.get('RABBITMQ_HOST', 'localhost'),
            port=os.environ.get('RABBITMQ_5672_TCP', '5672'),
            vhost=getattr(
                request.config, "slaveinput", {}
            ).get("slaveid", None),
        )
    elif request.param == 'tls':
        return get_connection(
            hostname=os.environ.get('RABBITMQ_HOST', 'localhost'),
            port=os.environ.get('RABBITMQ_5671_TCP', '5671'),
            vhost=getattr(
                request.config, "slaveinput", {}
            ).get("slaveid", None),
            use_tls=True,
            keyfile='t/certs/client_key.pem',
            certfile='t/certs/client_certificate.pem'
        )


@pytest.mark.env('rabbitmq')
@pytest.mark.flaky(reruns=5, reruns_delay=2)
def test_connect(connection):
    connection.connect()
    connection.close()


@pytest.mark.env('rabbitmq')
@pytest.mark.flaky(reruns=5, reruns_delay=2)
def test_tls_connect_fails():
    # testing that wrong client key/certificate yields SSLError
    # when encrypted connection is used
    connection = get_connection(
        hostname=os.environ.get('RABBITMQ_HOST', 'localhost'),
        port=os.environ.get('RABBITMQ_5671_TCP', '5671'),
        vhost='/',
        use_tls=True,
        keyfile='t/certs/client_key_broken.pem',
        certfile='t/certs/client_certificate_broken.pem'
    )
    with pytest.raises(ssl.SSLError):
        connection.connect()


@pytest.mark.env('rabbitmq')
class test_rabbitmq_operations():

    @pytest.fixture(autouse=True)
    def setup_conn(self, connection):
        self.connection = connection
        self.connection.connect()
        self.channel = self.connection.channel()
        yield
        self.channel.close()
        self.connection.close()

    @pytest.mark.parametrize(
        "publish_method,mandatory,immediate",
        (
            ('basic_publish', False, True),
            ('basic_publish', True, True),
            ('basic_publish', False, False),
            ('basic_publish', True, False),
            ('basic_publish_confirm', False, True),
            ('basic_publish_confirm', True, True),
            ('basic_publish_confirm', False, False),
            ('basic_publish_confirm', True, False),
        )
    )
    @pytest.mark.flaky(reruns=5, reruns_delay=2)
    def test_publish_consume(self, publish_method, mandatory, immediate):
        callback = Mock()
        self.channel.queue_declare(
            queue='py-amqp-unittest', durable=False, exclusive=True
        )
        # RabbitMQ 3 removed the support for the immediate flag
        # Since we confirm the message, RabbitMQ complains
        # See
        # http://www.rabbitmq.com/blog/2012/11/19/breaking-things-with-rabbitmq-3-0/
        if immediate and publish_method == "basic_publish_confirm":
            with pytest.raises(amqp.exceptions.AMQPNotImplementedError) as exc:
                getattr(self.channel, publish_method)(
                    amqp.Message('Unittest'),
                    routing_key='py-amqp-unittest',
                    mandatory=mandatory,
                    immediate=immediate
                )

            assert exc.value.reply_code == 540
            assert exc.value.method_name == 'Basic.publish'
            assert exc.value.reply_text == 'NOT_IMPLEMENTED - immediate=true'

            return
        else:
            getattr(self.channel, publish_method)(
                amqp.Message('Unittest'),
                routing_key='py-amqp-unittest',
                mandatory=mandatory,
                immediate=immediate
            )
        # RabbitMQ 3 removed the support for the immediate flag
        # See
        # http://www.rabbitmq.com/blog/2012/11/19/breaking-things-with-rabbitmq-3-0/
        if immediate:
            with pytest.raises(amqp.exceptions.AMQPNotImplementedError) as exc:
                self.channel.basic_consume(
                    queue='py-amqp-unittest',
                    callback=callback,
                    consumer_tag='amq.ctag-PCmzXGkhCw_v0Zq7jXyvkg'
                )
            assert exc.value.reply_code == 540
            assert exc.value.method_name == 'Basic.publish'
            assert exc.value.reply_text == 'NOT_IMPLEMENTED - immediate=true'

            return
        else:
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

    @pytest.mark.flaky(reruns=5, reruns_delay=2)
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
