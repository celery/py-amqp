import cython

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
