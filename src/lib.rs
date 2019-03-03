#[macro_use]
extern crate lazy_static;
extern crate byteorder;
extern crate pyo3;

use byteorder::{BigEndian, ReadBytesExt};
use pyo3::prelude::*;
use pyo3::types::*;
use pyo3::wrap_pyfunction;
use pyo3::{IntoPy, Py};
use std::io::{self, Cursor, Read, Seek, SeekFrom};
use pyo3::import_exception;

// Since this module is being currently imported we assume the GIL is acquired.
// If it isn't, this module is the least of our problems
lazy_static! {
    static ref DATETIME_MODULE: &'static PyModule =
        { unsafe { Python::assume_gil_acquired().import("datetime").unwrap() } };
    static ref DATETIME_CLASS: PyObject = {
        DATETIME_MODULE
            .get("datetime")
            .unwrap()
            .to_object(unsafe { Python::assume_gil_acquired() })
    };
    static ref DECIMAL_MODULE: &'static PyModule =
        { unsafe { Python::assume_gil_acquired().import("decimal").unwrap() } };
    static ref DECIMAL_CLASS: PyObject = {
        DECIMAL_MODULE
            .get("Decimal")
            .unwrap()
            .to_object(unsafe { Python::assume_gil_acquired() })
    };
}

import_exception!(amqp, FrameSyntaxError);

struct AMQPDeserializer<'deserializer_l> {
    py: &'deserializer_l Python<'deserializer_l>,
    format: &'deserializer_l str,
    cursor: Cursor<&'deserializer_l [u8]>,
    bitcount: u8,
    bits: u8,
    buffer_length: u64,
}

impl<'deserializer_l> AMQPDeserializer<'deserializer_l> {
    fn new(
        py: &'deserializer_l Python<'deserializer_l>,
        format: &'deserializer_l str,
        buf: &'deserializer_l [u8],
        offset: u64,
    ) -> io::Result<AMQPDeserializer<'deserializer_l>> {
        let mut cursor = Cursor::new(buf);
        cursor.seek(SeekFrom::Start(offset))?;

        Ok(AMQPDeserializer {
            py: &py,
            format: format,
            cursor,
            bitcount: 0,
            bits: 0,
            buffer_length: buf.len() as u64,
        })
    }

    #[inline]
    fn read_bitmap(&mut self, values: &PyList) -> io::Result<()> {
        if self.bitcount == 0 {
            self.bits = self.cursor.read_u8()?;
            self.bitcount = 8;
        }

        values.append((self.bits & 1) == 1)?;
        self.bits >>= 1;
        self.bitcount -= 1;
        Ok(())
    }

    #[inline(always)]
    fn reset_bitmap(&mut self) {
        self.bitcount = 0;
        self.bits = 0;
    }

    #[inline]
    fn read_short_string(&mut self) -> io::Result<String> {
        // TODO: According to 4.2.5.3 in AMQP 0.9 specification small strings are
        // limited to 255 octets, which is something we can use to optimize allocation

        let length = self.cursor.read_u8()?;
        let expected_position = self.cursor.position() + length as u64;
        return if expected_position > self.buffer_length {
            let length = (expected_position - self.buffer_length) as usize;
            let mut buffer = vec![0; length];
            self.cursor.read_to_end(&mut buffer)?;

            Ok(String::from(String::from_utf8_lossy(buffer.as_slice())))
        } else {
            let mut buffer = vec![0; length as usize];
            self.cursor.read_exact(&mut buffer)?;

            Ok(String::from(String::from_utf8_lossy(buffer.as_slice())))
        };
    }

    #[inline]
    fn read_long_string(&mut self) -> io::Result<String> {
        let length = self.cursor.read_u32::<BigEndian>()?;
        let expected_position = self.cursor.position() + length as u64;
        return if expected_position > self.buffer_length {
            let length = (expected_position - self.buffer_length) as usize;
            let mut buffer = vec![0; length];
            self.cursor.read_to_end(&mut buffer)?;

            Ok(String::from(String::from_utf8_lossy(buffer.as_slice())))
        } else {
            let mut buffer = vec![0; length as usize];
            self.cursor.read_exact(&mut buffer)?;

            Ok(String::from(String::from_utf8_lossy(buffer.as_slice())))
        };
    }

    #[inline]
    fn read_bytes_array(&mut self) -> io::Result<Py<PyBytes>> {
        let length = self.cursor.read_u32::<BigEndian>()?;
        let expected_position = self.cursor.position() + length as u64;
        return if expected_position > self.buffer_length {
            let length = (expected_position - self.buffer_length) as usize;
            let mut buffer = vec![0; length];
            self.cursor.read_to_end(&mut buffer)?;

            Ok(PyBytes::new(*self.py, buffer.as_slice()))
        } else {
            let mut buffer = vec![0; length as usize];
            self.cursor.read_exact(&mut buffer)?;

            Ok(PyBytes::new(*self.py, buffer.as_slice()))
        };
    }

    #[inline]
    fn read_timestamp(&mut self) -> io::Result<PyObject> {
        let timestamp = self.cursor.read_u64::<BigEndian>()?;;
        Ok(DATETIME_CLASS.call_method(*self.py, "utcfromtimestamp", (timestamp,), None)?)
    }

    #[inline]
    fn read_decimal(&mut self) -> io::Result<PyObject> {
        let _d = self.cursor.read_u8()?;
        let _n = self.cursor.read_i32::<BigEndian>()?;

        let n = DECIMAL_CLASS.call(*self.py, (_n,), None)?;
        let d = DECIMAL_CLASS.call(*self.py, (10_i32.pow(_d.into()),), None)?;

        let val = n.call_method(*self.py, "__truediv__", (d,), None)?;

        Ok(val)
    }

    #[inline]
    fn read_item(&mut self) -> PyResult<PyObject> {
        let ftype = self.cursor.read_u8()? as char;
        match ftype {
            'S' => {
                let pystring = self.read_long_string()?;
                Ok(PyUnicode::new(*self.py, &pystring).into())
            }
            's' => {
                let pystring = self.read_short_string()?;
                Ok(PyUnicode::new(*self.py, &pystring).into())
            }
            'x' => {
                let pybytes = self.read_bytes_array()?;
                Ok(pybytes.into())
            }
            'b' => Ok(self.cursor.read_u8()?.to_object(*self.py)),
            'B' => Ok(self.cursor.read_i8()?.to_object(*self.py)),
            'U' => Ok(self.cursor.read_i16::<BigEndian>()?.to_object(*self.py)),
            'u' => Ok(self.cursor.read_u16::<BigEndian>()?.to_object(*self.py)),
            'I' => Ok(self.cursor.read_i32::<BigEndian>()?.to_object(*self.py)),
            'i' => Ok(self.cursor.read_u32::<BigEndian>()?.to_object(*self.py)),
            'L' => Ok(self.cursor.read_i64::<BigEndian>()?.to_object(*self.py)),
            'l' => Ok(self.cursor.read_u64::<BigEndian>()?.to_object(*self.py)),
            'f' => Ok(self.cursor.read_f32::<BigEndian>()?.to_object(*self.py)),
            'd' => Ok(self.cursor.read_f64::<BigEndian>()?.to_object(*self.py)),
            'D' => Ok(self.read_decimal()?),
            'F' => Ok(self.read_frame()?.into()),
            'A' => Ok(self.read_array()?.into()),
            't' => Ok((self.cursor.read_u8()? == 1).to_object(*self.py)),
            'T' => Ok(self.read_timestamp()?.into()),
            'V' => Ok(self.py.None()),
            _ => Err(FrameSyntaxError::py_err(format!("Unknown value in table: '{}'", ftype as u8)).into()),
        }
    }

    #[inline]
    fn read_frame(&mut self) -> io::Result<&PyDict> {
        let table = PyDict::new(*self.py);
        let table_length = self.cursor.read_u32::<BigEndian>()? as u64;
        let limit = self.cursor.position() + table_length;
        while self.cursor.position() < limit {
            let key = self.read_short_string()?;
            table.set_item(key, self.read_item()?)?
        }
        Ok(table)
    }

    #[inline]
    fn read_array(&mut self) -> io::Result<&PyList> {
        let array = PyList::empty(*self.py);
        let array_length = self.cursor.read_u32::<BigEndian>()? as u64;
        let limit = self.cursor.position() + array_length;
        while self.cursor.position() < limit {
            array.append(self.read_item()?)?;
        }
        Ok(array)
    }

    fn deserialize(&mut self) -> PyResult<(&'deserializer_l PyList, u64)> {
        // TODO: Figure out why
        // let values = PyList::with_capacity(*self.py, self.format.len());
        // crashes
        let values = PyList::empty(*self.py);

        for p in self.format.chars() {
            match p {
                'b' => {
                    self.read_bitmap(values)?;
                }
                'o' => {
                    self.reset_bitmap();
                    values.append(self.cursor.read_u8()?)?;
                }
                'B' => {
                    self.reset_bitmap();
                    values.append(self.cursor.read_u16::<BigEndian>()?)?;
                }
                'l' => {
                    self.reset_bitmap();
                    values.append(self.cursor.read_u32::<BigEndian>()?)?;
                }
                'L' => {
                    self.reset_bitmap();
                    values.append(self.cursor.read_u64::<BigEndian>()?)?;
                }
                'f' => {
                    self.reset_bitmap();
                    values.append(self.cursor.read_f32::<BigEndian>()?)?;
                }
                's' => {
                    self.reset_bitmap();
                    values.append(self.read_short_string()?)?;
                }
                'S' => {
                    self.reset_bitmap();
                    values.append(self.read_long_string()?)?;
                }
                'x' => {
                    values.append(self.read_bytes_array()?)?;
                }
                'T' => {
                    self.reset_bitmap();
                    values.append(self.read_timestamp()?)?;
                }
                'F' => {
                    self.reset_bitmap();
                    values.append(self.read_frame()?)?;
                }
                'A' => {
                    self.reset_bitmap();
                    values.append(self.read_array()?)?;
                }
                _ => {
                    return Err(FrameSyntaxError::py_err(format!("Table type '{}' not handled by amqp.", p)).into());
                }
            }
        }

        Ok((values, self.cursor.position()))
    }
}

#[pyfunction]
fn loads<'deserializer_l>(
    py: pyo3::Python<'deserializer_l>,
    format: &str,
    buf: &PyBytes,
    offset: u64,
) -> PyResult<Py<PyTuple>> {
    let mut deserializer = AMQPDeserializer::new(&py, &format, buf.as_bytes(), offset)?;
    Ok(deserializer.deserialize()?.into_py(py))
}

#[pymodule]
fn amqp_serialization(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_wrapped(wrap_pyfunction!(loads))?;

    Ok(())
}
