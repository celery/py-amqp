from __future__ import absolute_import, unicode_literals

import pytest
from case import patch, call, Mock
from amqp import spec, Connection, Channel, sasl
from amqp.platform import pack
from amqp.serialization import dumps


def ret_factory(method, channel=0, args=b'', arg_format=None):
    if len(args) > 0:
        args = dumps(arg_format, args)
    else:
        args = b''
    frame = (b''.join([pack('>HH', *method), args]))
    return 1, channel, frame


connection_testdata = (
    (spec.Connection.Blocked, '_on_blocked'),
    (spec.Connection.Unblocked, '_on_unblocked'),
    (spec.Connection.OpenOk, '_on_open_ok'),
    (spec.Connection.Secure, '_on_secure'),
    (spec.Connection.CloseOk, '_on_close_ok'),
    (spec.Connection.Tune, '_on_tune'),
)


channel_testdata = (
    (spec.Basic.Ack, '_on_basic_ack'),
    (spec.Basic.Nack, '_on_basic_nack'),
    (spec.Basic.CancelOk, '_on_basic_cancel_ok'),
)

CLIENT_CAPABILITIES = {
    'product': 'py-amqp',
    'product_version': '2.3.2',
    'capabilities': {
        'consumer_cancel_notify': True,
        'connection.blocked': True,
        'authentication_failure_close': True
    }
}

SERVER_CAPABILITIES = {
    'capabilities': {
        'publisher_confirms': True,
        'exchange_exchange_bindings': True,
        'basic.nack': True,
        'consumer_cancel_notify': True,
        'connection.blocked': True,
        'consumer_priorities': True,
        'authentication_failure_close': True,
        'per_consumer_qos': True,
        'direct_reply_to': True
    },
    'cluster_name': 'rabbit@t3dredis01.solar.cat.com',
    'copyright': 'Copyright (C) 2007-2018 Pivotal Software, Inc.',
    'information': 'Licensed under the MPL.  See http://www.rabbitmq.com/',
    'platform': 'Erlang/OTP 20.3.8.9',
    'product': 'RabbitMQ',
    'version': '3.7.8'
}


class test_integration:

    def test_connect(self):
        # Test checking connection handshake
        frame_writer_cls_mock = Mock()
        frame_writer_mock = frame_writer_cls_mock()
        conn = Connection(frame_writer=frame_writer_cls_mock)

        with patch.object(conn, 'Transport') as transport_mock:
            # Mocked responses from Server
            transport_mock().read_frame.side_effect = [
                ret_factory(
                    spec.Connection.Start, channel=0,
                    args=(
                        0, 9, SERVER_CAPABILITIES, 'AMQPLAIN PLAIN', 'en_US'
                    ),
                    arg_format='ooFSS'
                ),
                ret_factory(
                    spec.Connection.Tune, channel=0,
                    args=(2047, 131072, 60), arg_format='BlB'
                ),
                ret_factory(
                    spec.Connection.OpenOk, channel=0
                )
            ]
            conn.connect()
            # Expected responses from client
            frame_writer_mock.assert_has_calls(
                [
                    call(
                        1, 0, spec.Connection.StartOk, dumps(
                            'FsSs',
                            (
                                CLIENT_CAPABILITIES, b'AMQPLAIN',
                                sasl.AMQPLAIN('guest', 'guest').start(conn),
                                'en_US'
                            )
                        ), None
                    ),
                    call(
                        1, 0, spec.Connection.TuneOk,
                        dumps(
                            'BlB',
                            (conn.channel_max, conn.frame_max, conn.heartbeat)
                        ),
                        None
                    ),
                    call(
                        1, 0, spec.Connection.Open,
                        dumps('ssb', (conn.virtual_host, '', False)),
                        None
                    )
                ]
            )

    @pytest.mark.parametrize("method, callback", connection_testdata)
    def test_connection_methods(self, method, callback):
        # Test verifying that proper Connection callback is called when
        # given method arrived from Broker.
        with patch.object(Connection, callback) as callback_mock:
            conn = Connection()
            # Protect to get handshake from server during conn.connect()
            conn._handshake_complete = True
            with patch.object(conn, 'Transport') as transport_mock:
                conn.connect()
                transport_mock().read_frame.return_value = ret_factory(
                    method, channel=0, args=(1, False), arg_format='Lb'
                )
                conn.drain_events(0)
                callback_mock.assert_called_once()

    @pytest.mark.parametrize("method, callback", channel_testdata)
    def test_channel_methods(self, method, callback):
        # Test verifying that proper Channel callback is called when
        # given method arrived from Broker
        with patch.object(Channel, callback) as callback_mock, \
                patch.object(Channel, '_on_close_ok') as close_ok_mock:
            conn = Connection()
            # Protect to get handshake from server during conn.connect()
            conn._handshake_complete = True
            with patch.object(conn, 'Transport') as transport_mock:
                conn.connect()
                channel_id = 1
                # Inject Open Handshake
                transport_mock().read_frame.return_value = ret_factory(
                    spec.Channel.OpenOk,
                    channel=channel_id,
                    args=(1, False),
                    arg_format='Lb'
                )
                with patch.object(Channel, '_on_open_ok') as open_ok_mock:
                    ch = conn.channel(channel_id=channel_id)
                    open_ok_mock.assert_called_once()
                # We need to call real method to open channel.
                ch._on_open_ok()
                # Inject desired method
                transport_mock().read_frame.return_value = ret_factory(
                    method,
                    channel=channel_id,
                    args=(1, False),
                    arg_format='Lb'
                )
                conn.drain_events(0)
                callback_mock.assert_called_once()
                # Inject close method
                transport_mock().read_frame.return_value = ret_factory(
                    spec.Channel.CloseOk,
                    channel=channel_id,
                    args=(1, False),
                    arg_format='Lb'
                )

                ch.close()
                close_ok_mock.assert_called_once()
