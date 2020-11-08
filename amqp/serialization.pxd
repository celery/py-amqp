# cython: language_level=3
import cython

from amqp.utils cimport bytes_to_str as pstr_t
from amqp.utils cimport str_to_bytes


cdef int _flushbits(list bits, write)

# Does not raise FrameSyntaxError due performance reasons
@cython.locals(blen=cython.int, limit=cython.int, keylen=cython.int, tlen=cython.int, alen=cython.int, blen=cython.int, slen=cython.int, d=cython.int)
cpdef tuple _read_item(buf, int offset)

# Does not raise FrameSyntaxError due performance reasons
@cython.locals(bitcount=cython.int, bits=cython.int, tlen=cython.int, limit=cython.int, slen=cython.int, keylen=cython.int)
cpdef tuple loads(format, buf, int offset)

@cython.locals(bitcount=cython.int, shift=cython.int)
cpdef dumps(format, values)

# Does not raise FrameSyntaxError due performance reasons
cpdef int _write_table(d, write, bits) except -1

# Does not raise FrameSyntaxError due performance reasons
cdef int _write_array(l, write, bits) except -1

@cython.locals(slen=cython.int, flags=cython.ushort)
cdef tuple decode_properties_basic(buf, int offset)

cdef int _write_item(v, write, bits) except -1

cdef dict PROPERTY_CLASSES

cdef class GenericContent:
    cdef public object frame_method
    cdef public object frame_args
    cdef public object body
    cdef list _pending_chunks
    cdef public int body_received
    cdef public int body_size
    cdef public bint ready
    cdef public dict properties

    @cython.locals(shift=cython.int, flag_bits=cython.int, flags=list)
    cpdef bytes _serialize_properties(self)

    cdef int _load_properties(self, class_id, buf, offset)
