//! Ordered JSON and reproducible search randomness; battle RNG stays in pyrandom.

use std::path::Path;

use crate::json::{self, Json};

pub fn object(entries: impl IntoIterator<Item = (&'static str, Json)>) -> Json {
    Json::Obj(entries.into_iter().map(|(k, v)| (k.to_owned(), v)).collect())
}

pub fn read(path: &Path) -> Result<Json, String> {
    let source = std::fs::read_to_string(path)
        .map_err(|error| format!("{}: {error}", path.display()))?;
    json::parse(source.trim_start_matches('\u{feff}')).map_err(|error| error.to_string())
}

pub fn encode(value: &Json) -> String {
    match value {
        Json::Null => "null".to_owned(),
        Json::Bool(value) => value.to_string(),
        Json::Num(value) => {
            assert!(value.is_finite(), "nonfinite report value");
            crate::trace::py_float_repr(*value)
        }
        Json::Str(value) => {
            let mut out = String::from("\"");
            for ch in value.chars() {
                match ch {
                    '"' => out.push_str("\\\""),
                    '\\' => out.push_str("\\\\"),
                    '\n' => out.push_str("\\n"),
                    '\r' => out.push_str("\\r"),
                    '\t' => out.push_str("\\t"),
                    ch if ch < ' ' => out.push_str(&format!("\\u{:04x}", ch as u32)),
                    ch => out.push(ch),
                }
            }
            out.push('"');
            out
        }
        Json::Arr(values) => format!("[{}]", values.iter().map(encode).collect::<Vec<_>>().join(",")),
        Json::Obj(values) => format!(
            "{{{}}}",
            values.iter().map(|(key, value)| format!("{}:{}", encode(&Json::Str(key.clone())), encode(value)))
                .collect::<Vec<_>>().join(",")
        ),
    }
}

pub fn write(path: &Path, value: &Json) -> Result<(), String> {
    std::fs::write(path, format!("{}\n", encode(value)))
        .map_err(|error| format!("{}: {error}", path.display()))
}

pub fn string(value: impl Into<String>) -> Json {
    Json::Str(value.into())
}

pub fn number(value: usize) -> Json {
    Json::Num(value as f64)
}

pub fn text<'a>(value: &'a Json, key: &str, default: &'a str) -> &'a str {
    value.get(key).and_then(Json::opt_str).unwrap_or(default)
}

pub fn array<'a>(value: &'a Json, key: &str) -> &'a [Json] {
    value.get(key).map_or(&[], Json::arr)
}

pub fn numeric(value: &Json, key: &str, default: f64) -> f64 {
    value.get(key).map_or(default, Json::f64)
}

pub fn hash(bytes: &[u8]) -> u64 {
    let mut value = 0xcbf29ce484222325_u64;
    for byte in bytes {
        value ^= u64::from(*byte);
        value = value.wrapping_mul(0x100000001b3);
    }
    value
}

#[derive(Clone, Debug)]
pub struct Random(pub u64);

impl Random {
    pub fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e3779b97f4a7c15);
        let mut value = self.0;
        value = (value ^ (value >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        value = (value ^ (value >> 27)).wrapping_mul(0x94d049bb133111eb);
        value ^ (value >> 31)
    }

    pub fn index(&mut self, length: usize) -> usize {
        assert!(length > 0);
        // Rejection avoids modulo bias and is independent of pointer width.
        let length = length as u64;
        let threshold = length.wrapping_neg() % length;
        loop {
            let value = self.next();
            if value >= threshold {
                return (value % length) as usize;
            }
        }
    }

    pub fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 * (1.0 / 9_007_199_254_740_992.0)
    }
}
