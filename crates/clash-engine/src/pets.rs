//! Ports pets.py:9-454 for every attacking pet.

use crate::battle::SpawnOptions;
use crate::geom::{dist, py_pow};
use crate::labels::{Name, Tag};
use crate::state::{Battle, EntityRef, Pending, UnitRef};
use crate::stats::{self, Level};
use crate::{effects, heroes, spells, units};

// pets.py:9-22: stable first minimum, with ordinary center distance.
fn valid(battle: &Battle, pet: UnitRef, target: Option<EntityRef>) -> bool {
    match target {
        Some(EntityRef::Unit(unit)) => {
            battle.unit(unit).targetable(battle) && battle.can_hit(pet, unit)
        }
        Some(EntityRef::Wall(wall)) => battle.walls[wall.0].alive && battle.unit(pet).hits_ground,
        Some(EntityRef::Building(building)) => battle.building_targetable(building),
        _ => false,
    }
}

fn nearest(
    battle: &Battle,
    origin: EntityRef,
    candidates: impl IntoIterator<Item = EntityRef>,
) -> Option<EntityRef> {
    let (x, y) = battle.entity_position(origin);
    let (mut best, mut closest) = (None, f64::INFINITY);
    for candidate in candidates {
        let (tx, ty) = battle.entity_position(candidate);
        let distance = dist(x, y, tx, ty);
        if best.is_none() || distance < closest {
            best = Some(candidate);
            closest = distance;
        }
    }
    best
}

// pets.py:25-48: Diggy can find a new Hero after defeat clears its owner.
fn hero(battle: &mut Battle, pet: UnitRef) -> Option<UnitRef> {
    let unit = battle.unit(pet);
    let previous = unit.extra.diggy_hero.or(unit.owner);
    if unit.name_id == Name::Diggy
        && previous.is_none_or(|hero| {
            let hero = battle.unit(hero);
            !hero.alive && hero.extra.recalled.is_none()
        })
    {
        // pets.py:25-48: nearest active Hero, retaining first ties in attacker order.
        let candidates = battle
            .attackers_pool()
            .filter(|ally| {
                Some(ally.reference()) != previous
                    && ally.kind == Tag::Hero
                    && ally.alive
                    && ally.extra.recalled.is_none()
                    && !ally.extra.suspended
                    && battle.t >= ally.active_at
            })
            .map(|ally| EntityRef::Unit(ally.reference()));
        let replacement = nearest(battle, EntityRef::Unit(pet), candidates);
        if let Some(EntityRef::Unit(hero)) = replacement {
            battle.unit_mut(pet).extra.diggy_hero = Some(hero);
            return Some(hero);
        }
        return None;
    }
    previous
}

// pets.py:52-71.
fn independent(
    battle: &mut Battle,
    pet: UnitRef,
    buildings: &[EntityRef],
    defenders: &[EntityRef],
) -> Option<EntityRef> {
    let unit = battle.unit(pet);
    let target = unit.target;
    if battle.t < unit.aware_until || battle.ally_under_attack(pet) {
        let nearby = defenders.iter().copied().filter(|target| {
            let (x, y) = battle.entity_position(*target);
            dist(unit.x, unit.y, x, y) <= 7.0
        });
        if let Some(target) = nearest(battle, EntityRef::Unit(pet), nearby) {
            return Some(target);
        }
    }
    let wall = battle.unit(pet).wall_target.map(EntityRef::Wall);
    if valid(battle, pet, wall) {
        return wall;
    }
    if target.is_some_and(|target| buildings.contains(&target) || defenders.contains(&target)) {
        return target;
    }
    let (target, _) = battle.choose_target(pet);
    target.filter(|target| valid(battle, pet, Some(*target)))
}

// pets.py:74-144: owner-target and radius preferences use raw registry text.
fn target(battle: &mut Battle, pet: UnitRef) -> Option<EntityRef> {
    let hero = hero(battle, pet);
    let owner_present = hero.is_some_and(|hero| battle.unit(hero).alive);
    let mut buildings = std::mem::take(&mut battle.pet_buildings_scratch);
    let mut defenders = std::mem::take(&mut battle.pet_defenders_scratch);
    buildings.clear();
    defenders.clear();
    buildings.extend(
        battle
            .buildings
            .iter()
            .map(|b| EntityRef::Building(b.id))
            .filter(|target| valid(battle, pet, Some(*target))),
    );
    defenders.extend(
        battle
            .defenders_pool()
            .map(|u| EntityRef::Unit(u.reference()))
            .filter(|target| valid(battle, pet, Some(*target))),
    );
    let result = target_from_pools(battle, pet, hero, owner_present, &buildings, &defenders);
    buildings.clear();
    defenders.clear();
    battle.pet_buildings_scratch = buildings;
    battle.pet_defenders_scratch = defenders;
    result
}

fn target_from_pools(
    battle: &mut Battle,
    pet: UnitRef,
    hero: Option<UnitRef>,
    owner_present: bool,
    buildings: &[EntityRef],
    defenders: &[EntityRef],
) -> Option<EntityRef> {
    let unit = battle.unit(pet);
    // pets.py:79-90: only targetable resources suppress the ordinary fallback.
    if unit.name == "Greedy Raven" {
        let resources: Vec<_> = buildings
            .iter()
            .copied()
            .filter(|target| {
                let EntityRef::Building(id) = target else {
                    return false;
                };
                let building = battle.building(*id);
                building.kind == Tag::Resource
                    || units::RESOURCE_KEYS.contains(&building.key.as_str())
            })
            .collect();
        if !resources.is_empty() {
            let origin = if owner_present {
                hero.expect("present owner")
            } else {
                pet
            };
            return nearest(battle, EntityRef::Unit(origin), resources);
        }
    }
    if unit.attached(battle) {
        let candidates = buildings.iter().copied().filter(|target| match target {
            EntityRef::Building(id) => {
                battle.is_defense_target(*id)
                    && battle.building(*id).edge_distance(unit.x, unit.y) <= unit.range
            }
            _ => false,
        });
        return nearest(battle, EntityRef::Unit(pet), candidates);
    }
    if unit.name_id == Name::AngryJelly && owner_present {
        let owner = battle.unit(hero.expect("present owner"));
        if let Some(EntityRef::Building(source)) = owner.extra.last_damage_source {
            let target = EntityRef::Building(source);
            if valid(battle, pet, Some(target))
                && battle.building(source).edge_distance(unit.x, unit.y) <= unit.range
            {
                return Some(target);
            }
        }
    }
    if unit.name_id == Name::PoisonLizard {
        let nearby = defenders.iter().copied().filter(|target| {
            if !owner_present {
                return true;
            }
            let hero = battle.unit(hero.expect("present owner"));
            let (x, y) = battle.entity_position(*target);
            dist(x, y, hero.x, hero.y) <= 6.5
        });
        if let Some(target) = nearest(battle, EntityRef::Unit(pet), nearby) {
            return Some(target);
        }
    }
    // pets.py:113-116: Sneezy chooses defenses independently of the Hero.
    if unit.name_id == Name::Sneezy {
        let defenses: Vec<_> = buildings
            .iter()
            .copied()
            .filter(
                |target| matches!(target, EntityRef::Building(id) if battle.is_defense_target(*id)),
            )
            .collect();
        let candidates = if defenses.is_empty() {
            buildings
        } else {
            &defenses
        };
        return nearest(battle, EntityRef::Unit(pet), candidates.iter().copied());
    }
    if owner_present {
        // pets.py:120-127: a new Hero target restarts Yak's wall selection.
        if battle.unit(pet).name_id == Name::MightyYak {
            let owner = battle.unit(hero.expect("present owner"));
            let hero_target = owner.target;
            if hero_target != battle.unit(pet).extra.hero_target {
                let unit = battle.unit_mut(pet);
                unit.wall_target = None;
                unit.extra.hero_target = hero_target;
            }
            let wall = battle
                .unit(hero.expect("present owner"))
                .wall_target
                .map(EntityRef::Wall);
            if valid(battle, pet, wall) {
                return wall;
            }
            let wall = battle.unit(pet).wall_target.map(EntityRef::Wall);
            if valid(battle, pet, wall) {
                return wall;
            }
        }
        let unit = battle.unit(pet);
        let hero = battle.unit(hero.expect("present owner"));
        let preference = battle
            .catalog
            .stats
            .attrs(&unit.name)
            .get("preferred_target")
            .map_or("", |value| value.str());
        if preference.starts_with("Within ") {
            let radius = stats::num(&crate::json::Json::Str(preference.to_owned()), None)
                .expect("pet preference radius");
            let candidates = buildings.iter().chain(defenders).copied().filter(|target| {
                let (x, y) = battle.entity_position(*target);
                dist(x, y, hero.x, hero.y) <= radius
            });
            return nearest(battle, EntityRef::Unit(pet), candidates);
        }
        let wall = hero.wall_target.map(EntityRef::Wall);
        if valid(battle, pet, wall) {
            return wall;
        }
        if unit.name_id == Name::Diggy
            && matches!(
                hero.target,
                Some(EntityRef::Unit(target)) if battle.unit(target).flying
            )
        {
            return nearest(battle, EntityRef::Unit(pet), buildings.iter().copied());
        }
        if valid(battle, pet, hero.target) {
            return hero.target;
        }
        return None;
    }
    independent(battle, pet, buildings, defenders)
}

// pets.py:147-163: owner loss clears old walls even for passive pets.
pub fn owner_defeated(battle: &mut Battle, pet: UnitRef) {
    let unit = battle.unit(pet);
    if !unit.alive || unit.extra.owner_defeated {
        return;
    }
    battle.unit_mut(pet).extra.owner_defeated = true;
    let unit = battle.unit(pet);
    if matches!(unit.name_id, Name::MightyYak | Name::Sneezy) {
        // pets.py:147-163: independent damage and additive movement Rage.
        let name = unit.name.clone();
        let raw = battle.catalog.stats.attrs(&name).at("raw");
        let damage = 1.0
            + stats::num(raw.at("Rage Damage Increase"), None).expect("pet Rage damage") / 100.0;
        let speed = raw
            .get("Rage Speed Increase")
            .and_then(|value| stats::num(value, Some(0.0)))
            .unwrap_or(0.0)
            / 8.0;
        let until =
            battle.t + stats::num(raw.at("Rage Duration"), None).expect("pet Rage duration");
        units::add_rage(
            battle.unit_mut(pet),
            crate::state::StatusSource::Name(name),
            damage,
            speed,
            until,
        );
    }
    let unit = battle.unit_mut(pet);
    if unit.name_id == Name::Sneezy {
        unit.range = 2.5;
    }
    unit.target = None;
    unit.wall_target = None;
}

// pets.py:166-216: Frosty's children spawn at the pet, in count order.
fn summon(battle: &mut Battle, pet: UnitRef) -> bool {
    let unit = battle.unit(pet);
    if !matches!(unit.name_id, Name::Frosty | Name::Sneezy) {
        return false;
    }
    let summon_at = unit.extra.summon_at;
    if summon_at.is_some_and(|at| battle.t < at) {
        return true;
    }
    if summon_at.is_none() && battle.t < unit.extra.next_summon {
        return battle.t < unit.extra.summon_until;
    }
    let mut alive: Vec<_> = unit
        .extra
        .children
        .iter()
        .copied()
        .filter(|child| battle.unit(*child).alive)
        .collect();
    let (name, level, count, cap, cooldown) = if unit.name_id == Name::Sneezy {
        (
            "Booger",
            unit.level.clone().expect("Sneezy level"),
            1,
            2,
            10.0,
        )
    } else {
        let level = unit.level.as_ref().expect("Frosty level");
        let count = battle
            .catalog
            .stats
            .get("Frosty", level, &["Frostmites per Summon"], None)
            .expect("Frostmite count") as i64;
        let cap = battle
            .catalog
            .stats
            .get("Frosty", level, &["Maximum Frostmites Summoned"], None)
            .expect("Frostmite cap") as i64;
        let cooldown = stats::num(
            battle
                .catalog
                .stats
                .attrs("Frosty")
                .at("raw")
                .at("Summon Cooldown"),
            None,
        )
        .expect("Frostmite cooldown");
        ("Frostmite", Level::Int(1), count, cap, cooldown)
    };
    if name == "Booger" && summon_at.is_none() {
        let next = battle.t + cooldown;
        let at = battle.t + 1.0;
        let until = battle.t + 1.5;
        let unit = battle.unit_mut(pet);
        unit.extra.next_summon = next;
        if alive.len() as i64 >= cap {
            return true;
        }
        unit.extra.summon_at = Some(at);
        unit.extra.summon_until = until;
        return true;
    }
    for _ in 0..count.min(0.max(cap - alive.len() as i64)) {
        let unit = battle.unit(pet);
        let child = battle.spawn(
            name,
            pet.team,
            unit.x,
            unit.y,
            SpawnOptions {
                level: Some(level.clone()),
                kind: Tag::Summon,
                owner: Some(pet),
                group: unit.group.clone(),
                ..Default::default()
            },
        );
        if name == "Booger" {
            battle.unit_mut(child).flying = true;
        }
        alive.push(child);
    }
    let t = battle.t;
    let next = t + cooldown;
    let unit = battle.unit_mut(pet);
    unit.extra.children = alive;
    if name == "Booger" {
        unit.extra.summon_at = None;
        return t < unit.extra.summon_until;
    }
    unit.extra.next_summon = next;
    false
}

// pets.py:219-227.
fn move_pet(battle: &mut Battle, pet: UnitRef, target: EntityRef) {
    if battle.t < battle.unit(pet).held_until {
        return;
    }
    let unit = battle.unit(pet);
    let previous = (unit.x, unit.y);
    battle.move_towards(pet, target, None);
    let unit = battle.unit_mut(pet);
    if unit.name_id == Name::MightyYak && (unit.x, unit.y) != previous {
        unit.extra.yak_first = true;
        unit.cooldown = 0.0;
    }
}

// pets.py:230-374: passives run here as well as before the can-act check.
pub fn act(battle: &mut Battle, pet: UnitRef) {
    let owner = hero(battle, pet);
    let present = owner.is_some_and(|hero| battle.unit(hero).alive);
    let unit = battle.unit_mut(pet);
    if unit.extra.hero_present && !present {
        unit.target = None;
        unit.wall_target = None;
    }
    unit.extra.hero_present = present;
    let t = battle.t;
    passives(battle, pet);
    if battle.unit(pet).extra.egg {
        if present {
            let owner = owner.expect("present owner");
            let speed = battle.speed_of(pet).max(battle.speed_of(owner));
            let hero = battle.unit(owner);
            battle.move_straight(pet, hero.x, hero.y, speed * battle.dt);
        }
        return;
    }
    if battle.unit(pet).name_id == Name::Unicorn {
        battle.unit_mut(pet).extra.healing_targets.clear();
        let target = if present {
            owner.map(EntityRef::Unit)
        } else {
            nearest(
                battle,
                EntityRef::Unit(pet),
                battle
                    .attackers_pool()
                    .filter(|ally| {
                        ally.alive
                            && ally.reference() != pet
                            && ally.team == pet.team
                            && t >= ally.active_at
                            && !ally.extra.suspended
                            && !matches!(ally.name_id, Name::Totem | Name::Furnace)
                            && ally.hp < ally.max_hp
                            && !matches!(ally.kind, Tag::Siege | Tag::SiegeIdle)
                            && !matches!(ally.spec.attack, Tag::Heal | Tag::HealChain)
                    })
                    .map(|ally| EntityRef::Unit(ally.reference())),
            )
        };
        battle.unit_mut(pet).target = target;
        if let Some(EntityRef::Unit(target)) = target {
            let unit = battle.unit(pet);
            let recipient = battle.unit(target);
            if dist(unit.x, unit.y, recipient.x, recipient.y) <= unit.range {
                battle.unit_mut(pet).extra.healing_targets = vec![target];
                let due = battle.unit(pet).extra.heal_next.unwrap_or(t);
                if t >= due || units::isclose(t, due) {
                    let effectiveness = units::heal_effectiveness(battle, pet, target);
                    let unit = battle.unit(pet);
                    let amount = battle
                        .catalog
                        .stats
                        .get(
                            "Unicorn",
                            unit.level.as_ref().expect("Unicorn level"),
                            &["Healing per Pulse"],
                            None,
                        )
                        .expect("Unicorn healing")
                        * effectiveness;
                    // pets.py:272-295: Unicorn healing travels without a start offset.
                    let recipient = battle.unit(target);
                    let row = battle
                        .catalog
                        .game_data("projectiles", "UnicornHealEnergy", None);
                    let speed = crate::catalog::game_int(row, "Speed", 0) as f64 / 100.0;
                    let mut pending = Pending::new(
                        t + dist(unit.x, unit.y, recipient.x, recipient.y) / speed,
                        recipient.x,
                        recipient.y,
                        0.0,
                        0.0,
                        false,
                        false,
                        unit.source.clone(),
                    );
                    pending.team = pet.team;
                    pending.extra.healing = Some(amount);
                    pending.actor = Some(EntityRef::Unit(pet));
                    pending.effect = Some(Tag::Heal);
                    pending.target = Some(EntityRef::Unit(target));
                    battle.add_pending(pending);
                    let interval = stats::num(
                        battle
                            .catalog
                            .stats
                            .attrs("Unicorn")
                            .at("raw")
                            .at("Healing Speed"),
                        None,
                    )
                    .expect("Unicorn healing speed");
                    battle.unit_mut(pet).extra.heal_next = Some(t + interval);
                }
            } else {
                move_pet(battle, pet, EntityRef::Unit(target));
            }
        }
        return;
    }
    if summon(battle, pet) {
        return;
    }
    // pets.py:302-305: Sneezy only summons and follows until owner defeat.
    let unit = battle.unit(pet);
    if unit.name_id == Name::Sneezy && !unit.extra.owner_defeated {
        if present {
            let owner = owner.expect("present owner");
            let hero = battle.unit(owner);
            if dist(unit.x, unit.y, hero.x, hero.y) > unit.range {
                move_pet(battle, pet, EntityRef::Unit(owner));
            }
        }
        return;
    }
    let target = target(battle, pet);
    battle.unit_mut(pet).target = target;
    let Some(target) = target else {
        if battle.unit(pet).name_id == Name::Diggy {
            battle.unit_mut(pet).underground = true;
        }
        if present && !battle.unit(pet).attached(battle) {
            move_pet(battle, pet, EntityRef::Unit(owner.expect("present owner")));
        }
        return;
    };
    let unit = battle.unit(pet);
    if heroes::distance(battle, target, unit.x, unit.y) > unit.range {
        let attached = unit.attached(battle);
        if unit.name_id == Name::Diggy {
            battle.unit_mut(pet).underground = true;
        }
        if !attached {
            move_pet(battle, pet, target);
        }
        return;
    }
    // output/research/usage/diggy.md:27; stun includes attackable defenders.
    // https://supercell.com/en/games/clashofclans/blog/release-notes/get-ready-for-ranked-update/
    let unit = battle.unit(pet);
    if unit.name_id == Name::Diggy && unit.underground {
        battle.unit_mut(pet).underground = false;
        let level = battle.unit(pet).level.as_ref().expect("Diggy level");
        let duration = battle
            .catalog
            .stats
            .get("Diggy", level, &["Stun Duration"], None)
            .expect("Diggy stun");
        match target {
            EntityRef::Unit(victim) => {
                let victim = battle.unit_mut(victim);
                victim.stun_until = victim.stun_until.max(t + duration);
            }
            EntityRef::Building(building) if battle.is_defense_target(building) => {
                let building = battle.building_mut(building);
                building.stun_until = building.stun_until.max(t + duration);
            }
            _ => {}
        }
    }
    // pets.py:331-336: first ram after moving has a half-second windup.
    let unit = battle.unit(pet);
    if unit.name_id == Name::MightyYak && unit.extra.yak_first {
        let cooldown = 0.5 / 0.05_f64.max(effects::slow_mult(unit, t, false));
        let unit = battle.unit_mut(pet);
        unit.extra.yak_first = false;
        unit.extra.yak_second = true;
        unit.cooldown = cooldown;
    }
    let unit = battle.unit(pet);
    if unit.cooldown > 0.0 && !units::isclose(t + unit.cooldown, t) {
        return;
    }
    let pending_start = battle.pending.len();
    effects::damage_source(battle, Some(EntityRef::Unit(pet)), Tag::Attack, |battle| {
        units::strike(battle, pet, target);
    });
    let unit = battle.unit(pet);
    let yak = unit.name_id == Name::MightyYak;
    let interval = if yak && unit.extra.yak_second {
        1.6
    } else {
        unit.interval
    };
    let delay = interval / 0.05_f64.max(effects::slow_mult(unit, t, false));
    let unit = battle.unit_mut(pet);
    if yak {
        unit.extra.yak_second = false;
        unit.cooldown = delay;
    } else {
        unit.cooldown += delay;
    }
    if battle.unit(pet).name_id == Name::PoisonLizard && matches!(target, EntityRef::Unit(_)) {
        // pets.py:350-360: attach poison to the newly released single shot.
        for pending in &mut battle.pending[pending_start..] {
            if pending.actor == Some(EntityRef::Unit(pet))
                && pending.target == Some(target)
                && pending.extra.troop_impact.as_deref() == Some("single")
            {
                pending.extra.hero_impact = Some("lizard".to_owned());
            }
        }
    }
    if battle.unit(pet).name_id == Name::ElectroOwl {
        let candidates = battle
            .buildings
            .iter()
            .map(|b| EntityRef::Building(b.id))
            .chain(
                battle
                    .defenders_pool()
                    .map(|u| EntityRef::Unit(u.reference())),
            )
            .filter(|candidate| {
                *candidate != target
                    && valid(battle, pet, Some(*candidate))
                    && owl_link(battle, target, *candidate)
            });
        if let Some(second) = nearest(battle, target, candidates) {
            let unit = battle.unit(pet);
            let boost = units::rage_boost(unit, t)
                .0
                .max(unit.aura_dmg)
                .max(unit.extra.bell_damage);
            let damage = unit.dmg * boost * 0.8;
            let (x, y) = battle.entity_position(second);
            let mut pending = Pending::new(t + 0.128, x, y, 0.0, damage, false, true, &unit.name);
            pending.extra.direct = true;
            pending.actor = Some(EntityRef::Unit(pet));
            pending.effect = Some(Tag::Chain);
            pending.target = Some(second);
            battle.add_pending(pending);
        }
    }
}

// pets.py:395-418: apply a three-second, non-ramping dose on projectile impact.
pub fn poison_hit(battle: &mut Battle, pet: UnitRef, target: UnitRef) {
    let unit = battle.unit(pet);
    let level = unit.level.as_ref().expect("Poison Lizard level");
    let movement = battle
        .catalog
        .stats
        .get(&unit.name, level, &["Poison Speed Decrease"], None)
        .expect("lizard movement slow")
        / 100.0;
    let attack = battle
        .catalog
        .stats
        .get(&unit.name, level, &["Poison Attack Rate Decrease"], None)
        .expect("lizard attack slow")
        / 100.0;
    let damage = battle
        .catalog
        .stats
        .get(&unit.name, level, &["Poison Max Damage per Second"], None)
        .expect("lizard poison damage");
    let source = Some(("unit".to_owned(), pet.id.0 as i64));
    spells::poison(
        battle,
        target,
        damage,
        movement,
        attack,
        1.0,
        spells::PoisonOptions {
            ramp: false,
            origin: "lizard",
            source: source.clone(),
            source_until: None,
            refresh: 0.2,
        },
    );
    let t = battle.t;
    if let Some(state) = battle
        .poison
        .iter_mut()
        .find(|state| state.unit == target && state.origin == "lizard" && state.source == source)
    {
        state.until = t + 3.0;
    }
}

// pets.py:377-394: unit links are inclusive; building-edge links are strict.
fn owl_link(battle: &Battle, mut first: EntityRef, mut second: EntityRef) -> bool {
    if matches!(first, EntityRef::Unit(_)) || matches!(second, EntityRef::Unit(_)) {
        if !matches!(second, EntityRef::Unit(_)) {
            std::mem::swap(&mut first, &mut second);
        }
        let (x, y) = battle.entity_position(second);
        return heroes::distance(battle, first, x, y) <= 3.0;
    }
    let (EntityRef::Building(first), EntityRef::Building(second)) = (first, second) else {
        return false;
    };
    let first = battle.building(first);
    let second = battle.building(second);
    let dx = 0.0_f64.max((first.x - second.x).abs() - (first.size + second.size) as f64 / 2.0);
    let dy = 0.0_f64.max((first.y - second.y).abs() - (first.size + second.size) as f64 / 2.0);
    py_pow(dx * dx + dy * dy, 0.5) < 3.0
}

// pets.py:397-412: Spirit Fox invisibility continues after owner defeat.
pub fn passives(battle: &mut Battle, pet: UnitRef) {
    let unit = battle.unit(pet);
    let owner = unit.owner;
    let present = owner.is_some_and(|hero| battle.unit(hero).alive);
    let t = battle.t;
    if unit.name_id == Name::SpiritFox && t >= unit.extra.fox_next {
        let duration = battle
            .catalog
            .stats
            .get(
                "Spirit Fox",
                unit.level.as_ref().expect("Fox level"),
                &["Invisibility Duration"],
                None,
            )
            .expect("Fox invisibility duration");
        let unit = battle.unit_mut(pet);
        unit.invisible_until = unit.invisible_until.max(t + duration);
        if present {
            let hero = battle.unit_mut(owner.expect("present owner"));
            hero.invisible_until = hero.invisible_until.max(t + duration);
        }
        battle.unit_mut(pet).extra.fox_next = t + duration + 6.0;
    }
    if battle.unit(pet).name_id == Name::AngryJelly {
        let range = if battle.unit(pet).attached(battle) {
            7.0
        } else {
            5.0
        };
        battle.unit_mut(pet).range = range;
    }
    if battle.unit(pet).attached(battle) {
        let hero = battle.unit(owner.expect("attached owner"));
        let (x, y) = (hero.x, hero.y);
        let unit = battle.unit_mut(pet);
        unit.x = x;
        unit.y = y;
    }
}
