//! Keyless observation ingestion. Raw archives are private caller-selected files.
//! Share-code parsing is shared with fidelity through `clash_data::battlelog`.

mod archive;
mod cli;
pub mod provider;
pub mod snapshots;

pub use archive::{collect, CollectReport};
pub use clash_data::battlelog::{identity, Decoder};
pub use cli::cli;

use clash_data::json::Json;

pub(crate) fn object(value: &Json) -> Result<&[(String, Json)], String> {
    match value {
        Json::Obj(fields) => Ok(fields),
        _ => Err("expected JSON object".to_owned()),
    }
}

pub(crate) fn required_text<'a>(value: &'a Json, key: &str) -> Result<&'a str, String> {
    match value.get(key) {
        Some(Json::Str(text)) if !text.is_empty() => Ok(text),
        _ => Err(format!("missing or invalid {key}")),
    }
}

pub(crate) fn timestamp(value: &str) -> Result<i64, String> {
    if !value.is_ascii() {
        return Err("invalid_timestamp".to_owned());
    }
    clash_data::snapshots::timestamp(value)
}

#[cfg(test)]
mod tests;
