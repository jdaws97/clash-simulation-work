//! Fallible legacy JSON boundary. Never use Json::i64/f64 on untrusted input.
use std::collections::{BTreeMap, BTreeSet};

use crate::json::Json;
use crate::stats::Level;

use super::admit::{AdmissionIssue, AdmissionReport};
use super::model::*;

pub fn string(value: impl Into<String>) -> Json {
    Json::Str(value.into())
}

pub fn number(value: impl Into<f64>) -> Json {
    Json::Num(value.into())
}

pub fn object(entries: impl IntoIterator<Item = (&'static str, Json)>) -> Json {
    Json::Obj(
        entries
            .into_iter()
            .map(|(k, v)| (k.to_owned(), v))
            .collect(),
    )
}

pub fn encode(value: &Json) -> String {
    crate::compile_cli::to_json(value)
}

/// Fixed FNV-1a/128 regression identity; not a cryptographic signature.
pub fn identity(bytes: &[u8]) -> String {
    let mut hash = 0x6c62272e07bb014262b821756295c58du128;
    for byte in bytes {
        hash ^= *byte as u128;
        hash = hash.wrapping_mul(0x1000000000000000000013b);
    }
    format!("fnv128:{hash:032x}")
}

pub fn read(path: &std::path::Path) -> Result<Json, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    crate::json::parse(text.trim_start_matches('\u{feff}')).map_err(|e| e.to_string())
}

fn issue(path: &str, code: &str, expected: &str, actual: &Json) -> AdmissionReport {
    AdmissionReport::one(AdmissionIssue::new(code, path, expected, actual.clone()))
}

pub fn integer(value: &Json, path: &str) -> Result<i32, AdmissionReport> {
    match value {
        Json::Num(v)
            if v.is_finite()
                && v.fract() == 0.0
                && *v >= i32::MIN as f64
                && *v <= i32::MAX as f64 =>
        {
            Ok(*v as i32)
        }
        _ => Err(issue(
            path,
            "integer",
            "finite integral JSON number within i32",
            value,
        )),
    }
}

fn text(value: &Json, path: &str) -> Result<String, AdmissionReport> {
    match value {
        Json::Str(v) => Ok(v.clone()),
        _ => Err(issue(path, "schema", "string", value)),
    }
}

fn field<'a>(value: &'a Json, key: &str, path: &str) -> Result<&'a Json, AdmissionReport> {
    value.get(key).ok_or_else(|| {
        issue(
            &format!("{path}.{key}"),
            "schema",
            "required field",
            &Json::Null,
        )
    })
}

fn array<'a>(value: &'a Json, path: &str) -> Result<&'a [Json], AdmissionReport> {
    match value {
        Json::Arr(v) => Ok(v),
        _ => Err(issue(path, "schema", "array", value)),
    }
}

fn entries<'a>(value: &'a Json, path: &str) -> Result<&'a [(String, Json)], AdmissionReport> {
    match value {
        Json::Obj(v) => {
            let mut keys = BTreeSet::new();
            for (k, _) in v {
                if !keys.insert(k) {
                    return Err(issue(
                        path,
                        "duplicate_field",
                        "unique object keys",
                        &string(k),
                    ));
                }
            }
            Ok(v)
        }
        _ => Err(issue(path, "schema", "object", value)),
    }
}

pub fn level(value: &Json, path: &str) -> Result<Level, AdmissionReport> {
    match value {
        Json::Str(v) if !v.is_empty() => Ok(Level::Text(v.clone())),
        _ => integer(value, path).map(|v| Level::Int(v as i64)),
    }
}

fn levels(value: Option<&Json>, path: &str) -> Result<BTreeMap<String, Level>, AdmissionReport> {
    let mut result = BTreeMap::new();
    if let Some(value) = value {
        for (k, v) in entries(value, path)? {
            result.insert(k.clone(), level(v, &format!("{path}.{k}"))?);
        }
    }
    Ok(result)
}

fn position(value: &Json, path: &str) -> Result<Tile, AdmissionReport> {
    Ok((
        integer(field(value, "x", path)?, &format!("{path}.x"))?,
        integer(field(value, "y", path)?, &format!("{path}.y"))?,
    ))
}

fn mode(value: &Json, path: &str) -> Result<Option<Mode>, AdmissionReport> {
    match value.get("mode") {
        None | Some(Json::Null) => Ok(None),
        Some(Json::Str(v)) if v.is_empty() => Ok(None),
        Some(Json::Str(v)) => Mode::parse(v).map(Some).ok_or_else(|| {
            issue(
                &format!("{path}.mode"),
                "unsupported_mode",
                "known mode",
                &string(v),
            )
        }),
        Some(v) => Err(issue(
            &format!("{path}.mode"),
            "schema",
            "string or null",
            v,
        )),
    }
}

fn ids(
    value: &Json,
    key: &str,
    count: usize,
    prefix: &str,
) -> Result<Vec<String>, AdmissionReport> {
    let supplied = value.get("instance_ids").and_then(|v| v.get(key));
    if let Some(supplied) = supplied {
        let path = format!("$.instance_ids.{key}");
        let values = array(supplied, &path)?;
        if values.len() != count {
            return Err(issue(
                &path,
                "instance_ids",
                "one ID per placement",
                supplied,
            ));
        }
        return values.iter().map(|v| text(v, &path)).collect();
    }
    Ok((0..count).map(|i| format!("{prefix}{i:04}")).collect())
}

impl Layout {
    pub fn parse(text: &str) -> Result<Self, AdmissionReport> {
        let value = crate::json::parse(text.trim_start_matches('\u{feff}')).map_err(|error| {
            AdmissionReport::one(AdmissionIssue::new(
                "json_syntax",
                "$",
                "valid JSON",
                string(error.to_string()),
            ))
        })?;
        Self::from_json(&value)
    }

    pub fn load(path: &std::path::Path) -> Result<Self, AdmissionReport> {
        let text = std::fs::read_to_string(path).map_err(|error| {
            AdmissionReport::one(AdmissionIssue::new(
                "input_io",
                "$",
                "readable UTF-8 layout",
                string(format!("{}: {error}", path.display())),
            ))
        })?;
        Self::parse(&text)
    }

    pub fn from_json(value: &Json) -> Result<Self, AdmissionReport> {
        entries(value, "$")?;
        if let Some(schema) = value.get("layout_schema") {
            if integer(schema, "$.layout_schema")? != 1 {
                return Err(issue("$.layout_schema", "schema_version", "1", schema));
            }
        }
        if let Some(id_map) = value.get("instance_ids") {
            entries(id_map, "$.instance_ids")?;
        }
        let empty = Json::Arr(Vec::new());
        let buildings_json = array(field(value, "buildings", "$")?, "$.buildings")?;
        let buildings_ids = ids(value, "buildings", buildings_json.len(), "b")?;
        let mut buildings = Vec::new();
        for (i, item) in buildings_json.iter().enumerate() {
            let path = format!("$.buildings[{i}]");
            entries(item, &path)?;
            buildings.push(BuildingPlacement {
                id: buildings_ids[i].clone(),
                key: text(field(item, "key", &path)?, &format!("{path}.key"))?,
                position: position(item, &path)?,
                mode: mode(item, &path)?,
            });
        }
        let walls_json = array(value.get("walls").unwrap_or(&empty), "$.walls")?;
        let walls_ids = ids(value, "walls", walls_json.len(), "w")?;
        let mut walls = Vec::new();
        for (i, item) in walls_json.iter().enumerate() {
            let path = format!("$.walls[{i}]");
            let pair = array(item, &path)?;
            if pair.len() != 2 {
                return Err(issue(&path, "schema", "coordinate pair", item));
            }
            walls.push(WallPiece {
                id: walls_ids[i].clone(),
                position: (
                    integer(&pair[0], &format!("{path}[0]"))?,
                    integer(&pair[1], &format!("{path}[1]"))?,
                ),
                level: None,
            });
        }
        let mut overrides = BTreeSet::new();
        for (i, item) in array(value.get("wall_levels").unwrap_or(&empty), "$.wall_levels")?
            .iter()
            .enumerate()
        {
            let path = format!("$.wall_levels[{i}]");
            entries(item, &path)?;
            let tile = position(item, &path)?;
            if !overrides.insert(tile) {
                return Err(issue(
                    &path,
                    "duplicate_wall_level",
                    "one override per wall",
                    item,
                ));
            }
            let Some(wall) = walls.iter_mut().find(|wall| wall.position == tile) else {
                return Err(issue(
                    &path,
                    "dangling_wall_level",
                    "corresponding wall",
                    item,
                ));
            };
            wall.level = Some(level(
                field(item, "level", &path)?,
                &format!("{path}.level"),
            )?);
        }
        let traps_json = array(value.get("traps").unwrap_or(&empty), "$.traps")?;
        let trap_ids = ids(value, "traps", traps_json.len(), "t")?;
        let mut traps = Vec::new();
        for (i, item) in traps_json.iter().enumerate() {
            let path = format!("$.traps[{i}]");
            entries(item, &path)?;
            traps.push(TrapPlacement {
                id: trap_ids[i].clone(),
                key: text(field(item, "key", &path)?, &format!("{path}.key"))?,
                position: position(item, &path)?,
                mode: mode(item, &path)?,
            });
        }
        let default_heroes = Json::Arr(
            [
                "Archer Queen",
                "Barbarian King",
                "Grand Warden",
                "Minion Prince",
            ]
            .map(string)
            .to_vec(),
        );
        let banners: Vec<_> = buildings.iter().filter(|b| b.key == "banner").collect();
        let mut heroes = Vec::new();
        for (i, hero) in array(value.get("heroes").unwrap_or(&default_heroes), "$.heroes")?
            .iter()
            .enumerate()
        {
            heroes.push(HeroBinding {
                hero: text(hero, &format!("$.heroes[{i}]"))?,
                banner: banners.get(i).map(|b| b.id.clone()),
            });
        }
        let default_cc = Json::Arr(
            [
                "Dragon",
                "Dragon",
                "Headhunter",
                "Archer",
                "Archer",
                "Archer",
                "Archer",
            ]
            .map(string)
            .to_vec(),
        );
        let mut cc_troops = Vec::new();
        for (i, item) in array(value.get("cc_troops").unwrap_or(&default_cc), "$.cc_troops")?
            .iter()
            .enumerate()
        {
            let path = format!("$.cc_troops[{i}]");
            if let Json::Str(name) = item {
                cc_troops.push(CcEntry {
                    name: name.clone(),
                    source: None,
                    level: None,
                    count: 1,
                    object_form: false,
                });
            } else {
                entries(item, &path)?;
                let name = item
                    .get("name")
                    .filter(|v| !v.is_null() && !matches!(v, Json::Str(s) if s.is_empty()))
                    .or_else(|| item.get("type"))
                    .ok_or_else(|| issue(&path, "schema", "name or type", item))?;
                let count = item
                    .get("count")
                    .map(|v| integer(v, &format!("{path}.count")))
                    .transpose()?
                    .unwrap_or(1);
                if !(1..=1000).contains(&count) {
                    return Err(issue(&path, "cc_count", "count 1..1000", item));
                }
                cc_troops.push(CcEntry {
                    name: text(name, &path)?,
                    source: item
                        .get("source")
                        .map(|v| text(v, &format!("{path}.source")))
                        .transpose()?,
                    level: item
                        .get("level")
                        .filter(|v| !v.is_null())
                        .map(|v| level(v, &format!("{path}.level")))
                        .transpose()?,
                    count: count as u32,
                    object_form: true,
                });
            }
        }
        Ok(Self {
            name: value
                .get("name")
                .map(|v| text(v, "$.name"))
                .transpose()?
                .unwrap_or_default(),
            notes: value
                .get("notes")
                .map(|v| text(v, "$.notes"))
                .transpose()?
                .unwrap_or_default(),
            town_hall: value
                .get("town_hall")
                .map(|v| integer(v, "$.town_hall"))
                .transpose()?
                .unwrap_or(16) as i64,
            buildings,
            walls,
            traps,
            setup: DefenseSetup {
                levels: levels(value.get("levels"), "$.levels")?,
                hero_levels: levels(value.get("hero_levels"), "$.hero_levels")?,
                cc_troops,
                heroes,
                guardian: match value.get("guardian") {
                    None => Some("Longshot".to_owned()),
                    Some(Json::Null) => None,
                    Some(Json::Str(s)) if s.is_empty() => None,
                    Some(v) => Some(text(v, "$.guardian")?),
                },
                wall_level: value
                    .get("wall_level")
                    .filter(|v| !v.is_null())
                    .map(|v| level(v, "$.wall_level"))
                    .transpose()?,
            },
        })
    }

    /// Legacy-compatible document; additive top-level IDs survive save/load.
    /// The engine ignores those fields. Array order is deliberately retained.
    pub fn to_json(&self) -> Json {
        let placements = |items: Vec<(&str, Tile, Option<Mode>)>| {
            Json::Arr(
                items
                    .into_iter()
                    .map(|(key, (x, y), mode)| {
                        let mut fields = vec![
                            ("key".to_owned(), string(key)),
                            ("x".to_owned(), number(x)),
                            ("y".to_owned(), number(y)),
                        ];
                        if let Some(mode) = mode {
                            fields.push(("mode".to_owned(), string(mode.as_str())));
                        }
                        Json::Obj(fields)
                    })
                    .collect(),
            )
        };
        let map = |values: &BTreeMap<String, Level>| {
            Json::Obj(
                values
                    .iter()
                    .map(|(k, v)| (k.clone(), level_json(v)))
                    .collect(),
            )
        };
        object([
            ("layout_schema", number(1)),
            (
                "instance_ids",
                object([
                    (
                        "buildings",
                        Json::Arr(self.buildings.iter().map(|b| string(&b.id)).collect()),
                    ),
                    (
                        "walls",
                        Json::Arr(self.walls.iter().map(|w| string(&w.id)).collect()),
                    ),
                    (
                        "traps",
                        Json::Arr(self.traps.iter().map(|t| string(&t.id)).collect()),
                    ),
                ]),
            ),
            ("name", string(&self.name)),
            ("notes", string(&self.notes)),
            ("town_hall", number(self.town_hall as i32)),
            (
                "buildings",
                placements(
                    self.buildings
                        .iter()
                        .map(|b| (b.key.as_str(), b.position, b.mode))
                        .collect(),
                ),
            ),
            (
                "walls",
                Json::Arr(
                    self.walls
                        .iter()
                        .map(|w| Json::Arr(vec![number(w.position.0), number(w.position.1)]))
                        .collect(),
                ),
            ),
            (
                "wall_levels",
                Json::Arr(
                    self.walls
                        .iter()
                        .filter_map(|w| {
                            w.level.as_ref().map(|level| {
                                object([
                                    ("x", number(w.position.0)),
                                    ("y", number(w.position.1)),
                                    ("level", level_json(level)),
                                ])
                            })
                        })
                        .collect(),
                ),
            ),
            (
                "wall_level",
                self.setup
                    .wall_level
                    .as_ref()
                    .map(level_json)
                    .unwrap_or(Json::Null),
            ),
            (
                "traps",
                placements(
                    self.traps
                        .iter()
                        .map(|t| (t.key.as_str(), t.position, t.mode))
                        .collect(),
                ),
            ),
            ("levels", map(&self.setup.levels)),
            ("hero_levels", map(&self.setup.hero_levels)),
            (
                "heroes",
                Json::Arr(self.setup.heroes.iter().map(|h| string(&h.hero)).collect()),
            ),
            (
                "cc_troops",
                Json::Arr(
                    self.setup
                        .cc_troops
                        .iter()
                        .map(|entry| {
                            if !entry.object_form && entry.level.is_none() && entry.count == 1 {
                                return string(&entry.name);
                            }
                            let mut fields = vec![
                                ("name".to_owned(), string(&entry.name)),
                                ("count".to_owned(), number(entry.count)),
                            ];
                            if let Some(source) = &entry.source {
                                fields.push(("source".to_owned(), string(source)));
                            }
                            if let Some(level) = &entry.level {
                                fields.push(("level".to_owned(), level_json(level)));
                            }
                            Json::Obj(fields)
                        })
                        .collect(),
                ),
            ),
            (
                "guardian",
                self.setup
                    .guardian
                    .as_ref()
                    .map(string)
                    .unwrap_or(Json::Null),
            ),
        ])
    }
}

pub fn level_json(level: &Level) -> Json {
    match level {
        Level::Int(v) => Json::Num(*v as f64),
        Level::Text(v) => string(v),
    }
}
