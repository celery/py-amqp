from serialization cimport GenericContent

cdef class Message(GenericContent):
    cdef public object channel
    cdef public object delivery_info
