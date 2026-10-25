//! Army share-code decoding and exact observed build construction.

use std::collections::BTreeMap;
use std::path::Path;

use baselab_engine::json::Json;
use baselab_engine::plans::spell_key;

use super::io::*;

pub struct Decoder {
    names: BTreeMap<(String, i64), String>,
}

impl Decoder {
    pub fn load(root: &Path) -> Result<Self, String> {
        let data = read(&root.join("data/clashking-static-data.json"))?;
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

    pub fn build(&self, code: &str, th: i64, index: usize) -> Result<Json, String> {
        let army = self.decode(code)?;
        if list(&army, "troops").is_empty() {
            return Err("undecodable_army".to_owned());
        }
        let mut unknown = Vec::new();
        let mut troops = obj([] as [(&str, Json); 0]);
        let mut spells = troops.clone();
        let mut cc = troops.clone();
        for (section, target, is_spell) in [
            ("troops", &mut troops, false),
            ("spells", &mut spells, true),
        ] {
            for pair in list(&army, section) {
                let pair = pair.arr();
                let name = pair[1].str();
                if name.contains('#') || is_spell && spell_key(name).is_none() {
                    unknown.push(name.to_owned());
                }
                // Python troop dict uses the last occurrence; spells sum duplicates.
                let previous = if is_spell {
                    number(target, name, 0.0)
                } else {
                    0.0
                };
                put(target, name, num(previous + pair[0].f64()));
            }
        }
        for section in ["cc_troops", "cc_spells"] {
            for pair in list(&army, section) {
                let pair = pair.arr();
                let name = pair[1].str();
                if name.contains('#') || name.ends_with("Spell") && spell_key(name).is_none() {
                    unknown.push(name.to_owned());
                }
                let previous = number(&cc, name, 0.0);
                put(&mut cc, name, num(previous + pair[0].f64()));
            }
        }
        let mut heroes = Vec::new();
        let mut loadouts = obj([] as [(&str, Json); 0]);
        let mut warden = None;
        for hero in list(&army, "heroes") {
            let name = text(hero, "hero", "");
            if name.contains('#') || name.starts_with("unparsed:") {
                unknown.push(name.to_owned());
            }
            let mut equipment = list(hero, "equipment").to_vec();
            for value in &equipment {
                if value.str().contains('#') {
                    unknown.push(value.str().to_owned());
                }
            }
            equipment.resize(2, Json::Null);
            let pet = hero.get("pet").cloned().unwrap_or(Json::Null);
            if matches!(&pet, Json::Str(name) if name.contains('#')) {
                unknown.push(pet.str().to_owned());
            }
            equipment.push(pet);
            put(&mut loadouts, name, arr(equipment));
            heroes.push(string(name));
            if name == "Grand Warden" {
                let mode = number(hero, "mode", 0.0);
                if mode != 0.0 && mode != 1.0 {
                    unknown.push(format!("Grand Warden mode#{mode}"));
                }
                warden = Some(if mode == 1.0 { "air" } else { "ground" });
            }
        }
        if !unknown.is_empty() {
            return Err(format!("unknown_share_content:{}", unknown.join(",")));
        }
        let mut build = obj([
            ("archetype", string(format!("log-{index}"))),
            ("build", num(1.0)),
            ("th", num(th as f64)),
            ("share", num(1.0)),
            ("three_star", num(0.0)),
            ("troops", troops),
            ("spells", spells),
            ("cc", cc),
            ("heroes", arr(heroes)),
            ("loadouts", loadouts),
        ]);
        if let Some(mode) = warden {
            put(&mut build, "warden_mode", string(mode));
        }
        Ok(build)
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

pub fn replay_seed(identity: &str, seed_index: i64, side: i64, angles: i64) -> i64 {
    let offset = i64::from_str_radix(&identity[..8], 16).expect("SHA prefix");
    5 * offset * angles
        + baselab_engine::scoring::group_seed(offset + seed_index, seed_index, side, angles)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn synthetic_decoder() -> Decoder {
        Decoder {
            names: [
                (("hero".to_owned(), 2), "Grand Warden".to_owned()),
                (("pet".to_owned(), 2), "Electro Owl".to_owned()),
                (("equipment".to_owned(), 4), "Eternal Tome".to_owned()),
                (("equipment".to_owned(), 34), "Healing Tome".to_owned()),
                (("troop".to_owned(), 0), "Barbarian".to_owned()),
            ]
            .into_iter()
            .collect(),
        }
    }

    #[test]
    fn mode_pet_equipment_and_unknown_hero_suffix_are_preserved() {
        let decoder = synthetic_decoder();
        let valid = decoder.decode("h2m1p2e4_34u1x0").unwrap();
        let hero = &list(&valid, "heroes")[0];
        assert_eq!(hero.at("mode"), &num(1.0));
        assert_eq!(list(hero, "equipment").len(), 2);
        let invalid = decoder.decode("h2q1p2e4_34u1x0").unwrap();
        assert_eq!(
            text(&list(&invalid, "heroes")[0], "hero", ""),
            "unparsed:2q1p2e4_34"
        );
        assert!(decoder.build("h2q1p2e4_34u1x0", 16, 0).is_err());
        assert!(decoder.build("u1x999", 16, 0).is_err());
        assert!(decoder.build("", 16, 0).is_err());
    }
}
