from __future__ import absolute_import, with_statement

from collections import deque
from struct import pack, unpack
import asyncio

from amqp.tests.case import Case, Mock

from amqp.promise import Thenable, promise, wrap


class CanThen(object):

    def then(self, x, y):
        pass


class CannotThen(object):
    pass


class test_Thenable(Case):

    def test_isa(self):
        self.assertIsInstance(CanThen(), Thenable)
        self.assertNotIsInstance(CannotThen(), Thenable)

    def test_promise(self):
        self.assertIsInstance(promise(lambda x: x), Thenable)


class test_promise(Case):

    def test_example(self):

        _pending = deque()

        class Protocol(object):

            def __init__(self):
                self.buffer = []

            def read(self, size, callback=None):
                print("R",end="")
                callback = callback or promise()
                _pending.append((size, callback))
                return callback

            def read_header(self, callback=None):
                print("H",end="")
                return self.read(4, callback)

            def read_body(self, header, callback=None):
                print("B",end="")
                body_size, = unpack('>L', header)
                return self.read(body_size, callback)

            def prepare_body(self, value):
                print("P",end="")
                self.buffer.append(value)

        x = promise()
        x()
        x.wait()
        x.wait()
        x.wait()
        proto = Protocol()
        proto.read_header().then(
            proto.read_body).then(wrap(proto.prepare_body))
        x.wait()
        x.wait()
        x.wait()

        while _pending:
            print("p",end="")
            x.wait()
            size, callback = _pending.popleft()
            if size == 4:
                callback(pack('>L', 1231012302))
            else:
                callback('Hello world')
            x.wait()

        x.wait()
        x.wait()
        x.wait()
        x.wait()
        self.assertTrue(proto.buffer)
        self.assertEqual(proto.buffer[0], 'Hello world')

    def test_signal(self):
        callback = Mock(name='callback')
        a = promise()
        a.then(callback)
        a(42)
        a.wait()
        callback.assert_called_with(42)

    def test_chained(self):

        def add(x, y):
            return x + y

        def pow2(x):
            return x ** 2

        adder = Mock(name='adder')
        adder.side_effect = add

        power = Mock(name='multiplier')
        power.side_effect = pow2

        final = Mock(name='final')

        p = promise()
        p.then(adder).then(power).then(final)

        p(42, 42)
        p.wait()
        p.wait()
        p.wait()
        self.assertEqual(p.result(), (42, 42))
        adder.assert_called_with(42, 42)
        power.assert_called_with(84)
        final.assert_called_with(7056)

    def test_shallow_filter(self):
        a, b = promise(Mock(name='a')), promise(Mock(name='b'))
        p = promise(a, callback=b)
        p(30)
        p.wait()
        a.fun.assert_called_with(30)
        b.wait()
        b.fun.assert_called_with(a.fun.return_value)

        c, d = Mock(name='c'), Mock(name='d')
        promise(c, callback=d)(1)
        c.assert_called_with(1)
        p.wait() # just run the event loop
        d.assert_called_with(c.return_value)

    def test_deep_filter(self):
        a = promise(Mock(name='a'))
        b1, b2, b3 = (
            promise(Mock(name='a1')),
            promise(Mock(name='a2')),
            promise(Mock(name='a3')),
        )
        p = promise(a)
        p.then(b1)
        p.then(b2)
        p.then(b3)

        p(42)
        a.wait()
        a.fun.assert_called_with(42)
        b1.wait()
        b1.fun.assert_called_with(a.fun.return_value)
        b2.wait()
        b2.fun.assert_called_with(a.fun.return_value)
        b3.wait()
        b3.fun.assert_called_with(a.fun.return_value)

    def test_chained_filter(self):
        a = promise(Mock(name='a'))
        b = promise(Mock(name='b'))
        c = promise(Mock(name='c'))
        d = promise(Mock(name='d'))

        p = promise(a)
        p.then(b).then(c).then(d)

        p(42, kw=300)
        d.wait()

        a.fun.assert_called_with(42, kw=300)
        b.fun.assert_called_with(a.fun.return_value)
        c.fun.assert_called_with(b.fun.return_value)
        d.fun.assert_called_with(c.fun.return_value)

    def test_repr(self):
        self.assertTrue(repr(promise()))

    def test_cancel(self):
        on_error = promise(Mock(name='on_error'))
        p = promise(on_error=on_error)
        a, b, c = (
            promise(Mock(name='a')),
            promise(Mock(name='b')),
            promise(Mock(name='c')),
        )
        a2 = promise(Mock(name='a1'))
        p.then(a).then(b).then(c)
        p.then(a2)

        p.cancel()
        p(42)
        p.wait()
        self.assertTrue(p.cancelled())
        a.wait()
        self.assertTrue(a.cancelled())
        a2.wait()
        self.assertTrue(a2.cancelled())
        b.wait()
        self.assertTrue(b.cancelled())
        c.wait()
        self.assertTrue(c.cancelled())
        on_error.wait()
        self.assertTrue(on_error.cancelled())
        d = promise(Mock(name='d'))
        p.then(d)
        self.assertTrue(d.cancelled())

    def test_svpending_raises(self):
        p = promise()
        a_on_error = promise(Mock(name='a_on_error'))
        a = promise(Mock(name='a'), on_error=a_on_error)
        p.then(a)
        exc = KeyError()
        a.fun.side_effect = exc

        p(42)
        p.wait()
        a_on_error.fun.assert_called_with(exc)

    def test_empty_promise(self):
        p = promise()
        p(42)
        x = Mock(name='x')
        p.then(x)
        p.wait()
        x.assert_called_with(42)

    def test_with_partial_args(self):
        m = Mock(name='m')
        p = promise(m, (1, 2, 3), {'foobar': 2})
        p()
        m.assert_called_with(1, 2, 3, foobar=2)

    def test_with_partial_args_and_args(self):
        m = Mock(name='m')
        p = promise(m, (1, 2, 3), {'foobar': 2})
        p(4, 5, bazbar=3)
        m.assert_called_with(1, 2, 3, 4, 5, foobar=2, bazbar=3)

    def test_lvpending_raises(self):
        p = promise()
        a_on_error = promise(Mock(name='a_on_error'))
        a = promise(Mock(name='a'), on_error=a_on_error)
        b_on_error = promise(Mock(name='b_on_error'))
        b = promise(Mock(name='a'), on_error=b_on_error)
        p.then(a)
        p.then(b)
        exc = KeyError()
        a.fun.side_effect = exc

        a.then(Mock(name='foobar'))
        a.then(Mock(name='foozi'))

        p.on_error = a_on_error
        p(42)
        p.wait()

        a_on_error.fun.assert_called_with(exc)
        b.fun.assert_called_with(42)

    def test_cancel_sv(self):
        p = promise()
        a = promise(Mock(name='a'))
        p.then(a)
        p.cancel()
        p.wait()
        self.assertTrue(p.cancelled())
        a.wait()
        self.assertTrue(a.cancelled())

        p.throw(KeyError())

    def test_throw_from_cb(self):
        ae = promise(Mock(name='ae'))
        a = Mock(name='a')
        be = promise(Mock(name='be'))
        b = promise(Mock(name='b'), on_error=be)
        ce = promise(Mock(name='ce'))
        c = promise(Mock(name='c'), on_error=ce)

        exc = a.side_effect = KeyError()
        p1 = promise(a, on_error=ae)
        p1.then(b)
        p1(42)
        p1.wait()
        p1.on_error.fun.assert_called_with(exc)

        p2 = promise(a)
        p2.then(b).then(c)
        with self.assertRaises(KeyError):
            p2(42)
            p2.wait()
            p2.result()

        de = promise(Mock(name='de'))
        d = promise(Mock(name='d'), on_error=de)
        p2.then(d)
        p2.wait()
        de.fun.assert_called_with(exc)

