"""Platform compatibility."""
from __future__ import absolute_import, unicode_literals

import sys
import platform

# Jython does not have this attribute
try:
    from socket import SOL_TCP
except ImportError:  # pragma: no cover
    from socket import IPPROTO_TCP as SOL_TCP  # noqa

LINUX_VERSION = None
if sys.platform.startswith('linux'):
    LINUX_VERSION = tuple(map(
        int, platform.release().split('-')[0].split('.')))

try:
    from socket import TCP_USER_TIMEOUT
    HAS_TCP_USER_TIMEOUT = True
except ImportError:  # pragma: no cover
    # should be in Python 3.6+ on Linux.
    TCP_USER_TIMEOUT = 18
    HAS_TCP_USER_TIMEOUT = LINUX_VERSION and LINUX_VERSION >= (2, 6, 37)

__all__ = [
    'LINUX_VERSION',
    'SOL_TCP',
    'TCP_USER_TIMEOUT',
    'HAS_TCP_USER_TIMEOUT',
]
