from unittest.mock import Mock, patch

from amqp.utils import bytes_to_str, coro, get_logger, str_to_bytes


class test_coro:

    def test_advances(self):
        @coro
        def x():
            yield 1
            yield 2
        it = x()
        assert next(it) == 2


class test_str_to_bytes:

    def test_from_unicode(self):
        assert isinstance(str_to_bytes('foo'), bytes)

    def test_from_bytes(self):
        assert isinstance(str_to_bytes(b'foo'), bytes)

    def test_supports_surrogates(self):
        bytes_with_surrogates = '\ud83d\ude4f'.encode('utf-8', 'surrogatepass')
        assert str_to_bytes('\ud83d\ude4f') == bytes_with_surrogates


class test_bytes_to_str:

    def test_from_unicode(self):
        assert isinstance(bytes_to_str('foo'), str)

    def test_from_bytes(self):
        assert bytes_to_str(b'foo')

    def test_support_surrogates(self):
        assert bytes_to_str('\ud83d\ude4f') == '\ud83d\ude4f'


class test_get_logger:

    def test_as_str(self):
        with patch('logging.getLogger') as getLogger:
            x = get_logger('foo.bar')
            getLogger.assert_called_with('foo.bar')
            assert x is getLogger()

    def test_as_logger(self):
        with patch('amqp.utils.NullHandler') as _NullHandler:
            m = Mock(name='logger')
            m.handlers = None
            x = get_logger(m)
            assert x is m
            x.addHandler.assert_called_with(_NullHandler())
