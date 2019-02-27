extern crate byteorder;
extern crate pyo3;

use byteorder::{BigEndian, ReadBytesExt};
use pyo3::prelude::*;
use pyo3::types::*;
use pyo3::wrap_pyfunction;
use pyo3::{IntoPy, Py};

#[inline]
fn _read_large_string(buf: &[u8], offset: & mut usize, values: &PyList) {
    let slen = (&buf[*offset..]).read_u32::<BigEndian>().unwrap() as usize;
    *offset += 4;
    if *offset + slen > buf.len() {
        values.append(String::from_utf8_lossy(&buf[(*offset)..])).unwrap();
    } else {
        values.append(
            String::from_utf8_lossy(&buf[*offset..*offset + slen]),
        ).unwrap();
    }
    *offset += slen;
}

#[inline]
fn _read_small_string(buf: &[u8], offset: & mut usize, values: &PyList) {
    let slen = (&buf[*offset..]).read_u8().unwrap() as usize;
    *offset += 1;
    if *offset + slen > buf.len() {
        values.append(String::from_utf8_lossy(&buf[*offset..])).unwrap();
    } else {
        values.append(
            String::from_utf8_lossy(&buf[*offset..*offset + slen]),
        ).unwrap();
    }
    *offset += slen;
}

#[inline]
fn _read_bytes_array(py: Python, buf: &[u8], offset: & mut usize, values: &PyList) {
    let blen = (&buf[*offset..]).read_u32::<BigEndian>().unwrap() as usize;
    *offset += 4;
    if *offset + blen > buf.len() {
        values.append(PyBytes::new(py, &buf[*offset..])).unwrap();
    } else {
        values.append(PyBytes::new(
            py,
            &buf[*offset..*offset + blen],
        )).unwrap();
    }
    *offset += blen;
}

#[inline]
fn _read_float(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_f32::<BigEndian>().unwrap()).unwrap();
    *offset += 4;
}

#[inline]
fn _read_double(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_f64::<BigEndian>().unwrap()).unwrap();
    *offset += 8;
}

#[inline]
fn _read_timestamp(py: Python, buf: &[u8], offset: & mut usize, values: &PyList) {
    let datetime = py.import("datetime").unwrap();
    let locals = PyDict::new(py);
    locals
        .set_item("datetime", datetime.get("datetime").unwrap())
        .unwrap();
    let timestamp = (&buf[*offset..]).read_u64::<BigEndian>().unwrap();
    // TODO: Replace this with the code below once I figure out how to use timezones
    values.append(py.eval(
        &format!("datetime.utcfromtimestamp({})", timestamp),
        None,
        Some(&locals),
    ).unwrap()).unwrap();
    // values.append(PyDateTime::from_timestamp(py, timestamp as f64, None)?)?;
    *offset += 8
}

#[inline]
fn _read_boolean(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append(buf[*offset] != 0).unwrap();
    *offset += 1;
}

#[inline]
fn _read_short_short_int(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append(buf[*offset]).unwrap();
    *offset += 1;
}

#[inline]
fn _read_short_short_unsigned_int(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_i8().unwrap()).unwrap();
    *offset += 1;
}

#[inline]
fn _read_short_int(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_i16::<BigEndian>().unwrap()).unwrap();
    *offset += 2;
}

#[inline]
fn _read_unsigned_short_int(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_u16::<BigEndian>().unwrap()).unwrap();
    *offset += 2;
}

#[inline]
fn _read_long_int(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_i32::<BigEndian>().unwrap()).unwrap();
    *offset += 4;
}

#[inline]
fn _read_unsigned_long_int(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_u32::<BigEndian>().unwrap()).unwrap();
    *offset += 4;
}

#[inline]
fn _read_long_long_int(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_i64::<BigEndian>().unwrap()).unwrap();
    *offset += 8;
}

#[inline]
fn _read_unsigned_long_long_int(buf: &[u8], offset: & mut usize, values: &PyList) {
    values.append((&buf[*offset..]).read_u64::<BigEndian>().unwrap()).unwrap();
    *offset += 8;
}

#[inline]
fn _read_void(py: Python, values: &PyList) {
    values.append(py.None()).unwrap();
}

#[inline]
fn _read_item_list(py: Python, buf: &[u8], offset: & mut usize, values: &PyList) {
    let ftype = buf[*offset] as char;
    *offset += 1;

    match ftype {
        'S' => {
            _read_large_string(buf, offset, values);
        },
        's' => {
            _read_small_string(buf, offset, values);
        },
        'x' => {
            _read_bytes_array(py, buf, offset, values);
        },
        'b' => {
            _read_short_short_int(buf, offset, values);
        },
        'B' => {
            _read_short_short_unsigned_int(buf, offset, values);
        },
        'U' => {
            _read_short_int(buf, offset, values);
        },
        'u' => {
            _read_unsigned_short_int(buf, offset, values);
        },
        'I' => {
            _read_long_int(buf, offset, values);
        },
        'i' => {
            _read_unsigned_long_int(buf, offset, values);
        },
        'L' => {
            _read_long_long_int(buf, offset, values);
        },
        'l' => {
            _read_unsigned_long_long_int(buf, offset, values);
        },
        'f' => {
            _read_float(buf, offset, values);
        },
        'd' => {
            _read_double(buf, offset, values);
        },
        'D' => {
            // TODO: Implement decimal support
        },
        'F' => {
            _read_frame(py, buf, offset, values);
        },
        'A' => {
            _read_array(py, buf, offset, values);
        },
        't' => {
            _read_boolean(buf, offset, values);
        }
        'T' => {
            _read_timestamp(py, buf, offset, values);
        },
        'V' => {
            _read_void(py, values);
        }
        _ => {
            // TODO: Raising an exception from here segfaults.
            // Create an API that reports errors
        }
    }
}

#[inline]
fn _read_item_dict(py: Python, buf: &[u8], offset: & mut usize, values: &PyDict) {
    *offset += 1;
}

#[inline]
fn _read_array(py: Python, buf: &[u8], offset: & mut usize, values: &PyList) {
    let alen = (&buf[*offset..]).read_u32::<BigEndian>().unwrap() as usize;
    *offset += 4;
    let limit = *offset + alen;
    let val = PyList::empty(py);
    while *offset < limit {
        _read_item_list(py, buf, & mut *offset, val);
    }
    values.append(val).unwrap();
}

#[inline]
fn _read_frame(py: Python, buf: &[u8], offset: & mut usize, values: &PyList) {
    let tlen = (&buf[*offset..]).read_u32::<BigEndian>().unwrap() as usize;
    *offset += 4;
    let limit = *offset + tlen;
    let val = PyDict::new(py);
    while *offset < limit {
        _read_item_dict(py, buf, & mut *offset, val);
    }
    values.append(val).unwrap();
}

#[pyfunction]
fn loads(py: Python, format: String, buf: &PyBytes, offset: usize) -> PyResult<Py<PyTuple>> {
    let mut bitcount = 0;
    let mut bits = 0;
    let mut current_offset = offset;
    let values = PyList::empty(py);
    let buf = buf.as_bytes();

    for p in format.chars() {
        match p {
            'b' => {
                if bitcount == 0 {
                    bits = buf.get(current_offset..current_offset + 1).unwrap()[0];
                    current_offset += 1;
                }

                bitcount = 8;
                values.append((bits & 1) == 1)?;
                bits >>= 1;
                bitcount -= 1;
            }
            'o' => {
                bitcount = 0;
                bits = 0;
                values.append((&buf[current_offset..]).read_u8().unwrap())?;
                current_offset += 1;
            }
            'B' => {
                bitcount = 0;
                bits = 0;
                values.append((&buf[current_offset..]).read_u16::<BigEndian>().unwrap())?;
                current_offset += 2;
            }
            'l' => {
                bitcount = 0;
                bits = 0;
                values.append((&buf[current_offset..]).read_u32::<BigEndian>().unwrap())?;
                current_offset += 4;
            }
            'L' => {
                bitcount = 0;
                bits = 0;
                values.append((&buf[current_offset..]).read_u64::<BigEndian>().unwrap())?;
                current_offset += 8;
            }
            'f' => {
                bitcount = 0;
                bits = 0;
                _read_float(buf, & mut current_offset, values);
            }
            's' => {
                bitcount = 0;
                bits = 0;
                _read_small_string(buf, & mut current_offset, values);
            }
            'S' => {
                bitcount = 0;
                bits = 0;
                _read_large_string(buf, & mut current_offset, values);
            }
            'x' => {
                _read_bytes_array(py, buf, & mut current_offset, values);
            }
            'T' => {
                bitcount = 0;
                bits = 0;
                _read_timestamp(py, buf, & mut current_offset, values);
            },
            'F' => {
                bitcount = 0;
                bits = 0;
                _read_frame(py, buf, & mut current_offset, values);
            },
            'A' => {
                bitcount = 0;
                bits = 0;
                _read_array(py, buf, & mut current_offset, values);
            },
            _ => {
                // TODO: Once the exception type moves to rust, rewrite this
                // Or find out how to use the import_exception! macro
                let pycode = &format!("from amqp.exceptions import FrameSyntaxError;raise FrameSyntaxError('Table type {} not handled by amqp.')", p);
                py.run(pycode, None, None)?;
            }
        }
    }
    Ok((values, current_offset).into_py(py))
}

#[pymodule]
fn amqp_serialization(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_wrapped(wrap_pyfunction!(loads))?;

    Ok(())
}
