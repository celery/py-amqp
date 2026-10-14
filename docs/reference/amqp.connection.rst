=====================================================
 ``amqp.connection``
=====================================================

.. contents::
    :local:
.. currentmodule:: amqp.connection

Renew an expiring secret
=======================

Use :meth:`Connection.update_secret` to send a new OAuth 2 token to RabbitMQ
on an open connection::

    connection.update_secret(new_token, 'token renewal')

The call waits for the broker to confirm the update. Existing channels stay
open. Obtain the token and call this method before the current token expires.
Do not put credentials in the reason string; the broker can log it.

This method requires the RabbitMQ ``connection.update-secret`` extension.
It updates the secret for the current connection. It does not change a user's
password in the broker or obtain tokens. Use current credentials when you open
a later connection. If the broker rejects the update, the call raises the
broker's connection error and the connection closes.

.. automodule:: amqp.connection
    :members:
    :undoc-members:
