import cython

cdef int _flushbits(list bits, write)

@cython.locals(blen=cython.int, limit=cython.int, keylen=cython.int, tlen=cython.int, alen=cython.int, blen=cython.int, slen=cython.int, d=cython.int)
cpdef tuple _read_item(buf, int offset)

@cython.locals(bitcount=cython.int, bits=cython.int, tlen=cython.int, limit=cython.int, slen=cython.int, keylen=cython.int)
cpdef tuple loads(format, buf, int offset)

@cython.locals(bitcount=cython.int, shift=cython.int)
cpdef dumps(format, values)

cpdef void _write_table(d, write, bits)

cdef void _write_array(l, write, bits)

@cython.locals(slen=cython.int, flags=cython.ushort)
cdef tuple decode_properties_basic(buf, int offset)
