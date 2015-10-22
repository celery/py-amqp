#!/usr/bin/env python
"""
Test amqp.serialization, checking conversions
between byte streams and higher level objects.

"""
# Copyright (C) 2007-2008 Barry Pederson <bp@barryp.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301

from datetime import datetime
from decimal import Decimal
from random import randint
import sys
import unittest

import settings

from amqp.serialization import (
    dumps, loads, GenericContent, FrameDataError, FrameSyntaxError,
)


class TestSerialization(unittest.TestCase):

    if sys.version_info[0] >= 3:

        def assertEqualBinary(self, b, s):
            """
            Helper for Py3k Compatibility

            """
            self.assertEqual(b, s.encode('latin_1'))
    else:
        assertEqualBinary = unittest.TestCase.assertEqual

    def test_empty_writer(self):
        s = dumps('', ())
        self.assertEqual(s, bytes())

    #
    # Bits
    #
    def test_single_bit(self):
        for val, check in [(True, '\x01'), (False, '\x00')]:
            s = dumps('b', (val,))

            self.assertEqualBinary(s, check)

            r = loads('b', s)
            self.assertEqual(r[0], [val])

    def test_multiple_bits(self):
        s = dumps('bbbb', (True,True,False,True))

        self.assertEqualBinary(s, '\x0b')

        r = loads('bbbb', s)
        self.assertEqual(r[0], [True,True,False,True])

    def test_multiple_bits2(self):
        """
        Check bits mixed with non-bits
        """
        s = dumps('bbbob', (True,True,False,10,True))

        self.assertEqualBinary(s, '\x03\x0a\x01')

        r = loads('bbbob', s)
        self.assertEqual(r[0], [True,True,False,10,True])

    def test_multiple_bits3(self):
        """
        Check bit groups that span multiple bytes
        """
        def gen():
            for i in range(10):
                yield True
                yield False
        s = dumps('bb'*10, gen())

        self.assertEqualBinary(s, '\x55\x55\x05')

        r = loads('bb'*10, s)
        self.assertEqual(r[0], list(gen()))

    #
    # Octets
    #
    def test_octet(self):
        for val in range(256):
            s = dumps('o', (val,))
            self.assertEqualBinary(s, chr(val))

            r = loads('o', s)
            self.assertEqual(r[0], [val])

    def test_octet_invalid(self):
        self.assertRaises(FrameDataError, dumps, 'o', (-1,))

    def test_octet_invalid2(self):
        self.assertRaises(FrameDataError, dumps, 'o', (256,))

    #
    # Shorts
    #
    def test_short(self):
        for i in range(256):
            val = randint(0, 65535)
            s = dumps('B', (val,))

            r = loads('B', s)
            self.assertEqual(r[0], [val])

    def test_short_invalid(self):
        self.assertRaises(FrameDataError, dumps, 'B', (-1,))

    def test_short_invalid2(self):
        self.assertRaises(FrameDataError, dumps, 'B', (65536,))

    #
    # Longs
    #
    def test_long(self):
        for i in range(256):
            val = randint(0, 4294967295)
            s = dumps('l', (val,))

            r = loads('l', s)
            self.assertEqual(r[0], [val])

    def test_long_invalid(self):
        self.assertRaises(FrameDataError, dumps, 'l', (-1,))

    def test_long_invalid2(self):
        self.assertRaises(FrameDataError, dumps, 'l', (4294967296,))

    #
    # LongLongs
    #
    def test_longlong(self):
        for i in range(256):
            val = randint(0, (2 ** 64) - 1)
            s = dumps('L', (val,))

            r = loads('L', s)
            self.assertEqual(r[0], [val])

    def test_longlong_invalid(self):
        self.assertRaises(FrameDataError, dumps, 'L', (-1,))

    def test_longlong_invalid2(self):
        self.assertRaises(FrameDataError, dumps, 'L', (2 ** 64,))

    #
    # Shortstr
    #
    def test_empty_shortstr(self):
        s = dumps('s', ('',))

        self.assertEqualBinary(s, '\x00')

        r = loads('s', s)
        self.assertEqual(r[0], [''])

    def test_shortstr(self):
        s = dumps('s', ('hello'.encode('utf-8'),))
        self.assertEqualBinary(s, '\x05hello')

        r = loads('s', s)
        self.assertEqual(r[0], ['hello'])

    def test_shortstr_unicode(self):
        s = dumps('s', (u'hello',))
        self.assertEqualBinary(s, '\x05hello')

        r = loads('s', s)
        self.assertEqual(r[0], ['hello'])

    def test_long_shortstr(self):
        self.assertRaises(FrameDataError, dumps, 's', ('x' * 256,))

    def test_long_shortstr_unicode(self):
        self.assertRaises(FrameDataError, dumps, 's', (u'\u0100' * 128,))

    #
    # Longstr
    #

    def test_empty_longstr(self):
        s = dumps('S', ('',))
        self.assertEqualBinary(s, '\x00\x00\x00\x00')

        r = loads('S', s)
        self.assertEqual(r[0], [''])

    def test_longstr(self):
        val = 'a'.encode('utf-8') * 512
        s = dumps('S', (val,))
        self.assertEqualBinary(s, '\x00\x00\x02\x00' + ('a' * 512))

        r = loads('S', s)
        self.assertEqual(r[0], [val.decode('utf-8')])

    def test_longstr_unicode(self):
        val = u'a' * 512
        s = dumps('S', (val,))
        self.assertEqualBinary(s, '\x00\x00\x02\x00' + ('a' * 512))

        r = loads('S', s)
        self.assertEqual(r[0], [val])

    #
    # Table
    #
    def test_table_empty(self):
        val = {}
        s = dumps('F', (val,))

        self.assertEqualBinary(s, '\x00\x00\x00\x00')

        r = loads('F', s)
        self.assertEqual(r[0], [val])

    def test_table(self):
        val = {'foo': 7}
        s = dumps('F', (val,))
        self.assertEqualBinary(s, '\x00\x00\x00\x09\x03fooI\x00\x00\x00\x07')

        r = loads('F', s)
        self.assertEqual(r[0], [val])

    def test_table_invalid(self):
        """
        Check that an un-serializable table entry raises a ValueError

        """
        val = {'test': object()}
        self.assertRaises(FrameSyntaxError, dumps, 'F', (val,))
        ### TODO this should be FrameDataError

    def test_table_multi(self):
        val = {
            'foo': 7,
            'bar': Decimal('123345.1234'),
            'baz': 'this is some random string I typed',
            'ubaz': u'And something in unicode',
            'dday_aniv': datetime(1994, 6, 6),
            'nothing': None,
            'more': {
                'abc': -123,
                'def': 'hello world',
                'now': datetime(2007, 11, 11, 21, 14, 31),
                'qty': Decimal('-123.45'),
                'blank': {},
                'extra': {
                    'deeper': 'more strings',
                    'nums': -12345678,
                },
            }
        }

        s = dumps('F', (val,))

        r = loads('F', s)
        self.assertEqual(r[0], [val])

    #
    # Array
    #
    def test_array_from_list(self):
        val = [1, 'foo', None]
        s = dumps('A', (val,))
        self.assertEqualBinary(
            s, '\x00\x00\x00\x0EI\x00\x00\x00\x01S\x00\x00\x00\x03fooV',
        )

        r = loads('A', s)
        self.assertEqual(r[0], [val])

    def test_array_from_tuple(self):
        val = (1, 'foo', None)
        s = dumps('A', (val,))

        self.assertEqualBinary(
            s, '\x00\x00\x00\x0EI\x00\x00\x00\x01S\x00\x00\x00\x03fooV',
        )

        r = loads('A', s)
        self.assertEqual(r[0], [list(val)])

    def test_table_with_array(self):
        val = {
            'foo': 7,
            'bar': Decimal('123345.1234'),
            'baz': 'this is some random string I typed',
            'blist': [1, 2, 3],
            'nlist': [1, [2, 3, 4]],
            'ndictl': {'nfoo': 8, 'nblist': [5, 6, 7]}
        }

        s = dumps('F', (val,))

        r = loads('F', s)
        self.assertEqual(r[0], [val])

    #
    # GenericContent
    #
    def test_generic_content_eq(self):
        msg_1 = GenericContent(dummy='foo')
        msg_2 = GenericContent(dummy='foo')
        msg_3 = GenericContent(dummy='bar')

        self.assertEqual(msg_1, msg_1)
        self.assertEqual(msg_1, msg_2)
        self.assertNotEqual(msg_1, msg_3)
        self.assertNotEqual(msg_1, None)


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSerialization)
    unittest.TextTestRunner(**settings.test_args).run(suite)


if __name__ == '__main__':
    main()
