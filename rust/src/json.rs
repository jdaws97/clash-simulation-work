//! Minimal JSON reader (std only; no crates can be downloaded here). Numbers
//! keep Python's `repr` round trip: `str::parse::<f64>` is correctly rounded,
//! and Python's json.dumps writes floats with repr. Object keys keep file order.

use std::fmt;

#[derive(Clone, Debug, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Num(f64),
    Str(String),
    Arr(Vec<Json>),
    Obj(Vec<(String, Json)>),
}

#[derive(Debug)]
pub struct JsonError {
    pub at: usize,
    pub message: String,
}

impl fmt::Display for JsonError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "JSON error at byte {}: {}", self.at, self.message)
    }
}

pub fn parse(text: &str) -> Result<Json, JsonError> {
    let mut p = Parser { s: text.as_bytes(), i: 0 };
    let value = p.value()?;
    p.ws();
    if p.i != p.s.len() {
        return Err(p.err("trailing characters"));
    }
    Ok(value)
}

impl Json {
    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Obj(items) => items.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }
    /// Field that must exist (panics with the key name: inputs come from our own exporter).
    pub fn at(&self, key: &str) -> &Json {
        self.get(key).unwrap_or_else(|| panic!("missing JSON field {key:?}"))
    }
    pub fn f64(&self) -> f64 {
        match self {
            Json::Num(v) => *v,
            Json::Bool(b) => f64::from(u8::from(*b)),
            other => panic!("expected a number, got {other:?}"),
        }
    }
    pub fn opt_f64(&self) -> Option<f64> {
        match self {
            Json::Null => None,
            other => Some(other.f64()),
        }
    }
    pub fn i64(&self) -> i64 {
        let v = self.f64();
        assert!(v.fract() == 0.0, "expected an integer, got {v}");
        v as i64
    }
    pub fn usize(&self) -> usize {
        let v = self.i64();
        assert!(v >= 0, "expected a nonnegative integer, got {v}");
        v as usize
    }
    pub fn bool(&self) -> bool {
        match self {
            Json::Bool(b) => *b,
            Json::Num(v) => *v != 0.0,
            Json::Null => false,
            other => panic!("expected a bool, got {other:?}"),
        }
    }
    pub fn str(&self) -> &str {
        match self {
            Json::Str(s) => s,
            other => panic!("expected a string, got {other:?}"),
        }
    }
    pub fn opt_str(&self) -> Option<&str> {
        match self {
            Json::Null => None,
            other => Some(other.str()),
        }
    }
    pub fn arr(&self) -> &[Json] {
        match self {
            Json::Arr(items) => items,
            other => panic!("expected an array, got {other:?}"),
        }
    }
    pub fn obj(&self) -> &[(String, Json)] {
        match self {
            Json::Obj(items) => items,
            other => panic!("expected an object, got {other:?}"),
        }
    }
    pub fn is_null(&self) -> bool {
        matches!(self, Json::Null)
    }
}

struct Parser<'a> {
    s: &'a [u8],
    i: usize,
}

impl Parser<'_> {
    fn err(&self, message: &str) -> JsonError {
        JsonError { at: self.i, message: message.to_owned() }
    }

    fn ws(&mut self) {
        while self.i < self.s.len() && matches!(self.s[self.i], b' ' | b'\t' | b'\n' | b'\r') {
            self.i += 1;
        }
    }

    fn eat(&mut self, lit: &str) -> bool {
        if self.s[self.i..].starts_with(lit.as_bytes()) {
            self.i += lit.len();
            true
        } else {
            false
        }
    }

    fn value(&mut self) -> Result<Json, JsonError> {
        self.ws();
        let Some(&c) = self.s.get(self.i) else {
            return Err(self.err("unexpected end"));
        };
        match c {
            b'{' => {
                self.i += 1;
                let mut items = Vec::new();
                self.ws();
                if self.eat("}") {
                    return Ok(Json::Obj(items));
                }
                loop {
                    self.ws();
                    let key = self.string()?;
                    self.ws();
                    if !self.eat(":") {
                        return Err(self.err("expected ':'"));
                    }
                    items.push((key, self.value()?));
                    self.ws();
                    if self.eat(",") {
                        continue;
                    }
                    if self.eat("}") {
                        return Ok(Json::Obj(items));
                    }
                    return Err(self.err("expected ',' or '}'"));
                }
            }
            b'[' => {
                self.i += 1;
                let mut items = Vec::new();
                self.ws();
                if self.eat("]") {
                    return Ok(Json::Arr(items));
                }
                loop {
                    items.push(self.value()?);
                    self.ws();
                    if self.eat(",") {
                        continue;
                    }
                    if self.eat("]") {
                        return Ok(Json::Arr(items));
                    }
                    return Err(self.err("expected ',' or ']'"));
                }
            }
            b'"' => Ok(Json::Str(self.string()?)),
            b't' if self.eat("true") => Ok(Json::Bool(true)),
            b'f' if self.eat("false") => Ok(Json::Bool(false)),
            b'n' if self.eat("null") => Ok(Json::Null),
            // Python's json.dumps writes these for non-finite floats.
            b'N' if self.eat("NaN") => Ok(Json::Num(f64::NAN)),
            b'I' if self.eat("Infinity") => Ok(Json::Num(f64::INFINITY)),
            b'-' if self.eat("-Infinity") => Ok(Json::Num(f64::NEG_INFINITY)),
            _ => self.number(),
        }
    }

    fn number(&mut self) -> Result<Json, JsonError> {
        let start = self.i;
        while self.i < self.s.len() && matches!(self.s[self.i], b'-' | b'+' | b'.' | b'e' | b'E' | b'0'..=b'9') {
            self.i += 1;
        }
        let text = std::str::from_utf8(&self.s[start..self.i]).map_err(|_| self.err("bad number"))?;
        text.parse::<f64>().map(Json::Num).map_err(|_| self.err("bad number"))
    }

    fn string(&mut self) -> Result<String, JsonError> {
        if !self.eat("\"") {
            return Err(self.err("expected a string"));
        }
        let mut out = String::new();
        loop {
            let Some(&c) = self.s.get(self.i) else {
                return Err(self.err("unterminated string"));
            };
            self.i += 1;
            match c {
                b'"' => return Ok(out),
                b'\\' => {
                    let Some(&e) = self.s.get(self.i) else {
                        return Err(self.err("bad escape"));
                    };
                    self.i += 1;
                    match e {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{8}'),
                        b'f' => out.push('\u{c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let mut code = self.hex4()?;
                            if (0xd800..0xdc00).contains(&code) && self.eat("\\u") {
                                let low = self.hex4()?;
                                code = 0x10000 + ((code - 0xd800) << 10) + (low - 0xdc00);
                            }
                            out.push(char::from_u32(code).unwrap_or('\u{fffd}'));
                        }
                        _ => return Err(self.err("bad escape")),
                    }
                }
                _ => {
                    // copy one UTF-8 sequence
                    let start = self.i - 1;
                    let len = match c {
                        0x00..=0x7f => 1,
                        0xc0..=0xdf => 2,
                        0xe0..=0xef => 3,
                        _ => 4,
                    };
                    self.i = start + len;
                    out.push_str(std::str::from_utf8(&self.s[start..self.i]).map_err(|_| self.err("bad UTF-8"))?);
                }
            }
        }
    }

    fn hex4(&mut self) -> Result<u32, JsonError> {
        let text = self.s.get(self.i..self.i + 4).ok_or_else(|| self.err("bad \\u escape"))?;
        let code = u32::from_str_radix(std::str::from_utf8(text).unwrap_or("x"), 16)
            .map_err(|_| self.err("bad \\u escape"))?;
        self.i += 4;
        Ok(code)
    }
}
