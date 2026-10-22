//! Ports playbook.py:63-69,113-681. Construction stays in Python.

use std::rc::Rc;

use crate::geom::py_hypot;
use crate::heroes;
use crate::json::Json;
use crate::plans::{self, count, flag, number, set, spell_key, spell_name, text, truth, AttackPlan};
use crate::state::*;
use crate::stats::Level;
use crate::trace::round_decimal;

const AIM_WAIT: f64 = 10.0;
const LATE: f64 = 150.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Action {
    Deploy,
    Spell,
    Ability,
    Recall,
    Redeploy,
    ReleaseSiege,
}

impl Action {
    fn parse(name: &str) -> Self {
        match name {
            "deploy" => Self::Deploy,
            "spell" => Self::Spell,
            "ability" => Self::Ability,
            "recall" => Self::Recall,
            "redeploy" => Self::Redeploy,
            "release_siege" => Self::ReleaseSiege,
            _ => panic!("unknown playbook action {name}"),
        }
    }
}

#[derive(Clone, Debug)]
pub enum Trigger {
    Always,
    All(Vec<Trigger>),
    Any(Vec<Trigger>),
    Time(f64),
    After(String, f64),
    Inside(String),
    GroupInside(String),
    NearTh(String, f64),
    HeavyFire(String, f64),
    HpBelow(String, f64),
    SpellsLeft(String, i64),
    Dead(String),
    DefendersNear(String),
    Destruction(f64),
}

impl Trigger {
    fn parse(w: &Json) -> Self {
        if !truth(w) {
            return Self::Always;
        }
        if let Some(parts) = w.get("all") {
            return Self::All(parts.arr().iter().map(Self::parse).collect());
        }
        if let Some(parts) = w.get("any") {
            return Self::Any(parts.arr().iter().map(Self::parse).collect());
        }
        if let Some(v) = w.get("t") {
            Self::Time(v.f64())
        } else if let Some(v) = w.get("after") {
            Self::After(v.str().to_owned(), number(w, "delay", 0.0))
        } else if let Some(v) = w.get("inside") {
            Self::Inside(v.str().to_owned())
        } else if let Some(v) = w.get("group_inside") {
            Self::GroupInside(v.str().to_owned())
        } else if let Some(v) = w.get("near_th") {
            Self::NearTh(v.str().to_owned(), number(w, "r", 8.0))
        } else if let Some(v) = w.get("heavy_fire") {
            Self::HeavyFire(v.str().to_owned(), number(w, "frac", 0.15))
        } else if let Some(v) = w.get("hp_below") {
            Self::HpBelow(v.str().to_owned(), number(w, "frac", 0.5))
        } else if let Some(v) = w.get("spells_left") {
            Self::SpellsLeft(spell_key(v.str()).unwrap_or(v.str()).to_owned(), number(w, "n", 0.0) as i64)
        } else if let Some(v) = w.get("dead") {
            Self::Dead(v.str().to_owned())
        } else if let Some(v) = w.get("defenders_near") {
            Self::DefendersNear(v.str().to_owned())
        } else if let Some(v) = w.get("destruction") {
            Self::Destruction(v.f64())
        } else {
            panic!("unknown trigger {w:?}");
        }
    }

    fn unit_condition(&self) -> Option<&str> {
        match self {
            Self::Inside(name) | Self::HeavyFire(name, _) | Self::HpBelow(name, _) => Some(name),
            _ => None,
        }
    }

    fn revive_names(&self, names: &mut Vec<String>) {
        match self {
            Self::Dead(name) => names.push(name.clone()),
            Self::All(parts) | Self::Any(parts) => {
                for part in parts {
                    part.revive_names(names);
                }
            }
            _ => {}
        }
    }
}

#[derive(Clone, Debug)]
pub struct Step {
    pub id: String,
    pub action: Action,
    pub what: Option<String>,
    pub count: Option<i64>,
    pub at: String,
    pub group: String,
    pub when: Trigger,
    pub every: Option<f64>,
    pub until: Option<Trigger>,
    pub spread: Option<f64>,
    pub level: Option<Level>,
    pub origin: Option<String>,
    pub aim: Option<String>,
    pub completion: bool,
    pub uncited: bool,
    pub skip_if_impossible: bool,
    pub source: Json,
}

impl Step {
    pub fn load(s: &Json) -> Self {
        Self {
            id: s.at("id").str().to_owned(),
            action: Action::parse(s.at("action").str()),
            what: s.get("what").and_then(Json::opt_str).map(str::to_owned),
            count: s.get("count")
                .filter(|v| !v.is_null()
                && !matches!(v, Json::Str(name) if name == "all"))
                .map(|v| {
                match v {
                    Json::Str(v) => v.parse().expect("integer step count"),
                    _ => v.f64() as i64,
                }
            }),
            at: text(s, "at", "edge:main").to_owned(),
            group: text(s, "group", "main").to_owned(),
            when: s.get("when").map_or(Trigger::Always, Trigger::parse),
            every: s.get("every").filter(|v| truth(v)).map(Json::f64),
            until: s.get("until").filter(|v| truth(v)).map(Trigger::parse),
            spread: s.get("spread").map(Json::f64),
            level: s.get("level").filter(|v| !v.is_null()).map(Level::from_json),
            origin: s.get("origin").and_then(Json::opt_str).map(str::to_owned),
            aim: s.get("aim").filter(|v| truth(v)).map(|v| v.str().to_owned()),
            completion: flag(s, "completion"),
            uncited: flag(s, "uncited"),
            skip_if_impossible: flag(s, "skip_if_impossible"),
            source: s.clone(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum HurtKey {
    Unit(UnitId),
    Engaged(String),
}

#[derive(Clone, Debug)]
pub enum HurtValue {
    History(Vec<(f64, f64)>),
    Since(f64),
}

#[derive(Clone, Debug)]
pub struct PlaybookPlan {
    pub attack: AttackPlan,
    pub steps: Rc<Vec<Step>>,
    pub inventory: Vec<(String, i64)>,
    pub flank_offset: f64,
    pub charge_side: String,
    pub done: Vec<(String, f64)>,
    pub next: Vec<(String, f64)>,
    pub hurt: Vec<(HurtKey, HurtValue)>,
    pub no_target: Vec<(String, f64)>,
    pub log_steps: Vec<(f64, String)>,
    pub deployed: Vec<String>,
    pub aim_since: Vec<(String, f64)>,
    pub last_alive: f64,
    pub busy_until: f64,
    pub next_fallback: f64,
    pub step_spells: Option<Vec<String>>,
    // All construction fields remain available for export inspection; runtime
    // branches above use typed fields rather than interpreting this snapshot.
    pub constructed: Rc<Json>,
}

impl PlaybookPlan {
    pub fn load(p: &Json) -> Self {
        assert_eq!(p.at("$type").str(), "PlaybookPlan");
        let hurt = p.at("_hurt").obj().iter().map(|(key, value)| {
            if let Some(group) = key.strip_prefix("engaged_since:") {
                (HurtKey::Engaged(group.to_owned()), HurtValue::Since(value.f64()))
            } else {
                let unit = UnitId(key.parse().expect("unit id in hurt history"));
                let history = value
                    .arr()
                    .iter()
                    .map(|v| (v.arr()[0].f64(), v.arr()[1].f64()))
                    .collect();
                (HurtKey::Unit(unit), HurtValue::History(history))
            }
        }).collect();
        Self {
            attack: AttackPlan::load(p),
            steps: Rc::new(p.at("steps").arr().iter().map(Step::load).collect()),
            inventory: plans::counts(p, "inventory"),
            flank_offset: p.at("flank_offset").f64(),
            charge_side: p.at("charge_side").str().to_owned(),
            done: plans::times(p, "_done"),
            next: plans::times(p, "_next"),
            hurt,
            no_target: plans::times(p, "_no_target"),
            log_steps: p.at("log_steps")
                .arr()
                .iter()
                .map(|v| (v.arr()[0].f64(), v.arr()[1].str().to_owned()))
                .collect(),
            deployed: p.get("_deployed")
                .map_or_else(Vec::new, |v| v.arr().iter().map(|v| v.str().to_owned()).collect()),
            aim_since: plans::times(p, "_aim_t"),
            last_alive: number(p, "_last_alive", 0.0),
            busy_until: number(p, "_busy_until", 0.0),
            next_fallback: number(p, "_next_fallback", 0.0),
            step_spells: p.get("_step_spells")
                .map(|v| v.arr().iter().map(|v| v.str().to_owned()).collect()),
            constructed: Rc::new(p.clone()),
        }
    }

    fn done(&self, id: &str) -> bool {
        self.done.iter().any(|(key, _)| key == id)
    }

    // playbook.py:113-117.
    pub fn has_pending(&self) -> bool {
        self.steps.iter()
            .any(|s| matches!(s.action, Action::Deploy | Action::Redeploy) && !self.done(&s.id))
    }

    // playbook.py:119-145.
    pub fn has_offensive_pending(&self, battle: &Battle) -> bool {
        if self.have("revive") && battle.attackers_pool()
            .any(|h| !h.alive && h.extra.revivable)
            && self.steps.iter()
            .any(|s| !self.done(&s.id)
            && s.action == Action::Spell
            && s.what.as_deref() == Some("Revive Spell")) {
            return true;
        }
        if battle.portal_units().iter().any(|r| battle.unit(*r).name != "Healer") {
            return true;
        }
        self.steps.iter().any(|s| {
            !self.done(&s.id)
                && s.action == Action::Deploy
                && s.what.as_deref() != Some("Healer")
                && s.what.as_deref()
                .is_some_and(|name| plans::is_hero(name) || count(&self.inventory, name) > 0)
        })
    }

    // playbook.py:148-154.
    fn edge_angle(&self, which: &str) -> f64 {
        let which = match which {
            "charge" => self.charge_side.as_str(),
            "funnel" => if self.charge_side == "left" {
                "right"
            } else {
                "left"
            },
            _ => which,
        };
        let offset = match which {
            "left" => -self.flank_offset,
            "right" => self.flank_offset,
            _ => 0.0,
        };
        self.attack.angle + offset
    }

    // playbook.py:156-157.
    fn edge(&self, battle: &mut Battle, which: &str) -> (f64, f64) {
        plans::edge_point(battle, self.edge_angle(which), 0.0)
    }

    // playbook.py:159-163.
    fn unit(&self, battle: &Battle, name: &str) -> Option<UnitRef> {
        battle.attackers_pool().find(|u| u.alive && u.name == name).map(Unit::reference)
    }

    // playbook.py:168-223: anchors retain first min/max ties.
    fn anchor(&self, battle: &mut Battle, at: &str) -> Option<(f64, f64)> {
        let (kind, arg) = at.split_once(':').unwrap_or((at, ""));
        match kind {
            "edge" => Some(self.edge(battle, arg)),
            "unit" => self.unit(battle, arg).map(|r| {
                let u = battle.unit(r);
                (u.x, u.y)
            }),
            "unit_ahead" => {
                let u = battle.unit(self.unit(battle, arg)?);
                let Some(target) = u.target.filter(|r| battle.entity_alive(*r)) else {
                    return Some((u.x, u.y));
                };
                let (x, y) = battle.entity_position(target);
                let (dx, dy) = (x - u.x, y - u.y);
                let d = py_hypot(dx, dy);
                let lead = 2.0_f64.min(d);
                Some(if d > 0.0 {
                    (u.x + dx / d * lead, u.y + dy / d * lead)
                } else {
                    (u.x, u.y)
                })
            }
            "group" => {
                let units = plans::main_units(battle, arg);
                (!units.is_empty()).then(|| plans::centroid(battle, &units))
            }
            "th" => battle.th.map(|id| battle.building(id)).filter(|b| b.alive).map(|b| (b.x, b.y)),
            "threat" => {
                let mut units = plans::main_units(battle, arg);
                if units.is_empty() {
                    units = plans::main_units(battle, "main");
                }
                if units.is_empty() {
                    return None;
                }
                let (x, y) = plans::centroid(battle, &units);
                let mut best = None;
                for (id, _) in plans::threats_near(battle, x, y, 12.0) {
                    let b = battle.building(id);
                    let w = b.weapon.as_ref().expect("weapon");
                    let score = plans::threat(&b.key, 1.0);
                    if (w.target.is_some()
                        || !w.multi.is_empty())
                        && best.is_none_or(|(s, _)| score > s) {
                        best = Some((score, id));
                    }
                }
                best.map(|(_, id)| {
                    let b = battle.building(id);
                    (b.x, b.y)
                })
            }
            "defenders" => {
                let units = plans::main_units(battle, if arg.is_empty() {
                    "main"
                } else {
                    arg
                });
                if units.is_empty() {
                    return None;
                }
                let (x, y) = plans::centroid(battle, &units);
                let defenders: Vec<_> = battle.defenders_pool()
                    .filter(|u| u.alive && u.target.is_some() && u.dist(x, y) <= 8.0)
                    .map(Unit::reference)
                    .collect();
                (!defenders.is_empty()).then(|| plans::centroid(battle, &defenders))
            }
            "building" => {
                let mut units = plans::main_units(battle, "main");
                if units.is_empty() {
                    units = battle.attackers_pool()
                        .filter(|u| u.alive)
                        .map(Unit::reference)
                        .collect();
                }
                let (x, y) = if !units.is_empty() {
                    plans::centroid(battle, &units)
                } else if let Some(th) = battle.th {
                    let b = battle.building(th);
                    (b.x, b.y)
                } else {
                    let center = battle.catalog.world as f64 / 2.0;
                    (center, center)
                };
                let mut best = None;
                let mut distance = f64::INFINITY;
                for b in &battle.buildings {
                    if b.alive && b.key == arg {
                        let d = b.dist(x, y);
                        if best.is_none() || d < distance {
                            best = Some((b.x, b.y));
                            distance = d;
                        }
                    }
                }
                best
            }
            _ => panic!("unknown anchor {at}"),
        }
    }

    // playbook.py:226-231.
    fn inside(&self, battle: &mut Battle, unit: UnitRef) -> bool {
        let u = battle.unit(unit);
        let (x, y) = (u.x as i32, u.y as i32);
        let blocked = battle.live_no_deploy();
        [-2, 0, 2].iter().all(|dx| [-2, 0, 2].iter().all(|dy| blocked.contains(&(x + dx, y + dy))))
    }

    // playbook.py:233-239.
    fn heavy_fire(&self, battle: &Battle, unit: UnitRef, fraction: f64) -> bool {
        let u = battle.unit(unit);
        let history = self.hurt.iter().find(|(key, _)| *key == HurtKey::Unit(u.id));
        let recent = history.and_then(|(_, value)| {
            if let HurtValue::History(history) = value {
                history.iter()
                    .filter(|(t, _)| battle.t - t <= 2.0)
                    .map(|(_, hp)| *hp)
                    .reduce(f64::max)
            } else {
                None
            }
        });
        let lost = recent.map_or(0.0, |hp| hp - u.hp);
        let locked = battle.buildings.iter().any(|b| {
            b.alive && plans::threat(&b.key, 0.0) >= 4.0 && b.weapon.as_ref()
                .is_some_and(|w| w.target == Some(unit) || w.multi.contains(&unit))
        });
        lost >= fraction * u.max_hp || locked
    }

    // playbook.py:241-249.
    fn down(&self, battle: &Battle, name: &str) -> bool {
        self.deployed.iter().any(|n| n == name) && self.unit(battle, name).is_none()
            && !battle.portal_units().iter().any(|r| battle.unit(*r).name == name)
            && (plans::is_hero(name) || count(&self.inventory, name) <= 0)
    }

    // playbook.py:251-260.
    fn impossible(&self, battle: &Battle, trigger: &Trigger) -> bool {
        match trigger {
            Trigger::All(parts) => parts.iter().any(|part| self.impossible(battle, part)),
            Trigger::Any(parts) => parts.iter().all(|part| self.impossible(battle, part)),
            _ => trigger.unit_condition().is_some_and(|name| self.down(battle, name)),
        }
    }

    // playbook.py:262-283.
    fn fallen(&self, battle: &Battle, step: &Step) -> Option<UnitRef> {
        let mut names = Vec::new();
        if let Some(name) = step.at.strip_prefix("unit:")
            .or_else(|| step.at.strip_prefix("unit_ahead:")) {
            names.push(name.to_owned());
        }
        step.when.revive_names(&mut names);
        let mut best = None;
        let mut last = 0.0;
        for u in battle.attackers_pool() {
            if u.is_hero
                && !u.alive
                && u.extra.revivable
                && (names.is_empty()
                || names.contains(&u.name)) {
                let at = u.extra.ko_at.unwrap_or(0.0);
                if best.is_none() || at > last {
                    best = Some(u.reference());
                    last = at;
                }
            }
        }
        best
    }

    // playbook.py:286-347: recursive triggers short circuit in Python order.
    fn ready(&mut self, battle: &mut Battle, trigger: &Trigger, relax: bool) -> bool {
        match trigger {
            Trigger::Always => true,
            Trigger::All(parts) => parts.iter().all(|part| self.ready(battle, part, relax)),
            Trigger::Any(parts) => {
                let parts: Vec<_> = parts.iter()
                    .filter(|part| !(relax && self.impossible(battle, part)))
                    .collect();
                parts.is_empty() || parts.iter().any(|part| self.ready(battle, part, relax))
            }
            _ if relax && trigger.unit_condition()
                .is_some_and(|name| self.down(battle, name)) => true,
            Trigger::Time(t) => battle.t >= *t,
            Trigger::After(id, delay) => self.done.iter()
                .find(|(key, _)| key == id)
                .is_some_and(|(_, at)| battle.t >= at + delay),
            Trigger::Inside(name) => self.unit(battle, name)
                .is_some_and(|u| self.inside(battle, u)),
            Trigger::GroupInside(group) => {
                let units = plans::main_units(battle, group);
                if units.is_empty() {
                    return false;
                }
                let needed = 1.max(units.len() / 2);
                let inside = units.iter().filter(|r| self.inside(battle, **r)).count();
                if inside >= needed {
                    return true;
                }
                let engaged = units.iter().filter(|r| {
                    let u = battle.unit(**r);
                    u.target.is_some_and(|r| battle.entity_alive(r)
                        && !matches!(r, EntityRef::Unit(_)))
                        && u.cooldown > 0.0
                }).count();
                let key = HurtKey::Engaged(group.clone());
                if engaged >= needed {
                    let index = if let Some(index) = self.hurt.iter().position(|(k, _)| *k == key) {
                        index
                    } else {
                        self.hurt.push((key, HurtValue::Since(battle.t)));
                        self.hurt.len() - 1
                    };
                    let HurtValue::Since(since) = &self.hurt[index].1 else {
                        panic!("engagement clock")
                    };
                    battle.t - *since >= 3.0
                } else {
                    self.hurt.retain(|(k, _)| *k != key);
                    false
                }
            }
            Trigger::NearTh(group, radius) => {
                let units = plans::main_units(battle, group);
                if units.is_empty() {
                    return false;
                }
                let Some(th) = battle.th else {
                    return false;
                };
                let (x, y) = plans::centroid(battle, &units);
                let th = battle.building(th);
                !th.alive || py_hypot(x - th.x, y - th.y) <= *radius
            }
            Trigger::HeavyFire(name, fraction) => battle.attackers_pool()
                .any(|u| u.alive
                && u.name == *name
                && self.heavy_fire(battle, u.reference(), *fraction)),
            Trigger::HpBelow(name, fraction) => self.unit(battle, name).is_some_and(|r| {
                let u = battle.unit(r);
                u.hp < fraction * u.max_hp
            }),
            Trigger::SpellsLeft(key, n) => count(&self.attack.spells, key) <= *n,
            Trigger::Dead(name) => self.unit(battle, name)
                .is_none() && self.deployed.contains(name) && !battle.portal_units()
                .iter()
                .any(|r| battle.unit(*r).name == *name),
            Trigger::DefendersNear(group) => self.anchor(battle, &format!("defenders:{group}"))
                .is_some(),
            Trigger::Destruction(amount) => battle.destruction() as f64 >= *amount,
        }
    }

    // playbook.py:350-377.
    fn deploy(&mut self, battle: &mut Battle, step: &Step, position: (f64, f64)) -> bool {
        let what = step.what.as_deref().expect("deploy name");
        if plans::is_hero(what) {
            if self.deployed.iter().any(|name| name == what) {
                return false;
            }
            self.attack.drop(battle, what, position.0, position.1, &step.group, 0.3);
            self.deployed.push(what.to_owned());
            return true;
        }
        let left = count(&self.inventory, what);
        let n = step.count.map_or(left, |n| left.min(n));
        if n <= 0 {
            return false;
        }
        if let Some(edge) = step.at.strip_prefix("edge:")
            .filter(|_| n >= 3
            && step.spread.is_none()
            && !matches!(what, "Healer" | "Wall Breaker")) {
            let angle = self.edge_angle(edge);
            let width = ((n - 1) as f64).min(8.0);
            for i in 0..n {
                let (x, y) = plans::edge_point(battle, angle, -width / 2.0 + width * i as f64 / (n - 1) as f64);
                self.attack.drop(battle, what, x, y, &step.group, 0.3);
            }
        } else {
            for _ in 0..n {
                self.attack.drop(battle, what, position.0, position.1, &step.group, step.spread.unwrap_or(1.0));
            }
        }
        set(&mut self.inventory, what.to_owned(), left - n);
        if !self.deployed.iter().any(|name| name == what) {
            self.deployed.push(what.to_owned());
        }
        true
    }

    // playbook.py:623-633.
    fn have(&self, kind: &str) -> bool {
        count(&self.attack.spells, kind) > 0
    }

    // playbook.py:379-391.
    fn spell(&mut self, battle: &mut Battle, step: &Step, position: (f64, f64)) -> bool {
        let name = if step.action == Action::Recall {
            "Recall Spell"
        } else {
            step.what.as_deref().unwrap_or("")
        };
        let Some(kind) = spell_key(name) else {
            return false;
        };
        if !self.have(kind) {
            return false;
        }
        self.attack.cast_spell(
            battle,
            spell_name(kind),
            position.0,
            position.1,
            step.level.as_ref(),
            step.origin.as_deref(),
        );
        true
    }

    // playbook.py:393-419.
    fn ability(&mut self, battle: &mut Battle, step: &Step) -> bool {
        let Some(hero) = self.unit(battle, step.what.as_deref().expect("ability hero")) else {
            return false;
        };
        let u = battle.unit(hero);
        if u.kit.is_none() || u.ability_used {
            return false;
        }
        if let Some(key) = step.aim.as_deref().and_then(|aim| aim.strip_prefix("building:")) {
            if self.aim_building(battle, hero, key) {
                return true;
            }
            let since = entry_time(&mut self.aim_since, &step.id, battle.t);
            if battle.t - since >= AIM_WAIT {
                heroes::activate(battle, hero);
                return true;
            }
            return false;
        }
        if let Some(aim) = &step.aim {
            if let Some(target) = self.attack.aim(battle, hero, aim) {
                plans::fire_aimed(battle, hero, target);
                return true;
            }
            return false;
        }
        heroes::activate(battle, hero);
        true
    }

    // playbook.py:421-469: Giant Arrow line-up and nearest-defense Fireball.
    fn aim_building(&self, battle: &mut Battle, hero: UnitRef, key: &str) -> bool {
        let u = battle.unit(hero);
        let (ux, uy) = (u.x, u.y);
        let mut target = None;
        let mut closest = f64::INFINITY;
        for b in &battle.buildings {
            if b.alive && b.key == key {
                let d = b.dist(ux, uy);
                if target.is_none() || d < closest {
                    target = Some(b.id);
                    closest = d;
                }
            }
        }
        let Some(target) = target else {
            heroes::activate(battle, hero);
            return true;
        };
        let kit = u.kit.as_ref().expect("hero kit");
        if kit.has("Giant Arrow") {
            let mut best = None;
            for b in &battle.buildings {
                let d = b.dist(ux, uy);
                if !b.alive || b.key != key || d > self.attack.p("arrow_reach") {
                    continue;
                }
                let (dx, dy) = (b.x - ux, b.y - uy);
                let norm = py_hypot(dx, dy);
                let norm = if norm == 0.0 {
                    1.0
                } else {
                    norm
                };
                let hits = battle.buildings.iter().filter(|o| {
                    if !o.alive || o.key != key {
                        return false;
                    }
                    let along = ((o.x - ux) * dx + (o.y - uy) * dy) / norm;
                    let off = ((o.x - ux) * dy - (o.y - uy) * dx).abs() / norm;
                    along > 0.0 && off <= o.half_hit + 1.0
                }).count();
                if best.is_none_or(|(h, neg_d, _)| (hits, -d) > (h, neg_d)) {
                    best = Some((hits, -d, b.id));
                }
            }
            let Some((_, _, id)) = best else {
                return false;
            };
            plans::fire_aimed(battle, hero, id);
            return true;
        }
        if kit.has("Fireball") {
            let level = kit.lv("Fireball").clone();
            let mut near = None;
            let mut closest = f64::INFINITY;
            for candidate in heroes::targets(battle, true) {
                let d = heroes::distance(battle, candidate, ux, uy);
                if near.is_none() || d < closest {
                    near = Some(candidate);
                    closest = d;
                }
            }
            let Some(near) = near else {
                return false;
            };
            let (x, y) = battle.entity_position(near);
            let radius = heroes::col(battle, "Fireball", &level, &["damage radius"], 0.0);
            if battle.building(target).edge_distance(x, y) > radius {
                return false;
            }
            heroes::activate(battle, hero);
            return true;
        }
        heroes::activate(battle, hero);
        true
    }

    // playbook.py:471-501.
    fn cannot(&self, battle: &Battle, step: &Step) -> Option<String> {
        let what = step.what.as_deref().unwrap_or("");
        let target = if what != "Revive Spell" {
            step.at.strip_prefix("unit:")
                .or_else(|| step.at.strip_prefix("unit_ahead:"))
        } else {
            None
        };
        let target = target.or_else(|| (step.action == Action::Ability).then_some(what));
        if let Some(target) = target.filter(|name| !name.is_empty() && self.down(battle, name)) {
            return Some(format!("{target} down"));
        }
        if step.action == Action::Deploy {
            return (plans::is_hero(what)


                && self.deployed.iter().any(|name| name == what)).then(|| format!("{what} already deployed"));
        }
        if self.impossible(battle, &step.when) {
            return Some("waits on a unit that is down".to_owned());
        }
        match step.action {
            Action::Spell | Action::Recall => {
                let key = if step.action == Action::Recall {
                    Some("recall")
                } else {
                    spell_key(what)
                };
                if let Some(key) = key.filter(|key| count(&self.attack.spells, key) <= 0) {
                    return Some(format!("no {} left", spell_name(key)));
                }
                if let Some(key) = step.at.strip_prefix("building:") {
                    if !battle.buildings.iter().any(|b| b.alive && b.key == key) {
                        return Some(format!("{key} gone"));
                    }
                }
                if step.at == "th"
                    && battle.th.is_none_or(|id| !battle.building(id).alive) {
                    return Some("Town Hall gone".to_owned());
                }
            }
            Action::Ability => {
                if self.unit(battle, what).is_some_and(|r| {
                    let u = battle.unit(r);
                    u.kit.is_none() || u.ability_used
                }) {
                    return Some("ability already used".to_owned());
                }
            }
            Action::Redeploy => {
                if battle.portal_stash.is_empty()
                    && count(&self.attack.spells, "recall") <= 0
                    && battle.t - self.attack.last("recall") > 5.0 {
                    return Some("nothing recalled".to_owned());
                }
            }
            _ => {}
        }
        None
    }

    // playbook.py:503-606: skip pass, cited steps, completion steps, late drops.
    pub fn on_tick(&mut self, battle: &mut Battle) {
        let t = battle.t;
        if (t * 10.0) as i64 % 5 == 0 {
            for u in battle.attackers_pool() {
                if u.alive && (u.is_hero || u.housing >= 5) {
                    let key = HurtKey::Unit(u.id);
                    let index = if let Some(index) = self.hurt.iter().position(|(k, _)| *k == key) {
                        index
                    } else {
                        self.hurt.push((key, HurtValue::History(Vec::new())));
                        self.hurt.len() - 1
                    };
                    let HurtValue::History(history) = &mut self.hurt[index].1 else {
                        panic!("unit HP history")
                    };
                    history.push((t, u.hp));
                    if history.len() > 8 {
                        history.remove(0);
                    }
                }
            }
        }
        if battle.attackers_pool()
            .any(|u| u.alive
            && u.name != "Totem"
            && !matches!(u.kind.as_str(), "pet" | "siege_idle")) {
            self.last_alive = t;
        }
        let stalled = t - self.last_alive > 3.0;
        let steps = self.steps.clone();
        for step in steps.iter() {
            if !self.done(&step.id) {
                if let Some(why) = self.cannot(battle, step) {
                    set(&mut self.done, step.id.clone(), t);
                    self.log_steps.push((round_decimal(t, 1), format!("{} (skipped: {why})", step.id)));
                }
            }
        }
        let order = steps.iter()
            .filter(|s| !(s.completion || s.uncited))
            .chain(steps.iter().filter(|s| s.completion || s.uncited));
        for step in order {
            if t < self.busy_until {
                break;
            }
            let done = self.done(&step.id);
            if done && step.every.is_none() {
                continue;
            }
            let mut forced = false;
            if step.every.is_some() && done {
                let next = self.next.iter()
                    .find(|(id, _)| id == &step.id)
                    .map_or(0.0, |(_, at)| *at);
                if t < next || step.until.as_ref()
                    .is_some_and(|until| self.ready(battle, until, false)) {
                    continue;
                }
            } else if !self.ready(battle, &step.when, false) {
                forced = step.action == Action::Deploy
                    && (stalled
                    || t >= LATE
                    || self.impossible(battle, &step.when)
                    && self.ready(battle, &step.when, true));
                if !forced {
                    continue;
                }
            }
            let before = count(&self.inventory, step.what.as_deref().unwrap_or(""));
            let ok = match step.action {
                Action::ReleaseSiege => crate::units::release_siege(battle, step.what.as_deref()),
                Action::Ability => self.ability(battle, step),
                _ => {
                    let mut position = if step.what.as_deref() == Some("Revive Spell") {
                        self.fallen(battle, step).map(|r| {
                            let u = battle.unit(r);
                            (u.x, u.y)
                        })
                    } else {
                        self.anchor(battle, &step.at)
                    };
                    if position.is_none() && forced {
                        position = Some(self.edge(battle, "main"));
                    }
                    let Some(position) = position else {
                        if matches!(step.action, Action::Spell | Action::Recall)
                            && step.what.as_deref() != Some("Revive Spell")
                            && !self.done(&step.id) {
                            let since = entry_time(&mut self.no_target, &step.id, t);
                            if t - since >= AIM_WAIT {
                                set(&mut self.done, step.id.clone(), t);
                                self.log_steps.push((round_decimal(t, 1), format!("{} (skipped: no target)", step.id)));
                            }
                        }
                        continue;
                    };
                    match step.action {
                        Action::Deploy => self.deploy(battle, step, position),
                        Action::Spell | Action::Recall => self.spell(battle, step, position),
                        Action::Redeploy if !battle.portal_stash.is_empty()
                            && t >= battle.portal_ready_at => {
                            heroes::portal_redeploy(battle, position.0, position.1);
                            true
                        }
                        _ => false,
                    }
                }
            };
            if ok {
                let n = if step.action == Action::Deploy {
                    1.max(before - count(&self.inventory, step.what.as_deref().unwrap_or("")))
                } else {
                    1
                };
                self.busy_until = t + action_time(battle, step.action, n);
            }
            if ok || step.skip_if_impossible {
                if !self.done(&step.id) {
                    set(&mut self.done, step.id.clone(), t);
                    self.log_steps.push((round_decimal(t, 1), step.id.clone()));
                }
                if let Some(every) = step.every {
                    set(&mut self.next, step.id.clone(), t + every);
                }
            }
        }
        if t >= LATE && t >= self.busy_until {
            let left = self.inventory.iter().find(|(name, n)| {
                *n > 0 && !self.steps.iter()
                    .any(|s| s.action == Action::Deploy
                    && !self.done(&s.id)
                    && s.what.as_ref() == Some(name))
            }).map(|(name, n)| (name.clone(), *n));
            if let Some((name, n)) = left {
                let step = Step::load(&Json::Obj(vec![
                    ("id".to_owned(), Json::Str(format!("late-{name}"))),
                    ("action".to_owned(), Json::Str("deploy".to_owned())),
                    ("what".to_owned(), Json::Str(name.clone())),
                    ("at".to_owned(), Json::Str("edge:main".to_owned())),
                ]));
                let point = self.edge(battle, "main");
                self.deploy(battle, &step, point);
                self.busy_until = t + action_time(battle, Action::Deploy, n);
                self.log_steps.push((round_decimal(t, 1), format!("late-{name}")));
            }
        }
        self.fallback_spells(battle);
    }

    // playbook.py:609-621.
    fn step_kinds(&mut self) {
        if self.step_spells.is_some() {
            return;
        }
        let mut kinds = Vec::new();
        for s in self.steps.iter() {
            let kind = match s.action {
                Action::Recall => Some("recall"),
                Action::Spell => s.what.as_deref().and_then(spell_key),
                _ => None,
            };
            if let Some(kind) = kind {
                if !kinds.iter().any(|k| k == kind) {
                    kinds.push(kind.to_owned());
                }
            }
        }
        self.attack.auto_revive = !kinds.iter().any(|k| k == "revive");
        self.step_spells = Some(kinds);
    }

    // playbook.py:635-681. Revive runs before fallback reservation mode.
    fn fallback_spells(&mut self, battle: &mut Battle) {
        self.step_kinds();
        let t = battle.t;
        if t < self.next_fallback || t < self.busy_until {
            return;
        }
        self.next_fallback = t + 0.5;
        if self.attack.auto_revive {
            let fallen: Vec<_> = battle.attackers_pool()
                .filter(|u| !u.alive && u.extra.revivable)
                .map(Unit::reference)
                .collect();
            for hero in fallen {
                let u = battle.unit(hero);
                if self.have("revive")
                    && t >= u.extra.ko_at.expect("KO time") + self.attack.revive_delay {
                    let (x, y) = (u.x, u.y);
                    self.attack.use_spell(battle, "revive", x, y);
                }
            }
        }
        if !battle.portal_stash.is_empty() && t >= battle.portal_ready_at && !self.steps.iter()
            .any(|s| s.action == Action::Redeploy && !self.done(&s.id)) {
            let (x, y) = self.attack.portal_point(battle);
            heroes::portal_redeploy(battle, x, y);
            self.busy_until = t + action_time(battle, Action::Redeploy, 1);
            return;
        }
        let units = plans::main_units(battle, "main");
        if units.is_empty() {
            return;
        }
        let kinds = self.step_spells.as_ref().expect("step kinds").clone();
        let reservations: Vec<_> = kinds.iter().map(|kind| {
            let mine: Vec<_> = self.steps.iter().filter(|s| {
                s.action == Action::Recall
                    && kind == "recall"
                    || s.action == Action::Spell
                    && s.what.as_deref()
                    .and_then(spell_key) == Some(kind.as_str())
            }).collect();
            let repeat = mine.iter().any(|s| s.every.is_some());
            let n = mine.iter().filter(|s| !self.done(&s.id)).count() as i64;
            (kind.clone(), if repeat {
                i64::MAX
            } else {
                n
            })
        }).collect();
        let have = |attack: &AttackPlan, kind: &str| count(&attack.spells, kind) > count(&reservations, kind);
        let left = self.attack.spells.iter()
            .chain(&self.attack.cc_spells)
            .map(|(_, n)| n)
            .sum::<i64>();
        if !self.attack.zap_done && self.attack.zap_ad != (0, 0) {
            self.attack.zap(battle, &have);
        }
        self.attack.generic_spells(battle, &units, &have);
        let cast = left - self.attack.spells.iter()
            .map(|(_, n)| n)
            .sum::<i64>() - self.attack.cc_spells.iter()
            .map(|(_, n)| n)
            .sum::<i64>();
        if cast > 0 {
            self.busy_until = t + cast as f64 * action_time(battle, Action::Spell, 1);
        }
        let held: Vec<_> = battle.attackers_pool().filter(|u| {
            u.alive && u.is_hero && !u.ability_used && self.steps.iter()
                .any(|s| s.action == Action::Ability
                && !self.done(&s.id)
                && s.what.as_ref() == Some(&u.name))
        }).map(Unit::reference).collect();
        for &hero in &held {
            battle.unit_mut(hero).ability_used = true;
        }
        self.attack.hero_abilities(battle);
        for hero in held {
            battle.unit_mut(hero).ability_used = false;
        }
    }
}

fn entry_time(times: &mut Vec<(String, f64)>, key: &str, t: f64) -> f64 {
    if let Some((_, since)) = times.iter().find(|(name, _)| name == key) {
        return *since;
    }
    times.push((key.to_owned(), t));
    t
}

// playbook.py:64-70: pace is part of the exported environment, not Rust's env.
fn action_time(battle: &Battle, action: Action, n: i64) -> f64 {
    match action {
        Action::Deploy => battle.pace * (battle.pace_switch + battle.pace_tap * n as f64),
        Action::Ability => battle.pace * battle.pace_ability,
        _ => battle.pace * battle.pace_switch,
    }
}
