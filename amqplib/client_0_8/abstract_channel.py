"""
Code common to Connection and Channel objects.

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

import logging

from exceptions import METHOD_NAME_MAP

__all__ =  [
            'AbstractChannel',
           ]

AMQP_LOGGER = logging.getLogger('amqplib')

_CLOSE_METHODS = [
    (10, 60), # Connection.close
    (20, 40), # Channel.close
    ]


class AbstractChannel(object):
    """
    Superclass for both the Connection, which is treated
    as channel 0, and other user-created Channel objects.

    The subclasses must have a _METHOD_MAP class property, mapping
    between AMQP method signatures and Python methods.

    """
    def __init__(self, connection, channel_id):
        self.connection = connection
        self.channel_id = channel_id
        connection.channels[channel_id] = self
        self.method_queue = [] # Higher level queue for methods
        self.auto_decode = False


    def _dispatch(self, method_sig, args, content):
        """
        Find and call a Python method to handle the given AMQP method.

        """
        amqp_method = self._METHOD_MAP.get(method_sig, None)

        if amqp_method is None:
            raise Exception('Unknown AMQP method (%d, %d)' % method_sig)

        if content is None:
            return amqp_method(self, args)
        else:
            return amqp_method(self, args, content)


    def _send_method_frame(self, method_sig, args=''):
        """
        Send a method frame for our channel.

        """
        self.connection._send_channel_method_frame(self.channel_id,
            method_sig, args)


    def wait(self, allowed_methods=None, timeout=None):
        """
        Wait for a method that matches our allowed_methods parameter (the
        default value of None means match any method), and dispatch to it.

        Unexpected methods are queued up for later calls to this Python
        method.

        """
        #
        # Check for a deferred method
        #
        for queued_method in self.method_queue:
            method_sig = queued_method[0]
            if (allowed_methods is None) \
            or (method_sig in allowed_methods):
                self.method_queue.remove(queued_method)
                AMQP_LOGGER.debug('Executing queued method: %s: %s' %
                    (str(method_sig), METHOD_NAME_MAP[method_sig]))

                return self._dispatch(*queued_method)

        #
        # No deferred methods?  wait for a new one
        #
        while True:
            method_sig, args, content = self.connection._wait_method(
                self.channel_id, timeout)

            if content \
            and self.auto_decode \
            and hasattr(content, 'content_encoding'):
                try:
                    content.body = content.body.decode(content.content_encoding)
                except:
                    pass

            if (allowed_methods is None) \
            or (method_sig in allowed_methods) \
            or (method_sig in _CLOSE_METHODS):
                return self._dispatch(method_sig, args, content)

            # Wasn't what we were looking for? save it for later
            AMQP_LOGGER.debug('Queueing for later: %s: %s' %
                (str(method_sig), METHOD_NAME_MAP[method_sig]))
            self.method_queue.append((method_sig, args, content))

    #
    # Placeholder, the concrete implementations will have to
    # supply their own versions of _METHOD_MAP
    #
    _METHOD_MAP = {}
