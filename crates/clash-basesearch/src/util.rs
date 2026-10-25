use std::path::Path;

use crate::json::Json;
pub(crate) use crate::layout::json::{encode, identity, object, read, string};

pub(crate) fn num(value: usize) -> Json {
    Json::Num(value as f64)
}

pub(crate) fn fingerprint(value: &Json) -> String {
    identity(encode(value).as_bytes())
}

pub(crate) fn write(path: &Path, value: &Json) -> Result<(), String> {
    std::fs::write(path, format!("{}\n", encode(value))).map_err(|error| error.to_string())
}

pub(crate) fn field<'a>(value: &'a Json, key: &str) -> Result<&'a Json, String> {
    value.get(key).ok_or_else(|| format!("missing {key}"))
}

pub(crate) fn usize_field(value: &Json, key: &str) -> Result<usize, String> {
    match field(value, key)? {
        Json::Num(n) if n.is_finite() && *n >= 0.0 && n.fract() == 0.0 && *n < 9e15 => {
            Ok(*n as usize)
        }
        _ => Err(format!("{key} must be a nonnegative exact integer")),
    }
}

pub(crate) fn u64_string(value: &Json, key: &str) -> Result<u64, String> {
    field(value, key)?
        .opt_str()
        .ok_or_else(|| format!("{key} must be a decimal string"))?
        .parse()
        .map_err(|_| format!("invalid {key}"))
}

/// Sources are read only; private input directories are deliberately excluded.
pub(crate) fn source_identity(root: &Path) -> Result<String, String> {
    fn walk(path: &Path, paths: &mut Vec<std::path::PathBuf>) -> Result<(), String> {
        for entry in std::fs::read_dir(path).map_err(|e| e.to_string())? {
            let path = entry.map_err(|e| e.to_string())?.path();
            if path.is_dir() {
                walk(&path, paths)?;
            } else if path
                .extension()
                .is_some_and(|extension| extension == "rs" || extension == "toml")
            {
                paths.push(path);
            }
        }
        Ok(())
    }
    let mut paths = Vec::new();
    walk(&root.join("crates"), &mut paths)?;
    paths.sort();
    let mut bytes = std::fs::read(root.join("Cargo.lock")).map_err(|e| e.to_string())?;
    for path in paths {
        bytes.extend_from_slice(
            path.strip_prefix(root)
                .unwrap()
                .to_string_lossy()
                .as_bytes(),
        );
        bytes.push(0);
        bytes.extend(std::fs::read(&path).map_err(|e| e.to_string())?);
        bytes.push(0);
    }
    Ok(identity(&bytes))
}
