from amqp.utils import (
    coro, str_to_bytes, bytes_to_str, NullHandler, get_logger,
)

from .case import Case, Mock, patch


class test_coro(Case):

    def test_advances(self):
        @coro
        def x():
            yield 1
            yield 2
        it = x()
        self.assertEqual(next(it), 2)


class test_str_to_bytes(Case):

    def test_from_unicode(self):
        self.assertIsInstance(str_to_bytes('foo'), bytes)

    def test_from_bytes(self):
        self.assertIsInstance(str_to_bytes(b'foo'), bytes)


class test_bytes_to_str(Case):

    def test_from_unicode(self):
        self.assertIsInstance(bytes_to_str('foo'), str)

    def test_from_bytes(self):
        self.assertTrue(bytes_to_str(b'foo'))


class test_NullHandler(Case):

    def test_emit(self):
        NullHandler().emit(Mock(name='record'))


class test_get_logger(Case):

    @patch('logging.getLogger')
    def test_as_str(self, getLogger):
        x = get_logger('foo.bar')
        getLogger.assert_called_with('foo.bar')
        self.assertIs(x, getLogger())

    @patch('amqp.utils.NullHandler')
    def test_as_logger(self, _NullHandler):
        m = Mock(name='logger')
        m.handlers = None
        x = get_logger(m)
        self.assertIs(x, m)
        x.addHandler.assert_called_with(_NullHandler())
