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
use std::str::Chars;

lazy_static! {
    static ref DATETIME_MODULE: &'static PyModule = {
        unsafe { Python::assume_gil_acquired().import("datetime").unwrap() }
    };
    static ref DATETIME_CLASS: PyObject = {
        DATETIME_MODULE.get("datetime").unwrap().to_object(Python::acquire_gil().python())
    };
}

struct AMQPDeserializer<'deserializer_l> {
    py: &'deserializer_l Python<'deserializer_l>,
    format: Chars<'deserializer_l>,
    cursor: Cursor<&'deserializer_l [u8]>,
    bitcount: u8,
    bits: u8,
    buffer_length: u64,
}

impl<'deserializer_l> AMQPDeserializer<'deserializer_l> {
    fn new(
        py: &'deserializer_l Python<'deserializer_l>,
        format: &'deserializer_l String,
        buf: &'deserializer_l [u8],
        offset: u64,
    ) -> io::Result<AMQPDeserializer<'deserializer_l>> {
        let mut cursor = Cursor::new(buf);
        cursor.seek(SeekFrom::Start(offset))?;

        Ok(AMQPDeserializer {
            py: &py,
            format: format.chars(),
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
        self.reset_bitmap();

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
        }
    }
    
    #[inline]
    fn read_long_string(&mut self) -> io::Result<String> {
        self.reset_bitmap();

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
        }
    }
    
    #[inline]
    fn read_timestamp(&mut self) -> io::Result<PyObject> {
        self.reset_bitmap();
        let timestamp = self.cursor.read_u64::<BigEndian>()?;;
        Ok(DATETIME_CLASS.call_method(
            *self.py,
            "utcfromtimestamp",
            (timestamp,),
            None
        )?)
    }
    
    #[inline]
    fn read_item(&mut self) -> io::Result<PyObject> {
        let ftype = self.cursor.read_u8()? as char;
        match ftype {
            _ => Ok(self.py.None()) // TODO: Return error
        }
    }
    
    #[inline]
    fn read_frame(&mut self) -> io::Result<&PyDict> {
        self.reset_bitmap();
        Ok(PyDict::new(*self.py))
    }
    
    #[inline]
    fn read_array(&mut self) -> io::Result<&PyList> {
        self.reset_bitmap();
        let array = PyList::empty(*self.py);
        let array_length = self.cursor.read_u32::<BigEndian>()? as u64;
        let limit = self.cursor.position() + array_length;
        while self.cursor.position() < limit {
            array.append(self.read_item()?)?;
        }
        Ok(array)
    }

    fn deserialize(&mut self) -> io::Result<(&'deserializer_l PyList, u64)> {
        let values = PyList::empty(*self.py);
        
        // TODO: Figure out why the borrow checker complains when we don't clone self.format
        for p in self.format.clone() {
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
                    values.append(self.read_short_string()?)?;
                }
                'S' => {
                    values.append(self.read_long_string()?)?;
                }
                'x' => {
                    let length = self.cursor.read_u32::<BigEndian>()?;
                    let expected_position = self.cursor.position() + length as u64;
                    if expected_position > self.buffer_length {
                        let length = (expected_position - self.buffer_length) as usize;
                        let mut buffer = vec![0; length];
                        self.cursor.read_to_end(&mut buffer)?;
                        values.append(PyBytes::new(*self.py, buffer.as_slice()))?;
                    } else {
                        let mut buffer = vec![0; length as usize];
                        self.cursor.read_exact(&mut buffer)?;
                        values.append(PyBytes::new(*self.py, buffer.as_slice()))?
                    }
                },
                'T' => {
                    values.append(self.read_timestamp()?)?;
                },
                'F' => {
                    values.append(self.read_frame()?)?;
                },
                'A' => {
                    values.append(self.read_array()?)?;
                }
                _ => {
                    // TODO: Handle errors correctly
                }
            }
        }

        Ok((values, self.cursor.position()))
    }
}

#[pyfunction]
fn loads<'deserializer_l>(
    py: pyo3::Python<'deserializer_l>,
    format: String,
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
