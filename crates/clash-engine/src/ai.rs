//! Ports battle.py:1133-1410,1444-1458,1522-1589,1672-1753.

use crate::battle::SpawnOptions;
use crate::labels::{Name, Special, Tag};
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
            || self.t < self.next_cc_exit
        {
            return;
        }
        let (x, y) = (b.x, b.y);
        let intruders: Vec<_> = self
            .attackers_near_iter(x, y, self.params.castle_radius)
            .filter(|id| {
                let u = self.unit(*id);
                !spells::NO_TRIGGER.contains(&u.name_id)
                    && self
                        .catalog
                        .game_unit_data(&u.name, u.level.as_ref())
                        .get("DoesNotOpenCC")
                        .and_then(crate::json::Json::opt_str)
                        != Some("TRUE")
                    && u.targetable(self)
                    && u.dash.is_none()
            })
            .collect();
        for i in 0..self.cc_queue.len() {
            let entry = &self.cc_queue[i];
            let nums = self.catalog.numbers(&entry.name, &entry.level);
            if !intruders.iter().any(|id| {
                if self.unit(*id).flying {
                    nums.hits_air
                } else {
                    nums.hits_ground
                }
            }) {
                continue;
            }
            let entry = self.cc_queue.remove(i);
            self.spawn(
                &entry.name,
                Team::Def,
                x + 1.5,
                y,
                SpawnOptions {
                    level: Some(entry.level),
                    kind: Tag::Cc,
                    ..Default::default()
                },
            );
            self.next_cc_exit = self.t + self.params.castle_exit_delay;
            self.cc_released = self.cc_queue.is_empty();
            return;
        }
    }

    // Only emptiness is observed by act_attacker. These live, read-only checks
    // may short-circuit without changing membership or any callback order.
    fn preferred_remaining(&self, reference: UnitRef) -> Option<bool> {
        let pref = &self.unit(reference).spec.prefer;
        if *pref == Tag::Wall {
            return Some(self.walls.iter().any(|wall| wall.alive));
        }
        if !matches!(
            pref,
            Tag::Defense | Tag::AirDefense | Tag::Resource | Tag::Building
        ) {
            return None;
        }
        let th_active = self.th_active();
        Some(self.buildings.iter().any(|building| {
            building.targetable(self.t)
                && match pref {
                    Tag::Defense | Tag::AirDefense => building.defense_target(th_active),
                    Tag::Resource => building.resource_target,
                    _ => true,
                }
        }))
    }

    // battle.py:1189-1311: local target differs from u.target until assignment.
    pub fn act_attacker(&mut self, reference: UnitRef) {
        self.target_memory_tick(reference);
        let t = self.t;
        // battle.py:_act_attacker: upkeep continues during Sweeper pushes.
        if units::pre_tick(self, reference) {
            units::interrupt_attack(self, reference);
            return;
        }
        // battle.py:1260-1267: displacement also blocks summon/siege attacks.
        if t < self.unit(reference).extra.pushed_until {
            if self.unit(reference).can_act(t) {
                let dt = self.dt;
                let unit = self.unit_mut(reference);
                unit.cooldown = (unit.cooldown - dt).max(-dt);
            }
            units::interrupt_attack(self, reference);
            return;
        }
        if heroes::summon_tick(self, reference) {
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
        let (attack, prefer, engages_units) = (
            u.spec.attack.clone(),
            u.spec.prefer.clone(),
            u.spec.engages_units,
        );
        if matches!(attack, Tag::Heal | Tag::HealChain) {
            units::act_healer(self, reference);
            return;
        }
        if prefer == Tag::None {
            return;
        }
        // battle.py:1226-1230: Angry drops existing defender targets too.
        let angry = t < u.extra.angry_until;
        let mut target = u.target;
        if angry && matches!(target, Some(EntityRef::Unit(_))) {
            target = None;
        }
        if let Some(current) = target {
            let u = self.unit(reference);
            if !self.entity_alive(current) && u.target_kind.as_ref() != Some(&Tag::Destination) {
                target = None;
            } else if u.target_kind.as_ref() == Some(&Tag::Building) {
                let EntityRef::Building(building) = current else {
                    panic!("building target kind");
                };
                if !self.building_targetable(building)
                    && (prefer != Tag::Th || !self.siege_blocks(current))
                {
                    target = None;
                }
            } else if prefer == Tag::Th
                && u.target_kind.as_ref() == Some(&Tag::Destination)
                && !u.flying
                && t >= u.extra.next_blocker_check
            {
                self.unit_mut(reference).extra.next_blocker_check =
                    t + self.params.siege_blocker_delay;
                target = None;
            } else if u.target_kind.as_ref() == Some(&Tag::Unit) {
                let EntityRef::Unit(unit) = current else {
                    panic!("unit target kind");
                };
                if !self.unit(unit).targetable(self) {
                    target = None;
                }
            }
        }
        if prefer == Tag::Wall && target.is_some() {
            // battle.py:1281-1287: resume wall targeting when Jump expires.
            let wall = units::wall_breaker_target(self, reference).map(EntityRef::Wall);
            if wall != target && (wall.is_some() || matches!(target, Some(EntityRef::Wall(_)))) {
                target = None;
                self.unit_mut(reference).wall_target = None;
            }
        }
        if prefer == Tag::Heroes && !angry {
            if let Some(hero) = self.nearest_defender(reference, f64::INFINITY, true) {
                target = Some(EntityRef::Unit(hero));
                self.unit_mut(reference).target_kind = Some(Tag::Unit);
                self.unit_mut(reference).wall_target = None;
            }
        }
        let preferred = self.preferred_remaining(reference);
        // For Defense/AirDefense, preferred is always Some and the branch
        // below replaces engages unconditionally. Its earlier defenses_gone
        // scan therefore had no observable use.
        let mut engages = engages_units;
        if let Some(preferred) = preferred {
            let u = self.unit_mut(reference);
            if u.extra.preferred_remaining && !preferred {
                if let Some(EntityRef::Building(building)) = target {
                    u.extra.finish_preferred = Some(building);
                }
            }
            u.extra.preferred_remaining = preferred;
            let mut finishing =
                target.is_some() && target == u.extra.finish_preferred.map(EntityRef::Building);
            // battle.py:1302-1304: finish the current building before retaliating.
            if matches!(prefer, Tag::Defense | Tag::AirDefense)
                && matches!(target, Some(EntityRef::Building(_)))
            {
                finishing = true;
            }
            // battle.py:1298-1305: Giant Giant may retaliate while defenses remain.
            let retaliates = matches!(u.name_id, Name::RoyalChampion | Name::GiantGiant);
            let pet = u.pet;
            let retaliation = retaliates || pet.is_some_and(|pet| self.unit(pet).attached(self));
            engages = retaliation || !preferred && !finishing;
            if preferred && matches!(target, Some(EntityRef::Unit(_))) && !retaliation {
                target = None;
            }
        }
        if target.is_none() {
            self.unit_mut(reference).target_kind = None;
            units::interrupt_attack(self, reference);
        }
        // battle.py:1279-1298: attached Jelly and Angry disable Warden grouping.
        let warden = matches!(
            self.unit(reference).name_id,
            Name::GrandWarden | Name::ApprenticeWarden
        );
        let attached = self
            .unit(reference)
            .pet
            .is_some_and(|pet| self.unit(pet).attached(self));
        if warden && !angry && !attached {
            let (followed, waiting) = if self.params.warden_spatial {
                self.spatial_follow_target(reference)
            } else {
                (units::follow_target(self, reference), false)
            };
            if waiting && !matches!(target, Some(EntityRef::Unit(_))) {
                let u = self.unit_mut(reference);
                u.target = None;
                u.target_kind = None;
                u.wall_target = None;
                u.extra.warden_group = true;
                units::interrupt_attack(self, reference);
                return;
            }
            let u = self.unit_mut(reference);
            // battle.py:1326-1335: retain a live retaliation target over grouping.
            if !matches!(target, Some(EntityRef::Unit(_))) {
                if let Some(followed) = followed {
                    target = Some(followed);
                    let kind = if matches!(followed, EntityRef::Wall(_)) {
                        "wall"
                    } else {
                        "building"
                    };
                    u.target_kind = Some(Tag::from(kind));
                    u.wall_target = None;
                } else if u.extra.warden_group {
                    target = None;
                }
            }
            u.extra.warden_group = followed.is_some();
        } else if warden {
            self.unit_mut(reference).extra.warden_group = false;
        }
        let u = self.unit(reference);
        if engages
            && !angry
            && u.target_kind.as_ref() != Some(&Tag::Unit)
            && t >= u.extra.next_engage
        {
            self.unit_mut(reference).extra.next_engage = t + self.params.attacker_engage_delay;
            if t < self.unit(reference).aware_until || self.ally_under_attack(reference) {
                if let Some(foe) =
                    self.nearest_defender(reference, self.params.retaliation_radius, false)
                {
                    target = Some(EntityRef::Unit(foe));
                    self.unit_mut(reference).target_kind = Some(Tag::Unit);
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
        if self.unit(reference).name_id == Name::Dragon
            && !angry
            && target.is_some()
            && !matches!(target, Some(EntityRef::Unit(_)))
        {
            if let Some(foe) =
                self.nearest_defender(reference, self.params.retaliation_radius, false)
            {
                let origin = EntityRef::Unit(reference);
                if units::target_distance(self, origin, EntityRef::Unit(foe))
                    < units::target_distance(self, origin, target.expect("dragon target"))
                {
                    target = Some(EntityRef::Unit(foe));
                    self.unit_mut(reference).target_kind = Some(Tag::Unit);
                }
            }
        }
        if let Some(new_target) = target {
            if target != self.unit(reference).target {
                // battle.py:1598-1599: selection timing also inspects target distance.
                units::new_target_windup(self, reference, new_target);
            }
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
            if (spells::wall_jumped(self, wall) || self.wall_mode(reference) == Tag::Ignore)
                && self.unit(reference).kind != Tag::Siege
            {
                self.unit_mut(reference).wall_target = None;
            }
        }
        if let Some(wall) = self.unit(reference).wall_target {
            if self.walls[wall.0].alive {
                let keep = !self.params.target_list
                    || self.target_memory.get(&reference).is_some_and(|memory| {
                        memory.selected_wall == Some(wall) && t < memory.wall_until
                    });
                if keep {
                    self.engage(reference, EntityRef::Wall(wall));
                    return;
                }
            }
        }
        self.unit_mut(reference).wall_target = None;
        self.engage(reference, target);
    }

    // battle.py:1313-1321.
    pub fn ally_under_attack(&self, reference: UnitRef) -> bool {
        let u = self.unit(reference);
        self.attackers_near_iter(u.x, u.y, self.params.retaliation_radius)
            .any(|other| {
                let a = self.unit(other);
                other != reference
                    && self.t - a.extra.troop_hit_at < self.params.ally_hit_memory
                    && a.name_id != Name::Totem
            })
    }

    // battle.py:1326-1410: ordered pools; strict comparisons keep first minimum.
    pub fn choose_target(&mut self, reference: UnitRef) -> (Option<EntityRef>, Option<Tag>) {
        let u = self.unit(reference);
        let mut pref = u.spec.prefer.clone();
        if u.pet.is_some_and(|pet| self.unit(pet).attached(self)) {
            pref = Tag::Defense;
        }
        if self.t < u.extra.angry_until {
            pref = Tag::Defense;
        }
        if pref == Tag::Heroes {
            if let Some(hero) = self.nearest_defender(reference, f64::INFINITY, true) {
                return (Some(EntityRef::Unit(hero)), Some(Tag::Unit));
            }
            pref = Tag::Any;
        }
        if pref == Tag::Wall {
            if let Some(wall) = units::wall_breaker_target(self, reference) {
                return (Some(EntityRef::Wall(wall)), Some(Tag::Wall));
            }
            pref = Tag::Any;
        }
        let u = self.unit(reference);
        if let (Tag::Th, Some(th)) = (&pref, self.th) {
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
                        if best.as_ref().is_none_or(|(previous, _)| entry < *previous) {
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
                    return (Some(blocker), Some(Tag::from(kind)));
                }
            }
            return (Some(EntityRef::Building(th)), Some(Tag::Destination));
        }
        if pref == Tag::Follow {
            if let Some(followed) = units::follow_target(self, reference) {
                let kind = if matches!(followed, EntityRef::Wall(_)) {
                    "wall"
                } else {
                    "building"
                };
                return (Some(followed), Some(Tag::from(kind)));
            }
            pref = Tag::Any;
        }
        if pref == Tag::Rubble {
            return units::rubble_target(self, reference);
        }
        let mut pool = std::mem::take(&mut self.target_pool_scratch);
        pool.clear();
        if pref == Tag::AirDefense {
            pool.extend(
                self.buildings
                    .iter()
                    .filter(|b| b.key == "ad" && b.targetable(self.t))
                    .map(|b| b.id),
            );
            if pool.is_empty() {
                pref = Tag::Defense;
            }
        }
        if pref == Tag::Defense && pool.is_empty() {
            let th_active = self.th_active();
            pool.extend(
                self.buildings
                    .iter()
                    .filter(|b| b.defense_target(th_active) && b.targetable(self.t))
                    .map(|b| b.id),
            );
        }
        if pref == Tag::Resource && pool.is_empty() {
            pool.extend(
                self.buildings
                    .iter()
                    .filter(|b| b.resource_target && b.targetable(self.t))
                    .map(|b| b.id),
            );
        }
        if pool.is_empty() {
            pool.extend(
                self.buildings
                    .iter()
                    .filter(|b| b.targetable(self.t))
                    .map(|b| b.id),
            );
        }
        let u = self.unit(reference);
        if pool.is_empty() {
            self.target_pool_scratch = pool;
            let u = self.unit(reference);
            // battle.py:1426-1432: Angry also prevents last-building retaliation.
            if self.t >= u.extra.angry_until
                && u.spec.engages_units
                && (self.t < u.aware_until || self.ally_under_attack(reference))
            {
                if let Some(foe) =
                    self.nearest_defender(reference, self.params.retaliation_radius, false)
                {
                    return (Some(EntityRef::Unit(foe)), Some(Tag::Unit));
                }
            }
            return (None, None);
        }
        if self.params.target_list {
            let chosen = self.target_list_target(reference, &pool);
            self.target_pool_scratch = pool;
            return (Some(EntityRef::Building(chosen)), Some(Tag::Building));
        }
        if !u.flying
            && self.wall_mode(reference) == Tag::Normal
            && !u.underground
            && pool.len() > 1
            && u.name_id != Name::WallBreaker
        {
            let chosen = self.path_target(reference, &pool);
            self.target_pool_scratch = pool;
            return (Some(EntityRef::Building(chosen)), Some(Tag::Building));
        }
        let mut best = None;
        let mut distance = 1e9;
        for &building in &pool {
            let d = self.building(building).edge_distance(u.x, u.y);
            if d < distance {
                distance = d;
                best = Some(EntityRef::Building(building));
            }
        }
        self.target_pool_scratch = pool;
        (best, best.map(|_| Tag::Building))
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
        if u.target_kind.as_ref() == Some(&Tag::Destination) {
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
            // battle.py:1589: separation nudges must not prevent spin attacks.
            if crate::geom::dist(u.x, u.y, position.0, position.1) > 0.3 {
                units::interrupt_attack(self, reference);
                if self.t >= self.unit(reference).held_until {
                    self.move_towards(reference, target, Some(position));
                }
                return;
            }
        }
        let d = units::target_distance(self, EntityRef::Unit(reference), target);
        let reach = units::effective_range(self, self.unit(reference));
        if self.unit(reference).name_id == Name::SuperHogRider {
            let u = self.unit(reference);
            let (dx, dy) = (tx - u.x, ty - u.y);
            let length = crate::geom::py_hypot(dx, dy);
            if length != 0.0 {
                self.unit_mut(reference).extra.heading = Some((dx / length, dy / length));
            }
        }
        if self.unit(reference).name_id == Name::SuperMiner && reference.team == Team::Atk {
            self.unit_mut(reference).underground = d > reach;
        }
        if d <= reach {
            if self.unit(reference).name_id == Name::SkyWagon {
                let EntityRef::Building(building) = target else {
                    return;
                };
                if !self.is_defense_target(building) {
                    return;
                }
                if self.t >= self.unit(reference).extra.next {
                    units::launch_barrel(self, reference, target);
                }
                return;
            }
            if !units::attack_ready(self, reference, target) {
                return;
            }
            units::track_beam(self, reference, target);
            if reference.team == Team::Atk && self.unit(reference).spec.has_special(Special::Burrow)
            {
                self.unit_mut(reference).underground = false;
            }
            let u = self.unit(reference);
            if self.t < u.extra.attack_lock_until {
                return;
            }
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
                if u.name_id == Name::DragonDuke && units::duke_alone(self, reference) {
                    interval /= 1.5;
                }
                self.unit_mut(reference).cooldown += interval / 0.05_f64.max(slow);
                units::target_killed_cooldown(self, reference, target);
                // battle.py:1627-1630: reset after a kill, then apply next-target windup.
                if self.unit(reference).name_id == Name::Valkyrie && !self.entity_alive(target) {
                    self.unit_mut(reference).cooldown = 0.0;
                }
            }
            return;
        }
        units::interrupt_attack(self, reference);
        if self.t < self.unit(reference).held_until {
            return;
        }
        self.move_towards(reference, target, None);
    }

    pub fn defender_in_leash(&self, reference: UnitRef, x: f64, y: f64) -> bool {
        let u = self.unit(reference);
        let center = u.home.unwrap_or((u.x, u.y));
        let radius = if u.home.is_some() {
            u.leash
        } else {
            f64::INFINITY
        };
        crate::geom::dist(center.0, center.1, x, y) <= radius
    }

    // battle.py:1672-1753: defender retargeting is every half-second.
    pub fn act_defender(&mut self, reference: UnitRef) {
        let t = self.t;
        let u = self.unit(reference);
        if let (Name::BarbarianKing, Some((x, y))) = (u.name_id, u.home) {
            let distance = crate::geom::dist(u.x, u.y, x, y);
            if distance > u.leash {
                let leash = u.leash;
                let u = self.unit_mut(reference);
                u.x = x + (u.x - x) * leash / distance;
                u.y = y + (u.y - y) * leash / distance;
            }
        }
        let u = self.unit(reference);
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
        if matches!(u.spec.attack, Tag::Heal | Tag::HealChain) {
            units::act_healer(self, reference);
            return;
        }
        if u.spec.attack == Tag::None && u.name_id != Name::RuinWitch {
            return;
        }
        let dt = self.dt;
        let u = self.unit_mut(reference);
        u.cooldown = (u.cooldown - dt).max(-dt);
        let mut target = match u.target {
            Some(EntityRef::Unit(target)) => Some(target),
            None => None,
            _ => panic!("defender target is not a unit"),
        };
        if target.is_some_and(|id| !self.unit(id).alive || !self.unit(id).targetable(self)) {
            target = None;
        }
        let u = self.unit(reference);
        if u.spec.prefer == Tag::Heroes && target.is_some_and(|id| !self.unit(id).is_hero) {
            target = None;
        }
        if u.name_id == Name::BarbarianKing && target.is_some() {
            let (x, y) = u.home.expect("King home");
            let target_unit = self.unit(target.expect("King target"));
            if crate::geom::dist(target_unit.x, target_unit.y, x, y) > u.leash {
                target = None;
            }
        }
        if target.is_none() || u.name_id != Name::BarbarianKing && t >= u.extra.next_retarget {
            let delay = self.params.defender_retarget_delay;
            let u = self.unit_mut(reference);
            u.extra.next_retarget = t + delay;
            let u = self.unit(reference);
            let prefer_heroes = u.spec.prefer == Tag::Heroes;
            let mut hero_available = false;
            let (mut best, mut distance) = (None, f64::INFINITY);
            let (mut best_hero, mut hero_distance) = (None, f64::INFINITY);
            for a in self.attackers_pool() {
                if !a.targetable(self) || !self.can_hit(reference, a.reference()) {
                    continue;
                }
                // Python's preference sees heroes even outside the leash.
                // Record global eligibility before filtering by that leash.
                let hero = prefer_heroes && a.is_hero;
                hero_available |= hero;
                if hero_available && !hero {
                    continue;
                }
                // With no leash this comparison can never reject a target.
                // Filter ineligible attackers before calling CPython hypot.
                if !self.defender_in_leash(reference, a.x, a.y) {
                    continue;
                }
                let d = a.dist(u.x, u.y);
                if d < distance {
                    distance = d;
                    best = Some(a.reference());
                }
                if hero && d < hero_distance {
                    hero_distance = d;
                    best_hero = Some(a.reference());
                }
            }
            // Both minima follow attacker_order and keep the first tie. If
            // every eligible hero is outside the leash, Python chooses None.
            target = if hero_available { best_hero } else { best };
        }
        if let Some(new_target) = target {
            if target.map(EntityRef::Unit) != self.unit(reference).target {
                // battle.py:2071-2072: defenders use the same target-aware windup.
                units::new_target_windup(self, reference, EntityRef::Unit(new_target));
            }
        }
        self.unit_mut(reference).target = target.map(EntityRef::Unit);
        let Some(target) = target else {
            units::interrupt_attack(self, reference);
            if spells::escape_poison(self, reference) {
                return;
            }
            if let Some(home) = self.unit(reference).home {
                let u = self.unit_mut(reference);
                u.extra.patrol_state = Some(
                    if (u.x, u.y) != home {
                        "returning"
                    } else {
                        "patrolling"
                    }
                    .to_owned(),
                );
                self.move_towards(reference, EntityRef::Unit(reference), Some(home));
            }
            return;
        };
        heroes::defending_hero_ability(self, reference);
        let u = self.unit(reference);
        let victim = self.unit(target);
        let d = u.dist(victim.x, victim.y);
        let reach = units::effective_range(self, u);
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
                units::target_killed_cooldown(self, reference, EntityRef::Unit(target));
                // battle.py:1796-1799: defending Valkyries reset on kills too.
                if self.unit(reference).name_id == Name::Valkyrie && !self.unit(target).alive {
                    self.unit_mut(reference).cooldown = 0.0;
                }
            }
            return;
        }
        units::interrupt_attack(self, reference);
        self.move_towards(reference, EntityRef::Unit(target), None);
    }
}
