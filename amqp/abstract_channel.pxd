# cython: language_level=3
import cython

from .serialization cimport dumps, loads


cdef object AMQP_LOGGER
cdef object IGNORED_METHOD_DURING_CHANNEL_CLOSE

