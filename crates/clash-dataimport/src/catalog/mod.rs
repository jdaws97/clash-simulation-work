//! Offline source-to-runtime catalog construction. See docs/DATA_PIPELINE.md.

mod build;
mod csv;
mod encoding;
mod registry;
mod specs;
mod stats;
mod tables;
#[cfg(test)]
mod tests;

use std::path::{Path, PathBuf};

use clash_data::json::Json;
use clash_data::wire::{self, obj};

static EMPTY: Json = Json::Obj(Vec::new());

fn field<'a>(value: &'a Json, key: &str) -> &'a Json {
    value.get(key).unwrap_or(&Json::Null)
}

fn object<'a>(value: &'a Json, key: &str) -> &'a Json {
    value.get(key).unwrap_or(&EMPTY)
}

fn entries(value: &Json) -> &[(String, Json)] {
    match value {
        Json::Obj(items) => items,
        _ => &[],
    }
}

fn items(value: &Json) -> &[Json] {
    match value {
        Json::Arr(items) => items,
        _ => &[],
    }
}

fn text(value: &Json) -> &str {
    match value {
        Json::Str(value) => value,
        _ => "",
    }
}

fn truth(value: &Json) -> bool {
    match value {
        Json::Null => false,
        Json::Bool(value) => *value,
        Json::Num(value) => *value != 0.0,
        Json::Str(value) => !value.is_empty(),
        Json::Arr(value) => !value.is_empty(),
        Json::Obj(value) => !value.is_empty(),
    }
}

fn merge(target: &mut Json, source: &Json) {
    for (key, value) in entries(source) {
        wire::put(target, key, value.clone());
    }
}

fn get_mut<'a>(value: &'a mut Json, key: &str) -> &'a mut Json {
    let Json::Obj(fields) = value else {
        panic!("internal catalog object expected");
    };
    &mut fields.iter_mut().find(|(name, _)| name == key).unwrap().1
}

/// Explicit input locations; the builder never discovers a sibling checkout.
pub struct Sources {
    pub root: PathBuf,
    pub wiki: PathBuf,
}

impl Sources {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        let root = root.into();
        let wiki = root.join("data/wiki");
        Self { root, wiki }
    }
}

/// Rebuild the unmodified registry intermediate from ClashKing and the wiki.
pub fn build_registry(sources: &Sources) -> Result<Json, String> {
    let raw = wire::read(&sources.root.join("data/clashking-static-data.json"))?;
    let mut registry = registry::build(&raw, &sources.wiki)?;
    registry::repair_inferno(&mut registry, &csv::Tables::load(&sources.root)?)?;
    Ok(registry)
}

/// Rebuild all runtime values from sources, without reading a runtime catalog.
pub fn build_catalog(sources: &Sources) -> Result<Json, String> {
    build::catalog(sources)
}

/// `clash dataimport catalog --out FILE [--root DIR] [--wiki-root DIR]`
/// Optional `--registry-out FILE` also writes the rebuilt intermediate.
pub fn cli(args: &[String]) -> Result<(), String> {
    let mut sources = Sources::new(env!("CARGO_MANIFEST_DIR").to_owned() + "/../..");
    let mut output = None;
    let mut registry_output = None;
    let mut wiki = None;
    let mut index = 0;
    while index < args.len() {
        let key = &args[index];
        let value = args
            .get(index + 1)
            .ok_or_else(|| format!("{key} needs a value"))?;
        match key.as_str() {
            "--out" => output = Some(PathBuf::from(value)),
            "--root" => sources = Sources::new(value),
            "--wiki-root" => wiki = Some(PathBuf::from(value)),
            "--registry-out" => registry_output = Some(PathBuf::from(value)),
            _ => return Err(format!("unknown catalog option: {key}")),
        }
        index += 2;
    }
    if let Some(wiki) = wiki {
        sources.wiki = wiki;
    }
    let output = output.ok_or("usage: clash dataimport catalog --out FILE [--root DIR] [--wiki-root DIR] [--registry-out FILE]")?;
    let catalog = build_catalog(&sources)?;
    if let Some(path) = registry_output {
        let registry = build_registry(&sources)?;
        if let Some(parent) = path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        }
        std::fs::write(&path, encoding::registry(&registry))
            .map_err(|error| format!("{}: {error}", path.display()))?;
    }
    wire::write(&output, &catalog)?;
    println!(
        "catalog: {} registry entries, {} units, {} unit levels -> {}",
        entries(field(&catalog, "registry")).len(),
        entries(field(&catalog, "units")).len(),
        entries(field(&catalog, "unit_numbers")).len(),
        output.display()
    );
    Ok(())
}

fn required_text(path: &Path) -> Result<String, String> {
    std::fs::read_to_string(path)
        .map_err(|error| format!("required catalog input {}: {error}", path.display()))
}

fn empty() -> Json {
    obj(Vec::<(String, Json)>::new())
}
