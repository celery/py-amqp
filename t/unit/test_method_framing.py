import threading
from struct import pack
from unittest.mock import Mock

import pytest

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
        buf = pack('>HH', 60, 51)
        assert self.g((1, 1, buf))
        self.callback.assert_called_with(1, (60, 51), buf, None)
        assert self.conn.bytes_recv

    def test_header_message_empty_body(self):
        assert not self.g((1, 1, pack('>HH', *spec.Basic.Deliver)))
        self.callback.assert_not_called()

        with pytest.raises(UnexpectedFrame):
            self.g((1, 1, pack('>HH', *spec.Basic.Deliver)))

        m = Message()
        m.properties = {}
        buf = pack('>HxxQ', m.CLASS_ID, 0)
        buf += m._serialize_properties()
        assert self.g((2, 1, buf))

        self.callback.assert_called()
        msg = self.callback.call_args[0][3]
        self.callback.assert_called_with(
            1, msg.frame_method, msg.frame_args, msg,
        )

    def test_header_message_content(self):
        assert not self.g((1, 1, pack('>HH', *spec.Basic.Deliver)))
        self.callback.assert_not_called()

        m = Message()
        m.properties = {}
        buf = pack('>HxxQ', m.CLASS_ID, 16)
        buf += m._serialize_properties()
        assert not self.g((2, 1, buf))
        self.callback.assert_not_called()

        assert not self.g((3, 1, b'thequick'))
        self.callback.assert_not_called()

        assert self.g((3, 1, b'brownfox'))
        self.callback.assert_called()
        msg = self.callback.call_args[0][3]
        self.callback.assert_called_with(
            1, msg.frame_method, msg.frame_args, msg,
        )
        assert msg.body == b'thequickbrownfox'

    def test_heartbeat_frame(self):
        assert not self.g((8, 1, ''))
        self.callback.assert_not_called()
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
        assert 'content_encoding' not in msg.properties

    def test_write_slow_content(self):
        msg = Message(body=b'y' * 2048, content_type='utf-8')
        frame = 2, 1, spec.Basic.Publish, b'x' * 10, msg
        self.g(*frame)
        self.write.assert_called()
        assert 'content_encoding' not in msg.properties

    def test_write_zero_len_body(self):
        msg = Message(body=b'', content_type='application/octet-stream')
        frame = 2, 1, spec.Basic.Publish, b'x' * 10, msg
        self.g(*frame)
        self.write.assert_called()
        assert 'content_encoding' not in msg.properties

    def test_write_fast_unicode(self):
        msg = Message(body='\N{CHECK MARK}')
        frame = 2, 1, spec.Basic.Publish, b'x' * 10, msg
        self.g(*frame)
        self.write.assert_called()
        memory = self.write.call_args[0][0]
        assert isinstance(memory, memoryview)
        assert '\N{CHECK MARK}'.encode() in memory.tobytes()
        assert msg.properties['content_encoding'] == 'utf-8'

    def test_write_slow_unicode(self):
        msg = Message(body='y' * 2048 + '\N{CHECK MARK}')
        frame = 2, 1, spec.Basic.Publish, b'x' * 10, msg
        self.g(*frame)
        self.write.assert_called()
        memory = self.write.call_args[0][0]
        assert isinstance(memory, bytes)
        assert '\N{CHECK MARK}'.encode() in memory
        assert msg.properties['content_encoding'] == 'utf-8'

    def test_write_non_utf8(self):
        msg = Message(body='body', content_encoding='utf-16')
        frame = 2, 1, spec.Basic.Publish, b'x' * 10, msg
        self.g(*frame)
        self.write.assert_called()
        memory = self.write.call_args[0][0]
        assert isinstance(memory, memoryview)
        assert 'body'.encode('utf-16') in memory.tobytes()
        assert msg.properties['content_encoding'] == 'utf-16'

    def test_write_frame__fast__buffer_store_resize(self):
        """The buffer_store is resized when the connection's frame_max is increased."""
        small_msg = Message(body='t')
        small_frame = 2, 1, spec.Basic.Publish, b'x' * 10, small_msg
        self.g(*small_frame)
        self.write.assert_called_once()
        write_arg = self.write.call_args[0][0]
        assert isinstance(write_arg, memoryview)
        assert len(write_arg) < self.connection.frame_max
        self.connection.reset_mock()

        # write a larger message to the same frame_writer after increasing frame_max
        large_msg = Message(body='t' * (self.connection.frame_max + 10))
        large_frame = 2, 1, spec.Basic.Publish, b'x' * 10, large_msg
        original_frame_max = self.connection.frame_max
        self.connection.frame_max += 100
        self.g(*large_frame)
        self.write.assert_called_once()
        write_arg = self.write.call_args[0][0]
        assert isinstance(write_arg, memoryview)
        assert len(write_arg) > original_frame_max

    def test_write_frame__concurrent_writers_are_serialized(self):
        """A second thread must not touch the shared buffer while a write
        is in flight (#462)."""
        in_write = threading.Event()
        release_write = threading.Event()
        seen = []

        def blocking_write(view):
            # Snapshot what the socket would send *after* it has consumed
            # the view; another writer must not be able to change it.
            in_write.set()
            release_write.wait(2)
            seen.append(bytes(view))

        self.transport.write.side_effect = blocking_write
        frame_a = 2, 1, spec.Basic.Publish, b'x' * 10, Message(body=b'A' * 40)
        frame_b = 2, 1, spec.Basic.Publish, b'x' * 10, Message(body=b'B' * 40)

        writer_a = threading.Thread(target=self.g, args=frame_a)
        writer_a.start()
        assert in_write.wait(2)

        writer_b = threading.Thread(target=self.g, args=frame_b)
        writer_b.start()
        try:
            writer_b.join(0.2)
            # B must not reach the transport while A's write is in flight.
            assert writer_b.is_alive()
            assert self.transport.write.call_count == 1
        finally:
            release_write.set()
            writer_a.join(2)
            writer_b.join(2)
        assert not writer_a.is_alive() and not writer_b.is_alive()
        assert self.transport.write.call_count == 2
        assert b'A' * 40 in seen[0] and b'B' * 40 not in seen[0]
        assert b'B' * 40 in seen[1] and b'A' * 40 not in seen[1]
