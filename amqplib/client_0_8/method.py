"""
Convert between frames and higher-level AMQP methods

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

from collections import defaultdict
from Queue import Empty, Queue
from struct import pack, unpack
from threading import Thread

from basic_message import Message
from exceptions import *
from serialization import AMQPReader

__all__ =  [
            'MethodReader',
           ]


#
# MethodReader needs to know which methods are supposed
# to be followed by content headers and bodies.
#
_CONTENT_METHODS = [
    (60, 60), # Basic.deliver
    (60, 71), # Basic.get_ok
    ]


class _PartialMessage(object):
    """
    Helper class to build up a multi-frame method.

    """
    def __init__(self, method_sig, args):
        self.method_sig = method_sig
        self.args = args
        self.msg = Message()
        self.body_parts = []
        self.body_received = 0
        self.complete = False


    def add_header(self, payload):
        class_id, weight, self.body_size = unpack('>HHQ', payload[:12])
        self.msg._load_properties(payload[12:])
        self.complete = (self.body_size == 0)


    def add_payload(self, payload):
        self.body_parts.append(payload)
        self.body_received += len(payload)

        if self.body_received == self.body_size:
            self.msg.body = ''.join(self.body_parts)
            self.complete = True


class MethodReader(object):
    """
    Helper class to receive frames from the broker, combine them if
    necessary with content-headers and content-bodies into complete methods.

    It may be used in both a threaded and non-threaded fashion.  The threaded
    mode allows for timeouts or non-blocking waits.

    Normally a method is represented as a tuple containing
    (channel, method_sig, args, content).

    In the case of a framing error, an AMQPConnectionException is placed
    in the queue.

    In the case of unexpected frames, a tuple made up of
    (channel, AMQPChannelException) is placed in the queue.

    If the connection is closed, None is placed in the queue and the thread
    exits.

    """
    def __init__(self, source, use_threading=False):
        self.source = source
        self.use_threading = use_threading
        self.queue = Queue()
        self.running = False
        self.expected_types = defaultdict(lambda:1) # For each channel, which type is expected next
        self.partial_messages = {}

        if use_threading:
            self.thread = Thread(group=None, target=self._next_method)
            self.thread.setDaemon(True)
            self.running = True
            self.thread.start()


    def _next_method(self):
        """
        Read the next method from the source.  In threaded mode it
        runs repeatedly, placing messages in the internal queue.
        In non-threaded mode it returns once one complete method has
        been assembled and placed in the internal queue.

        """
        while (self.use_threading and self.running) \
        or (not self.use_threading and self.queue.empty()):
            try:
                frame_type, channel, payload = self.source.read_frame()
            except:
                #
                # Connection was closed?  Framing Error?
                #
                self.queue.put(None)
                break

            if self.expected_types[channel] != frame_type:
                self.queue.put((channel, AMQPChannelException(channel, 'Received frame type %d while expecting type: %d' % (frame_type, self.expected_types[channel]))))
            elif frame_type == 1:
                self._process_method_frame(channel, payload)
            elif frame_type == 2:
                self._process_content_header(channel, payload)
            elif frame_type == 3:
                self._process_content_body(channel, payload)


    def _process_method_frame(self, channel, payload):
        """
        Process Method frames

        """
        method_sig = unpack('>HH', payload[:4])
        args = AMQPReader(payload[4:])

        if method_sig in _CONTENT_METHODS:
            #
            # Save what we've got so far and wait for the content-header
            #
            self.partial_messages[channel] = _PartialMessage(method_sig, args)
            self.expected_types[channel] = 2
        else:
            self.queue.put((channel, method_sig, args, None))


    def _process_content_header(self, channel, payload):
        """
        Process Content Header frames

        """
        partial = self.partial_messages[channel]
        partial.add_header(payload)

        if partial.complete:
            #
            # a bodyless message, we're done
            #
            self.queue.put((channel, partial.method_sig, partial.args, partial.msg))
            del self.partial_messages[channel]
            self.expected_types[channel] = 1
        else:
            #
            # wait for the content-body
            #
            self.expected_types[channel] = 3


    def _process_content_body(self, channel, payload):
        """
        Process Content Body frames

        """
        partial = self.partial_messages[channel]
        partial.add_payload(payload)
        if partial.complete:
            #
            # Stick the message in the queue and go back to
            # waiting for method frames
            #
            self.queue.put((channel, partial.method_sig, partial.args, partial.msg))
            del self.partial_messages[channel]
            self.expected_types[channel] = 1


    def read_method(self, timeout=None):
        """
        Read a method from the peer.

        """
        blocking = (timeout != 0)
        if not self.use_threading:
            if (not blocking) or timeout:
                raise Exception('non-blocking or timeout read requires threading')
            self._next_method()

        try:
            return self.queue.get(blocking, timeout)
        except Empty:
            raise TimeoutException


    def stop(self):
        """
        Stop any helper thread that's running.  Harmless to call if we're
        not using threading.

        """
        if self.use_threading:
            self.running = False
