//! Ports plans.py:140-157,227-229,423-463,581-598,713-721,791-1047.
//! Python constructs the inventory; runtime dictionaries retain insertion order.

use crate::geom::{py_cos, py_hypot, py_sin, round_half_even};
use crate::heroes::{self, HeroLoadout};
use crate::json::Json;
use crate::labels::{Name, Tag};
use crate::shared::SharedVec;
use crate::spells;
use crate::state::*;
use crate::stats::Level;
use crate::trace::round_decimal;

pub const SPELL_NAMES: &[(&str, &str)] = &[
    ("lightning", "Lightning Spell"),
    ("heal", "Healing Spell"),
    ("rage", "Rage Spell"),
    ("jump", "Jump Spell"),
    ("freeze", "Freeze Spell"),
    ("clone", "Clone Spell"),
    ("invis", "Invisibility Spell"),
    ("recall", "Recall Spell"),
    ("revive", "Revive Spell"),
    ("totem", "Totem Spell"),
    ("poison", "Poison Spell"),
    ("eq", "Earthquake Spell"),
    ("haste", "Haste Spell"),
    ("skeleton", "Skeleton Spell"),
    ("bat", "Bat Spell"),
    ("overgrowth", "Overgrowth Spell"),
    ("iceblock", "Ice Block Spell"),
    ("angry", "Angry Spell"),
    ("santa", "Santa's Surprise"),
    ("frostmites", "Bag of Frostmites"),
    ("birthday", "Birthday Boom"),
    ("yellow", "Yellow Card"),
];

pub fn spell_key(name: &str) -> Option<&'static str> {
    SPELL_NAMES.iter().find(|(_, value)| *value == name).map(|(key, _)| *key)
}

pub fn spell_name(key: &str) -> &'static str {
    SPELL_NAMES.iter().find(|(name, _)| *name == key).expect("known spell key").1
}

pub fn is_hero(name: &str) -> bool {
    matches!(
        name,
        "Barbarian King"
            | "Archer Queen"
            | "Grand Warden"
            | "Royal Champion"
            | "Minion Prince"
            | "Dragon Duke"
    )
}

pub fn threat(key: &str, default: f64) -> f64 {
    match key {
        "th" => 6.0,
        "inferno" => 10.0,
        "scatter" => 8.0,
        "eagle" => 7.0,
        "xbow" | "mono" | "mgt" | "swt" => 5.0,
        "firespitter" | "revenge" | "ad" | "ric" => 4.0,
        "mat" | "wt" | "st" => 3.0,
        "bt" | "at" | "tesla" => 2.0,
        "cannon" | "bh" | "mortar" | "sweeper" => 1.0,
        _ => default,
    }
}

pub fn count(items: &[(String, i64)], key: &str) -> i64 {
    items.iter().find(|(name, _)| name == key).map_or(0, |(_, n)| *n)
}

pub fn set<K: PartialEq, V>(items: &mut Vec<(K, V)>, key: K, value: V) {
    if let Some((_, previous)) = items.iter_mut().find(|(name, _)| *name == key) {
        *previous = value;
    } else {
        items.push((key, value));
    }
}

pub fn number(value: &Json, key: &str, default: f64) -> f64 {
    value.get(key).filter(|v| !v.is_null()).map_or(default, Json::f64)
}

pub fn text<'a>(value: &'a Json, key: &str, default: &'a str) -> &'a str {
    value.get(key).filter(|v| !v.is_null()).map_or(default, Json::str)
}

pub fn truth(value: &Json) -> bool {
    match value {
        Json::Null => false,
        Json::Bool(v) => *v,
        Json::Num(v) => *v != 0.0,
        Json::Str(v) => !v.is_empty(),
        Json::Arr(v) => !v.is_empty(),
        Json::Obj(v) => !v.is_empty(),
    }
}

pub fn flag(value: &Json, key: &str) -> bool {
    value.get(key).is_some_and(truth)
}

pub fn levels(value: &Json, key: &str) -> Vec<(String, Option<Level>)> {
    value.get(key).filter(|v| !v.is_null()).map_or_else(Vec::new, |v| {
        v.obj().iter().map(|(name, lv)| {
            (name.clone(), (!lv.is_null()).then(|| Level::from_json(lv)))
        }).collect()
    })
}

pub fn counts(value: &Json, key: &str) -> Vec<(String, i64)> {
    value.get(key).map_or_else(Vec::new, |v| {
        v.obj().iter().map(|(name, n)| (name.clone(), n.i64())).collect()
    })
}

pub fn times(value: &Json, key: &str) -> Vec<(String, f64)> {
    value.get(key).map_or_else(Vec::new, |v| {
        v.obj().iter().map(|(name, n)| (name.clone(), n.f64())).collect()
    })
}

#[derive(Clone, Debug)]
pub struct SpellStock {
    pub name: String,
    pub origin: String,
    pub remaining: i64,
    pub level: Option<Level>,
}

#[derive(Clone, Debug)]
pub struct AttackPlan {
    pub angle: f64,
    pub town_hall: i64,
    pub strength: f64,
    pub ground: bool,
    pub loadouts: SharedVec<(String, HeroLoadout)>,
    pub troop_levels: SharedVec<(String, Option<Level>)>,
    pub hero_levels: SharedVec<(String, Option<Level>)>,
    pub equipment_levels: SharedVec<(String, Option<Level>)>,
    pub pet_levels: SharedVec<(String, Option<Level>)>,
    pub spell_levels: SharedVec<(String, Option<Level>)>,
    pub auto_ability_on_ko: bool,
    pub observed: bool,
    pub spells: SharedVec<(String, i64)>,
    pub cc_spells: SharedVec<(String, i64)>,
    pub stock: SharedVec<SpellStock>,
    pub pol: SharedVec<(String, f64)>,
    pub auto_revive: bool,
    pub revive_delay: f64,
    pub freeze_first: SharedVec<String>,
    pub zap_ad: (i64, i64),
    pub zap_done: bool,
    pub cc_released: bool,
    pub siege_donated: bool,
    pub main_at: f64,
    pub cast_log: SharedVec<(f64, String)>,
    pub breakers: SharedVec<(String, i64)>,
    pub cleanup: SharedVec<(String, i64)>,
    pub distracts: i64,
    pub snipe_t: Option<f64>,
    pub snipe_points: SharedVec<(f64, f64)>,
}

impl AttackPlan {
    pub fn load(p: &Json) -> Self {
        let pairs = |key: &str| -> Vec<(String, i64)> {
            p.at(key)
                .arr()
                .iter()
                .map(|v| (v.arr()[0].str().to_owned(), v.arr()[1].i64()))
                .collect()
        };
        let stock: Vec<_> = p.at("_spell_stock").arr().iter().map(|v| {
            assert_eq!(v.at("$type").str(), "SpellStock");
            let remaining = v.at("remaining").i64();
            let level = v
                .get("level")
                .filter(|v| !v.is_null())
                .map(Level::from_json);
            assert!(
                remaining <= 0 || level.is_some(),
                "export live spell stock after resolving its constructed level"
            );
            SpellStock {
                name: v.at("name").str().to_owned(),
                origin: v.at("origin").str().to_owned(),
                remaining,
                level,
            }
        }).collect();
        Self {
            angle: p.at("angle").f64(),
            town_hall: p.at("town_hall").i64(),
            strength: p.at("strength").f64(),
            ground: p.at("ground").bool(),
            loadouts: p.at("loadouts").obj().iter().map(|(name, v)| {
                (name.clone(), HeroLoadout {
                    hero: v.at("hero").str().to_owned(),
                    equipment: v.at("equipment")
                        .arr()
                        .iter()
                        .map(|s| s.str().to_owned())
                        .collect(),
                    pet: v.at("pet").opt_str().map(str::to_owned),
                })
            }).collect(),
            troop_levels: levels(p, "troop_levels").into(),
            hero_levels: levels(p, "hero_levels").into(),
            equipment_levels: levels(p, "equipment_levels").into(),
            pet_levels: levels(p, "pet_levels").into(),
            spell_levels: levels(p, "spell_levels").into(),
            auto_ability_on_ko: p.at("auto_ability_on_ko").bool(),
            observed: flag(p, "observed"),
            spells: counts(p, "spells").into(),
            cc_spells: counts(p, "cc_spells").into(),
            stock: stock.into(),
            pol: times(p, "pol").into(),
            auto_revive: flag(p, "auto_revive"),
            revive_delay: number(p, "revive_delay", 1.5),
            freeze_first: p.at("freeze_first").arr().iter().map(|v| v.str().to_owned()).collect(),
            zap_ad: (p.at("zap_ad").arr()[0].i64(), p.at("zap_ad").arr()[1].i64()),
            zap_done: flag(p, "_zap_done"),
            cc_released: flag(p, "_cc_released"),
            siege_donated: flag(p, "siege_donated"),
            main_at: number(p, "_main_at", 0.0),
            cast_log: p.at("_cast_log")
                .arr()
                .iter()
                .map(|v| (v.arr()[0].f64(), v.arr()[1].str().to_owned()))
                .collect(),
            breakers: pairs("breakers").into(),
            cleanup: pairs("cleanup").into(),
            distracts: number(p, "_distracts", 0.0) as i64,
            snipe_t: None,
            snipe_points: SharedVec::default(),
        }
    }

    // plans.py:227-229; policy defaults used by runtime helpers.
    pub fn p(&self, name: &str) -> f64 {
        if let Some((_, v)) = self.pol.iter().find(|(key, _)| key == name) {
            return *v;
        }
        match name {
            "freeze_min_threat" => 5.0,
            "freeze_reach" => 1.5,
            "freeze_min_units" => 0.0,
            "totem_min_threats" => 3.0,
            "totem_gap" => 5.0,
            "og_min_score" => 18.0,
            "rage_engaged" => 0.5,
            "rage_gap" => 9.0,
            "heal_hp" | "invis_hp" | "duke_hp" => 0.6,
            "invis_hot" => 2.0,
            "invis_gap" => 4.5,
            "recall_after" => 12.0,
            "recall_hp" | "warden_hp" => 0.4,
            "haste_after" => 3.0,
            "haste_gap" => 8.0,
            "poison_min" => 3.0,
            "hero_hp" => 0.5,
            "hero_time" => 25.0,
            "warden_hurt" => 1.0 / 3.0,
            "arrow_aim" | "dash_aim" | "angry_min" | "skeleton_on" | "bat_on"
            | "eq_core_dist" | "distract_reach" => 0.0,
            "arrow_reach" => 12.0,
            "arrow_threat" | "dash_threat" => 7.0,
            "dash_reach" | "distract_threat" => 8.0,
            "eq_core_n" | "distract_max" => 2.0,
            _ => panic!("unknown runtime policy {name}"),
        }
    }

    pub fn last(&self, kind: &str) -> f64 {
        self.cast_log.iter().rev().find(|(_, k)| k == kind).map_or(-100.0, |(t, _)| *t)
    }

    // plans.py:423-446: retain first matching stock, including donated level.
    pub fn cast_spell(
        &mut self,
        battle: &mut Battle,
        name: &str,
        x: f64,
        y: f64,
        level: Option<&Level>,
        origin: Option<&str>,
    ) {
        let index = self.stock.iter().position(|s| {
            s.name == name && s.remaining > 0
                && origin.is_none_or(|origin| s.origin == origin)
                && level.is_none_or(|level| s.level.as_ref() == Some(level))
        }).unwrap_or_else(|| panic!("No matching {name} remaining"));
        let selected = self.stock[index]
            .level
            .clone()
            .expect("live spell stock needs its exported level");
        spells::cast_effect(battle, name, x, y, Some(selected));
        self.stock[index].remaining -= 1;
        let key = spell_key(name).expect("spell name");
        let remaining = count(&self.spells, key) - 1;
        set(&mut self.spells, key.to_owned(), remaining);
        battle.deployed_housing += 5 * battle.catalog.stats.attrs(name).at("housing").i64();
        self.cast_log.push((round_decimal(battle.t, 1), key.to_owned()));
    }

    pub fn use_spell(&mut self, battle: &mut Battle, kind: &str, x: f64, y: f64) {
        self.cast_spell(battle, spell_name(kind), x, y, None, None);
    }

    // plans.py:581-598. Jitter consumes x before y, even when deployment relocates.
    pub fn drop(
        &self,
        battle: &mut Battle,
        name: &str,
        mut x: f64,
        mut y: f64,
        group: &str,
        jitter: f64,
    ) {
        if jitter != 0.0 {
            x += battle.rng.as_mut().expect("battle rng").uniform(-jitter, jitter);
            y += battle.rng.as_mut().expect("battle rng").uniform(-jitter, jitter);
        }
        let world = battle.catalog.world as f64;
        let levels = if is_hero(name) {
            &self.hero_levels
        } else {
            &self.troop_levels
        };
        let level = levels.iter().find(|(key, _)| key == name).and_then(|(_, lv)| lv.clone());
        battle.deploy(Deployment {
            time: battle.t,
            name: name.to_owned(),
            x: (world - 0.6).min(0.6_f64.max(x)),
            y: (world - 0.6).min(0.6_f64.max(y)),
            group: group.to_owned(),
            level,
            town_hall: Some(self.town_hall),
            source: "army".to_owned(),
            mode: None,
        });
    }

    // plans.py:713-721: first maximum over the sixteen candidate edges.
    pub fn portal_point(&self, battle: &mut Battle) -> (f64, f64) {
        let mut best = (0.0, 0.0);
        let mut score = None;
        for k in 0..16 {
            let point = edge_point(battle, self.angle + 2.0 * std::f64::consts::PI * k as f64 / 16.0, 0.0);
            let n = battle.buildings.iter()
                .filter(|b| b.alive && b.counted && b.dist(point.0, point.1) < 11.0)
                .count();
            if score.is_none_or(|s| n > s) {
                best = point;
                score = Some(n);
            }
        }
        best
    }

    // plans.py:791-823.
    pub fn hero_abilities(&self, battle: &mut Battle) {
        let t = battle.t;
        let units: Vec<_> = battle.attackers_pool().map(Unit::reference).collect();
        for reference in units {
            let u = battle.unit(reference);
            let Some(kit) = &u.kit else {
                continue;
            };
            if !u.alive || !u.is_hero || u.ability_used {
                continue;
            }
            let frac = u.hp / 1.0_f64.max(u.max_hp);
            let engaged = u.target.is_some() && t - u.spawned_at > 2.0;
            let mut fire = false;
            if u.name_id == Name::MinionPrince && kit.has("Portal Pendant") {
                let near: Vec<_> = battle.attackers_near(u.x, u.y, 7.0).into_iter().filter(|r| {
                    let a = battle.unit(*r);
                    !a.is_hero && a.kind != Tag::Pet && a.name_id != Name::Totem
                }).collect();
                if !near.is_empty() {
                    let (cx, cy) = centroid(battle, &near);
                    let work = battle.buildings.iter()
                        .any(|b| b.alive && b.counted && b.edge_distance(cx, cy) < 7.0);
                    let hurt = near.iter().map(|r| {
                        let a = battle.unit(*r);
                        a.hp / a.max_hp
                    }).sum::<f64>() / near.len() as f64;
                    fire = near.len() >= 6 && (!work || hurt < 0.45) && t - u.spawned_at > 15.0;
                } else {
                    fire = frac < 0.35;
                }
            } else if u.name_id == Name::GrandWarden {
                let near: Vec<_> = battle.attackers_near(u.x, u.y, 7.0).into_iter().filter(|r| {
                    let a = battle.unit(*r);
                    a.name_id != Name::Totem && !a.is_hero
                }).collect();
                let hurt = near.iter().filter(|r| {
                    let a = battle.unit(**r);
                    a.hp < 0.55 * a.max_hp
                }).count();
                fire = near.len() >= 5
                    && hurt as i64 >= (near.len() as f64 * self.p("warden_hurt") + 1e-9) as i64
                    || frac < self.p("warden_hp");
            } else if self.p("arrow_aim") > 0.5
                && kit.has("Giant Arrow")
                && self.aim(battle, reference, "arrow").is_some()
            {
                let target = self.aim(battle, reference, "arrow").expect("aim target");
                fire_aimed(battle, reference, target);
                continue;
            } else if self.p("dash_aim") > 0.5
                && kit.has("Rocket Backpack")
                && self.aim(battle, reference, "dash").is_some()
            {
                unreachable!("dash aim is always false in Python");
            } else if u.name_id == Name::DragonDuke {
                fire = engaged
                    && (frac < self.p("duke_hp")
                    || u.target.is_some_and(|r| entity_is_defense(battle, r)));
            } else if frac < self.p("hero_hp")
                || engaged
                && t - u.spawned_at > self.p("hero_time") {
                fire = true;
            }
            if fire {
                heroes::activate(battle, reference);
            }
        }
    }

    // plans.py:825-840.
    pub fn aim(&self, battle: &Battle, hero: UnitRef, kind: &str) -> Option<BuildingId> {
        if kind == "dash" {
            return None;
        }
        let reach = self.p(&format!("{kind}_reach"));
        let threshold = self.p(&format!("{kind}_threat"));
        let u = battle.unit(hero);
        let mut best: Option<(f64, f64, BuildingId)> = None;
        for b in &battle.buildings {
            let weight = threat(&b.key, 0.0);
            if b.alive && b.weapon.is_some() && weight >= threshold {
                let d = b.dist(u.x, u.y);
                if d <= reach && best.is_none_or(|(w, neg_d, _)| (weight, -d) > (w, neg_d)) {
                    best = Some((weight, -d, b.id));
                }
            }
        }
        best.map(|(_, _, id)| id)
    }

    // plans.py:852-865.
    pub fn zap(&mut self, battle: &mut Battle, allowed: &impl Fn(&Self, &str) -> bool) {
        self.zap_done = true;
        let (ex, ey) = edge_point(battle, self.angle, 0.0);
        let mut best = None;
        let mut closest = f64::INFINITY;
        for b in &battle.buildings {
            if b.alive && b.key == "ad" {
                let d = b.dist(ex, ey);
                if best.is_none() || d < closest {
                    best = Some((b.x, b.y));
                    closest = d;
                }
            }
        }
        let Some((x, y)) = best else {
            return;
        };
        for _ in 0..self.zap_ad.1 {
            if allowed(self, "eq") {
                self.use_spell(battle, "eq", x, y);
            }
        }
        for _ in 0..self.zap_ad.0 {
            if allowed(self, "lightning") {
                self.use_spell(battle, "lightning", x, y);
            }
        }
    }

    // plans.py:899-923: breakers precede Jump and Earthquake.
    fn breach(&mut self, battle: &mut Battle, units: &[UnitRef], have: &impl Fn(&Self, &str) -> bool) {
        let stuck: Vec<_> = units.iter()
            .copied()
            .filter(|u| battle.unit(*u).wall_target.is_some_and(|w| battle.walls[w.0].alive))
            .collect();
        if stuck.len() < 2 {
            return;
        }
        let w = battle.walls[battle.unit(stuck[0]).wall_target.expect("wall").0].clone();
        let together = stuck.iter().filter(|r| {
            let other = &battle.walls[battle.unit(**r).wall_target.expect("wall").0];
            (other.x - w.x).abs() + (other.y - w.y).abs() <= 3.0
        }).count();
        if together < 2 {
            return;
        }
        let (cx, cy) = centroid(battle, &stuck);
        if let Some(index) = self.breakers.iter().position(|(_, n)| *n > 0) {
            let n = self.breakers[index].1.min(3);
            self.breakers[index].1 -= n;
            for _ in 0..n {
                self.drop(battle, &self.breakers[index].0, cx, cy, "breach", 0.4);
            }
            self.cast_log.push((round_decimal(battle.t, 1), "breach".to_owned()));
            return;
        }
        if have(self, "jump") {
            self.use_spell(battle, "jump", w.x, w.y);
            self.cast_log.push((round_decimal(battle.t, 1), "breach".to_owned()));
        } else if count(&self.spells, "eq") >= 4 {
            for _ in 0..4 {
                self.use_spell(battle, "eq", w.x, w.y);
            }
            self.cast_log.push((round_decimal(battle.t, 1), "breach".to_owned()));
        }
    }

    // plans.py:925-989. 'have' implements PlaybookPlan's fallback reservations.
    pub fn generic_spells(&mut self, battle: &mut Battle, units: &[UnitRef], have: &impl Fn(&Self, &str) -> bool) {
        if units.is_empty() {
            return;
        }
        let t = battle.t;
        if t - self.last("breach") > 3.0 {
            self.breach(battle, units, have);
        }
        let (cx, cy) = centroid(battle, units);
        let avg_hp = units.iter().map(|r| {
            let u = battle.unit(*r);
            u.hp / u.max_hp
        }).sum::<f64>() / units.len() as f64;
        let engaged = units.iter().filter(|r| {
            let u = battle.unit(**r);
            u.target.is_some() && u.cooldown > 0.0
        }).count();
        if have(self, "freeze") {
            let priority = |key: &str| self.freeze_first.iter()
                .position(|k| k == key)
                .map(|i| 100.0 - i as f64);
            let mut threats = threats_near(battle, cx, cy, 12.0);
            threats.sort_by(|(a, _), (b, _)| {
                let a = &battle.building(*a).key;
                let b = &battle.building(*b).key;
                let pa = priority(a).filter(|v| *v != 0.0).unwrap_or_else(|| threat(a, 1.0));
                let pb = priority(b).filter(|v| *v != 0.0).unwrap_or_else(|| threat(b, 1.0));
                pb.total_cmp(&pa)
            });
            for (id, d) in threats {
                let b = battle.building(id);
                let w = b.weapon.as_ref().expect("weapon");
                if (priority(&b.key).is_some() || threat(&b.key, 0.0) >= self.p("freeze_min_threat"))

                    && d <= w.range + self.p("freeze_reach")
                    && (w.target.is_some()
                    || !w.multi.is_empty()) {
                    if self.p("freeze_min_units") > 0.0 {
                        let in_range = units.iter()
                            .filter(|r| battle.unit(**r).dist(b.x, b.y) <= w.range)
                            .count();
                        if (in_range as f64) < self.p("freeze_min_units") {
                            continue;
                        }
                    }
                    let (x, y) = (b.x, b.y);
                    self.use_spell(battle, "freeze", x, y);
                    break;
                }
            }
        }
        if have(self, "totem")
            && t - self.last("totem") > self.p("totem_gap") {
            let hot = threats_near(battle, cx, cy, 10.0);
            if hot.len() as f64 >= self.p("totem_min_threats") {
                let fx = hot.iter()
                    .map(|(b, _)| battle.building(*b).x)
                    .sum::<f64>() / hot.len() as f64;
                let fy = hot.iter()
                    .map(|(b, _)| battle.building(*b).y)
                    .sum::<f64>() / hot.len() as f64;
                self.use_spell(battle, "totem", cx + (fx - cx) * 0.5, cy + (fy - cy) * 0.5);
            }
        }
        if have(self, "overgrowth") {
            let mut best = None;
            for (id, _) in threats_near(battle, cx, cy, 13.0) {
                let b = battle.building(id);
                if threat(&b.key, 0.0) < 4.0 {
                    continue;
                }
                let score = threats_near(battle, b.x, b.y, 6.0)
                    .iter()
                    .map(|(b, _)| threat(&battle.building(*b).key, 1.0))
                    .sum::<f64>();
                if best.is_none_or(|(s, _)| score > s) {
                    best = Some((score, id));
                }
            }
            if let Some((score, id)) = best {
                if score >= self.p("og_min_score") {
                    let b = battle.building(id);
                    let (x, y) = (b.x, b.y);
                    self.use_spell(battle, "overgrowth", x, y);
                }
            }
        }
        if have(self, "rage") && engaged >= 2
            .max((units.len() as f64 * self.p("rage_engaged")) as usize)
            && t - self.last("rage") > self.p("rage_gap") {
            self.use_spell(battle, "rage", cx, cy);
        }
        if have(self, "heal")
            && avg_hp < self.p("heal_hp")
            && t - self.last("heal") > 6.0 {
            self.use_spell(battle, "heal", cx, cy);
        }
        if have(self, "invis")
            && t - self.last("invis") > self.p("invis_gap") {
            let hot = threats_near(battle, cx, cy, 11.0).iter().filter(|(id, _)| {
                let b = battle.building(*id);
                let w = b.weapon.as_ref().expect("weapon");
                threat(&b.key, 0.0) >= 4.0 && (w.target.is_some() || !w.multi.is_empty())
            }).count();
            if avg_hp < self.p("invis_hp") || hot as f64 >= self.p("invis_hot") {
                self.use_spell(battle, "invis", cx, cy);
            }
        }
        if have(self, "recall")
            && t - self.last("recall") > 6.0
            && t - self.main_at > self.p("recall_after") {
            let work = battle.buildings.iter()
                .any(|b| b.alive && b.counted && b.edge_distance(cx, cy) < 7.0);
            if units.len() >= 6 && (!work || avg_hp < self.p("recall_hp")) {
                self.use_spell(battle, "recall", cx, cy);
            }
        }
        if have(self, "clone")
            && t - self.main_at > 1.0
            && t - self.last("clone") > 1.0 {
            let big: Vec<_> = units.iter().copied().filter(|r| {
                let u = battle.unit(*r);
                u.housing >= 10 && !u.extra.clone
            }).collect();
            if !big.is_empty() {
                let (x, y) = centroid(battle, &big);
                self.use_spell(battle, "clone", x, y);
            }
        }
        if have(self, "haste")
            && t - self.main_at > self.p("haste_after")
            && t - self.last("haste") > self.p("haste_gap") {
            self.use_spell(battle, "haste", cx, cy);
        }
        if have(self, "iceblock") && avg_hp < 0.45 && t - self.last("iceblock") > 8.0 {
            self.use_spell(battle, "iceblock", cx, cy);
        }
        if have(self, "poison") {
            let foes: Vec<_> = battle.defenders_pool()
                .filter(|d| d.alive && t >= d.active_at && d.dist(cx, cy) < 7.0)
                .map(Unit::reference)
                .collect();
            if foes.len() as f64 >= self.p("poison_min") || foes.iter()
                .any(|r| battle.unit(*r).is_hero) {
                let x = foes.iter().map(|r| battle.unit(*r).x).sum::<f64>() / foes.len() as f64;
                let y = foes.iter().map(|r| battle.unit(*r).y).sum::<f64>() / foes.len() as f64;
                self.use_spell(battle, "poison", x, y);
            }
        }
        self.learned_plays(battle, units, cx, cy, have);
    }

    // plans.py:991-1034: optional policy branches are preserved in full.
    fn learned_plays(
        &mut self,
        battle: &mut Battle,
        units: &[UnitRef],
        cx: f64,
        cy: f64,
        have: &impl Fn(&Self, &str) -> bool,
    ) {
        let t = battle.t;
        if self.p("angry_min") > 0.0
            && have(self, "angry")
            && t - self.last("angry") > 6.0 {
            let astray: Vec<_> = units.iter().copied().filter(|r| {
                let u = battle.unit(*r);
                u.target.is_some_and(|target| matches!(target, EntityRef::Building(_))
                    && !entity_is_defense(battle, target))
                    && battle.buildings.iter()
                    .any(|b| b.alive && b.weapon.is_some() && b.dist(u.x, u.y) < 7.0)
            }).collect();
            if astray.len() as f64 >= self.p("angry_min") {
                let (x, y) = centroid(battle, &astray);
                self.use_spell(battle, "angry", x, y);
            }
        }
        if self.p("skeleton_on") > 0.5
            && have(self, "skeleton")
            && t - self.last("skeleton") > 8.0 {
            for (id, _) in threats_near(battle, cx, cy, 12.0) {
                let b = battle.building(id);
                let w = b.weapon.as_ref().expect("weapon");
                if threat(&b.key, 0.0) >= 5.0 && w.target.is_some() && w.multi.is_empty() {
                    let (x, y) = (b.x + (cx - b.x) * 0.25, b.y + (cy - b.y) * 0.25);
                    self.use_spell(battle, "skeleton", x, y);
                    break;
                }
            }
        }
        if self.p("bat_on") > 0.5
            && have(self, "bat")
            && t - self.last("bat") > 6.0 {
            let hot = threats_near(battle, cx, cy, 10.0);
            if hot.len() >= 2 {
                let x = hot.iter()
                    .map(|(b, _)| battle.building(*b).x)
                    .sum::<f64>() / hot.len() as f64;
                let y = hot.iter()
                    .map(|(b, _)| battle.building(*b).y)
                    .sum::<f64>() / hot.len() as f64;
                self.use_spell(battle, "bat", x, y);
            }
        }
        let d_core = self.p("eq_core_dist");
        let n_eq = round_half_even(self.p("eq_core_n")) as i64;
        if d_core > 2.0
            && count(&self.spells, "eq") >= n_eq
            && self.last("eq_core") < 0.0 {
            if let Some(th) = battle.th.map(|id| battle.building(id)).filter(|b| b.alive) {
                if th.dist(cx, cy) <= d_core + 4.0 {
                    let (x, y) = (cx + (th.x - cx) * 0.6, cy + (th.y - cy) * 0.6);
                    for _ in 0..n_eq {
                        self.use_spell(battle, "eq", x, y);
                    }
                    self.cast_log.push((round_decimal(t, 1), "eq_core".to_owned()));
                }
            }
        }
        let reach = self.p("distract_reach");
        if reach > 2.0
            && self.distracts < round_half_even(self.p("distract_max")) as i64
            && t - self.last("distract") > 3.0 {
            for (id, d) in threats_near(battle, cx, cy, 16.0) {
                let b = battle.building(id);
                let w = b.weapon.as_ref().expect("weapon");
                if threat(&b.key, 0.0) >= self.p("distract_threat")
                    && w.range < d
                    && d <= w.range + reach {
                    let (x, y) = (b.x + (b.x - cx), b.y + (b.y - cy));
                    let Some(index) = self.cleanup.iter().position(|(_, n)| *n > 0) else {
                        break;
                    };
                    self.cleanup[index].1 -= 1;
                    let name = self.cleanup[index].0.clone();
                    let point = self.snipe_point(battle, x, y);
                    self.drop(battle, &name, point.0, point.1, "cleanup", 0.3);
                    self.distracts += 1;
                    self.cast_log.push((round_decimal(t, 1), "distract".to_owned()));
                    break;
                }
            }
        }
    }

    // plans.py:1043-1047.
    fn snipe_point(&mut self, battle: &mut Battle, x: f64, y: f64) -> (f64, f64) {
        if self.snipe_t != Some(battle.t) {
            self.snipe_points = (0..64)
                .map(|k| edge_point(battle, 2.0 * std::f64::consts::PI * k as f64 / 64.0, 0.0))
                .collect();
            self.snipe_points.extend(battle.inside_spots());
            self.snipe_t = Some(battle.t);
        }
        let mut best = self.snipe_points[0];
        let mut d = py_hypot(best.0 - x, best.1 - y);
        for &point in &self.snipe_points[1..] {
            let distance = py_hypot(point.0 - x, point.1 - y);
            if distance < d {
                best = point;
                d = distance;
            }
        }
        best
    }
}

// plans.py:140-157. Every trigonometric call uses CPython's C runtime.
pub fn edge_point(battle: &mut Battle, angle: f64, lateral: f64) -> (f64, f64) {
    let world = battle.catalog.world as f64;
    let center = world / 2.0;
    let (dx, dy) = (py_cos(angle), py_sin(angle));
    let (px, py) = (-dy, dx);
    let mut last = None;
    let mut r = world;
    while r > 0.0 {
        let x = center + px * lateral + dx * r;
        let y = center + py * lateral + dy * r;
        if 0.5 <= x && x < world - 0.5 && 0.5 <= y && y < world - 0.5 {
            if battle.can_deploy(x, y) {
                last = Some((x, y));
            } else if last.is_some() {
                break;
            }
        }
        r -= 0.5;
    }
    last.unwrap_or((
        (world - 1.0).min(1.0_f64.max(center + dx * 24.0)),
        (world - 1.0).min(1.0_f64.max(center + dy * 24.0)),
    ))
}

// plans.py:879-880.
pub fn main_units(battle: &Battle, group: &str) -> Vec<UnitRef> {
    battle.attackers_pool()
        .filter(|u| u.alive
        && u.group == group
        && u.name_id != Name::Totem
        && u.kind != Tag::Pet)
        .map(Unit::reference)
        .collect()
}

// plans.py:883-885.
pub fn centroid(battle: &Battle, units: &[UnitRef]) -> (f64, f64) {
    let w = units.iter().map(|r| battle.unit(*r).housing.max(1)).sum::<i64>() as f64;
    let x = units.iter().map(|r| {
        let u = battle.unit(*r);
        u.x * u.housing.max(1) as f64
    }).sum::<f64>() / w;
    let y = units.iter().map(|r| {
        let u = battle.unit(*r);
        u.y * u.housing.max(1) as f64
    }).sum::<f64>() / w;
    (x, y)
}

// plans.py:888-897.
pub fn threats_near(battle: &Battle, x: f64, y: f64, radius: f64) -> Vec<(BuildingId, f64)> {
    battle.buildings.iter().filter_map(|b| {
        if !b.alive || b.weapon.is_none() || b.disabled(battle.t) {
            return None;
        }
        let d = b.dist(x, y);
        (d <= radius).then_some((b.id, d))
    }).collect()
}

pub fn entity_is_defense(battle: &Battle, target: EntityRef) -> bool {
    matches!(target, EntityRef::Building(id) if battle.building(id).is_defense)
}

// plans.py:843-849.
pub fn fire_aimed(battle: &mut Battle, hero: UnitRef, target: BuildingId) {
    let u = battle.unit_mut(hero);
    let previous = (u.target, u.target_kind.clone());
    u.target = Some(EntityRef::Building(target));
    u.target_kind = Some(Tag::Building);
    heroes::activate(battle, hero);
    let u = battle.unit_mut(hero);
    u.target = previous.0;
    u.target_kind = previous.1;
}
