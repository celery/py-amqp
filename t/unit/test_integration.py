from __future__ import absolute_import, unicode_literals

import pytest
from struct import pack_into
from case import patch
from amqp import spec, Connection, Channel
from amqp.platform import pack
from amqp.serialization import dumps


def ret_factory(method, channel=0, args=b'', arg_format=None):
    if len(args) > 0:
        args = dumps(arg_format, args)
    else:
        args = b''
    frame_max = 131072
    offset = 0
    buf = bytearray(frame_max - 8)
    frame = (b''.join([pack('>HH', *method), args]))
    framelen = len(frame)
    pack_into('>BHI%dsB' % framelen, buf, offset,
              1, channel, framelen, frame, 0xce)
    offset += 8 + framelen
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


class test_integration:

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
