//! Admission aggregates deterministic structured issues. Partial inventory never
//! disables content, overlap, bounds, levels, or policy checks.
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::content::ContentError;
use crate::stats::Level;
use clash_data::json::Json;

use super::geometry;
use super::json::{encode, identity, level_json, number, object, string};
use super::model::*;
use super::rules::{valid_level, BaseRules};

#[derive(Clone, Debug, PartialEq)]
pub struct AdmissionIssue {
    pub code: String,
    pub path: String,
    pub instances: Vec<InstanceId>,
    pub coordinates: Vec<Tile>,
    pub expected: String,
    pub actual: Json,
}

impl AdmissionIssue {
    pub fn new(code: &str, path: &str, expected: &str, actual: Json) -> Self {
        Self {
            code: code.to_owned(),
            path: path.to_owned(),
            instances: Vec::new(),
            coordinates: Vec::new(),
            expected: expected.to_owned(),
            actual,
        }
    }

    pub fn to_json(&self) -> Json {
        fn finite(value: &Json) -> Json {
            match value {
                Json::Num(v) if !v.is_finite() => string(format!("{v}")),
                Json::Arr(v) => Json::Arr(v.iter().map(finite).collect()),
                Json::Obj(v) => Json::Obj(v.iter().map(|(k, v)| (k.clone(), finite(v))).collect()),
                _ => value.clone(),
            }
        }
        object([
            ("code", string(&self.code)),
            ("path", string(&self.path)),
            (
                "instances",
                Json::Arr(self.instances.iter().map(string).collect()),
            ),
            (
                "coordinates",
                Json::Arr(
                    self.coordinates
                        .iter()
                        .map(|&(x, y)| Json::Arr(vec![number(x), number(y)]))
                        .collect(),
                ),
            ),
            ("expected", string(&self.expected)),
            ("actual", finite(&self.actual)),
        ])
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct AdmissionReport {
    pub issues: Vec<AdmissionIssue>,
}

impl AdmissionReport {
    pub fn one(issue: AdmissionIssue) -> Self {
        Self {
            issues: vec![issue],
        }
    }

    pub fn push(&mut self, code: &str, path: &str, expected: &str, actual: Json) {
        self.issues
            .push(AdmissionIssue::new(code, path, expected, actual));
    }

    pub fn to_json(&self) -> Json {
        object([
            ("accepted", Json::Bool(self.issues.is_empty())),
            (
                "issues",
                Json::Arr(self.issues.iter().map(AdmissionIssue::to_json).collect()),
            ),
        ])
    }
}

/// Only admit() constructs this receipt. No mutable access to the admitted
/// layout is exposed; proposals clone Layout and must pass admission again.
#[derive(Clone, Debug)]
pub struct AdmittedLayout {
    layout: Layout,
    physical_identity: String,
    rules_identity: String,
    catalog_identity: String,
    account_identity: String,
    policy: AdmissionPolicy,
    hole_tiles: usize,
    effective_cc_levels: Vec<Level>,
}

impl AdmittedLayout {
    pub fn layout(&self) -> &Layout {
        &self.layout
    }
    pub fn physical_identity(&self) -> &str {
        &self.physical_identity
    }
    pub fn rules_identity(&self) -> &str {
        &self.rules_identity
    }
    pub fn catalog_identity(&self) -> &str {
        &self.catalog_identity
    }
    pub fn account_identity(&self) -> &str {
        &self.account_identity
    }
    pub fn policy(&self) -> &AdmissionPolicy {
        &self.policy
    }
    pub fn hole_tiles(&self) -> usize {
        self.hole_tiles
    }
    pub fn effective_cc_levels(&self) -> &[Level] {
        &self.effective_cc_levels
    }
    pub fn engine_json(&self) -> Json {
        self.layout.to_json()
    }

    pub fn receipt(&self) -> Json {
        object([
            ("accepted", Json::Bool(true)),
            ("schema_version", number(1)),
            ("physical_identity", string(&self.physical_identity)),
            ("rules_identity", string(&self.rules_identity)),
            ("catalog_identity", string(&self.catalog_identity)),
            ("account_identity", string(&self.account_identity)),
            ("hole_tiles", Json::Num(self.hole_tiles as f64)),
            (
                "effective_cc_levels",
                Json::Arr(self.effective_cc_levels.iter().map(level_json).collect()),
            ),
            (
                "evidence",
                string("synthetic model legality; not real-game calibration"),
            ),
        ])
    }
}

fn selected(
    catalog: &Catalog,
    levels: &BTreeMap<String, Level>,
    key: &str,
    name: &str,
    th: i64,
) -> Option<Level> {
    levels.get(key).cloned().or_else(|| {
        catalog
            .stats
            .registry
            .get(name)
            .and_then(|_| catalog.stats.max_level(name, th))
            .map(Level::Int)
    })
}

fn check_level(
    report: &mut AdmissionReport,
    catalog: &Catalog,
    name: &str,
    level: Option<&Level>,
    th: i64,
    path: &str,
) -> bool {
    if level.is_some_and(|lv| valid_level(catalog, name, lv, th)) {
        return true;
    }
    report.push(
        "level_limit",
        path,
        &format!("existing {name} level available at TH{th}"),
        level.map(level_json).unwrap_or(Json::Null),
    );
    false
}

pub fn mode_allowed(key: &str, mode: Option<Mode>) -> bool {
    let Some(mode) = mode else {
        return true;
    };
    use Mode::*;
    match key {
        "at" | "cannon" | "mortar" => matches!(mode, Normal | Geared | Fast | Burst),
        "inferno" => matches!(mode, Single | Multi),
        "xbow" => matches!(mode, Ground | Both),
        "st" => matches!(mode, Rage | Poison | Invis | Eq | Quake | Earthquake),
        "sweeper" => matches!(mode, N | NE | E | SE | S | SW | W | NW),
        "firespitter" => matches!(mode, N | E | S | W),
        "mgt" => matches!(mode, Long | Short),
        "crafting" => matches!(mode, None | Cake | Candle | Hunter),
        _ => false,
    }
}

/// Checks shared with setup. Inventory and spatial checks are deliberately
/// separate so small declared synthetic engine fixtures remain usable.
pub fn content_problems(layout: &Layout, catalog: &Catalog) -> AdmissionReport {
    let mut report = AdmissionReport::default();
    let th = layout.town_hall;
    let mut heroes = BTreeSet::new();
    for (i, hero) in layout.setup.heroes.iter().enumerate() {
        let path = format!("$.heroes[{i}]");
        if !matches!(
            hero.hero.as_str(),
            "Archer Queen"
                | "Barbarian King"
                | "Grand Warden"
                | "Royal Champion"
                | "Minion Prince"
                | "Dragon Duke"
        ) {
            report.push(
                "unknown_hero",
                &path,
                "supported defending hero",
                string(&hero.hero),
            );
        }
        if !heroes.insert(&hero.hero) {
            report.push(
                "duplicate_hero",
                &path,
                "unique defending hero",
                string(&hero.hero),
            );
        }
    }
    for (i, building) in layout.buildings.iter().enumerate() {
        let path = format!("$.buildings[{i}]");
        let Some((_, bt)) = catalog
            .building_types
            .iter()
            .find(|(key, _)| key == &building.key)
        else {
            report.push(
                "unknown_building",
                &format!("{path}.key"),
                "catalog building key",
                string(&building.key),
            );
            continue;
        };
        if !mode_allowed(&building.key, building.mode) {
            report.push(
                "building_mode",
                &format!("{path}.mode"),
                "supported mode for this building",
                building
                    .mode
                    .map(|m| string(m.as_str()))
                    .unwrap_or(Json::Null),
            );
        }
        let level = if building.key == "th" {
            Some(Level::Int(th))
        } else {
            selected(catalog, &layout.setup.levels, &building.key, &bt.name, th)
        };
        let ordinary = building.key != "crafting"
            && building.key != "banner"
            && catalog.stats.registry.get(&bt.name).is_some();
        let valid = !ordinary
            || check_level(
                &mut report,
                catalog,
                &bt.name,
                level.as_ref(),
                th,
                &format!("$.levels.{}", building.key),
            );
        if building.key == "st" && valid {
            let mode = building.mode.unwrap_or(Mode::Rage).as_str();
            let required = catalog
                .setup
                .at("spell_tower_unlocks")
                .get(mode)
                .map(Json::i64);
            if !matches!((&level, required), (Some(Level::Int(lv)), Some(req)) if *lv >= req && (req != 4 || th >= 17))
            {
                report.push(
                    "spell_tower_unlock",
                    &format!("{path}.mode"),
                    "Rage L1, Poison L2, Invis L3, Earthquake L4 and TH17+",
                    string(mode),
                );
            }
        }
        if building.mode.is_some_and(Mode::geared)
            && matches!(building.key.as_str(), "at" | "cannon" | "mortar")
        {
            let minimum = catalog.setup.at("gear_minimum").at(&building.key).i64();
            if !matches!(&level, Some(Level::Int(lv)) if *lv >= minimum) {
                report.push(
                    "gear_level",
                    &format!("{path}.mode"),
                    &format!("integer level >= {minimum}"),
                    level.as_ref().map(level_json).unwrap_or(Json::Null),
                );
            } else if valid {
                let row = catalog.game_data("buildings", &bt.name, level.as_ref());
                if crate::catalog::game_int(row, "GearUpCost", 0) <= 0
                    || crate::catalog::game_int(row, "GearUpLevelRequirement", 0) <= 0
                {
                    report.push(
                        "gear_unavailable",
                        &path,
                        "positive GearUpCost and GearUpLevelRequirement",
                        string(&building.key),
                    );
                }
            }
        }
    }
    for (i, trap) in layout.traps.iter().enumerate() {
        let path = format!("$.traps[{i}]");
        let Some((_, name)) = catalog.trap_names.iter().find(|(key, _)| key == &trap.key) else {
            report.push(
                "unknown_trap",
                &format!("{path}.key"),
                "catalog trap key",
                string(&trap.key),
            );
            continue;
        };
        if let Some(mode) = trap.mode {
            if !(trap.key == "skeleton" && matches!(mode, Mode::Ground | Mode::Air)) {
                report.push(
                    "trap_mode",
                    &format!("{path}.mode"),
                    "skeleton ground/air, other traps have no mode",
                    string(mode.as_str()),
                );
            }
        }
        let lv = selected(
            catalog,
            &layout.setup.levels,
            &format!("trap:{}", trap.key),
            name,
            th,
        );
        check_level(
            &mut report,
            catalog,
            name,
            lv.as_ref(),
            th,
            &format!("$.levels.trap:{}", trap.key),
        );
    }
    for key in ["cannon", "at", "mortar"] {
        let geared: Vec<_> = layout
            .buildings
            .iter()
            .filter(|b| b.key == key && b.mode.is_some_and(Mode::geared))
            .collect();
        if geared.len() > 1 {
            report.push(
                "gear_count",
                "$.buildings",
                "at most one geared copy per key",
                number(geared.len() as i32),
            );
        }
        if th >= 17
            && key == "at"
            && !geared.is_empty()
            && layout.buildings.iter().any(|b| b.key == "mgt")
        {
            report.push(
                "geared_at_merged",
                "$.buildings",
                "geared AT consumed by MGT",
                string("geared AT + MGT"),
            );
        }
    }
    report
}

/// Fallible boundary for the checks formerly asserted by setup. Job-level
/// overrides take precedence, just as setup's merge_levels does.
pub fn validate_engine_content(
    layout: &Json,
    options: &Json,
    catalog: &Catalog,
) -> Result<(), ContentError> {
    let mut imported = Layout::from_json(layout).map_err(|r| {
        if let Some(issue) = r.issues.iter().find(|i| i.code == "unsupported_mode") {
            ContentError::unsupported("defense mode", &encode(&issue.actual))
        } else {
            ContentError::Invalid(encode(&r.to_json()))
        }
    })?;
    if let Some(value) = options.get("town_hall") {
        imported.town_hall = super::json::integer(value, "job.town_hall")
            .map_err(|r| ContentError::Invalid(encode(&r.to_json())))?
            as i64;
    }
    for (field, destination) in [
        ("defense_levels", &mut imported.setup.levels),
        ("hero_levels", &mut imported.setup.hero_levels),
    ] {
        if let Some(Json::Obj(values)) = options.get(field) {
            for (key, value) in values {
                destination.insert(
                    key.clone(),
                    super::json::level(value, field)
                        .map_err(|r| ContentError::Invalid(encode(&r.to_json())))?,
                );
            }
        }
    }
    let report = content_problems(&imported, catalog);
    if let Some(issue) = report.issues.first() {
        let kind = match issue.code.as_str() {
            "unknown_building" => Some("building"),
            "unknown_trap" => Some("trap"),
            "unknown_hero" => Some("defending hero"),
            "building_mode" | "trap_mode" => Some("defense mode"),
            _ => None,
        };
        if let Some(kind) = kind {
            return Err(ContentError::unsupported(kind, &encode(&issue.actual)));
        }
        return Err(ContentError::Invalid(encode(&report.to_json())));
    }
    Ok(())
}

fn claim(
    report: &mut AdmissionReport,
    occupied: &mut BTreeMap<Tile, InstanceId>,
    id: &str,
    origin: Tile,
    size: usize,
    path: &str,
) {
    for dx in 0..size as i64 {
        for dy in 0..size as i64 {
            let x = origin.0 as i64 + dx;
            let y = origin.1 as i64 + dy;
            if !(0..geometry::VILLAGE as i64).contains(&x)
                || !(0..geometry::VILLAGE as i64).contains(&y)
            {
                let mut issue = AdmissionIssue::new(
                    "bounds",
                    path,
                    "all footprint tiles in 0..43",
                    Json::Arr(vec![Json::Num(x as f64), Json::Num(y as f64)]),
                );
                issue.instances.push(id.to_owned());
                issue.coordinates.push(origin);
                report.issues.push(issue);
            } else {
                let tile = (x as i32, y as i32);
                if let Some(other) = occupied.get(&tile) {
                    let mut issue =
                        AdmissionIssue::new("overlap", path, "unoccupied footprint", string(other));
                    issue.instances = vec![other.clone(), id.to_owned()];
                    issue.coordinates.push(tile);
                    report.issues.push(issue);
                } else {
                    occupied.insert(tile, id.to_owned());
                }
            }
        }
    }
}

fn inventory(
    report: &mut AdmissionReport,
    actual: &BTreeMap<String, usize>,
    wanted: &BTreeMap<String, usize>,
    path: &str,
    full: bool,
    seasonal: bool,
) {
    let keys: BTreeSet<_> = actual.keys().chain(wanted.keys()).collect();
    for key in keys {
        let want = wanted.get(key).copied().unwrap_or(0);
        let have = actual.get(key).copied().unwrap_or(0);
        let code = if have > want {
            "inventory_excess"
        } else if full && have < want && !(seasonal && key == "crafting") {
            "inventory_missing"
        } else {
            continue;
        };
        report.push(
            code,
            &format!("{path}.{key}"),
            &format!("{want}"),
            Json::Num(have as f64),
        );
    }
}

fn validate_setup(layout: &Layout, catalog: &Catalog, report: &mut AdmissionReport) -> Vec<Level> {
    let th = layout.town_hall;
    // Validate even unused level selections; a typo must not silently select max.
    for (key, level) in &layout.setup.levels {
        let name = if let Some(trap) = key.strip_prefix("trap:") {
            catalog
                .trap_names
                .iter()
                .find(|(k, _)| k == trap)
                .map(|(_, name)| name.as_str())
        } else if key.starts_with("crafting:") || key == "crafting" || key == "guardian" {
            continue;
        } else {
            catalog
                .building_types
                .iter()
                .find(|(k, _)| k == key)
                .map(|(_, bt)| bt.name.as_str())
        };
        if let Some(name) = name {
            if key == "banner" {
                if level != &Level::Int(1) {
                    report.push("level_limit", "$.levels.banner", "1", level_json(level));
                }
            } else if key == "th" && level != &Level::Int(th) {
                report.push(
                    "level_limit",
                    "$.levels.th",
                    "layout Town Hall level",
                    level_json(level),
                );
            } else if catalog.stats.registry.get(name).is_some() {
                check_level(
                    report,
                    catalog,
                    name,
                    Some(level),
                    th,
                    &format!("$.levels.{key}"),
                );
            } else if level != &Level::Int(1) {
                report.push(
                    "level_limit",
                    &format!("$.levels.{key}"),
                    "model obstacle level 1",
                    level_json(level),
                );
            }
        } else {
            report.push(
                "unknown_level_key",
                &format!("$.levels.{key}"),
                "building/trap/guardian/crafting module key",
                string(key),
            );
        }
    }
    let hall = selected(catalog, &layout.setup.levels, "herohall", "Hero Hall", th);
    let hall_valid = hall
        .as_ref()
        .is_some_and(|v| valid_level(catalog, "Hero Hall", v, th));
    let has_hall = layout.buildings.iter().any(|b| b.key == "herohall");
    if !layout.setup.heroes.is_empty() && !has_hall {
        report.push(
            "hero_hall_missing",
            "$.heroes",
            "Hero Hall placement for defending heroes",
            Json::Null,
        );
    }
    let slots = if hall_valid {
        catalog
            .stats
            .get(
                "Hero Hall",
                hall.as_ref().unwrap(),
                &["Hero Slots"],
                Some(0.0),
            )
            .unwrap_or(0.0) as usize
    } else {
        0
    };
    let banner_ids: Vec<_> = layout
        .buildings
        .iter()
        .filter(|b| b.key == "banner")
        .map(|b| &b.id)
        .collect();
    if layout.setup.heroes.len() > slots || layout.setup.heroes.len() > banner_ids.len() {
        report.push(
            "hero_capacity",
            "$.heroes",
            &format!(
                "<= {} Hero Hall slots and {} banners",
                slots,
                banner_ids.len()
            ),
            number(layout.setup.heroes.len() as i32),
        );
    }
    for (i, hero) in layout.setup.heroes.iter().enumerate() {
        if hero.banner.as_ref() != banner_ids.get(i).copied() {
            report.push(
                "hero_banner_order",
                &format!("$.heroes[{i}]"),
                "binding matches ordered engine banner zip",
                string(&hero.hero),
            );
        }
        if catalog.stats.registry.get(&hero.hero).is_none() {
            continue;
        }
        let lv = selected(
            catalog,
            &layout.setup.hero_levels,
            &hero.hero,
            &hero.hero,
            th,
        );
        if check_level(
            report,
            catalog,
            &hero.hero,
            lv.as_ref(),
            th,
            &format!("$.hero_levels.{}", hero.hero),
        ) && hall_valid
        {
            let required = catalog
                .stats
                .get(
                    &hero.hero,
                    lv.as_ref().unwrap(),
                    &["Hero Hall Level Required"],
                    Some(1.0),
                )
                .unwrap_or(1.0);
            if !matches!(&hall, Some(Level::Int(h)) if *h as f64 >= required) {
                report.push(
                    "hero_unlock",
                    &format!("$.heroes[{i}]"),
                    "Hero Hall meets selected hero level requirement",
                    Json::Num(required),
                );
            }
        }
    }
    for (hero, lv) in &layout.setup.hero_levels {
        if !matches!(
            hero.as_str(),
            "Archer Queen"
                | "Barbarian King"
                | "Grand Warden"
                | "Royal Champion"
                | "Minion Prince"
                | "Dragon Duke"
        ) {
            report.push(
                "unknown_hero",
                &format!("$.hero_levels.{hero}"),
                "supported hero",
                string(hero),
            );
        } else {
            check_level(
                report,
                catalog,
                hero,
                Some(lv),
                th,
                &format!("$.hero_levels.{hero}"),
            );
        }
    }
    if let Some(name) = &layout.setup.guardian {
        let known = catalog
            .stats
            .registry
            .get(name)
            .is_some_and(|r| r.at("kind").str() == "guardian")
            && catalog.units.contains_key(name);
        if !known {
            report.push(
                "guardian_unavailable",
                "$.guardian",
                "supported guardian",
                string(name),
            );
        } else if th >= 18 {
            if !layout.buildings.iter().any(|b| b.key == "th") {
                report.push(
                    "guardian_town_hall",
                    "$.guardian",
                    "TH placement",
                    Json::Null,
                );
            }
            let lv = selected(catalog, &layout.setup.levels, "guardian", name, th);
            check_level(report, catalog, name, lv.as_ref(), th, "$.levels.guardian");
        } else if name != "Longshot" {
            report.push(
                "guardian_unavailable",
                "$.guardian",
                "guardian active only at TH18; legacy Longshot default is inert",
                string(name),
            );
        }
    } else if layout.setup.levels.contains_key("guardian") {
        report.push(
            "guardian_unavailable",
            "$.levels.guardian",
            "selected guardian",
            Json::Null,
        );
    }
    for (key, lv) in &layout.setup.levels {
        if key.starts_with("crafting:")
            && !matches!(
                key.as_str(),
                "crafting:hitpoints" | "crafting:damage" | "crafting:effect"
            )
        {
            report.push(
                "unknown_level_key",
                &format!("$.levels.{key}"),
                "crafting hitpoints/damage/effect",
                string(key),
            );
        }
        if key == "guardian" && th < 18 {
            report.push(
                "guardian_unavailable",
                "$.levels.guardian",
                "TH18+",
                level_json(lv),
            );
        }
    }
    let craft = layout.buildings.iter().find(|b| b.key == "crafting");
    let crafted_name = craft
        .and_then(|b| b.mode)
        .and_then(|m| catalog.setup.at("crafted").get(m.as_str()))
        .map(Json::str);
    for key in [
        "crafting",
        "crafting:hitpoints",
        "crafting:damage",
        "crafting:effect",
    ] {
        if let Some(lv) = layout.setup.levels.get(key) {
            if let Some(name) = crafted_name {
                check_level(
                    report,
                    catalog,
                    name,
                    Some(lv),
                    th,
                    &format!("$.levels.{key}"),
                );
            } else {
                // Legacy layouts retain account module levels when their
                // optional station is inactive or omitted. Keep that ledger,
                // while requiring a level supported by this season's modes.
                let supported = catalog
                    .setup
                    .at("crafting")
                    .at("modes")
                    .arr()
                    .iter()
                    .any(|mode| {
                        let name = catalog.setup.at("crafted").at(mode.str()).str();
                        matches!(lv, Level::Int(_)) && valid_level(catalog, name, lv, th)
                    });
                if !supported {
                    report.push(
                        "level_limit",
                        &format!("$.levels.{key}"),
                        "module level supported by a phase-4 crafted defense",
                        level_json(lv),
                    );
                }
            }
        }
    }
    let castle = layout
        .buildings
        .iter()
        .any(|b| b.key == "cc")
        .then(|| selected(catalog, &layout.setup.levels, "cc", "Clan Castle", th))
        .flatten();
    let valid_castle = castle
        .as_ref()
        .is_some_and(|lv| valid_level(catalog, "Clan Castle", lv, th));
    if !layout.setup.cc_troops.is_empty() && !valid_castle {
        report.push(
            "cc_missing",
            "$.cc_troops",
            "valid Clan Castle placement and level",
            Json::Null,
        );
    }
    let mut housing = 0i64;
    let mut effective = Vec::new();
    for (i, entry) in layout.setup.cc_troops.iter().enumerate() {
        let path = format!("$.cc_troops[{i}]");
        if !(1..=1000).contains(&entry.count) {
            report.push("cc_count", &path, "count 1..1000", number(entry.count));
            continue;
        }
        let Some(record) = catalog.stats.registry.get(&entry.name) else {
            report.push("cc_unit", &path, "known donated troop", string(&entry.name));
            continue;
        };
        if !matches!(record.at("kind").str(), "troop" | "super_troop")
            || !catalog.units.contains_key(&entry.name)
            || catalog
                .setup
                .at("donated_laboratory")
                .get(&entry.name)
                .is_none()
        {
            report.push(
                "cc_donation",
                &path,
                "engine-supported donatable troop",
                string(&entry.name),
            );
            continue;
        }
        let lv = entry
            .level
            .clone()
            .or_else(|| catalog.stats.max_level(&entry.name, 18).map(Level::Int));
        if !check_level(
            report,
            catalog,
            &entry.name,
            lv.as_ref(),
            18,
            &format!("{path}.level"),
        ) {
            continue;
        }
        let Some(Level::Int(mut lv)) = lv else {
            report.push("cc_level", &path, "integer donated troop level", Json::Null);
            continue;
        };
        housing += catalog.numbers(&entry.name, &Level::Int(lv)).housing * entry.count as i64;
        if valid_castle {
            if let Some(cap) = catalog.stats.get(
                "Clan Castle",
                castle.as_ref().unwrap(),
                &["~Laboratory Level Cap"],
                None,
            ) {
                let required = catalog.setup.at("donated_laboratory").at(&entry.name);
                while lv > 1
                    && required
                        .get(&lv.to_string())
                        .and_then(Json::opt_f64)
                        .is_some_and(|v| v > cap)
                {
                    lv -= 1;
                }
            }
        }
        effective.push(Level::Int(lv));
    }
    if valid_castle {
        let capacity = catalog
            .stats
            .get(
                "Clan Castle",
                castle.as_ref().unwrap(),
                &["Troop Capacity"],
                Some(0.0),
            )
            .unwrap_or(0.0);
        if housing as f64 > capacity {
            report.push(
                "cc_housing",
                "$.cc_troops",
                &format!("housing <= {capacity}"),
                Json::Num(housing as f64),
            );
        }
    }
    effective
}

pub fn admit(
    mut layout: Layout,
    rules: &BaseRules,
    catalog: Arc<Catalog>,
    policy: &AdmissionPolicy,
) -> Result<AdmittedLayout, AdmissionReport> {
    let mut report = AdmissionReport::default();
    let Some(th_rules) = rules.town_halls.get(&layout.town_hall) else {
        return Err(AdmissionReport::one(AdmissionIssue::new(
            "town_hall",
            "$.town_hall",
            "16, 17 or 18",
            Json::Num(layout.town_hall as f64),
        )));
    };
    let (wanted_buildings, wanted_traps, wall_limit, account_id) = match &policy.inventory {
        InventoryPolicy::FullyMerged => (
            &th_rules.buildings,
            &th_rules.traps,
            th_rules.walls,
            "fully-merged-preset".to_owned(),
        ),
        InventoryPolicy::Owned {
            snapshot_id,
            buildings,
            traps,
            walls,
            levels,
            hero_levels,
            wall_level,
            wall_levels,
            geared,
        } => {
            // Check source consumption against unmerged unlocks, allowing accounts
            // that have not yet completed every optional building merge.
            let mut consumed = buildings.clone();
            for recipe in rules.document.at("merges").arr() {
                if recipe.at("product").str() == "Town Hall" {
                    continue;
                }
                let product = recipe.at("product").str();
                let count = catalog
                    .building_types
                    .iter()
                    .find(|(_, bt)| bt.name == product)
                    .and_then(|(k, _)| buildings.get(k))
                    .copied()
                    .unwrap_or(0);
                for ingredient in recipe.at("recipe").arr() {
                    if let Some((key, _)) = catalog
                        .building_types
                        .iter()
                        .find(|(_, bt)| bt.name == ingredient.at("name").str())
                    {
                        let value = consumed.entry(key.clone()).or_default();
                        *value = value.saturating_add(count);
                    }
                }
            }
            inventory(
                &mut report,
                &consumed,
                &th_rules.unmerged,
                "$account.buildings",
                false,
                false,
            );
            if layout.town_hall >= 17 && buildings.get("eagle").copied().unwrap_or(0) > 0 {
                report.push(
                    "account_merge",
                    "$account.buildings.eagle",
                    "Eagle consumed by TH17 upgrade",
                    number(1),
                );
            }
            inventory(
                &mut report,
                traps,
                &th_rules.traps,
                "$account.traps",
                false,
                false,
            );
            if *walls > th_rules.walls {
                report.push(
                    "account_inventory",
                    "$account.walls",
                    "within TH wall unlocks",
                    Json::Num(*walls as f64),
                );
                return Err(report);
            }
            for building in &layout.buildings {
                if !matches!(
                    building.key.as_str(),
                    "th" | "banner" | "helper" | "bob" | "crafting"
                ) && !levels.contains_key(&building.key)
                {
                    report.push(
                        "account_level_missing",
                        &format!("$account.levels.{}", building.key),
                        "explicit owned level",
                        Json::Null,
                    );
                }
                if building.mode.is_some_and(Mode::geared) && !geared.contains(&building.key) {
                    report.push(
                        "account_gear",
                        &format!("$account.geared.{}", building.key),
                        "owned gear-up unlock",
                        string(&building.key),
                    );
                }
                if building.key == "crafting"
                    && !matches!(building.mode, None | Some(Mode::None))
                    && !levels.contains_key("crafting")
                {
                    report.push(
                        "account_level_missing",
                        "$account.levels.crafting",
                        "explicit owned crafted module level",
                        Json::Null,
                    );
                }
            }
            for (key, count) in buildings {
                if *count > 0
                    && !matches!(
                        key.as_str(),
                        "th" | "banner" | "helper" | "bob" | "crafting"
                    )
                    && !levels.contains_key(key)
                {
                    report.push(
                        "account_level_missing",
                        &format!("$account.levels.{key}"),
                        "explicit level for every owned building",
                        Json::Null,
                    );
                }
            }
            for (key, count) in traps {
                let level_key = format!("trap:{key}");
                if *count > 0 && !levels.contains_key(&level_key) {
                    report.push(
                        "account_level_missing",
                        &format!("$account.levels.{level_key}"),
                        "explicit level for every owned trap",
                        Json::Null,
                    );
                }
            }
            for trap in &layout.traps {
                let key = format!("trap:{}", trap.key);
                if !levels.contains_key(&key) {
                    report.push(
                        "account_level_missing",
                        &format!("$account.levels.{key}"),
                        "explicit owned trap level",
                        Json::Null,
                    );
                }
            }
            for hero in &layout.setup.heroes {
                if !hero_levels.contains_key(&hero.hero) {
                    report.push(
                        "account_level_missing",
                        &format!("$account.hero_levels.{}", hero.hero),
                        "explicit owned hero level",
                        Json::Null,
                    );
                }
            }
            if layout.setup.guardian.is_some()
                && layout.town_hall >= 18
                && !levels.contains_key("guardian")
            {
                report.push(
                    "account_level_missing",
                    "$account.levels.guardian",
                    "explicit owned guardian level",
                    Json::Null,
                );
            }
            for (key, lv) in levels {
                if layout.setup.levels.get(key).is_some_and(|v| v != lv) {
                    report.push(
                        "account_level",
                        &format!("$.levels.{key}"),
                        "fixed owned level",
                        level_json(lv),
                    );
                }
                layout.setup.levels.insert(key.clone(), lv.clone());
            }
            for (key, lv) in hero_levels {
                if layout.setup.hero_levels.get(key).is_some_and(|v| v != lv) {
                    report.push(
                        "account_level",
                        &format!("$.hero_levels.{key}"),
                        "fixed owned hero level",
                        level_json(lv),
                    );
                }
                layout.setup.hero_levels.insert(key.clone(), lv.clone());
            }
            if layout
                .setup
                .wall_level
                .as_ref()
                .is_some_and(|v| v != wall_level)
            {
                report.push(
                    "account_level",
                    "$.wall_level",
                    "fixed owned wall level",
                    level_json(wall_level),
                );
            }
            let owned_wall_levels: Vec<_> = if wall_levels.is_empty() {
                vec![wall_level.clone(); *walls]
            } else {
                wall_levels.clone()
            };
            if owned_wall_levels.len() != *walls {
                report.push(
                    "account_wall_levels",
                    "$account.wall_levels",
                    "one level per owned wall",
                    number(owned_wall_levels.len() as i32),
                );
            }
            let mut available = BTreeMap::<String, usize>::new();
            for lv in &owned_wall_levels {
                check_level(
                    &mut report,
                    &catalog,
                    "Wall",
                    Some(lv),
                    layout.town_hall,
                    "$account.wall_levels",
                );
                *available.entry(lv.to_string()).or_default() += 1;
            }
            for wall in &layout.walls {
                let lv = wall.level.as_ref().unwrap_or(wall_level);
                let count = available.entry(lv.to_string()).or_default();
                if *count == 0 {
                    report.push(
                        "account_wall_levels",
                        "$.wall_levels",
                        "subset of fixed owned wall-level multiset",
                        level_json(lv),
                    );
                } else {
                    *count -= 1;
                }
            }
            layout.setup.wall_level = Some(wall_level.clone());
            (buildings, traps, *walls, snapshot_id.clone())
        }
    };
    report
        .issues
        .extend(content_problems(&layout, &catalog).issues);
    let mut occupied = BTreeMap::new();
    let mut ids = BTreeSet::new();
    let mut building_counts = BTreeMap::new();
    let mut trap_counts = BTreeMap::new();
    for (i, b) in layout.buildings.iter().enumerate() {
        *building_counts.entry(b.key.clone()).or_default() += 1;
        if let Some((_, bt)) = catalog.building_types.iter().find(|(key, _)| key == &b.key) {
            claim(
                &mut report,
                &mut occupied,
                &b.id,
                b.position,
                bt.size,
                &format!("$.buildings[{i}]"),
            );
        }
    }
    for (i, w) in layout.walls.iter().enumerate() {
        claim(
            &mut report,
            &mut occupied,
            &w.id,
            w.position,
            1,
            &format!("$.walls[{i}]"),
        );
    }
    for (i, t) in layout.traps.iter().enumerate() {
        *trap_counts.entry(t.key.clone()).or_default() += 1;
        let size = catalog
            .trap_sizes
            .iter()
            .find(|(k, _)| k == &t.key)
            .map_or(1, |(_, s)| *s);
        claim(
            &mut report,
            &mut occupied,
            &t.id,
            t.position,
            size,
            &format!("$.traps[{i}]"),
        );
    }
    for id in layout
        .buildings
        .iter()
        .map(|b| &b.id)
        .chain(layout.walls.iter().map(|w| &w.id))
        .chain(layout.traps.iter().map(|t| &t.id))
    {
        if id.is_empty() || !ids.insert(id) {
            report.push(
                "instance_id",
                "$.instance_ids",
                "nonempty globally unique IDs",
                string(id),
            );
        }
    }
    inventory(
        &mut report,
        &building_counts,
        wanted_buildings,
        "$.buildings",
        policy.require_full,
        true,
    );
    inventory(
        &mut report,
        &trap_counts,
        wanted_traps,
        "$.traps",
        policy.require_full,
        false,
    );
    if layout.walls.len() > wall_limit {
        report.push(
            "wall_count",
            "$.walls",
            &format!("<= {wall_limit}"),
            number(layout.walls.len() as i32),
        );
    }
    if policy.require_all_walls && layout.walls.len() != wall_limit {
        report.push(
            "walls_missing",
            "$.walls",
            &format!("exactly {wall_limit}"),
            number(layout.walls.len() as i32),
        );
    }
    if let Some(lv) = &layout.setup.wall_level {
        check_level(
            &mut report,
            &catalog,
            "Wall",
            Some(lv),
            layout.town_hall,
            "$.wall_level",
        );
    }
    let default_wall = layout.setup.wall_level.clone().or_else(|| {
        catalog
            .stats
            .max_level("Wall", layout.town_hall)
            .map(Level::Int)
    });
    for (i, wall) in layout.walls.iter_mut().enumerate() {
        if wall.level.is_none() {
            wall.level = default_wall.clone();
        }
        check_level(
            &mut report,
            &catalog,
            "Wall",
            wall.level.as_ref(),
            layout.town_hall,
            &format!("$.wall_levels[{i}].level"),
        );
    }
    let effective_cc_levels = validate_setup(&layout, &catalog, &mut report);
    if let HolePolicy::Penalize { per_tile } = policy.holes {
        if !per_tile.is_finite() || per_tile < 0.0 {
            report.push(
                "hole_policy",
                "$policy.holes",
                "finite nonnegative per-tile penalty",
                Json::Num(per_tile),
            );
        }
    }
    // Do not invoke footprint geometry on malformed or out-of-bounds content.
    if !report.issues.is_empty() {
        return Err(report);
    }
    let sizes: Vec<_> = catalog
        .building_types
        .iter()
        .map(|(k, bt)| (k.clone(), bt.size))
        .collect();
    let hole_tiles: usize = geometry::holes(&geometry::blocked(&layout, &sizes), 44, 3)
        .iter()
        .map(BTreeSet::len)
        .sum();
    if matches!(policy.holes, HolePolicy::Forbid) && hole_tiles > 0 {
        report.push(
            "deploy_holes",
            "$.buildings",
            "zero enclosed deployable tiles",
            number(hole_tiles as i32),
        );
        return Err(report);
    }
    // Freeze implicit account defaults before the layout enters search.
    for (key, bt) in &catalog.building_types {
        if wanted_buildings.get(key).copied().unwrap_or(0) > 0
            && !matches!(key.as_str(), "th" | "banner" | "crafting")
            && catalog.stats.registry.get(&bt.name).is_some()
        {
            if let Some(lv) = catalog.stats.max_level(&bt.name, layout.town_hall) {
                layout
                    .setup
                    .levels
                    .entry(key.clone())
                    .or_insert(Level::Int(lv));
            }
        }
    }
    for (key, name) in &catalog.trap_names {
        if wanted_traps.get(key).copied().unwrap_or(0) > 0 {
            if let Some(lv) = catalog.stats.max_level(name, layout.town_hall) {
                layout
                    .setup
                    .levels
                    .entry(format!("trap:{key}"))
                    .or_insert(Level::Int(lv));
            }
        }
    }
    if matches!(policy.inventory, InventoryPolicy::FullyMerged) {
        for name in [
            "Archer Queen",
            "Barbarian King",
            "Grand Warden",
            "Royal Champion",
            "Minion Prince",
            "Dragon Duke",
        ] {
            if let Some(lv) = catalog.stats.max_level(name, layout.town_hall) {
                layout
                    .setup
                    .hero_levels
                    .entry(name.to_owned())
                    .or_insert(Level::Int(lv));
            }
        }
    }
    layout.setup.wall_level = default_wall;
    let mut physical = layout.to_json();
    if let Json::Obj(fields) = &mut physical {
        fields.retain(|(k, _)| {
            !matches!(
                k.as_str(),
                "name" | "notes" | "instance_ids" | "layout_schema"
            )
        });
    }
    // Setup sorts walls by coordinate; wall array order has no runtime meaning.
    if let Json::Obj(fields) = &mut physical {
        for (key, value) in fields {
            if matches!(key.as_str(), "walls" | "wall_levels") {
                if let Json::Arr(values) = value {
                    values.sort_by_key(encode);
                }
            }
        }
    }
    let physical_identity = identity(encode(&physical).as_bytes());
    let mut account_wall_levels: Vec<_> = match &policy.inventory {
        InventoryPolicy::Owned {
            wall_levels,
            wall_level,
            walls,
            ..
        } => {
            if wall_levels.is_empty() {
                vec![level_json(wall_level); *walls]
            } else {
                wall_levels.iter().map(level_json).collect()
            }
        }
        InventoryPolicy::FullyMerged => {
            let mut values: Vec<_> = layout
                .walls
                .iter()
                .filter_map(|w| w.level.as_ref().map(level_json))
                .collect();
            values.extend((values.len()..wall_limit).map(|_| {
                layout
                    .setup
                    .wall_level
                    .as_ref()
                    .map(level_json)
                    .unwrap_or(Json::Null)
            }));
            values
        }
    };
    account_wall_levels.sort_by_key(encode);
    let counts_json = |values: &BTreeMap<String, usize>| {
        Json::Obj(
            values
                .iter()
                .map(|(key, count)| (key.clone(), Json::Num(*count as f64)))
                .collect(),
        )
    };
    let account_inventory = object([
        ("buildings", counts_json(wanted_buildings)),
        ("traps", counts_json(wanted_traps)),
        ("walls", Json::Num(wall_limit as f64)),
    ]);
    let account = object([
        ("snapshot_id", string(account_id)),
        ("inventory", account_inventory),
        ("levels", physical.at("levels").clone()),
        ("hero_levels", physical.at("hero_levels").clone()),
        ("wall_levels", Json::Arr(account_wall_levels)),
        ("wall_level", physical.at("wall_level").clone()),
    ]);
    Ok(AdmittedLayout {
        layout,
        physical_identity,
        rules_identity: rules.identity.clone(),
        catalog_identity: rules.catalog_identity.clone(),
        account_identity: identity(encode(&account).as_bytes()),
        policy: policy.clone(),
        hole_tiles,
        effective_cc_levels,
    })
}
