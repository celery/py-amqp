from __future__ import absolute_import, unicode_literals

from case import Mock

from amqp.exceptions import AMQPError, error_for_code


class test_AMQPError:

    def test_str(self):
        assert str(AMQPError())
        x = AMQPError(method_sig=(50, 60))
        assert str(x)


class test_error_for_code:

    def test_unknown_error(self):
        default = Mock(name='default')
        x = error_for_code(2134214314, 't', 'm', default)
        default.assert_called_with('t', 'm', reply_code=2134214314)
        assert x is default()
