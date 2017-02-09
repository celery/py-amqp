"""AMQP Spec."""
from typing import Mapping, NamedTuple

method_sig_t = NamedTuple('method_sig_t', [
    ('major', int),
    ('minor', int),
])
method_t = NamedTuple('method_t', [
    ('method_sig', method_sig_t),
    ('args', str),
    ('content', bool),
])

MethodMapT = Mapping[method_sig_t, method_t]


def method(method_sig: method_sig_t,
           args: str = None,
           content: bool = False):
    """Create amqp method specification tuple."""
    return method_t(method_sig, args, content)


def to_method_map(*methods: method_t) -> MethodMapT:
    return {m.method_sig: m for m in methods}


class Connection:
    """AMQ Connection class."""

    CLASS_ID = 10

    Start = method_sig_t(CLASS_ID, 10)
    StartOk = method_sig_t(CLASS_ID, 11)
    Secure = method_sig_t(CLASS_ID, 20)
    SecureOk = method_sig_t(CLASS_ID, 21)
    Tune = method_sig_t(CLASS_ID, 30)
    TuneOk = method_sig_t(CLASS_ID, 31)
    Open = method_sig_t(CLASS_ID, 40)
    OpenOk = method_sig_t(CLASS_ID, 41)
    Close = method_sig_t(CLASS_ID, 50)
    CloseOk = method_sig_t(CLASS_ID, 51)
    Blocked = method_sig_t(CLASS_ID, 60)
    Unblocked = method_sig_t(CLASS_ID, 61)


class Channel:
    """AMQ Channel class."""

    CLASS_ID = 20

    Open = method_sig_t(CLASS_ID, 10)
    OpenOk = method_sig_t(CLASS_ID, 11)
    Flow = method_sig_t(CLASS_ID, 20)
    FlowOk = method_sig_t(CLASS_ID, 21)
    Close = method_sig_t(CLASS_ID, 40)
    CloseOk = method_sig_t(CLASS_ID, 41)


class Access:
    """AMQ Access class."""

    CLASS_ID = 30

    Request = method_sig_t(CLASS_ID, 10)
    RequestOk = method_sig_t(CLASS_ID, 11)


class Exchange:
    """AMQ Exchange class."""

    CLASS_ID = 40

    Declare = method_sig_t(CLASS_ID, 10)
    DeclareOk = method_sig_t(CLASS_ID, 11)
    Delete = method_sig_t(CLASS_ID, 20)
    DeleteOk = method_sig_t(CLASS_ID, 21)
    Bind = method_sig_t(CLASS_ID, 30)
    BindOk = method_sig_t(CLASS_ID, 31)
    Unbind = method_sig_t(CLASS_ID, 40)
    UnbindOk = method_sig_t(CLASS_ID, 51)


class Queue:
    """AMQ Queue class."""

    CLASS_ID = 50

    Declare = method_sig_t(CLASS_ID, 10)
    DeclareOk = method_sig_t(CLASS_ID, 11)
    Bind = method_sig_t(CLASS_ID, 20)
    BindOk = method_sig_t(CLASS_ID, 21)
    Purge = method_sig_t(CLASS_ID, 30)
    PurgeOk = method_sig_t(CLASS_ID, 31)
    Delete = method_sig_t(CLASS_ID, 40)
    DeleteOk = method_sig_t(CLASS_ID, 41)
    Unbind = method_sig_t(CLASS_ID, 50)
    UnbindOk = method_sig_t(CLASS_ID, 51)


class Basic:
    """AMQ Basic class."""

    CLASS_ID = 60

    Qos = method_sig_t(CLASS_ID, 10)
    QosOk = method_sig_t(CLASS_ID, 11)
    Consume = method_sig_t(CLASS_ID, 20)
    ConsumeOk = method_sig_t(CLASS_ID, 21)
    Cancel = method_sig_t(CLASS_ID, 30)
    CancelOk = method_sig_t(CLASS_ID, 31)
    Publish = method_sig_t(CLASS_ID, 40)
    Return = method_sig_t(CLASS_ID, 50)
    Deliver = method_sig_t(CLASS_ID, 60)
    Get = method_sig_t(CLASS_ID, 70)
    GetOk = method_sig_t(CLASS_ID, 71)
    GetEmpty = method_sig_t(CLASS_ID, 72)
    Ack = method_sig_t(CLASS_ID, 80)
    Nack = method_sig_t(CLASS_ID, 120)
    Reject = method_sig_t(CLASS_ID, 90)
    RecoverAsync = method_sig_t(CLASS_ID, 100)
    Recover = method_sig_t(CLASS_ID, 110)
    RecoverOk = method_sig_t(CLASS_ID, 111)


class Confirm:
    """AMQ Confirm class."""

    CLASS_ID = 85

    Select = method_sig_t(CLASS_ID, 10)
    SelectOk = method_sig_t(CLASS_ID, 11)


class Tx:
    """AMQ Tx class."""

    CLASS_ID = 90

    Select = method_sig_t(CLASS_ID, 10)
    SelectOk = method_sig_t(CLASS_ID, 11)
    Commit = method_sig_t(CLASS_ID, 20)
    CommitOk = method_sig_t(CLASS_ID, 21)
    Rollback = method_sig_t(CLASS_ID, 30)
    RollbackOk = method_sig_t(CLASS_ID, 31)
