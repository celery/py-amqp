import os
from datetime import datetime

from amqp.serialization import loads, dumps


def test_deserialize(benchmark):
    format = b'bobBlLbsbSTx'
    x = dumps(format, [
        True, 32, False, 3415, 4513134, 13241923419,
        True, b'thequickbrownfox', False, 'jumpsoverthelazydog',
        datetime(2015, 3, 13, 10, 23),
        b'thequick\xff'
    ])
    benchmark(loads, format, x)


def test_deserialize_pure_python(benchmark):
    os.environ['PYAMQP_DUMPS_SKIP_SPEEDUPS'] = "True"
    format = b'bobBlLbsbSTx'
    x = dumps(format, [
        True, 32, False, 3415, 4513134, 13241923419,
        True, b'thequickbrownfox', False, 'jumpsoverthelazydog',
        datetime(2015, 3, 13, 10, 23),
        b'thequick\xff'
    ])
    benchmark(loads, format, x)
