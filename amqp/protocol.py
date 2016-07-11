from typing import NamedTuple


queue_declare_ok_t = NamedTuple('queue_declare_ok_t', [
    ('queue', str),
    ('message_count', int),
    ('consumer_count', int),
])

basic_return_t = NamedTuple('basic_return_t', [
    ('reply_code', int),
    ('reply_text', str),
    ('exchange', str),
    ('routing_key', str),
    ('message', str),
])
