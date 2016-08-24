from __future__ import absolute_import, unicode_literals

from case import Mock, patch

from amqp.five import text_t
from amqp.utils import (
    get_errno, coro, str_to_bytes, bytes_to_str, NullHandler, get_logger,
)


class test_get_errno:

    def test_has_attr(self):
        exc = KeyError('foo')
        exc.errno = 23
        assert get_errno(exc) == 23

    def test_in_args(self):
        exc = KeyError(34, 'foo')
        exc.args = (34, 'foo')
        assert get_errno(exc) == 34

    def test_args_short(self):
        exc = KeyError(34)
        assert not get_errno(exc)

    def test_no_args(self):
        assert not get_errno(object())


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


class test_bytes_to_str:

    def test_from_unicode(self):
        assert isinstance(bytes_to_str('foo'), text_t)

    def test_from_bytes(self):
        assert bytes_to_str(b'foo')


class test_NullHandler:

    def test_emit(self):
        NullHandler().emit(Mock(name='record'))


class test_get_logger:

    @patch('logging.getLogger')
    def test_as_str(self, getLogger):
        x = get_logger('foo.bar')
        getLogger.assert_called_with('foo.bar')
        assert x is getLogger()

    @patch('amqp.utils.NullHandler')
    def test_as_logger(self, _NullHandler):
        m = Mock(name='logger')
        m.handlers = None
        x = get_logger(m)
        assert x is m
        x.addHandler.assert_called_with(_NullHandler())
