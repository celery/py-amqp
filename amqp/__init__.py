"""Low-level AMQP client for Python (fork of amqplib)."""
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
import re
from typing import NamedTuple
from vine import promise

__version__ = '3.0.0a1'
__author__ = 'Barry Pederson'
__maintainer__ = 'Ask Solem'
__contact__ = 'pyamqp@celeryproject.org'
__homepage__ = 'http://github.com/celery/py-amqp'
__docformat__ = 'restructuredtext'

# -eof meta-

from .basic_message import Message  # noqa: F401
from .channel import Channel        # noqa: F401
from .connection import Connection  # noqa: F401
from .exceptions import (           # noqa: F401
    AMQPError,
    ConnectionError,
    RecoverableConnectionError,
    IrrecoverableConnectionError,
    ChannelError,
    RecoverableChannelError,
    IrrecoverableChannelError,
    ConsumerCancelled,
    ContentTooLarge,
    NoConsumers,
    ConnectionForced,
    InvalidPath,
    AccessRefused,
    NotFound,
    ResourceLocked,
    PreconditionFailed,
    FrameError,
    FrameSyntaxError,
    InvalidCommand,
    ChannelNotOpen,
    UnexpectedFrame,
    ResourceError,
    NotAllowed,
    AMQPNotImplementedError,
    InternalError,
    error_for_code,
)
from .types import ChannelT, ConnectionT, MessageT  # noqa: F401

__all__ = [
    'Connection',
    'ConnectionT',
    'Channel',
    'ChannelT',
    'Message',
    'MessageT',
    'promise',
    'AMQPError',
    'ConnectionError',
    'RecoverableConnectionError',
    'IrrecoverableConnectionError',
    'ChannelError',
    'RecoverableChannelError',
    'IrrecoverableChannelError',
    'ConsumerCancelled',
    'ContentTooLarge',
    'NoConsumers',
    'ConnectionForced',
    'InvalidPath',
    'AccessRefused',
    'NotFound',
    'ResourceLocked',
    'PreconditionFailed',
    'FrameError',
    'FrameSyntaxError',
    'InvalidCommand',
    'ChannelNotOpen',
    'UnexpectedFrame',
    'ResourceError',
    'NotAllowed',
    'AMQPNotImplementedError',
    'InternalError',
    'error_for_code',
    'version_info_t',
]


class version_info_t(NamedTuple):
    major: int
    minor: int
    micro: int
    releaselevel: str
    serial: str


# bumpversion can only search for {current_version}
# so we have to parse the version here.
_temp = re.match(
    r'(\d+)\.(\d+).(\d+)(.+)?', __version__).groups()
VERSION = version_info = version_info_t(
    int(_temp[0]), int(_temp[1]), int(_temp[2]), _temp[3] or '', '')
del(_temp)
del(re)
