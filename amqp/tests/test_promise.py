from __future__ import absolute_import, with_statement

from collections import deque
from struct import pack, unpack

from amqp.tests.case import Case, Mock

from amqp.promise import (
    Thenable, barrier, maybe_promise, ppartial, preplace,
    promise, ready_promise, starpromise, transform, wrap,
)


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


class test_barrier(Case):

    def setup(self):
        self.m1, self.m2, self.m3 = Mock(), Mock(), Mock()
        self.ps = [promise(self.m1), promise(self.m2), promise(self.m3)]

    def test_evaluate(self):
        x = barrier(self.ps)
        x()
        self.assertFalse(x.ready)
        x()
        self.assertFalse(x.ready)
        x.add(promise())
        x()
        self.assertFalse(x.ready)
        x()
        self.assertTrue(x.ready)
        x()
        x()

        with self.assertRaises(ValueError):
            x.add(promise())

    def test_reverse(self):
        callback = Mock()
        x = barrier(self.ps, callback=promise(callback))
        for p in self.ps:
            p()
        self.assertTrue(x.ready)
        callback.assert_called_with()

    def test_cancel(self):
        x = barrier(self.ps)
        x.cancel()
        for p in self.ps:
            p()
        x.add(promise())
        x.throw(KeyError())
        self.assertFalse(x.ready)

    def test_throw(self):
        x = barrier(self.ps)
        with self.assertRaises(KeyError):
            x.throw(KeyError(10))


class test_promise(Case):

    def test_example(self):

        _pending = deque()

        class Protocol(object):

            def __init__(self):
                self.buffer = []

            def read(self, size, callback=None):
                callback = callback or promise()
                _pending.append((size, callback))
                return callback

            def read_header(self, callback=None):
                return self.read(4, callback)

            def read_body(self, header, callback=None):
                body_size, = unpack('>L', header)
                return self.read(body_size, callback)

            def prepare_body(self, value):
                self.buffer.append(value)

        proto = Protocol()
        proto.read_header().then(
            proto.read_body).then(wrap(proto.prepare_body))

        while _pending:
            size, callback = _pending.popleft()
            if size == 4:
                callback(pack('>L', 1231012302))
            else:
                callback('Hello world')

        self.assertTrue(proto.buffer)
        self.assertEqual(proto.buffer[0], 'Hello world')

    def test_signal(self):
        callback = Mock(name='callback')
        a = promise()
        a.then(callback)
        a(42)
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
        self.assertEqual(p.value, ((42, 42), {}))
        adder.assert_called_with(42, 42)
        power.assert_called_with(84)
        final.assert_called_with(7056)

    def test_shallow_filter(self):
        a, b = promise(Mock(name='a')), promise(Mock(name='b'))
        p = promise(a, callback=b)
        self.assertIsNotNone(p._svpending)
        self.assertIsNone(p._lvpending)
        p(30)
        self.assertIsNone(p._svpending)
        a.fun.assert_called_with(30)
        b.fun.assert_called_with(a.fun.return_value)

        c, d = Mock(name='c'), Mock(name='d')
        promise(c, callback=d)(1)
        c.assert_called_with(1)
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
        self.assertIsNone(p._lvpending)
        self.assertIsNotNone(p._svpending)
        p.then(b2)
        self.assertIsNotNone(p._lvpending)
        self.assertIsNone(p._svpending)
        p.then(b3)

        p(42)
        a.fun.assert_called_with(42)
        b1.fun.assert_called_with(a.fun.return_value)
        b2.fun.assert_called_with(a.fun.return_value)
        b3.fun.assert_called_with(a.fun.return_value)

    def test_chained_filter(self):
        a = promise(Mock(name='a'))
        b = promise(Mock(name='b'))
        c = promise(Mock(name='c'))
        d = promise(Mock(name='d'))

        p = promise(a)
        p.then(b).then(c).then(d)

        p(42, kw=300)

        a.fun.assert_called_with(42, kw=300)
        b.fun.assert_called_with(a.fun.return_value)
        c.fun.assert_called_with(b.fun.return_value)
        d.fun.assert_called_with(c.fun.return_value)

    def test_repr(self):
        self.assertTrue(repr(promise()))
        self.assertTrue(repr(promise(Mock())))

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
        self.assertTrue(p.cancelled)
        self.assertTrue(a.cancelled)
        self.assertTrue(a2.cancelled)
        self.assertTrue(b.cancelled)
        self.assertTrue(c.cancelled)
        self.assertTrue(on_error.cancelled)
        d = promise(Mock(name='d'))
        p.then(d)
        self.assertTrue(d.cancelled)

    def test_svpending_raises(self):
        p = promise()
        a_on_error = promise(Mock(name='a_on_error'))
        a = promise(Mock(name='a'), on_error=a_on_error)
        p.then(a)
        exc = KeyError()
        a.fun.side_effect = exc

        p(42)
        a_on_error.fun.assert_called_with(exc)

    def test_empty_promise(self):
        p = promise()
        p(42)
        x = Mock(name='x')
        p.then(x)
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
        a_on_error.fun.assert_called_with(exc)
        b.fun.assert_called_with(42)

    def test_cancel_sv(self):
        p = promise()
        a = promise(Mock(name='a'))
        p.then(a)
        p.cancel()
        self.assertTrue(p.cancelled)
        self.assertTrue(a.cancelled)

        p.throw(KeyError())
        p.throw1(KeyError())

    def test_throw_None(self):
        try:
            raise KeyError()
        except Exception:
            with self.assertRaises(KeyError):
                promise().throw()

    def test_listeners(self):
        p = promise()
        p.then(Mock())
        self.assertEqual(len(p.listeners), 1)
        p.then(Mock())
        self.assertEqual(len(p.listeners), 2)

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
        self.assertTrue(p1._svpending)
        p1(42)
        p1.on_error.fun.assert_called_with(exc)

        p2 = promise(a)
        p2.then(b).then(c)
        with self.assertRaises(KeyError):
            p2(42)

        de = promise(Mock(name='de'))
        d = promise(Mock(name='d'), on_error=de)
        p2.then(d)
        de.fun.assert_called_with(exc)


class test_wrap(Case):

    def test_wrap(self):
        cb1 = Mock()
        cb2 = Mock()
        x = wrap(promise(cb1))
        x(1, y=2)
        cb1.assert_called_with(1, y=2)
        p2 = promise(cb2)
        x(p2)
        p2()
        cb1.assert_called_with(cb2())


class test_transform(Case):

    def test_transform(self):
        callback = Mock()

        def filter_key_value(key, filter_, mapping):
            return filter_(mapping[key])

        x = transform(filter_key_value, promise(callback), 'Value', int)
        x({'Value': 303})
        callback.assert_called_with(303)

        with self.assertRaises(KeyError):
            x({})


class test_maybe_promise(Case):

    def test_when_none(self):
        self.assertIsNone(maybe_promise(None))

    def test_when_promise(self):
        p = promise()
        self.assertIs(maybe_promise(p), p)

    def test_when_other(self):
        m = Mock()
        p = maybe_promise(m)
        self.assertIsInstance(p, Thenable)


class test_starpromise(Case):

    def test_apply(self):
        m = Mock()
        p = starpromise(m, 1, 2, z=3)
        p()
        m.assert_called_with(1, 2, z=3)


class test_ready_promise(Case):

    def test_apply(self):
        m = Mock()
        p = ready_promise(m, 1, 2, 3)
        m.assert_called_with(1, 2, 3)
        self.assertTrue(p.ready)


class test_ppartial(Case):

    def test_apply(self):
        m = Mock()
        p = ppartial(m, 1)
        p()
        m.assert_called_with(1)
        p = ppartial(m, z=2)
        p()
        m.assert_called_with(z=2)


class test_preplace(Case):

    def test_preplace(self):
        m = Mock()
        p = promise(m)
        p2 = preplace(p, 1, 2, z=3)
        p2(4, 5, x=3)
        m.assert_called_with(1, 2, z=3)
