import cython
from .serialization cimport loads, dumps

cdef object AMQP_LOGGER
cdef object IGNORED_METHOD_DURING_CHANNEL_CLOSE

