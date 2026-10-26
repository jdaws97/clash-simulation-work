use clash_data::json::{self, Json};
use clash_data::wire;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT_FILE: AtomicU64 = AtomicU64::new(0);

pub fn read(path: &Path) -> Result<Json, String> {
    wire::read(path)
}

pub fn parse(text: &str) -> Result<Json, String> {
    json::parse(text.trim_start_matches('\u{feff}')).map_err(|error| error.to_string())
}

pub fn write(path: &Path, value: &Json) -> Result<(), String> {
    atomic_write(path, format!("{}\n", wire::encode(value)).as_bytes())
}

pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let name = path
        .file_name()
        .ok_or("output needs a file name")?
        .to_string_lossy();
    let temporary = parent.join(format!(
        ".{name}.{}.{}.tmp",
        std::process::id(),
        NEXT_FILE.fetch_add(1, Ordering::Relaxed)
    ));
    let result = (|| {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
            .map_err(|e| e.to_string())?;
        file.write_all(bytes).map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())?;
        fs::rename(&temporary, path).map_err(|e| format!("{}: {e}", path.display()))
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

pub fn files(directory: &Path, extension: &str) -> Result<Vec<PathBuf>, String> {
    let mut paths = fs::read_dir(directory)
        .map_err(|e| format!("{}: {e}", directory.display()))?
        .map(|entry| entry.map(|entry| entry.path()).map_err(|e| e.to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    paths.retain(|p| p.extension().and_then(|e| e.to_str()) == Some(extension));
    paths.sort();
    Ok(paths)
}

pub fn safe_name(value: &str) -> Result<&str, String> {
    if value.is_empty()
        || value == "."
        || value == ".."
        || !value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"_-".contains(&c))
    {
        return Err(format!("invalid file identifier {value:?}"));
    }
    Ok(value)
}

pub fn optional_number(value: Option<&Json>) -> Result<Option<f64>, String> {
    match value {
        None | Some(Json::Null) => Ok(None),
        Some(Json::Num(n)) if n.is_finite() => Ok(Some(*n)),
        Some(Json::Str(n)) => n
            .parse::<f64>()
            .ok()
            .filter(|n| n.is_finite())
            .map(Some)
            .ok_or_else(|| format!("invalid time {n:?}")),
        _ => Err("expected a finite time".to_owned()),
    }
}

pub fn truth(value: &Json) -> bool {
    match value {
        Json::Null => false,
        Json::Bool(b) => *b,
        Json::Num(n) => *n != 0.0,
        Json::Str(s) => !s.is_empty(),
        Json::Arr(a) => !a.is_empty(),
        Json::Obj(o) => !o.is_empty(),
    }
}
