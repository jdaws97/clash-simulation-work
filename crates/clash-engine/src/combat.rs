//! Ports battle.py:587-785,960-1076: hits, death and delayed impacts.

use crate::battle::SpawnOptions;
use crate::geom::py_hypot;
use crate::labels::{Name, Tag};
use crate::state::*;
use crate::trace::{round_decimal, LogValue};
use crate::{defense, effects, geom, heroes, spells, traps, units};

pub struct SplashBuildingsOptions<'a> {
    pub walls: bool,
    pub exclude: Option<EntityRef>,
    pub kind: &'a str,
    pub wall_mult: f64,
}

impl Default for SplashBuildingsOptions<'_> {
    fn default() -> Self {
        Self {
            walls: true,
            exclude: None,
            kind: "normal",
            wall_mult: 1.0,
        }
    }
}

pub struct SplashUnitsOptions<'a> {
    pub team: Team,
    pub falloff: bool,
    pub src: Option<&'a str>,
    pub kind: &'a str,
    pub exclude: Option<UnitRef>,
}

impl Default for SplashUnitsOptions<'_> {
    fn default() -> Self {
        Self {
            team: Team::Atk,
            falloff: false,
            src: None,
            kind: "normal",
            exclude: None,
        }
    }
}

impl Battle {
    // battle.py:587-676: armor deliberately discards overkill and reports its hit.
    pub fn hit_unit(
        &mut self,
        victim: UnitRef,
        mut amount: f64,
        src: Option<&str>,
        kind: &str,
        attacker: Option<EntityRef>,
    ) -> f64 {
        let u = self.unit(victim);
        if !u.alive || amount <= 0.0 {
            return 0.0;
        }
        let t = self.t;
        if u.underground && kind != "th_poison" {
            return 0.0;
        }
        let source = attacker.or(self.src_obj);
        let effect = if kind == "th_poison" {
            Tag::Poison
        } else if kind != "normal" {
            Tag::from(kind)
        } else {
            self.effect.clone()
        };
        if effects::invulnerable(u, t) || u.attached(self) || u.extra.suspended || u.extra.leaping {
            return 0.0;
        }
        if u.dash.is_some() && !matches!(effect.as_str(), "poison" | "spell") {
            return 0.0;
        }
        if u.extra.recalled.is_some() {
            return 0.0;
        }
        if kind == "trap" && u.name_id == Name::DragonDuke && units::duke_alone(self, victim) {
            amount *= 0.8;
        }
        let mut red = if t < u.dmg_taken_until {
            u.dmg_taken_mult
        } else {
            1.0
        };
        red = red.min(1.0 - effects::torch_stats(u, t).1);
        if u.kit.is_some() {
            red = red.min(heroes::damage_taken_mult(self, victim));
        }
        if t < u.iceblock_until {
            red = red.min(1.0 - u.iceblock_red);
        }
        for (_, (reduction, until)) in &u.extra.iceblocks {
            if t < *until {
                red = red.min(1.0 - reduction);
            }
        }
        amount *= red;
        if self.def_mult != 1.0
            && u.team == Team::Atk
            && matches!(source, Some(EntityRef::Building(_)))
            && !matches!(effect.as_str(), "death" | "counter" | "spell" | "poison")
        {
            amount *= self.def_mult;
        }
        let armor = u.extra.armor_hp;
        if armor > 0.0 {
            self.unit_mut(victim).extra.armor_hp = 0.0_f64.max(armor - amount);
            amount = armor.min(amount);
        }
        if victim.team == Team::Atk {
            let label = src.filter(|s| !s.is_empty()).unwrap_or(self.src.as_str());
            let dealt = amount.min(self.unit(victim).hp);
            if let Some((_, total)) = self
                .damage_by_source
                .iter_mut()
                .find(|(key, _)| key.as_str() == label)
            {
                *total += dealt;
            } else {
                self.damage_by_source.push((label.into(), dealt));
            }
        }
        // Preserve the effect captured before on_damaged changes provenance.
        let aware = matches!(source, Some(EntityRef::Unit(v)) if v.team != victim.team)
            && victim.team == Team::Atk
            && matches!(effect.as_str(), "attack" | "secondary" | "chain");
        let u = self.unit_mut(victim);
        if armor <= 0.0 {
            u.extra.aura_hp = 0.0_f64.max(u.extra.aura_hp - amount);
            u.hp -= amount;
        }
        u.last_hit = t;
        u.extra.last_damage_source = source;
        if aware {
            u.aware_until = t + 2.0;
            u.extra.troop_hit_at = t;
        }
        units::on_damaged(self, victim, amount);
        let u = self.unit(victim);
        if u.kit.is_some() && u.alive {
            heroes::on_damaged(self, victim, amount, source, &effect);
        }
        let u = self.unit(victim);
        if u.hp <= 0.0
            && victim.team == Team::Atk
            && u.is_hero
            && u.kit.is_some()
            && !u.ability_used
            && u.alive
            && self.plan.auto_ability_on_ko()
        {
            heroes::activate(self, victim, true);
            let name = self.unit(victim).name.clone();
            self.log_event(vec![
                round_decimal(self.t, 1).into(),
                "ability".into(),
                name.into(),
                "on KO".into(),
            ]);
        }
        if self.unit(victim).hp <= 0.0 {
            if victim.team == Team::Atk {
                let label = src.filter(|s| !s.is_empty()).unwrap_or(self.src.as_str());
                let housing = 1.max(self.unit(victim).housing);
                if let Some((_, total)) = self
                    .kills_by_source
                    .iter_mut()
                    .find(|(key, _)| key.as_str() == label)
                {
                    *total += housing;
                } else {
                    self.kills_by_source.push((label.into(), housing));
                }
            }
            self.kill(victim);
        }
        amount
    }

    // battle.py:678-691.
    pub fn kill(&mut self, victim: UnitRef) {
        if !self.unit(victim).alive {
            return;
        }
        effects::record_death(self, victim);
        if self.unit(victim).kit.is_some() && heroes::on_death(self, victim) {
            // battle.py:702-706: Phoenix resumes flight when the egg hatches.
            if let Some(pet) = self.unit(victim).pet {
                if self.unit(pet).name_id == Name::Phoenix {
                    self.unit_mut(pet).flying = true;
                }
            }
            return;
        }
        let u = self.unit_mut(victim);
        u.alive = false;
        u.hp = 0.0;
        if let Some(kit) = &mut u.kit {
            // A terminal death consumes the Phoenix lifetime, including damage
            // on its expiry tick before the hero lifecycle tick runs.
            kit.doomed_at = None;
        }
        heroes::summon_death(self, victim);
        units::on_death(self, victim);
        let u = self.unit(victim);
        if u.is_hero && u.team == Team::Atk {
            spells::maybe_revive(self, victim);
        }
        let name = self.unit(victim).name.clone();
        self.log_event(vec![
            round_decimal(self.t, 1).into(),
            "dies".into(),
            name.into(),
            victim.team.as_str().into(),
        ]);
    }

    // battle.py:693-728: src/kind currently do not alter a building hit.
    pub fn hit_building(
        &mut self,
        target: EntityRef,
        amount: f64,
        _src: Option<&str>,
        _kind: &str,
    ) -> f64 {
        if !self.entity_alive(target) || amount <= 0.0 {
            return 0.0;
        }
        if let EntityRef::Building(id) = target {
            if self.t < self.building(id).overgrown_until {
                return 0.0;
            }
            if self.effect != Tag::Meteor {
                let t = self.t;
                self.building_mut(id).last_hit = t;
            }
            if let Some(EntityRef::Unit(source)) = self.src_obj {
                if source.team == Team::Atk
                    && !matches!(self.effect, Tag::Meteor | Tag::Spell | Tag::Poison)
                {
                    let (x, y) = self.entity_position(target);
                    let hp = self.building(id).hp;
                    let half_hit = self.building(id).half_hit;
                    let t = self.t;
                    for tower in &mut self.buildings {
                        let Some(w) = &mut tower.weapon else {
                            continue;
                        };
                        if tower.alive
                            && w.kind == Tag::SpellTower
                            && w.mode.as_deref() == Some("invis")
                            && w.cooldown <= 0.0
                            // battle.py:731: Invisibility coverage includes building edges.
                            && geom::edge_distance(tower.x, tower.y, x, y, half_hit) <= 4.5
                            && (hp > amount || tower.id == id)
                            && !w.extra.hit_triggers.iter().any(|(unit, _)| *unit == source)
                        {
                            w.extra.hit_triggers.push((source, t));
                        }
                    }
                }
            }
            if Some(id) == self.th {
                self.trigger_th();
            }
        }
        let hp = match target {
            EntityRef::Building(id) => &mut self.building_mut(id).hp,
            EntityRef::Wall(id) => &mut self.walls[id.0].hp,
            _ => panic!("hit_building requires a building or wall"),
        };
        *hp -= amount;
        if *hp <= 0.0 {
            self.destroy(target);
        }
        amount
    }

    // battle.py:730-750: walls have no destroyed event or counted destruction.
    pub fn destroy(&mut self, target: EntityRef) {
        if !self.entity_alive(target) {
            return;
        }
        let id = match target {
            EntityRef::Wall(id) => {
                let wall = &mut self.walls[id.0];
                wall.alive = false;
                wall.hp = 0.0;
                self.grid.set_wall(wall.tx, wall.ty, false);
                return;
            }
            EntityRef::Building(id) => id,
            _ => panic!("destroy requires a building or wall"),
        };
        let b = self.building_mut(id);
        b.alive = false;
        b.hp = 0.0;
        let (x, y, half, counted) = (b.x, b.y, b.half_hit, b.counted);
        self.grid.block_square(x, y, half, false);
        if counted {
            self.destroyed_counted += 1;
            if self.first_destroy_t.is_none() {
                self.first_destroy_t = Some(self.t);
            }
        }
        defense::on_destroyed(self, id);
        if self.destruction() >= 51 {
            self.trigger_th();
            for i in 0..self.buildings.len() {
                if self.buildings[i].key == "tesla" {
                    let tesla = self.buildings[i].id;
                    defense::reveal_tesla(self, tesla);
                }
            }
        }
        self.log_event(vec![
            round_decimal(self.t, 1).into(),
            "destroyed".into(),
            self.building(id).key.clone().into(),
            LogValue::Int(self.destruction() as i64),
        ]);
    }

    // battle.py:752-762: wall collateral uses coordinate-loop order, not dict order.
    pub fn splash_buildings(
        &mut self,
        x: f64,
        y: f64,
        radius: f64,
        damage: f64,
        options: SplashBuildingsOptions<'_>,
    ) {
        for i in 0..self.buildings.len() {
            let b = &self.buildings[i];
            let target = EntityRef::Building(b.id);
            if b.alive && Some(target) != options.exclude && b.edge_distance(x, y) <= radius {
                self.hit_building(target, damage, None, options.kind);
            }
        }
        if options.walls && radius >= 0.5 {
            let r = radius as i32 + 1;
            for tx in x as i32 - r..=x as i32 + r {
                for ty in y as i32 - r..=y as i32 + r {
                    if let Some(&id) = self.wall_indices.get(&(tx, ty)) {
                        let wall = &self.walls[id.0];
                        if wall.alive && wall.edge_distance(x, y) <= radius {
                            self.hit_building(
                                EntityRef::Wall(id),
                                damage * options.wall_mult,
                                None,
                                options.kind,
                            );
                        }
                    }
                }
            }
        }
    }

    // battle.py:764-774.
    pub fn splash_units(
        &mut self,
        x: f64,
        y: f64,
        radius: f64,
        damage: f64,
        hits_air: bool,
        hits_ground: bool,
        options: SplashUnitsOptions<'_>,
    ) {
        let pool = if options.team == Team::Atk {
            self.attackers_near(x, y, radius)
        } else {
            self.defenders_near(x, y, radius)
        };
        for reference in pool {
            let u = self.unit(reference);
            if Some(reference) == options.exclude || u.underground {
                continue;
            }
            if u.name_id != Name::Totem && (u.flying && !hits_air || !u.flying && !hits_ground) {
                continue;
            }
            let d = u.dist(x, y);
            let amount = if options.falloff && radius > 0.0 {
                damage * (1.0 - 0.5 * d / radius)
            } else {
                damage
            };
            self.hit_unit(reference, amount, options.src, options.kind, None);
        }
    }

    // battle.py:776-785.
    pub fn add_pending(&mut self, mut pending: Pending) {
        if pending.actor.is_none() {
            pending.actor = self.src_obj;
        }
        if pending.effect.is_none() {
            pending.effect = Some(self.effect.clone());
        }
        if pending.target.is_none() {
            pending.target = pending.extra.track;
        }
        if pending.released_at.is_none() {
            pending.released_at = Some(self.t);
        }
        self.pending.push(pending);
    }

    // battle.py:_resolve_pending: newly queued impacts wait, except due Revenge hops.
    pub fn resolve_pending(&mut self) {
        let mut due = Vec::new();
        let pending = std::mem::take(&mut self.pending);
        for p in pending {
            if p.at <= self.t {
                due.push(p);
            } else {
                self.pending.push(p);
            }
        }
        // battle.py:_resolve_pending: stable arrival order, including ties.
        due.sort_by(|a, b| a.at.partial_cmp(&b.at).expect("pending arrival time"));
        while !due.is_empty() {
            let mut p = due.remove(0);
            if let Some(trap) = p.extra.trap_skeleton {
                traps::spawn_skeleton(self, trap, p.x, p.y);
                continue;
            }
            if p.extra.launcher_barrel.is_some() {
                units::barrel_impact(self, p);
                continue;
            }
            if let Some((name, level, group, owner)) = p.extra.summon.take() {
                self.spawn(
                    &name,
                    p.team,
                    p.x,
                    p.y,
                    SpawnOptions {
                        level: Some(level),
                        kind: Tag::Summon,
                        group,
                        owner,
                        ..Default::default()
                    },
                );
                continue;
            }
            let effect = p.effect.clone().expect("pending effect");
            let revenge = p
                .extra
                .scatter
                .is_some_and(|owner| self.building(owner).key == "revenge");
            effects::damage_source(self, p.actor, effect, |battle| {
                battle.src = p.src.clone();
                battle.resolve_impact(p);
            });
            if revenge {
                // projectiles.csv RevengeTowerProjectile*: bounce flight begins
                // at nominal arrival, including hops due in this same tick.
                let pending = std::mem::take(&mut self.pending);
                for next in pending {
                    if next.at <= self.t
                        && next
                            .extra
                            .scatter
                            .is_some_and(|owner| self.building(owner).key == "revenge")
                    {
                        due.push(next);
                    } else {
                        self.pending.push(next);
                    }
                }
                due.sort_by(|a, b| a.at.partial_cmp(&b.at).expect("pending arrival time"));
            }
        }
    }

    fn resolve_impact(&mut self, p: Pending) {
        // battle.py:997-1001: quake hits resolve in the normal pending order.
        if let Some(quake) = &p.extra.quake {
            spells::quake_hit(self, &mut quake.borrow_mut());
            return;
        }
        // battle.py:1011-1030: a Sweeper wave rechecks its target on arrival.
        if let Some(aim) = p.extra.sweeper_aim {
            let Some(EntityRef::Unit(target)) = p.target else {
                panic!("Sweeper unit target");
            };
            let unit = self.unit(target);
            if !unit.alive || !unit.flying || geom::dist(unit.x, unit.y, p.x, p.y) > p.radius {
                return;
            }
            let angle = geom::py_atan2(unit.y - p.y, unit.x - p.x);
            let pi = std::f64::consts::PI;
            if ((angle - aim + pi).rem_euclid(2.0 * pi) - pi).abs() > 5.0 * (pi / 180.0) {
                return;
            }
            let (old_x, old_y) = (unit.x, unit.y);
            self.nudge(
                target,
                geom::py_cos(angle) * p.extra.push,
                geom::py_sin(angle) * p.extra.push,
            );
            let t = self.t;
            let unit = self.unit_mut(target);
            unit.extra.pushed_at = Some(t);
            // battle.py:1037-1047: use actual displacement after map clipping.
            let duration = 1.2_f64.min(geom::dist(old_x, old_y, unit.x, unit.y) / 6.0);
            unit.extra.pushed_until = unit.extra.pushed_until.max(t + duration);
            units::reset_beam(unit);
            return;
        }
        if p.extra.hero_impact.is_some() {
            heroes::projectile_impact(self, p);
            return;
        }
        // battle.py:1212-1220: released Scattershot shells retain their live weapon.
        if let Some(owner) = p.extra.scatter {
            if self.building(owner).key == "revenge" {
                defense::revenge_impact(self, p);
                return;
            }
            let Some(EntityRef::Unit(target)) = p.target else {
                panic!("Scattershot unit target");
            };
            defense::scatter(self, owner, target, p.damage, p.extra.rage);
            return;
        }
        if p.extra.direct {
            let target = p.target.expect("direct pending target");
            match target {
                EntityRef::Unit(u) => {
                    if self.unit(u).indirect_targetable(self) {
                        self.hit_unit(u, p.damage, None, "normal", None);
                    }
                }
                _ if self.entity_alive(target) => {
                    self.hit_building(target, p.damage, None, "normal");
                }
                _ => {}
            }
            return;
        }
        if p.extra.troop_impact.is_some() {
            units::projectile_impact(self, p);
            return;
        }
        if let Some(healing) = p.extra.healing {
            let Some(EntityRef::Unit(unit)) = p.target else {
                panic!("healing pending target");
            };
            self.unit_mut(unit).heal(healing);
            return;
        }
        let (mut x, mut y) = p
            .target
            .map_or((p.x, p.y), |target| self.entity_position(target));
        if p.src == "eagle" {
            let (ox, oy) = p.extra.origin.expect("eagle origin");
            let (mut dx, mut dy) = (x - ox, y - oy);
            let mut distance = py_hypot(dx, dy);
            if distance == 0.0 {
                dx = p.x - ox;
                dy = p.y - oy;
                distance = py_hypot(dx, dy);
            }
            let landing = p.extra.max_range.min(p.extra.min_range.max(distance));
            x = ox + dx * landing / distance;
            y = oy + dy * landing / distance;
        }
        // battle.py:1251-1266: requeue from the scheduled arrival, clearing tracking.
        if p.extra.damage_delay != 0.0 {
            let mut delayed = p;
            delayed.at += delayed.extra.damage_delay;
            delayed.x = x;
            delayed.y = y;
            delayed.target = None;
            delayed.extra.damage_delay = 0.0;
            delayed.extra.track = None;
            self.add_pending(delayed);
            return;
        }
        self.splash_units(
            x,
            y,
            p.radius,
            p.damage,
            p.hits_air,
            p.hits_ground,
            SplashUnitsOptions {
                team: p.team,
                falloff: p.falloff,
                src: Some(&p.src),
                kind: if p.src.starts_with("trap:") {
                    "trap"
                } else {
                    "normal"
                },
                ..Default::default()
            },
        );
        if p.extra.push != 0.0 {
            for reference in self.attackers_near(x, y, p.radius) {
                let u = self.unit(reference);
                if u.alive
                    // local/research/usage/totem-spell.md: Totems stay fixed.
                    // https://clashofclans.fandom.com/wiki/Totem_Spell
                    && u.name_id != Name::Totem
                    && !u.is_hero
                    && !matches!(u.kind, Tag::Pet | Tag::Siege | Tag::SiegeIdle)
                    && 0 < u.housing
                    && u.housing as f64 <= p.extra.push_housing
                    && !u.underground
                {
                    let (mut dx, mut dy) = (u.x - x, u.y - y);
                    let mut distance = py_hypot(dx, dy);
                    if distance == 0.0 {
                        let (ox, oy) = p.extra.origin.expect("push origin");
                        dx = x - ox;
                        dy = y - oy;
                        distance = py_hypot(dx, dy);
                    }
                    if distance != 0.0 {
                        self.nudge(
                            reference,
                            p.extra.push * dx / distance,
                            p.extra.push * dy / distance,
                        );
                        self.unit_mut(reference).target = None;
                        self.unit_mut(reference).wall_target = None;
                    }
                }
            }
        }
        if p.src == "mortar" {
            for reference in self.attackers_near(x, y, p.radius) {
                let u = self.unit(reference);
                if u.alive
                    && u.name_id != Name::Totem
                    && !u.flying
                    && !u.is_hero
                    && !matches!(u.kind, Tag::Pet | Tag::Siege | Tag::SiegeIdle)
                    && 0 < u.housing
                    && u.housing <= 3
                    && !u.underground
                {
                    let (ox, oy) = p.extra.origin.unwrap_or((x, y));
                    let (dx, dy) = (u.x - ox, u.y - oy);
                    let distance = py_hypot(dx, dy);
                    if distance != 0.0 {
                        self.nudge(reference, dx / distance, dy / distance);
                    }
                    self.unit_mut(reference).target = None;
                    self.unit_mut(reference).wall_target = None;
                }
            }
        }
        if p.extra.buildings != 0.0 {
            self.splash_buildings(x, y, p.radius, p.extra.buildings, Default::default());
        }
        if let Some(config) = p.extra.poison {
            spells::add_defensive_poison(self, x, y, config, "town_hall");
        }
    }
}
