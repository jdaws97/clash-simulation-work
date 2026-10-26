//! CSV quoting, inherited cells and positional level clamping from specs.py.

use std::path::Path;

use clash_data::json::Json;
use clash_data::wire::{put, string};

use super::{empty, field, items, required_text, EMPTY};

pub(super) fn parse(source: &str) -> Result<Vec<Vec<String>>, String> {
    let mut rows = Vec::new();
    let mut row = Vec::new();
    let mut cell = String::new();
    let mut quoted = false;
    let mut chars = source.chars().peekable();
    while let Some(ch) = chars.next() {
        match ch {
            '"' if quoted && chars.peek() == Some(&'"') => {
                cell.push('"');
                chars.next();
            }
            '"' => quoted = !quoted,
            ',' if !quoted => row.push(std::mem::take(&mut cell)),
            '\n' if !quoted => {
                if !row.is_empty() || !cell.is_empty() {
                    row.push(std::mem::take(&mut cell));
                    rows.push(std::mem::take(&mut row));
                }
            }
            '\r' if !quoted => {}
            _ => cell.push(ch),
        }
    }
    if quoted {
        return Err("unterminated quoted CSV field".to_owned());
    }
    if !row.is_empty() || !cell.is_empty() {
        row.push(cell);
        rows.push(row);
    }
    Ok(rows)
}

pub(super) struct Tables {
    pub data: Json,
    pub ranges: Json,
    pub delays: Json,
}

impl Tables {
    pub fn load(root: &Path) -> Result<Self, String> {
        let mut result = Self {
            data: empty(),
            ranges: empty(),
            delays: empty(),
        };
        for table in [
            "buildings",
            "characters",
            "heroes",
            "pets",
            "projectiles",
            "special_abilities",
            "spells",
        ] {
            let path = root
                .join("data/source/gamecsv/v18.200.9")
                .join(format!("{table}.csv"));
            let rows = parse(&required_text(&path)?)?;
            let header = rows
                .first()
                .ok_or_else(|| format!("empty CSV {}", path.display()))?;
            let mut resolved = empty();
            let mut current = "";
            let mut inherited = empty();
            for row in rows.iter().skip(2) {
                if row.is_empty() {
                    continue;
                }
                if !row[0].is_empty() {
                    current = &row[0];
                    inherited = empty();
                }
                if current.is_empty() {
                    continue;
                }
                for (key, value) in header.iter().zip(row) {
                    if !value.is_empty() {
                        put(&mut inherited, key, string(value));
                    }
                }
                if resolved.get(current).is_none() {
                    put(&mut resolved, current, Json::Arr(Vec::new()));
                }
                if let Json::Arr(values) = super::get_mut(&mut resolved, current) {
                    values.push(inherited.clone());
                }
            }
            if ["characters", "heroes", "pets"].contains(&table) {
                let range = header.iter().position(|key| key == "AttackRange");
                let alt = header.iter().position(|key| key == "AltAttackRange");
                let delay = header.iter().position(|key| key == "NewTargetAttackDelay");
                let mut current = "";
                for row in rows.iter().skip(2) {
                    if row.is_empty() {
                        continue;
                    }
                    if !row[0].is_empty() {
                        current = &row[0];
                    }
                    if !row[0].is_empty() && result.ranges.get(current).is_none() {
                        if let Some(value) = range
                            .and_then(|i| row.get(i))
                            .and_then(|v| v.parse::<f64>().ok())
                        {
                            put(&mut result.ranges, current, Json::Num(value / 100.0));
                            if let Some(value) = alt
                                .and_then(|i| row.get(i))
                                .and_then(|v| v.parse::<f64>().ok())
                            {
                                put(
                                    &mut result.ranges,
                                    &format!("{current}|alt"),
                                    Json::Num(value / 100.0),
                                );
                            }
                        }
                    }
                    if table != "pets"
                        && !current.is_empty()
                        && result.delays.get(current).is_none()
                    {
                        if let Some(value) = delay
                            .and_then(|i| row.get(i))
                            .and_then(|v| v.parse::<f64>().ok())
                        {
                            put(&mut result.delays, current, Json::Num(value / 1000.0));
                        }
                    }
                }
            }
            put(&mut result.data, table, resolved);
        }
        for (name, alias) in RANGE_ALIASES {
            if let Some(value) = result.ranges.get(alias).cloned() {
                put(&mut result.ranges, name, value);
            }
        }
        for (name, alias) in [
            ("Bat", "Spell Bat"),
            ("Frostmite", "Icemite"),
            ("Firemite", "Firemite Spawn"),
            ("The Disarmer", "Disarmer"),
        ] {
            if let Some(value) = result.delays.get(alias).cloned() {
                put(&mut result.delays, name, value);
            }
        }
        Ok(result)
    }

    pub fn row(&self, table: &str, name: &str, level: i64) -> &Json {
        let rows = items(field(field(&self.data, table), name));
        if rows.is_empty() {
            return &EMPTY;
        }
        &rows[(level.max(1) as usize).min(rows.len()) - 1]
    }

    pub fn unit(&self, name: &str, level: i64) -> &Json {
        let name = UNIT_ALIASES
            .iter()
            .find(|(key, _)| *key == name)
            .map_or(name, |(_, alias)| alias);
        for table in ["characters", "heroes", "pets"] {
            let row = self.row(table, name, level);
            if !super::entries(row).is_empty() {
                return row;
            }
        }
        &EMPTY
    }
}

const UNIT_ALIASES: &[(&str, &str)] = &[
    ("Frostmite", "Icemite"),
    ("Firemite", "Firemite Spawn"),
    ("Ice Pup", "Ice Hound Pup"),
    ("Lavaloon", "GW Equipment Lavaloon"),
    ("Lavaloon Pup", "GW Equipment Lavaloon Pup"),
    ("Snake", "BK Equipment Snake"),
    ("Bat", "Spell Bat"),
    ("Henchman", "MP Equipment Henchman"),
    ("Spell Skeleton", "Spell Shielded Skeleton"),
    ("L.A.S.S.I", "LASSI"),
    ("Greedy Raven", "Crow"),
];
const RANGE_ALIASES: &[(&str, &str)] = &[
    ("P.E.K.K.A", "PEKKA"),
    ("Pumpkin Barbarian", "Pumpkin Barbarian Armored"),
    ("M.E.C.H.A", "MECHA"),
    ("C.O.O.K.I.E", "COOKIE"),
    ("Debt Collector", "Tax Collector"),
    ("K.A.N.E", "KANE"),
    ("The Disarmer", "Disarmer"),
    ("L.A.S.S.I", "LASSI"),
    ("Greedy Raven", "Crow"),
    ("Frostmite", "Icemite"),
    ("Firemite", "Firemite Spawn"),
    ("Ice Pup", "Ice Hound Pup"),
    ("Lavaloon", "GW Equipment Lavaloon"),
    ("Lavaloon Pup", "GW Equipment Lavaloon Pup"),
    ("Spell Skeleton", "Spell Shielded Skeleton"),
    ("Bat", "Spell Bat"),
    ("Henchman", "MP Equipment Henchman"),
    ("Snake", "BK Equipment Snake"),
];
