//! Ports battle.py:212-234,370-577,787-958,1079-1085.
//! Damage, movement and AI continue in combat.rs, movement.rs and ai.rs.

use crate::geom::{round6, round_half_even};
use crate::state::*;
use crate::stats::Level;
use crate::trace::{exported_value, round_decimal, LogValue};
use crate::{defense, effects, geom, heroes, spells, traps, units};

const BUCKET: f64 = 4.0;
const SCOUT_TIME: f64 = 30.0;
const TH_ACTIVATION_DELAY: f64 = 0.5;

pub struct SpawnOptions {
    pub level: Option<Level>,
    pub kind: String,
    pub group: String,
    pub owner: Option<UnitRef>,
    pub town_hall: Option<i64>,
}

impl Default for SpawnOptions {
    fn default() -> Self {
        Self {
            level: None,
            kind: "troop".to_owned(),
            group: "main".to_owned(),
            owner: None,
            town_hall: None,
        }
    }
}

impl Battle {
    // battle.py:214-234: delayed activation is distinct from a direct setter.
    pub fn th_active(&self) -> bool {
        self.th_on_at.is_some_and(|at| self.t >= at)
    }

    pub fn set_th_active(&mut self, active: bool) {
        self.th_on_at = active.then_some(f64::NEG_INFINITY);
    }

    pub fn trigger_th(&mut self) {
        if self.th_on_at.is_none() && self.th.is_some_and(|id| {
            let th = self.building(id);
            th.weapon.is_some() && !th.extra.unavailable
        }) {
            self.th_on_at = Some(self.t + TH_ACTIVATION_DELAY);
        }
    }

    // battle.py:518-534: destruction is an integer ceiling; raw damage is not.
    pub fn raw_destruction(&self) -> f64 {
        100.0 * self.destroyed_counted as f64 / self.total_counted.max(1) as f64
    }

    pub fn destruction(&self) -> usize {
        let total = self.total_counted.max(1);
        (100 * self.destroyed_counted + total - 1) / total
    }

    pub fn stars(&self) -> usize {
        usize::from(self.destruction() >= 50)
            + usize::from(self.th.is_some_and(|id| !self.building(id).alive))
            + usize::from(self.destroyed_counted >= self.total_counted)
    }

    // battle.py:536-554: unavailable structures can still be targeted.
    pub fn building_targetable(&self, id: BuildingId) -> bool {
        let b = self.building(id);
        if !b.alive || !b.counted && b.key != "th" {
            return false;
        }
        if self.t < b.overgrown_until || self.t < b.invisible_until
            || self.t < b.extra.yellow_until {
            return false;
        }
        b.key != "tesla" || b.revealed
    }

    pub fn is_defense_target(&self, id: BuildingId) -> bool {
        let b = self.building(id);
        if b.key == "th" {
            b.weapon.is_some() && self.th_active()
        } else {
            b.is_defense
        }
    }

    // battle.py:1079-1085: cells and their members keep first insertion order.
    // Membership stays frozen during the tick, but queries read current x/y.
    pub fn rebuild_buckets(&mut self) {
        self.buckets.clear();
        self.bucket_indices.clear();
        let attackers: Vec<_> = self.attackers_pool().filter(|unit| unit.alive)
            .map(Unit::reference).collect();
        for reference in attackers {
            let unit = self.unit(reference);
            let cell = ((unit.x / BUCKET) as i32, (unit.y / BUCKET) as i32);
            let index = match self.bucket_indices.get(&cell) {
                Some(index) => *index,
                None => {
                    let index = self.buckets.len();
                    self.buckets.push((cell, Vec::new()));
                    self.bucket_indices.insert(cell, index);
                    index
                }
            };
            self.buckets[index].1.push(reference);
        }
        self.buckets_initialized = true;
        heroes::apply_auras(self);
    }

    pub fn attackers_near(&self, x: f64, y: f64, radius: f64) -> Vec<UnitRef> {
        let mut out = Vec::new();
        let radius_squared = radius * radius;
        // battle.py:560-561: int() truncates toward zero, even outside the world.
        for i in ((x - radius) / BUCKET) as i32..=((x + radius) / BUCKET) as i32 {
            for j in ((y - radius) / BUCKET) as i32..=((y + radius) / BUCKET) as i32 {
                if let Some(index) = self.bucket_indices.get(&(i, j)) {
                    for reference in &self.buckets[*index].1 {
                        let unit = self.unit(*reference);
                        let dx = unit.x - x;
                        let dy = unit.y - y;
                        if dx * dx + dy * dy <= radius_squared && unit.alive
                            && !unit.extra.suspended {
                            out.push(*reference);
                        }
                    }
                }
            }
        }
        out
    }

    pub fn defenders_near(&self, x: f64, y: f64, radius: f64) -> Vec<UnitRef> {
        let radius_squared = radius * radius;
        self.defenders_pool().filter(|unit| {
            // battle.py:577 uses `** 2` (C pow), not a product
            unit.alive && geom::py_pow(unit.x - x, 2.0) + geom::py_pow(unit.y - y, 2.0) <= radius_squared
        }).map(Unit::reference).collect()
    }

    // battle.py:579-584: Totems count as both heights for attack eligibility.
    pub fn can_hit(&self, attacker: UnitRef, victim: UnitRef) -> bool {
        let attacker = self.unit(attacker);
        let victim = self.unit(victim);
        if !victim.alive || victim.underground || victim.extra.leaping {
            return false;
        }
        if victim.name == "Totem" {
            return true;
        }
        if victim.flying {
            attacker.hits_air
        } else {
            attacker.hits_ground
        }
    }

    // battle.py:370-390: the red line follows standing footprints and walls;
    // banners remain occupied, while Hidden Teslas never create a red line.
    pub fn live_no_deploy(&mut self) -> &std::collections::HashSet<(i32, i32)> {
        if self.nd_version == Some(self.grid.version) {
            return &self.nd_cache;
        }
        let mut occupied = self.banner_tiles.clone();
        for b in &self.buildings {
            if !b.alive || b.key == "tesla" || b.key == "banner" {
                continue;
            }
            let x0 = round_half_even(b.x - b.size as f64 / 2.0) as i32;
            let y0 = round_half_even(b.y - b.size as f64 / 2.0) as i32;
            for dx in 0..b.size as i32 {
                for dy in 0..b.size as i32 {
                    occupied.insert((x0 + dx, y0 + dy));
                }
            }
        }
        for w in &self.walls {
            if w.alive {
                occupied.insert((w.tx, w.ty));
            }
        }
        self.nd_cache.clear();
        for (tx, ty) in occupied {
            for dx in -1..=1 {
                for dy in -1..=1 {
                    self.nd_cache.insert((tx + dx, ty + dy));
                }
            }
        }
        self.nd_version = Some(self.grid.version);
        &self.nd_cache
    }

    pub fn can_deploy(&mut self, x: f64, y: f64) -> bool {
        let world = self.catalog.world as f64;
        if !(0.0 <= x && x < world && 0.0 <= y && y < world) {
            return false;
        }
        !self.live_no_deploy().contains(&(x as i32, y as i32))
    }

    pub fn deploy_tiles(&mut self) -> &[(f64, f64)] {
        if self.dt_version == Some(self.grid.version) {
            return &self.dt_cache;
        }
        self.live_no_deploy();
        self.dt_cache.clear();
        for x in 0..self.catalog.world as i32 {
            for y in 0..self.catalog.world as i32 {
                if !self.nd_cache.contains(&(x, y)) {
                    self.dt_cache.push((x as f64 + 0.5, y as f64 + 0.5));
                }
            }
        }
        self.dt_version = Some(self.grid.version);
        &self.dt_cache
    }

    // battle.py:409-424: walls, rather than red-line occupancy, enclose holes.
    pub fn inside_spots(&mut self) -> Vec<(f64, f64)> {
        use std::collections::HashSet;
        self.live_no_deploy();
        let world = self.catalog.world as i32;
        let walls: HashSet<_> = self.walls.iter().filter(|w| w.alive).map(|w| (w.tx, w.ty)).collect();
        let mut queue = Vec::new();
        for i in 0..world {
            for j in [0, world - 1] { queue.push((i, j)); }
        }
        for i in 0..world {
            for j in [0, world - 1] { queue.push((j, i)); }
        }
        let mut seen: HashSet<_> = queue.iter().copied().collect();
        while let Some((x, y)) = queue.pop() {
            for (dx, dy) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
                let next = (x + dx, y + dy);
                if 0 <= next.0 && next.0 < world && 0 <= next.1 && next.1 < world
                    && !walls.contains(&next) && !seen.contains(&next) {
                    seen.insert(next);
                    queue.push(next);
                }
            }
        }
        let mut spots = Vec::new();
        for x in 0..world {
            for y in 0..world {
                let tile = (x, y);
                if !seen.contains(&tile) && !self.nd_cache.contains(&tile) && !walls.contains(&tile) {
                    spots.push((x as f64 + 0.5, y as f64 + 0.5));
                }
            }
        }
        spots
    }

    // battle.py:427-455. Catalog summon_spec already includes heroes.summon_spec.
    pub fn spawn(
        &mut self,
        name: &str,
        team: Team,
        x: f64,
        y: f64,
        options: SpawnOptions,
    ) -> UnitRef {
        let town_hall = options.town_hall.filter(|th| *th != 0).unwrap_or(self.town_hall);
        let level = options.level.unwrap_or_else(|| {
            Level::Int(self.catalog.stats.max_level(name, town_hall).filter(|lv| *lv != 0).unwrap_or(1))
        });
        let nums = self.catalog.numbers(name, &level).clone();
        let spec = self.catalog.unit(name).summon_spec.clone();
        self.uid += 1;
        let mut facing = (self.catalog.world as f64 / 2.0 - x,
            self.catalog.world as f64 / 2.0 - y);
        if facing == (0.0, 0.0) {
            facing = (1.0, 0.0);
        }
        let is_hero = options.kind == "hero" || options.kind == "hero_clone";
        let unit = Unit {
            id: UnitId(self.uid),
            name: name.to_owned(),
            kind: options.kind,
            team,
            level: Some(level),
            x,
            y,
            hp: nums.hp,
            max_hp: nums.hp,
            base_max_hp: nums.hp,
            dmg: nums.dmg,
            interval: nums.interval,
            range: nums.range,
            speed: nums.speed,
            housing: nums.housing,
            flying: nums.flying || spec.walls == "fly",
            hits_air: nums.hits_air,
            hits_ground: nums.hits_ground,
            spec,
            alive: true,
            cooldown: 0.0,
            target: None,
            target_kind: None,
            wall_target: None,
            group: options.group,
            spawned_at: self.t,
            active_at: self.t,
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
            is_hero,
            kit: None,
            pet: None,
            owner: options.owner,
            follow: None,
            home: None,
            leash: 0.0,
            ability_used: false,
            decay: 0.0,
            dash: None,
            extra: UnitExtra {
                facing,
                ..UnitExtra::default()
            },
            damage_dealt: 0.0,
            in_pool: true,
        };
        let reference = unit.reference();
        let pool = match team {
            Team::Atk => &mut self.attackers,
            Team::Def => &mut self.defenders,
        };
        self.unit_indices.insert(unit.id, (team, pool.len()));
        pool.push(unit);
        if team == Team::Atk {
            self.attacker_order.push(reference);
        }
        units::on_spawn(self, reference);
        if team == Team::Atk {
            heroes::new_member(self, reference);
        }
        if let Some(owner) = options.owner {
            units::inherit_clone(self, owner, reference);
        }
        reference
    }

    pub fn deploy(&mut self, mut deployment: Deployment) -> UnitRef {
        // battle.py:458-462: stable min retains x-major tile order on ties.
        if !self.can_deploy(deployment.x, deployment.y) {
            let mut best = None;
            let mut best_distance = f64::INFINITY;
            for &(x, y) in self.deploy_tiles() {
                // Python `** 2` is the C runtime's pow, which differs from
                // dx * dx in the last bit for some inputs (geom::py_pow).
                let distance = geom::py_pow(x - deployment.x, 2.0) + geom::py_pow(y - deployment.y, 2.0);
                if best.is_none() || distance < best_distance {
                    best = Some((x, y));
                    best_distance = distance;
                }
            }
            let (x, y) = best.expect("no legal deployment tile");
            deployment.x = x;
            deployment.y = y;
        }
        self.start_battle();
        if self.first_deploy_t.is_none() {
            self.first_deploy_t = Some(self.t);
        }
        let record_kind = self.catalog.stats.record(&deployment.name).at("kind").str().to_owned();
        let kind = match record_kind.as_str() {
            "hero" => "hero",
            "siege" => "siege",
            _ => "troop",
        };
        let reference = self.spawn(
            &deployment.name,
            Team::Atk,
            deployment.x,
            deployment.y,
            SpawnOptions {
                level: deployment.level.clone(),
                kind: kind.to_owned(),
                group: deployment.group.clone(),
                owner: None,
                town_hall: deployment.town_hall,
            },
        );
        let strength = self.plan.strength();
        let default_mode = match &self.plan {
            Plan::Playbook(p) if !p.attack.ground => "air",
            _ => "ground",
        };
        let unit = self.unit_mut(reference);
        // battle.py:469-480: Stage's default Warden mode is ground.
        if unit.name == "Grand Warden" {
            let mode = deployment.mode.as_deref().unwrap_or(default_mode);
            assert!(mode == "air" || mode == "ground", "Grand Warden mode must be air or ground");
            unit.flying = mode == "air";
        }
        if strength != 1.0 {
            unit.hp *= strength;
            unit.max_hp *= strength;
            unit.base_max_hp *= strength;
            unit.dmg *= strength;
        }
        if unit.is_hero {
            heroes::equip(self, reference);
            let multiplier = self.atk_hero_mult;
            if multiplier != 1.0 {
                let unit = self.unit_mut(reference);
                unit.hp *= multiplier;
                unit.max_hp *= multiplier;
                unit.base_max_hp *= multiplier;
                unit.dmg *= multiplier;
            }
        }
        let unit = self.unit_mut(reference);
        let is_hero = unit.is_hero;
        let housing = unit.housing;
        unit.extra.deployment_source = Some(deployment.source.clone());
        let activation_housing = if is_hero {
            25
        } else if kind == "siege" {
            1
        } else {
            housing
        };
        // battle.py:489-512: direct CC troops contribute no activation housing.
        if deployment.source != "cc" && deployment.source != "clan_castle" {
            self.deployed_housing += activation_housing;
        }
        if deployment.source == "army" && ["troop", "hero", "siege"].contains(&record_kind.as_str()) {
            self.monolith_housing += activation_housing;
        }
        self.log_event(vec![
            LogValue::Float(round_decimal(self.t, 1)),
            LogValue::from("deploy"),
            LogValue::from(deployment.name),
            LogValue::Float(round_decimal(deployment.x, 1)),
            LogValue::Float(round_decimal(deployment.y, 1)),
        ]);
        reference
    }

    // battle.py:787-810: Stage needs no plan validation.
    pub fn start_battle(&mut self) {
        assert!(!self.ended, "Battle has ended");
        self.scouting = false;
    }

    pub fn end_battle(&mut self) {
        self.ended = true;
    }

    pub fn run(&mut self) -> BattleResult {
        while !self.ended && (self.scouting || self.t < self.max_time) {
            self.step();
            if self.scouting {
                continue;
            }
            if self.destroyed_counted >= self.total_counted || self.offense_finished() {
                break;
            }
        }
        self.ended = true;
        self.result()
    }

    pub fn offense_finished(&self) -> bool {
        // battle.py:821-855: Stage has no spell inventory or deferred callbacks.
        if self.attackers_pool().any(|unit| unit.alive
            && !["Healer", "Unicorn", "Totem"].contains(&unit.name.as_str())
            && unit.kind != "siege_idle") {
            return false;
        }
        if self.deployments[self.next_deploy..].iter().any(|d| d.name != "Healer")
            || match &self.plan {
                Plan::Playbook(p) => p.has_offensive_pending(self),
                Plan::Stage { .. } => self.plan.has_pending(),
            } {
            return false;
        }
        if !self.fast_end {
            if let Plan::Playbook(p) = &self.plan {
                if crate::plans::count(&p.attack.spells, "lightning") != 0
                    || crate::plans::count(&p.attack.spells, "eq") != 0 {
                    return false;
                }
            }
        }
        if self.pending.iter().any(|pending| matches!(pending.actor,
            Some(EntityRef::Unit(UnitRef {
                team: Team::Atk,
                ..
            })))) {
            return false;
        }
        !self.fields.iter().any(|field| ["lightning", "quake", "revive_cast", "revive_due",
            "summon", "santa", "birthday"].contains(&field.kind.as_str()))
    }

    pub fn result(&mut self) -> BattleResult {
        // battle.py:872-890: result() itself can append the onboard cargo event.
        if self.record && !self.onboard_cargo.is_empty() {
            let cargo = self.onboard_cargo.iter().map(|entry| {
                let level = match &entry.level {
                    Level::Int(level) => LogValue::Int(*level),
                    Level::Text(level) => LogValue::from(level.clone()),
                };
                let mut row = vec![
                    ("name".to_owned(), LogValue::from(entry.name.clone())),
                    ("level".to_owned(), level),
                    ("source".to_owned(), LogValue::from(entry.source.clone())),
                ];
                row.extend(entry.unknown.iter().map(|(key, value)|
                    (key.clone(), exported_value(self, value))));
                LogValue::Map(row)
            }).collect();
            self.log_event(vec![LogValue::Float(round_decimal(self.t, 1)),
                LogValue::from("onboard_cc"), LogValue::List(cargo)]);
        }
        let mut destroyed: Vec<(String, usize)> = Vec::new();
        let mut surviving = Vec::new();
        for building in &self.buildings {
            if building.counted && !building.alive {
                if let Some((_, count)) = destroyed.iter_mut().find(|(key, _)| *key == building.key) {
                    *count += 1;
                } else {
                    destroyed.push((building.key.clone(), 1));
                }
            }
            if building.alive && building.is_defense {
                surviving.push(building.key.clone());
            }
        }
        BattleResult {
            stars: self.stars(),
            destruction: self.destruction(),
            th_destroyed: self.th.is_some_and(|id| !self.building(id).alive),
            time: round_decimal(self.t, 1),
            destroyed_keys: destroyed,
            surviving_defenses: surviving,
            units_left: self.attackers_pool().filter(|unit| unit.alive).count(),
            log: self.log.clone(),
        }
    }

    // battle.py:893-950: retain exact subsystem order and snapshot iteration.
    pub fn step(&mut self) {
        if self.ended || self.t >= self.max_time {
            return;
        }
        if self.scouting {
            self.scout_time = SCOUT_TIME.min(self.scout_time + self.dt);
            if self.scout_time >= SCOUT_TIME {
                self.start_battle();
            }
            return;
        }
        let t = self.t;
        while self.next_deploy < self.deployments.len()
            && self.deployments[self.next_deploy].time <= t {
            self.deploy(self.deployments[self.next_deploy].clone());
            self.next_deploy += 1;
        }
        self.rebuild_buckets();
        self.plan_on_tick();
        if self.ended {
            return;
        }
        self.src_obj = None;
        self.src = "spell".to_owned();
        self.effect = "spell".to_owned();
        spells::tick(self);
        self.resolve_pending();
        self.src = "trap".to_owned();
        self.src_obj = None;
        self.effect = "trap".to_owned();
        traps::tick(self);
        self.castle();
        heroes::guardians_tick(self);
        defense::bell_tick(self);
        defense::builders_tick(self);
        let attackers: Vec<_> = self.attackers_pool().map(Unit::reference).collect();
        for reference in attackers {
            if self.unit(reference).alive {
                effects::damage_source(self, Some(EntityRef::Unit(reference)), "attack", |battle| {
                    battle.act_attacker(reference);
                });
            }
        }
        self.separate();
        for index in 0..self.buildings.len() {
            let building = &self.buildings[index];
            if building.alive && building.weapon.is_some() {
                let id = building.id;
                self.src = building.key.clone();
                effects::damage_source(self, Some(EntityRef::Building(id)), "attack", |battle| {
                    defense::act(battle, id);
                });
            }
        }
        let defenders: Vec<_> = self.defenders_pool().map(Unit::reference).collect();
        for reference in defenders {
            let unit = self.unit(reference);
            if unit.alive {
                self.src = format!("unit:{}", unit.name);
                effects::damage_source(self, Some(EntityRef::Unit(reference)), "attack", |battle| {
                    battle.act_defender(reference);
                });
            }
        }
        self.src_obj = None;
        if round_half_even(t * 10.0) as i64 % 50 == 0 {
            self.grid.prune();
        }
        // battle.py:940-947: retire list membership without invalidating ids.
        if self.attackers_pool().count() > 160 {
            for unit in &mut self.attackers {
                if unit.in_pool && !unit.alive && !unit.is_hero && unit.extra.recalled.is_none() {
                    unit.in_pool = false;
                }
            }
        }
        if self.defenders_pool().count() > 80 {
            for unit in &mut self.defenders {
                if unit.in_pool && !unit.alive {
                    unit.in_pool = false;
                }
            }
        }
        if self.record && round_half_even(t * 10.0) as i64 % 5 == 0 {
            self.frames.push(self.snapshot());
        }
        self.t = round6(t + self.dt);
    }

    fn plan_on_tick(&mut self) {
        if let Plan::Playbook(plan) = &self.plan {
            // Runtime helpers need &mut Battle while deploy/equip read immutable
            // plan configuration. Keep that configuration in Battle throughout.
            let mut running = (**plan).clone();
            running.on_tick(self);
            running.attack.cc_released |= self.plan.cc_released();
            self.plan = Plan::Playbook(Box::new(running));
        }
    }

    // battle.py:952-958: frames are independent of the per-tick trace.
    fn snapshot(&self) -> Snapshot {
        Snapshot {
            t: round_decimal(self.t, 1),
            units: self.attackers_pool().chain(self.defenders_pool()).filter(|unit| unit.alive)
                .map(|unit| SnapshotUnit {
                    name: unit.name.clone(),
                    x: round_decimal(unit.x, 2),
                    y: round_decimal(unit.y, 2),
                    hp_fraction: round_decimal(unit.hp / 1.0_f64.max(unit.max_hp), 2),
                    team: unit.team,
                }).collect(),
            dead: self.buildings.iter().filter(|b| !b.alive && b.key != "banner")
                .map(|b| b.id).collect(),
            walls: self.walls.iter().filter(|w| !w.alive).map(|w| (w.tx, w.ty)).collect(),
        }
    }
}
