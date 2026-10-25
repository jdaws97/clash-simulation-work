//! Rust-only normalization of local game data. No catalog count is used as a
//! Town Hall inventory. Each quantity and merge retains a JSON source pointer.
use std::collections::BTreeMap;
use std::path::Path;

use crate::catalog::Catalog;
use crate::json::Json;
use crate::stats::Level;

use super::json::{encode, identity, number, object, read, string};

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

fn count_json(values: &BTreeMap<String, usize>) -> Json {
    Json::Obj(
        values
            .iter()
            .map(|(k, v)| (k.clone(), Json::Num(*v as f64)))
            .collect(),
    )
}

fn consume(counts: &mut BTreeMap<String, usize>, key: &str, count: usize) -> Result<(), String> {
    let available = counts
        .get_mut(key)
        .ok_or_else(|| format!("merge source {key} missing"))?;
    *available = available
        .checked_sub(count)
        .ok_or_else(|| format!("merge overconsumes {key}"))?;
    Ok(())
}

/// Derive from the local snapshot, with named compatibility/model overrides.
pub fn derive(root: &Path, catalog: &Catalog, catalog_bytes: &[u8]) -> Result<Json, String> {
    let source_path = root.join("data/clashking-static-data.json");
    let source_bytes = std::fs::read(&source_path).map_err(|e| e.to_string())?;
    let source = crate::json::parse(std::str::from_utf8(&source_bytes).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let buildings = source.at("buildings").arr();
    let (th_index, th) = buildings
        .iter()
        .enumerate()
        .find(|(_, b)| b.at("name").str() == "Town Hall")
        .ok_or("Town Hall source missing")?;
    let mut unlocks = Vec::new();
    let mut merges = Vec::new();
    let mut quantities = BTreeMap::<String, usize>::new();
    let mut snapshots = Vec::new();
    let source_ref = |pointer: String| string(format!("data/clashking-static-data.json#{pointer}"));
    for (level_index, row) in th.at("levels").arr().iter().enumerate() {
        let th_level = row.at("level").i64();
        if th_level > 18 {
            continue;
        }
        for (i, unlock) in row
            .get("unlocks")
            .map_or(&[][..], Json::arr)
            .iter()
            .enumerate()
        {
            let name = unlock.at("name").str();
            let quantity = unlock.at("quantity").usize();
            *quantities.entry(name.to_owned()).or_default() += quantity;
            unlocks.push(object([
                ("town_hall", number(th_level as i32)),
                ("name", string(name)),
                ("quantity", Json::Num(quantity as f64)),
                (
                    "source",
                    source_ref(format!(
                        "/buildings/{th_index}/levels/{level_index}/unlocks/{i}/quantity"
                    )),
                ),
            ]));
        }
        if !(16..=18).contains(&th_level) {
            continue;
        }
        let mut merged = quantities.clone();
        // A TH upgrade consumes its merge_requirement once, not once per TH.
        for (i, prior_th) in th.at("levels").arr().iter().enumerate() {
            if prior_th.at("level").i64() > th_level {
                continue;
            }
            if let Some(recipe) = prior_th.get("merge_requirement") {
                for ingredient in recipe.arr() {
                    consume(&mut merged, ingredient.at("name").str(), 1)?;
                }
                if th_level == 17 {
                    merges.push(object([
                        ("product", string("Town Hall")),
                        ("town_hall", number(17)),
                        ("recipe", recipe.clone()),
                        (
                            "source",
                            source_ref(format!(
                                "/buildings/{th_index}/levels/{i}/merge_requirement"
                            )),
                        ),
                    ]));
                }
            }
        }
        for (i, building) in buildings.iter().enumerate() {
            let Some(first) = building.at("levels").arr().first() else {
                continue;
            };
            if let Some(recipe) = first.get("merge_requirement") {
                let product = building.at("name").str();
                let count = quantities.get(product).copied().unwrap_or(0);
                for ingredient in recipe.arr() {
                    consume(&mut merged, ingredient.at("name").str(), count)?;
                }
                if first.at("required_townhall").i64() == th_level {
                    merges.push(object([
                        ("product", string(product)),
                        ("town_hall", first.at("required_townhall").clone()),
                        ("recipe", recipe.clone()),
                        (
                            "source",
                            source_ref(format!("/buildings/{i}/levels/0/merge_requirement")),
                        ),
                    ]));
                }
            }
        }
        let mut inventory = BTreeMap::new();
        let mut unmerged = BTreeMap::new();
        let mut maximums = Vec::new();
        for (key, bt) in &catalog.building_types {
            let mut quantity = merged.get(&bt.name).copied().unwrap_or(0);
            let mut raw = quantities.get(&bt.name).copied().unwrap_or(0);
            match key.as_str() {
                "th" => {
                    quantity = 1;
                    raw = 1;
                }
                "banner" => {
                    quantity = 4;
                    raw = 4;
                }
                "crafting" => {
                    quantity = 1;
                    raw = 1;
                }
                _ => {}
            }
            inventory.insert(key.clone(), quantity);
            unmerged.insert(key.clone(), raw);
            let maximum = if catalog.stats.registry.get(&bt.name).is_some() {
                catalog
                    .stats
                    .max_level(&bt.name, th_level)
                    .map(|v| number(v as i32))
                    .unwrap_or(Json::Null)
            } else {
                number(1)
            };
            maximums.push((key.clone(), maximum));
        }
        let traps: BTreeMap<_, _> = catalog
            .trap_names
            .iter()
            .map(|(key, name)| (key.clone(), quantities.get(name).copied().unwrap_or(0)))
            .collect();
        let walls = *quantities.get("Wall").ok_or("wall unlocks missing")?;
        let castle_level = Level::Int(
            catalog
                .stats
                .max_level("Clan Castle", th_level)
                .ok_or("castle level missing")?,
        );
        let hall_level = Level::Int(
            catalog
                .stats
                .max_level("Hero Hall", th_level)
                .ok_or("Hero Hall level missing")?,
        );
        let trap_maximums = Json::Obj(
            catalog
                .trap_names
                .iter()
                .map(|(key, name)| {
                    let maximum = catalog
                        .stats
                        .max_level(name, th_level)
                        .map(|v| number(v as i32))
                        .unwrap_or(Json::Null);
                    (key.clone(), maximum)
                })
                .collect(),
        );
        snapshots.push((
            th_level.to_string(),
            object([
                ("buildings", count_json(&inventory)),
                ("unmerged", count_json(&unmerged)),
                ("traps", count_json(&traps)),
                ("walls", Json::Num(walls as f64)),
                ("max_levels", Json::Obj(maximums)),
                ("trap_max_levels", trap_maximums),
                (
                    "cc_capacity",
                    Json::Num(
                        catalog
                            .stats
                            .get("Clan Castle", &castle_level, &["Troop Capacity"], None)
                            .ok_or("CC capacity missing")?,
                    ),
                ),
                (
                    "cc_laboratory_cap",
                    Json::Num(
                        catalog
                            .stats
                            .get(
                                "Clan Castle",
                                &castle_level,
                                &["~Laboratory Level Cap"],
                                None,
                            )
                            .ok_or("CC lab cap missing")?,
                    ),
                ),
                (
                    "hero_slots",
                    Json::Num(
                        catalog
                            .stats
                            .get("Hero Hall", &hall_level, &["Hero Slots"], None)
                            .ok_or("Hero Hall slots missing")?,
                    ),
                ),
                (
                    "wall_max_level",
                    number(
                        catalog
                            .stats
                            .max_level("Wall", th_level)
                            .ok_or("wall maximum missing")? as i32,
                    ),
                ),
            ]),
        ));
    }
    let mut footprints = Vec::new();
    for (key, bt) in &catalog.building_types {
        let source = format!(
            "rust/data/catalog.json#/building_types/{key}; \
             data/clashking-static-data.json buildings[name={}].width; \
             src/baselab/mechanics.py _SIZE_FALLBACK",
            bt.name
        );
        let footprint = object([
            ("name", string(&bt.name)),
            ("size", Json::Num(bt.size as f64)),
            ("source", string(source)),
        ]);
        footprints.push((key.clone(), footprint));
    }
    let mut trap_footprints = Vec::new();
    for (key, name) in &catalog.trap_names {
        let size = catalog
            .trap_sizes
            .iter()
            .find(|(k, _)| k == key)
            .map_or(1, |(_, s)| *s);
        let footprint = object([
            ("name", string(name)),
            ("size", Json::Num(size as f64)),
            (
                "source",
                string("rust/data/catalog.json#/trap_sizes; src/baselab/mechanics.py TRAP_SIZES"),
            ),
        ]);
        trap_footprints.push((key.clone(), footprint));
    }
    let level_limits = Json::Obj(
        catalog
            .stats
            .registry
            .obj()
            .iter()
            .filter(|(_, record)| matches!(record.at("kind").str(), "hero" | "guardian"))
            .map(|(name, _)| {
                (
                    name.clone(),
                    Json::Obj(
                        (16..=18)
                            .map(|th| {
                                (
                                    th.to_string(),
                                    catalog
                                        .stats
                                        .max_level(name, th)
                                        .map(|v| number(v as i32))
                                        .unwrap_or(Json::Null),
                                )
                            })
                            .collect(),
                    ),
                )
            })
            .collect(),
    );
    let overrides = Json::Arr(vec![
        string("Town Hall=1: the upgraded structure is not itself an unlock"),
        string("Hero Banner=4 at TH16-18: src/baselab/mechanics.py BUILDING_TYPES; Hero Hall registry levels[].wiki.Hero Slots"),
        string("Crafting Station=1 optional at TH16-18: src/baselab/mechanics.py INVENTORY/OPTIONAL_KEYS; frozen seasonal model overrides static TH18-only unlock"),
        string("Unlisted trap footprint=1; giant/giga=2: src/baselab/mechanics.py TRAP_SIZES"),
    ]);
    let mode_source = "rust/data/catalog.json#/setup/{spell_tower_unlocks,gear_minimum,crafting}; game_data.buildings.{Cannon,Archer Tower,Mortar}[].{GearUpCost,GearUpLevelRequirement}";
    let mode_unlocks = object([
        (
            "spell_tower",
            catalog.setup.at("spell_tower_unlocks").clone(),
        ),
        ("gear_minimum", catalog.setup.at("gear_minimum").clone()),
        ("crafting", catalog.setup.at("crafting").clone()),
        ("source", string(mode_source)),
    ]);
    let capacity_source = "rust/data/catalog.json#/registry/{Hero Hall,Clan Castle}/levels/*/wiki/{Hero Slots,Troop Capacity,Laboratory Level Cap}; /setup/donated_laboratory";
    let level_source = "rust/data/catalog.json#/registry/*/{levels,max_level}; levels[].{required_townhall,wiki.Town Hall Level Required}";
    let preset = "fully-merged-th16-18; model compatibility, not account ownership";
    Ok(object([
        ("schema_version", number(1)),
        ("preset", string(preset)),
        ("patch", string("local v18.200.9 / crafting phase 4")),
        ("catalog_identity", string(identity(catalog_bytes))),
        ("source_identity", string(identity(&source_bytes))),
        ("village", number(44)),
        ("margin", number(3)),
        ("buildings", Json::Obj(footprints)),
        ("trap_footprints", Json::Obj(trap_footprints)),
        ("unlocks", Json::Arr(unlocks)),
        ("merges", Json::Arr(merges)),
        ("overrides", overrides),
        ("optional_buildings", Json::Arr(vec![string("crafting")])),
        ("town_halls", Json::Obj(snapshots)),
        ("hero_guardian_max_levels", level_limits),
        ("mode_unlocks", mode_unlocks),
        ("capacity_source", string(capacity_source)),
        ("level_source", string(level_source)),
    ]))
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
