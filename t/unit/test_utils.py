from case import Mock, patch
from amqp.utils import get_errno, want_bytes, want_str, get_logger


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


class test_want_bytes:

    def test_from_unicode(self):
        assert isinstance(want_bytes('foo'), bytes)

    def test_from_bytes(self):
        assert isinstance(want_bytes(b'foo'), bytes)


class test_want_str:

    def test_from_unicode(self):
        assert isinstance(want_str('foo'), str)

    def test_from_bytes(self):
        assert want_str(b'foo')


class test_get_logger:

    @patch('logging.getLogger')
    def test_as_str(self, getLogger):
        x = get_logger('foo.bar')
        getLogger.assert_called_with('foo.bar')
        assert x is getLogger()

    @patch('logging.NullHandler')
    def test_as_logger(self, _NullHandler):
        m = Mock(name='logger')
        m.handlers = None
        x = get_logger(m)
        assert x is m
        x.addHandler.assert_called_with(_NullHandler())
