from __future__ import absolute_import, unicode_literals

import os
from datetime import datetime

import pytest

from amqp.serialization import dumps, loads


@pytest.mark.benchmark(group='bitmaps')
@pytest.mark.parametrize("bits,pure_python", [
    (4, False),
    (4, True),
    (8, False),
    (8, True),
    (16, False),
    (16, True),
],
    ids=[
    '4 bits | Rust Extension',
    '4 bits | Pure Python',
    '8 bits | Rust Extension',
    '8 bits | Pure Python',
    '16 bits | Rust Extension',
    '16 bits | Pure Python',
]
)
def test_deserialize_bitmap(benchmark, bits, pure_python):
    pytest.importorskip("amqp_serialization")

    if pure_python:
        os.environ['PYAMQP_DUMPS_SKIP_SPEEDUPS'] = "True"
    format = 'b' * bits
    x = dumps(format, [True] * bits)
    benchmark(loads, format, x)


@pytest.mark.benchmark(group='timestamps')
@pytest.mark.parametrize("size_multipler,pure_python", [
    (1, False),
    (1, True),
    (2, False),
    (2, True),
    (4, False),
    (4, True),
],
    ids=[
    '1 elements | Rust Extension',
    '1 elements | Pure Python',
    '2 elements | Rust Extension',
    '2 elements | Pure Python',
    '4 elements | Rust Extension',
    '4 elements | Pure Python',
]
)
def test_deserialize_timestamp(benchmark, size_multipler, pure_python):
    pytest.importorskip("amqp_serialization")

    if pure_python:
        os.environ['PYAMQP_DUMPS_SKIP_SPEEDUPS'] = "True"
    format = b'T' * size_multipler
    x = dumps(format, [datetime.utcnow()] * size_multipler)
    benchmark(loads, format, x)


@pytest.mark.benchmark(group='mixed')
@pytest.mark.parametrize("size_multipler,pure_python", [
    (1, False),
    (1, True),
    (2, False),
    (2, True),
    (3, False),
    (3, True),
],
    ids=[
    '11 elements | Rust Extension',
    '11 elements | Pure Python',
    '22 elements | Rust Extension',
    '22 elements | Pure Python',
    '33 elements | Rust Extension',
    '33 elements | Pure Python',
]
)
def test_deserialize(benchmark, size_multipler, pure_python):
    pytest.importorskip("amqp_serialization")

    if pure_python:
        os.environ['PYAMQP_DUMPS_SKIP_SPEEDUPS'] = "True"
    format = b'bobBlLbsbSx' * size_multipler
    x = dumps(format, [
        True, 32, False, 3415, 4513134, 13241923419,
        True, b'thequickbrownfox', False, 'jumpsoverthelazydog',
        b'thequick\xff'
    ] * size_multipler)
    benchmark(loads, format, x)
