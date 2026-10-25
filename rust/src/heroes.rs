//! Ports heroes.py, including TH18 Guardians. setup.rs constructs defenders.

use std::cell::RefCell;
use std::rc::Rc;

use crate::battle::SpawnOptions;
use crate::catalog::{game_float, game_int, game_required_int, UnitSpec};
use crate::combat::{SplashBuildingsOptions, SplashUnitsOptions};
use crate::geom::{dist, py_hypot};
use crate::labels::{Name, Special, Specials, Tag};
use crate::state::*;
use crate::stats::{self, Level};
use crate::trace::round_decimal;
use crate::{effects, pets, spells, units};

#[derive(Clone, Debug)]
pub struct HeroLoadout {
    pub hero: String,
    pub equipment: Vec<String>,
    pub pet: Option<String>,
}

// heroes.py:33-64: retain every slot, with Python's initial values.
#[derive(Clone, Debug)]
pub struct Kit {
    pub hero: String,
    pub equip: Vec<String>,
    pub levels: Vec<(String, Level)>,
    pub pet_name: Option<String>,
    pub pet_level: Option<Level>,
    pub pet_unit: Option<UnitRef>,
    pub regen: f64,
    pub hp_recovery: f64,
    pub phoenix: bool,
    pub doomed_at: Option<f64>,
    pub spear_shots: i64,
    pub spear_bonus: f64,
    pub reduction_until: f64,
    pub reduction: f64,
    pub heal_until: f64,
    pub heal_rate: f64,
    pub next_meteor: f64,
    pub crown_stage: usize,
    pub vamp: f64,
    pub frozen_arrow: Option<(f64, f64)>,
    pub mono_arrow: Option<[f64; 3]>,
}

impl Kit {
    pub fn new(hero: &str) -> Self {
        Self {
            hero: hero.to_owned(),
            equip: Vec::new(),
            levels: Vec::new(),
            pet_name: None,
            pet_level: None,
            pet_unit: None,
            regen: 0.0,
            hp_recovery: 0.0,
            phoenix: false,
            doomed_at: None,
            spear_shots: 0,
            spear_bonus: 0.0,
            reduction_until: 0.0,
            reduction: 0.0,
            heal_until: 0.0,
            heal_rate: 0.0,
            next_meteor: 0.0,
            crown_stage: 0,
            vamp: 0.0,
            frozen_arrow: None,
            mono_arrow: None,
        }
    }

    pub fn has(&self, name: &str) -> bool {
        self.equip.iter().any(|equipment| equipment == name)
    }

    pub fn lv(&self, name: &str) -> &Level {
        let (_, level) = self
            .levels
            .iter()
            .find(|(equipment, _)| equipment == name)
            .expect("equipped item level");
        level
    }
}

#[derive(Clone, Debug)]
pub struct Dash {
    pub direction: (f64, f64),
    pub until: f64,
    pub end: (f64, f64),
    pub hit: Vec<EntityRef>,
    pub damage: f64,
    pub pet: Option<UnitRef>,
}

// heroes.py:28-30.
pub fn col(battle: &Battle, name: &str, level: &Level, fragments: &[&str], default: f64) -> f64 {
    let keys: Vec<_> = fragments
        .iter()
        .map(|fragment| format!("~{fragment}"))
        .collect();
    let keys: Vec<_> = keys.iter().map(String::as_str).collect();
    battle
        .catalog
        .stats
        .get(name, level, &keys, Some(default))
        .expect("numeric default")
}

// heroes.py:574-578: use the same CSV range for scouting and activation.
pub fn spear_range(battle: &Battle) -> f64 {
    game_float(
        battle
            .catalog
            .game_data("special_abilities", "RocketSpears", None),
        "AttackRange",
    ) / 100.0
}

// heroes.py:1504-1518: the current target determines the forward arrow band.
pub fn arrow_geometry(
    battle: &Battle,
    hero: UnitRef,
    target: Option<EntityRef>,
) -> (f64, f64, f64, f64) {
    let u = battle.unit(hero);
    let (dx, dy) = target.map_or(u.extra.facing, |target| {
        let (x, y) = battle.entity_position(target);
        (x - u.x, y - u.y)
    });
    let distance = py_hypot(dx, dy);
    let distance = if distance == 0.0 { 1.0 } else { distance };
    let data = battle.catalog.game_data(
        "special_abilities",
        "ArcherQueenPierceProjectile",
        Some(&Level::Int(1)),
    );
    (
        dx / distance,
        dy / distance,
        distance + game_float(data, "PenetratingExtraRange") / 100.0,
        game_float(data, "PenetratingRadius") / 100.0,
    )
}

// heroes.py:1521-1540: center-facing dash, bounded by the world edge.
pub fn dash_geometry(battle: &Battle, x: f64, y: f64, facing: (f64, f64)) -> (f64, f64, f64, f64) {
    let world = battle.catalog.world as f64;
    let data = battle.catalog.game_data(
        "special_abilities",
        "DragonDukeDeadlyDashMapCenter",
        Some(&Level::Int(1)),
    );
    let (mut dx, mut dy) = (world / 2.0 - x, world / 2.0 - y);
    let mut distance = py_hypot(dx, dy);
    if distance == 0.0 {
        (dx, dy) = facing;
        distance = py_hypot(dx, dy);
        if distance == 0.0 {
            distance = 1.0;
        }
    }
    (dx, dy) = (dx / distance, dy / distance);
    let mut travel = game_float(data, "MovementOverrideDistance");
    for (position, direction) in [(x, dx), (y, dy)] {
        if direction > 0.0 {
            travel = travel.min((world - 0.5 - position) / direction);
        } else if direction < 0.0 {
            travel = travel.min((0.5 - position) / direction);
        }
    }
    (
        dx,
        dy,
        0.0_f64.max(travel),
        game_float(data, "ActAsPenetratingRadius") / 100.0,
    )
}

// heroes.py:153,575,623,864: equipment levels map to ability/spell levels.
fn equipment_ability_level(level: &Level) -> Level {
    let Level::Int(level) = level else {
        panic!("integer equipment level");
    };
    Level::Int(level.div_euclid(3) + 1)
}

pub fn default_loadout(battle: &Battle, hero: &str) -> Option<HeroLoadout> {
    if let Some(loadouts) = battle.catalog.setup.get("default_loadouts") {
        let loadout = loadouts.get(hero)?;
        return Some(HeroLoadout {
            hero: loadout.at("hero").str().to_owned(),
            equipment: loadout
                .at("equipment")
                .arr()
                .iter()
                .map(|v| v.str().to_owned())
                .collect(),
            pet: loadout.at("pet").opt_str().map(str::to_owned),
        });
    }
    // Compatibility with catalogs exported before setup tables were added.
    let (equipment, pet) = match hero {
        "Archer Queen" => (["Giant Arrow", "Action Figure"], "Unicorn"),
        "Barbarian King" => (["Spiky Ball", "Earthquake Boots"], "Spirit Fox"),
        "Grand Warden" => (["Eternal Tome", "Rage Gem"], "Electro Owl"),
        "Royal Champion" => (["Rocket Spear", "Electro Boots"], "L.A.S.S.I"),
        "Minion Prince" => (["Dark Orb", "Meteor Staff"], "Angry Jelly"),
        "Dragon Duke" => (["Rocket Backpack", "Fire Heart"], "Phoenix"),
        _ => return None,
    };
    Some(HeroLoadout {
        hero: hero.to_owned(),
        equipment: equipment.iter().map(|name| (*name).to_owned()).collect(),
        pet: Some(pet.to_owned()),
    })
}

// heroes.py:67-100: setup validation occurs before applying any equipment.
fn pet_level(
    battle: &Battle,
    hero: UnitRef,
    loadout: &HeroLoadout,
    town_hall: i64,
) -> Option<Level> {
    let name = loadout.pet.as_deref().filter(|name| !name.is_empty())?;
    let stats = &battle.catalog.stats;
    assert!(
        stats.registry.get(name).is_some() && stats.record(name).at("kind").str() == "pet",
        "{name} is not a pet"
    );
    let maximum = stats
        .max_level(name, town_hall)
        .unwrap_or_else(|| panic!("{name} is unavailable at Town Hall {town_hall}"));
    let level = battle
        .plan
        .pet_level(name)
        .cloned()
        .unwrap_or(Level::Int(maximum));
    assert!(
        matches!(&level, Level::Int(value) if 1 <= *value && *value <= maximum),
        "Illegal {name} level {level} at Town Hall {town_hall}"
    );
    let _ = stats.row(name, &level);
    let stashed = battle.portal_stash.iter().map(|value| match value {
        Value::Ref(EntityRef::Unit(unit)) => *unit,
        _ => panic!("Portal stash member must be a unit reference"),
    });
    for reference in battle.attackers_pool().map(Unit::reference).chain(stashed) {
        let unit = battle.unit(reference);
        if unit.reference() == hero {
            continue;
        }
        assert!(
            !unit
                .kit
                .as_ref()
                .is_some_and(|kit| kit.pet_name.as_deref() == Some(name)),
            "{name} is already assigned to {}",
            unit.name
        );
        assert!(
            !(unit.kind == Tag::Pet && unit.name == name && unit.owner != Some(hero)),
            "{name} is already assigned to another Hero"
        );
    }
    assert!(battle.unit(hero).pet.is_none(), "hero already has a pet");
    Some(level)
}

// heroes.py:103-182: equip is called after strength, before league scaling.
pub fn equip(battle: &mut Battle, hero: UnitRef) {
    let name = battle.unit(hero).name.clone();
    let Some(mut loadout) = battle
        .plan
        .loadout(&name)
        .cloned()
        .or_else(|| default_loadout(battle, &name))
    else {
        return;
    };
    // heroes.py:108-126: validate every slot before applying any boosts.
    assert_eq!(
        loadout.hero, name,
        "Loadout for {} cannot be applied to {name}",
        loadout.hero
    );
    assert!(
        loadout.equipment.len() <= 2,
        "{name} can equip at most 2 equipment items"
    );
    let mut equipped = Vec::new();
    for equipment in &loadout.equipment {
        assert!(
            !equipped.contains(&equipment),
            "Duplicate equipment for {name}: {equipment}"
        );
        equipped.push(equipment);
        let stats = &battle.catalog.stats;
        assert!(
            stats.registry.get(equipment).is_some()
                && stats.record(equipment).at("kind").str() == "equipment",
            "{equipment} is not hero equipment"
        );
        let owner = stats
            .attrs(equipment)
            .get("raw")
            .and_then(|raw| raw.get("User"))
            .and_then(crate::json::Json::opt_str);
        assert!(
            owner == Some(name.as_str()),
            "{equipment} belongs to {owner:?}, not {name}"
        );
    }
    let th = battle.plan.town_hall();
    if loadout.pet.as_deref().is_some_and(|pet| {
        !pet.is_empty()
            && battle.catalog.stats.registry.get(pet).is_some()
            && battle.catalog.stats.record(pet).at("kind").str() == "pet"
            && battle.plan.observed()
            && battle.catalog.stats.max_level(pet, th).is_none()
    }) {
        // heroes.py:176-215: reserve explicit assignments and live replacements.
        let loadouts: &[(String, HeroLoadout)] = match &battle.plan {
            Plan::Attack(plan) => &plan.loadouts,
            Plan::Playbook(plan) => &plan.attack.loadouts,
            Plan::Stage { loadouts, .. } => loadouts,
        };
        let mut assigned: Vec<String> = loadouts
            .iter()
            .filter(|(_, other)| other.hero != name)
            .filter_map(|(_, other)| other.pet.clone())
            .collect();
        for reference in battle
            .attackers_pool()
            .map(Unit::reference)
            .chain(battle.portal_units())
        {
            if reference == hero {
                continue;
            }
            let unit = battle.unit(reference);
            if let Some(pet) = unit.kit.as_ref().and_then(|kit| kit.pet_name.as_ref()) {
                assigned.push(pet.clone());
            }
            if unit.kind == Tag::Pet {
                assigned.push(unit.name.clone());
            }
        }
        let stats = &battle.catalog.stats;
        let mut pets: Vec<_> = stats
            .registry
            .obj()
            .iter()
            .filter(|(_, record)| record.at("kind").str() == "pet")
            .map(|(name, _)| name.clone())
            .collect();
        pets.sort_by(|a, b| {
            let unlock = |name: &str| {
                stats::num(
                    stats.attrs(name).at("raw").at("Pet House Level Required"),
                    None,
                )
                .expect("pet unlock level")
            };
            unlock(a).total_cmp(&unlock(b)).then_with(|| a.cmp(b))
        });
        let preferred = default_loadout(battle, &name)
            .expect("default hero loadout")
            .pet;
        loadout.pet = preferred
            .into_iter()
            .chain(pets)
            .find(|pet| !assigned.contains(pet) && stats.max_level(pet, th).is_some());
    }
    let pet_level = pet_level(battle, hero, &loadout, th);
    let mut kit = Kit::new(&name);
    let base_interval = battle.unit(hero).interval;
    let (mut passive_dps, mut passive_speed) = (0.0, 0.0);
    for equipment in &loadout.equipment {
        // heroes.py:137-141: account inventories leave unowned slots empty.
        if !battle.plan.equipment_owned(equipment) {
            continue;
        }
        if battle.catalog.stats.registry.get(equipment).is_none() {
            continue;
        }
        let level = battle
            .plan
            .equipment_level(equipment)
            .cloned()
            .filter(|level| !matches!(level, Level::Int(0)))
            .or_else(|| {
                battle
                    .catalog
                    .stats
                    .max_level(equipment, th)
                    .map(Level::Int)
            })
            .expect("equipment available at Town Hall");
        kit.equip.push(equipment.clone());
        if let Some((_, previous)) = kit.levels.iter_mut().find(|(name, _)| name == equipment) {
            *previous = level.clone();
        } else {
            kit.levels.push((equipment.clone(), level.clone()));
        }
        // stats.py:21-28,76-81: equipment boosts use the balance-adjusted catalog registry.
        let hp = col(
            battle,
            equipment,
            &level,
            &["hitpoint increase", "hp increase"],
            0.0,
        );
        let dps = col(
            battle,
            equipment,
            &level,
            &["damage per second increase", "dps increase"],
            0.0,
        );
        let attack_speed = col(
            battle,
            equipment,
            &level,
            &[
                "hero boosts / attack speed increase",
                "hero boost / attack speed increase",
            ],
            0.0,
        );
        let unit = battle.unit_mut(hero);
        unit.max_hp += hp;
        unit.base_max_hp += hp;
        unit.hp += hp;
        passive_dps += dps;
        passive_speed += attack_speed / 100.0;
        if equipment == "Fire Heart" {
            // stats.py:82-84: resolved abilities also include balance replacements.
            let ability = battle.catalog.equipment_ability(equipment, &level);
            kit.regen += game_float(ability, "Regeneration") * 1000.0
                / game_float(ability, "RegenerationTimeBetweenHitsMS");
        } else {
            kit.regen += col(battle, equipment, &level, &["self healing per second"], 0.0);
        }
        kit.hp_recovery += col(
            battle,
            equipment,
            &level,
            &["hp recovery increase", "health recovery increase"],
            0.0,
        );
        if matches!(equipment.as_str(), "Royal Gem" | "Stun Blaster") {
            kit.hp_recovery += col(battle, equipment, &level, &["health recovery"], 0.0);
        }
        // heroes.py:166-192: equipment-specific passive state.
        match equipment.as_str() {
            "Vampstache" => {
                kit.vamp = col(battle, equipment, &level, &["heal per hit"], 0.0);
            }
            "Electro Boots" => battle.unit_mut(hero).extra.boots_next = Some(battle.t + 0.4),
            "Frozen Arrow" => {
                kit.frozen_arrow = Some((
                    col(battle, equipment, &level, &["slow down"], 0.0) / 100.0,
                    col(battle, equipment, &level, &["slow down duration"], 0.0),
                ));
            }
            "Stick Horse" => {
                // ClashKing / special_abilities.csv StickHorseBoost: exact
                // ability values, rather than rounded display percentages.
                let Level::Int(equipment_level) = &level else {
                    panic!("Stick Horse needs an integer level");
                };
                let ability_level = Level::Int(equipment_level / 3 + 1);
                let ability = battle.catalog.game_data(
                    "special_abilities",
                    "StickHorseBoost",
                    Some(&ability_level),
                );
                let until = battle.t + game_float(ability, "DeactivateAfterTime") / 1000.0;
                let speed = game_float(ability, "SpeedBoost") / 100.0;
                let attack_interval = game_float(ability, "AttackSpeed") / 1000.0;
                let attack = base_interval / attack_interval - 1.0;
                let unit = battle.unit_mut(hero);
                unit.extra.horse_until = until;
                unit.extra.paused_timers.horse_until = true;
                unit.extra.horse_speed = speed;
                unit.extra.horse_attack = attack;
                unit.extra.horse_interval = base_interval;
            }
            "Monolith Arrow" => {
                kit.mono_arrow = Some([
                    col(battle, equipment, &level, &["highest extra damage"], 0.0) / 100.0,
                    col(battle, equipment, &level, &["extra damage (181-250"], 0.0) / 100.0,
                    col(battle, equipment, &level, &["extra damage (251+"], 0.0) / 100.0,
                ]);
                kit.reduction = col(
                    battle,
                    equipment,
                    &level,
                    &["incoming damage reduction"],
                    0.0,
                ) / 100.0;
                kit.reduction_until = 1e9;
            }
            "Rocket Spear" | "Revenge Deck" | "Fire Heart" | "Action Figure" | "Giant Arrow"
            | "Eternal Tome" | "Rage Gem" | "Fireball" | "Rocket Backpack" | "Spiky Ball"
            | "Earthquake Boots" | "Dark Orb" | "Meteor Staff" | "Barbarian Puppet"
            | "Archer Puppet" | "Hog Rider Puppet" | "Healer Puppet" | "Lavaloon Puppet"
            | "Seeking Shield" | "Haste Vial" | "Heroic Torch" | "Magic Mirror"
            | "Henchmen Puppet" | "Stun Blaster" | "Noble Iron" | "Rage Vial"
            | "Giant Gauntlet" | "Snake Bracelet" | "Invisibility Vial" | "Life Gem"
            | "Healing Tome" | "Royal Gem" | "Frost Flake" | "Dark Crown" | "Metal Pants"
            | "Portal Pendant" | "Flame Blower" | "Electro Fangs" => {}
            _ => panic!("unsupported hero equipment {equipment}"),
        }
    }
    let unit = battle.unit_mut(hero);
    unit.dmg += passive_dps * base_interval;
    unit.interval = base_interval / (1.0 + passive_speed);
    if kit.has("Noble Iron") {
        let level = kit.lv("Noble Iron");
        let ability = battle.catalog.equipment_ability("Noble Iron", level);
        let shots = game_required_int(ability, "DeactivateAfterNumberOfHits");
        let bonus = col(
            battle,
            "Noble Iron",
            level,
            &["damage per shot increase"],
            0.0,
        );
        let range = col(battle, "Noble Iron", level, &["attack range"], 0.0);
        kit.spear_shots = shots;
        kit.spear_bonus = bonus;
        let unit = battle.unit_mut(hero);
        unit.extra.spear_base_range = Some(unit.range);
        unit.range = range;
    }
    kit.hp_recovery += battle
        .catalog
        .stats
        .get(
            &name,
            battle.unit(hero).level.as_ref().expect("hero level"),
            &["Health Recovery"],
            Some(0.0),
        )
        .expect("numeric default");
    if let Some(pet) = loadout.pet.filter(|name| !name.is_empty()) {
        kit.phoenix = pet == "Phoenix";
        kit.pet_name = Some(pet);
        kit.pet_level = pet_level;
        spawn_pet(battle, hero, &mut kit);
    }
    if kit.has("Meteor Staff") {
        kit.next_meteor = battle.t
            + col(
                battle,
                "Meteor Staff",
                kit.lv("Meteor Staff"),
                &["cooldown time"],
                0.0,
            );
    }
    let tracks_summons = [
        "Action Figure",
        "Magic Mirror",
        "Henchmen Puppet",
        "Healer Puppet",
    ]
    .iter()
    .any(|name| kit.has(name));
    let unit = battle.unit_mut(hero);
    unit.kit = Some(kit);
    if tracks_summons {
        unit.extra.summon_position = Some((unit.x, unit.y));
        unit.extra.summon_facing = Some(unit.extra.facing);
    }
}

// heroes.py:188-266: pets use a fresh owner-following specification and Unit
// constructor, bypassing spawn/on_spawn and preserving the shared ID counter.
fn spawn_pet(battle: &mut Battle, hero: UnitRef, kit: &mut Kit) {
    let name = kit.pet_name.as_deref().expect("pet name").to_owned();
    let level = kit.pet_level.clone().expect("pet level");
    assert!(
        matches!(
            name.as_str(),
            "Unicorn"
                | "Phoenix"
                | "Frosty"
                | "Poison Lizard"
                | "Spirit Fox"
                | "Electro Owl"
                | "Angry Jelly"
                | "L.A.S.S.I"
                | "Diggy"
                | "Mighty Yak"
                | "Sneezy"
                | "Greedy Raven"
        ),
        "unsupported attacking pet {name}"
    );
    let stats = &battle.catalog.stats;
    let attrs = stats.attrs(&name);
    let hp = stats
        .get(&name, &level, &["hitpoints", "Hitpoints"], Some(2000.0))
        .expect("pet HP");
    let mut dps = stats
        .get(
            &name,
            &level,
            &["dps", "Damage per Second", "~damage per second"],
            Some(0.0),
        )
        .expect("pet DPS");
    if name == "Unicorn" {
        dps = 0.0;
    }
    let interval = attrs
        .get("attack_interval")
        .and_then(|v| v.opt_f64())
        .filter(|v| *v != 0.0)
        .or_else(|| {
            attrs
                .get("attack_interval_ck")
                .and_then(|v| v.opt_f64())
                .filter(|v| *v != 0.0)
        })
        .unwrap_or(1.0);
    // heroes.py:232-234: pet construction bypasses unit_numbers' range override.
    let range = *battle
        .catalog
        .pet_spawn_ranges
        .get(&name)
        .expect("pet spawn range");
    let speed = battle
        .catalog
        .resolved
        .at("pet_spawn_speeds")
        .at(&name)
        .f64();
    let flying = attrs.get("is_flying").is_some_and(|v| v.bool());
    let hits_air = attrs.get("is_air_targeting").map_or(true, |v| v.bool());
    // heroes.py:204 constructs UnitSpec directly, rather than spec(name).
    let mut spec = UnitSpec {
        name: name.clone(),
        prefer: Tag::Owner,
        walls: if flying { Tag::Fly } else { Tag::Ignore },
        attack: Tag::Single,
        splash: 0.0,
        splash_ground_only: false,
        chain: 0,
        chain_range: 3.0,
        chain_decay: 0.8,
        chain_from_primary: false,
        bounces: 0,
        bounce_gap: 3.0,
        pierce: 0.0,
        vs_walls: 1.0,
        vs_resources: 1.0,
        vs_defenses: 1.0,
        vs_heroes: 1.0,
        vs_buildings: 1.0,
        engages_units: true,
        death_damage: None,
        death_radius: 0.0,
        death_delay: 0.0,
        death_freeze: None,
        death_freeze_radius: 0.0,
        death_spawn: Vec::new(),
        special: Specials::default(),
        heal_air: false,
        flying_override: None,
        notes: String::new(),
    };
    if name == "Phoenix" {
        spec.attack = Tag::Splash;
        spec.splash = 0.3;
    }
    // heroes.py:289-297: wall ramming and resource damage multipliers.
    if name == "Mighty Yak" {
        spec.walls = Tag::Normal;
        spec.vs_walls = 20.0;
    }
    if name == "Greedy Raven" {
        spec.vs_resources = 5.0;
    }
    battle.uid += 1;
    let owner = battle.unit(hero);
    let mut pet = Unit {
        source: format!("unit:{name}").into(),
        name_id: Name::from_str(&name),
        id: UnitId(battle.uid),
        name: name.clone(),
        kind: Tag::Pet,
        team: Team::Atk,
        level: Some(level.clone()),
        x: owner.x + 0.5,
        y: owner.y + 0.5,
        hp,
        max_hp: hp,
        base_max_hp: hp,
        dmg: dps * interval,
        interval,
        range,
        speed,
        housing: 0,
        flying,
        hits_air,
        hits_ground: true,
        spec: std::sync::Arc::new(spec),
        alive: true,
        cooldown: 0.0,
        target: None,
        target_kind: None,
        wall_target: None,
        group: owner.group.clone(),
        spawned_at: battle.t,
        active_at: 0.0,
        stuck: 0.0,
        frozen_until: 0.0,
        stun_until: 0.0,
        held_until: 0.0,
        invisible_until: 0.0,
        invuln_until: 0.0,
        move_slow: 1.0,
        move_slow_until: 0.0,
        atk_slow: 1.0,
        atk_slow_until: 0.0,
        rage_dmg: 1.0,
        rage_spd: 0.0,
        rage_until: 0.0,
        haste_spd: 0.0,
        haste_until: 0.0,
        iceblock_red: 0.0,
        iceblock_until: 0.0,
        dmg_taken_mult: 1.0,
        dmg_taken_until: 0.0,
        aura_bonus: 0.0,
        aura_dmg: 1.0,
        underground: false,
        aware_until: 0.0,
        last_hit: -100.0,
        poison_stack: 0,
        is_hero: false,
        kit: None,
        pet: None,
        owner: Some(hero),
        follow: None,
        home: None,
        leash: 0.0,
        ability_used: false,
        decay: 0.0,
        dash: None,
        extra: UnitExtra::default(),
        damage_dealt: 0.0,
        in_pool: true,
    };
    if name == "Angry Jelly" {
        pet.range = 5.0;
        let owner = battle.unit(hero);
        pet.x = owner.x;
        pet.y = owner.y;
        pet.extra.brainwash_until = battle.t
            + battle
                .catalog
                .stats
                .get(&name, &level, &["Brainwash Duration"], None)
                .expect("Brainwash duration");
        pet.extra.paused_timers.brainwash_until = true;
    }
    if name == "Spirit Fox" {
        let duration = battle
            .catalog
            .stats
            .get(&name, &level, &["Invisibility Duration"], None)
            .expect("Fox invisibility duration");
        pet.invisible_until = pet.invisible_until.max(battle.t + duration);
        let until = battle.t + duration;
        let hero = battle.unit_mut(hero);
        hero.invisible_until = hero.invisible_until.max(until);
        pet.extra.fox_next = battle.t + duration + 6.0;
    }
    if name == "Diggy" {
        pet.underground = true;
    }
    if name == "Phoenix" {
        pet.extra.egg = true;
        pet.invisible_until = 1e9;
        pet.invuln_until = 1e9;
    }
    if name == "Frosty" {
        pet.extra.next_summon = battle.t
            + stats::num(
                battle
                    .catalog
                    .stats
                    .attrs(&name)
                    .at("raw")
                    .at("Summon Cooldown"),
                None,
            )
            .expect("Frosty summon cooldown");
    }
    if name == "Sneezy" {
        pet.extra.next_summon = battle.t + 10.0;
    }
    let reference = pet.reference();
    battle.register_unit(pet.id, Team::Atk, battle.attackers.len());
    battle.attackers.push(pet);
    battle.attacker_order.push(reference);
    new_member(battle, reference);
    kit.pet_unit = Some(reference);
    battle.unit_mut(hero).pet = Some(reference);
}

// heroes.py:275-345: called inside units.pre_tick's aura provenance.
pub fn tick(battle: &mut Battle, hero: UnitRef) {
    let t = battle.t;
    if battle.unit(hero).extra.summon_position.is_some() {
        summon_facing(battle, hero, None);
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.doomed_at.is_some_and(|until| t >= until) {
        let unit = battle.unit_mut(hero);
        unit.kit.as_mut().expect("hero kit").doomed_at = None;
        unit.invuln_until = 0.0;
        unit.alive = false;
        unit.hp = 0.0;
        spells::maybe_revive(battle, hero);
        let name = battle.unit(hero).name.clone();
        battle.log_event(vec![
            round_decimal(t, 1).into(),
            "dies".into(),
            name.into(),
            hero.team.as_str().into(),
        ]);
        return;
    }
    let regen = kit.regen;
    if regen != 0.0 {
        let amount = regen * battle.dt;
        battle.unit_mut(hero).heal(amount);
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.has("Meteor Staff") && t >= kit.next_meteor {
        let level = kit.lv("Meteor Staff").clone();
        let mut candidates = targets(battle, true);
        if candidates.is_empty() {
            candidates = battle
                .buildings
                .iter()
                .filter(|b| battle.building_targetable(b.id))
                .map(|b| EntityRef::Building(b.id))
                .collect();
        }
        let u = battle.unit(hero);
        let mut best = None;
        let mut closest = f64::INFINITY;
        for target in candidates {
            let (x, y) = battle.entity_position(target);
            let distance = dist(x, y, u.x, u.y);
            if best.is_none() || distance < closest {
                best = Some(target);
                closest = distance;
            }
        }
        if let Some(target) = best {
            let (x, y) = battle.entity_position(target);
            let mut pending = Pending::new(
                t + 0.8,
                x,
                y,
                battle
                    .catalog
                    .stats
                    .attrs("Meteor Staff")
                    .at("radius")
                    .f64(),
                col(battle, "Meteor Staff", &level, &["damage per hit"], 0.0),
                true,
                true,
                &battle.unit(hero).name,
            );
            pending.extra.hero_impact = Some("blast".to_owned());
            pending.actor = Some(EntityRef::Unit(hero));
            pending.effect = Some(Tag::Meteor);
            effects::damage_source(battle, Some(EntityRef::Unit(hero)), Tag::Meteor, |battle| {
                battle.add_pending(pending);
            });
        }
        let next = t + col(battle, "Meteor Staff", &level, &["cooldown time"], 0.0);
        battle
            .unit_mut(hero)
            .kit
            .as_mut()
            .expect("hero kit")
            .next_meteor = next;
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.has("Electro Boots") {
        let due = battle.unit(hero).extra.boots_next.unwrap_or(t);
        if t >= due || units::isclose(t, due) {
            let damage = col(
                battle,
                "Electro Boots",
                kit.lv("Electro Boots"),
                &["aura damage per hit"],
                0.0,
            );
            let unit = battle.unit(hero);
            let (x, y) = (unit.x, unit.y);
            blast(battle, x, y, 4.5, damage, None, 0.25, false);
            battle.unit_mut(hero).extra.boots_next = Some(t + 0.4);
        }
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if t < kit.heal_until {
        let amount = kit.heal_rate * battle.dt;
        let unit = battle.unit(hero);
        for ally in battle.attackers_near(unit.x, unit.y, 9.0) {
            if !matches!(battle.unit(ally).kind, Tag::Siege | Tag::SiegeIdle) {
                battle.unit_mut(ally).heal(amount);
            }
        }
    }
}

// heroes.py:348-402: cooldowns are keyed by typed source identity.
pub fn on_damaged(
    battle: &mut Battle,
    hero: UnitRef,
    amount: f64,
    source: Option<EntityRef>,
    effect: &str,
) {
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.has("Snake Bracelet") {
        // heroes.py:398-408: every 300 damage, up to the lifetime summon cap.
        let level = kit.lv("Snake Bracelet");
        let cap = col(
            battle,
            "Snake Bracelet",
            level,
            &["max summoned snakes"],
            54.0,
        ) as i64;
        let snake_level = col(battle, "Snake Bracelet", level, &["snake level"], 10.0) as i64;
        let unit = battle.unit(hero);
        let mut accumulated = unit.extra.snake_dmg + amount;
        let mut made = unit.extra.snakes;
        while accumulated >= 300.0 && made < cap {
            accumulated -= 300.0;
            made += 1;
            let unit = battle.unit(hero);
            battle.spawn(
                "Snake",
                hero.team,
                unit.x + 0.4,
                unit.y + 0.4,
                SpawnOptions {
                    level: Some(Level::Int(snake_level)),
                    kind: Tag::Summon,
                    group: unit.group.clone(),
                    ..Default::default()
                },
            );
        }
        let unit = battle.unit_mut(hero);
        unit.extra.snake_dmg = accumulated;
        unit.extra.snakes = made;
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    let Some(source) = source else {
        return;
    };
    if !kit.has("Revenge Deck")
        || !battle.entity_alive(source)
        || matches!(effect, "trap" | "spell" | "death" | "aura" | "counter")
    {
        return;
    }
    if let EntityRef::Unit(unit) = source {
        let unit = battle.unit(unit);
        if unit.name_id == Name::Firemite && effect == "secondary"
            || unit.name_id == Name::ElectroDragon && effect == "chain"
            || unit.spec.attack == Tag::Suicide
            || matches!(unit.name_id, Name::Yetimite | Name::Electromite)
        {
            return;
        }
    }
    let (x, y) = battle.entity_position(source);
    let unit = battle.unit(hero);
    let counter_range = battle
        .catalog
        .resolved
        .at("revenge_ranges")
        .at(&kit.lv("Revenge Deck").to_string())
        .f64();
    if dist(x, y, unit.x, unit.y) > counter_range {
        return;
    }
    let due = unit
        .extra
        .revenge_cd
        .iter()
        .find(|(key, _)| *key == source)
        .map_or(-1.0, |(_, at)| *at);
    if battle.t < due {
        return;
    }
    let t = battle.t;
    let cds = &mut battle.unit_mut(hero).extra.revenge_cd;
    if let Some((_, at)) = cds.iter_mut().find(|(key, _)| *key == source) {
        *at = t + 0.8;
    } else {
        cds.push((source, t + 0.8));
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    let damage = col(
        battle,
        "Revenge Deck",
        kit.lv("Revenge Deck"),
        &["counter damage"],
        225.0,
    );
    let heal = col(
        battle,
        "Revenge Deck",
        kit.lv("Revenge Deck"),
        &["heal per counter"],
        0.0,
    );
    battle.unit_mut(hero).heal(heal);
    effects::damage_source(
        battle,
        Some(EntityRef::Unit(hero)),
        Tag::Counter,
        |battle| {
            damage_target(battle, source, damage);
        },
    );
}

// heroes.py:408-440.
pub fn damage_taken_mult(battle: &Battle, hero: UnitRef) -> f64 {
    let unit = battle.unit(hero);
    let kit = unit.kit.as_ref().expect("hero kit");
    let reduction = if battle.t < kit.reduction_until {
        kit.reduction
    } else {
        0.0
    };
    1.0 - reduction.max(effects::torch_stats(unit, battle.t).1)
}

pub fn strike_bonus(battle: &mut Battle, hero: UnitRef) -> f64 {
    let multiplier = battle.atk_hero_mult;
    let unit = battle.unit_mut(hero);
    let kit = unit.kit.as_mut().expect("hero kit");
    let mut bonus = 0.0;
    if kit.spear_shots > 0 {
        kit.spear_shots -= 1;
        bonus += kit.spear_bonus * multiplier;
        if kit.spear_shots == 0 {
            if let Some(range) = unit.extra.spear_base_range.take() {
                unit.range = range;
            }
        }
    }
    let vamp = if kit.doomed_at.is_none() {
        kit.vamp
    } else {
        0.0
    };
    if vamp != 0.0 {
        unit.heal(vamp);
    }
    bonus
}

pub fn monolith_bonus(battle: &Battle, hero: UnitRef, target: EntityRef) -> f64 {
    let Some(tiers) = battle.unit(hero).kit.as_ref().expect("hero kit").mono_arrow else {
        return 0.0;
    };
    let stage = if battle.monolith_housing <= 180 {
        0
    } else if battle.monolith_housing <= 250 {
        1
    } else {
        2
    };
    let hp = match target {
        EntityRef::Building(id) => battle.building(id).max_hp,
        EntityRef::Wall(id) => battle.walls[id.0].max_hp,
        EntityRef::Unit(id) => battle.unit(id).max_hp,
        EntityRef::Trap(_) => panic!("Monolith Arrow trap target"),
    };
    tiers[stage] * hp
}

// heroes.py:484-512: stable chain selection, then the primary target's slow.
pub fn on_hit_extra(battle: &mut Battle, hero: UnitRef, target: EntityRef) {
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.has("Electro Fangs") {
        let level = kit.lv("Electro Fangs");
        let mut damage = col(battle, "Electro Fangs", level, &["damage per hit"], 0.0);
        let count = col(battle, "Electro Fangs", level, &["number of targets"], 0.0) as i64;
        let mut previous = target;
        let mut visited = vec![target];
        for _ in 0..count {
            let (x, y) = battle.entity_position(previous);
            let mut best = None;
            let mut closest = f64::INFINITY;
            for candidate in target_candidates(battle, false, true) {
                if visited.contains(&candidate) {
                    continue;
                }
                let distance = distance(battle, candidate, x, y);
                if distance <= 3.0 && (best.is_none() || distance < closest) {
                    best = Some(candidate);
                    closest = distance;
                }
            }
            let Some(next) = best else {
                break;
            };
            visited.push(next);
            damage_target(battle, next, damage);
            previous = next;
            damage *= 0.8;
        }
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if let Some((slow, duration)) = kit.frozen_arrow {
        if matches!(target, EntityRef::Building(_) | EntityRef::Unit(_)) {
            let until = battle.t + duration;
            add_target_slow(
                battle,
                target,
                StatusSource::Actor("Frozen Arrow".to_owned(), hero.id),
                1.0 - slow,
                1.0 - slow,
                until,
            );
        }
    }
}

// heroes.py:474-504: owner loss precedes dash completion and the defeat blast.
pub fn on_death(battle: &mut Battle, hero: UnitRef) -> bool {
    if let Some(pet) = battle.unit(hero).pet {
        pets::owner_defeated(battle, pet);
        let t = battle.t;
        let pet = battle.unit_mut(pet);
        pet.extra.rampage_detached = true;
        if pet.name_id == Name::AngryJelly {
            pet.extra.brainwash_until = t;
            pet.extra.paused_timers.brainwash_until = true;
        }
    }
    if battle.unit(hero).dash.is_some() {
        end_dash(battle, hero);
    }
    let unit = battle.unit(hero);
    let kit = unit.kit.as_ref().expect("hero kit");
    if kit.has("Fire Heart") && !unit.extra.fire_heart_done {
        let damage = col(
            battle,
            "Fire Heart",
            kit.lv("Fire Heart"),
            &["damage on defeat"],
            0.0,
        );
        let (x, y) = (unit.x, unit.y);
        battle.unit_mut(hero).extra.fire_heart_done = true;
        // heroes.py:508-512: Fire Heart reaches structures, walls and all defenders.
        battle.splash_buildings(
            x,
            y,
            4.0,
            damage,
            SplashBuildingsOptions {
                walls: true,
                ..Default::default()
            },
        );
        battle.splash_units(
            x,
            y,
            4.0,
            damage,
            true,
            true,
            SplashUnitsOptions {
                team: Team::Def,
                ..Default::default()
            },
        );
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.phoenix && kit.pet_unit.is_some_and(|pet| battle.unit(pet).alive) {
        let egg = kit.pet_unit.expect("Phoenix egg");
        let duration = battle
            .catalog
            .stats
            .get(
                "Phoenix",
                kit.pet_level.as_ref().expect("pet level"),
                &["Revive Duration"],
                Some(8.5),
            )
            .expect("Phoenix revive duration");
        let until = battle.t + duration;
        let unit = battle.unit_mut(hero);
        let kit = unit.kit.as_mut().expect("hero kit");
        kit.phoenix = false;
        kit.doomed_at = Some(until);
        unit.hp = 1.0;
        unit.invuln_until = until;
        let pet = battle.unit_mut(egg);
        pet.extra.egg = false;
        pet.invisible_until = 0.0;
        pet.invuln_until = until;
        pet.extra.phoenix_until = until;
        pet.extra.paused_timers.phoenix_until = true;
        return true;
    }
    false
}

// heroes.py:508-803: stable equipment priority, under ability provenance.
pub fn activate(battle: &mut Battle, hero: UnitRef, on_ko: bool) {
    effects::damage_source(
        battle,
        Some(EntityRef::Unit(hero)),
        Tag::Ability,
        |battle| {
            activate_effect(battle, hero, on_ko);
        },
    );
}

fn activate_effect(battle: &mut Battle, hero: UnitRef, on_ko: bool) {
    let unit = battle.unit(hero);
    if unit.kit.is_none() || unit.ability_used || !unit.alive {
        return;
    }
    let recovery = unit.kit.as_ref().expect("hero kit").hp_recovery;
    let unit = battle.unit_mut(hero);
    unit.ability_used = true;
    // heroes.py:566-570: a KO leaves 1 HP before applying activation healing.
    if on_ko {
        unit.hp = 1.0;
    }
    unit.heal(recovery);
    let t = battle.t;
    let mut target = battle.unit(hero).target;
    if target.is_some_and(|target| match target {
        EntityRef::Building(id) => !battle.building_targetable(id),
        EntityRef::Unit(id) => !battle.unit(id).targetable(battle),
        _ => false,
    }) {
        target = None;
    }
    let mut equipment = battle
        .unit(hero)
        .kit
        .as_ref()
        .expect("hero kit")
        .equip
        .clone();
    equipment.sort_by_key(|name| match name.as_str() {
        "Fireball" => 0,
        "Rocket Backpack" => 1,
        "Lavaloon Puppet" => 3,
        _ => 2,
    });
    for name in equipment {
        let level = battle
            .unit(hero)
            .kit
            .as_ref()
            .expect("hero kit")
            .lv(&name)
            .clone();
        match name.as_str() {
            "Giant Arrow" => {
                let ability = battle.catalog.equipment_ability(&name, &level);
                let damage = game_float(ability, "Damage");
                line(battle, hero, target, 75.0, 1.0, damage);
            }
            "Spiky Ball" => {
                let damage = col(battle, &name, &level, &["projectile damage"], 0.0);
                let count = col(battle, &name, &level, &["number of targets"], 0.0) as i64;
                let mut hit = Vec::new();
                let candidates = ball_targets(battle, &hit);
                let u = battle.unit(hero);
                let current = if target.is_some_and(|target| candidates.contains(&target)) {
                    target
                } else {
                    // output/research/usage/barbarian-king.md:19; initial targeting includes size.
                    // https://supercell.com/en/games/clashofclans/blog/release-notes/june-update-full-patch-notes/
                    candidates.iter().copied().min_by(|left, right| {
                        distance(battle, *left, u.x, u.y)
                            .total_cmp(&distance(battle, *right, u.x, u.y))
                    })
                };
                if let Some(victim) = current.filter(|_| count > 0) {
                    hit.push(victim);
                    let (x, y) = battle.entity_position(victim);
                    let row =
                        battle
                            .catalog
                            .game_data("projectiles", "BarbarianKingGearFootball", None);
                    let speed = game_int(row, "Speed", 0) as f64 / 100.0;
                    let u = battle.unit(hero);
                    let mut pending = Pending::new(
                        t + dist(u.x, u.y, x, y) / speed,
                        u.x,
                        u.y,
                        0.0,
                        damage,
                        false,
                        true,
                        &u.name,
                    );
                    pending.extra.hero_impact = Some("ball".to_owned());
                    pending.extra.remaining = count as usize;
                    pending.extra.visited = hit;
                    pending.actor = Some(EntityRef::Unit(hero));
                    pending.target = Some(victim);
                    battle.add_pending(pending);
                }
            }
            "Earthquake Boots" => {
                let spell_level = equipment_ability_level(&level);
                let spell = battle.catalog.game_data(
                    "spells",
                    "Earthquake Boots Spell",
                    Some(&spell_level),
                );
                let count = game_required_int(spell, "NumberOfHits");
                let gap = game_required_int(spell, "TimeBetweenHitsMS") as f64 / 1000.0;
                let u = battle.unit(hero);
                let mut field =
                    Field::new("boots_quake", u.x, u.y, 8.0, t + (count - 1) as f64 * gap);
                field.value = game_float(spell, "BuildingDamagePermil") / 1000.0;
                field.extra.troop = game_float(spell, "TroopDamagePermil") / 1000.0;
                field.started = t;
                let field = Rc::new(RefCell::new(field));
                for index in 0..count {
                    let u = battle.unit(hero);
                    let mut pending = Pending::new(
                        crate::geom::round6(t + index as f64 * gap),
                        u.x,
                        u.y,
                        8.0,
                        0.0,
                        false,
                        true,
                        &u.name,
                    );
                    pending.team = Team::Def;
                    pending.extra.hero_impact = Some("boots_quake".to_owned());
                    pending.extra.field = Some(Rc::clone(&field));
                    pending.actor = Some(EntityRef::Unit(hero));
                    battle.add_pending(pending);
                }
                for index in 0..battle.walls.len() {
                    let wall = &battle.walls[index];
                    let u = battle.unit(hero);
                    if wall.alive && dist(wall.x, wall.y, u.x, u.y) <= 8.0 {
                        battle.hit_building(EntityRef::Wall(wall.id), 1e9, None, "normal");
                    }
                }
            }
            // heroes.py:654-677: active reduction, independent Rage, and shot bonus.
            "Giant Gauntlet" => {
                let reduction =
                    col(battle, &name, &level, &["incoming damage reduction"], 0.0) / 100.0;
                let until = t + col(battle, &name, &level, &["ability duration"], 0.0);
                let unit = battle.unit_mut(hero);
                let kit = unit.kit.as_mut().expect("hero kit");
                kit.reduction = reduction;
                kit.reduction_until = until;
                unit.extra.gauntlet_until = until;
                unit.extra.paused_timers.gauntlet_until = true;
                unit.extra.gauntlet_radius = 2.5;
            }
            "Rage Vial" => {
                let damage = 1.0 + col(battle, &name, &level, &["damage increase"], 0.0) / 100.0;
                let ability = battle.catalog.equipment_ability(&name, &level);
                let speed = game_float(ability, "SpeedBoost") / 100.0;
                units::add_rage(
                    battle.unit_mut(hero),
                    StatusSource::Name(name.clone()),
                    damage,
                    speed,
                    t + 10.0,
                );
            }
            "Invisibility Vial" => {
                let until = t + col(battle, &name, &level, &["ability duration"], 0.0);
                let bonus = col(battle, &name, &level, &["damage per shot increase"], 0.0);
                let unit = battle.unit_mut(hero);
                invisible(unit, until);
                unit.extra.vial_until = until;
                unit.extra.paused_timers.vial_until = true;
                unit.extra.vial_bonus = bonus;
            }
            "Dark Orb" => {
                let u = battle.unit(hero);
                let (dx, dy) = u.extra.facing;
                let length = py_hypot(dx, dy);
                let length = if length == 0.0 { 1.0 } else { length };
                let mut pending = Pending::new(
                    t,
                    u.x,
                    u.y,
                    5.0,
                    col(battle, &name, &level, &["projectile damage"], 0.0),
                    true,
                    true,
                    &u.name,
                );
                pending.extra.hero_impact = Some("orb".to_owned());
                pending.extra.direction = Some((dx / length, dy / length));
                pending.extra.speed = 12.5;
                pending.extra.until = t + 1.25;
                pending.extra.last_at = t;
                pending.extra.slow = col(battle, &name, &level, &["slow down"], 0.0) / 100.0;
                pending.extra.duration = col(battle, &name, &level, &["slow down duration"], 0.0);
                battle.add_pending(pending);
            }
            "Action Figure" => {
                let level = col(battle, &name, &level, &["giant giant level"], 10.0) as i64;
                let (x, y) = summon_position(battle, hero, target, 0, 1, false, py_hypot(0.5, 0.5));
                let unit = battle.unit(hero);
                battle.spawn(
                    "Giant Giant",
                    Team::Atk,
                    x,
                    y,
                    SpawnOptions {
                        level: Some(Level::Int(level)),
                        kind: Tag::Summon,
                        group: unit.group.clone(),
                        ..Default::default()
                    },
                );
                invisible(battle.unit_mut(hero), t + 1.0);
            }
            "Magic Mirror" => {
                let count = col(battle, &name, &level, &["clones"], 2.0) as i64;
                for index in 0..count {
                    let (x, y) = summon_position(battle, hero, target, index, count, true, 0.5);
                    let unit = battle.unit(hero);
                    let child = battle.spawn(
                        "Archer Queen",
                        Team::Atk,
                        x,
                        y,
                        SpawnOptions {
                            level: unit.level.clone(),
                            kind: Tag::HeroClone,
                            group: unit.group.clone(),
                            ..Default::default()
                        },
                    );
                    let health = col(battle, &name, &level, &["clone health"], 0.0);
                    let dps = col(battle, &name, &level, &["clone dps"], 0.0);
                    let duration = col(battle, &name, &level, &["clone duration"], 0.0);
                    let multiplier = battle.atk_hero_mult;
                    let child = battle.unit_mut(child);
                    child.hp = health;
                    child.max_hp = health;
                    child.base_max_hp = health;
                    child.dmg = dps * child.interval;
                    child.hp *= multiplier;
                    child.max_hp *= multiplier;
                    child.base_max_hp *= multiplier;
                    child.dmg *= multiplier;
                    child.extra.mirror_clone = true;
                    child.extra.expire_at = t + duration;
                    child.ability_used = true;
                }
                invisible(battle.unit_mut(hero), t + 1.0);
            }
            "Henchmen Puppet" => {
                for index in 0..2 {
                    let (x, y) = summon_position(battle, hero, target, index, 2, false, 0.5);
                    let level = col(battle, &name, &level, &["henchmen level"], 7.0) as i64;
                    let group = battle.unit(hero).group.clone();
                    battle.spawn(
                        "Henchman",
                        Team::Atk,
                        x,
                        y,
                        SpawnOptions {
                            level: Some(Level::Int(level)),
                            kind: Tag::Summon,
                            group,
                            ..Default::default()
                        },
                    );
                }
                invisible(battle.unit_mut(hero), t + 1.0);
            }
            "Stun Blaster" => {
                let duration = col(battle, &name, &level, &["stun duration"], 7.5);
                let radius = battle.catalog.stats.attrs(&name).at("radius").f64();
                for target in target_candidates(battle, false, true) {
                    if let EntityRef::Building(id) = target {
                        if matches!(battle.building(id).key.as_str(), "gs" | "es" | "ds") {
                            continue;
                        }
                    }
                    let u = battle.unit(hero);
                    if distance(battle, target, u.x, u.y) <= radius {
                        match target {
                            EntityRef::Building(id) => {
                                let building = battle.building_mut(id);
                                building.stun_until = building.stun_until.max(t + duration);
                            }
                            EntityRef::Unit(id) => {
                                let unit = battle.unit_mut(id);
                                unit.stun_until = unit.stun_until.max(t + duration);
                            }
                            _ => panic!("Stun Blaster target"),
                        }
                        let damage = col(battle, &name, &level, &["ability total damage"], 0.0);
                        damage_target(battle, target, damage);
                    }
                }
            }
            "Barbarian Puppet" | "Archer Puppet" | "Hog Rider Puppet" | "Healer Puppet"
            | "Lavaloon Puppet" => puppet(battle, hero, &name, &level, 0, None),
            "Eternal Tome" => {
                // heroes.py:678-682: emission excludes the recipient's shield tail.
                let ability = battle.catalog.equipment_ability(&name, &level);
                let duration = game_float(ability, "DeactivateAfterTime") / 1000.0;
                battle.unit_mut(hero).extra.tome_until = t + duration;
                battle.unit_mut(hero).extra.paused_timers.tome_until = true;
                moving_auras(battle, hero, None);
            }
            // heroes.py:719-721.
            "Healing Tome" => {
                let rate = col(battle, &name, &level, &["healing per second"], 0.0);
                let until = t + col(battle, &name, &level, &["ability duration"], 20.0);
                let kit = battle.unit_mut(hero).kit.as_mut().expect("hero kit");
                kit.heal_rate = rate;
                kit.heal_until = until;
            }
            "Fireball" => {
                let mut candidates = targets(battle, true);
                if candidates.is_empty() {
                    candidates = targets(battle, false);
                }
                let unit = battle.unit(hero);
                let mut best = None;
                let mut closest = f64::INFINITY;
                for candidate in candidates {
                    let distance = distance(battle, candidate, unit.x, unit.y);
                    if best.is_none() || distance < closest {
                        best = Some(candidate);
                        closest = distance;
                    }
                }
                let (x, y) = best.map_or((0.0, 0.0), |target| battle.entity_position(target));
                let mut pending = Pending::new(
                    t + 1.5,
                    x,
                    y,
                    col(battle, &name, &level, &["damage radius"], 0.0),
                    col(battle, &name, &level, &["projectile damage"], 0.0),
                    true,
                    true,
                    &unit.name,
                );
                pending.extra.hero_impact = Some("blast".to_owned());
                battle.add_pending(pending);
            }
            "Heroic Torch" => {
                let ability = battle.catalog.equipment_ability(&name, &level);
                let duration = game_float(ability, "DeactivateAfterTime") / 1000.0;
                let reduction =
                    col(battle, &name, &level, &["incoming damage reduction"], 0.0) / 100.0;
                let speed = col(
                    battle,
                    &name,
                    &level,
                    &["ability attributes / speed increase"],
                    0.0,
                ) / 8.0;
                let unit = battle.unit_mut(hero);
                unit.extra.torch_until = t + duration;
                unit.extra.paused_timers.torch_until = true;
                unit.extra.torch_reduction = reduction;
                unit.extra.torch_speed = speed;
                moving_auras(battle, hero, None);
            }
            "Seeking Shield" => {
                let unit = battle.unit_mut(hero);
                unit.extra.attack_lock_until = t + 1.2;
                unit.extra.paused_timers.attack_lock_until = true;
                let unit = battle.unit(hero);
                // heroes.py:761-765: automatic KO activation releases instantly.
                let delay = if on_ko { 0.0 } else { 0.933 };
                let mut pending = Pending::new(
                    t + delay,
                    unit.x,
                    unit.y,
                    0.0,
                    col(battle, &name, &level, &["projectile damage"], 0.0),
                    true,
                    true,
                    &unit.name,
                );
                pending.extra.hero_impact = Some("shield".to_owned());
                pending.extra.remaining = 4;
                battle.add_pending(pending);
            }
            "Rocket Spear" => {
                let spear_range = spear_range(battle);
                let shots = col(battle, &name, &level, &["number of attacks"], 9.0) as i64;
                let bonus = col(battle, &name, &level, &["damage per shot increase"], 0.0);
                let unit = battle.unit_mut(hero);
                let kit = unit.kit.as_mut().expect("hero kit");
                kit.spear_shots = shots;
                kit.spear_bonus = bonus;
                if unit.extra.spear_base_range.is_none() {
                    unit.extra.spear_base_range = Some(unit.range);
                }
                unit.range = spear_range;
            }
            "Haste Vial" => {
                let duration = col(battle, &name, &level, &["ability duration"], 10.0);
                let speed = col(battle, &name, &level, &["speed increase"], 0.0) / 8.0;
                let attack = 1.0
                    + col(
                        battle,
                        &name,
                        &level,
                        &["ability attributes / attack speed increase"],
                        0.0,
                    ) / 100.0;
                let source = StatusSource::Name(name.clone());
                let unit = battle.unit_mut(hero);
                let value = (speed, t + duration);
                if let Some((_, previous)) = unit
                    .extra
                    .haste_effects
                    .iter_mut()
                    .find(|(key, _)| *key == source)
                {
                    *previous = value;
                } else {
                    unit.extra.haste_effects.push((source, value));
                }
                unit.extra.haste_attack_until = t + duration;
                unit.extra.haste_attack = attack;
                unit.extra.paused_timers.haste_attack_until = true;
                // heroes.py:721-722: preserve the current ordinary attack cooldown.
            }
            // heroes.py:944-973: target selection precedes delayed damage and freeze.
            "Frost Flake" => {
                let count = col(battle, &name, &level, &["number of targets"], 7.0) as i64;
                let mut visited = Vec::new();
                for _ in 0..count {
                    let mut candidates = targets(battle, true);
                    candidates.retain(|target| !visited.contains(target));
                    if candidates.is_empty() {
                        candidates = targets(battle, false);
                        candidates.retain(|target| !visited.contains(target));
                    }
                    let unit = battle.unit(hero);
                    let mut best = None;
                    let mut closest = f64::INFINITY;
                    for candidate in candidates {
                        let distance = distance(battle, candidate, unit.x, unit.y);
                        if best.is_none() || distance < closest {
                            best = Some(candidate);
                            closest = distance;
                        }
                    }
                    let Some(target) = best else {
                        break;
                    };
                    visited.push(target);
                    let damage = col(battle, &name, &level, &["projectile damage"], 0.0);
                    let (x, y) = battle.entity_position(target);
                    let unit = battle.unit(hero);
                    let mut pending = Pending::new(
                        t + dist(unit.x, unit.y, x, y) / 15.0,
                        x,
                        y,
                        0.0,
                        damage,
                        true,
                        true,
                        &unit.name,
                    );
                    pending.extra.hero_impact = Some("frost".to_owned());
                    pending.extra.duration =
                        col(battle, &name, &level, &["slow down duration"], 0.0);
                    pending.actor = Some(EntityRef::Unit(hero));
                    pending.target = Some(target);
                    battle.add_pending(pending);
                }
            }
            // heroes.py:840-842.
            "Metal Pants" => {
                let reduction =
                    col(battle, &name, &level, &["incoming damage reduction"], 0.0) / 100.0;
                let until = t + col(battle, &name, &level, &["ability duration"], 15.0);
                let kit = battle.unit_mut(hero).kit.as_mut().expect("hero kit");
                kit.reduction = reduction;
                kit.reduction_until = until;
            }
            "Portal Pendant" => portal(battle, hero, &level),
            "Rocket Backpack" => {
                let ability = battle.catalog.equipment_ability(&name, &level);
                let damage = game_float(ability, "ActAsPenetratingDamage");
                start_dash(battle, hero, damage);
            }
            // heroes.py:877-893: Backpack's dash direction takes priority.
            "Flame Blower" => {
                let damage = col(battle, &name, &level, &["ability damage"], 0.0);
                let unit = battle.unit(hero);
                let direction = unit
                    .dash
                    .as_ref()
                    .map_or(unit.extra.facing, |dash| dash.direction);
                battle.unit_mut(hero).extra.flame_direction = Some(direction);
                let facing = crate::geom::py_atan2(direction.1, direction.0);
                let half_angle = (60.0 * (std::f64::consts::PI / 180.0)) / 2.0;
                let radius = battle.catalog.stats.attrs(&name).at("radius").f64();
                let mut targets = target_candidates(battle, false, true);
                targets.extend(
                    battle
                        .walls
                        .iter()
                        .filter(|wall| wall.alive)
                        .map(|wall| EntityRef::Wall(wall.id)),
                );
                for target in targets {
                    let (x, y) = battle.entity_position(target);
                    let unit = battle.unit(hero);
                    let angle = crate::geom::py_atan2(y - unit.y, x - unit.x);
                    let offset = ((angle - facing + std::f64::consts::PI)
                        .rem_euclid(2.0 * std::f64::consts::PI)
                        - std::f64::consts::PI)
                        .abs();
                    if offset <= half_angle && distance(battle, target, unit.x, unit.y) <= radius {
                        damage_target(battle, target, damage);
                    }
                }
            }
            // These pieces have passive effects only in Python's activate.
            "Electro Boots" | "Revenge Deck" | "Fire Heart" | "Rage Gem" | "Meteor Staff"
            | "Noble Iron" | "Vampstache" | "Snake Bracelet" | "Frozen Arrow"
            | "Monolith Arrow" | "Life Gem" | "Stick Horse" | "Royal Gem" | "Dark Crown"
            | "Electro Fangs" => {}
            _ => panic!("unsupported hero ability equipment {name}"),
        }
    }
    let name = battle.unit(hero).name.clone();
    battle.log_event(vec![
        round_decimal(t, 1).into(),
        "ability".into(),
        name.into(),
    ]);
}

// heroes.py:898-921: movement updates the fallback facing even without a target.
fn summon_facing(battle: &mut Battle, hero: UnitRef, target: Option<EntityRef>) -> f64 {
    let target_position = target.map(|target| battle.entity_position(target));
    let unit = battle.unit_mut(hero);
    let previous = unit.extra.summon_position.unwrap_or((unit.x, unit.y));
    if (unit.x, unit.y) != previous {
        unit.extra.summon_facing = Some((unit.x - previous.0, unit.y - previous.1));
    }
    unit.extra.summon_position = Some((unit.x, unit.y));
    let (mut dx, mut dy) = unit.extra.summon_facing.unwrap_or(unit.extra.facing);
    if let Some((x, y)) = target_position.filter(|position| *position != (unit.x, unit.y)) {
        dx = x - unit.x;
        dy = y - unit.y;
    }
    crate::geom::py_atan2(dy, dx)
}

fn summon_position(
    battle: &mut Battle,
    hero: UnitRef,
    target: Option<EntityRef>,
    index: i64,
    count: i64,
    behind: bool,
    radius: f64,
) -> (f64, f64) {
    let mut angle = summon_facing(battle, hero, target);
    if behind {
        angle += std::f64::consts::PI;
    }
    angle += std::f64::consts::PI * ((index as f64 + 0.5) / count as f64 - 0.5);
    let unit = battle.unit(hero);
    (
        unit.x + radius * crate::geom::py_cos(angle),
        unit.y + radius * crate::geom::py_sin(angle),
    )
}

// heroes.py:924-953: all pending impacts share this cast's diminishing counts.
fn boots_quake_hit(battle: &mut Battle, field: &mut Field) {
    for index in 0..battle.buildings.len() {
        let building = &battle.buildings[index];
        if !(building.alive
            && building.counted
            && building.edge_distance(field.x, field.y) <= field.radius)
        {
            continue;
        }
        let id = building.id;
        let target = EntityRef::Building(id);
        let cached = field
            .extra
            .quake_hits
            .iter()
            .find(|(key, _)| *key == target);
        let count = if let Some((_, count)) = cached {
            *count
        } else {
            battle.building_mut(id).eq_hits += 1;
            let count = battle.building(id).eq_hits;
            field.extra.quake_hits.push((target, count));
            count
        };
        let damage = battle.building(id).max_hp * field.value / (2 * count - 1) as f64;
        battle.hit_building(target, damage, None, "normal");
    }
    for defender in battle.defenders_near(field.x, field.y, field.radius) {
        let unit = battle.unit(defender);
        if unit.flying || unit.kind == Tag::TrapSkeleton {
            continue;
        }
        let target = EntityRef::Unit(defender);
        let cached = field
            .extra
            .quake_hits
            .iter()
            .find(|(key, _)| *key == target);
        let count = if let Some((_, count)) = cached {
            *count
        } else {
            battle.unit_mut(defender).extra.eq_n += 1;
            let count = battle.unit(defender).extra.eq_n;
            field.extra.quake_hits.push((target, count));
            count
        };
        let damage = battle.unit(defender).max_hp * field.extra.troop / (2 * count - 1) as f64;
        battle.hit_unit(defender, damage, None, "normal", None);
    }
}

// heroes.py:956-1147: delayed blasts and Dark Orb's swept path.
pub fn projectile_impact(battle: &mut Battle, mut pending: Pending) {
    match pending
        .extra
        .hero_impact
        .as_deref()
        .expect("hero impact mode")
    {
        "boots_quake" => {
            let field = pending
                .extra
                .field
                .as_ref()
                .expect("Earthquake Boots field");
            boots_quake_hit(battle, &mut field.borrow_mut());
        }
        "lizard" => {
            let Some(EntityRef::Unit(actor)) = pending.actor else {
                panic!("Poison Lizard actor");
            };
            let Some(EntityRef::Unit(target)) = pending.target else {
                panic!("Poison Lizard target");
            };
            units::projectile_impact(battle, pending);
            if battle.unit(target).indirect_targetable(battle) {
                pets::poison_hit(battle, actor, target);
            }
        }
        "blast" => blast(
            battle,
            pending.x,
            pending.y,
            pending.radius,
            pending.damage,
            None,
            1.0,
            pending.effect == Some(Tag::Meteor),
        ),
        // heroes.py:845-855: subsequent puppet batches retain the scheduled clock.
        "puppet" => {
            let Some(EntityRef::Unit(hero)) = pending.actor else {
                panic!("puppet hero actor");
            };
            puppet(
                battle,
                hero,
                pending
                    .extra
                    .equipment
                    .as_deref()
                    .expect("puppet equipment"),
                pending.extra.level.as_ref().expect("puppet level"),
                pending.extra.first,
                Some(pending.at),
            );
        }
        "frost" => {
            let target = pending.target.expect("Frost Flake target");
            let targetable = battle.entity_alive(target)
                && match target {
                    EntityRef::Unit(unit) => battle.unit(unit).indirect_targetable(battle),
                    _ => true,
                };
            if targetable {
                damage_target(battle, target, pending.damage);
                let until = battle.t + pending.extra.duration;
                match target {
                    EntityRef::Building(id) => {
                        let building = battle.building_mut(id);
                        building.frozen_until = building.frozen_until.max(until);
                    }
                    EntityRef::Unit(id) => {
                        let unit = battle.unit_mut(id);
                        unit.frozen_until = unit.frozen_until.max(until);
                    }
                    _ => unreachable!("Frost Flake target"),
                }
            }
        }
        // heroes.py:1161-1180: continue bounces from the exact arrival deadline.
        "ball" => {
            let target = pending.target.expect("Spiky Ball target");
            (pending.x, pending.y) = battle.entity_position(target);
            if battle.entity_alive(target)
                && match target {
                    EntityRef::Unit(unit) => battle.unit(unit).indirect_targetable(battle),
                    _ => true,
                }
            {
                damage_target(battle, target, pending.damage);
            }
            pending.extra.remaining -= 1;
            if pending.extra.remaining == 0 {
                return;
            }
            let candidates = ball_targets(battle, &pending.extra.visited);
            let Some(target) = nearest_center(battle, &candidates, pending.x, pending.y) else {
                return;
            };
            pending.extra.visited.push(target);
            let (x, y) = battle.entity_position(target);
            let row = battle
                .catalog
                .game_data("projectiles", "BarbarianKingGearFootball", None);
            let speed = game_int(row, "Speed", 0) as f64 / 100.0;
            pending.at += dist(pending.x, pending.y, x, y) / speed;
            pending.target = Some(target);
            battle.add_pending(pending);
        }
        // heroes.py:883-917: sweep only the newly travelled segment each tick.
        "arrow" => {
            let (dx, dy) = pending.extra.direction.expect("Giant Arrow direction");
            let previous = pending.extra.travel;
            let row = battle
                .catalog
                .game_data("projectiles", "QueenPierceProjectile", None);
            let speed = game_int(row, "Speed", 0) as f64 / 100.0;
            let travel = pending
                .extra
                .length
                .min((battle.t - pending.released_at.expect("Giant Arrow release")) * speed);
            let targets: Vec<_> = battle
                .buildings
                .iter()
                .map(|b| EntityRef::Building(b.id))
                .chain(battle.walls.iter().map(|w| EntityRef::Wall(w.id)))
                .chain(
                    battle
                        .defenders_pool()
                        .map(|u| EntityRef::Unit(u.reference())),
                )
                .collect();
            for target in targets {
                if !battle.entity_alive(target) || pending.extra.visited.contains(&target) {
                    continue;
                }
                let half = match target {
                    EntityRef::Building(id) => {
                        let building = battle.building(id);
                        if !building.counted {
                            continue;
                        }
                        building.half_hit
                    }
                    EntityRef::Wall(id) => battle.walls[id.0].half_hit,
                    EntityRef::Unit(unit) => {
                        if !battle.unit(unit).indirect_targetable(battle) {
                            continue;
                        }
                        0.0
                    }
                    EntityRef::Trap(_) => unreachable!(),
                };
                let (x, y) = battle.entity_position(target);
                let (px, py) = (x - pending.x, y - pending.y);
                let along = px * dx + py * dy;
                if along + half >= previous
                    && along - half <= travel
                    && 0.0 < along
                    && along < pending.extra.length
                    && (px * dy - py * dx).abs() <= half + pending.radius
                {
                    pending.extra.visited.push(target);
                    let multiplier = if matches!(
                        target,
                        EntityRef::Building(id) if battle.building(id).key == "ad"
                    ) {
                        2.0
                    } else {
                        1.0
                    };
                    damage_target(battle, target, pending.damage * multiplier);
                }
            }
            if travel < pending.extra.length {
                pending.extra.travel = travel;
                pending.at = crate::geom::round6(battle.t + battle.dt);
                battle.add_pending(pending);
            }
        }
        "shield" => {
            if let Some(target) = pending.target {
                (pending.x, pending.y) = battle.entity_position(target);
                if battle.entity_alive(target) {
                    damage_target(battle, target, pending.damage);
                }
                pending.extra.remaining -= 1;
            }
            if pending.extra.remaining == 0 {
                return;
            }
            let mut candidates = targets(battle, true);
            candidates.retain(|target| !pending.extra.visited.contains(target));
            if candidates.is_empty() {
                candidates = targets(battle, false);
                candidates.retain(|target| !pending.extra.visited.contains(target));
            }
            let mut best = None;
            let mut closest = f64::INFINITY;
            for target in candidates {
                let distance = distance(battle, target, pending.x, pending.y);
                if best.is_none() || distance < closest {
                    best = Some(target);
                    closest = distance;
                }
            }
            let Some(target) = best else {
                let Some(EntityRef::Unit(hero)) = pending.actor else {
                    panic!("Seeking Shield actor must be a hero");
                };
                battle.unit_mut(hero).extra.shield_destination = Some((0.0, 0.0));
                return;
            };
            pending.extra.visited.push(target);
            let (x, y) = battle.entity_position(target);
            pending.at += dist(pending.x, pending.y, x, y) / 20.0;
            pending.target = Some(target);
            battle.add_pending(pending);
        }
        "orb" => {
            let at = battle.t.min(pending.extra.until);
            let travel = 0.0_f64.max(at - pending.extra.last_at) * pending.extra.speed;
            let (dx, dy) = pending.extra.direction.expect("Dark Orb direction");
            // heroes.py:1076-1094: indirect hits include invisible targets.
            let targets: Vec<_> = battle
                .buildings
                .iter()
                .map(|b| EntityRef::Building(b.id))
                .chain(
                    battle
                        .defenders_pool()
                        .map(|u| EntityRef::Unit(u.reference())),
                )
                .collect();
            for target in targets {
                if pending.extra.visited.contains(&target) {
                    continue;
                }
                match target {
                    EntityRef::Building(id) => {
                        let b = battle.building(id);
                        if !b.alive
                            || !b.counted && b.key != "th"
                            || battle.t < b.overgrown_until
                            || battle.t < b.extra.yellow_until
                            || b.key == "tesla" && !b.revealed
                        {
                            continue;
                        }
                    }
                    EntityRef::Unit(id) => {
                        let u = battle.unit(id);
                        if !u.indirect_targetable(battle)
                            || u.dash.is_some()
                            || battle.t < u.extra.yellow_until
                        {
                            continue;
                        }
                    }
                    _ => unreachable!("Dark Orb target"),
                }
                let (tx, ty) = battle.entity_position(target);
                let along = (tx - pending.x) * dx + (ty - pending.y) * dy;
                let along = travel.min(0.0_f64.max(along));
                let (x, y) = (pending.x + dx * along, pending.y + dy * along);
                if distance(battle, target, x, y) > pending.radius {
                    continue;
                }
                pending.extra.visited.push(target);
                damage_target(battle, target, pending.damage);
                let slow = 1.0 - pending.extra.slow;
                let Some(EntityRef::Unit(actor)) = pending.actor else {
                    panic!("Dark Orb actor must be a hero");
                };
                add_target_slow(
                    battle,
                    target,
                    StatusSource::Actor("Dark Orb".to_owned(), actor.id),
                    slow,
                    slow,
                    battle.t + pending.extra.duration,
                );
            }
            pending.x += dx * travel;
            pending.y += dy * travel;
            pending.extra.last_at = at;
            if at < pending.extra.until {
                pending.at = (battle.t + battle.dt).min(pending.extra.until);
                battle.add_pending(pending);
            }
        }
        // heroes.py:951-1097 defines all equipment/pet modes above.
        mode => panic!("unsupported hero projectile mode {mode}"),
    }
}

// heroes.py:873-884: all buildings precede targetable ground defenders.
fn ball_targets(battle: &Battle, hit: &[EntityRef]) -> Vec<EntityRef> {
    let buildings: Vec<_> = battle
        .buildings
        .iter()
        .map(|b| EntityRef::Building(b.id))
        .filter(|target| !hit.contains(target))
        .filter(
            |target| matches!(target, EntityRef::Building(id) if battle.building_targetable(*id)),
        )
        .collect();
    if !buildings.is_empty() {
        return buildings;
    }
    battle
        .defenders_pool()
        .filter(|u| {
            !hit.contains(&EntityRef::Unit(u.reference())) && !u.flying && u.targetable(battle)
        })
        .map(|u| EntityRef::Unit(u.reference()))
        .collect()
}

fn nearest_center(battle: &Battle, candidates: &[EntityRef], x: f64, y: f64) -> Option<EntityRef> {
    let mut best = None;
    let mut closest = f64::INFINITY;
    for &target in candidates {
        let (tx, ty) = battle.entity_position(target);
        let distance = dist(tx, ty, x, y);
        if best.is_none() || distance < closest {
            best = Some(target);
            closest = distance;
        }
    }
    best
}

fn add_target_slow(
    battle: &mut Battle,
    target: EntityRef,
    source: StatusSource,
    movement: f64,
    attack: f64,
    until: f64,
) {
    match target {
        EntityRef::Unit(unit) => {
            effects::add_slow(battle.unit_mut(unit), source, movement, attack, until);
        }
        EntityRef::Building(id) => {
            let slows = &mut battle.building_mut(id).extra.slows;
            let value = (movement, attack, until);
            if let Some((_, previous)) = slows.iter_mut().find(|(key, _)| *key == source) {
                *previous = value;
            } else {
                slows.push((source, value));
            }
        }
        _ => panic!("equipment slow requires a building or unit"),
    }
}

// heroes.py:887-911: building, wall, defender order; no visibility filter.
fn line(
    battle: &mut Battle,
    hero: UnitRef,
    target: Option<EntityRef>,
    length: f64,
    width: f64,
    damage: f64,
) {
    let unit = battle.unit(hero);
    let (x, y) = (unit.x, unit.y);
    let (dx, dy) = target.map_or(unit.extra.facing, |target| {
        let (tx, ty) = battle.entity_position(target);
        (tx - x, ty - y)
    });
    let magnitude = py_hypot(dx, dy);
    let magnitude = if magnitude == 0.0 { 1.0 } else { magnitude };
    // heroes.py:992-1022: normalize before multiplying along/cross distances.
    let mut pending = Pending::new(
        battle.t + battle.dt,
        x,
        y,
        width,
        damage,
        true,
        true,
        &unit.name,
    );
    pending.extra.hero_impact = Some("arrow".to_owned());
    pending.extra.direction = Some((dx / magnitude, dy / magnitude));
    pending.extra.length = length;
    pending.actor = Some(EntityRef::Unit(hero));
    battle.add_pending(pending);
}

// heroes.py:1025-1083: preserve batch indices, spawn order and the scheduled clock.
fn puppet(
    battle: &mut Battle,
    hero: UnitRef,
    equipment: &str,
    equipment_level: &Level,
    first: i64,
    at: Option<f64>,
) {
    let (troop, count_column, level_column) = match equipment {
        "Barbarian Puppet" => ("Barbarian", "summoned barbarians", None),
        "Archer Puppet" => ("Archer", "summoned archers", None),
        "Hog Rider Puppet" => ("Hog Rider", "summoned hog riders", Some("hog rider level")),
        "Healer Puppet" => ("Healer", "summoned healers", Some("healer level")),
        "Lavaloon Puppet" => ("Lavaloon", "summoned lavaloons", Some("lavaloon level")),
        _ => unreachable!("puppet equipment"),
    };
    let t = battle.t;
    if equipment == "Hog Rider Puppet" && first == 0 {
        invisible(battle.unit_mut(hero), t + 1.0);
    }
    let count = col(battle, equipment, equipment_level, &[count_column], 1.0) as i64;
    let level = match level_column {
        Some(column) => Some(Level::Int(
            col(battle, equipment, equipment_level, &[column], 0.0) as i64,
        )),
        None => battle.plan.researched_level(troop).cloned().flatten(),
    };
    // heroes.py:1188-1200: Hog/Healer Puppets also use three-unit batches.
    let ability = match equipment {
        "Barbarian Puppet" => Some("BarbarianKingSpawnBarbarians"),
        "Archer Puppet" => Some("ArcherQueenSpawnArchers"),
        "Hog Rider Puppet" => Some("RCEquipSpawnHogs"),
        "Healer Puppet" => Some("ArcherQueenSpawnHealers"),
        "Lavaloon Puppet" => Some("GrandWardenSummonLavaloon"),
        _ => None,
    };
    let (batch, delay) = ability.map_or((count, 0.0), |name| {
        let row = battle.catalog.game_data("special_abilities", name, None);
        let batch = game_int(row, "SpawnnedTroopsPerHit", count);
        let delay = game_int(row, "SpawnDelayBetweenHitsMS", 0) as f64 / 1000.0;
        (batch, delay)
    });
    for index in first..(first + batch).min(count) {
        let (x, y) = if equipment == "Healer Puppet" {
            let target = battle.unit(hero).target;
            summon_position(battle, hero, target, index, count, true, 0.6)
        } else {
            let angle = 2.0 * std::f64::consts::PI * index as f64 / count.max(1) as f64;
            let unit = battle.unit(hero);
            (
                unit.x + 0.6 * crate::geom::py_cos(angle),
                unit.y + 0.6 * crate::geom::py_sin(angle),
            )
        };
        let unit = battle.unit(hero);
        let summon = battle.spawn(
            troop,
            Team::Atk,
            x,
            y,
            SpawnOptions {
                level: level.clone(),
                kind: Tag::Summon,
                group: unit.group.clone(),
                town_hall: Some(battle.plan.town_hall()),
                ..Default::default()
            },
        );
        if equipment == "Archer Puppet" {
            let duration = col(
                battle,
                equipment,
                equipment_level,
                &["archer invisibility duration"],
                6.0,
            );
            invisible(battle.unit_mut(summon), t + duration);
        }
        if equipment == "Barbarian Puppet" {
            let damage = 1.0
                + col(
                    battle,
                    equipment,
                    equipment_level,
                    &["barbarian damage increase"],
                    0.0,
                ) / 100.0;
            let speed = col(
                battle,
                equipment,
                equipment_level,
                &["barbarian speed increase"],
                0.0,
            ) / 8.0;
            units::add_rage(
                battle.unit_mut(summon),
                StatusSource::Name(equipment.to_owned()),
                damage,
                speed,
                t + 20.0,
            );
        }
    }
    if first + batch < count {
        let u = battle.unit(hero);
        let mut pending = Pending::new(
            at.unwrap_or(battle.t) + delay,
            u.x,
            u.y,
            0.0,
            0.0,
            false,
            false,
            &u.name,
        );
        pending.extra.hero_impact = Some("puppet".to_owned());
        pending.extra.equipment = Some(equipment.to_owned());
        pending.extra.level = Some(equipment_level.clone());
        pending.extra.first = first + batch;
        pending.actor = Some(EntityRef::Unit(hero));
        battle.add_pending(pending);
    }
}

// heroes.py:947-977: suspend the pet without changing its identity.
pub fn start_dash(battle: &mut Battle, hero: UnitRef, damage: f64) {
    // heroes.py:1231-1232: end Ice Block's freeze while retaining its reduction.
    let t = battle.t;
    let unit = battle.unit_mut(hero);
    unit.frozen_until = unit.frozen_until.min(t);
    let world = battle.catalog.world as f64;
    let unit = battle.unit(hero);
    let (mut dx, mut dy) = (world / 2.0 - unit.x, world / 2.0 - unit.y);
    let mut distance = py_hypot(dx, dy);
    if distance == 0.0 {
        (dx, dy) = unit.extra.facing;
        distance = py_hypot(dx, dy);
    }
    dx /= distance;
    dy /= distance;
    let mut limits = Vec::new();
    for (position, direction) in [(unit.x, dx), (unit.y, dy)] {
        if direction > 0.0 {
            limits.push((world - 0.5 - position) / direction);
        } else if direction < 0.0 {
            limits.push((0.5 - position) / direction);
        }
    }
    let travel = 0.0_f64.max(limits.into_iter().reduce(f64::min).expect("dash direction"));
    let pet = unit.pet.filter(|pet| battle.unit(*pet).alive);
    let dash = Dash {
        direction: (dx, dy),
        until: battle.t + travel / 15.0,
        end: (unit.x + dx * travel, unit.y + dy * travel),
        hit: Vec::new(),
        damage,
        pet,
    };
    let unit = battle.unit_mut(hero);
    unit.extra.facing = (dx, dy);
    unit.dash = Some(dash);
    if let Some(pet) = pet {
        let pet = battle.unit_mut(pet);
        pet.extra.suspended = true;
        pet.in_pool = false;
    }
}

// heroes.py:980-988: Python appends the returning pet at the list tail.
pub fn end_dash(battle: &mut Battle, hero: UnitRef) {
    let pet = battle.unit_mut(hero).dash.take().expect("active dash").pet;
    if let Some(pet) = pet {
        let (x, y) = (battle.unit(hero).x, battle.unit(hero).y);
        let unit = battle.unit_mut(pet);
        unit.extra.suspended = false;
        if unit.alive {
            unit.x = x;
            unit.y = y;
            if !unit.in_pool {
                unit.in_pool = true;
                battle.attacker_order.retain(|reference| *reference != pet);
                battle.attacker_order.push(pet);
            }
        }
    }
}

// heroes.py:991-1011.
pub fn dash_step(battle: &mut Battle, hero: UnitRef) {
    let t = battle.t;
    if t < battle.unit(hero).extra.pushed_until {
        return;
    }
    let dash = battle.unit(hero).dash.as_ref().expect("active dash");
    let remaining = 0.0_f64.max(dash.until - t);
    let step = 15.0 * battle.dt.min(remaining);
    let (dx, dy) = dash.direction;
    let unit = battle.unit_mut(hero);
    unit.x += dx * step;
    unit.y += dy * step;
    for index in 0..battle.buildings.len() {
        let building = &battle.buildings[index];
        let unit = battle.unit(hero);
        let dash = unit.dash.as_ref().expect("active dash");
        let target = EntityRef::Building(building.id);
        if building.alive
            && !dash.hit.contains(&target)
            && building.edge_distance(unit.x, unit.y) <= 1.5
        {
            let damage = dash.damage;
            battle
                .unit_mut(hero)
                .dash
                .as_mut()
                .expect("active dash")
                .hit
                .push(target);
            battle.hit_building(target, damage, None, "normal");
        }
    }
    let unit = battle.unit(hero);
    for defender in battle.defenders_near(unit.x, unit.y, 1.5) {
        let dash = battle.unit(hero).dash.as_ref().expect("active dash");
        let target = EntityRef::Unit(defender);
        let unit = battle.unit(defender);
        if !dash.hit.contains(&target) && unit.alive && !unit.underground {
            let damage = dash.damage;
            battle
                .unit_mut(hero)
                .dash
                .as_mut()
                .expect("active dash")
                .hit
                .push(target);
            battle.hit_unit(
                defender,
                damage,
                None,
                "normal",
                Some(EntityRef::Unit(hero)),
            );
        }
    }
    let dash = battle.unit(hero).dash.as_ref().expect("active dash");
    if t + battle.dt >= dash.until {
        let (x, y) = dash.end;
        let unit = battle.unit_mut(hero);
        unit.x = x;
        unit.y = y;
        end_dash(battle, hero);
    }
}

// heroes.py:1014-1053.
pub fn distance(battle: &Battle, target: EntityRef, x: f64, y: f64) -> f64 {
    match target {
        EntityRef::Unit(unit) => battle.unit(unit).dist(x, y),
        EntityRef::Building(id) => battle.building(id).edge_distance(x, y),
        EntityRef::Wall(id) => battle.walls[id.0].edge_distance(x, y),
        EntityRef::Trap(_) => panic!("hero distance to trap"),
    }
}

pub fn targets(battle: &Battle, defenses: bool) -> Vec<EntityRef> {
    target_candidates(battle, defenses, false)
}

// heroes.py:_targets: indirect equipment damage may reach invisible targets.
fn target_candidates(battle: &Battle, defenses: bool, indirect: bool) -> Vec<EntityRef> {
    let mut result: Vec<_> = battle
        .buildings
        .iter()
        .filter(|building| {
            let targetable = if indirect {
                building.alive
                    && (building.counted || building.key == "th")
                    && battle.t >= building.overgrown_until
                    && battle.t >= building.extra.yellow_until
                    && (building.key != "tesla" || building.revealed)
            } else {
                battle.building_targetable(building.id)
            };
            targetable && (!defenses || battle.is_defense_target(building.id))
        })
        .map(|building| EntityRef::Building(building.id))
        .collect();
    if !defenses {
        result.extend(
            battle
                .defenders_pool()
                .filter(|u| {
                    if indirect {
                        u.indirect_targetable(battle)
                            && u.dash.is_none()
                            && battle.t >= u.extra.yellow_until
                    } else {
                        u.targetable(battle)
                    }
                })
                .map(|u| EntityRef::Unit(u.reference())),
        );
    }
    result
}

pub fn damage_target(battle: &mut Battle, target: EntityRef, damage: f64) {
    if let EntityRef::Unit(unit) = target {
        battle.hit_unit(unit, damage, None, "normal", None);
    } else {
        battle.hit_building(target, damage, None, "normal");
    }
}

pub fn blast(
    battle: &mut Battle,
    x: f64,
    y: f64,
    radius: f64,
    damage: f64,
    exclude: Option<EntityRef>,
    hero_mult: f64,
    walls: bool,
) {
    let targets: Vec<_> = battle
        .buildings
        .iter()
        .map(|b| EntityRef::Building(b.id))
        .chain(
            battle
                .defenders_pool()
                .map(|u| EntityRef::Unit(u.reference())),
        )
        .collect();
    for target in targets {
        if Some(target) == exclude || !battle.entity_alive(target) {
            continue;
        }
        let hero = match target {
            EntityRef::Unit(unit) => {
                let unit = battle.unit(unit);
                if unit.underground {
                    continue;
                }
                unit.is_hero
            }
            EntityRef::Building(id) => {
                if !battle.building(id).counted {
                    continue;
                }
                false
            }
            _ => unreachable!(),
        };
        if distance(battle, target, x, y) <= radius {
            damage_target(
                battle,
                target,
                if hero { damage * hero_mult } else { damage },
            );
        }
    }
    if walls {
        for index in 0..battle.walls.len() {
            let wall = &battle.walls[index];
            if wall.alive && wall.edge_distance(x, y) <= radius {
                let id = wall.id;
                damage_target(battle, EntityRef::Wall(id), damage);
            }
        }
    }
}

// heroes.py:1202-1229: recipient tails last one second after the final aura tick.
fn moving_auras(battle: &mut Battle, warden: UnitRef, members: Option<&[UnitRef]>) {
    let t = battle.t;
    let unit = battle.unit(warden);
    let extra = &unit.extra;
    let (tome, torch, speed, reduction) = (
        extra.tome_until,
        extra.torch_until,
        extra.torch_speed,
        extra.torch_reduction,
    );
    if t >= tome && t >= torch {
        return;
    }
    let source = StatusSource::Name(unit.id.0.to_string());
    let members = members.map_or_else(
        || battle.attackers_near(unit.x, unit.y, 9.0),
        |members| members.to_vec(),
    );
    for ally in members {
        let unit = battle.unit_mut(ally);
        if unit.name_id == Name::Totem {
            continue;
        }
        if t < tome {
            if let Some((_, until)) = unit.extra.tomes.iter_mut().find(|(key, _)| *key == source) {
                *until = t + 1.0;
            } else {
                unit.extra.tomes.push((source.clone(), t + 1.0));
            }
        }
        if t < torch && !matches!(unit.kind, Tag::Siege | Tag::SiegeIdle) {
            let speed = if unit.is_hero && ally != warden {
                speed / 2.0
            } else {
                speed
            };
            let value = (t + 1.0, speed, reduction);
            if let Some((_, old)) = unit
                .extra
                .torches
                .iter_mut()
                .find(|(key, _)| *key == source)
            {
                *old = value;
            } else {
                unit.extra.torches.push((source.clone(), value));
            }
        }
    }
}

// heroes.py:1082-1140: all combatants reset before any strongest-buff selection.
pub fn apply_auras(battle: &mut Battle) {
    let t = battle.t;
    let mut combatants = std::mem::take(&mut battle.actor_scratch);
    combatants.clear();
    combatants.extend(
        battle
            .attackers_pool()
            .chain(battle.defenders_pool())
            .map(Unit::reference),
    );
    let mut want = std::mem::take(&mut battle.aura_want_scratch);
    want.clear();
    for &reference in &combatants {
        let boost = effects::crown_buff(battle, reference);
        let unit = battle.unit_mut(reference);
        unit.aura_dmg = 1.0 + boost;
        for (_, (until, increase)) in &unit.extra.rage_auras {
            if t < *until {
                unit.aura_dmg = unit.aura_dmg.max(1.0 + increase);
            }
        }
        if boost != 0.0 {
            want.push((reference, (boost, f64::INFINITY)));
        }
    }
    // Aura updates do not change life, name, team or pool membership. This
    // walks the same filtered combatant snapshot without a second allocation.
    for &reference in &combatants {
        let unit = battle.unit(reference);
        if !unit.alive || !matches!(unit.name_id, Name::GrandWarden | Name::ApprenticeWarden) {
            continue;
        }
        let (percentage, cap, rage, radius) = if unit.name_id == Name::ApprenticeWarden {
            (
                battle
                    .catalog
                    .stats
                    .get(
                        "Apprentice Warden",
                        unit.level.as_ref().expect("Warden level"),
                        &["Aura HP Increase"],
                        None,
                    )
                    .expect("aura HP increase")
                    / 100.0,
                f64::INFINITY,
                0.0,
                7.0,
            )
        } else {
            moving_auras(battle, reference, None);
            let kit = battle.unit(reference).kit.as_ref();
            let (mut percentage, mut cap, mut rage) = (0.0, 0.0, 0.0);
            if let Some(kit) = kit {
                if kit.has("Life Gem") {
                    percentage = col(
                        battle,
                        "Life Gem",
                        kit.lv("Life Gem"),
                        &["% hp increase"],
                        0.0,
                    ) / 100.0;
                    cap = col(
                        battle,
                        "Life Gem",
                        kit.lv("Life Gem"),
                        &["max hp increase"],
                        0.0,
                    );
                }
                if kit.has("Rage Gem") {
                    rage = col(
                        battle,
                        "Rage Gem",
                        kit.lv("Rage Gem"),
                        &["% damage increase"],
                        0.0,
                    ) / 100.0;
                }
            }
            (percentage, cap, rage, 9.0)
        };
        let unit = battle.unit(reference);
        let (x, y) = (unit.x, unit.y);
        for &ally in &combatants {
            if ally.team != reference.team {
                continue;
            }
            let unit = battle.unit(ally);
            if !unit.alive
                || dist(unit.x, unit.y, x, y) > radius
                || ally == reference
                || unit.name_id == Name::Totem
                || matches!(unit.kind, Tag::Siege | Tag::SiegeIdle)
            {
                continue;
            }
            if percentage != 0.0 {
                if let Some((_, (previous_pct, previous_cap))) =
                    want.iter_mut().find(|(unit, _)| *unit == ally)
                {
                    if (percentage * unit.base_max_hp).min(cap)
                        > (*previous_pct * unit.base_max_hp).min(*previous_cap)
                    {
                        *previous_pct = percentage;
                        *previous_cap = cap;
                    }
                } else if (percentage * unit.base_max_hp).min(cap) > 0.0 {
                    want.push((ally, (percentage, cap)));
                }
            }
            let increase = if unit.is_hero { rage / 2.0 } else { rage };
            let unit = battle.unit_mut(ally);
            if increase != 0.0 {
                let source = StatusSource::Name(reference.id.0.to_string());
                let value = (t + 1.0, increase);
                if let Some((_, old)) = unit
                    .extra
                    .rage_auras
                    .iter_mut()
                    .find(|(key, _)| *key == source)
                {
                    *old = value;
                } else {
                    unit.extra.rage_auras.push((source, value));
                }
            }
            unit.aura_dmg = unit.aura_dmg.max(1.0 + increase);
        }
    }
    for &reference in &combatants {
        if battle.unit(reference).alive {
            let (percentage, cap) = want
                .iter()
                .find(|(unit, _)| *unit == reference)
                .map_or((0.0, 0.0), |(_, value)| *value);
            let ally = battle.unit_mut(reference);
            let transferred = std::mem::take(&mut ally.extra.meteor_aura_transfer);
            if transferred && percentage != 0.0 {
                ally.aura_bonus = (ally.base_max_hp * percentage).min(cap);
                ally.max_hp = ally.base_max_hp + ally.aura_bonus;
            }
            effects::health_aura(ally, percentage, cap);
        }
    }
    combatants.clear();
    want.clear();
    battle.actor_scratch = combatants;
    battle.aura_want_scratch = want;
}

// heroes.py:1826-1852: rooftop activation precedes Smasher's one-time enrage.
pub fn guardians_tick(battle: &mut Battle) {
    let Some(guardian) = battle.guardian.filter(|g| battle.unit(*g).alive) else {
        return;
    };
    let t = battle.t;
    let th_down = battle.th.is_some_and(|th| !battle.building(th).alive);
    let g = battle.unit(guardian);
    // output/research/usage/freeze-spell.md:20; frozen Guardians cannot activate.
    // https://supercell.com/en/games/clashofclans/blog/release-notes/the-sound-of-clash-update/
    if g.extra.waiting && t >= g.frozen_until {
        let trigger = g.extra.guardian_trigger.expect("Guardian trigger radius");
        let near = battle
            .attackers_near(g.x, g.y, trigger)
            .into_iter()
            .any(|attacker| {
                let a = battle.unit(attacker);
                a.name_id != Name::Totem && t >= a.invisible_until && !a.underground
            });
        if near || th_down {
            let g = battle.unit_mut(guardian);
            g.extra.waiting = false;
            g.active_at = t + 0.5;
        }
    }
    let g = battle.unit(guardian);
    if g.spec.has_special(Special::Smasher) && th_down && !g.extra.enraged {
        let g = battle.unit_mut(guardian);
        g.extra.enraged = true;
        g.dmg *= 1.6;
        g.speed *= 1.6;
    }
}

// units.py:1024-1028: called at the Smasher branch of units::on_death.
// Keep this at that call site so nested deaths retain Python's field order.
// Integration: replace units.rs's Smasher TODO with heroes::guardian_death(battle, unit).
pub fn guardian_death(battle: &mut Battle, guardian: UnitRef) {
    let g = battle.unit(guardian);
    if g.team != Team::Def || !g.spec.has_special(Special::Smasher) {
        return;
    }
    let mut field = Field::new("def_rage", g.x, g.y, 5.0, battle.t + 18.0);
    field.team = Team::Def;
    field.value = 1.6;
    field.started = battle.t;
    battle.fields.push(field);
}

// units.py:2553-2578: called inside after_unit_hit's secondary source scope.
// Each pass queries the buckets anew: collateral deaths and prior nudges can
// change membership, and the primary victim's position stays live throughout.
// Integration: replace units.rs's Logger TODO with
// heroes::guardian_after_hit(battle, unit, target, damage).
pub fn guardian_after_hit(battle: &mut Battle, guardian: UnitRef, target: UnitRef, damage: f64) {
    let g = battle.unit(guardian);
    if !g.spec.has_special(Special::Logger) {
        return;
    }
    let travel = battle
        .catalog
        .stats
        .get(
            &g.name,
            g.level.as_ref().expect("Logger level"),
            &["Post-Hit Tile Range"],
            None,
        )
        .expect("Logger post-hit range");
    let raw = battle.catalog.stats.attrs(&g.name).at("raw");
    let push = stats::num(raw.at("Pushback Range"), None).expect("Logger pushback range");
    let victim = battle.unit(target);
    let (dx, dy) = (victim.x - g.x, victim.y - g.y);
    let distance = py_hypot(dx, dy);
    let distance = if distance == 0.0 { 1.0 } else { distance };
    let (dx, dy) = (dx / distance, dy / distance);
    let radius = travel + g.spec.splash;
    for other in battle.attackers_near(victim.x, victim.y, radius) {
        let v = battle.unit(other);
        if other == target || !v.alive || v.underground {
            continue;
        }
        let victim = battle.unit(target);
        let (px, py) = (v.x - victim.x, v.y - victim.y);
        let along = px * dx + py * dy;
        if 0.0 < along && along <= travel && (px * dy - py * dx).abs() <= 0.8 {
            battle.hit_unit(
                other,
                damage,
                None,
                "normal",
                Some(EntityRef::Unit(guardian)),
            );
        }
    }
    let victim = battle.unit(target);
    for other in battle.attackers_near(victim.x, victim.y, radius) {
        let v = battle.unit(other);
        let victim = battle.unit(target);
        let (px, py) = (v.x - victim.x, v.y - victim.y);
        if px * dx + py * dy >= -1.5
            && (px * dy - py * dx).abs() <= 1.5
            && v.name_id != Name::Totem
            && !matches!(v.kind, Tag::Siege | Tag::SiegeIdle)
        {
            battle.nudge(other, dx * push, dy * push);
            let v = battle.unit_mut(other);
            v.target = None;
            v.wall_target = None;
            units::reset_beam(v);
        }
    }
}

// Declared synthetic CLI fixtures for heroes.py:1806-1852 and
// units.py:839-864,1024-1028,2553-2578. No real-game calibration is implied.
// main.rs wires guardian-check to this entry point; exercise the real units
// callbacks so missing Smasher/Logger integration fails instead of passing.
pub fn guardian_check(catalog: std::sync::Arc<crate::catalog::Catalog>) -> Result<(), String> {
    use crate::json;
    use std::sync::Arc;

    let plan = json::parse(
        r#"{
        "$type": "Stage", "drops": [], "ticks": [], "town_hall": 18,
        "strength": 1.0, "loadouts": {}, "revives_left": 0
    }"#,
    )
    .map_err(|error| error.to_string())?;
    let fixture = |name: &str, level: i64, mode: &str, upgrading: &str| {
        let layout = json::parse(&format!(
            r#"{{
            "buildings": [{{"key": "th", "x": 20, "y": 20}}],
            "walls": [], "traps": [], "heroes": [], "cc_troops": [],
            "guardian": "{name}", "levels": {{"guardian": {level}}}
        }}"#
        ))
        .expect("synthetic Guardian layout");
        let options = json::parse(&format!(
            r#"{{
            "town_hall": 18, "battle_mode": "{mode}",
            "upgrading": [{upgrading}], "modifier": "legend1"
        }}"#
        ))
        .expect("synthetic Guardian options");
        crate::setup::build(&layout, &plan, &options, Arc::clone(&catalog))
            .expect("supported Guardian fixture")
    };
    let mut cases = 0;
    for name in ["Longshot", "Smasher", "Logger"] {
        for level in [0, 1, 2, 3, 4, 5] {
            let mut battle = fixture(name, level, "ranked", "");
            let guardian = battle.guardian.expect("TH18 Guardian");
            let th = battle.th.expect("fixture Town Hall");
            let expected_level = if level == 0 {
                catalog.stats.max_level(name, 18).expect("Guardian maximum")
            } else {
                level
            };
            let numbers = catalog.numbers(name, &Level::Int(expected_level));
            let g = battle.unit(guardian);
            assert_eq!(g.level, Some(Level::Int(expected_level)));
            assert_eq!(g.kind, Tag::Guardian);
            assert!(!g.is_hero);
            assert_eq!(g.home, Some((battle.building(th).x, battle.building(th).y)),);
            assert_eq!(g.y, battle.building(th).y + 1.0);
            assert_eq!(g.hp.to_bits(), (numbers.hp * 1.2).to_bits());
            assert_eq!(g.dmg.to_bits(), (numbers.dmg * 1.2).to_bits());
            assert!(battle.building(th).weapon.is_none());
            assert!(!battle.is_defense_target(th));
            assert_eq!(spells::poison_factors(g, 100.0, 0.5, 0.6), (0.0, 0.0, 0.0),);
            let (x, y) = (g.x, g.y);
            let (trigger, leash) = match name {
                "Longshot" => (19.0, 17.0),
                "Smasher" => (14.0, 12.0),
                "Logger" => (15.0, 14.0),
                _ => unreachable!(),
            };
            assert_eq!(g.extra.guardian_trigger, Some(trigger));
            assert_eq!(g.leash, leash);
            battle.t = 2.0;
            guardians_tick(&mut battle);
            assert!(battle.unit(guardian).extra.waiting);
            let intruder = battle.spawn(
                "Archer",
                Team::Atk,
                x + trigger + 0.25,
                y,
                SpawnOptions::default(),
            );
            battle.refresh_buckets();
            guardians_tick(&mut battle);
            assert!(battle.unit(guardian).extra.waiting);
            battle.unit_mut(intruder).x = x + trigger;
            battle.refresh_buckets();
            battle.unit_mut(intruder).invisible_until = 3.0;
            guardians_tick(&mut battle);
            assert!(battle.unit(guardian).extra.waiting);
            battle.unit_mut(intruder).invisible_until = 2.0;
            battle.unit_mut(intruder).underground = true;
            guardians_tick(&mut battle);
            assert!(battle.unit(guardian).extra.waiting);
            battle.unit_mut(intruder).underground = false;
            // A Totem cannot wake the Guardian, even on the trigger boundary.
            battle.unit_mut(intruder).name_id = Name::Totem;
            guardians_tick(&mut battle);
            assert!(battle.unit(guardian).extra.waiting);
            battle.unit_mut(intruder).name_id = Name::from_str("Archer");
            guardians_tick(&mut battle);
            let g = battle.unit(guardian);
            assert!(!g.extra.waiting);
            assert_eq!(g.active_at, 2.5);
            assert!(!g.targetable(&battle));
            assert_eq!(
                spells::poison_factors(g, 100.0, 0.5, 0.6),
                (30.0, 0.15, 0.18),
            );
            guardians_tick(&mut battle);
            assert_eq!(battle.unit(guardian).active_at, 2.5);
            battle.t = 2.5;
            assert!(battle.unit(guardian).targetable(&battle));
            cases += 1;

            // Town Hall destruction wakes a waiting Guardian with no attacker.
            let mut battle = fixture(name, level, "ranked", "");
            let guardian = battle.guardian.expect("TH18 Guardian");
            let th = battle.th.expect("fixture Town Hall");
            let (damage, speed) = (battle.unit(guardian).dmg, battle.unit(guardian).speed);
            battle.t = 4.0;
            battle.hit_building(EntityRef::Building(th), 1e9, None, "normal");
            guardians_tick(&mut battle);
            let g = battle.unit(guardian);
            assert!(!g.extra.waiting);
            assert_eq!(g.active_at, 4.5);
            let multiplier = if name == "Smasher" { 1.6 } else { 1.0 };
            assert_eq!(g.dmg.to_bits(), (damage * multiplier).to_bits());
            assert_eq!(g.speed.to_bits(), (speed * multiplier).to_bits());
            assert_eq!(g.extra.enraged, name == "Smasher");
            let (damage, speed) = (g.dmg, g.speed);
            guardians_tick(&mut battle);
            assert_eq!(battle.unit(guardian).dmg.to_bits(), damage.to_bits());
            assert_eq!(battle.unit(guardian).speed.to_bits(), speed.to_bits());
            battle.kill(guardian);
            if name == "Smasher" {
                let field = battle.fields.last().expect("Smasher death Rage callback");
                assert_eq!(field.kind, Tag::DefRage);
                assert_eq!(field.team, Team::Def);
                assert_eq!(field.radius, 5.0);
                assert_eq!(field.value, 1.6);
                assert_eq!(field.started, 4.0);
                assert_eq!(field.until, 22.0);
            } else if name == "Longshot" {
                let pending = battle.pending.last().expect("Longshot death bomb");
                assert_eq!(pending.at.to_bits(), (4.0_f64 + 0.2).to_bits());
                assert_eq!(pending.radius, 3.5);
                assert!(pending.hits_air && pending.hits_ground);
                assert_eq!(pending.team, Team::Atk);
                assert_eq!(pending.actor, Some(EntityRef::Unit(guardian)));
            }
            guardians_tick(&mut battle);
            cases += 1;
        }
        for upgrading in [r#""guardian""#, r#""th""#] {
            assert!(fixture(name, 1, "multiplayer", upgrading)
                .guardian
                .is_none());
            assert!(fixture(name, 1, "ranked", upgrading).guardian.is_some());
            cases += 2;
        }
    }
    for level in [1, 5] {
        let mut battle = fixture("Logger", level, "ranked", "");
        let guardian = battle.guardian.expect("Logger fixture");
        let g = battle.unit_mut(guardian);
        g.x = 10.0;
        g.y = 10.0;
        let target = battle.spawn("Giant", Team::Atk, 21.5, 10.0, SpawnOptions::default());
        let tail = battle.spawn("Giant", Team::Atk, 27.0, 10.0, SpawnOptions::default());
        let buried = battle.spawn("Giant", Team::Atk, 23.5, 10.5, SpawnOptions::default());
        battle.unit_mut(buried).underground = true;
        let siege = battle.spawn(
            "Giant",
            Team::Atk,
            23.5,
            10.0,
            SpawnOptions {
                kind: Tag::Siege,
                ..Default::default()
            },
        );
        let behind = battle.spawn("Giant", Team::Atk, 20.0, 10.0, SpawnOptions::default());
        let tail_hp = battle.unit(tail).hp;
        let buried_hp = battle.unit(buried).hp;
        let siege_hp = battle.unit(siege).hp;
        for other in [target, buried] {
            let v = battle.unit_mut(other);
            v.target = Some(EntityRef::Unit(guardian));
            v.extra.beam_target = Some(EntityRef::Unit(guardian));
            v.extra.beam_time = Some(2.0);
            v.extra.beam_tick = Some(0.0);
        }
        battle.refresh_buckets();
        units::after_unit_hit(&mut battle, guardian, target, 10.0, true);
        let tail_damage = if level == 5 { 10.0 } else { 0.0 };
        assert_eq!(battle.unit(tail).hp, tail_hp - tail_damage);
        assert_eq!(battle.unit(buried).hp, buried_hp);
        assert_eq!(battle.unit(siege).hp, siege_hp - 10.0);
        assert_eq!(battle.unit(siege).x, 23.5);
        assert_eq!(battle.unit(target).x, 23.0);
        assert_eq!(battle.unit(tail).x, 28.5);
        assert_eq!(battle.unit(buried).x, 25.0);
        for other in [target, buried] {
            let v = battle.unit(other);
            assert!(v.target.is_none() && v.wall_target.is_none());
            assert!(v.extra.beam_target.is_none());
            assert!(v.extra.beam_time.is_none() && v.extra.beam_tick.is_none());
        }
        // This bucket visits the primary first. Its push moves the origin,
        // leaving the trailing unit outside the second pass's -1.5 bound.
        assert_eq!(battle.unit(behind).x, 20.0);
        cases += 1;
    }
    println!("guardian-check: {cases} declared synthetic fixtures passed");
    Ok(())
}

// heroes.py:1348-1350: defenders have no abilities or equipment in Python.
pub fn defending_hero_ability(_battle: &mut Battle, _unit: UnitRef) {}

// heroes.py:1532-1571: Lavaloon bombs share troop damage and attack modifiers.
pub fn summon_tick(battle: &mut Battle, unit: UnitRef) -> bool {
    if battle.unit(unit).name_id != Name::Lavaloon {
        return false;
    }
    if !battle.unit(unit).can_act(battle.t) || battle.t < battle.unit(unit).extra.pushed_until {
        return true;
    }
    let mut target = battle.unit(unit).target;
    let defenses_gone = !battle
        .buildings
        .iter()
        .any(|building| building.alive && battle.is_defense_target(building.id));
    let angry = battle.t < battle.unit(unit).extra.angry_until;
    match target {
        Some(EntityRef::Unit(foe)) => {
            if !battle.unit(foe).targetable(battle) || !defenses_gone || angry {
                target = None;
            }
        }
        Some(EntityRef::Building(id)) if !battle.building_targetable(id) => target = None,
        _ => {}
    }
    if defenses_gone
        && !angry
        && !matches!(target, Some(EntityRef::Unit(_)))
        && battle.t >= battle.unit(unit).extra.next_engage
    {
        battle.unit_mut(unit).extra.next_engage = battle.t + 0.5;
        if battle.t < battle.unit(unit).aware_until || battle.ally_under_attack(unit) {
            if let Some(foe) = battle.nearest_defender(unit, 7.0, false) {
                target = Some(EntityRef::Unit(foe));
                battle.unit_mut(unit).target_kind = Some(Tag::Unit);
            }
        }
    }
    if target.is_none() {
        let (chosen, kind) = battle.choose_target(unit);
        target = chosen;
        battle.unit_mut(unit).target_kind = kind;
    }
    battle.unit_mut(unit).target = target;
    let mut interval = units::attack_interval(battle, unit);
    let u = battle.unit(unit);
    if battle.t < u.extra.haste_attack_until {
        interval /= u.extra.haste_attack;
    }
    interval /= 0.05_f64.max(effects::slow_mult(u, battle.t, false));
    let due = u.extra.bomb_next.unwrap_or(u.spawned_at + interval);
    if battle.t >= due {
        let (rage, _) = units::rage_boost(u, battle.t);
        let damage = u.dmg * rage.max(u.aura_dmg).max(u.extra.bell_damage);
        let (x, y) = (u.x, u.y);
        units::area_hit(battle, unit, x, y, 1.8, damage, true, None);
        let u = battle.unit(unit);
        battle.spawn(
            "Lavaloon Pup",
            unit.team,
            u.x,
            u.y,
            SpawnOptions {
                level: u.level.clone(),
                kind: Tag::Summon,
                owner: Some(unit),
                group: u.group.clone(),
                ..Default::default()
            },
        );
        let next = battle.t + interval;
        battle.unit_mut(unit).extra.bomb_next = Some(next);
    }
    let u = battle.unit(unit);
    if let Some(target) = target {
        if distance(battle, target, u.x, u.y) > u.range {
            battle.move_towards(unit, target, None);
        }
    }
    true
}

// heroes.py:1390-1425: children precede the delayed death bomb.
pub fn summon_death(battle: &mut Battle, unit: UnitRef) {
    let u = battle.unit(unit);
    if u.name_id != Name::Lavaloon {
        return;
    }
    let count = battle
        .catalog
        .stats
        .get(
            "Lavaloon",
            u.level.as_ref().expect("Lavaloon level"),
            &["Lavaloon Pups Spawned (After Death)"],
            None,
        )
        .expect("Lavaloon death count") as usize;
    // heroes.py:1730-1746: draw one radius per pup, in evenly spaced order.
    let row = battle
        .catalog
        .game_data("characters", "GW Equipment Lavaloon", u.level.as_ref());
    let spawn_distance = game_required_int(row, "SecondarySpawnDist") as f64 / 100.0;
    let spawn_offset = game_int(row, "SecondarySpawnOffset", 0) as f64 / 100.0;
    let randomize_distance = row
        .get("RandomizeSecSpawnDist")
        .and_then(crate::json::Json::opt_str)
        == Some("TRUE");
    for index in 0..count {
        let angle = 2.0 * std::f64::consts::PI * index as f64 / count.max(1) as f64;
        let mut radius = spawn_distance;
        if randomize_distance {
            radius *= battle.rng.as_mut().expect("battle rng").random();
        }
        radius += spawn_offset;
        let u = battle.unit(unit);
        battle.spawn(
            "Lavaloon Pup",
            unit.team,
            u.x + radius * crate::geom::py_cos(angle),
            u.y + radius * crate::geom::py_sin(angle),
            SpawnOptions {
                level: u.level.clone(),
                kind: Tag::Summon,
                owner: Some(unit),
                group: u.group.clone(),
                ..Default::default()
            },
        );
    }
    let u = battle.unit(unit);
    let damage = battle
        .catalog
        .stats
        .get(
            "Lavaloon",
            u.level.as_ref().expect("Lavaloon level"),
            &["Damage when Destroyed"],
            None,
        )
        .expect("Lavaloon death damage");
    let mut pending = Pending::new(
        battle.t + 0.416,
        u.x,
        u.y,
        2.0,
        damage,
        false,
        true,
        &u.name,
    );
    pending.team = if unit.team == Team::Atk {
        Team::Def
    } else {
        Team::Atk
    };
    pending.extra.buildings = if unit.team == Team::Atk { damage } else { 0.0 };
    pending.actor = Some(EntityRef::Unit(unit));
    pending.effect = Some(Tag::Death);
    battle.add_pending(pending);
}

// heroes.py:1428-1432.
fn invisible(unit: &mut Unit, until: f64) {
    unit.invisible_until = unit.invisible_until.max(until);
    unit.extra.equipment_invisible_until = unit.extra.equipment_invisible_until.max(until);
    unit.extra.paused_timers.equipment_invisible_until = true;
}

// heroes.py:1435-1449: also preprocessed in the exported catalog.
pub fn summon_spec(name: &str, mut specification: UnitSpec) -> UnitSpec {
    match name {
        "Henchman" | "Booger" => specification.walls = Tag::Fly,
        "Lavaloon" => specification.prefer = Tag::AirDefense,
        "Frostmite" => {
            specification.prefer = Tag::Defense;
            specification.walls = Tag::Ignore;
            specification.engages_units = false;
        }
        _ => {}
    }
    specification
}

// heroes.py:1452-1470: new members receive active moving Warden auras.
pub fn new_member(battle: &mut Battle, reference: UnitRef) {
    let unit = battle.unit_mut(reference);
    match unit.name.as_str() {
        "Frostmite" => unit.housing = 1,
        "Booger" => unit.housing = 4,
        _ => {}
    }
    if battle.buckets_initialized {
        let unit = battle.unit(reference);
        let cell = ((unit.x / 4.0) as i32, (unit.y / 4.0) as i32);
        let index = if let Some(&index) = battle.bucket_indices.get(&cell) {
            index
        } else {
            let index = battle.buckets.len();
            let members = battle.spare_bucket_members.pop().unwrap_or_default();
            battle.buckets.push((cell, members));
            battle.bucket_indices.insert(cell, index);
            index
        };
        if !battle.buckets[index].1.contains(&reference) {
            battle.buckets[index].1.push(reference);
        }
    }
    let unit = battle.unit(reference);
    let wardens: Vec<_> = battle
        .attackers_pool()
        .filter(|warden| {
            warden.alive
                && warden.name_id == Name::GrandWarden
                && dist(warden.x, warden.y, unit.x, unit.y) <= 9.0
        })
        .map(Unit::reference)
        .collect();
    for warden in wardens {
        moving_auras(battle, warden, Some(&[reference]));
    }
}

pub fn pet_passives(battle: &mut Battle, unit: UnitRef) {
    pets::passives(battle, unit);
}
pub fn act_pet(battle: &mut Battle, unit: UnitRef) {
    pets::act(battle, unit);
}

// heroes.py:1477-1508: stable hero/housing/spawn-time selection, excluding free pets.
fn portal(battle: &mut Battle, hero: UnitRef, level: &Level) {
    let name = "Portal Pendant";
    let radius = col(battle, name, level, &["portal tile radius"], 0.0);
    let mut capacity = col(battle, name, level, &["recall capacity"], 0.0);
    let unit = battle.unit(hero);
    let mut candidates = battle.attackers_near(unit.x, unit.y, radius);
    candidates.retain(|reference| {
        let unit = battle.unit(*reference);
        *reference != hero
            && unit.name_id != Name::Totem
            && !matches!(unit.kind, Tag::Siege | Tag::SiegeIdle)
            && !free_pet(battle, *reference)
    });
    candidates.sort_by(|first, second| {
        let first = battle.unit(*first);
        let second = battle.unit(*second);
        (!first.is_hero, -spells::interaction_housing(first))
            .cmp(&(!second.is_hero, -spells::interaction_housing(second)))
            .then_with(|| {
                first
                    .spawned_at
                    .partial_cmp(&second.spawned_at)
                    .expect("spawn time")
            })
    });
    let mut taken = vec![hero];
    for candidate in candidates {
        let housing = spells::interaction_housing(battle.unit(candidate)) as f64;
        if housing <= capacity {
            capacity -= housing;
            taken.push(candidate);
        }
    }
    let heal = col(battle, name, level, &["healing on redeploy"], 0.0) / 100.0;
    let duration = col(battle, name, level, &["haste on redeploy"], 0.0);
    let speed = battle
        .catalog
        .stats
        .attrs(name)
        .at("raw")
        .get("Redeploy Speed Increase")
        .and_then(|value| stats::num(value, Some(56.0)))
        .unwrap_or(56.0)
        / 8.0;
    stash(battle, taken, (heal, duration, speed));
}

// heroes.py:1237-1245: these pets travel free with their paired hero.
pub fn free_pet(battle: &Battle, reference: UnitRef) -> bool {
    let u = battle.unit(reference);
    u.kind == Tag::Pet
        && (u.extra.egg
            || u.attached(battle)
            || u.name_id == Name::Sneezy && u.owner.is_some_and(|owner| battle.unit(owner).alive))
}

// heroes.py:1248-1268: Recall and Portal Pendant share the same stash path.
pub fn stash(battle: &mut Battle, mut taken: Vec<UnitRef>, bonuses: (f64, f64, f64)) {
    for reference in taken.clone() {
        // output/research/usage/rocket-backpack.md; cached Rocket_Backpack.txt:
        // https://clashofclans.fandom.com/wiki/Rocket_Backpack
        // The transported pet accompanies a mid-flight Recall for free.
        let transported = battle
            .unit(reference)
            .dash
            .as_ref()
            .and_then(|dash| dash.pet);
        if battle.unit(reference).dash.is_some() {
            end_dash(battle, reference);
        }
        if let Some(pet) = battle.unit(reference).pet {
            if battle.unit(pet).alive
                && (Some(pet) == transported || free_pet(battle, pet))
                && !taken.contains(&pet)
            {
                taken.push(pet);
            }
        }
    }
    let t = battle.t;
    for reference in taken {
        let u = battle.unit_mut(reference);
        if u.extra.recalled.is_some() {
            continue;
        }
        u.extra.recalled = Some(t);
        u.extra.portal = Some(bonuses);
        u.alive = false;
        battle
            .portal_stash
            .push(Value::Ref(EntityRef::Unit(reference)));
    }
    battle.portal_ready_at = t;
}

// heroes.py:1429-1488: only explicitly named timers pause during Recall.
fn resume_timers(unit: &mut Unit, now: f64) {
    let recalled = unit
        .extra
        .recalled
        .take()
        .expect("recalled unit needs a recall time");
    let elapsed = now - recalled;
    let e = &mut unit.extra;
    for (present, deadline) in [
        (e.paused_timers.gauntlet_until, &mut e.gauntlet_until),
        (e.paused_timers.attack_lock_until, &mut e.attack_lock_until),
        (e.paused_timers.horse_until, &mut e.horse_until),
        (e.paused_timers.vial_until, &mut e.vial_until),
        (e.paused_timers.tome_until, &mut e.tome_until),
        (e.paused_timers.torch_until, &mut e.torch_until),
        (
            e.paused_timers.haste_attack_until,
            &mut e.haste_attack_until,
        ),
        (e.paused_timers.angry_until, &mut e.angry_until),
        // heroes.py:1419-1421: Angry Jelly's attachment clock pauses in Recall.
        (e.paused_timers.brainwash_until, &mut e.brainwash_until),
    ] {
        if present {
            *deadline += elapsed;
        }
    }
    if let Some(until) = &mut e.boots_next {
        *until += elapsed;
    }
    if e.clone || e.mirror_clone {
        e.expire_at += elapsed;
    }
    for (_, until) in &mut e.tomes {
        *until += elapsed;
    }
    for (_, (until, _, _)) in &mut e.torches {
        *until += elapsed;
    }
    for (_, until) in &mut e.revenge_cd {
        *until += elapsed;
    }
    for (source, (_, _, until)) in &mut e.rage_effects {
        if matches!(source, StatusSource::Name(name) if name == "Rage Vial" || name == "Barbarian Puppet")
        {
            *until += elapsed;
        }
    }
    for (source, (_, until)) in &mut e.haste_effects {
        if matches!(source, StatusSource::Name(name) if name == "Haste Vial" || name == "Portal Pendant")
        {
            *until += elapsed;
        }
    }
    if e.paused_timers.equipment_invisible_until {
        e.equipment_invisible_until += elapsed;
        unit.invisible_until = unit.invisible_until.max(e.equipment_invisible_until);
    }
    if e.paused_timers.phoenix_until {
        e.phoenix_until += elapsed;
        unit.invuln_until = unit.invuln_until.max(e.phoenix_until);
    }
    if let Some(kit) = &mut unit.kit {
        if kit.reduction_until != 0.0 {
            kit.reduction_until += elapsed;
        }
        if kit.heal_until != 0.0 {
            kit.heal_until += elapsed;
        }
        if kit.next_meteor != 0.0 {
            kit.next_meteor += elapsed;
        }
        if let Some(until) = &mut kit.doomed_at {
            *until += elapsed;
            unit.invuln_until = *until;
        }
    }
}

// heroes.py:1314-1345: stable housing/time order, reuse existing unit identities.
pub fn portal_redeploy(battle: &mut Battle, x: f64, y: f64) {
    assert!(
        battle.can_deploy(x, y),
        "Portal redeployment requires a legal deployment tile"
    );
    let t = battle.t;
    let mut ordered: Vec<_> = battle.portal_units().collect();
    ordered.sort_by(|a, b| {
        let a = battle.unit(*a);
        let b = battle.unit(*b);
        (-spells::interaction_housing(a))
            .cmp(&(-spells::interaction_housing(b)))
            .then_with(|| a.spawned_at.total_cmp(&b.spawned_at))
    });
    let n = ordered.len();
    for reference in ordered {
        let u = battle.unit_mut(reference);
        resume_timers(u, t);
        if u.extra.mirror_clone && t >= u.extra.expire_at {
            u.hp = 0.0;
            continue;
        }
        let (heal, duration, speed) = u.extra.portal.take().expect("portal bonuses");
        u.x = x;
        u.y = y;
        u.alive = true;
        let was_in_pool = u.in_pool;
        u.in_pool = true;
        u.heal(heal * u.max_hp);
        if duration > 0.0 {
            crate::plans::set(
                &mut u.extra.haste_effects,
                StatusSource::Name("Portal Pendant".to_owned()),
                (speed, t + duration),
            );
        }
        u.target = None;
        u.wall_target = None;
        let clone = u.extra.clone;
        if !was_in_pool {
            battle.attacker_order.retain(|r| *r != reference);
            battle.attacker_order.push(reference);
        }
        if clone && !battle.clones.contains(&reference) {
            battle.clones.push(reference);
        }
    }
    battle.log_event(vec![
        round_decimal(t, 1).into(),
        "portal".into(),
        crate::trace::LogValue::Int(n as i64),
        round_decimal(x, 1).into(),
        round_decimal(y, 1).into(),
    ]);
    battle.portal_stash.clear();
    battle.rebuild_buckets();
}
