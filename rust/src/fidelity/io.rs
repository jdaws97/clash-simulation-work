//! Local wire helpers and SHA-256; no dependency on Python or network services.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use baselab_engine::json::{self, Json};

pub fn read(path: &Path) -> Result<Json, String> {
    let source =
        std::fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    json::parse(source.trim_start_matches('\u{feff}'))
        .map_err(|error| format!("{}: {error}", path.display()))
}

pub fn write(path: &Path, value: &Json) -> Result<(), String> {
    if let Some(parent) = path.parent().filter(|path| !path.as_os_str().is_empty()) {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    std::fs::write(path, format!("{}\n", encode(value)))
        .map_err(|error| format!("{}: {error}", path.display()))
}

pub fn encode(value: &Json) -> String {
    baselab_engine::compile_cli::to_json(value)
}

pub fn obj(fields: impl IntoIterator<Item = (impl Into<String>, Json)>) -> Json {
    Json::Obj(
        fields
            .into_iter()
            .map(|(key, value)| (key.into(), value))
            .collect(),
    )
}

pub fn arr(values: impl IntoIterator<Item = Json>) -> Json {
    Json::Arr(values.into_iter().collect())
}

pub fn num(value: impl Into<f64>) -> Json {
    Json::Num(value.into())
}

pub fn string(value: impl Into<String>) -> Json {
    Json::Str(value.into())
}

pub fn list<'a>(value: &'a Json, key: &str) -> &'a [Json] {
    match value.get(key) {
        Some(Json::Arr(values)) => values,
        _ => &[],
    }
}

pub fn text<'a>(value: &'a Json, key: &str, fallback: &'a str) -> &'a str {
    match value.get(key) {
        Some(Json::Str(value)) => value,
        _ => fallback,
    }
}

pub fn number(value: &Json, key: &str, fallback: f64) -> f64 {
    match value.get(key) {
        Some(Json::Num(value)) => *value,
        _ => fallback,
    }
}

pub fn put(value: &mut Json, key: &str, item: Json) {
    let Json::Obj(fields) = value else {
        panic!("internal fidelity object expected");
    };
    if let Some((_, old)) = fields.iter_mut().find(|(name, _)| name == key) {
        *old = item;
    } else {
        fields.push((key.to_owned(), item));
    }
}

pub fn remove(value: &mut Json, key: &str) {
    if let Json::Obj(fields) = value {
        fields.retain(|(name, _)| name != key);
    }
}

pub fn count_map(values: &BTreeMap<String, usize>) -> Json {
    obj(values
        .iter()
        .map(|(key, value)| (key.clone(), num(*value as f64))))
}

pub fn resolve(root: &Path, path: &str) -> PathBuf {
    // Frozen Windows reports use backslashes even when consumed on Linux.
    let normalized = path.replace('\\', "/");
    let path = Path::new(&normalized);
    if path.is_absolute() {
        path.to_owned()
    } else {
        root.join(path)
    }
}

pub fn file_hash(path: &Path) -> Result<String, String> {
    std::fs::read(path)
        .map(|bytes| sha256(&bytes))
        .map_err(|error| format!("{}: {error}", path.display()))
}

pub fn sha256(bytes: &[u8]) -> String {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4,
        0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe,
        0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f,
        0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
        0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116,
        0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut state: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab,
        0x5be0cd19,
    ];
    let mut padded = bytes.to_vec();
    padded.push(0x80);
    while padded.len() % 64 != 56 {
        padded.push(0);
    }
    padded.extend_from_slice(&((bytes.len() as u64) * 8).to_be_bytes());
    for chunk in padded.chunks_exact(64) {
        let mut words = [0_u32; 64];
        for (word, bytes) in words.iter_mut().zip(chunk.chunks_exact(4)) {
            *word = u32::from_be_bytes(bytes.try_into().expect("four bytes"));
        }
        for i in 16..64 {
            let x = words[i - 15];
            let y = words[i - 2];
            words[i] = words[i - 16]
                .wrapping_add(x.rotate_right(7) ^ x.rotate_right(18) ^ (x >> 3))
                .wrapping_add(words[i - 7])
                .wrapping_add(y.rotate_right(17) ^ y.rotate_right(19) ^ (y >> 10));
        }
        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut h] = state;
        for i in 0..64 {
            let first = h
                .wrapping_add(e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25))
                .wrapping_add((e & f) ^ (!e & g))
                .wrapping_add(K[i])
                .wrapping_add(words[i]);
            let second = (a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22))
                .wrapping_add((a & b) ^ (a & c) ^ (b & c));
            h = g;
            g = f;
            f = e;
            e = d.wrapping_add(first);
            d = c;
            c = b;
            b = a;
            a = first.wrapping_add(second);
        }
        for (old, next) in state.iter_mut().zip([a, b, c, d, e, f, g, h]) {
            *old = old.wrapping_add(next);
        }
    }
    state.iter().map(|word| format!("{word:08x}")).collect()
}

/// Python json.dumps(..., ensure_ascii=True) string representation.
pub fn ascii_string(value: &str) -> String {
    let mut out = String::from("\"");
    for unit in value.encode_utf16() {
        match unit {
            8 => out.push_str("\\b"),
            9 => out.push_str("\\t"),
            10 => out.push_str("\\n"),
            12 => out.push_str("\\f"),
            13 => out.push_str("\\r"),
            34 => out.push_str("\\\""),
            92 => out.push_str("\\\\"),
            32..=126 => out.push(char::from_u32(unit as u32).expect("ASCII")),
            _ => out.push_str(&format!("\\u{unit:04x}")),
        }
    }
    out.push('"');
    out
}

/// Canonical snapshot bytes preserve integer versus float tokens, unlike Json's
/// intentionally f64-only runtime representation. Sorting matches snapshot.py.
pub fn canonical(source: &str) -> Result<String, String> {
    json::parse(source).map_err(|error| error.to_string())?;
    fn value(bytes: &[u8], index: &mut usize) -> Result<String, String> {
        while bytes.get(*index).is_some_and(u8::is_ascii_whitespace) {
            *index += 1;
        }
        let start = *index;
        match bytes[*index] {
            b'{' | b'[' => {
                let object = bytes[*index] == b'{';
                let end = if object { b'}' } else { b']' };
                *index += 1;
                let mut fields = Vec::new();
                let mut values = Vec::new();
                loop {
                    while bytes.get(*index).is_some_and(u8::is_ascii_whitespace) {
                        *index += 1;
                    }
                    if bytes[*index] == end {
                        *index += 1;
                        break;
                    }
                    if object {
                        let key = value(bytes, index)?;
                        while bytes.get(*index).is_some_and(u8::is_ascii_whitespace) {
                            *index += 1;
                        }
                        *index += 1;
                        let item = value(bytes, index)?;
                        let decoded = json::parse(&key).map_err(|error| error.to_string())?;
                        fields.push((decoded.str().to_owned(), format!("{key}:{item}")));
                    } else {
                        values.push(value(bytes, index)?);
                    }
                    while bytes.get(*index).is_some_and(u8::is_ascii_whitespace) {
                        *index += 1;
                    }
                    if bytes[*index] == b',' {
                        *index += 1;
                    }
                }
                if object {
                    fields.sort_by(|left, right| left.0.cmp(&right.0));
                    Ok(format!(
                        "{{{}}}",
                        fields
                            .into_iter()
                            .map(|(_, value)| value)
                            .collect::<Vec<_>>()
                            .join(",")
                    ))
                } else {
                    Ok(format!("[{}]", values.join(",")))
                }
            }
            b'"' => {
                *index += 1;
                while bytes[*index] != b'"' {
                    if bytes[*index] == b'\\' {
                        *index += 1;
                    }
                    *index += 1;
                }
                *index += 1;
                let token = std::str::from_utf8(&bytes[start..*index])
                    .map_err(|error| error.to_string())?;
                Ok(ascii_string(
                    json::parse(token).map_err(|error| error.to_string())?.str(),
                ))
            }
            _ => {
                while bytes
                    .get(*index)
                    .is_some_and(|byte| !b",]} \n\r\t".contains(byte))
                {
                    *index += 1;
                }
                let token = std::str::from_utf8(&bytes[start..*index])
                    .map_err(|error| error.to_string())?;
                if token.contains(['.', 'e', 'E']) {
                    Ok(encode(
                        &json::parse(token).map_err(|error| error.to_string())?,
                    ))
                } else {
                    Ok(token.to_owned())
                }
            }
        }
    }
    value(source.as_bytes(), &mut 0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn standard_sha_vectors_and_python_canonicalization() {
        assert_eq!(
            sha256(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        assert_eq!(
            sha256(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        );
        assert_eq!(
            canonical("{\"z\":1.0,\"é\":2,\"a\":[true,null,\"😀\"]}").unwrap(),
            "{\"a\":[true,null,\"\\ud83d\\ude00\"],\"z\":1.0,\"\\u00e9\":2}"
        );
    }
}
