//! Ports battle.py:1133-1410,1444-1458,1522-1589,1672-1753.

use crate::battle::SpawnOptions;
use crate::state::*;
use crate::{effects, heroes, spells, units};

impl Battle {
    // battle.py:1133-1170: one eligible queue entry per exit, in queue order.
    pub fn castle(&mut self) {
        let Some(castle) = self.cc_building else {
            return;
        };
        let b = self.building(castle);
        if self.cc_released
            || self.cc_queue.is_empty()
            || !b.alive
            || b.mode.as_deref() == Some("sleep")
            || self.t < self.next_cc_exit {
            return;
        }
        let (x, y) = (b.x, b.y);
        let intruders: Vec<_> = self.attackers_near(x, y, 13.0).into_iter().filter(|id| {
            let u = self.unit(*id);
            !spells::NO_TRIGGER.contains(&u.name.as_str()) && u.targetable(self) && u.dash.is_none()
        }).collect();
        for i in 0..self.cc_queue.len() {
            let entry = &self.cc_queue[i];
            let nums = self.catalog.numbers(&entry.name, &entry.level);
            if !intruders.iter().any(|id| if self.unit(*id).flying {
                nums.hits_air
            } else {
                nums.hits_ground
            }) {
                continue;
            }
            let entry = self.cc_queue.remove(i);
            self.spawn(&entry.name, Team::Def, x + 1.5, y, SpawnOptions {
                level: Some(entry.level),
                kind: "cc".to_owned(),
                ..Default::default()
            });
            self.next_cc_exit = self.t + 0.3;
            self.cc_released = self.cc_queue.is_empty();
            return;
        }
    }

    // battle.py:1173-1187: None means no preferred-target rule; empty means gone.
    pub fn preferred_pool(&self, reference: UnitRef) -> Option<Vec<EntityRef>> {
        let pref = self.unit(reference).spec.prefer.as_str();
        if !matches!(pref, "defense" | "air_defense" | "resource" | "wall" | "building") {
            return None;
        }
        if pref == "wall" {
            return Some(self.walls.iter().filter(|w| w.alive).map(|w| EntityRef::Wall(w.id)).collect());
        }
        Some(self.buildings.iter().filter(|b| {
            self.building_targetable(b.id) && match pref {
                "defense" | "air_defense" => self.is_defense_target(b.id),
                "resource" => b.kind == "resource" || units::RESOURCE_KEYS.contains(&b.key.as_str()),
                _ => true,
            }
        }).map(|b| EntityRef::Building(b.id)).collect())
    }

    // battle.py:1189-1311: local target differs from u.target until assignment.
    pub fn act_attacker(&mut self, reference: UnitRef) {
        let t = self.t;
        if heroes::summon_tick(self, reference) {
            return;
        }
        if units::pre_tick(self, reference) {
            units::interrupt_attack(self, reference);
            return;
        }
        let u = self.unit(reference);
        if !u.can_act(t) || t < u.held_until && u.speed > 0.0 && u.target.is_none() {
            units::interrupt_attack(self, reference);
            return;
        }
        let dt = self.dt;
        let u = self.unit_mut(reference);
        u.cooldown = (u.cooldown - dt).max(-dt);
        let sp = u.spec.clone();
        if matches!(sp.attack.as_str(), "heal" | "heal_chain") {
            units::act_healer(self, reference);
            return;
        }
        if sp.prefer == "none" {
            return;
        }
        let mut target = u.target;
        if let Some(current) = target {
            let u = self.unit(reference);
            if !self.entity_alive(current) && u.target_kind.as_deref() != Some("destination") {
                target = None;
            } else if u.target_kind.as_deref() == Some("building") {
                let EntityRef::Building(building) = current else {
                    panic!("building target kind");
                };
                if !self.building_targetable(building)
                    && (sp.prefer != "th" || !self.siege_blocks(current))
                {
                    target = None;
                }
            } else if sp.prefer == "th"
                && u.target_kind.as_deref() == Some("destination")
                && !u.flying
                && t >= u.extra.next_blocker_check {
                self.unit_mut(reference).extra.next_blocker_check = t + 0.5;
                target = None;
            } else if u.target_kind.as_deref() == Some("unit") {
                let EntityRef::Unit(unit) = current else {
                    panic!("unit target kind");
                };
                if !self.unit(unit).targetable(self) {
                    target = None;
                }
            }
        }
        if sp.prefer == "wall" && matches!(target, Some(EntityRef::Wall(_))) {
            todo!("stage 2: battle.py:1228 Wall Breaker preferred wall");
        }
        if sp.prefer == "heroes" {
            if let Some(hero) = self.nearest_defender(reference, f64::INFINITY, true) {
                target = Some(EntityRef::Unit(hero));
                self.unit_mut(reference).target_kind = Some("unit".to_owned());
                self.unit_mut(reference).wall_target = None;
            }
        }
        let preferred = self.preferred_pool(reference);
        let mut engages = sp.engages_units;
        if matches!(sp.prefer.as_str(), "defense" | "air_defense") {
            engages = engages || self.defenses_gone();
        }
        if let Some(preferred) = &preferred {
            let u = self.unit_mut(reference);
            if u.extra.preferred_remaining && preferred.is_empty() {
                if let Some(EntityRef::Building(building)) = target {
                    u.extra.finish_preferred = Some(building);
                }
            }
            u.extra.preferred_remaining = !preferred.is_empty();
            let finishing = target.is_some() && target == u.extra.finish_preferred.map(EntityRef::Building);
            let royal_champion = u.name == "Royal Champion";
            let pet = u.pet;
            let retaliation = royal_champion || pet.is_some_and(|pet| self.unit(pet).attached(self));
            engages = retaliation || preferred.is_empty() && !finishing;
            if !preferred.is_empty() && matches!(target, Some(EntityRef::Unit(_))) && !retaliation {
                target = None;
            }
        }
        if target.is_none() {
            self.unit_mut(reference).target_kind = None;
            units::interrupt_attack(self, reference);
        }
        if matches!(self.unit(reference).name.as_str(), "Grand Warden" | "Apprentice Warden") {
            let followed = units::follow_target(self, reference);
            let u = self.unit_mut(reference);
            if let Some(followed) = followed {
                target = Some(followed);
                let kind = if matches!(followed, EntityRef::Wall(_)) {
                    "wall"
                } else {
                    "building"
                };
                u.target_kind = Some(kind.to_owned());
                u.wall_target = None;
            } else if u.extra.warden_group {
                target = None;
            }
            u.extra.warden_group = followed.is_some();
        }
        let u = self.unit(reference);
        let angry = t < u.extra.angry_until;
        if engages && !angry && u.target_kind.as_deref() != Some("unit") && t >= u.extra.next_engage {
            self.unit_mut(reference).extra.next_engage = t + 0.5;
            if t < self.unit(reference).aware_until || self.ally_under_attack(reference) {
                if let Some(foe) = self.nearest_defender(reference, 7.0, false) {
                    target = Some(EntityRef::Unit(foe));
                    self.unit_mut(reference).target_kind = Some("unit".to_owned());
                    self.unit_mut(reference).wall_target = None;
                }
            }
        }
        if target.is_none() {
            self.unit_mut(reference).wall_target = None;
            let chosen = self.choose_target(reference);
            target = chosen.0;
            self.unit_mut(reference).target_kind = chosen.1;
        }
        if self.unit(reference).name == "Dragon"
            && target.is_some()
            && !matches!(target, Some(EntityRef::Unit(_))) {
            if let Some(foe) = self.nearest_defender(reference, 7.0, false) {
                let origin = EntityRef::Unit(reference);
                if units::target_distance(self, origin, EntityRef::Unit(foe)) < units::target_distance(self, origin, target.expect("dragon target")) {
                    target = Some(EntityRef::Unit(foe));
                    self.unit_mut(reference).target_kind = Some("unit".to_owned());
                }
            }
        }
        if target.is_some() && target != self.unit(reference).target {
            units::new_target_windup(self, reference);
        }
        self.unit_mut(reference).target = target;
        units::update_burrow(self, reference, target);
        let Some(target) = target else {
            units::interrupt_attack(self, reference);
            return;
        };
        if t < self.unit(reference).extra.horse_until {
            self.unit_mut(reference).wall_target = None;
        }
        if let Some(wall) = self.unit(reference).wall_target {
            if (spells::wall_jumped(self, wall)
                || self.wall_mode(reference) == "ignore")
                && self.unit(reference).kind != "siege" {
                self.unit_mut(reference).wall_target = None;
            }
        }
        if let Some(wall) = self.unit(reference).wall_target {
            if self.walls[wall.0].alive {
                self.engage(reference, EntityRef::Wall(wall));
                return;
            }
        }
        self.unit_mut(reference).wall_target = None;
        self.engage(reference, target);
    }

    // battle.py:1313-1321.
    pub fn ally_under_attack(&self, reference: UnitRef) -> bool {
        let u = self.unit(reference);
        self.attackers_near(u.x, u.y, 7.0).iter().any(|other| {
            let a = self.unit(*other);
            *other != reference && self.t - a.extra.troop_hit_at < 1.0 && a.name != "Totem"
        })
    }

    // battle.py:1323-1324.
    pub fn defenses_gone(&self) -> bool {
        !self.buildings.iter().any(|b| b.alive && self.is_defense_target(b.id))
    }

    // battle.py:1326-1410: ordered pools; strict comparisons keep first minimum.
    pub fn choose_target(&mut self, reference: UnitRef) -> (Option<EntityRef>, Option<String>) {
        let u = self.unit(reference);
        let mut pref = u.spec.prefer.clone();
        if u.pet.is_some_and(|pet| self.unit(pet).attached(self)) {
            pref = "defense".to_owned();
        }
        if self.t < u.extra.angry_until {
            pref = "defense".to_owned();
        }
        if pref == "heroes" {
            if let Some(hero) = self.nearest_defender(reference, f64::INFINITY, true) {
                return (Some(EntityRef::Unit(hero)), Some("unit".to_owned()));
            }
            pref = "any".to_owned();
        }
        if pref == "wall" {
            todo!("stage 2: battle.py:1341 Wall Breaker target selection");
        }
        if pref == "th" && self.th.is_some() {
            let th = self.th.expect("Town Hall destination");
            let (tx, ty) = self.entity_position(EntityRef::Building(th));
            if !u.flying {
                let mut best: Option<(f64, EntityRef)> = None;
                let blockers = self
                    .buildings
                    .iter()
                    .map(|b| EntityRef::Building(b.id))
                    .chain(self.walls.iter().map(|w| EntityRef::Wall(w.id)));
                for blocker in blockers {
                    if blocker == EntityRef::Building(th)
                        || !self.entity_alive(blocker)
                        || !self.siege_blocks(blocker)
                    {
                        continue;
                    }
                    if let Some(entry) = units::segment_entry(self, u.x, u.y, tx, ty, blocker) {
                        if best.as_ref().map_or(true, |(previous, _)| entry < *previous) {
                            best = Some((entry, blocker));
                        }
                    }
                }
                if let Some((_, blocker)) = best {
                    let kind = if matches!(blocker, EntityRef::Wall(_)) {
                        "wall"
                    } else {
                        "building"
                    };
                    return (Some(blocker), Some(kind.to_owned()));
                }
            }
            return (Some(EntityRef::Building(th)), Some("destination".to_owned()));
        }
        if pref == "follow" {
            if let Some(followed) = units::follow_target(self, reference) {
                let kind = if matches!(followed, EntityRef::Wall(_)) {
                    "wall"
                } else {
                    "building"
                };
                return (Some(followed), Some(kind.to_owned()));
            }
            pref = "any".to_owned();
        }
        if pref == "rubble" {
            return units::rubble_target(self, reference);
        }
        let mut pool: Option<Vec<BuildingId>> = None;
        if pref == "air_defense" {
            let buildings: Vec<_> = self.buildings.iter().filter(|b| b.key == "ad" && self.building_targetable(b.id)).map(|b| b.id).collect();
            if buildings.is_empty() {
                pref = "defense".to_owned();
            } else {
                pool = Some(buildings);
            }
        }
        if pref == "defense" && pool.is_none() {
            pool = Some(self.buildings.iter().filter(|b| self.is_defense_target(b.id) && self.building_targetable(b.id)).map(|b| b.id).collect());
        }
        if pref == "resource" && pool.is_none() {
            pool = Some(self.buildings.iter().filter(|b| (b.kind == "resource" || units::RESOURCE_KEYS.contains(&b.key.as_str())) && self.building_targetable(b.id)).map(|b| b.id).collect());
        }
        let pool = pool.filter(|p| !p.is_empty()).unwrap_or_else(|| self.buildings.iter().filter(|b| self.building_targetable(b.id)).map(|b| b.id).collect());
        let u = self.unit(reference);
        if pool.is_empty() {
            if u.spec.engages_units && (self.t < u.aware_until || self.ally_under_attack(reference)) {
                if let Some(foe) = self.nearest_defender(reference, 7.0, false) {
                    return (Some(EntityRef::Unit(foe)), Some("unit".to_owned()));
                }
            }
            return (None, None);
        }
        if !u.flying
            && self.wall_mode(reference) == "normal"
            && !u.underground
            && pool.len() > 1
            && u.name != "Wall Breaker" {
            return (Some(EntityRef::Building(self.path_target(reference, &pool))), Some("building".to_owned()));
        }
        let mut best = None;
        let mut distance = 1e9;
        for building in pool {
            let d = self.building(building).edge_distance(u.x, u.y);
            if d < distance {
                distance = d;
                best = Some(EntityRef::Building(building));
            }
        }
        (best, best.map(|_| "building".to_owned()))
    }

    // battle.py:1412-1426: overgrowth and suspension still block ground sieges.
    fn siege_blocks(&self, blocker: EntityRef) -> bool {
        match blocker {
            EntityRef::Wall(_) => true,
            EntityRef::Building(id) => {
                let b = self.building(id);
                if b.key == "tesla" && !b.revealed {
                    return false;
                }
                self.t >= b.invisible_until
            }
            _ => panic!("siege blocker must be a structure"),
        }
    }

    // battle.py:1444-1458: <= intentionally picks the LAST equal defender.
    pub fn nearest_defender(
        &self,
        reference: UnitRef,
        radius: f64,
        heroes_only: bool,
    ) -> Option<UnitRef> {
        let u = self.unit(reference);
        let mut best = None;
        let mut distance = radius;
        for v in self.defenders_pool() {
            if !v.alive || self.t < v.active_at || self.t < v.invisible_until {
                continue;
            }
            if heroes_only && !v.is_hero {
                continue;
            }
            if !self.can_hit(reference, v.reference()) {
                continue;
            }
            let d = u.dist(v.x, v.y);
            if d <= distance {
                distance = d;
                best = Some(v.reference());
            }
        }
        best
    }

    // battle.py:1522-1589.
    pub fn engage(&mut self, reference: UnitRef, target: EntityRef) {
        let (tx, ty) = self.entity_position(target);
        let u = self.unit_mut(reference);
        if (tx, ty) != (u.x, u.y) {
            u.extra.facing = (tx - u.x, ty - u.y);
        }
        if u.target_kind.as_deref() == Some("destination") {
            let (x, y, reach) = (u.x, u.y, u.range);
            if self.entity_edge_distance(target, x, y) <= reach {
                self.kill(reference);
            } else {
                let step = self.speed_of(reference) * self.dt;
                self.move_straight(reference, tx, ty, step);
            }
            return;
        }
        let position = units::valkyrie_position(self, reference, target);
        if let Some(position) = position {
            let u = self.unit(reference);
            if (u.x, u.y) != position {
                units::interrupt_attack(self, reference);
                if self.t >= self.unit(reference).held_until {
                    self.move_towards(reference, target, Some(position));
                }
                return;
            }
        }
        let d = units::target_distance(self, EntityRef::Unit(reference), target);
        let reach = units::effective_range(self.unit(reference));
        if self.unit(reference).name == "Super Hog Rider" {
            let u = self.unit(reference);
            let (dx, dy) = (tx - u.x, ty - u.y);
            let length = crate::geom::py_hypot(dx, dy);
            if length != 0.0 {
                self.unit_mut(reference).extra.heading = Some((dx / length, dy / length));
            }
        }
        if self.unit(reference).name == "Super Miner" && reference.team == Team::Atk {
            self.unit_mut(reference).underground = d > reach;
        }
        if d <= reach {
            if self.unit(reference).name == "Sky Wagon" {
                todo!("stage 2: battle.py:1559 Sky Wagon barrel attack");
            }
            if !units::attack_ready(self, reference, target) {
                return;
            }
            units::track_beam(self, reference, target);
            if reference.team == Team::Atk && self.unit(reference).spec.has_special("burrow") {
                self.unit_mut(reference).underground = false;
            }
            let u = self.unit(reference);
            if u.cooldown <= 0.0 && self.t >= u.held_until || u.cooldown <= 0.0 && u.range >= 1.0 {
                units::strike(self, reference, target);
                let slow = effects::slow_mult(self.unit(reference), self.t, false);
                let mut interval = units::attack_interval(self, reference);
                let u = self.unit(reference);
                if self.t < u.extra.horse_until {
                    let base_interval = u.extra.horse_interval;
                    let passive_speed = base_interval / u.interval;
                    interval = base_interval / (passive_speed + u.extra.horse_attack);
                }
                if self.t < u.extra.haste_attack_until {
                    interval /= u.extra.haste_attack;
                }
                if u.name == "Dragon Duke" {
                    todo!("stage 3: battle.py:1582 Dragon Duke Royal Rampage cadence");
                }
                self.unit_mut(reference).cooldown += interval / 0.05_f64.max(slow);
            }
            return;
        }
        units::interrupt_attack(self, reference);
        if self.t < self.unit(reference).held_until {
            return;
        }
        self.move_towards(reference, target, None);
    }

    // battle.py:1672-1753: defender retargeting is every half-second.
    pub fn act_defender(&mut self, reference: UnitRef) {
        let t = self.t;
        let u = self.unit(reference);
        if u.name == "Barbarian King" && u.home.is_some() {
            todo!("stage 3: battle.py:1675 defending King leash clamp");
        }
        if t < u.active_at {
            return;
        }
        if units::pre_tick(self, reference) {
            units::interrupt_attack(self, reference);
            return;
        }
        let u = self.unit(reference);
        if !u.can_act(t) || t < u.held_until {
            units::interrupt_attack(self, reference);
            return;
        }
        if matches!(u.spec.attack.as_str(), "heal" | "heal_chain") {
            units::act_healer(self, reference);
            return;
        }
        if u.spec.attack == "none" && u.name != "Ruin Witch" {
            return;
        }
        let dt = self.dt;
        let u = self.unit_mut(reference);
        u.cooldown = (u.cooldown - dt).max(-dt);
        let mut target = match u.target {
            Some(EntityRef::Unit(target)) => Some(target), None => None,
            _ => panic!("defender target is not a unit")
        };
        if target.is_some_and(|id| !self.unit(id).alive || !self.unit(id).targetable(self)) {
            target = None;
        }
        let u = self.unit(reference);
        if u.spec.prefer == "heroes" && target.is_some_and(|id| !self.unit(id).is_hero) {
            target = None;
        }
        if u.name == "Barbarian King" && target.is_some() {
            todo!("stage 3: battle.py:1697 defending King target leash");
        }
        if target.is_none() || u.name != "Barbarian King" && t >= u.extra.next_retarget {
            let u = self.unit_mut(reference);
            u.extra.next_retarget = t + 0.5;
            let center = u.home.unwrap_or((u.x, u.y));
            let radius = if u.home.is_some() {
                u.leash
            } else {
                f64::INFINITY
            };
            let u = self.unit(reference);
            let (mut best, mut distance) = (None, f64::INFINITY);
            for a in self.attackers_pool() {
                if crate::geom::py_hypot(center.0 - a.x, center.1 - a.y) > radius {
                    continue;
                }
                if !a.targetable(self) || !self.can_hit(reference, a.reference()) {
                    continue;
                }
                if u.spec.prefer == "heroes"
                    && self.attackers_pool().any(|hero| hero.is_hero
                    && hero.targetable(self)
                    && self.can_hit(reference, hero.reference()))
                    && !a.is_hero {
                    continue;
                }
                let d = a.dist(u.x, u.y);
                if d < distance {
                    distance = d;
                    best = Some(a.reference());
                }
            }
            target = best;
        }
        if target.is_some() && target.map(EntityRef::Unit) != self.unit(reference).target {
            units::new_target_windup(self, reference);
        }
        self.unit_mut(reference).target = target.map(EntityRef::Unit);
        let Some(target) = target else {
            units::interrupt_attack(self, reference);
            if spells::escape_poison(self, reference) {
                return;
            }
            if let Some(home) = self.unit(reference).home {
                let u = self.unit_mut(reference);
                u.extra.patrol_state = Some(if (u.x, u.y) != home {
                    "returning"
                } else {
                    "patrolling"
                }
                .to_owned());
                self.move_towards(reference, EntityRef::Unit(reference), Some(home));
            }
            return;
        };
        heroes::defending_hero_ability(self, reference);
        let u = self.unit(reference);
        let victim = self.unit(target);
        let d = u.dist(victim.x, victim.y);
        let reach = units::effective_range(u);
        if d <= reach {
            if !units::attack_ready(self, reference, EntityRef::Unit(target)) {
                return;
            }
            units::track_beam(self, reference, EntityRef::Unit(target));
            if self.unit(reference).cooldown <= 0.0 {
                units::strike(self, reference, EntityRef::Unit(target));
                let slow = effects::slow_mult(self.unit(reference), t, false);
                let interval = units::attack_interval(self, reference);
                self.unit_mut(reference).cooldown += interval / 0.05_f64.max(slow);
            }
            return;
        }
        units::interrupt_attack(self, reference);
        self.move_towards(reference, EntityRef::Unit(target), None);
    }
}
