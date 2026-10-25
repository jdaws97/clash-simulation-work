//! Ports committed plans.py:199-327,766-1523,1877-2070,2281-2469.
//! Scouting is deterministic; caches retain the reference's complete score keys.

use super::*;
use std::cell::Cell;
use crate::catalog::game_float;
use crate::grid::RES;

pub type Band = (f64, f64, f64, f64, f64);
pub type Cluster = (f64, f64, f64, usize);

#[derive(Clone, Debug, PartialEq)]
pub struct ClusterEffect {
    pub kind: String,
    pub radius: f64,
    pub damage: f64,
}

impl ClusterEffect {
    fn new(kind: &str, radius: f64, damage: f64) -> Self {
        Self {
            kind: kind.to_owned(),
            radius,
            damage,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
struct ScoreKey {
    effects: Vec<ClusterEffect>,
    points: Vec<(f64, f64)>,
    min_kills: usize,
    band: Option<Band>,
    hp: Option<Vec<f64>>,
    eq_hits: Option<Vec<usize>>,
}

#[derive(Default)]
pub struct ClusterCache {
    version: Option<(f64, Vec<(BuildingId, f64, usize)>)>,
    points: Vec<((Option<(f64, f64)>, Option<f64>), Vec<(f64, f64)>)>,
    scores: Vec<(ScoreKey, Option<Cluster>)>,
}

#[derive(Clone, Debug)]
pub struct DefenseSnipe {
    pub target: BuildingId,
    pub tool: String,
    pub kind: String,
    pub x: f64,
    pub y: f64,
    pub value: f64,
    pub seconds: f64,
    pub cost: f64,
    pub damage: Vec<(BuildingId, f64)>,
    pub casts: i64,
    pub confidence: f64,
}

impl DefenseSnipe {
    pub fn load(value: &Json) -> Self {
        Self {
            target: BuildingId(value.at("target").at("$building").usize()),
            tool: value.at("tool").str().to_owned(),
            kind: value.at("kind").str().to_owned(),
            x: value.at("x").f64(),
            y: value.at("y").f64(),
            value: value.at("value").f64(),
            seconds: number(value, "seconds", 0.0),
            cost: number(value, "cost", 0.0),
            damage: value
                .at("damage")
                .obj()
                .iter()
                .map(|(id, damage)| {
                    (
                        BuildingId(id.parse().expect("snipe building id")),
                        damage.f64(),
                    )
                })
                .collect(),
            casts: number(value, "casts", 0.0) as i64,
            confidence: number(value, "confidence", 1.0),
        }
    }
}

// Playbook overrides are captured from the current steps, never from scout RNG.
#[derive(Clone, Debug, Default)]
pub struct ScoutingContext {
    pub inventory: Vec<(String, i64)>,
    pub unavailable: Vec<String>,
    pub roles: Vec<(String, String)>,
    pub reservations: Vec<(String, i64)>,
    pub pending_spells: Vec<(String, i64)>,
    pub pending_heroes: Vec<String>,
    pub reserve_lightning: bool,
    pub used_spell_reservations: Cell<bool>,
}

pub fn band_hit(building: &Building, band: Band, kind: &str, radius: f64) -> bool {
    let (x, y, dx, dy, length) = band;
    let along = (building.x - x) * dx + (building.y - y) * dy;
    if kind == "arrow" {
        let off = ((building.x - x) * dy - (building.y - y) * dx).abs();
        return 0.0 < along && along < length && off <= building.half_hit + radius;
    }
    let along = length.min(0.0_f64.max(along));
    if building.edge_distance(x + dx * along, y + dy * along) <= radius {
        return true;
    }
    for offset_x in [-building.half_hit, building.half_hit] {
        for offset_y in [-building.half_hit, building.half_hit] {
            let along = (building.x + offset_x - x) * dx
                + (building.y + offset_y - y) * dy;
            let along = length.min(0.0_f64.max(along));
            if building.edge_distance(x + dx * along, y + dy * along) <= radius {
                return true;
            }
        }
    }
    false
}

fn storage(key: &str) -> bool {
    matches!(key, "gs" | "es" | "ds")
}

impl AttackPlan {
    pub fn defense_cluster(
        &self,
        battle: &mut Battle,
        effects: &[ClusterEffect],
        hp: Option<&[(BuildingId, f64)]>,
        eq_hits: Option<&[(BuildingId, usize)]>,
        points: Option<&[(f64, f64)]>,
        min_kills: usize,
        band: Option<Band>,
        mut center: Option<(f64, f64)>,
        mut reach: Option<f64>,
    ) -> Option<Cluster> {
        let defenses: Vec<_> = battle
            .buildings
            .iter()
            .filter(|b| {
                b.is_defense
                    && battle.building_targetable(b.id)
                    && !self.snipe_claimed.contains(&b.id)
                    && hp.is_none_or(|hp| lookup(hp, b.id, b.hp) > 1e-9)
            })
            .map(|b| b.id)
            .collect();
        if defenses.is_empty() || effects.is_empty() {
            return None;
        }
        let version = (
            battle.t,
            defenses
                .iter()
                .map(|id| {
                    let b = battle.building(*id);
                    (*id, b.hp, b.eq_hits)
                })
                .collect(),
        );
        if battle.cluster_cache.version.as_ref() != Some(&version) {
            battle.cluster_cache = ClusterCache {
                version: Some(version),
                ..ClusterCache::default()
            };
        }
        let points = if let Some(points) = points {
            points.to_vec()
        } else {
            if center.is_none() {
                // The reference includes pets/Totems here if their group is main.
                let army: Vec<_> = battle
                    .attackers_pool()
                    .filter(|u| u.alive && u.group == "main")
                    .map(Unit::reference)
                    .collect();
                if !army.is_empty() {
                    center = Some(centroid(battle, &army));
                    reach = Some(18.0);
                }
            }
            let key = (center, reach);
            if let Some((_, points)) = battle
                .cluster_cache
                .points
                .iter()
                .find(|(k, _)| *k == key)
            {
                points.clone()
            } else {
                let mut nearby: Vec<_> = defenses
                    .iter()
                    .copied()
                    .filter(|id| match (center, reach) {
                        (Some((x, y)), Some(reach)) => {
                            battle.building(*id).edge_distance(x, y) <= reach
                        }
                        _ => true,
                    })
                    .collect();
                nearby.sort_by(|a, b| {
                    threat(&battle.building(*b).key, 1.0)
                        .total_cmp(&threat(&battle.building(*a).key, 1.0))
                });
                let points: Vec<_> = nearby
                    .into_iter()
                    .take(24)
                    .map(|id| {
                        let b = battle.building(id);
                        (b.x, b.y)
                    })
                    .collect();
                battle.cluster_cache.points.push((key, points.clone()));
                points
            }
        };
        let key = ScoreKey {
            effects: effects.to_vec(),
            points: points.clone(),
            min_kills,
            band,
            hp: hp.map(|hp| {
                defenses
                    .iter()
                    .map(|id| lookup(hp, *id, battle.building(*id).hp))
                    .collect()
            }),
            eq_hits: eq_hits.map(|hits| {
                defenses
                    .iter()
                    .map(|id| lookup(hits, *id, battle.building(*id).eq_hits))
                    .collect()
            }),
        };
        if let Some((_, result)) = battle.cluster_cache.scores.iter().find(|(k, _)| *k == key) {
            return *result;
        }
        let mut best: Option<Cluster> = None;
        for (x, y) in points {
            let mut score = 0.0;
            let mut kills = 0;
            for id in &defenses {
                let b = battle.building(*id);
                let remaining = hp.map_or(b.hp, |hp| lookup(hp, *id, b.hp));
                let mut damage = 0.0;
                let mut quakes = eq_hits.map_or(b.eq_hits, |hits| lookup(hits, *id, b.eq_hits));
                for effect in effects {
                    let kind = effect.kind.as_str();
                    if matches!(kind, "arrow" | "dash") {
                        if band_hit(b, band.expect("line scoring band"), kind, effect.radius) {
                            let multiplier = if kind == "arrow" && b.key == "ad" {
                                2.0
                            } else {
                                1.0
                            };
                            damage += effect.damage * multiplier;
                        }
                        continue;
                    } else if b.edge_distance(x, y) > effect.radius {
                        continue;
                    }
                    if kind == "lightning"
                        && (storage(&b.key) || matches!(b.key.as_str(), "th" | "cc"))
                    {
                        continue;
                    }
                    if kind == "quake" {
                        damage += b.max_hp * effect.damage / (2 * quakes + 1) as f64;
                        quakes += 1;
                    } else {
                        damage += effect.damage;
                    }
                }
                score += threat(&b.key, 1.0) * 1.0_f64.min(damage / remaining);
                if damage >= remaining - 1e-9 {
                    kills += 1;
                }
            }
            if score > 0.0 && kills >= min_kills && best.is_none_or(|best| score > best.2) {
                best = Some((x, y, score, kills));
            }
        }
        battle.cluster_cache.scores.push((key, best));
        best
    }

    pub fn charge_point(&self, battle: &mut Battle, angle: f64, lateral: f64) -> (f64, f64) {
        let center = battle.catalog.world as f64 / 2.0;
        let origin = edge_point(battle, angle, lateral);
        let direction = py_atan2(origin.1 - center, origin.0 - center);
        let buildings: Vec<_> = battle.buildings.iter().map(|b| b.id).collect();
        let mut candidates = Vec::new();
        for id in buildings {
            let b = battle.building(id);
            if !b.is_defense || !battle.building_targetable(id) {
                continue;
            }
            let bearing = py_atan2(b.y - center, b.x - center);
            if py_cos(bearing - direction) < py_cos(std::f64::consts::PI / 4.0) {
                continue;
            }
            let (x, y) = edge_point(battle, bearing, lateral);
            let b = battle.building(id);
            if b.edge_distance(x, y) <= 12.0 {
                candidates.push((b.x, b.y));
            }
        }
        let effects = [ClusterEffect::new("damage", 6.0, f64::INFINITY)];
        let cluster = self.defense_cluster(
            battle,
            &effects,
            None,
            None,
            Some(&candidates),
            0,
            None,
            None,
            None,
        );
        match cluster {
            Some(cluster) => edge_point(
                battle,
                py_atan2(cluster.1 - center, cluster.0 - center),
                lateral,
            ),
            None => edge_point(battle, angle, lateral),
        }
    }

    fn snipe_loadout(&self, battle: &Battle, name: &str) -> HeroLoadout {
        self.loadouts
            .iter()
            .find(|(hero, _)| hero == name)
            .map(|(_, loadout)| loadout.clone())
            .unwrap_or_else(|| heroes::default_loadout(battle, name).expect("default hero loadout"))
    }

    fn owned(&self, name: &str) -> bool {
        !self.account_equipment || self.equipment_levels.iter().any(|(item, _)| item == name)
    }

    fn equipment_level(&self, battle: &Battle, name: &str) -> Level {
        self.equipment_levels
            .iter()
            .find(|(item, _)| item == name)
            .and_then(|(_, level)| level.clone())
            .filter(level_truth)
            .unwrap_or_else(|| {
                Level::Int(
                    battle.catalog.stats.max_level(name, self.town_hall)
                        .expect("equipment max level"),
                )
            })
    }

    pub fn has_backpack(&self, battle: &Battle) -> bool {
        self.snipe_loadout(battle, "Dragon Duke")
            .equipment
            .iter()
            .any(|item| item == "Rocket Backpack")
            && self.owned("Rocket Backpack")
    }

    pub fn backpack_point(&self, battle: &mut Battle, angle: f64, lateral: f64) -> (f64, f64) {
        let level = self.equipment_level(battle, "Rocket Backpack");
        let damage = game_float(
            battle.catalog.equipment_ability("Rocket Backpack", &level),
            "ActAsPenetratingDamage",
        );
        let point = edge_point(battle, angle, lateral);
        let mut best: Option<Cluster> = None;
        for index in 0..360 {
            let (x, y) = if index == 0 {
                point
            } else {
                edge_point(
                    battle,
                    angle + index as f64 * (std::f64::consts::PI / 180.0),
                    0.0,
                )
            };
            if !battle.can_deploy(x, y) {
                continue;
            }
            let (dx, dy, length, radius) = heroes::dash_geometry(battle, x, y, (1.0, 0.0));
            let effect = [ClusterEffect::new("dash", radius, damage)];
            let candidate = self.defense_cluster(
                battle,
                &effect,
                None,
                None,
                Some(&[(x, y)]),
                0,
                Some((x, y, dx, dy, length)),
                None,
                None,
            );
            if let Some(candidate) = candidate {
                if best.is_none_or(|best| candidate.2 > best.2) {
                    best = Some(candidate);
                }
            }
        }
        best.map_or(point, |best| (best.0, best.1))
    }
}

fn lookup<T: Copy>(items: &[(BuildingId, T)], id: BuildingId, default: T) -> T {
    items.iter().find(|(key, _)| *key == id).map_or(default, |(_, value)| *value)
}

fn level_truth(level: &Level) -> bool {
    match level {
        Level::Int(value) => *value != 0,
        Level::Text(value) => !value.is_empty(),
    }
}

impl AttackPlan {
    pub fn cluster_effects(&self, battle: &Battle, kind: &str, mut count: i64) -> Vec<ClusterEffect> {
        let mut effects = Vec::new();
        for stock in &self.stock {
            if stock.name != spell_name(kind) || stock.remaining <= 0 {
                continue;
            }
            let level = stock.level.as_ref().expect("resolved spell stock level");
            let radius = battle.catalog.resolved.at("zap_radii")
                .at(&format!("{}|{level}", stock.name)).f64();
            let value = if kind == "eq" {
                battle.catalog.stats.get(&stock.name, level, &["Building Damage %"], None).expect("quake damage") / 100.0
            } else {
                battle.catalog.stats.get(&stock.name, level, &["damage", "Damage"], None).expect("spell damage")
            };
            let take = count.min(stock.remaining);
            for _ in 0..take {
                effects.push(ClusterEffect::new(if kind == "eq" { "quake" } else { kind }, radius, value));
            }
            count -= take;
            if count == 0 {
                break;
            }
        }
        effects
    }

    pub fn unreserved_spells(&self, kind: &str, fallback: bool) -> i64 {
        let mut available = count(&self.spells, kind);
        if fallback {
            if let Some(context) = &self.scouting_context {
                context.used_spell_reservations.set(true);
                if available <= count(&context.reservations, kind) {
                    return 0;
                }
                available -= count(&context.pending_spells, kind);
            }
        }
        available.max(0)
    }

    pub fn cluster_state(
        &self,
        battle: &Battle,
    ) -> (Vec<(BuildingId, f64)>, Vec<(BuildingId, usize)>) {
        let mut targets: Vec<_> = battle
            .buildings
            .iter()
            .filter(|b| b.alive)
            .map(|b| ZapTarget {
                id: b.id,
                hp: b.hp,
                eq_hits: b.eq_hits,
            })
            .collect();
        let mut casts = Vec::new();
        for pending in &battle.pending {
            if let Some(shared) = &pending.extra.quake {
                let field = shared.borrow();
                if field.kind == Tag::Quake {
                    account_cluster(
                        battle,
                        &field,
                        1.0,
                        ZapCast::Pending(Rc::as_ptr(shared) as usize),
                        &mut targets,
                        &mut casts,
                    );
                }
            }
        }
        for (index, field) in battle.fields.iter().enumerate() {
            if matches!(field.kind, Tag::Lightning | Tag::Quake) {
                let hits = if field.kind == Tag::Quake { 5.0 } else { 1.0 };
                account_cluster(
                    battle,
                    field,
                    hits,
                    ZapCast::Field(index),
                    &mut targets,
                    &mut casts,
                );
            }
        }
        let hp = targets
            .iter()
            .map(|target| {
                let hp = if self.snipe_claimed.contains(&target.id) {
                    0.0
                } else {
                    target.hp
                };
                (target.id, hp)
            })
            .collect();
        let hits = targets.iter().map(|target| (target.id, target.eq_hits)).collect();
        (hp, hits)
    }

    fn spare_quakes(&self, battle: &Battle) -> i64 {
        let available = self.unreserved_spells("eq", self.fallback);
        let mut reserved = self.fallback_quakes.len() as i64;
        if self.ground && !self.allowed_spell("jump") && battle.walls.iter().any(|w| w.alive)
            && count(&self.spells, "eq") >= 4
        {
            reserved = reserved.max(4);
        }
        if self.p("eq_core_dist") > 2.0 && self.last("eq_core") < 0.0 {
            reserved = reserved.max(round_half_even(self.p("eq_core_n")) as i64);
        }
        (available - reserved).max(0)
    }

    fn allowed_spell(&self, kind: &str) -> bool {
        if self.fallback {
            if let Some(context) = &self.scouting_context {
                context.used_spell_reservations.set(true);
                return count(&self.spells, kind) > count(&context.reservations, kind);
            }
        }
        self.have(kind)
    }

    fn hold_line_quake(&self, battle: &Battle) -> bool {
        for (name, equipment) in [("Archer Queen", "Giant Arrow"), ("Dragon Duke", "Rocket Backpack")] {
            let deployed: Vec<_> = battle.attackers_pool().filter(|u| u.name == name && u.kind != Tag::HeroClone).collect();
            if !deployed.is_empty() {
                if deployed.iter().any(|u| u.alive && !u.ability_used
                    && u.kit.as_ref().is_some_and(|kit| kit.has(equipment))
                    && u.extra.line_quake_until.is_none())
                {
                    return true;
                }
                continue;
            }
            if !self.snipe_loadout(battle, name).equipment.iter().any(|item| item == equipment)
                || !self.owned(equipment)
            {
                continue;
            }
            let pending = self.scouting_context.as_ref().map_or_else(|| {
                self.push_heroes.iter().any(|hero| hero == name)
                    || self.funnel_heroes.iter().any(|(hero, _)| hero == name)
                    || self.charge_hero.as_deref() == Some(name)
            }, |context| context.pending_heroes.iter().any(|hero| hero == name));
            if pending {
                return true;
            }
        }
        false
    }

    pub fn spare_lightning_cluster(&mut self, battle: &mut Battle) -> bool {
        if !self.cluster_casts.is_empty() {
            let (kind, x, y) = self.cluster_casts.remove(0);
            let effects = if self.allowed_spell(&kind) {
                self.cluster_effects(battle, &kind, 1)
            } else {
                Vec::new()
            };
            let cluster = if effects.is_empty() {
                None
            } else {
                self.defense_cluster(
                    battle, &effects, None, None, Some(&[(x, y)]), 0, None, None, None,
                )
            };
            if cluster.is_some() {
                self.use_spell(battle, &kind, x, y);
                return true;
            }
            self.cluster_casts.clear();
        }
        let available = self.unreserved_spells("lightning", self.fallback);
        if available == 0 {
            return false;
        }
        let (hp, eq_hits) = self.cluster_state(battle);
        if battle.buildings.iter().any(|b| b.alive && b.key == "ad" && lookup(&hp, b.id, 0.0) > 1e-9) {
            return false;
        }
        let effects = self.cluster_effects(battle, "lightning", available);
        let mut combo: Option<(Cluster, usize)> = None;
        if available >= 2 && self.spare_quakes(battle) > i64::from(self.hold_line_quake(battle)) {
            let quake = self.cluster_effects(battle, "eq", 1);
            for count in [2, 3] {
                if count > available as usize {
                    break;
                }
                let mut combined = quake.clone();
                combined.extend_from_slice(&effects[..count.min(effects.len())]);
                let candidate = self.defense_cluster(
                    battle, &combined, Some(&hp), Some(&eq_hits), None, 2, None, None, None,
                );
                if let Some(candidate) = candidate {
                    if combo.is_none_or(|(cluster, _)| candidate.2 > cluster.2) {
                        combo = Some((candidate, count));
                    }
                }
            }
        }
        if let Some((cluster, count)) = combo {
            self.cluster_casts = vec![("lightning".to_owned(), cluster.0, cluster.1); count].into();
            self.use_spell(battle, "eq", cluster.0, cluster.1);
            return true;
        }
        let Some(cluster) = self.defense_cluster(battle, &effects, Some(&hp), Some(&eq_hits), None, 0, None, None, None) else {
            return false;
        };
        self.use_spell(battle, "lightning", cluster.0, cluster.1);
        true
    }

    pub fn spare_quake(&mut self, battle: &mut Battle) -> bool {
        let available = self.spare_quakes(battle);
        if available <= i64::from(self.hold_line_quake(battle)) {
            return false;
        }
        let (hp, hits) = self.cluster_state(battle);
        let effects = self.cluster_effects(battle, "eq", available);
        let Some(cluster) = self.defense_cluster(battle, &effects, Some(&hp), Some(&hits), None, 0, None, None, None) else {
            return false;
        };
        self.use_spell(battle, "eq", cluster.0, cluster.1);
        true
    }

    pub fn ability_band(&self, battle: &Battle, hero: UnitRef) -> Option<(Band, ClusterEffect)> {
        let u = battle.unit(hero);
        let kit = u.kit.as_ref().expect("hero kit");
        let (kind, dx, dy, length, radius, damage) = if kit.has("Giant Arrow") {
            let target = u.target.filter(|target| battle.entity_alive(*target))?;
            match target {
                EntityRef::Building(id) if !battle.building_targetable(id) => return None,
                EntityRef::Unit(unit) if unit.team == Team::Def && !battle.unit(unit).targetable(battle) => return None,
                _ => {}
            }
            let (dx, dy, length, radius) = heroes::arrow_geometry(battle, hero, Some(target));
            let damage = game_float(battle.catalog.equipment_ability("Giant Arrow", kit.lv("Giant Arrow")), "Damage");
            ("arrow", dx, dy, length, radius, damage)
        } else if kit.has("Rocket Backpack") {
            let (dx, dy, length, radius) = heroes::dash_geometry(battle, u.x, u.y, u.extra.facing);
            let damage = game_float(
                battle.catalog.equipment_ability("Rocket Backpack", kit.lv("Rocket Backpack")),
                "ActAsPenetratingDamage",
            );
            ("dash", dx, dy, length, radius, damage)
        } else {
            return None;
        };
        Some(((u.x, u.y, dx, dy, length), ClusterEffect::new(kind, radius, damage)))
    }

    pub fn aim_cluster(&self, battle: &mut Battle, hero: UnitRef, kind: &str) -> bool {
        let Some((band, effect)) = self.ability_band(battle, hero) else {
            return false;
        };
        self.defense_cluster(battle, &[effect], None, None, Some(&[(band.0, band.1)]), 0, Some(band), None, None)
            .is_some_and(|current| current.2 >= self.p(&format!("{kind}_threat")))
    }

    pub fn line_ability(
        &mut self,
        battle: &mut Battle,
        hero: UnitRef,
        force: bool,
        deadline: Option<f64>,
    ) -> bool {
        let t = battle.t;
        let since = *battle.unit_mut(hero).extra.line_ability_since.get_or_insert(t);
        let limit = deadline.map_or(since + 10.0, |deadline| (since + 10.0).min(deadline));
        let ready = battle.unit(hero).kit.as_ref().expect("hero kit").has("Rocket Backpack")
            || self.aim_cluster(battle, hero, "arrow");
        if force || ready || t >= limit {
            return self.fire_aimed(battle, hero, Some(limit));
        }
        false
    }

    pub fn fire_aimed(&mut self, battle: &mut Battle, hero: UnitRef, deadline: Option<f64>) -> bool {
        if self.pair_line_quake(battle, hero, deadline) {
            return false;
        }
        heroes::activate(battle, hero, false);
        true
    }

    fn pair_line_quake(&mut self, battle: &mut Battle, hero: UnitRef, deadline: Option<f64>) -> bool {
        if let Some(until) = battle.unit(hero).extra.line_quake_until {
            return battle.t < until && deadline.is_none_or(|deadline| battle.t < deadline);
        }
        let pace = crate::playbook::action_time(battle, crate::playbook::Action::Spell, 1);
        let wait = pace.max(spells::LAND_DELAY + 4.0 * 0.4);
        if deadline.is_some_and(|deadline| battle.t + wait > deadline) {
            return false;
        }
        let fallback = self.fallback;
        self.fallback = true;
        let spare = self.spare_quakes(battle);
        self.fallback = fallback;
        if spare == 0 {
            return false;
        }
        let Some((band, effect)) = self.ability_band(battle, hero) else {
            return false;
        };
        let (x, y, dx, dy, length) = band;
        let mut targets: Vec<_> = battle.buildings.iter().filter(|b| b.is_defense
            && battle.building_targetable(b.id) && band_hit(b, band, &effect.kind, effect.radius)).collect();
        targets.sort_by(|a, b| threat(&b.key, 1.0).total_cmp(&threat(&a.key, 1.0)));
        let mut points: Vec<_> = targets.into_iter().take(12).map(|b| {
            let along = length.min(0.0_f64.max((b.x - x) * dx + (b.y - y) * dy));
            (x + dx * along, y + dy * along)
        }).collect();
        let centers = points.clone();
        for (index, first) in centers.iter().enumerate() {
            for second in &centers[index + 1..] {
                if points.len() >= 24 {
                    break;
                }
                points.push(((first.0 + second.0) / 2.0, (first.1 + second.1) / 2.0));
            }
        }
        let (hp, hits) = self.cluster_state(battle);
        let mut effects = self.cluster_effects(battle, "eq", 1);
        effects.push(effect);
        let cluster = self.defense_cluster(
            battle, &effects, Some(&hp), Some(&hits), Some(&points), 0, Some(band), None, None,
        );
        let Some(cluster) = cluster else {
            return false;
        };
        self.use_spell(battle, "eq", cluster.0, cluster.1);
        battle.unit_mut(hero).extra.line_quake_until = Some(battle.t + wait);
        self.busy_until = self.busy_until.max(battle.t + pace);
        true
    }

    pub fn cluster_ability(&self, battle: &mut Battle, hero: UnitRef, force: bool) -> bool {
        let t = battle.t;
        let since = *battle.unit_mut(hero).extra.cluster_ability_since.get_or_insert(t);
        if force || t - since >= 10.0 {
            heroes::activate(battle, hero, false);
            return true;
        }
        if t < battle.unit(hero).extra.cluster_ability_check_at {
            return false;
        }
        battle.unit_mut(hero).extra.cluster_ability_check_at = t + 0.5;
        let u = battle.unit(hero);
        let kit = u.kit.as_ref().expect("hero kit");
        let (x, y) = (u.x, u.y);
        let (radius, damage, reach) = if kit.has("Fireball") {
            let radius = heroes::col(battle, "Fireball", kit.lv("Fireball"), &["damage radius"], 0.0);
            let damage = heroes::col(battle, "Fireball", kit.lv("Fireball"), &["projectile damage"], 0.0);
            (radius, damage, u.range + radius)
        } else if u.name_id == Name::RoyalChampion {
            let mut damage = 0.0;
            if kit.has("Rocket Spear") {
                damage += u.dmg
                    + heroes::col(
                        battle,
                        "Rocket Spear",
                        kit.lv("Rocket Spear"),
                        &["damage per shot increase"],
                        0.0,
                    ) * battle.atk_hero_mult;
            }
            if kit.has("Seeking Shield") {
                damage += heroes::col(
                    battle,
                    "Seeking Shield",
                    kit.lv("Seeking Shield"),
                    &["projectile damage"],
                    0.0,
                ) * battle.atk_hero_mult;
            }
            (6.0, damage, if kit.has("Rocket Spear") { heroes::spear_range(battle) } else { u.range + 6.0 })
        } else {
            return false;
        };
        let defenses = heroes::targets(battle, true);
        let nearest = defenses.into_iter().min_by(|a, b| {
            heroes::distance(battle, *a, x, y).total_cmp(&heroes::distance(battle, *b, x, y))
        });
        let Some(nearest) = nearest else {
            heroes::activate(battle, hero, false);
            return true;
        };
        let point = battle.entity_position(nearest);
        let effects = [ClusterEffect::new("damage", radius, damage)];
        let best = self.defense_cluster(battle, &effects, None, None, None, 0, None, Some((x, y)), Some(reach));
        let current = self.defense_cluster(battle, &effects, None, None, Some(&[point]), 0, None, None, None);
        let ready = best.zip(current).is_some_and(|(best, current)| current.2 >= best.2
            && heroes::distance(battle, nearest, x, y) <= reach);
        if force || ready || t - since >= 10.0 {
            heroes::activate(battle, hero, false);
            return true;
        }
        false
    }
}

fn account_cluster(
    battle: &Battle,
    field: &Field,
    hits: f64,
    cast: ZapCast,
    targets: &mut [ZapTarget],
    casts: &mut Vec<(ZapCast, BuildingId, usize)>,
) {
    for target in targets {
        let b = battle.building(target.id);
        if b.edge_distance(field.x, field.y) > field.radius {
            continue;
        }
        if field.kind == Tag::Lightning {
            if !storage(&b.key) && !matches!(b.key.as_str(), "th" | "cc") {
                target.hp -= field.value;
            }
        } else if b.counted && !storage(&b.key) {
            let n = if let Some((_, _, n)) = casts.iter().find(|(key, id, _)| *key == cast && *id == target.id) {
                *n
            } else {
                let n = field
                    .extra
                    .quake_hits
                    .iter()
                    .find(|(key, _)| *key == EntityRef::Building(target.id))
                    .map(|(_, n)| *n)
                    .unwrap_or_else(|| {
                        target.eq_hits += 1;
                        target.eq_hits
                    });
                casts.push((cast, target.id, n));
                n
            };
            target.hp -= b.max_hp * field.value * hits / (2 * n - 1) as f64;
        }
    }
}

impl AttackPlan {
    fn snipe_available(&self, name: &str) -> bool {
        if self.snipe_deployed.iter().any(|tool| tool == name) {
            return false;
        }
        if let Some(context) = &self.scouting_context {
            if context.unavailable.iter().any(|tool| tool == name) {
                return false;
            }
            if name == "Flame Flinger" {
                return self.siege.as_deref() == Some(name) && count(&context.inventory, name) > 0;
            }
        } else {
            if name == "Flame Flinger" {
                return self.siege.as_deref() == Some(name);
            }
            if self.charge_hero.as_deref() == Some(name) {
                return false;
            }
        }
        self.push_heroes.iter().any(|hero| hero == name)
            || self.funnel_heroes.iter().any(|(hero, _)| hero == name)
    }

    fn snipe_weights(&self, battle: &Battle) -> Vec<(BuildingId, f64)> {
        let troops: Vec<_> = self.scouting_context.as_ref().map_or_else(|| {
            let mut troops: Vec<_> = self.main.iter().chain(self.support.iter())
                .flat_map(|wave| wave.units.iter().cloned()).collect();
            troops.extend(self.flank.iter().map(|(name, count, _)| (name.clone(), *count)));
            troops.extend(self.cleanup.iter().cloned());
            troops
        }, |context| context.inventory.clone());
        let mut air = 0;
        let mut ground = 0;
        for (name, count) in troops {
            if name == "Healer" || text(battle.catalog.stats.record(&name), "kind", "") == "siege" {
                continue;
            }
            let attrs = battle.catalog.stats.attrs(&name);
            let housing = count * number(attrs, "housing", 0.0) as i64;
            if flag(attrs, "is_flying") {
                air += housing;
            } else {
                ground += housing;
            }
        }
        let air_army = air > ground;
        let healers = self.scouting_context.as_ref().map_or_else(|| {
            self.charge_n + self.main.iter().chain(self.support.iter())
                .flat_map(|wave| wave.units.iter()).filter(|(name, _)| name == "Healer")
                .map(|(_, count)| *count).sum::<i64>()
        }, |context| count(&context.inventory, "Healer"));
        // output/research/usage/hidden-tesla.md: concealed Teslas are not scouted.
        // https://clashofclans.fandom.com/wiki/Hidden_Tesla/Home_Village
        let others: Vec<_> = battle
            .buildings
            .iter()
            .filter(|b| b.key != "wall" && (b.key != "tesla" || b.revealed))
            .collect();
        battle.buildings.iter().map(|b| {
            let mut weight = threat(&b.key, 1.0);
            if air_army {
                weight *= match b.key.as_str() {
                    "ad" => 2.5,
                    "sweeper" => 3.0,
                    "eagle" | "scatter" => 1.25,
                    _ => 1.0,
                };
                if b.weapon.as_ref().is_some_and(|weapon| weapon.targets == Tag::Ground) {
                    weight *= 0.2;
                }
            } else if b.key == "ad" {
                weight *= if healers != 0 { 0.5 } else { 0.0 };
            } else if b.key == "sweeper" {
                weight = 0.0;
            }
            if healers >= 4 || self.charge_hero.is_some() {
                if b.key == "mono" {
                    weight *= 1.6;
                } else if b.key == "inferno" && b.mode.as_deref() == Some("single") {
                    weight *= 1.5;
                }
            }
            if let Some(weapon) = &b.weapon {
                if !others.is_empty() {
                    let covered = others
                        .iter()
                        .filter(|other| {
                            if other.id == b.id {
                                return false;
                            }
                            let distance = py_hypot(other.x - b.x, other.y - b.y);
                            weapon.min_range <= distance && distance <= weapon.range + b.half_hit
                        })
                        .count();
                    weight *= 1.0 + covered as f64 / others.len() as f64;
                }
            }
            (b.id, weight)
        }).collect()
    }

    fn snipe_role(&self, name: &str) -> &str {
        let role = self.scouting_context.as_ref()
            .and_then(|context| context.roles.iter().find(|(hero, _)| hero == name));
        if let Some((_, role)) = role {
            return role;
        }
        if self.push_heroes.iter().any(|hero| hero == name) || self.siege.as_deref() == Some(name) { "main" } else { "funnel" }
    }

    fn snipe_cost(&self, battle: &Battle, name: &str, kind: &str) -> f64 {
        let mut cost = match kind {
            "queen" => 3.0,
            "arrow" | "flinger" => 4.0,
            "spear" => 5.0,
            "dash" | "fireball" => 7.0,
            _ => unreachable!("snipe tool kind"),
        };
        cost += if self.snipe_role(name) == "main" { 2.0 } else { 0.5 };
        if !matches!(kind, "queen" | "flinger") {
            let paired = self.snipe_loadout(battle, name).equipment.iter()
                .filter(|item| self.owned(item)).map(|item| match item.as_str() {
                    "Eternal Tome" => 6.0,
                    "Healing Tome" => 3.0,
                    "Invisibility Vial" | "Healer Puppet" | "Haste Vial" | "Seeking Shield"
                    | "Action Figure" | "Revenge Deck" => 2.0,
                    "Royal Gem" => 1.5,
                    _ => 0.0,
                }).sum::<f64>();
            cost += paired;
        }
        cost
    }

    fn snipe_level(&self, battle: &Battle, name: &str) -> Level {
        self.level(battle, name).filter(level_truth).unwrap_or_else(|| {
            Level::Int(battle.catalog.stats.max_level(name, self.town_hall).expect("snipe troop max level"))
        })
    }

    // heroes.py:581-651: the sustained tools' infinity is only a ranking estimate.
    fn sniping_tool(&self, battle: &Battle, name: &str) -> Option<(String, f64, f64, f64)> {
        let level = self.snipe_level(battle, name);
        if name == "Flame Flinger" {
            let data = battle.catalog.game_data("characters", name, Some(&level));
            return Some(("flinger".to_owned(), battle.catalog.numbers(name, &level).range,
                game_float(data, "DamageRadius") / 100.0, f64::INFINITY));
        }
        let item = match name {
            "Archer Queen" => "Giant Arrow",
            "Royal Champion" => "Rocket Spear",
            "Dragon Duke" => "Rocket Backpack",
            "Grand Warden" => "Fireball",
            _ => unreachable!("opening hero"),
        };
        let equipped = self.snipe_loadout(battle, name)
            .equipment
            .iter()
            .any(|equipment| equipment == item && self.owned(equipment));
        if !equipped {
            return (name == "Archer Queen").then(|| {
                (
                    "queen".to_owned(),
                    battle.catalog.numbers(name, &level).range,
                    0.0,
                    f64::INFINITY,
                )
            });
        }
        let level = self.equipment_level(battle, item);
        let (kind, reach, radius, damage) = match item {
            "Giant Arrow" => {
                let data = battle.catalog.equipment_ability(item, &level);
                ("arrow", f64::INFINITY, game_float(data, "PenetratingRadius") / 100.0, game_float(data, "Damage"))
            }
            "Rocket Spear" => {
                let damage = heroes::col(battle, item, &level, &["damage per shot increase"], 0.0)
                    * heroes::col(battle, item, &level, &["number of attacks"], 0.0);
                ("spear", heroes::spear_range(battle), 0.0, damage * self.strength)
            }
            "Rocket Backpack" => {
                let data = battle.catalog.equipment_ability(item, &level);
                ("dash", game_float(data, "MovementOverrideDistance"),
                    game_float(data, "ActAsPenetratingRadius") / 100.0, game_float(data, "ActAsPenetratingDamage"))
            }
            _ => (
                "fireball",
                f64::INFINITY,
                heroes::col(battle, item, &level, &["damage radius"], 0.0),
                heroes::col(battle, item, &level, &["projectile damage"], 0.0),
            ),
        };
        Some((kind.to_owned(), reach, radius, damage))
    }

    fn snipe_lightning_count(&self) -> i64 {
        if self.scouting_context.as_ref().is_some_and(|context| context.reserve_lightning) {
            return 0;
        }
        self.unreserved_spells("lightning", true)
    }

    fn snipe_timing(
        &self,
        battle: &Battle,
        name: &str,
        kind: &str,
        target: BuildingId,
        x: f64,
        y: f64,
        mut damage: f64,
    ) -> (f64, f64, f64) {
        use crate::playbook::{action_time, Action};
        let target = battle.building(target);
        let distance = py_hypot(target.x - x, target.y - y);
        let mut seconds = action_time(battle, Action::Deploy, 1) + action_time(battle, Action::Ability, 1);
        let numbers = battle.catalog.numbers(name, &self.snipe_level(battle, name));
        match kind {
            "arrow" => seconds += distance / 35.0,
            "dash" => seconds += distance / 15.0,
            "fireball" => seconds += 1.5,
            "spear" => {
                let level = self.equipment_level(battle, "Rocket Spear");
                let bonus = heroes::col(battle, "Rocket Spear", &level, &["damage per shot increase"], 0.0);
                let shot = (numbers.dmg + bonus) * self.strength * battle.atk_hero_mult;
                let shots = 1.0_f64.max((target.hp / 1.0_f64.max(shot)).ceil());
                seconds += (shots - 1.0) * numbers.interval + distance / 12.0;
            }
            _ => {
                let dps = 1.0_f64.max(numbers.dps * self.strength * battle.atk_hero_mult);
                seconds = action_time(battle, Action::Deploy, 1) + target.hp / dps;
                let projectile_speed = if kind == "flinger" { 5.0 } else { 12.0 };
                seconds += distance / projectile_speed;
                damage = target.hp;
            }
        }
        let flying = numbers.flying || name == "Grand Warden" && !self.ground;
        let excluded_target = if flying { Tag::Ground } else { Tag::Air };
        let mut incoming = 0.0;
        for defense in &battle.buildings {
            let Some(weapon) = &defense.weapon else {
                continue;
            };
            if !battle.building_targetable(defense.id) || weapon.targets == excluded_target {
                continue;
            }
            if weapon.kind == Tag::Eagle && battle.deployed_housing < weapon.extra.activation as i64 {
                continue;
            }
            let separation = py_hypot(defense.x - x, defense.y - y);
            if weapon.min_range <= separation && separation <= weapon.range {
                incoming += weapon.damage / 0.1_f64.max(weapon.interval);
            }
        }
        let loss = 1.0_f64.min(incoming * seconds / 1.0_f64.max(numbers.hp));
        (damage, seconds, loss)
    }

    fn opening_reachable(&self, battle: &mut Battle, tiles: &[(f64, f64)]) -> Vec<bool> {
        if let Some(reached) = &battle.opening_reachable {
            return reached.clone();
        }
        let n = battle.grid.n;
        let mut blocked = battle.grid.blocked.clone();
        for b in &battle.buildings {
            if b.key == "tesla" && !b.revealed {
                let bound = |value| (round_half_even(value * RES as f64) as isize).clamp(0, n as isize) as usize;
                for i in bound(b.x - b.half_hit)..bound(b.x + b.half_hit) {
                    for j in bound(b.y - b.half_hit)..bound(b.y + b.half_hit) {
                        blocked[i * n + j] = false;
                    }
                }
            }
        }
        let walkable: Vec<_> = blocked.iter().zip(&battle.grid.wall).map(|(blocked, wall)| !(*blocked || *wall)).collect();
        let mut reached = vec![false; n * n];
        let mut queue = Vec::new();
        for &(x, y) in tiles {
            let (i, j) = battle.grid.cell(x, y);
            if walkable[i * n + j] && !reached[i * n + j] {
                reached[i * n + j] = true;
                queue.push((i, j));
            }
        }
        let mut head = 0;
        while head < queue.len() {
            let (i, j) = queue[head];
            head += 1;
            for (di, dj) in [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)] {
                let (ni, nj) = (i as isize + di, j as isize + dj);
                if ni < 0 || nj < 0 || ni >= n as isize || nj >= n as isize {
                    continue;
                }
                let (ni, nj) = (ni as usize, nj as usize);
                if reached[ni * n + nj] || !walkable[ni * n + nj] {
                    continue;
                }
                if di != 0 && dj != 0 && (!walkable[i * n + nj] || !walkable[ni * n + j]) {
                    continue;
                }
                reached[ni * n + nj] = true;
                queue.push((ni, nj));
            }
        }
        battle.opening_reachable = Some(reached.clone());
        reached
    }

    fn exposed_defenses(&mut self, battle: &mut Battle) -> Vec<DefenseSnipe> {
        use crate::playbook::{action_time, Action};
        if !self.snipe_exposed || self.snipe_mode == "off" {
            return Vec::new();
        }
        let mut tools = Vec::new();
        for name in ["Archer Queen", "Royal Champion", "Flame Flinger", "Dragon Duke", "Grand Warden"] {
            if self.snipe_available(name) {
                if let Some(tool) = self.sniping_tool(battle, name) {
                    tools.push((name, tool));
                }
            }
        }
        let lightning = self.snipe_lightning_count();
        if lightning != 0 {
            let effects = self.cluster_effects(battle, "lightning", lightning);
            tools.push((
                "Lightning Spell",
                (
                    "lightning".to_owned(),
                    f64::INFINITY,
                    effects[0].radius,
                    effects.iter().map(|e| e.damage).sum(),
                ),
            ));
        }
        if tools.is_empty() {
            return Vec::new();
        }
        let visible: Vec<_> = battle.buildings.iter().filter(|b| battle.building_targetable(b.id)).map(|b| b.id).collect();
        let defenses: Vec<_> = visible.iter().copied().filter(|id| battle.is_defense_target(*id)).collect();
        let weights = self.snipe_weights(battle);
        let mut targets = defenses.clone();
        targets.sort_by(|a, b| lookup(&weights, *b, 0.0).total_cmp(&lookup(&weights, *a, 0.0)));
        targets.truncate(24);
        let main_point = edge_point(battle, self.angle, 0.0);
        let tiles = battle.deploy_tiles().to_vec();
        let reached = self.opening_reachable(battle, &tiles);
        let mut ranked_tiles: Vec<(BuildingId, Vec<(f64, f64, f64)>)> = Vec::new();
        let lightning_effects = self.cluster_effects(battle, "lightning", self.snipe_lightning_count());
        let fallback = self.fallback;
        self.fallback = true;
        let paired_quake = self.spare_quakes(battle) > 0;
        self.fallback = fallback;
        let mut out = Vec::new();
        for (name, (kind, reach, mut radius, damage)) in tools {
            let (approach, base_cost) = if kind == "lightning" {
                (0.5, 0.0)
            } else {
                let range = battle.catalog.numbers(name, &self.snipe_level(battle, name)).range;
                (if kind == "spear" { reach } else { reach.min(range) }, self.snipe_cost(battle, name, &kind))
            };
            for &target_id in &targets {
                let target = battle.building(target_id);
                if lookup(&weights, target_id, 0.0) < base_cost - 0.5
                    || kind == "lightning" && (storage(&target.key) || matches!(target.key.as_str(), "th" | "cc"))
                {
                    continue;
                }
                let extent = target.half_hit + approach;
                let n = battle.grid.n;
                let start = |value: f64| ((value * RES as f64) as isize).max(0) as usize;
                let end = |value: f64| (((value * RES as f64) as isize) + 1).min(n as isize).max(0) as usize;
                let accessible = (start(target.x - extent)..end(target.x + extent)).any(|i| {
                    (start(target.y - extent)..end(target.y + extent)).any(|j| {
                        reached[i * n + j]
                            && target.edge_distance(
                                (i as f64 + 0.5) / RES as f64,
                                (j as f64 + 0.5) / RES as f64,
                            ) <= approach
                    })
                });
                if !accessible {
                    continue;
                }
                if !ranked_tiles.iter().any(|(id, _)| *id == target_id) {
                    let mut ranked: Vec<_> = tiles.iter().map(|&(x, y)| (target.edge_distance(x, y), x, y)).collect();
                    ranked.sort_by(|a, b| a.0.total_cmp(&b.0));
                    ranked_tiles.push((target_id, ranked));
                }
                let ranked = &ranked_tiles
                    .iter()
                    .find(|(id, _)| *id == target_id)
                    .expect("ranked target")
                    .1;
                let legal: Vec<_> = ranked
                    .iter()
                    .copied()
                    .filter(|item| item.0 <= reach)
                    .collect();
                let mut drops = Vec::new();
                for item in legal.iter().take(4).chain(legal.iter().skip(legal.len().saturating_sub(4))) {
                    if !drops.contains(item) {
                        drops.push(*item);
                    }
                }
                let mut best: Option<((f64, f64), DefenseSnipe)> = None;
                for (distance, x, y) in drops {
                    let mut band = None;
                    let mut center = (target.x, target.y);
                    let mut effect_kind = "damage";
                    if matches!(kind.as_str(), "queen" | "arrow") {
                        let nearest = *visible
                            .iter()
                            .min_by(|a, b| {
                                battle.building(**a).edge_distance(x, y)
                                    .total_cmp(&battle.building(**b).edge_distance(x, y))
                            })
                            .expect("visible target");
                        if kind == "queen" && nearest != target_id {
                            continue;
                        }
                        if kind == "arrow" {
                            let nearest = battle.building(nearest);
                            let (dx, dy) = (nearest.x - x, nearest.y - y);
                            let length = py_hypot(dx, dy);
                            let data = battle.catalog.game_data("special_abilities", "ArcherQueenPierceProjectile", None);
                            band = Some((
                                x,
                                y,
                                dx / length,
                                dy / length,
                                length + game_float(data, "PenetratingExtraRange") / 100.0,
                            ));
                            effect_kind = "arrow";
                        }
                    } else if kind == "dash" {
                        let (dx, dy, length, dash_radius) = heroes::dash_geometry(battle, x, y, (1.0, 0.0));
                        radius = dash_radius;
                        band = Some((x, y, dx, dy, length));
                        effect_kind = "dash";
                    } else if matches!(kind.as_str(), "spear" | "flinger" | "fireball") {
                        let nearest = *defenses
                            .iter()
                            .min_by(|a, b| {
                                battle.building(**a).edge_distance(x, y)
                                    .total_cmp(&battle.building(**b).edge_distance(x, y))
                            })
                            .expect("defense target");
                        if kind != "fireball" && nearest != target_id {
                            continue;
                        }
                        let nearest = battle.building(nearest);
                        center = (nearest.x, nearest.y);
                        if kind == "fireball" && target.edge_distance(center.0, center.1) > radius {
                            continue;
                        }
                    }
                    if let Some(band) = band {
                        if !band_hit(target, band, effect_kind, radius) {
                            continue;
                        }
                        center = (x, y);
                    }
                    let mut casts = 0;
                    let (dealt, mut seconds, loss, mut cost) = if kind == "lightning" {
                        let mut dealt = 0.0;
                        for effect in &lightning_effects {
                            dealt += effect.damage;
                            casts += 1;
                            if dealt >= target.hp {
                                break;
                            }
                        }
                        if dealt < target.hp {
                            continue;
                        }
                        (
                            dealt,
                            casts as f64 * action_time(battle, Action::Spell, 1) + spells::LAND_DELAY,
                            0.0,
                            1.5 * casts as f64,
                        )
                    } else {
                        let (dealt, seconds, loss) = self.snipe_timing(battle, name, &kind, target_id, x, y, damage);
                        (dealt, seconds, loss, base_cost)
                    };
                    if kind != "lightning" {
                        if paired_quake && matches!(kind.as_str(), "arrow" | "dash") {
                            seconds += action_time(battle, Action::Spell, 1).max(spells::LAND_DELAY + 4.0 * 0.4);
                            cost += 1.5;
                        }
                        cost += 2.0 * py_hypot(x - main_point.0, y - main_point.1) / battle.catalog.world as f64;
                    }
                    if seconds > 12.0 {
                        continue;
                    }
                    cost += 0.25 * seconds + 4.0 * loss;
                    let mut hits = Vec::new();
                    let mut value = -cost;
                    for &id in &defenses {
                        let defense = battle.building(id);
                        let mut hit = band.map_or_else(|| defense.edge_distance(center.0, center.1) <= radius,
                            |band| band_hit(defense, band, effect_kind, radius));
                        if matches!(kind.as_str(), "queen" | "spear") {
                            hit = id == target_id;
                        }
                        if !hit || kind == "lightning"
                            && (storage(&defense.key) || matches!(defense.key.as_str(), "th" | "cc"))
                        {
                            continue;
                        }
                        let mut hit_damage = dealt;
                        if kind == "arrow" && defense.key == "ad" {
                            hit_damage *= 2.0;
                        }
                        let probability = 1.0_f64.min(hit_damage / defense.hp) * (1.0 - loss);
                        hits.push((id, hit_damage));
                        if id == target_id {
                            value += lookup(&weights, id, 0.0) * probability;
                        }
                    }
                    let rank = (value, distance);
                    if best.as_ref().is_none_or(|(previous, candidate)| rank > (candidate.value, previous.1)) {
                        best = Some((rank, DefenseSnipe {
                            target: target_id, tool: name.to_owned(), kind: kind.clone(), x, y,
                            value, seconds, cost, damage: hits, casts, confidence: 1.0 - loss,
                        }));
                    }
                }
                if let Some((_, chosen)) = best {
                    out.push(chosen);
                }
            }
        }
        out
    }

    fn selected_snipes(&self, battle: &Battle, exposed: &[DefenseSnipe]) -> Vec<DefenseSnipe> {
        use crate::playbook::{action_time, Action};
        if !self.snipe_exposed || self.snipe_mode == "off" {
            return Vec::new();
        }
        let threshold = if self.snipe_mode == "value" { 2.0 } else { -0.5 };
        let mut remaining: Vec<_> = battle.buildings.iter().map(|b| (b.id, b.hp)).collect();
        let weights = self.snipe_weights(battle);
        let mut selected = Vec::new();
        let mut used: Vec<String> = Vec::new();
        let mut at = 0.0;
        loop {
            let mut best: Option<(f64, &DefenseSnipe)> = None;
            for candidate in exposed {
                let hp = lookup(&remaining, candidate.target, 0.0);
                if used.contains(&candidate.tool) || hp <= 0.0 || at + candidate.seconds > 12.0 {
                    continue;
                }
                let probability = 1.0_f64.min(lookup(&candidate.damage, candidate.target, 0.0) / hp) * candidate.confidence;
                let value = lookup(&weights, candidate.target, 0.0) * probability - candidate.cost - 0.25 * at;
                if value >= threshold && best.is_none_or(|(previous, _)| value > previous) {
                    best = Some((value, candidate));
                }
            }
            let Some((_, chosen)) = best else {
                break;
            };
            used.push(chosen.tool.clone());
            selected.push(chosen.clone());
            for &(id, damage) in &chosen.damage {
                let entry = remaining.iter_mut().find(|(key, _)| *key == id).expect("remaining building HP");
                entry.1 -= damage;
            }
            at += if chosen.kind == "lightning" {
                action_time(battle, Action::Spell, 1) * chosen.casts as f64
            } else {
                action_time(battle, Action::Deploy, 1)
            };
        }
        selected
    }

    pub fn opening_deployments(&mut self, battle: &mut Battle) -> Vec<Deployment> {
        use crate::playbook::{action_time, Action};
        self.snipe_deployed.clear();
        self.snipe_assignments.clear();
        self.snipe_claimed.clear();
        self.snipe_lightning = None;
        self.snipe_lightning_at = 0.0;
        self.snipe_lightning_left = 0;
        let exposed = if self.snipe_exposed { self.exposed_defenses(battle) } else { Vec::new() };
        let mut out = Vec::new();
        let mut at = 0.0;
        let mut remaining: Vec<_> = battle.buildings.iter().map(|b| (b.id, b.hp)).collect();
        for chosen in self.selected_snipes(battle, &exposed) {
            if chosen.kind == "lightning" {
                self.snipe_lightning = Some(chosen.clone());
                self.snipe_lightning_at = at;
                self.snipe_lightning_left = chosen.casts;
            } else {
                set(&mut self.snipe_assignments, chosen.tool.clone(), chosen.clone());
                self.snipe_deployed.push(chosen.tool.clone());
                out.push(Deployment {
                    time: at, name: chosen.tool.clone(), x: chosen.x, y: chosen.y,
                    group: "snipe".to_owned(), level: self.level(battle, &chosen.tool),
                    town_hall: Some(self.town_hall), source: "army".to_owned(), mode: None,
                });
                self.log_snipe(at, &format!("deploy:{}", chosen.kind), chosen.target, chosen.x, chosen.y);
            }
            for &(id, damage) in &chosen.damage {
                let entry = remaining.iter_mut().find(|(key, _)| *key == id).expect("remaining building HP");
                entry.1 -= damage;
                if entry.1 <= 0.0 && chosen.kind != "lightning" && !self.snipe_claimed.contains(&id) {
                    self.snipe_claimed.push(id);
                }
            }
            at += if chosen.kind == "lightning" {
                action_time(battle, Action::Spell, 1) * chosen.casts as f64
            } else {
                action_time(battle, Action::Deploy, 1)
            };
        }
        if !out.is_empty() {
            self.busy_until = at;
        }
        // Python exports these sets in repr order. Their runtime uses are membership only.
        self.snipe_deployed.sort();
        self.snipe_claimed.sort_by_key(|id| id.0.to_string());
        out
    }

    fn log_snipe(&mut self, time: f64, kind: &str, target: BuildingId, x: f64, y: f64) {
        self.snipe_log.push(Json::Arr(vec![
            Json::Num(round_decimal(time, 1)),
            Json::Str(kind.to_owned()),
            Json::Num(target.0 as f64),
            Json::Num(x),
            Json::Num(y),
        ]));
    }

    pub fn opening_actions(&mut self, battle: &mut Battle) -> bool {
        use crate::playbook::{action_time, Action};
        // output/research/usage/hero-sniping-of-exposed-defenses.md:
        // https://clashofclans.fandom.com/wiki/Rocket_Spear
        // Claims predict the opening, not permanent destruction. Release any
        // survivor when the existing 12-second opening policy ends.
        if battle.t > 12.0 {
            self.snipe_claimed.clear();
            // Tick callbacks also read the previous copy-on-write plan.
            match &mut battle.plan {
                Plan::Attack(plan) => plan.snipe_claimed.clear(),
                Plan::Playbook(plan) => plan.attack.snipe_claimed.clear(),
                Plan::Stage { .. } => {}
            }
        }
        if !self.snipe_exposed || self.snipe_mode == "off" || battle.t > 12.0 || battle.t < self.busy_until {
            return false;
        }
        if let Some(chosen) = self.snipe_lightning.clone().filter(|chosen| self.snipe_lightning_left > 0
            && battle.t >= self.snipe_lightning_at && battle.building_targetable(chosen.target)
            && !self.snipe_claimed.contains(&chosen.target))
        {
            let available = self.snipe_lightning_count().min(self.snipe_lightning_left);
            let (hp, _) = self.cluster_state(battle);
            let remaining = lookup(&hp, chosen.target, 0.0);
            let effects = if available != 0 { self.cluster_effects(battle, "lightning", available) } else { Vec::new() };
            if remaining > 0.0 && effects.iter().map(|effect| effect.damage).sum::<f64>() >= remaining
                && battle.t + spells::LAND_DELAY <= 12.0
            {
                let target = battle.building(chosen.target);
                let (x, y) = (target.x, target.y);
                self.use_spell(battle, "lightning", x, y);
                self.snipe_lightning_left -= 1;
                self.snipe_lightning_at = battle.t + action_time(battle, Action::Spell, 1);
                self.busy_until = self.busy_until.max(self.snipe_lightning_at);
                self.log_snipe(battle.t, "lightning", chosen.target, x, y);
                return true;
            }
        }
        if battle.t < self.busy_until {
            return false;
        }
        let units: Vec<_> = battle.attackers_pool().map(Unit::reference).collect();
        for hero in units {
            let u = battle.unit(hero);
            let assignment = self.snipe_assignments.iter().find(|(name, _)| *name == u.name);
            let Some((_, chosen)) = assignment else {
                continue;
            };
            let chosen = chosen.clone();
            if !u.alive || u.kind == Tag::HeroClone || u.ability_used || u.kit.is_none()
                || battle.t + chosen.seconds > 12.0 || !battle.building_targetable(chosen.target) || chosen.kind == "queen"
            {
                continue;
            }
            if matches!(chosen.kind.as_str(), "arrow" | "dash") {
                let Some((band, effect)) = self.ability_band(battle, hero) else {
                    continue;
                };
                if !band_hit(battle.building(chosen.target), band, &effect.kind, effect.radius) {
                    continue;
                }
                if !self.fire_aimed(battle, hero, None) {
                    return true;
                }
            } else {
                let (x, y) = (u.x, u.y);
                let nearest = heroes::targets(battle, true).into_iter().min_by(|a, b| {
                    heroes::distance(battle, *a, x, y).total_cmp(&heroes::distance(battle, *b, x, y))
                });
                let Some(nearest) = nearest else {
                    continue;
                };
                let target = battle.building(chosen.target);
                if chosen.kind == "spear" {
                    if nearest != EntityRef::Building(chosen.target)
                        || target.edge_distance(x, y) > heroes::spear_range(battle)
                    {
                        continue;
                    }
                } else {
                    let center = battle.entity_position(nearest);
                    let level = u.kit.as_ref().expect("hero kit").lv("Fireball");
                    let radius = heroes::col(battle, "Fireball", level, &["damage radius"], 0.0);
                    if target.edge_distance(center.0, center.1) > radius {
                        continue;
                    }
                }
                heroes::activate(battle, hero, false);
            }
            let u = battle.unit(hero);
            self.log_snipe(battle.t, &chosen.kind, chosen.target, u.x, u.y);
            self.busy_until = battle.t + action_time(battle, Action::Ability, 1);
            return true;
        }
        false
    }
}
