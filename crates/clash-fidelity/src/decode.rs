//! Army share-code decoding and exact observed build construction.

use std::path::Path;

use clash_data::json::Json;
use clash_engine::plans::spell_key;

use super::io::*;

pub struct Decoder {
    inner: clash_data::battlelog::Decoder,
}

impl Decoder {
    pub fn load(root: &Path) -> Result<Self, String> {
        Ok(Self {
            inner: clash_data::battlelog::Decoder::load(root)?,
        })
    }

    pub fn decode(&self, code: &str) -> Result<Json, String> {
        self.inner.decode(code)
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

pub use clash_data::battlelog::identity;

pub fn replay_seed(identity: &str, seed_index: i64, side: i64, angles: i64) -> i64 {
    let offset = i64::from_str_radix(&identity[..8], 16).expect("SHA prefix");
    5 * offset * angles
        + clash_scoring::scoring::group_seed(offset + seed_index, seed_index, side, angles)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn synthetic_decoder() -> Decoder {
        Decoder {
            inner: clash_data::battlelog::Decoder::from_names(
                [
                    (("hero".to_owned(), 2), "Grand Warden".to_owned()),
                    (("pet".to_owned(), 2), "Electro Owl".to_owned()),
                    (("equipment".to_owned(), 4), "Eternal Tome".to_owned()),
                    (("equipment".to_owned(), 34), "Healing Tome".to_owned()),
                    (("troop".to_owned(), 0), "Barbarian".to_owned()),
                ]
                .into_iter()
                .collect(),
            ),
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
