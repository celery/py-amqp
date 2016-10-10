from __future__ import absolute_import, unicode_literals

from io import BytesIO
import socket

import warnings

from amqp.serialization import _write_table


class SASL(object):
    """
    The base class for all amqp SASL authentication mechanisms

    You should sub-class this if you're implementing your own authentication.
    """

    @property
    def mechanism(self):
        """Returns a bytes containing the SASL mechanism name"""
        raise NotImplementedError

    def start(self, connection):
        """Returns the first response to a SASL challenge as a bytes object"""
        raise NotImplementedError


class PLAIN(SASL):
    """
    PLAIN SASL authentication mechanism.

    See https://tools.ietf.org/html/rfc4616 for details
    """
    mechanism = b'PLAIN'

    def __init__(self, username, password):
        self.username, self.password = username, password

    def start(self, connection):
        login_response = BytesIO()
        login_response.write(b'\0')
        login_response.write(self.username.encode('utf-8'))
        login_response.write(b'\0')
        login_response.write(self.password.encode('utf-8'))
        return login_response.getvalue()


class AMQPLAIN(SASL):
    mechanism = b'AMQPLAIN'

    def __init__(self, username, password):
        self.username, self.password = username, password

    def start(self, connection):
        login_response = BytesIO()
        _write_table({b'LOGIN': self.username, b'PASSWORD': self.password},
                     login_response.write, [])
        # Skip the length at the beginning
        return login_response.getvalue()[4:]


def _get_gssapi_mechanism():
    try:
        import gssapi
    except ImportError:
        class GSSAPI(SASL):
            def __init__(self, service=b'amqp', rdns=False):
                raise NotImplementedError("You need to install the `gssapi` "
                                          "module for GSSAPI SASL support")
    else:
        class GSSAPI(SASL):
            """
            GSSAPI SASL authentication mechanism

            See https://tools.ietf.org/html/rfc4752 for details
            """
            mechanism = b'GSSAPI'

            def __init__(self, service=b'amqp', rdns=False):
                self.service = service
                self.rdns = rdns

            def get_hostname(self, connection):
                if self.rdns:
                    peer = connection.transport.sock.getpeername()
                    if isinstance(peer, tuple) and len(peer) == 2:
                        hostname, _, _ = socket.gethostbyaddr(peer[0])
                    else:
                        raise AssertionError
                else:
                    hostname = connection.transport.host
                if not isinstance(hostname, bytes):
                    hostname = hostname.encode('ascii')
                return hostname

            def start(self, connection):
                name = gssapi.Name(b'@'.join([self.service,
                                              self.get_hostname(connection)]),
                                   gssapi.NameType.hostbased_service)
                self.context = gssapi.SecurityContext(name=name)
                data = self.context.step(None)
                return data
    return GSSAPI

GSSAPI = _get_gssapi_mechanism()


class RAW(SASL):
    mechanism = None

    def __init__(self, mechanism, response):
        assert isinstance(mechanism, bytes)
        assert isinstance(response, bytes)
        self.mechanism, self.response = mechanism, response
        warnings.warn("Passing login_method and login_response to Connection "
                      "is deprecated. Please implement a SASL subclass "
                      "instead.", DeprecationWarning)

    def start(self, connection):
        return self.response
