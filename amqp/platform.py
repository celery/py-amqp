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

RE_NUM: Pattern = re.compile(r'(\d+).+')
TCP_USER_TIMEOUT = 18


def _linux_version_to_tuple(s: str) -> Tuple[int, int, int]:
    a, b, c, *_ = tuple(map(_versionatom, s.split('.')))
    return a, b, c


def _versionatom(s: str) -> int:
    if s.isdigit():
        return int(s)
    match = RE_NUM.match(s)
    return int(match.groups()[0]) if match else 0


LINUX_VERSION: Tuple[int, int, int] = None
if sys.platform.startswith('linux'):
    LINUX_VERSION = _linux_version_to_tuple(platform.release())

try:
    from socket import TCP_USER_TIMEOUT  # type: ignore
    HAS_TCP_USER_TIMEOUT = True
except ImportError:  # pragma: no cover
    # should be in Python 3.6+ on Linux.
    HAS_TCP_USER_TIMEOUT = LINUX_VERSION and LINUX_VERSION >= (2, 6, 37)
