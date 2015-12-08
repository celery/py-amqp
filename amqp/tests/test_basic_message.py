from __future__ import absolute_import, unicode_literals

from amqp.basic_message import Message

from .case import Case, Mock


class test_Message(Case):

    def test_message(self):
        m = Message(
            'foo',
            channel=Mock(name='channel'),
            application_headers={'h': 'v'},
        )
        m.delivery_info = {'delivery_tag': '1234'},
        self.assertEqual(m.body, 'foo')
        self.assertTrue(m.channel)
        self.assertDictEqual(m.headers, {'h': 'v'})
