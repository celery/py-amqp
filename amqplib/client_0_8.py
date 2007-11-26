"""
AMQP 0-8 Client Library

"""
# Copyright (C) 2007 Barry Pederson <bp@barryp.org>
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


import socket
from Queue import Queue
from struct import unpack
from util_0_8 import AMQPReader, AMQPWriter, GenericContent

__all__ =  [
            'Connection',
            'Channel',      # here mainly so it shows in in pydoc
            'Message',
            'AMQPException',
            'AMQPConnectionException',
            'AMQPChannelException',
           ]

AMQP_PORT = 5672
AMQP_PROTOCOL_HEADER = 'AMQP\x01\x01\x09\x01'
# Yes, Advanced Message Queuing Protocol Protocol is redundant

#
# Client property info that gets sent to the server on connection startup
#
LIBRARY_PROPERTIES = {
    'library': 'Python amqplib',
    'library_version': '0.1',
    }

DEBUG = False

class AMQPException(Exception):
    def __init__(self, reply_code, reply_text, method_sig):
        self.amqp_reply_code = reply_code
        self.amqp_reply_text = reply_text
        self.amqp_method_sig = method_sig
        self.args = (
            reply_code,
            reply_text,
            method_sig,
            _METHOD_NAME_MAP.get(method_sig, '')
            )


class AMQPConnectionException(AMQPException):
    pass


class AMQPChannelException(AMQPException):
    pass


class _SSLWrap(object):
    """
    Helper class just to give a do-nothing
    'flush' method to SSLObjects
    """
    def __init__(self, sock):
        self.sock = sock
        self.sslobj = socket.ssl(sock)
        self.write = self.sslobj.write
        self.read = self.sslobj.read

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def flush(self):
        pass


class Connection(object):
    """
    The connection class provides methods for a client to establish a
    network connection to a server, and for both peers to operate the
    connection thereafter.

    GRAMMAR:

        connection          = open-connection *use-connection close-connection
        open-connection     = C:protocol-header
                              S:START C:START-OK
                              *challenge
                              S:TUNE C:TUNE-OK
                              C:OPEN S:OPEN-OK | S:REDIRECT
        challenge           = S:SECURE C:SECURE-OK
        use-connection      = *channel
        close-connection    = C:CLOSE S:CLOSE-OK
                            / S:CLOSE C:CLOSE-OK

    """
    def __init__(self, host, userid=None, password=None,
        login_method='AMQPLAIN', login_response=None,
        virtual_host='/', locale='en_US', client_properties={},
        ssl=False, **kwargs):
        """
        Create a connection to the specified host, which should be
        a 'host[:port]', such as 'localhost', or '1.2.3.4:5672'

        If a userid and password are specified, a login_response is built up
        for you.  Otherwise you have to roll your own.

        """
        self.channels = {}
        self.frame_queue = Queue()
        self.input = self.out = None

        if ':' in host:
            host, port = host.split(':', 1)
            port = int(port)
        else:
            port = AMQP_PORT

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))

        if ssl:
            self.out = _SSLWrap(sock)
            self.input = AMQPReader(self.out)
        else:
            self.out = sock.makefile('w')
            self.input = AMQPReader(sock.makefile('r'))

        self.out.write(AMQP_PROTOCOL_HEADER)
        self.out.flush()

        self.wait(allowed_methods=[
                (10, 10), # start
                ])

        if (userid is not None) and (password is not None):
            login_response = AMQPWriter()
            login_response.write_table({'LOGIN': userid, 'PASSWORD': password})
            login_response = login_response.getvalue()[4:]  #Skip the length
                                                            #at the beginning

        d = {}
        d.update(LIBRARY_PROPERTIES)
        d.update(client_properties)
        self._x_start_ok(d, login_method, login_response, locale)

        self._wait_tune_ok = True
        while self._wait_tune_ok:
            self.wait(allowed_methods=[
                (10, 20), # secure
                (10, 30), # tune
                ])

        self._x_open(virtual_host)


    def __del__(self):
        if self.input is not None:
            self.close()

    def _do_close(self):
        self.input.close()
        self.out.close()
        self.input = self.out = None


    def _get_channel_queue(self, channel_id):
        if channel_id == 0:
            return self.frame_queue
        return self.channels[channel_id].frame_queue

    def _get_free_channel_id(self):
        for i in xrange(1, self.channel_max+1):
            if i not in self.channels:
                return i
        raise AMQPException('No free channel ids, current=%d, channel_max=%d'
            % (len(self.channels), self.channel_max))


    def _send_content(self, channel, class_id, weight, body_size,
                        packed_properties, body):
        pkt = AMQPWriter()

        pkt.write_octet(2)
        pkt.write_short(channel)
        pkt.write_long(len(packed_properties)+12)

        pkt.write_short(class_id)
        pkt.write_short(weight)
        pkt.write_longlong(body_size)
        pkt.write(packed_properties)

        pkt.write_octet(0xce)
        pkt = pkt.getvalue()
        self.out.write(pkt)
        self.out.flush()

        while body:
            payload, body = body[:self.frame_max - 8], body[self.frame_max -8:]
            pkt = AMQPWriter()

            pkt.write_octet(3)
            pkt.write_short(channel)
            pkt.write_long(len(payload))

            pkt.write(payload)

            pkt.write_octet(0xce)
            pkt = pkt.getvalue()
            self.out.write(pkt)
            self.out.flush()


    def _send_method_frame(self, channel, method_sig, args=''):
        if isinstance(args, AMQPWriter):
            args = args.getvalue()

        pkt = AMQPWriter()

        pkt.write_octet(1)
        pkt.write_short(channel)
        pkt.write_long(len(args)+4)  # 4 = length of class_id and method_id
                                     # in payload

        pkt.write_short(method_sig[0]) # class_id
        pkt.write_short(method_sig[1]) # method_id
        pkt.write(args)

        pkt.write_octet(0xce)
        pkt = pkt.getvalue()
#        _hexdump(pkt)
        self.out.write(pkt)
        self.out.flush()

        if DEBUG:
            print '> %s: %s' % (str(method_sig), _METHOD_NAME_MAP[method_sig])


    def _wait_frame(self):
        """
        Wait for a frame from the server

        """
        frame_type = self.input.read_octet()
        channel = self.input.read_short()
        size = self.input.read_long()
        payload = self.input.read(size)

        ch = self.input.read_octet()
        if ch != 0xce:
            raise Exception('Framing error, unexpected byte: %x' % ch)

        return frame_type, channel, payload


    def _wait_channel(self, channel_id):
        """
        Wait for a frame from the server sent to a particular
        channel.

        """
        queue = self._get_channel_queue(channel_id)
        if not queue.empty():
            return queue.get()

        while True:
            frame_type, frame_channel, payload = self._wait_frame()

            if frame_channel == channel_id:
                return frame_type, payload

            self._get_channel_queue(frame_channel).put((frame_type, payload))


    def _dispatch_method(self, channel, payload, allowed_methods):
        if len(payload) < 4:
            raise Exception('Method frame too short')

        method_sig = unpack('>HH', payload[:4])

        if DEBUG:
            print '< %s: %s' % (str(method_sig), _METHOD_NAME_MAP[method_sig])

        if allowed_methods \
        and (method_sig not in allowed_methods) \
        and (method_sig not in _CLOSE_METHODS):
            raise Exception('Received unexpected method: %s, was expecting one of: %s'
                % (method_sig, allowed_methods))

        args = AMQPReader(payload[4:])

        amqp_class, amqp_method = _METHOD_MAP.get(method_sig, (None, None))

        if amqp_class is Connection:
            return amqp_method(self, args)
        if amqp_class is Channel:
            ch = self.channels[channel]
            return amqp_method(ch, args)

        raise Exception('Unknown AMQP method (%d, %d)'
            % amqp_class, amqp_method)


    def channel(self, channel_id=None):
        """
        Fetch a Channel object identified by the numeric channel_id, or
        create that object of it doesn't already exist.

        """
        if channel_id in self.channels:
            return self.channels[channel_id]

        return Channel(self, channel_id)


    def wait(self, allowed_methods=None):
        """
        Not sure yet if this should even be a public method.

        """
        frame_type, payload = self._wait_channel(0)

        if frame_type == 1:
            return self._dispatch_method(0, payload, allowed_methods)


    #################

    def close(self, reply_code=0, reply_text='', method_sig=(0, 0)):
        """
        This method indicates that the sender wants to close the connection.
        This may be due to internal conditions (e.g. a forced shut-down) or
        due to an error handling a specific method, i.e. an exception.  When
        a close is due to an exception, the sender provides the class and
        method id of the method which caused the exception.

        """
        args = AMQPWriter()
        args.write_short(reply_code)
        args.write_shortstr(reply_text)
        args.write_short(method_sig[0]) # class_id
        args.write_short(method_sig[1]) # method_id
        self._send_method_frame(0, (10, 60), args)
        return self.wait(allowed_methods=[
                          (10, 61),    # Connection.close_ok
                        ])


    def _close(self, args):
        """
        This method indicates that the sender wants to close the connection.
        This may be due to internal conditions (e.g. a forced shut-down) or
        due to an error handling a specific method, i.e. an exception.  When
        a close is due to an exception, the sender provides the class and
        method id of the method which caused the exception.

        """
        reply_code = args.read_short()
        reply_text = args.read_shortstr()
        class_id = args.read_short()
        method_id = args.read_short()

        self._x_close_ok()

        raise AMQPConnectionException(reply_code, reply_text, (class_id, method_id))


    def _x_close_ok(self):
        """
        This method confirms a Connection.Close method and tells the
        recipient that it is safe to release resources for the connection
        and close the socket.

        """
        self._send_method_frame(0, (10, 61))
        self._do_close()


    def _close_ok(self, args):
        """
        This method confirms a Connection.Close method and tells the
        recipient that it is safe to release resources for the connection
        and close the socket.

        """
        self._do_close()


    def _x_open(self, virtual_host, capabilities='', insist=False):
        """
        This method opens a connection to a virtual host, which is a
        collection of resources, and acts to separate multiple application
        domains within a server.

        """
        args = AMQPWriter()
        args.write_shortstr(virtual_host)
        args.write_shortstr(capabilities)
        args.write_bit(insist)
        self._send_method_frame(0, (10, 40), args)
        return self.wait(allowed_methods=[
                          (10, 41),    # Connection.open_ok
                          (10, 50),    # Connection.redirect
                        ])


    def _open_ok(self, args):
        """
        This method signals to the client that the connection is ready for
        use.

        """
        self.known_hosts = args.read_shortstr()
        if DEBUG:
            print 'Open OK! known_hosts [%s]' % self.known_hosts


    def _redirect(self, args):
        """
        This method redirects the client to another server, based on the
        requested virtual host and/or capabilities.

        """
        host = args.read_shortstr()
        known_hosts = args.read_shortstr()


    def _secure(self, args):
        """
        The SASL protocol works by exchanging challenges and responses until
        both peers have received sufficient information to authenticate each
        other.  This method challenges the client to provide more information.

        """
        challenge = args.read_longstr()


    def _x_secure_ok(self, response):
        """
        This method attempts to authenticate, passing a block of SASL data
        for the security mechanism at the server side.

        """
        args = AMQPWriter()
        args.write_longstr(response)
        self._send_method_frame(0, (10, 21), args)


    def _start(self, args):
        """
        This method starts the connection negotiation process by telling
        the client the protocol version that the server proposes, along
        with a list of security mechanisms which the client can use for
        authentication.

        """
        self.version_major = args.read_octet()
        self.version_minor = args.read_octet()
        self.server_properties = args.read_table()
        self.mechanisms = args.read_longstr().split(' ')
        self.locales = args.read_longstr().split(' ')

        if DEBUG:
            print 'Start from server, version: %d.%d, properties: %s, mechanisms: %s, locales: %s' \
                % (self.version_major, self.version_minor,
                   str(self.server_properties), self.mechanisms, self.locales)


    def _x_start_ok(self, client_properties, mechanism, response, locale):
        """
        This method selects a SASL security mechanism. ASL uses SASL
        (RFC2222) to negotiate authentication and encryption.

        """
        args = AMQPWriter()
        args.write_table(client_properties)
        args.write_shortstr(mechanism)
        args.write_longstr(response)
        args.write_shortstr(locale)
        self._send_method_frame(0, (10, 11), args)


    def _tune(self, args):
        """
        This method proposes a set of connection configuration values
        to the client.  The client can accept and/or adjust these.

        """
        self.channel_max = args.read_short() or 65535
        self.frame_max = args.read_long() or 131072
        self.heartbeat = args.read_short()

        self._x_tune_ok(self.channel_max, self.frame_max, 0)


    def _x_tune_ok(self, channel_max, frame_max, heartbeat):
        """
        This method sends the client's connection tuning parameters to the
        server. Certain fields are negotiated, others provide capability
        information.

        """
        args = AMQPWriter()
        args.write_short(channel_max)
        args.write_long(frame_max)
        args.write_short(heartbeat)
        self._send_method_frame(0, (10, 31), args)
        self._wait_tune_ok = False


class Channel(object):
    """
    The channel class provides methods for a client to establish a virtual
    connection - a channel - to a server and for both peers to operate the
    virtual connection thereafter.

    GRAMMAR:

        channel             = open-channel *use-channel close-channel
        open-channel        = C:OPEN S:OPEN-OK
        use-channel         = C:FLOW S:FLOW-OK
                            / S:FLOW C:FLOW-OK
                            / S:ALERT
                            / functional-class
        close-channel       = C:CLOSE S:CLOSE-OK
                            / S:CLOSE C:CLOSE-OK

    """
    def __init__(self, connection, channel_id=None):
        """
        Create a channel bound to a connection and using the specified
        numeric channel_id, and open on the server.

        """
        self.connection = connection
        if channel_id is None:
            channel_id = connection._get_free_channel_id()
        if DEBUG:
            print 'using channel_id', channel_id
        self.channel_id = channel_id
        self.default_ticket = 0
        self.is_open = False
        self.active = True # Flow control
        connection.channels[channel_id] = self
        self.frame_queue = Queue()
        self.alerts = Queue()
        self.callbacks = {}

        self._x_open()


    def __del__(self):
        if self.connection:
            self.close(msg='destroying channel')


    def _do_close(self):
        """
        Tear down this object, after we've agreed to close with the server.

        """
        if DEBUG:
            print 'Closed channel #%d' % self.channel_id
        self.is_open = False
        del self.connection.channels[self.channel_id]
        self.channel_id = self.connection = None


    def wait(self, allowed_methods=None):
        frame_type, payload = self.connection._wait_channel(self.channel_id)

        if frame_type == 1:
            return self.connection._dispatch_method(self.channel_id, payload, allowed_methods)
        if frame_type == 2:
            class_id, weight, body_size = unpack('>HHQ', payload[:12])
            msg = Message()
            msg._load_properties(payload[12:])

            body_parts = []
            body_received = 0
            while body_received < body_size:
                frame_type, payload = self.connection._wait_channel(self.channel_id)
                if frame_type == 3:
                    body_parts.append(payload)
                    body_received += len(payload)

            msg.body = ''.join(body_parts)
            return msg


    def _send_method_frame(self, method_sig, args=''):
        self.connection._send_method_frame(self.channel_id, method_sig, args)

    #################

    def _alert(self, args):
        """
        This method allows the server to send a non-fatal warning to the
        client.  This is used for methods that are normally asynchronous
        and thus do not have confirmations, and for which the server may
        detect errors that need to be reported.  Fatal errors are handled
        as channel or connection exceptions; non-fatal errors are sent
        through this method.

        """
        reply_code = args.read_short()
        reply_text = args.read_shortstr()
        details = args.read_table()

        self.alerts.put((reply_code, reply_text, details))


    def close(self, reply_code=0, reply_text='', method_sig=(0, 0)):
        """
        This method indicates that the sender wants to close the channel.
        This may be due to internal conditions (e.g. a forced shut-down) or
        due to an error handling a specific method, i.e. an exception.  When
        a close is due to an exception, the sender provides the class and
        method id of the method which caused the exception.

        """
        args = AMQPWriter()
        args.write_short(reply_code)
        args.write_shortstr(reply_text)
        args.write_short(method_sig[0]) # class_id
        args.write_short(method_sig[1]) # method_id
        self._send_method_frame((20, 40), args)
        return self.wait(allowed_methods=[
                          (20, 41),    # Channel.close_ok
                        ])


    def _close(self, args):
        """
        This method indicates that the sender wants to close the channel.
        This may be due to internal conditions (e.g. a forced shut-down) or
        due to an error handling a specific method, i.e. an exception.  When
        a close is due to an exception, the sender provides the class and
        method id of the method which caused the exception.

        """
        reply_code = args.read_short()
        reply_text = args.read_shortstr()
        class_id = args.read_short()
        method_id = args.read_short()

#        self.close_ok()


#    def close_ok(self):
#        """
#        This method confirms a Channel.Close method and tells the recipient
#        that it is safe to release resources for the channel and close the
#        socket.
#
#        """
        self._send_method_frame((20, 41))
        self._do_close()

        raise AMQPChannelException(reply_code, reply_text, (class_id, method_id))


    def _close_ok(self, args):
        """
        This method confirms a Channel.Close method and tells the recipient
        that it is safe to release resources for the channel and close the
        socket.

        """
        self._do_close()


    def flow(self, active):
        """
        This method asks the peer to pause or restart the flow of content
        data. This is a simple flow-control mechanism that a peer can use
        to avoid oveflowing its queues or otherwise finding itself receiving
        more messages than it can process.  Note that this method is not
        intended for window control.  The peer that receives a request to
        stop sending content should finish sending the current content, if
        any, and then wait until it receives a Flow restart method.

        """
        args = AMQPWriter()
        args.write_bit(active)
        self._send_method_frame((20, 20), args)
        return self.wait(allowed_methods=[
                          (20, 21),    # Channel.flow_ok
                        ])


    def _flow(self, args):
        """
        This method asks the peer to pause or restart the flow of content
        data. This is a simple flow-control mechanism that a peer can use
        to avoid oveflowing its queues or otherwise finding itself receiving
        more messages than it can process.  Note that this method is not
        intended for window control.  The peer that receives a request to
        stop sending content should finish sending the current content, if
        any, and then wait until it receives a Flow restart method.

        """
        self.active = args.read_bit()

        self._x_flow_ok(self.active)


    def _x_flow_ok(self, active):
        """
        Confirms to the peer that a flow command was received and processed.

        """
        args = AMQPWriter()
        args.write_bit(active)
        self._send_method_frame((20, 21), args)


    def _flow_ok(self, args):
        """
        Confirms to the peer that a flow command was received and processed.

        """
        return args.read_bit()


    def _x_open(self, out_of_band=''):
        """
        This method opens a virtual connection (a channel).

        """
        if self.is_open:
            return

        args = AMQPWriter()
        args.write_shortstr(out_of_band)
        self._send_method_frame((20, 10), args)
        return self.wait(allowed_methods=[
                          (20, 11),    # Channel.open_ok
                        ])


    def _open_ok(self, args):
        """
        This method signals to the client that the channel is ready for use.

        """
        self.is_open = True
        if DEBUG:
            print 'Channel open'


    #############
    #
    #  Access
    #
    #
    # The protocol control access to server resources using access tickets.
    # A client must explicitly request access tickets before doing work.
    # An access ticket grants a client the right to use a specific set of
    # resources - called a "realm" - in specific ways.
    #
    # GRAMMAR:
    #
    #     access              = C:REQUEST S:REQUEST-OK
    #
    #

    def access_request(self, realm, exclusive=False,
        passive=False, active=False, write=False, read=False):
        """
        This method requests an access ticket for an access realm.
        The server responds by granting the access ticket.  If the
        client does not have access rights to the requested realm
        this causes a connection exception.  Access tickets are a
        per-channel resource.

        The most recently requested ticket is used as the channel's
        default ticket for any method that requires a ticket.

        """
        args = AMQPWriter()
        args.write_shortstr(realm)
        args.write_bit(exclusive)
        args.write_bit(passive)
        args.write_bit(active)
        args.write_bit(write)
        args.write_bit(read)
        self._send_method_frame((30, 10), args)
        return self.wait(allowed_methods=[
                          (30, 11),    # Channel.access_request_ok
                        ])


    def _access_request_ok(self, args):
        """
        This method provides the client with an access ticket. The access
        ticket is valid within the current channel and for the lifespan of
        the channel.

        """
        self.default_ticket = args.read_short()
        return self.default_ticket


    #############
    #
    #  Exchange
    #
    #
    # Exchanges match and distribute messages across queues.  Exchanges can
    # be configured in the server or created at runtime.
    #
    # GRAMMAR:
    #
    #     exchange            = C:DECLARE  S:DECLARE-OK
    #                         / C:DELETE   S:DELETE-OK
    #
    #

    def exchange_declare(self, exchange, type, passive=False, durable=False,
        auto_delete=False, internal=False, nowait=False,
        arguments={}, ticket=None):
        """
        This method creates an exchange if it does not already exist, and if
        the exchange exists, verifies that it is of the correct and expected
        class.

        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(exchange)
        args.write_shortstr(type)
        args.write_bit(passive)
        args.write_bit(durable)
        args.write_bit(auto_delete)
        args.write_bit(internal)
        args.write_bit(nowait)
        args.write_table(arguments)
        self._send_method_frame((40, 10), args)

        if not nowait:
            return self.wait(allowed_methods=[
                              (40, 11),    # Channel.exchange_declare_ok
                            ])


    def _exchange_declare_ok(self, args):
        """
        This method confirms a Declare method and confirms the name of the
        exchange, essential for automatically-named exchanges.

        """
        pass


    def exchange_delete(self, exchange, if_unused=False,
        nowait=False, ticket=None):
        """
        This method deletes an exchange.  When an exchange is deleted all
        queue bindings on the exchange are cancelled.

        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(exchange)
        args.write_bit(if_unused)
        args.write_bit(nowait)
        self._send_method_frame((40, 20), args)

        if not nowait:
            return self.wait(allowed_methods=[
                              (40, 21),    # Channel.exchange_delete_ok
                            ])


    def _exchange_delete_ok(self, args):
        """
        This method confirms the deletion of an exchange.

        """
        pass


    #############
    #
    #  Queue
    #
    #
    # Queues store and forward messages.  Queues can be configured in the
    # server or created at runtime.  Queues must be attached to at least one
    # exchange in order to receive messages from publishers.
    #
    # GRAMMAR:
    #
    #     queue               = C:DECLARE  S:DECLARE-OK
    #                         / C:BIND     S:BIND-OK
    #                         / C:PURGE    S:PURGE-OK
    #                         / C:DELETE   S:DELETE-OK
    #
    #

    def queue_bind(self, queue, exchange, routing_key='',
        nowait=False, arguments={}, ticket=None):
        """
        This method binds a queue to an exchange.  Until a queue is
        bound it will not receive any messages.  In a classic messaging
        model, store-and-forward queues are bound to a dest exchange
        and subscription queues are bound to a dest_wild exchange.

        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(queue)
        args.write_shortstr(exchange)
        args.write_shortstr(routing_key)
        args.write_bit(nowait)
        args.write_table(arguments)
        self._send_method_frame((50, 20), args)

        if not nowait:
            return self.wait(allowed_methods=[
                              (50, 21),    # Channel.queue_bind_ok
                            ])


    def _queue_bind_ok(self, args):
        """
        This method confirms that the bind was successful.

        """
        pass


    def queue_declare(self, queue='', passive=False, durable=False,
        exclusive=False, auto_delete=False, nowait=False,
        arguments={}, ticket=None):
        """
        This method creates or checks a queue.  When creating a new queue
        the client can specify various properties that control the
        durability of the queue and its contents, and the level of sharing
        for the queue.

        Returns a tuple containing 3 items:
            the name of the queue (essential for automatically-named queues)
            message count
            consumer count

        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(queue)
        args.write_bit(passive)
        args.write_bit(durable)
        args.write_bit(exclusive)
        args.write_bit(auto_delete)
        args.write_bit(nowait)
        args.write_table(arguments)
        self._send_method_frame((50, 10), args)

        if not nowait:
            return self.wait(allowed_methods=[
                              (50, 11),    # Channel.queue_declare_ok
                            ])


    def _queue_declare_ok(self, args):
        """
        This method confirms a Declare method and confirms the name of the
        queue, essential for automatically-named queues.

        """
        queue = args.read_shortstr()
        message_count = args.read_long()
        consumer_count = args.read_long()

        return queue, message_count, consumer_count


    def queue_delete(self, queue, if_unused=False, if_empty=False,
        nowait=False, ticket=None):
        """
        This method deletes a queue.  When a queue is deleted any pending
        messages are sent to a dead-letter queue if this is defined in the
        server configuration, and all consumers on the queue are cancelled.

        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(queue)
        args.write_bit(if_unused)
        args.write_bit(if_empty)
        args.write_bit(nowait)
        self._send_method_frame((50, 40), args)

        if not nowait:
            return self.wait(allowed_methods=[
                              (50, 41),    # Channel.queue_delete_ok
                            ])


    def _queue_delete_ok(self, args):
        """
        This method confirms the deletion of a queue.

        """
        return args.read_long()


    def queue_purge(self, queue, nowait=False, ticket=None):
        """
        This method removes all messages from a queue.  It does not cancel
        consumers.  Purged messages are deleted without any formal "undo"
        mechanism.

        if nowait is False, returns a message_count

        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(queue)
        args.write_bit(nowait)
        self._send_method_frame((50, 30), args)

        if not nowait:
            return self.wait(allowed_methods=[
                              (50, 31),    # Channel.queue_purge_ok
                            ])


    def _queue_purge_ok(self, args):
        """
        This method confirms the purge of a queue.

        """
        return args.read_long()


    #############
    #
    #  Basic
    #
    #
    # The Basic class provides methods that support an industry-standard
    # messaging model.
    #
    # GRAMMAR:
    #
    #     basic               = C:QOS S:QOS-OK
    #                         / C:CONSUME S:CONSUME-OK
    #                         / C:CANCEL S:CANCEL-OK
    #                         / C:PUBLISH content
    #                         / S:RETURN content
    #                         / S:DELIVER content
    #                         / C:GET ( S:GET-OK content / S:GET-EMPTY )
    #                         / C:ACK
    #                         / C:REJECT
    #
    # RULE:
    #
    #     The server SHOULD respect the persistent property of basic
    #     messages and SHOULD make a best-effort to hold persistent basic
    #     messages on a reliable storage mechanism.
    #
    # RULE:
    #
    #     The server MUST NOT discard a persistent basic message in case of
    #     a queue overflow. The server MAY use the Channel.Flow method to
    #     slow or stop a basic message publisher when necessary.
    #
    # RULE:
    #
    #     The server MAY overflow non-persistent basic messages to
    #     persistent storage and MAY discard or dead-letter non-persistent
    #     basic messages on a priority basis if the queue size exceeds some
    #     configured limit.
    #
    # RULE:
    #
    #     The server MUST implement at least 2 priority levels for basic
    #     messages, where priorities 0-4 and 5-9 are treated as two distinct
    #     levels. The server MAY implement up to 10 priority levels.
    #
    # RULE:
    #
    #     The server MUST deliver messages of the same priority in order
    #     irrespective of their individual persistence.
    #
    # RULE:
    #
    #     The server MUST support both automatic and explicit
    #     acknowledgements on Basic content.
    #
    #

    def basic_ack(self, delivery_tag, multiple=False):
        """
        This method acknowledges one or more messages delivered via the
        Deliver or Get-Ok methods.  The client can ask to confirm a
        single message or a set of messages up to and including a specific
        message.

        """
        args = AMQPWriter()
        args.write_longlong(delivery_tag)
        args.write_bit(multiple)
        self._send_method_frame((60, 80), args)


    def basic_cancel(self, consumer_tag, nowait=False):
        """
        This method cancels a consumer. This does not affect already
        delivered messages, but it does mean the server will not send any
        more messages for that consumer.  The client may receive an
        abitrary number of messages in between sending the cancel method
        and receiving the cancel-ok reply.

        RULE:

            If the queue no longer exists when the client sends a cancel
            command, or the consumer has been cancelled for other reasons,
            this command has no effect.

        """
        args = AMQPWriter()
        args.write_shortstr(consumer_tag)
        args.write_bit(nowait)
        self._send_method_frame((60, 30), args)
        return self.wait(allowed_methods=[
                          (60, 31),    # Channel.basic_cancel_ok
                        ])


    def _basic_cancel_ok(self, args):
        """
        This method confirms that the cancellation was completed.

        """
        consumer_tag = args.read_shortstr()
        del self.callbacks[consumer_tag]


    def basic_consume(self, queue, consumer_tag='', no_local=False,
        no_ack=False, exclusive=False, nowait=False,
        callback=None, ticket=None):
        """
        This method asks the server to start a "consumer", which is a
        transient request for messages from a specific queue. Consumers
        last as long as the channel they were created on, or until the
        client cancels them.

        RULE:

            The server SHOULD support at least 16 consumers per queue,
            unless the queue was declared as private, and ideally, impose
            no limit except as defined by available resources.

        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(queue)
        args.write_shortstr(consumer_tag)
        args.write_bit(no_local)
        args.write_bit(no_ack)
        args.write_bit(exclusive)
        args.write_bit(nowait)
        self._send_method_frame((60, 20), args)

        if not nowait:
            consumer_tag = self.wait(allowed_methods=[
                              (60, 21),    # Channel.basic_consume_ok
                            ])

        self.callbacks[consumer_tag] = callback

        return consumer_tag


    def _basic_consume_ok(self, args):
        """
        The server provides the client with a consumer tag, which is used
        by the client for methods called on the consumer at a later stage.

        """
        return args.read_shortstr()


    def _basic_deliver(self, args):
        """
        This method delivers a message to the client, via a consumer.  In
        the asynchronous message delivery model, the client starts a
        consumer using the Consume method, then the server responds with
        Deliver methods as and when messages arrive for that consumer.

        RULE:

            The server SHOULD track the number of times a message has been
            delivered to clients and when a message is redelivered a certain
            number of times - e.g. 5 times - without being acknowledged, the
            server SHOULD consider the message to be unprocessable (possibly
            causing client applications to abort), and move the message to a
            dead letter queue.

        """
        consumer_tag = args.read_shortstr()
        delivery_tag = args.read_longlong()
        redelivered = args.read_bit()
        exchange = args.read_shortstr()
        routing_key = args.read_shortstr()

        msg = self.wait()

        msg.delivery_info = {
            'channel': self,
            'consumer_tag': consumer_tag,
            'delivery_tag': delivery_tag,
            'redelivered': redelivered,
            'exchange': exchange,
            'routing_key': routing_key,
            }

        if consumer_tag in self.callbacks:
            self.callbacks[consumer_tag](msg)


    def basic_get(self, queue, no_ack=False, ticket=None):
        """
        This method provides a direct access to the messages in a queue
        using a synchronous dialogue that is designed for specific types of
        application where synchronous functionality is more important than
        performance.

        Non-blocking, returns a message object, or None.
        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(queue)
        args.write_bit(no_ack)
        self._send_method_frame((60, 70), args)
        return self.wait(allowed_methods=[
                          (60, 71),    # Channel.basic_get_ok
                          (60, 72),    # Channel.basic_get_empty
                        ])


    def _basic_get_empty(self, args):
        """
        This method tells the client that the queue has no messages
        available for the client.

        """
        cluster_id = args.read_shortstr()


    def _basic_get_ok(self, args):
        """
        This method delivers a message to the client following a get
        method.  A message delivered by 'get-ok' must be acknowledged
        unless the no-ack option was set in the get method.

        """
        delivery_tag = args.read_longlong()
        redelivered = args.read_bit()
        exchange = args.read_shortstr()
        routing_key = args.read_shortstr()
        message_count = args.read_long()

        msg = self.wait()

        msg.delivery_info = {
            'delivery_tag': delivery_tag,
            'redelivered': redelivered,
            'exchange': exchange,
            'routing_key': routing_key,
            'message_count': message_count
            }

        return msg


    def basic_publish(self, msg, exchange, routing_key='', mandatory=False,
        immediate=False, ticket=None):
        """
        This method publishes a message to a specific exchange. The message
        will be routed to queues as defined by the exchange configuration
        and distributed to any active consumers when the transaction, if
        any, is committed.

        """
        args = AMQPWriter()
        args.write_short(ticket if ticket is not None else self.default_ticket)
        args.write_shortstr(exchange)
        args.write_shortstr(routing_key)
        args.write_bit(mandatory)
        args.write_bit(immediate)
        self._send_method_frame((60, 40), args)

        self.connection._send_content(self.channel_id, 60, 0,
            len(msg.body),
            msg._serialize_properties(),
            msg.body)


    def basic_qos(self, prefetch_size, prefetch_count, a_global):
        """
        This method requests a specific quality of service.  The QoS can
        be specified for the current channel or for all channels on the
        connection.  The particular properties and semantics of a qos method
        always depend on the content class semantics.  Though the qos method
        could in principle apply to both peers, it is currently meaningful
        only for the server.

        """
        args = AMQPWriter()
        args.write_long(prefetch_size)
        args.write_short(prefetch_count)
        args.write_bit(a_global)
        self._send_method_frame((60, 10), args)
        return self.wait(allowed_methods=[
                          (60, 11),    # Channel.basic_qos_ok
                        ])


    def _basic_qos_ok(self, args):
        """
        This method tells the client that the requested QoS levels could
        be handled by the server.  The requested QoS applies to all active
        consumers until a new QoS is defined.

        """
        pass


    def basic_recover(self, requeue=False):
        """
        This method asks the broker to redeliver all unacknowledged messages
        on a specified channel. Zero or more messages may be redelivered.
        This method is only allowed on non-transacted channels.

        RULE:

            The server MUST set the redelivered flag on all messages that
            are resent.

        RULE:

            The server MUST raise a channel exception if this is called on a
            transacted channel.

        """
        args = AMQPWriter()
        args.write_bit(requeue)
        self._send_method_frame((60, 100), args)


    def basic_reject(self, delivery_tag, requeue):
        """
        This method allows a client to reject a message.  It can be used to
        interrupt and cancel large incoming messages, or return untreatable
        messages to their original queue.

        RULE:

            The server SHOULD be capable of accepting and process the Reject
            method while sending message content with a Deliver or Get-Ok
            method.  I.e. the server should read and process incoming
            methods while sending output frames.  To cancel a partially-send
            content, the server sends a content body frame of size 1
            (i.e. with no data except the frame-end octet).

        RULE:

            The server SHOULD interpret this method as meaning that the
            client is unable to process the message at this time.

        RULE:

            A client MUST NOT use this method as a means of selecting
            messages to process.  A rejected message MAY be discarded or
            dead-lettered, not necessarily passed to another client.

        """
        args = AMQPWriter()
        args.write_longlong(delivery_tag)
        args.write_bit(requeue)
        self._send_method_frame((60, 90), args)


    def _basic_return(self, args):
        """
        This method returns an undeliverable message that was published
        with the "immediate" flag set, or an unroutable message published
        with the "mandatory" flag set. The reply code and text provide
        information about the reason that the message was undeliverable.

        """
        reply_code = args.read_short()
        reply_text = args.read_shortstr()
        exchange = args.read_shortstr()
        routing_key = args.read_shortstr()
        msg = self.wait()


    #############
    #
    #  Tx
    #
    #
    # Standard transactions provide so-called "1.5 phase commit".  We can
    # ensure that work is never lost, but there is a chance of confirmations
    # being lost, so that messages may be resent.  Applications that use
    # standard transactions must be able to detect and ignore duplicate
    # messages.
    #
    # GRAMMAR:
    #
    #     tx                  = C:SELECT S:SELECT-OK
    #                         / C:COMMIT S:COMMIT-OK
    #                         / C:ROLLBACK S:ROLLBACK-OK
    #
    #

    def tx_commit(self):
        """
        This method commits all messages published and acknowledged in
        the current transaction.  A new transaction starts immediately
        after a commit.

        """
        self._send_method_frame((90, 20))
        return self.wait(allowed_methods=[
                          (90, 21),    # Channel.tx_commit_ok
                        ])


    def _tx_commit_ok(self, args):
        """
        This method confirms to the client that the commit succeeded.
        Note that if a commit fails, the server raises a channel exception.

        """
        pass


    def tx_rollback(self):
        """
        This method abandons all messages published and acknowledged in
        the current transaction.  A new transaction starts immediately
        after a rollback.

        """
        self._send_method_frame((90, 30))
        return self.wait(allowed_methods=[
                          (90, 31),    # Channel.tx_rollback_ok
                        ])


    def _tx_rollback_ok(self, args):
        """
        This method confirms to the client that the rollback succeeded.
        Note that if an rollback fails, the server raises a
        channel exception.

        """
        pass


    def tx_select(self):
        """
        This method sets the channel to use standard transactions.  The
        client must use this method at least once on a channel before
        using the Commit or Rollback methods.

        """
        self._send_method_frame((90, 10))
        return self.wait(allowed_methods=[
                          (90, 11),    # Channel.tx_select_ok
                        ])


    def _tx_select_ok(self, args):
        """
        This method confirms to the client that the channel was
        successfully set to use standard transactions.

        """
        pass


_METHOD_MAP = {
    (10, 10): (Connection, Connection._start),
    (10, 20): (Connection, Connection._secure),
    (10, 30): (Connection, Connection._tune),
    (10, 41): (Connection, Connection._open_ok),
    (10, 50): (Connection, Connection._redirect),
    (10, 60): (Connection, Connection._close),
    (10, 61): (Connection, Connection._close_ok),
    (20, 11): (Channel, Channel._open_ok),
    (20, 20): (Channel, Channel._flow),
    (20, 21): (Channel, Channel._flow_ok),
    (20, 30): (Channel, Channel._alert),
    (20, 40): (Channel, Channel._close),
    (20, 41): (Channel, Channel._close_ok),
    (30, 11): (Channel, Channel._access_request_ok),
    (40, 11): (Channel, Channel._exchange_declare_ok),
    (40, 21): (Channel, Channel._exchange_delete_ok),
    (50, 11): (Channel, Channel._queue_declare_ok),
    (50, 21): (Channel, Channel._queue_bind_ok),
    (50, 31): (Channel, Channel._queue_purge_ok),
    (50, 41): (Channel, Channel._queue_delete_ok),
    (60, 11): (Channel, Channel._basic_qos_ok),
    (60, 21): (Channel, Channel._basic_consume_ok),
    (60, 31): (Channel, Channel._basic_cancel_ok),
    (60, 50): (Channel, Channel._basic_return),
    (60, 60): (Channel, Channel._basic_deliver),
    (60, 71): (Channel, Channel._basic_get_ok),
    (60, 72): (Channel, Channel._basic_get_empty),
    (90, 11): (Channel, Channel._tx_select_ok),
    (90, 21): (Channel, Channel._tx_commit_ok),
    (90, 31): (Channel, Channel._tx_rollback_ok),
}

_CLOSE_METHODS = [
    (10, 60), # Connection.close
    (20, 40), # Channel.close
    ]

_METHOD_NAME_MAP = {
    (10, 10): 'Connection.start',
    (10, 11): 'Connection.start_ok',
    (10, 20): 'Connection.secure',
    (10, 21): 'Connection.secure_ok',
    (10, 30): 'Connection.tune',
    (10, 31): 'Connection.tune_ok',
    (10, 40): 'Connection.open',
    (10, 41): 'Connection.open_ok',
    (10, 50): 'Connection.redirect',
    (10, 60): 'Connection.close',
    (10, 61): 'Connection.close_ok',
    (20, 10): 'Channel.open',
    (20, 11): 'Channel.open_ok',
    (20, 20): 'Channel.flow',
    (20, 21): 'Channel.flow_ok',
    (20, 30): 'Channel.alert',
    (20, 40): 'Channel.close',
    (20, 41): 'Channel.close_ok',
    (30, 10): 'Channel.access_request',
    (30, 11): 'Channel.access_request_ok',
    (40, 10): 'Channel.exchange_declare',
    (40, 11): 'Channel.exchange_declare_ok',
    (40, 20): 'Channel.exchange_delete',
    (40, 21): 'Channel.exchange_delete_ok',
    (50, 10): 'Channel.queue_declare',
    (50, 11): 'Channel.queue_declare_ok',
    (50, 20): 'Channel.queue_bind',
    (50, 21): 'Channel.queue_bind_ok',
    (50, 30): 'Channel.queue_purge',
    (50, 31): 'Channel.queue_purge_ok',
    (50, 40): 'Channel.queue_delete',
    (50, 41): 'Channel.queue_delete_ok',
    (60, 10): 'Channel.basic_qos',
    (60, 11): 'Channel.basic_qos_ok',
    (60, 20): 'Channel.basic_consume',
    (60, 21): 'Channel.basic_consume_ok',
    (60, 30): 'Channel.basic_cancel',
    (60, 31): 'Channel.basic_cancel_ok',
    (60, 40): 'Channel.basic_publish',
    (60, 50): 'Channel.basic_return',
    (60, 60): 'Channel.basic_deliver',
    (60, 70): 'Channel.basic_get',
    (60, 71): 'Channel.basic_get_ok',
    (60, 72): 'Channel.basic_get_empty',
    (60, 80): 'Channel.basic_ack',
    (60, 90): 'Channel.basic_reject',
    (60, 100): 'Channel.basic_recover',
    (90, 10): 'Channel.tx_select',
    (90, 11): 'Channel.tx_select_ok',
    (90, 20): 'Channel.tx_commit',
    (90, 21): 'Channel.tx_commit_ok',
    (90, 30): 'Channel.tx_rollback',
    (90, 31): 'Channel.tx_rollback_ok',
}


class Message(GenericContent):
    """
    A Message for use with the Channnel.basic_* methods.

    """
    #
    # Instances of this class have these attributes, which
    # are passed back and forth as message properties between
    # client and server
    #
    PROPERTIES = [
        ('content_type', 'shortstr'),
        ('content_encoding', 'shortstr'),
        ('application_headers', 'table'),
        ('delivery_mode', 'octet'),
        ('priority', 'octet'),
        ('correlation_id', 'shortstr'),
        ('reply_to', 'shortstr'),
        ('expiration', 'shortstr'),
        ('message_id', 'shortstr'),
        ('timestamp', 'timestamp'),
        ('type', 'shortstr'),
        ('user_id', 'shortstr'),
        ('app_id', 'shortstr'),
        ('cluster_id', 'shortstr')
        ]

    def __init__(self, body='', children=None, **properties):
        """
        Expected arg types

            body: string
            children: (not supported)

        Keyword properties may include:

            content_type: string
            content_encoding: string
            application_headers: dict with string keys, and
                string/int/Decimal/datetime/dict values
            delivery_mode: Non-persistent=1 or persistent=2
            priority: 0..9
            correlation_id: string
            reply_to: string
            expiration: string
            message_id: string
            timestamp: datetime.datetime
            type: string
            user_id: string
            app_id: string
            cluster_id: string

        Unicode bodies are encoded according to the 'content_encoding'
        argument. If that's None, it's set to 'UTF-8' automatically.

        example:

            msg = Message('hello world',
                            content_type='text/plain',
                            application_headers={'foo': 7})

        """
        if isinstance(body, unicode):
            if properties.get('content_encoding', None) is None:
                properties['content_encoding'] = 'UTF-8'
            self.body = body.encode(properties['content_encoding'])
        else:
            self.body = body

        super(Message, self).__init__(**properties)


    def __eq__(self, other):
        """
        Check if the properties and bodies of this Message and another
        Message are the same.

        Received messages may contain a 'delivery_info' attribute,
        which isn't compared.

        """
        return super(Message, self).__eq__(other) and (self.body == other.body)
