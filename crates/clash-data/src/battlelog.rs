//! Shared share-code decoding and observation identity.
use crate::json::Json;
use crate::wire::*;
use std::collections::BTreeMap;
use std::path::Path;

pub struct Decoder {
    names: BTreeMap<(String, i64), String>,
}

impl Decoder {
    pub fn from_names(names: BTreeMap<(String, i64), String>) -> Self {
        Self { names }
    }

    pub fn load(root: &Path) -> Result<Self, String> {
        let data = read(&root.join("data/source/clashking-static-data.json"))?;
        let mut names = BTreeMap::new();
        for (section, kind, offset) in [
            ("troops", "troop", 4_000_000),
            ("spells", "spell", 26_000_000),
            ("heroes", "hero", 28_000_000),
            ("pets", "pet", 73_000_000),
            ("equipment", "equipment", 90_000_000),
        ] {
            for entry in list(&data, section) {
                names.insert(
                    (kind.to_owned(), entry.at("_id").i64() - offset),
                    text(entry, "name", "").to_owned(),
                );
            }
        }
        Ok(Self { names })
    }

    fn name(&self, kind: &str, index: i64) -> String {
        self.names
            .get(&(kind.to_owned(), index))
            .cloned()
            .unwrap_or_else(|| format!("{kind}#{index}"))
    }

    pub fn decode(&self, code: &str) -> Result<Json, String> {
        let mut sections = BTreeMap::new();
        let mut start = None;
        for (index, character) in code.char_indices() {
            if "hiuds".contains(character) {
                if let Some((key, offset)) = start {
                    sections.insert(key, &code[offset..index]);
                }
                start = Some((character, index + 1));
            }
        }
        if let Some((key, offset)) = start {
            sections.insert(key, &code[offset..]);
        }
        let mut out = obj([] as [(&str, Json); 0]);
        if let Some(heroes) = sections.get(&'h') {
            let mut decoded = Vec::new();
            for part in heroes.split('-') {
                let mut index = 0;
                let digits = |index: &mut usize| -> Option<i64> {
                    let start = *index;
                    while part.as_bytes().get(*index).is_some_and(u8::is_ascii_digit) {
                        *index += 1;
                    }
                    part[start..*index].parse().ok()
                };
                let hero = digits(&mut index);
                let mut mode = None;
                let mut pet = None;
                let mut equipment = Vec::new();
                let mut valid = hero.is_some();
                for key in ['m', 'p', 'e'] {
                    if part.as_bytes().get(index) != Some(&(key as u8)) {
                        continue;
                    }
                    index += 1;
                    let number = digits(&mut index);
                    valid &= number.is_some();
                    match key {
                        'm' => mode = number,
                        'p' => pet = number,
                        _ => {
                            if let Some(number) = number {
                                equipment.push(number);
                            }
                            while part.as_bytes().get(index) == Some(&b'_') {
                                index += 1;
                                match digits(&mut index) {
                                    Some(number) => equipment.push(number),
                                    None => valid = false,
                                }
                            }
                        }
                    }
                }
                valid &= index == part.len();
                if valid {
                    decoded.push(obj([
                        (
                            "hero",
                            string(self.name("hero", hero.expect("parsed hero"))),
                        ),
                        ("mode", mode.map_or(Json::Null, |value| num(value as f64))),
                        (
                            "pet",
                            pet.map_or(Json::Null, |value| string(self.name("pet", value))),
                        ),
                        (
                            "equipment",
                            arr(equipment
                                .into_iter()
                                .map(|value| string(self.name("equipment", value)))),
                        ),
                    ]));
                } else {
                    decoded.push(obj([
                        ("hero", string(format!("unparsed:{part}"))),
                        ("pet", Json::Null),
                        ("equipment", arr([])),
                    ]));
                }
            }
            put(&mut out, "heroes", arr(decoded));
        }
        for (key, label, kind) in [
            ('u', "troops", "troop"),
            ('s', "spells", "spell"),
            ('i', "cc_troops", "troop"),
            ('d', "cc_spells", "spell"),
        ] {
            if let Some(section) = sections.get(&key).filter(|section| !section.is_empty()) {
                let mut items = Vec::new();
                for part in section.split('-') {
                    let (count, index) = part.split_once('x').ok_or("undecodable_army")?;
                    let count: i64 = count.parse().map_err(|_| "undecodable_army")?;
                    let index: i64 = index.parse().map_err(|_| "undecodable_army")?;
                    if count <= 0 || index < 0 {
                        return Err("undecodable_army".to_owned());
                    }
                    items.push(arr([num(count as f64), string(self.name(kind, index))]));
                }
                put(&mut out, label, arr(items));
            }
        }
        Ok(out)
    }
}

pub fn identity(battle: &Json) -> Result<String, String> {
    let timestamp = battle
        .get("battleTimestamp")
        .and_then(Json::opt_str)
        .ok_or("missing timestamp")?;
    let th = number(battle, "opponentTownHallLevel", 0.0);
    let payload = format!(
        "[{},{},{}]",
        ascii_string(timestamp),
        th as i64,
        ascii_string(text(battle, "armyShareCode", ""))
    );
    Ok(sha256(payload.as_bytes()))
}
