from __future__ import absolute_import, unicode_literals
import pytest
from amqp.platform import _linux_version_to_tuple


@pytest.mark.parametrize('s,expected', [
    ('3.13.0-46-generic', (3, 13, 0)),
    ('3.19.43-1-amd64', (3, 19, 43)),
    ('4.4.34+', (4, 4, 34)),
    ('4.4.what', (4, 4, 0)),
    ('4.what.what', (4, 0, 0)),
])
def test_linux_version_to_tuple(s, expected):
    assert _linux_version_to_tuple(s) == expected
