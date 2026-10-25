//! Small JSON value/parser for updating the crate's own saved observations.
use std::collections::BTreeMap;
use std::io;

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Number(f64),
    String(String),
    Array(Vec<Value>),
    Object(BTreeMap<String, Value>),
}

impl Value {
    pub fn parse(text: &str) -> io::Result<Self> {
        struct Parser<'a> {
            bytes: &'a [u8],
            pos: usize,
        }
        impl Parser<'_> {
            fn whitespace(&mut self) {
                while self
                    .bytes
                    .get(self.pos)
                    .is_some_and(u8::is_ascii_whitespace)
                {
                    self.pos += 1;
                }
            }
            fn value(&mut self) -> Option<Value> {
                self.whitespace();
                let first = *self.bytes.get(self.pos)?;
                self.pos += 1;
                match first {
                    b'n' if self.literal(b"ull") => Some(Value::Null),
                    b't' if self.literal(b"rue") => Some(Value::Bool(true)),
                    b'f' if self.literal(b"alse") => Some(Value::Bool(false)),
                    b'"' => self.string().map(Value::String),
                    b'[' => {
                        let mut values = Vec::new();
                        self.whitespace();
                        if self.bytes.get(self.pos) == Some(&b']') {
                            self.pos += 1;
                            return Some(Value::Array(values));
                        }
                        loop {
                            values.push(self.value()?);
                            self.whitespace();
                            let c = *self.bytes.get(self.pos)?;
                            self.pos += 1;
                            match c {
                                b']' => break,
                                b',' => (),
                                _ => return None,
                            }
                        }
                        Some(Value::Array(values))
                    }
                    b'{' => {
                        let mut values = BTreeMap::new();
                        self.whitespace();
                        if self.bytes.get(self.pos) == Some(&b'}') {
                            self.pos += 1;
                            return Some(Value::Object(values));
                        }
                        loop {
                            self.whitespace();
                            if *self.bytes.get(self.pos)? != b'"' {
                                return None;
                            }
                            self.pos += 1;
                            let key = self.string()?;
                            self.whitespace();
                            if *self.bytes.get(self.pos)? != b':' {
                                return None;
                            }
                            self.pos += 1;
                            if values.insert(key, self.value()?).is_some() {
                                return None;
                            }
                            self.whitespace();
                            let c = *self.bytes.get(self.pos)?;
                            self.pos += 1;
                            match c {
                                b'}' => break,
                                b',' => (),
                                _ => return None,
                            }
                        }
                        Some(Value::Object(values))
                    }
                    b'-' | b'0'..=b'9' => {
                        let start = self.pos - 1;
                        while self.bytes.get(self.pos).is_some_and(|c| {
                            matches!(c, b'0'..=b'9' | b'.' | b'e' | b'E' | b'+' | b'-')
                        }) {
                            self.pos += 1;
                        }
                        let number = std::str::from_utf8(&self.bytes[start..self.pos])
                            .ok()?
                            .parse::<f64>()
                            .ok()?;
                        number.is_finite().then_some(Value::Number(number))
                    }
                    _ => None,
                }
            }
            fn literal(&mut self, rest: &[u8]) -> bool {
                if self.bytes.get(self.pos..self.pos + rest.len()) != Some(rest) {
                    return false;
                }
                self.pos += rest.len();
                true
            }
            fn string(&mut self) -> Option<String> {
                let mut out = Vec::new();
                loop {
                    let c = *self.bytes.get(self.pos)?;
                    self.pos += 1;
                    match c {
                        b'"' => return String::from_utf8(out).ok(),
                        b'\\' => {
                            let escape = *self.bytes.get(self.pos)?;
                            self.pos += 1;
                            match escape {
                                b'"' | b'\\' | b'/' => out.push(escape),
                                b'n' => out.push(b'\n'),
                                b'r' => out.push(b'\r'),
                                b't' => out.push(b'\t'),
                                b'b' => out.push(8),
                                b'f' => out.push(12),
                                b'u' => {
                                    let hex = std::str::from_utf8(
                                        self.bytes.get(self.pos..self.pos + 4)?,
                                    )
                                    .ok()?;
                                    let code = u32::from_str_radix(hex, 16).ok()?;
                                    self.pos += 4;
                                    let character = char::from_u32(code)?;
                                    out.extend_from_slice(
                                        character.encode_utf8(&mut [0; 4]).as_bytes(),
                                    );
                                }
                                _ => return None,
                            }
                        }
                        0..=31 => return None,
                        _ => out.push(c),
                    }
                }
            }
        }
        let mut parser = Parser {
            bytes: text.as_bytes(),
            pos: 0,
        };
        let result = parser
            .value()
            .ok_or_else(|| io::Error::other("invalid saved JSON"))?;
        parser.whitespace();
        if parser.pos != parser.bytes.len() {
            return Err(io::Error::other("trailing JSON input"));
        }
        Ok(result)
    }
    pub fn get(&self, key: &str) -> &Value {
        match self {
            Self::Object(values) => values.get(key).unwrap_or(&Self::Null),
            _ => &Self::Null,
        }
    }
    pub fn set(&mut self, key: &str, value: Value) {
        if let Self::Object(values) = self {
            values.insert(key.to_string(), value);
        }
    }
    pub fn number(&self) -> Option<f64> {
        if let Self::Number(v) = self {
            Some(*v)
        } else {
            None
        }
    }
    pub fn string(&self) -> Option<&str> {
        if let Self::String(v) = self {
            Some(v)
        } else {
            None
        }
    }
    pub fn array(&self) -> &[Value] {
        if let Self::Array(v) = self {
            v
        } else {
            &[]
        }
    }
    pub fn array_mut(&mut self) -> Option<&mut Vec<Value>> {
        if let Self::Array(v) = self {
            Some(v)
        } else {
            None
        }
    }
    pub fn object_array_mut(&mut self, key: &str) -> Option<&mut Vec<Value>> {
        if let Self::Object(values) = self {
            values.get_mut(key)?.array_mut()
        } else {
            None
        }
    }
    pub fn encode(&self) -> String {
        match self {
            Self::Null => "null".into(),
            Self::Bool(v) => v.to_string(),
            Self::Number(v) => v.to_string(),
            Self::String(v) => crate::extract::quoted(v),
            Self::Array(values) => format!(
                "[{}]",
                values
                    .iter()
                    .map(Self::encode)
                    .collect::<Vec<_>>()
                    .join(",")
            ),
            Self::Object(values) => format!(
                "{{{}}}",
                values
                    .iter()
                    .map(|(k, v)| format!("{}:{}", crate::extract::quoted(k), v.encode()))
                    .collect::<Vec<_>>()
                    .join(",\n")
            ),
        }
    }
}

impl From<&str> for Value {
    fn from(value: &str) -> Self {
        Self::String(value.into())
    }
}
impl From<f64> for Value {
    fn from(value: f64) -> Self {
        Self::Number(value)
    }
}
impl From<bool> for Value {
    fn from(value: bool) -> Self {
        Self::Bool(value)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn saved_json_roundtrip_and_rejections() {
        // Declared synthetic JSON, including escaped Unicode and null values.
        let text = "{\"a\":[1,null,true,\"é\\n\\u0041\"],\"b\":-0.2}";
        let value = Value::parse(text).unwrap();
        assert_eq!(Value::parse(&value.encode()).unwrap(), value);
        for invalid in ["{", "[1,]", "{\"x\":1,\"x\":2}", "null garbage"] {
            assert!(Value::parse(invalid).is_err());
        }
    }
}
