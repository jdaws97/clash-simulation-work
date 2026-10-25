//! Rust-only normalization of local game data. No catalog count is used as a
//! Town Hall inventory. Each quantity and merge retains a JSON source pointer.
use std::collections::BTreeMap;
use std::path::Path;

use crate::catalog::Catalog;
use crate::stats::Level;
use clash_data::json::Json;

use super::json::{encode, identity, read, string};

#[derive(Clone, Debug)]
pub struct TownHallRules {
    pub buildings: BTreeMap<String, usize>,
    pub unmerged: BTreeMap<String, usize>,
    pub traps: BTreeMap<String, usize>,
    pub walls: usize,
}

#[derive(Clone, Debug)]
pub struct BaseRules {
    pub identity: String,
    pub catalog_identity: String,
    pub town_halls: BTreeMap<i64, TownHallRules>,
    pub document: Json,
}

fn counts(value: &Json) -> BTreeMap<String, usize> {
    value
        .obj()
        .iter()
        .map(|(k, v)| (k.clone(), v.usize()))
        .collect()
}

impl BaseRules {
    pub fn load(path: &Path) -> Result<Self, String> {
        Self::from_json(read(path)?)
    }

    pub fn from_json(document: Json) -> Result<Self, String> {
        // This is generated trusted data, but report a corrupt file as an error.
        std::panic::catch_unwind(|| {
            if document.at("schema_version").i64() != 1 {
                return Err("unsupported base rules schema".to_owned());
            }
            let town_halls = document
                .at("town_halls")
                .obj()
                .iter()
                .map(|(th, row)| {
                    Ok((
                        th.parse::<i64>().map_err(|e| e.to_string())?,
                        TownHallRules {
                            buildings: counts(row.at("buildings")),
                            unmerged: counts(row.at("unmerged")),
                            traps: counts(row.at("traps")),
                            walls: row.at("walls").usize(),
                        },
                    ))
                })
                .collect::<Result<_, String>>()?;
            Ok(Self {
                identity: identity(encode(&document).as_bytes()),
                catalog_identity: document.at("catalog_identity").str().to_owned(),
                town_halls,
                document,
            })
        })
        .map_err(|_| "malformed base rules document".to_owned())?
    }
}

/// Registry validation without assertion-based Stats::validate_level.
pub fn valid_level(catalog: &Catalog, name: &str, level: &Level, th: i64) -> bool {
    let Some(record) = catalog.stats.registry.get(name) else {
        return false;
    };
    let exists = record
        .at("levels")
        .arr()
        .iter()
        .any(|row| match (level, row.at("level")) {
            (Level::Int(a), Json::Num(b)) => *a >= 1 && *a as f64 == *b,
            (Level::Text(a), Json::Str(b)) => a == b,
            _ => false,
        });
    exists
        && catalog.stats.max_level(name, th).is_some()
        && catalog.stats.required_town_hall(name, level) <= th as f64
}

pub fn pretty(value: &Json) -> String {
    fn write(value: &Json, depth: usize, out: &mut String) {
        let pad = "  ".repeat(depth);
        match value {
            Json::Obj(values) if !values.is_empty() => {
                out.push_str("{\n");
                for (i, (key, value)) in values.iter().enumerate() {
                    out.push_str(&format!("{pad}  {}: ", encode(&string(key))));
                    write(value, depth + 1, out);
                    out.push_str(if i + 1 == values.len() { "\n" } else { ",\n" });
                }
                out.push_str(&format!("{pad}}}"));
            }
            Json::Arr(values) if !values.is_empty() => {
                out.push_str("[\n");
                for (i, value) in values.iter().enumerate() {
                    out.push_str(&format!("{pad}  "));
                    write(value, depth + 1, out);
                    out.push_str(if i + 1 == values.len() { "\n" } else { ",\n" });
                }
                out.push_str(&format!("{pad}]"));
            }
            _ => out.push_str(&encode(value)),
        }
    }
    let mut out = String::new();
    write(value, 0, &mut out);
    out.push('\n');
    out
}
