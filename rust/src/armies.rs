//! Native army libraries and role composition; meta_armies.py:61-277,282-366.
//!
//! Objects retain source order. The output is rust_bridge.py:39-105's plan
//! representation, accepted directly by plans.rs/playbook.rs and Runner.

use std::fs;
use std::path::{Path, PathBuf};

use crate::json::{self, Json};
use crate::plans::{flag, is_hero, number, spell_key, spell_name, text, truth};
use crate::stats::Stats;

pub const META_FILE: &str = "meta-armies-2026-10-15.json";

#[derive(Clone, Debug)]
pub struct Build {
    pub library: String,
    pub id: String,
    pub value: Json,
}

#[derive(Clone, Debug)]
pub struct ArmyLibrary {
    pub root: PathBuf,
    pub builds: Vec<Build>,
    pub user: Json,
    pub policy: Json,
}

pub(crate) fn read_json(path: &Path) -> Result<Json, String> {
    let source =
        fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    json::parse(source.trim_start_matches('\u{feff}'))
        .map_err(|error| format!("{}: {error}", path.display()))
}

pub(crate) fn object() -> Json {
    Json::Obj(Vec::new())
}

pub(crate) fn string(value: &str) -> Json {
    Json::Str(value.to_owned())
}

pub(crate) fn array(values: impl IntoIterator<Item = Json>) -> Json {
    Json::Arr(values.into_iter().collect())
}

pub(crate) fn put(value: &mut Json, key: &str, item: Json) {
    let Json::Obj(items) = value else {
        panic!("expected object while assigning {key}");
    };
    if let Some((_, old)) = items.iter_mut().find(|(name, _)| name == key) {
        *old = item;
    } else {
        items.push((key.to_owned(), item));
    }
}

pub(crate) fn remove(value: &mut Json, key: &str) {
    let Json::Obj(items) = value else {
        panic!("expected object while removing {key}");
    };
    items.retain(|(name, _)| name != key);
}

pub(crate) fn items(value: &Json, key: &str) -> Vec<(String, Json)> {
    value
        .get(key)
        .filter(|v| !v.is_null())
        .map_or_else(Vec::new, |v| v.obj().to_vec())
}

pub(crate) fn list<'a>(value: &'a Json, key: &str) -> &'a [Json] {
    value.get(key).map_or(&[], Json::arr)
}

pub(crate) fn field(value: &Json, key: &str) -> Json {
    value.get(key).cloned().unwrap_or(Json::Null)
}

pub(crate) fn python_value(value: &Json) -> String {
    match value {
        Json::Null => "None".to_owned(),
        Json::Bool(true) => "True".to_owned(),
        Json::Bool(false) => "False".to_owned(),
        Json::Num(value) if value.fract() == 0.0 => format!("{value:.0}"),
        Json::Num(value) => crate::trace::py_float_repr(*value),
        Json::Str(value) => value.clone(),
        _ => format!("{value:?}"),
    }
}

pub fn build_id(build: &Json) -> String {
    format!(
        "{}-{}-{}",
        build.at("archetype").str(),
        build.at("th").i64(),
        build.at("build").i64()
    )
}

pub fn is_siege(name: &str) -> bool {
    matches!(
        name,
        "Log Launcher"
            | "Sky Wagon"
            | "Siege Barracks"
            | "Troop Launcher"
            | "Stone Slammer"
            | "Battle Blimp"
            | "Wall Wrecker"
            | "Battle Drill"
            | "Flame Flinger"
    )
}

// meta_armies.py:282-343: explicit archetypes precede signature troop order.
pub fn family_of(build: &Json) -> Option<&'static str> {
    let explicit = match text(build, "archetype", "") {
        "root-rider" | "user-rr" => Some("root-rider"),
        "mass-thrower" => Some("thrower"),
        "mass-dragons" => Some("dragon"),
        "e-drag-spam" => Some("electro-dragon"),
        "super-bowler-smash" => Some("super-bowler"),
        "mass-super-yeti" => Some("yeti"),
        "mass-meteor-golem" => Some("meteor-golem"),
        "user-air" => Some("super-minion-air"),
        "user-fireball-warden" => Some("fireball-warden"),
        "user-druid-ruin" => Some("druid-ruin-witch"),
        "mass-dragon-rider" => Some("dragon-rider"),
        "mass-super-dragon" => Some("super-dragon"),
        _ => None,
    };
    explicit.or_else(|| {
        let troops = build.get("troops")?;
        [
            ("Root Rider", "root-rider"),
            ("Thrower", "thrower"),
            ("Electro Dragon", "electro-dragon"),
            ("Super Bowler", "super-bowler"),
            ("Meteor Golem", "meteor-golem"),
            ("Super Yeti", "yeti"),
            // output/research/usage/yeti.md: no cited ordinary-Yeti book exists.
            // https://clashofclans.fandom.com/wiki/Yeti
            ("Yeti", "ordinary-yeti"),
            ("Ruin Witch", "druid-ruin-witch"),
            ("Super Minion", "super-minion-air"),
            ("Lava Hound", "lavaloon"),
            ("Dragon", "dragon"),
            ("Witch", "witch"),
            ("Electro Titan", "electro-titan"),
            ("P.E.K.K.A", "pekka"),
            ("Super Dragon", "super-dragon"),
            ("Dragon Rider", "dragon-rider"),
        ]
        .into_iter()
        .find(|(name, _)| number(troops, name, 0.0) >= 2.0)
        .map(|(_, family)| family)
    })
}

impl ArmyLibrary {
    pub fn load(root: &Path, stats: &Stats) -> Result<Self, String> {
        let directory = root.join("data");
        let meta = read_json(&directory.join(META_FILE))?;
        let observed_path = directory.join("observed-armies.json");
        let observed = if observed_path.exists() {
            read_json(&observed_path)?
        } else {
            object()
        };
        let mut combined = list(&meta, "builds").to_vec();
        combined.extend_from_slice(list(&observed, "builds"));
        fill_missing_cc(&mut combined, stats)?;
        let mut builds = Vec::new();
        for (index, value) in combined.into_iter().enumerate() {
            builds.push(Build {
                library: if index < list(&meta, "builds").len() {
                    META_FILE
                } else {
                    "observed-armies.json"
                }
                .to_owned(),
                id: build_id(&value),
                value,
            });
        }
        let custom_path = directory.join("custom-armies.json");
        if custom_path.exists() {
            for value in list(&read_json(&custom_path)?, "builds") {
                builds.push(Build {
                    library: "custom-armies.json".to_owned(),
                    id: format!("custom:{}", value.at("archetype").str()),
                    value: value.clone(),
                });
            }
        }
        let policy_path = directory.join("attacker-policy.json");
        Ok(Self {
            root: root.to_owned(),
            builds,
            user: user_levels(&directory, stats)?,
            policy: if policy_path.exists() {
                read_json(&policy_path)?
            } else {
                object()
            },
        })
    }

    pub fn build_by_id(&self, id: &str) -> Result<&Json, String> {
        let id = id.strip_prefix("meta:").unwrap_or(id);
        self.builds
            .iter()
            .find(|build| build.id == id)
            .map(|build| &build.value)
            .ok_or_else(|| format!("Unknown army build {id}"))
    }

    // policy.py:45-47: empty per-army entries fall back to '*'.
    pub fn policy_for(&self, archetype: &str) -> Json {
        self.policy
            .get(archetype)
            .filter(|value| !archetype.starts_with('_') && truth(value))
            .or_else(|| self.policy.get("*").filter(|value| truth(value)))
            .cloned()
            .unwrap_or_else(object)
    }
}

fn user_levels(directory: &Path, stats: &Stats) -> Result<Json, String> {
    let mut user = read_json(&directory.join("your-levels.json"))?;
    let live = directory.join("live/player-latest.json");
    if live.is_file() {
        // ClashKing player inventory (snapshot_log.py), as meta_armies.user_levels.
        // Preserve measured buildings and skip unboosted Super Troop placeholders.
        let player = read_json(&live)?;
        for section in ["heroes", "heroEquipment", "troops", "spells"] {
            for item in list(&player, section) {
                let name = item.at("name").str();
                if text(item, "village", "home") != "home" {
                    continue;
                }
                let Some(record) = stats.registry.get(name) else {
                    continue;
                };
                let field = match text(record, "kind", "") {
                    "hero" => "hero_levels",
                    "equipment" => "equipment_levels",
                    "pet" => "pet_levels",
                    "troop" | "siege" | "spell" => "attack_levels",
                    _ => continue,
                };
                let mut levels = user.get(field).cloned().unwrap_or_else(object);
                put(&mut levels, name, item.at("level").clone());
                put(&mut user, field, levels);
            }
        }
        put(
            &mut user,
            "live_source",
            string("data/live/player-latest.json"),
        );
    }
    Ok(user)
}

// meta_armies.py:71-104: mutate in library order, so earlier borrowed castles
// can themselves be donors; min() ties keep the first source entry.
pub fn fill_missing_cc(builds: &mut [Json], stats: &Stats) -> Result<(), String> {
    for index in 0..builds.len() {
        if flag(&builds[index], "cc") {
            continue;
        }
        let build = &builds[index];
        let donor = builds
            .iter()
            .enumerate()
            .filter(|(other, value)| {
                *other != index
                    && value.get("archetype") == build.get("archetype")
                    && flag(value, "cc")
            })
            .min_by_key(|(_, value)| {
                (
                    (value.at("th").i64() - build.at("th").i64()).abs(),
                    -value.at("th").i64(),
                    value.at("build").i64(),
                )
            })
            .map(|(_, value)| value.clone());
        let Some(donor) = donor else {
            continue;
        };
        let mut cc = object();
        let mut room = if build.at("th").i64() == 18 { 4 } else { 3 };
        for (name, amount) in donor.at("cc").obj() {
            let mut count = amount.i64();
            if spell_key(name).is_some() {
                let space = stats.attrs(name).at("housing").i64();
                if space <= 0 {
                    return Err(format!("Invalid spell housing for {name}"));
                }
                count = count.min(room / space);
                room -= count * space;
                if count <= 0 {
                    continue;
                }
            }
            put(&mut cc, name, Json::Num(count as f64));
        }
        put(&mut builds[index], "cc", cc);
        put(
            &mut builds[index],
            "cc_assumed_from",
            string(&build_id(&donor)),
        );
    }
    Ok(())
}

pub fn default_loadout(hero: &str) -> Option<Json> {
    let (equipment, pet) = match hero {
        "Archer Queen" => (["Giant Arrow", "Action Figure"], "Unicorn"),
        "Barbarian King" => (["Spiky Ball", "Earthquake Boots"], "Spirit Fox"),
        "Grand Warden" => (["Eternal Tome", "Rage Gem"], "Electro Owl"),
        "Royal Champion" => (["Rocket Spear", "Electro Boots"], "L.A.S.S.I"),
        "Minion Prince" => (["Dark Orb", "Meteor Staff"], "Angry Jelly"),
        "Dragon Duke" => (["Rocket Backpack", "Fire Heart"], "Phoenix"),
        _ => return None,
    };
    Some(Json::Obj(vec![
        ("$type".to_owned(), string("HeroLoadout")),
        ("hero".to_owned(), string(hero)),
        (
            "equipment".to_owned(),
            array(equipment.into_iter().map(string)),
        ),
        ("pet".to_owned(), string(pet)),
    ]))
}

// meta_armies.py:266-277: None padding is not an equipped item.
pub fn loadouts(build: &Json, heroes: &[Json]) -> Result<Json, String> {
    let mut out = object();
    for hero in heroes {
        if let Some(loadout) = default_loadout(hero.str()) {
            put(&mut out, hero.str(), loadout);
        }
    }
    for (hero, spec) in items(build, "loadouts") {
        let spec = spec.arr();
        if spec.len() > 3 {
            return Err(format!(
                "Too many loadout entries for {hero}: {}",
                spec.len()
            ));
        }
        put(
            &mut out,
            &hero,
            Json::Obj(vec![
                ("$type".to_owned(), string("HeroLoadout")),
                ("hero".to_owned(), string(&hero)),
                (
                    "equipment".to_owned(),
                    array(spec.iter().take(2).filter(|value| truth(value)).cloned()),
                ),
                ("pet".to_owned(), spec.get(2).cloned().unwrap_or(Json::Null)),
            ]),
        );
    }
    Ok(out)
}

fn wave(units: Vec<Json>, spread: f64) -> Json {
    Json::Obj(vec![
        ("$type".to_owned(), string("Wave")),
        ("group".to_owned(), string("main")),
        ("units".to_owned(), Json::Arr(units)),
        ("spread".to_owned(), Json::Num(spread)),
    ])
}

// plans.py:435-552: fresh dataclass fields and __post_init__ runtime stock.
pub(crate) fn empty_plan() -> Json {
    let mut plan = object();
    put(&mut plan, "$type", string("AttackPlan"));
    for (key, value) in [
        ("angle", 0.0),
        ("town_hall", 18.0),
        ("seed", 0.0),
        ("main_min", 8.0),
        ("main_max", 22.0),
        ("strength", 1.0),
        ("revive_delay", 1.5),
        ("charge_lat", 0.0),
        ("charge_at", 0.0),
        ("charge_recall_hp", 0.35),
        ("charge_len", 25.0),
        ("split_main", 0.0),
        ("_next_brain", 0.0),
        ("_main_at", 0.0),
        ("_charge_n", 0.0),
        ("_distracts", 0.0),
    ] {
        put(&mut plan, key, Json::Num(value));
    }
    for key in [
        "funnel_heroes",
        "flank",
        "main",
        "support",
        "push_heroes",
        "cleanup",
        "breakers",
        "cc_troops",
        "freeze_first",
        "recalled",
        "_cast_log",
        "_totem_casts",
        "_later",
        "_spell_stock",
    ] {
        put(&mut plan, key, Json::Arr(Vec::new()));
    }
    for key in [
        "cc_spells",
        "spells",
        "loadouts",
        "troop_levels",
        "spell_levels",
        "cc_spell_levels",
        "event_ruleset",
        "equipment_levels",
        "pet_levels",
        "hero_levels",
        "pol",
        "_spells0",
        "_cc_spells0",
    ] {
        put(&mut plan, key, object());
    }
    for key in [
        "siege",
        "spell_factory_level",
        "dark_spell_factory_level",
        "laboratory_level",
        "clan_castle_level",
        "charge_hero",
        "_entry",
    ] {
        put(&mut plan, key, Json::Null);
    }
    for key in ["ground", "auto_ability_on_ko", "auto_revive"] {
        put(&mut plan, key, Json::Bool(true));
    }
    for key in [
        "siege_donated",
        "account_equipment",
        "recall_funnel",
        "_zap_done",
        "_cc_released",
        "_lured",
    ] {
        put(&mut plan, key, Json::Bool(false));
    }
    put(&mut plan, "label", string("attack"));
    put(&mut plan, "_phase", string("funnel"));
    put(&mut plan, "zap_ad", array([Json::Num(0.0), Json::Num(0.0)]));
    plan
}

pub(crate) fn init_spells(plan: &mut Json, brewed: Json, donated: Json) {
    let mut combined = brewed.clone();
    let mut stock = Vec::new();
    for (origin, inventory) in [("brewed", &brewed), ("donated", &donated)] {
        for (key, count) in inventory.obj() {
            stock.push(Json::Obj(vec![
                ("$type".to_owned(), string("SpellStock")),
                ("name".to_owned(), string(spell_name(key))),
                ("origin".to_owned(), string(origin)),
                ("remaining".to_owned(), count.clone()),
                ("level".to_owned(), Json::Null),
            ]));
        }
    }
    for (key, count) in donated.obj() {
        let total = number(&combined, key, 0.0) + count.f64();
        put(&mut combined, key, Json::Num(total));
    }
    put(plan, "spells", combined);
    put(plan, "cc_spells", donated.clone());
    put(plan, "_spells0", brewed);
    put(plan, "_cc_spells0", donated);
    put(plan, "_spell_stock", Json::Arr(stock));
}

pub fn compose(
    library: &ArmyLibrary,
    stats: &Stats,
    build: &Json,
    angle: f64,
    seed: i64,
) -> Result<Json, String> {
    if !angle.is_finite() {
        return Err("angle must be finite".to_owned());
    }
    for key in ["troops", "cc", "spells"] {
        for (name, count) in items(build, key) {
            if !matches!(count, Json::Num(value) if value.is_finite() && value >= 0.0 && value
                .fract() == 0.0 && value <= i32::MAX as f64)
            {
                return Err(format!(
                    "Invalid count for {name}: {}",
                    python_value(&count)
                ));
            }
            if stats.registry.get(&name).is_none() {
                return Err(format!("Unknown unit or spell: {name}"));
            }
            if key == "spells" && spell_key(&name).is_none() {
                return Err(format!("Unknown spell: {name}"));
            }
        }
    }
    let heroes = list(build, "heroes");
    for (index, hero) in heroes.iter().enumerate() {
        if heroes[..index].contains(hero) {
            return Err("Duplicate heroes in build".to_owned());
        }
        if !matches!(hero, Json::Str(name) if is_hero(name)) {
            return Err("Unknown hero in build".to_owned());
        }
    }
    let mut troops = Json::Obj(items(build, "troops"));
    let cc = Json::Obj(items(build, "cc"));
    let siege = troops
        .obj()
        .iter()
        .chain(cc.obj())
        .find(|(name, count)| is_siege(name) && truth(count))
        .map(|(name, _)| name.clone());
    if let Some(name) = &siege {
        remove(&mut troops, name);
    }
    let mut cc_troops = Vec::new();
    let mut cc_spells = object();
    for (name, count) in cc.obj() {
        if siege.as_deref() == Some(name) {
            continue;
        }
        if let Some(key) = spell_key(name) {
            put(&mut cc_spells, key, count.clone());
        } else {
            cc_troops.extend((0..count.i64()).map(|_| string(name)));
        }
    }
    let mut spells = object();
    for (name, count) in build.at("spells").obj() {
        put(
            &mut spells,
            spell_key(name).expect("validated spell name"),
            count.clone(),
        );
    }
    let default_funnel: Vec<Json> = ["Barbarian King", "Dragon Duke", "Royal Champion"]
        .into_iter()
        .filter(|name| heroes.contains(&string(name)))
        .take(2)
        .map(string)
        .collect();
    let funnel = build
        .get("funnel")
        .map_or(default_funnel.as_slice(), Json::arr);
    let default_push: Vec<Json> = heroes
        .iter()
        .filter(|hero| !funnel.contains(hero))
        .cloned()
        .collect();
    let push = build.get("push").map_or(default_push.as_slice(), Json::arr);
    let mut assigned: Vec<&str> = funnel.iter().chain(push).map(Json::str).collect();
    let mut roster: Vec<&str> = heroes.iter().map(Json::str).collect();
    assigned.sort_unstable();
    roster.sort_unstable();
    if assigned != roster {
        return Err("Hero roles must assign each build hero exactly once".to_owned());
    }
    let housing = |name: &str| number(stats.attrs(name), "housing", 1.0).max(1.0) as i64;
    let bulk = troops
        .obj()
        .iter()
        .enumerate()
        .max_by_key(|(index, (name, count))| {
            (count.i64() * housing(name), std::cmp::Reverse(*index))
        })
        .map(|(_, (name, _))| name.as_str());
    let (mut flank, mut main, mut support, mut cleanup, mut breakers) =
        (Vec::new(), Vec::new(), Vec::new(), Vec::new(), Vec::new());
    let mut lateral = -4.0;
    let (mut air_space, mut main_space) = (0_i64, 0_i64);
    for (name, count) in troops.obj() {
        let pair = array([string(name), count.clone()]);
        if matches!(name.as_str(), "Healer" | "Apprentice Warden") {
            support.push(pair);
        } else if matches!(name.as_str(), "Wall Breaker" | "Super Wall Breaker") {
            breakers.push(pair);
        } else if matches!(name.as_str(), "Archer" | "Minion" | "Barbarian" | "Goblin")
            && Some(name.as_str()) != bulk
        {
            cleanup.push(pair);
        } else if matches!(name.as_str(), "Balloon" | "Baby Dragon" | "Rocket Balloon")
            && Some(name.as_str()) != bulk
            && count.i64() <= 6
        {
            flank.push(array([string(name), count.clone(), Json::Num(lateral)]));
            lateral = -lateral;
        } else {
            let space = count.i64() * housing(name);
            main_space += space;
            if flag(stats.attrs(name), "flying") || flag(stats.attrs(name), "is_flying") {
                air_space += space;
            }
            main.push(pair);
        }
    }
    let air = air_space as f64 > 0.5 * main_space as f64;
    let mut plan = empty_plan();
    let th = build.at("th").i64();
    if !(16..=18).contains(&th) {
        return Err(format!("Unsupported attacker Town Hall {th}"));
    }
    let evidence = match build.get("three_star") {
        None | Some(Json::Null) => "observed, uncalibrated".to_owned(),
        Some(rate) => format!(
            "real 3* {:.0}%",
            crate::geom::round_half_even(rate.f64() * 100.0)
        ),
    };
    for (key, value) in [
        ("angle", angle),
        ("town_hall", th as f64),
        ("seed", seed as f64),
        ("main_min", if air { 10.0 } else { 8.0 }),
        ("main_max", if air { 20.0 } else { 18.0 }),
    ] {
        put(&mut plan, key, Json::Num(value));
    }
    put(
        &mut plan,
        "label",
        string(&format!(
            "{} #{} (TH{th}, {evidence})",
            build.at("archetype").str(),
            build.at("build").i64()
        )),
    );
    put(
        &mut plan,
        "funnel_heroes",
        array(funnel.iter().enumerate().map(|(index, hero)| {
            array([hero.clone(), Json::Num(if index == 0 { -6.0 } else { 6.0 })])
        })),
    );
    put(&mut plan, "push_heroes", array(push.iter().cloned()));
    put(&mut plan, "flank", Json::Arr(flank));
    put(
        &mut plan,
        "main",
        array([wave(main, if air { 3.0 } else { 2.5 })]),
    );
    put(
        &mut plan,
        "support",
        if support.is_empty() {
            array([])
        } else {
            array([wave(support, 1.0)])
        },
    );
    put(&mut plan, "cleanup", Json::Arr(cleanup));
    put(&mut plan, "breakers", Json::Arr(breakers));
    // output/research/usage/grand-warden.md: preserve the replay's chosen mode.
    // https://clashofclans.fandom.com/wiki/Grand_Warden
    let ground = match build.get("warden_mode") {
        Some(Json::Str(mode)) if mode == "ground" => true,
        Some(Json::Str(mode)) if mode == "air" => false,
        None => !air,
        _ => return Err("Grand Warden mode must be air or ground".to_owned()),
    };
    put(&mut plan, "ground", Json::Bool(ground));
    put(
        &mut plan,
        "siege",
        siege.as_deref().map_or(Json::Null, string),
    );
    put(
        &mut plan,
        "siege_donated",
        Json::Bool(
            siege
                .as_ref()
                .is_some_and(|name| build.at("troops").get(name).is_none()),
        ),
    );
    put(&mut plan, "cc_troops", Json::Arr(cc_troops));
    put(&mut plan, "loadouts", loadouts(build, heroes)?);
    let lightning = number(&spells, "lightning", 0.0) + number(&cc_spells, "lightning", 0.0);
    put(
        &mut plan,
        "zap_ad",
        array([
            Json::Num(if lightning >= 3.0 { lightning } else { 0.0 }),
            Json::Num(0.0),
        ]),
    );
    init_spells(&mut plan, spells, cc_spells);
    put(&mut plan, "observed", Json::Bool(flag(build, "observed")));
    put(&mut plan, "build_id", string(&build_id(build)));
    if flag(build, "own_levels") || text(build, "archetype", "").starts_with("user-") {
        put(&mut plan, "account_equipment", Json::Bool(true));
        for key in ["hero_levels", "equipment_levels", "pet_levels"] {
            put(
                &mut plan,
                key,
                library.user.get(key).cloned().unwrap_or_else(object),
            );
        }
        let mut troop_levels = object();
        let mut spell_levels = object();
        for (name, level) in items(&library.user, "attack_levels") {
            if spell_key(&name).is_some() {
                put(&mut spell_levels, &name, level);
            } else if !(flag(&plan, "siege_donated") && siege.as_deref() == Some(&name)) {
                put(&mut troop_levels, &name, level);
            }
        }
        for (name, _) in troops.obj() {
            if !flag(stats.record(name), "super") {
                continue;
            }
            for (column, _) in items(stats.attrs(name), "raw") {
                if let Some(base) = column.strip_suffix(" Level Required") {
                    if let Some(level) = troop_levels.get(base).cloned() {
                        put(&mut troop_levels, name, level);
                        break;
                    }
                }
            }
        }
        put(&mut plan, "troop_levels", troop_levels);
        put(&mut plan, "spell_levels", spell_levels);
        for (attribute, key) in [
            ("clan_castle_level", "cc"),
            ("laboratory_level", "lab"),
            ("dark_spell_factory_level", "dsf"),
            ("spell_factory_level", "sf"),
        ] {
            if let Some(value @ Json::Num(_)) = library
                .user
                .get("levels")
                .and_then(|levels| levels.get(key))
            {
                put(&mut plan, attribute, value.clone());
            }
        }
    }
    let mut policy = library.policy_for(build.at("archetype").str());
    for (key, value) in items(build, "pol") {
        put(&mut policy, &key, value);
    }
    put(&mut plan, "pol", policy);
    Ok(plan)
}
