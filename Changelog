Changes
=======

py-amqp is fork of amqplib used by Kombu containing additional features and improvements.
The previous amqplib changelog is here:
http://code.google.com/p/py-amqplib/source/browse/CHANGES

.. _version-1.0.8:

1.0.8
=====
:release-date: 2013-02-08 01:00 P.M UTC

- Fixed SyntaxError on Python 2.5

.. _version-1.0.7:

1.0.7
=====
:release-date: 2013-02-08 01:00 P.M UTC

- Workaround for bug on some Python 2.5 installations where (2**32) is 0.

- Can now serialize the ARRAY type.

    Contributed by Adam Wentz.

- Fixed tuple format bug in exception (Issue #4).

.. _version-1.0.6:

1.0.6
=====
:release-date: 2012-11-29 01:14 P.M UTC

- ``Channel.close`` is now ignored if the connection attribute is None.

.. _version-1.0.5

1.0.5
=====
:release-date: 2012-11-21 04:00 P.M UTC

- ``Channel.basic_cancel`` is now ignored if the channel was already closed.

- ``Channel.events`` is now a dict of sets::

    >>> channel.events['basic_return'].add(on_basic_return)
    >>> channel.events['basic_return'].discard(on_basic_return)

.. _version-1.0.4:

1.0.4
=====
:release-date: 2012-11-13 04:00 P.M UTC

- Fixes Python 2.5 support

.. _version-1.0.3:

1.0.3
=====
:release-date: 2012-11-12 04:00 P.M UTC

- Now can also handle float in headers/tables when receiving messages.

- Now uses :class:`array.array` to keep track of unused channel ids.

- The :data:`~amqp.exceptions.METHOD_NAME_MAP` has been updated for
  amqp/0.9.1 and Rabbit extensions.

- Removed a bunch of accidentally included images.

.. _version-1.0.2:

1.0.2
=====
:release-date: 2012-11-06 05:00 P.M UTC

- Now supports float values in headers/tables.

.. _version-1.0.1:

1.0.1
=====
:release-date: 2012-11-05 01:00 P.M UTC

- Connection errors does no longer include :exc:`AttributeError`.

- Fixed problem with using the SSL transport in a non-blocking context.

    Fix contributed by Mher Movsisyan.


.. _version-1.0.0:

1.0.0
=====
:release-date: 2012-11-05 01:00 P.M UTC

- Channels are now restored on channel error, so that the connection does not
  have to closed.

.. _version-0.9.4:

Version 0.9.4
=============

- Adds support for ``exchange_bind`` and ``exchange_unbind``.

    Contributed by Rumyana Neykova

- Fixed bugs in funtests and demo scripts.

    Contributed by Rumyana Neykova

.. _version-0.9.3:

Version 0.9.3
=============

- Fixed bug that could cause the consumer to crash when reading
  large message payloads asynchronously.

- Serialization error messages now include the invalid value.

.. _version-0.9.2:

Version 0.9.2
=============

- Consumer cancel notification support was broken (Issue #1)

    Fix contributed by Andrew Grangaard

.. _version-0.9.1:

Version 0.9.1
=============

- Supports draining events from multiple channels (``Connection.drain_events``)
- Support for timeouts
- Support for heartbeats
    - ``Connection.heartbeat_tick(rate=2)`` must called at regular intervals
      (half of the heartbeat value if rate is 2).
    - Or some other scheme by using ``Connection.send_heartbeat``.
- Supports RabbitMQ extensions:
    - Consumer Cancel Notifications
        - by default a cancel results in ``ChannelError`` being raised
        - but not if a ``on_cancel`` callback is passed to ``basic_consume``.
    - Publisher confirms
        - ``Channel.confirm_select()`` enables publisher confirms.
        - ``Channel.events['basic_ack'].append(my_callback)`` adds a callback
          to be called when a message is confirmed. This callback is then
          called with the signature ``(delivery_tag, multiple)``.
- Support for ``basic_return``
- Uses AMQP 0-9-1 instead of 0-8.
    - ``Channel.access_request`` and ``ticket`` arguments to methods
      **removed**.
    - Supports the ``arguments`` argument to ``basic_consume``.
    - ``internal`` argument to ``exchange_declare`` removed.
    - ``auto_delete`` argument to ``exchange_declare`` deprecated
    - ``insist`` argument to ``Connection`` removed.
    - ``Channel.alerts`` has been removed.
    - Support for ``Channel.basic_recover_async``.
    - ``Channel.basic_recover`` deprecated.
- Exceptions renamed to have idiomatic names:
    - ``AMQPException`` -> ``AMQPError``
    - ``AMQPConnectionException`` -> ConnectionError``
    - ``AMQPChannelException`` -> ChannelError``
    - ``Connection.known_hosts`` removed.
    - ``Connection`` no longer supports redirects.
    - ``exchange`` argument to ``queue_bind`` can now be empty
      to use the "default exchange".
- Adds ``Connection.is_alive`` that tries to detect
  whether the connection can still be used.
- Adds ``Connection.connection_errors`` and ``.channel_errors``,
  a list of recoverable errors.
- Exposes the underlying socket as ``Connection.sock``.
- Adds ``Channel.no_ack_consumers`` to keep track of consumer tags
  that set the no_ack flag.
- Slightly better at error recovery
