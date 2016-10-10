from __future__ import absolute_import, unicode_literals

from io import BytesIO

from case import Mock, patch
import pytest
import sys

from amqp import sasl
from amqp.serialization import _write_table


class tet_SASL:
    def test_sasl_notimplemented(self):
        mech = sasl.SASL()
        with pytest.raises(NotImplementedError):
            mech.mechanism
        with pytest.raises(NotImplementedError):
            mech.start(None)

    def test_plain(self):
        username, password = 'foo', 'bar'
        mech = sasl.PLAIN(username, password)
        response = mech.start(None)
        assert isinstance(response, bytes)
        assert response.split(b'\0') == \
            [b'', username.encode('utf-8'), password.encode('utf-8')]

    def test_amqplain(self):
        username, password = 'foo', 'bar'
        mech = sasl.AMQPLAIN(username, password)
        response = mech.start(None)
        assert isinstance(response, bytes)
        login_response = BytesIO()
        _write_table({b'LOGIN': username, b'PASSWORD': password},
                     login_response.write, [])
        expected_response = login_response.getvalue()[4:]
        assert response == expected_response

    def test_gssapi_missing(self):
        gssapi = sys.modules.pop('gssapi', None)
        GSSAPI = sasl._get_gssapi_mechanism()
        with pytest.raises(NotImplementedError):
            GSSAPI()
        if gssapi is not None:
            sys.modules['gssapi'] = gssapi

    @patch('socket.gethostbyaddr')
    def test_gssapi_rdns(self, gethostbyaddr):
        orig_gssapi = sys.modules.pop('gssapi', None)
        gssapi = sys.modules['gssapi'] = Mock()
        connection = Mock()
        connection.transport.sock.getpeername.return_value = ('192.0.2.0',
                                                              5672)
        gethostbyaddr.return_value = ('broker.example.org', (), ())
        GSSAPI = sasl._get_gssapi_mechanism()

        mech = GSSAPI(rdns=True)
        mech.start(connection)

        connection.transport.sock.getpeername.assert_called()
        gethostbyaddr.assert_called_with('192.0.2.0')
        gssapi.Name.assert_called_with(b'amqp@broker.example.org',
                                       gssapi.NameType.hostbased_service)

        if orig_gssapi is None:
            del sys.modules['gssapi']
        else:
            sys.modules['gssapi'] = orig_gssapi

    def test_gssapi_no_rdns(self):
        orig_gssapi = sys.modules.pop('gssapi', None)
        gssapi = sys.modules['gssapi'] = Mock()
        connection = Mock()
        connection.transport.host = 'broker.example.org'
        GSSAPI = sasl._get_gssapi_mechanism()

        mech = GSSAPI()
        mech.start(connection)

        gssapi.Name.assert_called_with(b'amqp@broker.example.org',
                                       gssapi.NameType.hostbased_service)

        if orig_gssapi is None:
            del sys.modules['gssapi']
        else:
            sys.modules['gssapi'] = orig_gssapi

    def test_gssapi_step(self):
        orig_gssapi = sys.modules.pop('gssapi', None)
        gssapi = sys.modules['gssapi'] = Mock()
        context = Mock()
        context.step.return_value = b'secrets'
        name = Mock()
        gssapi.SecurityContext.return_value = context
        gssapi.Name = name
        connection = Mock()
        connection.transport.host = 'broker.example.org'
        GSSAPI = sasl._get_gssapi_mechanism()

        mech = GSSAPI()
        response = mech.start(connection)

        gssapi.SecurityContext.assert_called_with(name=name)
        context.step.assert_called_with(None)
        assert response == b'secrets'

        if orig_gssapi is None:
            del sys.modules['gssapi']
        else:
            sys.modules['gssapi'] = orig_gssapi
