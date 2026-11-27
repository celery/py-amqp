=====================================================
 ``amqp.connection``
=====================================================

.. contents::
    :local:
.. currentmodule:: amqp.connection

RabbitMQ blocked connections
============================

Set ``blocked_connection_timeout`` to bound a resource-alarm block after the
client receives ``Connection.Blocked``::

    from amqp import Connection
    from amqp.exceptions import ConnectionBlockedTimeout

    connection = Connection(
        'localhost', blocked_connection_timeout=10,
    )

The option defaults to ``None`` (disabled). The deadline starts when the
notification is processed, applies across synchronous RPC reads, and is not
renewed by partial frames or repeated blocked notifications. An unblocked
notification cancels it. Existing shorter read or per-call socket timeouts
can still end a wait earlier.

When the deadline expires, ``ConnectionBlockedTimeout`` is raised and the
connection is discarded immediately, including its channels. Disposal skips
the AMQP close exchange and TLS shutdown handshake. Create a fresh connection
before retrying. The exception derives from ``RecoverableConnectionError``.

The client has no background reader or timer. An idle connection checks expiry
on its next read or method send. A blocked socket write can prevent the client
from receiving the notification at all. Use ``operation_timeout`` below to also
bound declaration and publication writes before the notification is read.
A publish write timeout discards the connection because its partially written
frames cannot be safely reused.
This setting does not impose a total deadline on connection establishment,
publication, application callbacks, or multiple retry attempts.

A publication that raises an exception may already have been delivered.
Applications must account for possible duplicate delivery when retrying.

Explicitly closing a known-blocked connection also discards it without waiting
for a close handshake. A broker-initiated connection or channel close preserves
the broker's error and reason while disposing of the blocked connection,
including any sibling channels. A channel already closing, or closing with its
connection, continues to suppress the broker's channel error as before.

Operation wait budget
=====================

An optional execution-context budget bounds library-controlled network and
writer-lock waits independently of blocked notifications::

    from amqp import Connection, Message, OperationTimeout, operation_timeout

    connection = Connection('localhost')
    with operation_timeout(5):
        connection.connect()
        channel = connection.channel()
        channel.queue_declare('example')
        channel.basic_publish(Message('hello'), routing_key='example')

The deadline uses a monotonic clock and spans TCP address attempts, TLS and
AMQP handshakes, metadata RPCs, complete reads and writes (including partial
frames), confirms, and writer-lock acquisition. Nested scopes inherit the
earlier deadline. Earlier socket or blocked timeouts still apply. A finite
non-negative timeout no greater than ``threading.TIMEOUT_MAX`` is required;
zero expires immediately, and ``None`` only
inherits an existing scope.

On expiry ``OperationTimeout`` (a ``RecoverableConnectionError``) is raised.
Interrupted protocol I/O disposes of the connection and its channels without
waiting for AMQP or TLS shutdown. A timeout before acquiring the writer lock
sets ``connection_usable=True`` and does not close the active writer's socket.
Callers must preserve this distinction when returning resources to pools.

If a broker channel error has already been received, it takes precedence over
a later socket or deadline timeout while acknowledging that error or reopening
the channel. With either timeout feature enabled, that cleanup failure discards
the connection and its sibling channels; the received channel error retains its
reply code, reason and exception class, with the cleanup timeout as its cause.
When the connection is discarded, the preserved channel error also sets
``connection_usable=False``. Clients must reconnect before retrying, including
for a recoverable channel error such as ``ResourceLocked``. Successful channel
revival leaves this marker unset and retains normal channel retry behavior.
A deadline that expires before a channel error is processed still raises
``OperationTimeout`` normally. Closing-state suppression is unchanged, and
unrelated cleanup exceptions are not suppressed.

There is no background timer. Synchronous DNS and application callbacks are
checked cooperatively when they return; the library cannot safely interrupt
arbitrary application or resolver code. Scheduling delays can also exceed the
budget. Work outside the scope or in another thread is not timed. Include
connection disposal in the scope when a bounded close is required. A timeout
does not prove non-delivery; a retry can duplicate the message.

.. automodule:: amqp.connection
    :members:
    :undoc-members:
