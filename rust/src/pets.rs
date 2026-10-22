//! Ports pets.py:9-374,397-412 for Unicorn, Phoenix, Frosty, Poison Lizard
//! and Spirit Fox. Other pets retain explicit stage-3+ exclusions at equip.

use crate::battle::SpawnOptions;
use crate::geom::dist;
use crate::labels::{Name, Tag};
use crate::state::{Battle, EntityRef, UnitRef};
use crate::stats::{self, Level};
use crate::{effects, heroes, spells, units};

// pets.py:9-22: stable first minimum, with ordinary center distance.
fn valid(battle: &Battle, pet: UnitRef, target: Option<EntityRef>) -> bool {
    match target {
        Some(EntityRef::Unit(unit)) => battle.unit(unit).targetable(battle) && battle.can_hit(pet, unit),
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

// pets.py:25-49: these five pets retain their owner until defeat detaches it.
fn hero(battle: &Battle, pet: UnitRef) -> Option<UnitRef> {
    let unit = battle.unit(pet);
    if unit.name_id == Name::Diggy {
        todo!("stage 3+: Diggy owner reassignment");
    }
    unit.owner
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
    buildings.extend(battle.buildings.iter().map(|b| EntityRef::Building(b.id))
        .filter(|target| valid(battle, pet, Some(*target))));
    defenders.extend(battle.defenders_pool().map(|u| EntityRef::Unit(u.reference()))
        .filter(|target| valid(battle, pet, Some(*target))));
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
    if unit.attached(battle) {
        let candidates = buildings.iter().copied().filter(|target| match target {
            EntityRef::Building(id) => battle.is_defense_target(*id)
                && battle.building(*id).edge_distance(unit.x, unit.y) <= unit.range,
            _ => false,
        });
        return nearest(battle, EntityRef::Unit(pet), candidates);
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
    if owner_present {
        let hero = battle.unit(hero.expect("present owner"));
        let preference = battle.catalog.stats.attrs(&unit.name).get("preferred_target")
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
    if matches!(unit.name_id, Name::MightyYak | Name::Sneezy) {
        todo!("stage 3+: pet owner-loss rage");
    }
    let unit = battle.unit_mut(pet);
    unit.extra.owner_defeated = true;
    unit.target = None;
    unit.wall_target = None;
}

// pets.py:166-216: Frosty's children spawn at the pet, in count order.
fn summon(battle: &mut Battle, pet: UnitRef) -> bool {
    let unit = battle.unit(pet);
    if unit.name_id == Name::Sneezy {
        todo!("stage 3+: Sneezy summons");
    }
    if unit.name_id != Name::Frosty {
        return false;
    }
    if battle.t < unit.extra.next_summon {
        return false;
    }
    let mut alive: Vec<_> = unit.extra.children.iter().copied()
        .filter(|child| battle.unit(*child).alive).collect();
    let level = unit.level.as_ref().expect("Frosty level");
    let count = battle.catalog.stats.get("Frosty", level, &["Frostmites per Summon"], None)
        .expect("Frostmite count") as i64;
    let cap = battle.catalog.stats.get("Frosty", level, &["Maximum Frostmites Summoned"], None)
        .expect("Frostmite cap") as i64;
    let cooldown = stats::num(battle.catalog.stats.attrs("Frosty").at("raw").at("Summon Cooldown"), None)
        .expect("Frostmite cooldown");
    for _ in 0..count.min(0.max(cap - alive.len() as i64)) {
        let unit = battle.unit(pet);
        let child = battle.spawn("Frostmite", pet.team, unit.x, unit.y, SpawnOptions {
            level: Some(Level::Int(1)),
            kind: Tag::Summon,
            owner: Some(pet),
            group: unit.group.clone(),
            ..Default::default()
        });
        alive.push(child);
    }
    let next = battle.t + cooldown;
    let unit = battle.unit_mut(pet);
    unit.extra.children = alive;
    unit.extra.next_summon = next;
    false
}

// pets.py:219-227.
fn move_pet(battle: &mut Battle, pet: UnitRef, target: EntityRef) {
    if battle.t < battle.unit(pet).held_until {
        return;
    }
    battle.move_towards(pet, target, None);
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
            nearest(battle, EntityRef::Unit(pet), battle.attackers_pool().filter(|ally| {
                ally.alive && ally.reference() != pet && ally.hp < ally.max_hp
                    && !matches!(ally.kind, Tag::Siege | Tag::SiegeIdle)
                    && !matches!(ally.spec.attack, Tag::Heal | Tag::HealChain)
            }).map(|ally| EntityRef::Unit(ally.reference())))
        };
        battle.unit_mut(pet).target = target;
        if let Some(EntityRef::Unit(target)) = target {
            let unit = battle.unit(pet);
            let recipient = battle.unit(target);
            if dist(unit.x, unit.y, recipient.x, recipient.y) <= 2.5 {
                battle.unit_mut(pet).extra.healing_targets = vec![target];
                let due = battle.unit(pet).extra.heal_next.unwrap_or(t);
                if t >= due || units::isclose(t, due) {
                    let effectiveness = units::heal_effectiveness(battle, pet, target);
                    let unit = battle.unit(pet);
                    let amount = battle.catalog.stats.get("Unicorn", unit.level.as_ref().expect("Unicorn level"),
                        &["Healing per Pulse"], None).expect("Unicorn healing") * effectiveness;
                    battle.unit_mut(target).heal(amount);
                    let interval = stats::num(battle.catalog.stats.attrs("Unicorn").at("raw").at("Healing Speed"), None)
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
    let target = target(battle, pet);
    battle.unit_mut(pet).target = target;
    let Some(target) = target else {
        if present && !battle.unit(pet).attached(battle) {
            move_pet(battle, pet, EntityRef::Unit(owner.expect("present owner")));
        }
        return;
    };
    let unit = battle.unit(pet);
    if heroes::distance(battle, target, unit.x, unit.y) > unit.range {
        if !unit.attached(battle) {
            move_pet(battle, pet, target);
        }
        return;
    }
    let unit = battle.unit(pet);
    if unit.cooldown > 0.0 && !units::isclose(t + unit.cooldown, t) {
        return;
    }
    effects::damage_source(battle, Some(EntityRef::Unit(pet)), Tag::Attack, |battle| {
        units::strike(battle, pet, target);
    });
    let unit = battle.unit(pet);
    let delay = unit.interval / 0.05_f64.max(effects::slow_mult(unit, t, false));
    battle.unit_mut(pet).cooldown += delay;
    if battle.unit(pet).name_id == Name::PoisonLizard {
        if let EntityRef::Unit(target) = target {
            let unit = battle.unit(pet);
            let level = unit.level.as_ref().expect("Poison Lizard level");
            let movement = battle.catalog.stats.get(&unit.name, level, &["Poison Speed Decrease"], None)
                .expect("lizard movement slow") / 100.0;
            let attack = battle.catalog.stats.get(&unit.name, level, &["Poison Attack Rate Decrease"], None)
                .expect("lizard attack slow") / 100.0;
            let (_, movement, attack) = spells::poison_factors(battle.unit(target), 0.0, movement, attack);
            let unit = battle.unit_mut(target);
            if !(unit.kind == Tag::Guardian && unit.extra.waiting) {
                unit.move_slow = 1.0 - movement;
                unit.move_slow_until = t + 3.0;
                unit.atk_slow = 1.0 - attack;
                unit.atk_slow_until = t + 3.0;
            }
        }
    }
}

// pets.py:397-412: Spirit Fox invisibility continues after owner defeat.
pub fn passives(battle: &mut Battle, pet: UnitRef) {
    let unit = battle.unit(pet);
    let owner = unit.owner;
    let present = owner.is_some_and(|hero| battle.unit(hero).alive);
    let t = battle.t;
    if unit.name_id == Name::SpiritFox && t >= unit.extra.fox_next {
        let duration = battle.catalog.stats.get("Spirit Fox", unit.level.as_ref().expect("Fox level"),
            &["Invisibility Duration"], None).expect("Fox invisibility duration");
        let unit = battle.unit_mut(pet);
        unit.invisible_until = unit.invisible_until.max(t + duration);
        if present {
            let hero = battle.unit_mut(owner.expect("present owner"));
            hero.invisible_until = hero.invisible_until.max(t + duration);
        }
        battle.unit_mut(pet).extra.fox_next = t + duration + 6.0;
    }
    if battle.unit(pet).attached(battle) {
        let hero = battle.unit(owner.expect("attached owner"));
        let (x, y) = (hero.x, hero.y);
        let unit = battle.unit_mut(pet);
        unit.x = x;
        unit.y = y;
    }
}
