# cython: language_level=3
from .basic_message cimport Message


cdef object FRAME_OVERHEAD
cdef object _CONTENT_METHODS

cdef class Buffer:
    cdef bytearray _buf
    cdef object view
