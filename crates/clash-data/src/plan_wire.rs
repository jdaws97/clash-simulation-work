//! Order-preserving plan JSON helpers.
use crate::json::{self, Json};
use std::fs;
use std::path::Path;

pub fn read_json(path: &Path) -> Result<Json, String> {
    let source =
        fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    json::parse(source.trim_start_matches('\u{feff}'))
        .map_err(|error| format!("{}: {error}", path.display()))
}

pub fn object() -> Json {
    Json::Obj(Vec::new())
}

pub fn string(value: &str) -> Json {
    Json::Str(value.to_owned())
}

pub fn array(values: impl IntoIterator<Item = Json>) -> Json {
    Json::Arr(values.into_iter().collect())
}

pub fn put(value: &mut Json, key: &str, item: Json) {
    let Json::Obj(items) = value else {
        panic!("expected object while assigning {key}");
    };
    if let Some((_, old)) = items.iter_mut().find(|(name, _)| name == key) {
        *old = item;
    } else {
        items.push((key.to_owned(), item));
    }
}

pub fn remove(value: &mut Json, key: &str) {
    let Json::Obj(items) = value else {
        panic!("expected object while removing {key}");
    };
    items.retain(|(name, _)| name != key);
}

pub fn items(value: &Json, key: &str) -> Vec<(String, Json)> {
    value
        .get(key)
        .filter(|v| !v.is_null())
        .map_or_else(Vec::new, |v| v.obj().to_vec())
}

pub fn list<'a>(value: &'a Json, key: &str) -> &'a [Json] {
    value.get(key).map_or(&[], Json::arr)
}

pub fn field(value: &Json, key: &str) -> Json {
    value.get(key).cloned().unwrap_or(Json::Null)
}

pub fn python_value(value: &Json) -> String {
    match value {
        Json::Null => "None".to_owned(),
        Json::Bool(true) => "True".to_owned(),
        Json::Bool(false) => "False".to_owned(),
        Json::Num(value) if value.fract() == 0.0 => format!("{value:.0}"),
        Json::Num(value) => crate::float::py_float_repr(*value),
        Json::Str(value) => value.clone(),
        _ => format!("{value:?}"),
    }
}
