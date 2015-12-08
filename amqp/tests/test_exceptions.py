from __future__ import absolute_import, unicode_literals

from amqp.exceptions import AMQPError, error_for_code

from .case import Case, Mock


class test_AMQPError(Case):

    def test_str(self):
        self.assertTrue(str(AMQPError()))
        x = AMQPError(method_sig=(50, 60))
        self.assertTrue(str(x))


class test_error_for_code(Case):

    def test_unknown_error(self):
        default = Mock(name='default')
        x = error_for_code(2134214314, 't', 'm', default)
        default.assert_called_with('t', 'm', reply_code=2134214314)
        self.assertIs(x, default())
