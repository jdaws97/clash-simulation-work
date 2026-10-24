//! Ports playbook.py:63-69,114-770. Construction stays in Python.

use std::cell::Cell;
use std::rc::Rc;

use crate::geom::py_hypot;
use crate::heroes;
use crate::json::Json;
use crate::labels::{Name, Tag};
use crate::plans::{self, count, flag, number, set, spell_key, spell_name, text, truth, AttackPlan};
use crate::shared::SharedVec;
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
    pub inventory: SharedVec<(String, i64)>,
    pub flank_offset: f64,
    pub charge_side: String,
    pub done: SharedVec<(String, f64)>,
    pub next: SharedVec<(String, f64)>,
    pub cancelled: SharedVec<String>,
    pub hurt: SharedVec<(HurtKey, HurtValue)>,
    // Lookup-only hints, validated against hurt after engagement-key removal.
    hurt_indices: SharedVec<Option<usize>>,
    pub no_target: SharedVec<(String, f64)>,
    pub log_steps: SharedVec<(f64, String)>,
    pub deployed: SharedVec<String>,
    pub aim_since: SharedVec<(String, f64)>,
    pub last_alive: f64,
    charge_edge: Cell<Option<(f64, f64)>>,
    pub next_fallback: f64,
    pub step_spells: Option<Rc<Vec<String>>>,
    pub equipment_steps: SharedVec<(String, Option<String>)>,
    pub ad_reservations: SharedVec<(String, Vec<BuildingId>)>,
    // Immutable construction inputs remain available for export inspection.
    // Runtime fields have typed storage above and do not belong in this snapshot.
    pub constructed: Rc<Json>,
}

impl PlaybookPlan {
    pub fn load(p: &Json) -> Self {
        assert_eq!(p.at("$type").str(), "PlaybookPlan");
        let hurt: Vec<_> = p.at("_hurt").obj().iter().map(|(key, value)| {
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
            inventory: plans::counts(p, "inventory").into(),
            flank_offset: p.at("flank_offset").f64(),
            charge_side: p.at("charge_side").str().to_owned(),
            done: plans::times(p, "_done").into(),
            next: plans::times(p, "_next").into(),
            cancelled: p.get("_cancelled").map_or_else(SharedVec::default, |v| {
                v.arr().iter().map(|v| v.str().to_owned()).collect()
            }),
            hurt: hurt.into(),
            hurt_indices: SharedVec::default(),
            no_target: plans::times(p, "_no_target").into(),
            log_steps: p.at("log_steps")
                .arr()
                .iter()
                .map(|v| (v.arr()[0].f64(), v.arr()[1].str().to_owned()))
                .collect(),
            deployed: p.get("_deployed")
                .map_or_else(SharedVec::default, |v| v.arr().iter().map(|v| v.str().to_owned()).collect()),
            aim_since: plans::times(p, "_aim_t").into(),
            last_alive: number(p, "_last_alive", 0.0),
            charge_edge: Cell::new(p.get("_charge_edge").map(|v| (v.arr()[0].f64(), v.arr()[1].f64()))),
            next_fallback: number(p, "_next_fallback", 0.0),
            step_spells: p.get("_step_spells")
                .map(|v| Rc::new(v.arr().iter().map(|v| v.str().to_owned()).collect())),
            equipment_steps: p.get("_equipment_steps").map_or_else(SharedVec::default, |v| {
                v.obj().iter().map(|(id, names)| {
                    (id.clone(), names.arr().first().map(|name| name.str().to_owned()))
                }).collect()
            }),
            ad_reservations: p.get("_ad_reservations").map_or_else(SharedVec::default, |v| {
                v.obj().iter().map(|(id, buildings)| {
                    (id.clone(), buildings.arr().iter().map(|b| BuildingId(b.usize())).collect())
                }).collect()
            }),
            constructed: Rc::new(Json::Obj(
                p.obj()
                    .iter()
                    .filter(|(name, _)| {
                        !name.starts_with('_')
                            && !matches!(name.as_str(), "inventory" | "snipe_log" | "auto_revive")
                    })
                    .cloned()
                    .collect(),
            )),
        }
    }

    fn done(&self, id: &str) -> bool {
        self.done.iter().any(|(key, _)| key == id)
    }

    // playbook.py:121-143 (port2.diff): only aimed abilities and siege releases reserve tools.
    pub(crate) fn sync_scouting(&mut self, battle: &Battle) {
        let mut context = plans::ScoutingContext {
            inventory: self.inventory.iter().cloned().collect(),
            ..plans::ScoutingContext::default()
        };
        let steps = self.steps.clone();
        for step in steps.iter() {
            if step.action == Action::Deploy {
                if let Some(name) = &step.what {
                    if !context.roles.iter().any(|(hero, _)| hero == name) {
                        context.roles.push((name.clone(), step.group.clone()));
                    }
                    if !self.done(&step.id) && !self.cancelled(&step.id) {
                        context.pending_heroes.push(name.clone());
                    }
                }
            }
            let cancelled = self.cancelled(&step.id);
            let done = self.done(&step.id);
            if step.action == Action::Spell && !cancelled && !done {
                if let Some(kind) = step.what.as_deref().and_then(spell_key) {
                    let n = count(&context.pending_spells, kind) + 1;
                    set(&mut context.pending_spells, kind.to_owned(), n);
                }
            }
            if !cancelled {
                let kind = if step.action == Action::Recall {
                    Some("recall")
                } else if step.action == Action::Spell {
                    step.what.as_deref().and_then(spell_key)
                } else {
                    None
                };
                if let Some(kind) = kind {
                    let old = count(&context.reservations, kind);
                    let n = if step.every.is_some() || old == i64::MAX {
                        i64::MAX
                    } else {
                        old + i64::from(!done)
                    };
                    set(&mut context.reservations, kind.to_owned(), n);
                }
            }
            if Self::ad_target_count(step) > 0 && !done && !cancelled
                && self.missing_equipment(battle, step, None).is_none()
            {
                context.reserve_lightning = true;
            }
            if cancelled || done && step.every.is_none() || step.completion || step.uncited {
                continue;
            }
            for name in [
                "Archer Queen",
                "Royal Champion",
                "Flame Flinger",
                "Dragon Duke",
                "Grand Warden",
            ] {
                let reserves = name == "Flame Flinger" && step.action == Action::ReleaseSiege
                    && step.what.as_deref().is_none_or(|what| what == name);
                // playbook.py:_snipe_available: a cited ability, or a step
                // anchored on the hero (its Healers, Invisibility), keeps it.
                let ability = step.action == Action::Ability
                    && step.what.as_deref() == Some(name);
                let suffix = format!(":{name}");
                let anchored = step.at.ends_with(&suffix)
                    || step.aim.as_deref().is_some_and(|aim| aim.ends_with(&suffix));
                if reserves || ability || anchored {
                    if !context.unavailable.iter().any(|tool| tool == name) {
                        context.unavailable.push(name.to_owned());
                    }
                }
            }
        }
        self.attack.scouting_context = Some(context);
    }

    pub fn deployments(&mut self, battle: &mut Battle) -> Vec<Deployment> {
        self.sync_scouting(battle);
        let out = self.attack.opening_deployments(battle);
        if self.attack.scouting_context
            .as_ref()
            .is_some_and(|context| context.used_spell_reservations.get())
        {
            // Scouting calls the same lazy _have/_step_kinds path as Python.
            self.step_kinds();
        }
        self.deployed = self.attack.snipe_deployed.clone();
        // playbook.py:109-116: dict replacement keeps the last opening time per name.
        let mut opened = Vec::new();
        for deployment in &out {
            if self.attack.snipe_deployed.contains(&deployment.name) {
                set(&mut opened, deployment.name.clone(), deployment.time);
            }
        }
        for step in self.steps.iter() {
            if step.action != Action::Deploy {
                continue;
            }
            if let Some((_, time)) = opened
                .iter()
                .find(|(name, _)| step.what.as_ref() == Some(name))
            {
                entry_time(&mut self.done, &step.id, *time);
                self.log_steps.push((
                    round_decimal(*time, 1),
                    format!("{} (opened on a snipe)", step.id),
                ));
            }
        }
        for deployment in &out {
            if !plans::is_hero(&deployment.name) {
                let remaining = count(&self.inventory, &deployment.name) - 1;
                set(&mut self.inventory, deployment.name.clone(), remaining);
            }
        }
        self.sync_scouting(battle);
        out
    }

    fn cancelled(&self, id: &str) -> bool {
        self.cancelled.iter().any(|key| key == id)
    }

    // playbook.py:672-678: explicit pending or repeating Revives retain control.
    fn auto_revive(&self) -> bool {
        !self.steps.iter().any(|step| {
            step.action == Action::Spell
                && step.what.as_deref() == Some("Revive Spell")
                && !self.cancelled(&step.id)
                && (!self.done(&step.id) || step.every.is_some())
        })
    }

    // playbook.py:114-125: undeployed reserves keep the battle running.
    pub fn has_pending(&self) -> bool {
        self.inventory.iter().any(|(_, n)| *n != 0)
            || self.steps.iter().any(|s| {
                matches!(s.action, Action::Deploy | Action::Redeploy) && !self.done(&s.id)
            })
    }

    // playbook.py:127-165.
    pub fn has_offensive_pending(&self, battle: &Battle) -> bool {
        // Read the current _step_kinds result even before the first fallback
        // tick; this query runs through an immutable Battle snapshot.
        let auto_revive = self.auto_revive();
        if self.have("revive")
            && battle.attackers_pool().any(|h| !h.alive && h.extra.revivable)
            && (auto_revive
                || self.steps.iter().any(|s| {
                    (!self.done(&s.id) || s.every.is_some())
                        && !self.cancelled(&s.id)
                        && s.action == Action::Spell
                        && s.what.as_deref() == Some("Revive Spell")
                }))
        {
            return true;
        }
        if battle.portal_units().any(|r| battle.unit(r).name_id != Name::Healer) {
            return true;
        }
        // playbook.py:149-153: skipped non-healing reserves still need deployment.
        if self
            .inventory
            .iter()
            .any(|(name, n)| name != "Healer" && *n > 0)
        {
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
        if which == "charge" && self.steps.iter().any(|step| step.action == Action::Deploy
            && step.what.as_deref().is_some_and(plans::is_hero) && step.group == "charge")
        {
            if let Some(point) = self.charge_edge.get() {
                return point;
            }
            let point = self.attack.charge_point(battle, self.edge_angle(which), 0.0);
            self.charge_edge.set(Some(point));
            return point;
        }
        plans::edge_point(battle, self.edge_angle(which), 0.0)
    }

    // playbook.py:159-163.
    fn unit(&self, battle: &Battle, name: &str) -> Option<UnitRef> {
        battle.attackers_pool().find(|u| {
            u.alive && u.name == name && u.kind != Tag::HeroClone
        }).map(Unit::reference)
    }

    // playbook.py:168-223: anchors retain first min/max ties.
    fn anchor(&self, battle: &mut Battle, at: &str, unclaimed: bool) -> Option<(f64, f64)> {
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
                    // playbook.py:218-226: hidden firing defenses are unavailable.
                    if !battle.building_targetable(id) || unclaimed && self.attack.snipe_claimed.contains(&id) {
                        continue;
                    }
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
                    if b.alive && b.key == arg && !(unclaimed && self.attack.snipe_claimed.contains(&b.id)) {
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

    // playbook.py:250-302: redirect within the anchor family, retaining first ties.
    fn totem_anchor(
        &self,
        battle: &Battle,
        at: &str,
        position: (f64, f64),
    ) -> Option<(f64, f64)> {
        if !self.attack.totem_covered(battle, position.0, position.1) {
            return Some(position);
        }
        let (kind, arg) = at.split_once(':').unwrap_or((at, ""));
        if kind == "defenders" {
            let group = plans::main_units(
                battle,
                if arg.is_empty() { "main" } else { arg },
            );
            if group.is_empty() {
                return None;
            }
            let (cx, cy) = plans::centroid(battle, &group);
            let foes: Vec<_> = battle
                .defenders_pool()
                .filter(|unit| {
                    unit.alive
                        && unit.target.is_some()
                        && py_hypot(unit.x - cx, unit.y - cy) <= 8.0
                        && !self.attack.totem_covered(battle, unit.x, unit.y)
                })
                .collect();
            let mut best: Option<(f64, (f64, f64))> = None;
            for unit in foes {
                let distance = py_hypot(unit.x - position.0, unit.y - position.1);
                if best.is_none_or(|(previous, _)| distance < previous) {
                    best = Some((distance, (unit.x, unit.y)));
                }
            }
            return best.map(|(_, point)| point);
        }
        let threats = if matches!(kind, "threat" | "group") {
            let mut group = plans::main_units(battle, arg);
            if kind == "threat" && group.is_empty() {
                group = plans::main_units(battle, "main");
            }
            if group.is_empty() {
                return None;
            }
            let (cx, cy) = plans::centroid(battle, &group);
            let mut threats = plans::threats_near(battle, cx, cy, 12.0);
            if kind == "threat" {
                threats.retain(|&(id, _)| {
                    let weapon = battle.building(id).weapon.as_ref().expect("weapon");
                    weapon.target.is_some() || !weapon.multi.is_empty()
                });
            }
            threats
        } else {
            let radius = plans::totem_radius(battle);
            plans::threats_near(battle, position.0, position.1, radius)
        };
        let mut best: Option<((f64, f64), BuildingId)> = None;
        for (id, _, score) in self.attack.totem_targets(battle, &threats) {
            let building = battle.building(id);
            let key = (
                py_hypot(building.x - position.0, building.y - position.1),
                -score,
            );
            if best.is_none_or(|(previous, _)| key < previous) {
                best = Some((key, id));
            }
        }
        best.map(|(_, id)| {
            let building = battle.building(id);
            (building.x, building.y)
        })
    }

    // playbook.py:226-231.
    fn inside(&self, battle: &mut Battle, unit: UnitRef) -> bool {
        let u = battle.unit(unit);
        let (x, y) = (u.x as i32, u.y as i32);
        battle.live_no_deploy();
        [-2, 0, 2].iter().all(|dx| {
            [-2, 0, 2].iter().all(|dy| battle.no_deploy_tile(x + dx, y + dy))
        })
    }

    // playbook.py:233-239.
    fn heavy_fire(&self, battle: &Battle, unit: UnitRef, fraction: f64) -> bool {
        let u = battle.unit(unit);
        let history = self.hurt_index(u.id).map(|index| &self.hurt[index]);
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

    fn hurt_index(&self, unit: UnitId) -> Option<usize> {
        if let Some(index) = self.hurt_indices.get(unit.0).copied().flatten() {
            if self
                .hurt
                .get(index)
                .is_some_and(|(key, _)| *key == HurtKey::Unit(unit))
            {
                return Some(index);
            }
        }
        self.hurt
            .iter()
            .position(|(key, _)| *key == HurtKey::Unit(unit))
    }

    // playbook.py:241-249.
    fn down(&self, battle: &Battle, name: &str) -> bool {
        self.deployed.iter().any(|n| n == name) && self.unit(battle, name).is_none()
            && !battle.portal_units().any(|r| {
                let u = battle.unit(r);
                u.name == name && u.kind != Tag::HeroClone
            })
            && !battle.deployments[battle.next_deploy..].iter().any(|d| d.name == name)
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
                if !relax {
                    return parts.is_empty()
                        || parts.iter().any(|part| self.ready(battle, part, false));
                }
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
                    // Avoid cloning every HP history through SharedVec when
                    // the engagement clock is already absent.
                    if self.hurt.iter().any(|(k, _)| *k == key) {
                        self.hurt.retain(|(k, _)| *k != key);
                    }
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
                && u.kind != Tag::HeroClone
                && self.heavy_fire(battle, u.reference(), *fraction)),
            Trigger::HpBelow(name, fraction) => self.unit(battle, name).is_some_and(|r| {
                let u = battle.unit(r);
                u.hp < fraction * u.max_hp
            }),
            Trigger::SpellsLeft(key, n) => count(&self.attack.spells, key) <= *n,
            Trigger::Dead(name) => self.unit(battle, name)
                .is_none() && self.deployed.contains(name) && !battle.portal_units()
                .any(|r| {
                    let u = battle.unit(r);
                    u.name == *name && u.kind != Tag::HeroClone
                }),
            Trigger::DefendersNear(group) => self.anchor(battle, &format!("defenders:{group}"), false)
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
            let at = text(&step.source, "at", "edge:charge");
            let backpack = what == "Dragon Duke" && self.attack.has_backpack(battle)
                && matches!(at, "edge:charge" | "edge:funnel")
                && !flag(&step.source, "at_cite");
            let position = if backpack {
                self.attack.backpack_point(battle, self.edge_angle(at.split_once(':').expect("edge anchor").1), 0.0)
            } else {
                position
            };
            let time = battle.t;
            self.attack.drop_fixed_at(battle, what, position.0, position.1, &step.group, 0.3, time, backpack);
            self.deployed.push(what.to_owned());
            return true;
        }
        let left = count(&self.inventory, what);
        let n = step.count.map_or(left, |n| left.min(n));
        if n <= 0 {
            return false;
        }
        let tap = battle.pace_tap * battle.pace;
        let started = battle.t;
        if let Some(edge) = step.at.strip_prefix("edge:")
            .filter(|_| n >= 3
            && step.spread.is_none()
            && !matches!(what, "Healer" | "Wall Breaker")) {
            let angle = self.edge_angle(edge);
            let width = ((n - 1) as f64).min(8.0);
            for i in 0..n {
                let (x, y) = plans::edge_point(battle, angle, -width / 2.0 + width * i as f64 / (n - 1) as f64);
                self.attack.drop_at(
                    battle,
                    what,
                    x,
                    y,
                    &step.group,
                    0.3,
                    started + i as f64 * tap,
                );
            }
        } else {
            for i in 0..n {
                self.attack.drop_at(
                    battle,
                    what,
                    position.0,
                    position.1,
                    &step.group,
                    step.spread.unwrap_or(1.0),
                    started + i as f64 * tap,
                );
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

    // playbook.py:456-521: requirements come only from the action, not citations.
    fn missing_equipment(
        &mut self,
        battle: &Battle,
        step: &Step,
        unit: Option<UnitRef>,
    ) -> Option<String> {
        let what = step.what.as_deref().unwrap_or("");
        if !self.equipment_steps.iter().any(|(id, _)| id == &step.id) {
            let action = step.source.get("ability")
                .filter(|value| truth(value))
                .map_or(step.id.as_str(), Json::str)
                .replace('_', " ")
                .to_lowercase();
            let mut required = step.source.get("equipment")
                .filter(|value| truth(value))
                .map(|value| value.str().to_owned())
                .or_else(|| {
                    battle.catalog.stats.registry.obj().iter()
                        .find(|(name, record)| {
                            record.at("kind").str() == "equipment"
                                && record.get("attrs")
                                    .and_then(|attrs| attrs.get("raw"))
                                    .and_then(|raw| raw.get("User"))
                                    .and_then(Json::opt_str) == Some(what)
                                && action.contains(&name.to_lowercase())
                        })
                        .map(|(name, _)| name.clone())
                });
            let aliases: &[(&str, &str)] = match what {
                "Archer Queen" => &[
                    ("arrow", "Giant Arrow"),
                    ("queen shot", "Giant Arrow"),
                    ("healers out", "Healer Puppet"),
                ],
                "Grand Warden" => &[("tome", "Eternal Tome"), ("torch", "Heroic Torch")],
                "Royal Champion" => &[("spear", "Rocket Spear")],
                "Dragon Duke" => &[
                    ("backpack", "Rocket Backpack"),
                    ("jetpack", "Rocket Backpack"),
                    ("blaster", "Stun Blaster"),
                    ("stun", "Stun Blaster"),
                ],
                _ => &[],
            };
            for &(word, equipment) in aliases {
                if action.contains(word) && required.is_none() {
                    required = Some(equipment.to_owned());
                }
            }
            let aim = step.aim.as_deref().unwrap_or("");
            if !flag(&step.source, "equipment") {
                if aim == "arrow" || aim.starts_with("building:") && what == "Archer Queen" {
                    required = Some("Giant Arrow".to_owned());
                } else if aim == "dash" {
                    required = Some("Rocket Backpack".to_owned());
                } else if aim.starts_with("building:") && what == "Grand Warden" {
                    required = Some("Fireball".to_owned());
                }
            }
            self.equipment_steps.push((step.id.clone(), required));
        }
        let required = self.equipment_steps.iter()
            .find(|(id, _)| id == &step.id)
            .and_then(|(_, required)| required.as_ref())?;
        let loadout = self.attack.loadouts.iter()
            .find(|(name, _)| name == what)
            .map(|(_, loadout)| loadout.clone())
            .or_else(|| heroes::default_loadout(battle, what));
        let equipped = unit.and_then(|reference| battle.unit(reference).kit.as_ref())
            .map(|kit| kit.equip.as_slice())
            .or_else(|| loadout.as_ref().map(|loadout| loadout.equipment.as_slice()))
            .unwrap_or(&[]);
        (!equipped.contains(required)
            || self.attack.account_equipment
                && !self.attack.equipment_levels.iter().any(|(name, _)| name == required))
            .then(|| required.clone())
    }

    // playbook.py:523-559: reserve only aimed damaging abilities and cited counts.
    fn ad_target_count(step: &Step) -> usize {
        if step.action != Action::Ability {
            return 0;
        }
        let what = step.what.as_deref().unwrap_or("");
        let equipment = match what {
            "Archer Queen" => "Giant Arrow",
            "Grand Warden" => "Fireball",
            _ => return 0,
        };
        let aim = step.aim.as_deref().unwrap_or("");
        if !matches!(aim, "arrow" | "building:ad")
            || aim == "arrow" && what != "Archer Queen"
            || step.source.get("equipment")
                .is_some_and(|value| value.opt_str() != Some(equipment))
        {
            return 0;
        }
        let quotes = ["aim_cite", "cite"].iter()
            .flat_map(|key| step.source.get(key).into_iter().flat_map(Json::arr))
            .map(|cite| text(cite, "quote", ""))
            .collect::<Vec<_>>()
            .join(" ")
            .to_lowercase();
        if aim != "building:ad" && !quotes.contains("air defense") {
            return 0;
        }
        let mut count: usize = 1;
        for (word, number) in [
            ("two", 2),
            ("three", 3),
            ("four", 4),
            ("both", 2),
            ("both those", 2),
            ("couple of", 2),
        ] {
            if quotes.contains(&format!("{word} air defenses")) {
                count = count.max(number);
            }
        }
        count
    }

    // playbook.py:702-818: automatic aim shares the step's original deadline.
    fn ability(&mut self, battle: &mut Battle, step: &Step) -> bool {
        let Some(hero) = self.unit(battle, step.what.as_deref().expect("ability hero")) else {
            return false;
        };
        let u = battle.unit(hero);
        if u.kit.is_none() || u.ability_used
            || self.missing_equipment(battle, step, Some(hero)).is_some()
        {
            return false;
        }
        self.sync_scouting(battle);
        let since = entry_time(&mut self.aim_since, &step.id, battle.t);
        let deadline = since + AIM_WAIT;
        if battle.t >= deadline {
            return self.attack.fire_aimed(battle, hero, Some(deadline));
        }
        let u = battle.unit(hero);
        let kit = u.kit.as_ref().expect("hero kit");
        let fireball = kit.has("Fireball");
        let line = kit.has("Giant Arrow") || kit.has("Rocket Backpack");
        let champion = u.name_id == Name::RoyalChampion
            && (kit.has("Rocket Spear") || kit.has("Seeking Shield"));
        if Self::ad_target_count(step) > 0 && !fireball
            && !battle.buildings.iter().any(|b| b.alive && b.key == "ad")
        {
            return false;
        }
        if let Some(key) = step.aim.as_deref().and_then(|aim| aim.strip_prefix("building:")) {
            if self.aim_building(battle, hero, key, Some(deadline), 1) {
                return true;
            }
            if battle.t - since >= AIM_WAIT {
                return self.attack.fire_aimed(battle, hero, Some(deadline));
            }
            return false;
        }
        if step.aim.as_deref() == Some("arrow") && Self::ad_target_count(step) > 0 {
            if self.aim_building(battle, hero, "ad", Some(deadline), Self::ad_target_count(step)) {
                return true;
            }
            if battle.t >= deadline {
                return self.attack.fire_aimed(battle, hero, Some(deadline));
            }
            return false;
        }
        if line {
            return self.attack.line_ability(battle, hero, false, Some(deadline));
        }
        if let Some(aim) = &step.aim {
            if self.attack.aim_cluster(battle, hero, aim) {
                return self.attack.fire_aimed(battle, hero, Some(deadline));
            }
            return false;
        }
        if fireball || champion {
            return self.attack.cluster_ability(battle, hero, false);
        }
        heroes::activate(battle, hero, false);
        true
    }

    fn aim_building(&mut self, battle: &mut Battle, hero: UnitRef, key: &str, deadline: Option<f64>, count: usize) -> bool {
        let u = battle.unit(hero);
        let (ux, uy) = (u.x, u.y);
        let target = battle.buildings.iter().filter(|b| b.alive && b.key == key)
            .min_by(|a, b| a.dist(ux, uy).total_cmp(&b.dist(ux, uy))).map(|b| b.id);
        let kit = u.kit.as_ref().expect("hero kit");
        let Some(target) = target else {
            if kit.has("Fireball") || u.name_id == Name::RoyalChampion
                && (kit.has("Rocket Spear") || kit.has("Seeking Shield"))
            {
                return self.attack.cluster_ability(battle, hero, false);
            }
            if key == "ad" {
                return false;
            }
            if kit.has("Giant Arrow") {
                return self.attack.line_ability(battle, hero, false, deadline);
            }
            heroes::activate(battle, hero, false);
            return true;
        };
        if kit.has("Giant Arrow") {
            let Some((band, effect)) = self.attack.ability_band(battle, hero) else {
                return false;
            };
            let hits = battle.buildings.iter().filter(|b| b.key == key
                && battle.building_targetable(b.id) && plans::band_hit(b, band, &effect.kind, effect.radius)).count();
            if hits >= count {
                return self.attack.fire_aimed(battle, hero, deadline);
            }
            return false;
        }
        if kit.has("Fireball") {
            let level = kit.lv("Fireball");
            let near = heroes::targets(battle, true).into_iter().min_by(|a, b| {
                heroes::distance(battle, *a, ux, uy).total_cmp(&heroes::distance(battle, *b, ux, uy))
            });
            let Some(near) = near else {
                return false;
            };
            let (x, y) = battle.entity_position(near);
            let radius = heroes::col(battle, "Fireball", level, &["damage radius"], 0.0);
            if battle.building(target).edge_distance(x, y) > radius {
                return false;
            }
            heroes::activate(battle, hero, false);
            return true;
        }
        heroes::activate(battle, hero, false);
        true
    }

    // playbook.py:471-501.
    fn cannot(&mut self, battle: &Battle, step: &Step) -> Option<String> {
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
        let holding = step.action == Action::Ability && self.aim_since.iter().any(|(id, _)| id == &step.id);
        if !holding && self.impossible(battle, &step.when) {
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
                let hero = self.unit(battle, what);
                if let Some(missing) = self.missing_equipment(battle, step, hero) {
                    return Some(format!("missing {missing}"));
                }
                if self.unit(battle, what).is_some_and(|r| {
                    let u = battle.unit(r);
                    u.kit.is_none() || u.ability_used
                }) {
                    return Some("ability already used".to_owned());
                }
                if Self::ad_target_count(step) > 0
                    && what != "Grand Warden"
                    && !battle.buildings.iter().any(|b| b.alive && b.key == "ad")
                {
                    return Some("ad gone".to_owned());
                }
            }
            Action::Redeploy => {
                if battle.portal_stash.is_empty()
                    && count(&self.attack.spells, "recall") <= 0
                    && battle.t - self.attack.last("recall") > 5.0 {
                    return Some("nothing recalled".to_owned());
                }
            }
            Action::ReleaseSiege => {
                let name = step
                    .what
                    .as_deref()
                    .filter(|name| !name.is_empty())
                    .or(self.attack.siege.as_deref())
                    .unwrap_or("");
                if count(&self.inventory, name) <= 0
                    && !battle.attackers_pool().any(|unit| {
                        unit.alive
                            && unit.kind == Tag::Siege
                            && step.what.as_deref().is_none_or(|what| unit.name == what)
                    })
                    && !battle.deployments[battle.next_deploy..]
                        .iter()
                        .any(|entry| entry.name == name)
                {
                    return Some("no siege left".to_owned());
                }
            }
            _ => {}
        }
        None
    }

    // playbook.py:527-661: skip pass, cited steps, completion steps, rescue drops.
    pub fn on_tick(&mut self, battle: &mut Battle) {
        let t = battle.t;
        self.sync_scouting(battle);
        self.attack.opening_actions(battle);
        if (t * 10.0) as i64 % 5 == 0 {
            // Keep Python history order, but reuse dense unit-id hints rather
            // than rebuilding a hash map for every sampling pass. A removed
            // engagement clock can shift indices, so hurt_index validates.
            for u in battle.attackers_pool() {
                if u.alive && (u.is_hero || u.housing >= 5) {
                    let index = if let Some(index) = self.hurt_index(u.id) {
                        index
                    } else {
                        let index = self.hurt.len();
                        self.hurt
                            .push((HurtKey::Unit(u.id), HurtValue::History(Vec::new())));
                        index
                    };
                    if self.hurt_indices.len() <= u.id.0 {
                        self.hurt_indices.resize(u.id.0 + 1, None);
                    }
                    if self.hurt_indices[u.id.0] != Some(index) {
                        self.hurt_indices[u.id.0] = Some(index);
                    }
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
            && u.name_id != Name::Totem
            && !matches!(u.kind, Tag::Pet | Tag::SiegeIdle)) {
            self.last_alive = t;
        }
        let stalled = t - self.last_alive > 3.0;
        let steps = self.steps.clone();
        for step in steps.iter() {
            if self.cancelled(&step.id) {
                continue;
            }
            if !self.done(&step.id) || step.every.is_some() {
                let mut why = self.cannot(battle, step);
                if why.is_none()
                    && step.every.is_some()
                    && step
                        .until
                        .as_ref()
                        .is_some_and(|until| self.ready(battle, until, false))
                {
                    why = Some("until reached".to_owned());
                }
                if let Some(why) = why {
                    entry_time(&mut self.done, &step.id, t);
                    self.cancelled.push(step.id.clone());
                    self.log_steps.push((
                        round_decimal(t, 1),
                        format!("{} (skipped: {why})", step.id),
                    ));
                }
            }
        }
        // playbook.py:570-572: opening Lightning precedes deployment actions.
        if !self.attack.zap_done && self.attack.zap_ad != (0, 0) {
            self.fallback_spells(battle, true);
        }
        let order = steps.iter()
            .filter(|s| !(s.completion || s.uncited))
            .chain(steps.iter().filter(|s| s.completion || s.uncited));
        for step in order {
            if t < self.attack.busy_until {
                break;
            }
            let done = self.done(&step.id);
            if self.cancelled(&step.id) || done && step.every.is_none() {
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
            } else if !(step.action == Action::Ability && self.aim_since.iter().any(|(id, _)| id == &step.id))
                && !self.ready(battle, &step.when, false) {
                forced = step.action == Action::Deploy
                    && (stalled
                    || t >= LATE
                    || self.impossible(battle, &step.when)
                    && self.ready(battle, &step.when, true));
                if !forced {
                    continue;
                }
            }
            let what = step.what.as_deref().unwrap_or("");
            if step.action == Action::Deploy
                && !plans::is_hero(what)
                && count(&self.inventory, what) <= 0
            {
                if !self.done(&step.id) {
                    self.done.push((step.id.clone(), t));
                }
                self.cancelled.push(step.id.clone());
                self.log_steps.push((
                    round_decimal(t, 1),
                    format!("{} (skipped: no {what} left)", step.id),
                ));
                continue;
            }
            let before = count(&self.inventory, what);
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
                        self.anchor(battle, &step.at, step.action == Action::Spell)
                    };
                    if position.is_none() && forced {
                        position = Some(self.edge(battle, "main"));
                    }
                    // playbook.py:839-851: wait when every suitable Totem area is covered.
                    let mut totem_covered = false;
                    if step.action == Action::Spell
                        && step.what.as_deref() == Some("Totem Spell")
                    {
                        if let Some(point) = position {
                            position = self.totem_anchor(battle, &step.at, point);
                            totem_covered = position.is_none();
                        }
                    }
                    let Some(position) = position else {
                        if matches!(step.action, Action::Spell | Action::Recall)
                            && step.what.as_deref() != Some("Revive Spell")
                        {
                            let since = entry_time(&mut self.no_target, &step.id, t);
                            if totem_covered && t == since {
                                self.log_steps.push((
                                    round_decimal(t, 1),
                                    format!("{} (waiting: Totem area covered)", step.id),
                                ));
                            }
                            if t - since >= AIM_WAIT {
                                entry_time(&mut self.done, &step.id, t);
                                self.cancelled.push(step.id.clone());
                                let why = if totem_covered {
                                    "Totem area covered"
                                } else {
                                    "no target"
                                };
                                self.log_steps.push((
                                    round_decimal(t, 1),
                                    format!("{} (skipped: {why})", step.id),
                                ));
                            }
                        }
                        continue;
                    };
                    self.no_target.retain(|(id, _)| id != &step.id);
                    match step.action {
                        Action::Deploy => self.deploy(battle, step, position),
                        Action::Spell | Action::Recall => self.spell(battle, step, position),
                        Action::Redeploy if !battle.portal_stash.is_empty()
                            && t >= battle.portal_ready_at => {
                            let recalled: Vec<_> = battle.portal_units().collect();
                            for unit in recalled {
                                battle.unit_mut(unit).group = step.group.clone();
                            }
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
                self.attack.busy_until = t + action_time(battle, step.action, n);
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
        if t >= self.attack.busy_until {
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
                self.attack.busy_until = t + action_time(battle, Action::Deploy, n);
                self.log_steps.push((round_decimal(t, 1), format!("late-{name}")));
            }
        }
        self.fallback_spells(battle, false);
    }

    // playbook.py:664-679: cache spell kinds, refresh auto-revive every time.
    fn step_kinds(&mut self) {
        if self.step_spells.is_none() {
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
            // a Python set, exported sorted; only membership matters
            kinds.sort();
            self.step_spells = Some(Rc::new(kinds));
        }
        self.attack.auto_revive = self.auto_revive();
    }

    // playbook.py:876-927: retain per-step reservations while the ability can fire.
    fn reserved_ads(&mut self, battle: &mut Battle) -> Vec<BuildingId> {
        let mut reserved = Vec::new();
        let steps = self.steps.clone();
        for step in steps.iter() {
            let count = Self::ad_target_count(step);
            if count == 0 || self.done(&step.id) || self.cancelled(&step.id) {
                continue;
            }
            let what = step.what.as_deref().expect("aimed hero ability");
            let hero = self.unit(battle, what);
            if self.missing_equipment(battle, step, hero).is_some()
                || hero.is_some_and(|hero| {
                    let unit = battle.unit(hero);
                    unit.kit.is_none() || unit.ability_used
                })
            {
                continue;
            }
            if hero.is_none()
                && !steps.iter().any(|step| {
                    step.action == Action::Deploy
                        && step.what.as_deref() == Some(what)
                        && !self.done(&step.id)
                        && !self.cancelled(&step.id)
                })
                && !battle.deployments[battle.next_deploy..].iter().any(|d| d.name == what)
            {
                continue;
            }
            if !self.ad_reservations.iter().any(|(id, _)| id == &step.id) {
                let at = steps.iter()
                    .find(|step| {
                        step.action == Action::Deploy && step.what.as_deref() == Some(what)
                    })
                    .map_or("edge:main", |step| step.at.as_str());
                let position = self.anchor(battle, at, false)
                    .unwrap_or_else(|| self.edge(battle, "main"));
                let mut ads: Vec<_> = battle.buildings.iter()
                    .filter(|b| b.alive && b.key == "ad" && !reserved.contains(&b.id))
                    .map(|b| b.id)
                    .collect();
                ads.sort_by(|a, b| {
                    battle.building(*a).dist(position.0, position.1)
                        .total_cmp(&battle.building(*b).dist(position.0, position.1))
                });
                ads.truncate(count);
                self.ad_reservations.push((step.id.clone(), ads));
            }
            let ads = &self.ad_reservations.iter()
                .find(|(id, _)| id == &step.id)
                .expect("AD reservation")
                .1;
            for &id in ads {
                if !reserved.contains(&id) {
                    reserved.push(id);
                }
            }
        }
        reserved
    }

    // playbook.py:929-1015: opening zap, spare Lightning, Revive, other support.
    fn fallback_spells(&mut self, battle: &mut Battle, opening: bool) {
        self.step_kinds();
        let t = battle.t;
        if t < self.next_fallback || t < self.attack.busy_until {
            return;
        }
        self.next_fallback = t + 0.5;
        let kinds = self.step_spells.as_ref().expect("step kinds");
        let reservations: Vec<_> = kinds
            .iter()
            .map(|kind| {
                let mine = self.steps.iter().filter(|s| {
                    !self.cancelled(&s.id)
                        && (s.action == Action::Recall && kind == "recall"
                            || s.action == Action::Spell
                                && s.what.as_deref().and_then(spell_key) == Some(kind.as_str()))
                });
                let mut repeat = false;
                let mut n = 0;
                for step in mine {
                    repeat |= step.every.is_some();
                    n += i64::from(!self.done(&step.id));
                }
                (kind.clone(), if repeat { i64::MAX } else { n })
            })
            .collect();
        let have = |attack: &AttackPlan, kind: &str| {
            count(&attack.spells, kind) > count(&reservations, kind)
        };
        if !self.attack.zap_done && self.attack.zap_ad != (0, 0) {
            let left = self.attack.spells.iter().map(|(_, n)| n).sum::<i64>();
            let reserved = self.reserved_ads(battle);
            self.attack.zap(battle, &have, true, &reserved);
            if self.attack.spells.iter().map(|(_, n)| n).sum::<i64>() < left {
                self.attack.busy_until = t + action_time(battle, Action::Spell, 1);
                return;
            }
        }
        if opening {
            return;
        }
        let lightning_reserved = count(&reservations, "lightning");
        self.sync_scouting(battle);
        self.attack.fallback = true;
        let cast = self.attack.spare_lightning_cluster(battle) || self.attack.spare_quake(battle);
        self.attack.fallback = false;
        if cast {
            self.attack.busy_until = t + action_time(battle, Action::Spell, 1);
            return;
        }
        let before_revive = self.attack.cast_log.len();
        self.attack.revive_knocked_out(
            battle,
            &|attack, kind| count(&attack.spells, kind) > 0,
            true,
        );
        if self.attack.cast_log.len() > before_revive {
            self.attack.busy_until = t + action_time(battle, Action::Spell, 1);
            return;
        }
        if !battle.portal_stash.is_empty() && t >= battle.portal_ready_at && !self.steps.iter()
            .any(|s| s.action == Action::Redeploy && !self.done(&s.id)) {
            let (x, y) = self.attack.portal_point(battle);
            heroes::portal_redeploy(battle, x, y);
            self.attack.busy_until = t + action_time(battle, Action::Redeploy, 1);
            return;
        }
        let mut units = plans::main_units(battle, "main");
        if units.is_empty() {
            units = self.attack.cargo_support(battle).unwrap_or_default();
            if units.is_empty() {
                return;
            }
        }
        let left = self.attack.spells.iter()
            .map(|(_, n)| n)
            .sum::<i64>();
        if !self.attack.fallback_quakes.is_empty() {
            let (x, y) = self.attack.fallback_quakes.remove(0);
            if have(&self.attack, "eq") {
                self.attack.use_spell(battle, "eq", x, y);
            }
        }
        if self.attack.spells.iter().map(|(_, n)| n).sum::<i64>() == left {
            self.sync_scouting(battle);
            self.attack.fallback = true;
            self.attack.generic_spells(
                battle,
                &units,
                &have,
                Some(&mut self.inventory),
                true,
                lightning_reserved,
            );
            self.attack.fallback = false;
        }
        if self.attack.spells.iter().map(|(_, n)| n).sum::<i64>() < left {
            self.attack.busy_until = t + action_time(battle, Action::Spell, 1);
            return;
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
        self.sync_scouting(battle);
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
pub fn action_time(battle: &Battle, action: Action, n: i64) -> f64 {
    match action {
        Action::Deploy => battle.pace * (battle.pace_switch + battle.pace_tap * n as f64),
        Action::Ability => battle.pace * battle.pace_ability,
        _ => battle.pace * battle.pace_switch,
    }
}
