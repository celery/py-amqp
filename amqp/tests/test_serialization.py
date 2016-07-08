from __future__ import absolute_import, unicode_literals

from datetime import datetime
from decimal import Decimal
from math import ceil
from struct import pack

from amqp.basic_message import Message
from amqp.exceptions import FrameSyntaxError
from amqp.serialization import GenericContent, _read_item, dumps, loads

from .case import Case


class ANY(object):

    def __eq__(self, other):
        return other is not None

    def __ne__(self, other):
        return other is None


class test_serialization(Case):

    def test_read_item_S(self):
        self.assertEqual(_read_item(b's8thequick')[0], 'thequick')

    def test_read_item_b(self):
        self.assertEqual(_read_item(b'b' + pack(b'>B', True))[0], True)

    def test_read_item_B(self):
        self.assertEqual(_read_item(b'B' + pack(b'>b', 123))[0], 123)

    def test_read_item_U(self):
        self.assertEqual(_read_item(b'U' + pack(b'>h', -321))[0], -321)

    def test_read_item_u(self):
        self.assertEqual(_read_item(b'u' + pack(b'>H', 321))[0], 321)

    def test_read_item_i(self):
        self.assertEqual(_read_item(b'i' + pack(b'>I', 1234))[0], 1234)

    def test_read_item_L(self):
        self.assertEqual(_read_item(b'L' + pack(b'>q', -32451))[0], -32451)

    def test_read_item_l(self):
        self.assertEqual(_read_item(b'l' + pack(b'>Q', 32451))[0], 32451)

    def test_read_item_f(self):
        self.assertEqual(ceil(_read_item(b'f' + pack(b'>f', 33.3))[0]), 34.0)

    def test_read_item_V(self):
        self.assertIsNone(_read_item(b'V')[0])

    def test_roundtrip(self):
        format = b'bobBlLbsbST'
        x = dumps(format, [
            True, 32, False, 3415, 4513134, 13241923419,
            True, b'thequickbrownfox', False, 'jumpsoverthelazydog',
            datetime(2015, 3, 13, 10, 23),
        ])
        y = loads(format, x)
        self.assertListEqual([
            True, 32, False, 3415, 4513134, 13241923419,
            True, 'thequickbrownfox', False, 'jumpsoverthelazydog',
            ANY(),
        ], y[0])

    def test_int_boundaries(self):
        format = b'F'
        x = dumps(format, [
            {'a': -2147483649, 'b': 2147483648},  # celery/celery#3121
        ])
        y = loads(format, x)
        self.assertListEqual([
            {'a': -2147483649, 'b': 2147483648},  # celery/celery#3121
        ], y[0])

    def test_loads_unknown_type(self):
        with self.assertRaises(FrameSyntaxError):
            loads('x', 'asdsad')

    def test_float(self):
        self.assertEqual(
            int(loads(b'fb', dumps(b'fb', [32.31, False]))[0][0] * 100),
            3231,
        )

    def test_table(self):
        table = {'foo': 32, 'bar': 'baz', 'nil': None}
        self.assertDictEqual(
            loads(b'F', dumps(b'F', [table]))[0][0],
            table,
        )

    def test_array(self):
        array = [
            'A', 1, True, 33.3,
            Decimal('55.5'), Decimal('-3.4'),
            datetime(2015, 3, 13, 10, 23),
            {'quick': 'fox', 'amount': 1},
            [3, 'hens'],
            None,
        ]
        expected = list(array)
        expected[6] = ANY()

        self.assertListEqual(
            expected,
            loads('A', dumps('A', [array]))[0][0],
        )

    def test_array_unknown_type(self):
        with self.assertRaises(FrameSyntaxError):
            dumps('A', [[object()]])


class test_GenericContent(Case):

    def setup(self):
        self.g = GenericContent()

    def test_getattr(self):
        self.g.properties['foo'] = 30
        with self.assertRaises(AttributeError):
            self.g.__setstate__
        self.assertEqual(self.g.foo, 30)
        with self.assertRaises(AttributeError):
            self.g.bar

    def test_load_properties(self):
        m = Message()
        m.properties = {
            'content_type': 'application/json',
            'content_encoding': 'utf-8',
            'application_headers': {
                'foo': 1,
                'id': 'id#1',
            },
            'delivery_mode': 1,
            'priority': 255,
            'correlation_id': 'df31-142f-34fd-g42d',
            'reply_to': 'cosmo',
            'expiration': '2015-12-23',
            'message_id': '3312',
            'timestamp': 3912491234,
            'type': 'generic',
            'user_id': 'george',
            'app_id': 'vandelay',
            'cluster_id': 'NYC',
        }
        s = m._serialize_properties()
        m2 = Message()
        m2._load_properties(m2.CLASS_ID, s)
        self.assertDictEqual(m2.properties, m.properties)

    def test_load_properties__some_missing(self):
        m = Message()
        m.properties = {
            'content_type': 'application/json',
            'content_encoding': 'utf-8',
            'delivery_mode': 1,
            'correlation_id': 'df31-142f-34fd-g42d',
            'reply_to': 'cosmo',
            'expiration': '2015-12-23',
            'message_id': '3312',
            'type': None,
            'app_id': None,
            'cluster_id': None,
        }
        s = m._serialize_properties()
        m2 = Message()
        m2._load_properties(m2.CLASS_ID, s)

    def test_inbound_header(self):
        m = Message()
        m.properties = {
            'content_type': 'application/json',
            'content_encoding': 'utf-8',
        }
        body = 'the quick brown fox'
        buf = b'\0' * 30 + pack(b'>HxxQ', m.CLASS_ID, len(body))
        buf += m._serialize_properties()
        self.assertEqual(m.inbound_header(buf, offset=30), 42)
        self.assertEqual(m.body_size, len(body))
        self.assertEqual(m.properties['content_type'], 'application/json')
        self.assertFalse(m.ready)

    def test_inbound_header__empty_body(self):
        m = Message()
        m.properties = {}
        buf = pack(b'>HxxQ', m.CLASS_ID, 0)
        buf += m._serialize_properties()
        self.assertEqual(m.inbound_header(buf, offset=0), 12)
        self.assertTrue(m.ready)

    def test_inbound_body(self):
        m = Message()
        m.body_size = 16
        m.body_received = 8
        m._pending_chunks = [b'the', b'quick']
        m.inbound_body(b'brown')
        self.assertFalse(m.ready)
        m.inbound_body(b'fox')
        self.assertTrue(m.ready)
        self.assertEqual(m.body, b'thequickbrownfox')

    def test_inbound_body__no_chunks(self):
        m = Message()
        m.body_size = 16
        m.inbound_body('thequickbrownfox')
        self.assertTrue(m.ready)
