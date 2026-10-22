//! Ports heroes.py:28-1140,1348-1476. Python constructs defending heroes.

use crate::battle::SpawnOptions;
use crate::catalog::UnitSpec;
use crate::combat::SplashBuildingsOptions;
use crate::geom::{dist, py_hypot};
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
    let keys: Vec<_> = fragments.iter().map(|fragment| format!("~{fragment}")).collect();
    let keys: Vec<_> = keys.iter().map(String::as_str).collect();
    battle.catalog.stats.get(name, level, &keys, Some(default)).expect("numeric default")
}

fn default_loadout(hero: &str) -> Option<HeroLoadout> {
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
fn pet_level(battle: &Battle, hero: UnitRef, loadout: &HeroLoadout, town_hall: i64) -> Option<Level> {
    let name = loadout.pet.as_deref().filter(|name| !name.is_empty())?;
    let stats = &battle.catalog.stats;
    assert!(stats.registry.get(name).is_some() && stats.record(name).at("kind").str() == "pet",
        "{name} is not a pet");
    let maximum = stats.max_level(name, town_hall).unwrap_or_else(|| {
        assert!(battle.plan.observed(), "{name} is unavailable at Town Hall {town_hall}");
        stats.record(name).at("levels").arr().iter()
            .map(|row| row.at("level").i64()).max().expect("pet levels")
    });
    let level = battle.plan.pet_level(name).cloned().unwrap_or(Level::Int(maximum));
    assert!(matches!(&level, Level::Int(value) if 1 <= *value && *value <= maximum),
        "Illegal {name} level {level} at Town Hall {town_hall}");
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
        assert!(!unit.kit.as_ref().is_some_and(|kit| kit.pet_name.as_deref() == Some(name)),
            "{name} is already assigned to {}", unit.name);
        assert!(!(unit.kind == "pet" && unit.name == name && unit.owner != Some(hero)),
            "{name} is already assigned to another Hero");
    }
    assert!(battle.unit(hero).pet.is_none(), "hero already has a pet");
    Some(level)
}

// heroes.py:103-182: equip is called after strength, before league scaling.
pub fn equip(battle: &mut Battle, hero: UnitRef) {
    let name = battle.unit(hero).name.clone();
    let Some(loadout) = battle.plan.loadout(&name).cloned().or_else(|| default_loadout(&name)) else {
        return;
    };
    let th = battle.plan.town_hall();
    let pet_level = pet_level(battle, hero, &loadout, th);
    let mut kit = Kit::new(&name);
    let base_interval = battle.unit(hero).interval;
    let (mut passive_dps, mut passive_speed) = (0.0, 0.0);
    for equipment in &loadout.equipment {
        if battle.catalog.stats.registry.get(equipment).is_none() {
            continue;
        }
        let level = battle.plan.equipment_level(equipment).cloned()
            .filter(|level| !matches!(level, Level::Int(0)))
            .or_else(|| battle.catalog.stats.max_level(equipment, th).map(Level::Int))
            .expect("equipment available at Town Hall");
        kit.equip.push(equipment.clone());
        if let Some((_, previous)) = kit.levels.iter_mut().find(|(name, _)| name == equipment) {
            *previous = level.clone();
        } else {
            kit.levels.push((equipment.clone(), level.clone()));
        }
        let hp = col(battle, equipment, &level, &["hitpoint increase", "hp increase"], 0.0);
        let dps = col(battle, equipment, &level, &["damage per second increase", "dps increase"], 0.0);
        let attack_speed = col(battle, equipment, &level,
            &["hero boosts / attack speed increase", "hero boost / attack speed increase"], 0.0);
        let unit = battle.unit_mut(hero);
        unit.max_hp += hp;
        unit.base_max_hp += hp;
        unit.hp += hp;
        passive_dps += dps;
        passive_speed += attack_speed / 100.0;
        kit.regen += col(battle, equipment, &level, &["self healing per second"], 0.0);
        kit.hp_recovery += col(battle, equipment, &level,
            &["hp recovery increase", "health recovery increase"], 0.0);
        match equipment.as_str() {
            "Electro Boots" => battle.unit_mut(hero).extra.boots_next = Some(battle.t + 0.4),
            "Rocket Spear" | "Revenge Deck" | "Fire Heart" | "Action Figure" | "Giant Arrow"
            | "Eternal Tome" | "Rage Gem" | "Fireball" | "Rocket Backpack" => {}
            _ => todo!("stage 3+: equip {equipment}"),
        }
    }
    let unit = battle.unit_mut(hero);
    unit.dmg += passive_dps * base_interval;
    unit.interval = base_interval / (1.0 + passive_speed);
    kit.hp_recovery += battle.catalog.stats.get(&name,
        battle.unit(hero).level.as_ref().expect("hero level"), &["Health Recovery"], Some(0.0))
        .expect("numeric default");
    if let Some(pet) = loadout.pet.filter(|name| !name.is_empty()) {
        kit.phoenix = pet == "Phoenix";
        kit.pet_name = Some(pet);
        kit.pet_level = pet_level;
        spawn_pet(battle, hero, &mut kit);
    }
    battle.unit_mut(hero).kit = Some(kit);
}

// heroes.py:188-266: pets use a fresh owner-following specification and Unit
// constructor, bypassing spawn/on_spawn and preserving the shared ID counter.
fn spawn_pet(battle: &mut Battle, hero: UnitRef, kit: &mut Kit) {
    let name = kit.pet_name.as_deref().expect("pet name").to_owned();
    let level = kit.pet_level.clone().expect("pet level");
    if !matches!(name.as_str(), "Unicorn" | "Phoenix" | "Frosty" | "Poison Lizard" | "Spirit Fox") {
        todo!("stage 3+: pet {name}");
    }
    let stats = &battle.catalog.stats;
    let attrs = stats.attrs(&name);
    let hp = stats.get(&name, &level, &["hitpoints", "Hitpoints"], Some(2000.0)).expect("pet HP");
    let mut dps = stats.get(&name, &level, &["dps", "Damage per Second", "~damage per second"], Some(0.0))
        .expect("pet DPS");
    if name == "Unicorn" {
        dps = 0.0;
    }
    let interval = attrs.get("attack_interval").and_then(|v| v.opt_f64()).filter(|v| *v != 0.0)
        .or_else(|| attrs.get("attack_interval_ck").and_then(|v| v.opt_f64()).filter(|v| *v != 0.0))
        .unwrap_or(1.0);
    let raw = attrs.get("raw");
    let healing_range = raw.and_then(|raw| raw.get("Healing Range"))
        .and_then(|value| stats::num(value, None)).filter(|value| *value != 0.0);
    let range = healing_range.or_else(|| {
        ["Range", "Attack Range"].iter().find_map(|key| raw.and_then(|raw| raw.get(key))
            .and_then(|value| stats::num(value, None)))
    }).or_else(|| attrs.get("range").and_then(|v| v.opt_f64()))
        .or_else(|| attrs.get("range_ck").and_then(|v| v.opt_f64())).expect("pet range");
    let speed = attrs.get("speed").and_then(|v| v.opt_f64())
        .or_else(|| attrs.get("speed_display").and_then(|v| v.opt_f64()).map(|v| v / 8.0))
        .unwrap_or(0.0);
    let flying = attrs.get("is_flying").is_some_and(|v| v.bool());
    let hits_air = attrs.get("is_air_targeting").map_or(true, |v| v.bool());
    // heroes.py:204 constructs UnitSpec directly, rather than spec(name).
    let mut spec = UnitSpec {
        name: name.clone(),
        prefer: "owner".to_owned(),
        walls: if flying { "fly" } else { "ignore" }.to_owned(),
        attack: "single".to_owned(),
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
        special: Vec::new(),
        heal_air: false,
        flying_override: None,
        notes: String::new(),
    };
    if name == "Phoenix" {
        spec.attack = "splash".to_owned();
        spec.splash = 0.3;
    }
    battle.uid += 1;
    let owner = battle.unit(hero);
    let mut pet = Unit {
        id: UnitId(battle.uid),
        name: name.clone(),
        kind: "pet".to_owned(),
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
        spec,
        alive: true,
        cooldown: 0.0,
        target: None,
        target_kind: None,
        wall_target: None,
        group: "main".to_owned(),
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
    if name == "Spirit Fox" {
        let duration = battle.catalog.stats.get(&name, &level, &["Invisibility Duration"], None)
            .expect("Fox invisibility duration");
        pet.invisible_until = pet.invisible_until.max(battle.t + duration);
        let until = battle.t + duration;
        let hero = battle.unit_mut(hero);
        hero.invisible_until = hero.invisible_until.max(until);
        pet.extra.fox_next = battle.t + duration + 6.0;
    }
    if name == "Phoenix" {
        pet.extra.egg = true;
        pet.invisible_until = 1e9;
        pet.invuln_until = 1e9;
    }
    if name == "Frosty" {
        pet.extra.next_summon = battle.t + stats::num(
            battle.catalog.stats.attrs(&name).at("raw").at("Summon Cooldown"), None)
            .expect("Frosty summon cooldown");
    }
    let reference = pet.reference();
    battle.unit_indices.insert(pet.id, (Team::Atk, battle.attackers.len()));
    battle.attackers.push(pet);
    battle.attacker_order.push(reference);
    new_member(battle, reference);
    kit.pet_unit = Some(reference);
    battle.unit_mut(hero).pet = Some(reference);
}

// heroes.py:275-345: called inside units.pre_tick's aura provenance.
pub fn tick(battle: &mut Battle, hero: UnitRef) {
    let t = battle.t;
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.doomed_at.is_some_and(|until| t >= until) {
        let unit = battle.unit_mut(hero);
        unit.kit.as_mut().expect("hero kit").doomed_at = None;
        unit.invuln_until = 0.0;
        unit.alive = false;
        unit.hp = 0.0;
        spells::maybe_revive(battle, hero);
        let name = battle.unit(hero).name.clone();
        battle.log_event(vec![round_decimal(t, 1).into(), "dies".into(), name.into(), hero.team.as_str().into()]);
        return;
    }
    let regen = kit.regen;
    if regen != 0.0 {
        let amount = regen * battle.dt;
        battle.unit_mut(hero).heal(amount);
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.has("Meteor Staff") {
        todo!("stage 3+: Meteor Staff tick");
    }
    if kit.has("Electro Boots") {
        let due = battle.unit(hero).extra.boots_next.unwrap_or(t);
        if t >= due || units::isclose(t, due) {
            let damage = col(battle, "Electro Boots", kit.lv("Electro Boots"), &["aura damage per hit"], 0.0);
            let unit = battle.unit(hero);
            let (x, y) = (unit.x, unit.y);
            blast(battle, x, y, 4.5, damage, None, 0.25);
            battle.unit_mut(hero).extra.boots_next = Some(t + 0.4);
        }
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if t < kit.heal_until {
        let amount = kit.heal_rate * battle.dt;
        let unit = battle.unit(hero);
        for ally in battle.attackers_near(unit.x, unit.y, 9.0) {
            if !matches!(battle.unit(ally).kind.as_str(), "siege" | "siege_idle") {
                battle.unit_mut(ally).heal(amount);
            }
        }
    }
}

// heroes.py:348-402: cooldowns are keyed by typed source identity.
pub fn on_damaged(
    battle: &mut Battle,
    hero: UnitRef,
    _amount: f64,
    source: Option<EntityRef>,
    effect: &str,
) {
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.has("Snake Bracelet") {
        todo!("stage 3+: Snake Bracelet damage reaction");
    }
    let Some(source) = source else {
        return;
    };
    if !kit.has("Revenge Deck") || !battle.entity_alive(source)
        || matches!(effect, "trap" | "spell" | "death" | "aura" | "counter") {
        return;
    }
    if let EntityRef::Unit(unit) = source {
        let unit = battle.unit(unit);
        if unit.name == "Firemite" && effect == "secondary"
            || unit.name == "Electro Dragon" && effect == "chain"
            || unit.spec.attack == "suicide" || matches!(unit.name.as_str(), "Yetimite" | "Electromite") {
            return;
        }
    }
    let (x, y) = battle.entity_position(source);
    let unit = battle.unit(hero);
    if dist(x, y, unit.x, unit.y) > 25.0 {
        return;
    }
    let due = unit.extra.revenge_cd.iter().find(|(key, _)| *key == source).map_or(-1.0, |(_, at)| *at);
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
    let damage = col(battle, "Revenge Deck", kit.lv("Revenge Deck"), &["counter damage"], 225.0);
    let heal = col(battle, "Revenge Deck", kit.lv("Revenge Deck"), &["heal per counter"], 0.0);
    battle.unit_mut(hero).heal(heal);
    effects::damage_source(battle, Some(EntityRef::Unit(hero)), "counter", |battle| {
        damage_target(battle, source, damage);
    });
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

// heroes.py:443-471: these items are outside the requested loadouts.
pub fn on_hit_extra(battle: &mut Battle, hero: UnitRef, _target: EntityRef) {
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.has("Electro Fangs") || kit.frozen_arrow.is_some() {
        todo!("stage 3+: Electro Fangs/Frozen Arrow on-hit effects");
    }
}

// heroes.py:474-504: owner loss precedes dash completion and the defeat blast.
pub fn on_death(battle: &mut Battle, hero: UnitRef) -> bool {
    if let Some(pet) = battle.unit(hero).pet {
        pets::owner_defeated(battle, pet);
        let t = battle.t;
        let pet = battle.unit_mut(pet);
        pet.extra.rampage_detached = true;
        if pet.name == "Angry Jelly" {
            pet.extra.brainwash_until = t;
        }
    }
    if battle.unit(hero).dash.is_some() {
        end_dash(battle, hero);
    }
    let unit = battle.unit(hero);
    let kit = unit.kit.as_ref().expect("hero kit");
    if kit.has("Fire Heart") && !unit.extra.fire_heart_done {
        let damage = col(battle, "Fire Heart", kit.lv("Fire Heart"), &["damage on defeat"], 0.0);
        let (x, y) = (unit.x, unit.y);
        battle.unit_mut(hero).extra.fire_heart_done = true;
        battle.splash_buildings(x, y, 4.0, damage, SplashBuildingsOptions {
            walls: false,
            ..Default::default()
        });
    }
    let kit = battle.unit(hero).kit.as_ref().expect("hero kit");
    if kit.phoenix && kit.pet_unit.is_some_and(|pet| battle.unit(pet).alive) {
        let egg = kit.pet_unit.expect("Phoenix egg");
        let duration = battle.catalog.stats.get("Phoenix", kit.pet_level.as_ref().expect("pet level"),
            &["Revive Duration"], Some(8.5)).expect("Phoenix revive duration");
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
        return true;
    }
    false
}

// heroes.py:508-803: stable equipment priority, under ability provenance.
pub fn activate(battle: &mut Battle, hero: UnitRef) {
    effects::damage_source(battle, Some(EntityRef::Unit(hero)), "ability", |battle| {
        activate_effect(battle, hero);
    });
}

fn activate_effect(battle: &mut Battle, hero: UnitRef) {
    let unit = battle.unit(hero);
    if unit.kit.is_none() || unit.ability_used || !unit.alive {
        return;
    }
    let recovery = unit.kit.as_ref().expect("hero kit").hp_recovery;
    let unit = battle.unit_mut(hero);
    unit.ability_used = true;
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
    let mut equipment = battle.unit(hero).kit.as_ref().expect("hero kit").equip.clone();
    equipment.sort_by_key(|name| match name.as_str() {
        "Fireball" => 0,
        "Rocket Backpack" => 1,
        "Lavaloon Puppet" => 3,
        _ => 2,
    });
    for name in equipment {
        let level = battle.unit(hero).kit.as_ref().expect("hero kit").lv(&name).clone();
        match name.as_str() {
            "Giant Arrow" => {
                let damage = col(battle, &name, &level, &["projectile damage"], 0.0);
                line(battle, hero, target, 75.0, 1.0, damage);
            }
            "Action Figure" => {
                let level = col(battle, &name, &level, &["giant giant level"], 10.0) as i64;
                let unit = battle.unit(hero);
                battle.spawn("Giant Giant", Team::Atk, unit.x + 0.5, unit.y + 0.5, SpawnOptions {
                    level: Some(Level::Int(level)),
                    kind: "summon".to_owned(),
                    group: unit.group.clone(),
                    ..Default::default()
                });
                invisible(battle.unit_mut(hero), t + 1.0);
            }
            "Eternal Tome" => {
                let duration = col(battle, &name, &level, &["ability duration"], 8.0);
                battle.unit_mut(hero).extra.tome_until = t + duration;
                moving_auras(battle, hero, None);
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
                let mut pending = Pending::new(t + 1.5, x, y,
                    col(battle, &name, &level, &["damage radius"], 0.0),
                    col(battle, &name, &level, &["projectile damage"], 0.0), true, true, &unit.name);
                pending.extra.hero_impact = Some("blast".to_owned());
                battle.add_pending(pending);
            }
            "Rocket Spear" => {
                let shots = col(battle, &name, &level, &["number of attacks"], 9.0) as i64;
                let bonus = col(battle, &name, &level, &["damage per shot increase"], 0.0);
                let unit = battle.unit_mut(hero);
                let kit = unit.kit.as_mut().expect("hero kit");
                kit.spear_shots = shots;
                kit.spear_bonus = bonus;
                if unit.extra.spear_base_range.is_none() {
                    unit.extra.spear_base_range = Some(unit.range);
                }
                unit.range = 10.0;
            }
            "Rocket Backpack" => {
                let damage = col(battle, &name, &level, &["ability damage"], 0.0);
                start_dash(battle, hero, damage);
            }
            // These pieces have passive effects only in Python's activate.
            "Electro Boots" | "Revenge Deck" | "Fire Heart" | "Rage Gem" => {}
            _ => todo!("stage 3+: activate {name}"),
        }
    }
    let name = battle.unit(hero).name.clone();
    battle.log_event(vec![round_decimal(t, 1).into(), "ability".into(), name.into()]);
}

// heroes.py:806-870: stage-3 loadouts launch Fireball's blast only.
pub fn projectile_impact(battle: &mut Battle, pending: Pending) {
    match pending.extra.hero_impact.as_deref().expect("hero impact mode") {
        "blast" => blast(battle, pending.x, pending.y, pending.radius, pending.damage, None, 1.0),
        mode => todo!("stage 3+: hero projectile {mode}"),
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
    let targets: Vec<_> = battle.buildings.iter().map(|b| EntityRef::Building(b.id))
        .chain(battle.walls.iter().map(|w| EntityRef::Wall(w.id)))
        .chain(battle.defenders_pool().map(|u| EntityRef::Unit(u.reference()))).collect();
    for target in targets {
        if !battle.entity_alive(target) {
            continue;
        }
        let (half, multiplier) = match target {
            EntityRef::Building(id) => {
                let building = battle.building(id);
                if !building.counted {
                    continue;
                }
                (building.half_hit, if building.key == "ad" { 2.0 } else { 1.0 })
            }
            EntityRef::Wall(id) => (battle.walls[id.0].half_hit, 1.0),
            EntityRef::Unit(id) => {
                if battle.unit(id).underground {
                    continue;
                }
                (0.0, 1.0)
            }
            EntityRef::Trap(_) => unreachable!(),
        };
        let (tx, ty) = battle.entity_position(target);
        let (px, py) = (tx - x, ty - y);
        let along = (px * dx + py * dy) / magnitude;
        if 0.0 < along && along < length && (px * dy - py * dx).abs() / magnitude <= half + width {
            damage_target(battle, target, damage * multiplier);
        }
    }
}

// heroes.py:947-977: suspend the pet without changing its identity.
pub fn start_dash(battle: &mut Battle, hero: UnitRef, damage: f64) {
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
        if building.alive && !dash.hit.contains(&target) && building.edge_distance(unit.x, unit.y) <= 1.5 {
            let damage = dash.damage;
            battle.unit_mut(hero).dash.as_mut().expect("active dash").hit.push(target);
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
            battle.unit_mut(hero).dash.as_mut().expect("active dash").hit.push(target);
            battle.hit_unit(defender, damage, None, "normal", Some(EntityRef::Unit(hero)));
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

fn targets(battle: &Battle, defenses: bool) -> Vec<EntityRef> {
    let mut result: Vec<_> = battle.buildings.iter().filter(|building| {
        battle.building_targetable(building.id) && (!defenses || battle.is_defense_target(building.id))
    }).map(|building| EntityRef::Building(building.id)).collect();
    if !defenses {
        result.extend(battle.defenders_pool().filter(|u| u.targetable(battle))
            .map(|u| EntityRef::Unit(u.reference())));
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
) {
    let targets: Vec<_> = battle.buildings.iter().map(|b| EntityRef::Building(b.id))
        .chain(battle.defenders_pool().map(|u| EntityRef::Unit(u.reference()))).collect();
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
            damage_target(battle, target, if hero { damage * hero_mult } else { damage });
        }
    }
}

// heroes.py:1056-1078: one second of persistence, capped by the ability expiry.
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
    let source = StatusSource::Name(unit.id.0.to_string());
    let members = members.map_or_else(|| battle.attackers_near(unit.x, unit.y, 9.0), |members| members.to_vec());
    for ally in members {
        let unit = battle.unit_mut(ally);
        if unit.name == "Totem" {
            continue;
        }
        if t < tome {
            if let Some((_, until)) = unit.extra.tomes.iter_mut().find(|(key, _)| *key == source) {
                *until = tome.min(t + 1.0);
            } else {
                unit.extra.tomes.push((source.clone(), tome.min(t + 1.0)));
            }
        }
        if t < torch && !matches!(unit.kind.as_str(), "siege" | "siege_idle") {
            let speed = if unit.is_hero && ally != warden {
                speed / 2.0
            } else {
                speed
            };
            let value = (torch.min(t + 1.0), speed, reduction);
            if let Some((_, old)) = unit.extra.torches.iter_mut().find(|(key, _)| *key == source) {
                *old = value;
            } else {
                unit.extra.torches.push((source.clone(), value));
            }
        }
    }
}

// heroes.py:1082-1140: all combatants reset before any strongest-buff selection.
pub fn apply_auras(battle: &mut Battle) {
    let combatants: Vec<_> = battle.attackers_pool().chain(battle.defenders_pool())
        .map(Unit::reference).collect();
    let mut want = Vec::new();
    for &reference in &combatants {
        let unit = battle.unit_mut(reference);
        let boost = effects::crown_buff(unit);
        unit.aura_dmg = 1.0 + boost;
        if boost != 0.0 {
            want.push((reference, (boost, f64::INFINITY)));
        }
    }
    let wardens: Vec<_> = combatants.iter().copied().filter(|reference| {
        let unit = battle.unit(*reference);
        unit.alive && matches!(unit.name.as_str(), "Grand Warden" | "Apprentice Warden")
    }).collect();
    for reference in wardens {
        let unit = battle.unit(reference);
        let (percentage, cap, rage, radius) = if unit.name == "Apprentice Warden" {
            (battle.catalog.stats.get("Apprentice Warden", unit.level.as_ref().expect("Warden level"),
                &["Aura HP Increase"], None).expect("aura HP increase") / 100.0, f64::INFINITY, 0.0, 7.0)
        } else {
            moving_auras(battle, reference, None);
            let kit = battle.unit(reference).kit.as_ref();
            let (mut percentage, mut cap, mut rage) = (0.0, 0.0, 0.0);
            if let Some(kit) = kit {
                if kit.has("Life Gem") {
                    percentage = col(battle, "Life Gem", kit.lv("Life Gem"), &["% hp increase"], 0.0) / 100.0;
                    cap = col(battle, "Life Gem", kit.lv("Life Gem"), &["max hp increase"], 0.0);
                }
                if kit.has("Rage Gem") {
                    rage = col(battle, "Rage Gem", kit.lv("Rage Gem"), &["% damage increase"], 0.0) / 100.0;
                }
            }
            (percentage, cap, rage, 9.0)
        };
        let unit = battle.unit(reference);
        let (x, y) = (unit.x, unit.y);
        let allies: Vec<_> = if reference.team == Team::Atk {
            battle.attackers_pool().map(Unit::reference).collect()
        } else {
            battle.defenders_pool().map(Unit::reference).collect()
        };
        for ally in allies {
            let unit = battle.unit(ally);
            if !unit.alive || dist(unit.x, unit.y, x, y) > radius || ally == reference
                || unit.name == "Totem" || matches!(unit.kind.as_str(), "siege" | "siege_idle") {
                continue;
            }
            if percentage != 0.0 {
                if let Some((_, (previous_pct, previous_cap))) = want.iter_mut().find(|(unit, _)| *unit == ally) {
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
            unit.aura_dmg = unit.aura_dmg.max(1.0 + increase);
        }
    }
    for reference in combatants {
        if battle.unit(reference).alive {
            let (percentage, cap) = want.iter().find(|(unit, _)| *unit == reference)
                .map_or((0.0, 0.0), |(_, value)| *value);
            effects::health_aura(battle.unit_mut(reference), percentage, cap);
        }
    }
}

// heroes.py:1185-1200: Town Hall 18 guardians are outside stage 3's scenarios.
pub fn guardians_tick(battle: &mut Battle) {
    if battle.guardian.is_some_and(|g| battle.unit(g).alive) {
        todo!("stage 3+: heroes.py:1189 Guardian activation and enrage");
    }
}

// heroes.py:1348-1350: defenders have no abilities or equipment in Python.
pub fn defending_hero_ability(_battle: &mut Battle, _unit: UnitRef) {}

// heroes.py:1357-1387.
pub fn summon_tick(battle: &mut Battle, unit: UnitRef) -> bool {
    if battle.unit(unit).name != "Lavaloon" {
        return false;
    }
    if !battle.unit(unit).can_act(battle.t) {
        return true;
    }
    let target = battle.unit(unit).target;
    let valid = matches!(target, Some(EntityRef::Building(id)) if battle.building_targetable(id));
    if !valid {
        let (target, kind) = battle.choose_target(unit);
        let unit = battle.unit_mut(unit);
        unit.target = target;
        unit.target_kind = kind;
    }
    let u = battle.unit(unit);
    let due = u.extra.bomb_next.unwrap_or(u.spawned_at + u.interval);
    if battle.t >= due {
        let (x, y, damage) = (u.x, u.y, u.dmg);
        units::area_hit(battle, unit, x, y, 1.8, damage, true, None);
        let u = battle.unit(unit);
        battle.spawn("Lavaloon Pup", unit.team, u.x, u.y, SpawnOptions {
            level: u.level.clone(),
            kind: "summon".to_owned(),
            owner: Some(unit),
            group: u.group.clone(),
            ..Default::default()
        });
        let next = battle.t + battle.unit(unit).interval;
        battle.unit_mut(unit).extra.bomb_next = Some(next);
    }
    let u = battle.unit(unit);
    if let Some(target) = u.target {
        if distance(battle, target, u.x, u.y) > u.range {
            battle.move_towards(unit, target, None);
        }
    }
    true
}

// heroes.py:1390-1425: children precede the delayed death bomb.
pub fn summon_death(battle: &mut Battle, unit: UnitRef) {
    let u = battle.unit(unit);
    if u.name != "Lavaloon" {
        return;
    }
    let count = battle.catalog.stats.get("Lavaloon", u.level.as_ref().expect("Lavaloon level"),
        &["Lavaloon Pups Spawned (After Death)"], None).expect("Lavaloon death count") as usize;
    for _ in 0..count {
        let u = battle.unit(unit);
        battle.spawn("Lavaloon Pup", unit.team, u.x, u.y, SpawnOptions {
            level: u.level.clone(),
            kind: "summon".to_owned(),
            owner: Some(unit),
            group: u.group.clone(),
            ..Default::default()
        });
    }
    let u = battle.unit(unit);
    let damage = battle.catalog.stats.get("Lavaloon", u.level.as_ref().expect("Lavaloon level"),
        &["Damage when Destroyed"], None).expect("Lavaloon death damage");
    let mut pending = Pending::new(battle.t + 0.416, u.x, u.y, 2.0, damage, false, true, &u.name);
    pending.team = if unit.team == Team::Atk { Team::Def } else { Team::Atk };
    pending.extra.buildings = if unit.team == Team::Atk { damage } else { 0.0 };
    pending.actor = Some(EntityRef::Unit(unit));
    pending.effect = Some("death".to_owned());
    battle.add_pending(pending);
}

// heroes.py:1428-1432.
fn invisible(unit: &mut Unit, until: f64) {
    unit.invisible_until = unit.invisible_until.max(until);
    unit.extra.equipment_invisible_until = unit.extra.equipment_invisible_until.max(until);
}

// heroes.py:1435-1449: also preprocessed in the exported catalog.
pub fn summon_spec(name: &str, mut specification: UnitSpec) -> UnitSpec {
    match name {
        "Henchman" | "Booger" => specification.walls = "fly".to_owned(),
        "Lavaloon" => specification.prefer = "air_defense".to_owned(),
        "Frostmite" => {
            specification.prefer = "defense".to_owned();
            specification.walls = "ignore".to_owned();
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
            battle.buckets.push((cell, Vec::new()));
            battle.bucket_indices.insert(cell, index);
            index
        };
        if !battle.buckets[index].1.contains(&reference) {
            battle.buckets[index].1.push(reference);
        }
    }
    let unit = battle.unit(reference);
    let wardens: Vec<_> = battle.attackers_pool().filter(|warden| {
        warden.alive && warden.name == "Grand Warden" && dist(warden.x, warden.y, unit.x, unit.y) <= 9.0
    }).map(Unit::reference).collect();
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
