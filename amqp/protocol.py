"""Protocol data."""
from typing import NamedTuple


class queue_declare_ok_t(NamedTuple):
    """Tuple returned by Queue.Declare."""

    queue: str
    message_count: int
    consumer_count: int


class basic_return_t(NamedTuple):
    """Tuple provided by Basic.Return."""

    reply_code: int
    reply_text: str
    exchange: str
    routing_key: str
    message: str
