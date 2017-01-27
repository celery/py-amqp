"""Platform compatibility."""
import sys
import platform
import re
from typing import Pattern, Tuple

# Jython does not have this attribute
try:
    from socket import SOL_TCP
except ImportError:  # pragma: no cover
    from socket import IPPROTO_TCP as SOL_TCP  # noqa

__all__ = [
    'LINUX_VERSION',
    'SOL_TCP',
    'TCP_USER_TIMEOUT',
    'HAS_TCP_USER_TIMEOUT',
]

RE_NUM = re.compile(r'(\d+).+')  # type: Pattern


def _linux_version_to_tuple(s: str) -> Tuple[int, int, int]:
    return tuple(map(_versionatom, s.split('.')[:3]))


def _versionatom(s: str) -> int:
    if s.isdigit():
        return int(s)
    match = RE_NUM.match(s)
    return int(match.groups()[0]) if match else 0


LINUX_VERSION = None
if sys.platform.startswith('linux'):
    LINUX_VERSION = _linux_version_to_tuple(platform.release())

try:
    from socket import TCP_USER_TIMEOUT
    HAS_TCP_USER_TIMEOUT = True
except ImportError:  # pragma: no cover
    # should be in Python 3.6+ on Linux.
    TCP_USER_TIMEOUT = 18
    HAS_TCP_USER_TIMEOUT = LINUX_VERSION and LINUX_VERSION >= (2, 6, 37)
