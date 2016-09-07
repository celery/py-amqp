from __future__ import absolute_import, unicode_literals

import pytest

from struct import pack

from case import Mock

from amqp import spec
from amqp.basic_message import Message
from amqp.exceptions import UnexpectedFrame
from amqp.method_framing import frame_handler, frame_writer


class test_frame_handler:

    @pytest.fixture(autouse=True)
    def setup_conn(self):
        self.conn = Mock(name='connection')
        self.conn.bytes_recv = 0
        self.callback = Mock(name='callback')
        self.g = frame_handler(self.conn, self.callback)

    def test_header(self):
        buf = pack(b'>HH', 60, 51)
        self.g((1, 1, buf))
        self.callback.assert_called_with(1, (60, 51), buf, None)
        assert self.conn.bytes_recv

    def test_header_message_empty_body(self):
        self.g((1, 1, pack(b'>HH', *spec.Basic.Deliver)))
        self.callback.assert_not_called()

        with pytest.raises(UnexpectedFrame):
            self.g((1, 1, pack(b'>HH', *spec.Basic.Deliver)))

        m = Message()
        m.properties = {}
        buf = pack(b'>HxxQ', m.CLASS_ID, 0)
        buf += m._serialize_properties()
        self.g((2, 1, buf))

        self.callback.assert_called()
        msg = self.callback.call_args[0][3]
        self.callback.assert_called_with(
            1, msg.frame_method, msg.frame_args, msg,
        )

    def test_header_message_content(self):
        self.g((1, 1, pack(b'>HH', *spec.Basic.Deliver)))
        self.callback.assert_not_called()

        m = Message()
        m.properties = {}
        buf = pack(b'>HxxQ', m.CLASS_ID, 16)
        buf += m._serialize_properties()
        self.g((2, 1, buf))
        self.callback.assert_not_called()

        self.g((3, 1, b'thequick'))
        self.callback.assert_not_called()

        self.g((3, 1, b'brownfox'))
        self.callback.assert_called()
        msg = self.callback.call_args[0][3]
        self.callback.assert_called_with(
            1, msg.frame_method, msg.frame_args, msg,
        )
        assert msg.body == b'thequickbrownfox'

    def test_heartbeat_frame(self):
        self.g((8, 1, ''))
        assert self.conn.bytes_recv


class test_frame_writer:

    @pytest.fixture(autouse=True)
    def setup_conn(self):
        self.connection = Mock(name='connection')
        self.transport = self.connection.Transport()
        self.connection.frame_max = 512
        self.connection.bytes_sent = 0
        self.g = frame_writer(self.connection, self.transport)
        self.write = self.transport.write

    def test_write_fast_header(self):
        frame = 1, 1, spec.Queue.Declare, b'x' * 30, None
        self.g(*frame)
        self.write.assert_called()

    def test_write_fast_content(self):
        msg = Message(body=b'y' * 10, content_type='utf-8')
        frame = 2, 1, spec.Basic.Publish, b'x' * 10, msg
        self.g(*frame)
        self.write.assert_called()

    def test_write_slow_content(self):
        msg = Message(body=b'y' * 2048, content_type='utf-8')
        frame = 2, 1, spec.Basic.Publish, b'x' * 10, msg
        self.g(*frame)
        self.write.assert_called()
