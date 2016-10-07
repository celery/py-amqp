from __future__ import absolute_import, unicode_literals

from io import BytesIO
import abc
import socket

from amqp.serialization import _write_table


class SASL(object):
    pass


class PLAIN(SASL):
    mechanism = b'PLAIN'
    # As per https://tools.ietf.org/html/rfc4616

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

try:
    import gssapi
except ImportError:
    pass
else:
    class GSSAPI(SASL):
        mechanism = b'GSSAPI'

        def __init__(self, service=b'amqp', rdns=False):
            self.service = service
            self.rdns = rdns

        def get_hostname(self, connection):
            if self.rdns:
                peer = connection.transport.sock.getpeername()
                if isinstance(peer, tuple) and len(peer) == 2:
                    hostname, _, _ = socket.gethostbyaddr(peer[0])
                    return hostname
                else:
                    raise AssertionError
            else:
                return connection.transport.host

        def start(self, connection):
            name = gssapi.Name(b'{}@{}'.format(self.service,
                                              self.get_hostname(connection)),
                               gssapi.NameType.hostbased_service)
            self.context = gssapi.SecurityContext(name=name)
            data = self.context.step(None)
            return data

