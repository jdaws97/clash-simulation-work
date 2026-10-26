//! Ports playbook.py:63-69,114-770. Construction stays in Python.

use std::cell::Cell;
use std::rc::Rc;

use crate::geom::py_hypot;
use crate::heroes;
use crate::json::Json;
use crate::labels::{Name, Tag};
use crate::plans::{
    self, count, flag, number, set, spell_key, spell_name, text, truth, AttackPlan,
};
use crate::shared::SharedVec;
use crate::state::*;
use crate::stats::Level;
use crate::trace::round_decimal;

#[cfg(test)]
#[path = "playbook_tests.rs"]
mod tests;

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
    EffectActive(String),
    EffectExpired(String),
    ObjectiveState(String, String),
    NamedDefenders(String, String),
    CohortAbsent(String),
    Succeeded(String),
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
        if let Some(v) = w.get("succeeded") {
            Self::Succeeded(v.str().to_owned())
        } else if let Some(v) = w.get("cohort_absent") {
            Self::CohortAbsent(v.str().to_owned())
        } else if let Some(v) = w.get("effect_active") {
            Self::EffectActive(v.str().to_owned())
        } else if let Some(v) = w.get("effect_expired") {
            Self::EffectExpired(v.str().to_owned())
        } else if let Some(v) = w.get("objective") {
            Self::ObjectiveState(v.str().to_owned(), text(w, "state", "alive").to_owned())
        } else if let Some(v) = w.get("defender") {
            Self::NamedDefenders(v.str().to_owned(), text(w, "group", "main").to_owned())
        } else if let Some(v) = w.get("t") {
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
            Self::SpellsLeft(
                spell_key(v.str()).unwrap_or(v.str()).to_owned(),
                number(w, "n", 0.0) as i64,
            )
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
    fn spell_kind(&self) -> Option<&str> {
        match self.action {
            Action::Spell => self.what.as_deref().and_then(spell_key),
            Action::Recall => Some("recall"),
            _ => None,
        }
    }

    pub fn load(s: &Json) -> Self {
        Self {
            id: s.at("id").str().to_owned(),
            action: Action::parse(s.at("action").str()),
            what: s.get("what").and_then(Json::opt_str).map(str::to_owned),
            count: s
                .get("count")
                .filter(|v| !v.is_null() && !matches!(v, Json::Str(name) if name == "all"))
                .map(|v| match v {
                    Json::Str(v) => v.parse().expect("integer step count"),
                    _ => v.f64() as i64,
                }),
            at: text(s, "at", "edge:main").to_owned(),
            group: text(s, "group", "main").to_owned(),
            when: s.get("when").map_or(Trigger::Always, Trigger::parse),
            every: s.get("every").filter(|v| truth(v)).map(Json::f64),
            until: s.get("until").filter(|v| truth(v)).map(Trigger::parse),
            spread: s.get("spread").map(Json::f64),
            level: s
                .get("level")
                .filter(|v| !v.is_null())
                .map(Level::from_json),
            origin: s.get("origin").and_then(Json::opt_str).map(str::to_owned),
            aim: s
                .get("aim")
                .filter(|v| truth(v))
                .map(|v| v.str().to_owned()),
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
    entered: SharedVec<String>,
    charge_closed: bool,
    pub deployed: SharedVec<String>,
    pub aim_since: SharedVec<(String, f64)>,
    pub last_alive: f64,
    charge_edge: Cell<Option<(f64, f64)>>,
    pub next_fallback: f64,
    pub step_spells: Option<Rc<Vec<String>>>,
    pub equipment_steps: SharedVec<(String, Vec<String>)>,
    pub ad_reservations: SharedVec<(String, Vec<BuildingId>)>,
    siege_landings: SharedVec<(String, (f64, f64))>,
    objectives: SharedVec<(String, BuildingId)>,
    effect_ends: SharedVec<(String, f64)>,
    effect_starts: SharedVec<(String, f64)>,
    objective_jobs: SharedVec<(String, BuildingId)>,
    // Immutable construction inputs remain available for export inspection.
    // Runtime fields have typed storage above and do not belong in this snapshot.
    pub constructed: Rc<Json>,
}

impl PlaybookPlan {
    pub fn load(p: &Json) -> Self {
        assert_eq!(p.at("$type").str(), "PlaybookPlan");
        let mut steps: Vec<_> = p.at("steps").arr().iter().map(Step::load).collect();
        let source = steps.clone();
        for step in &mut steps {
            if step.action != Action::Redeploy || step.source.get("recall_from").is_some() {
                continue;
            }
            let name = step.what.as_deref().unwrap_or("");
            if !source
                .iter()
                .any(|s| s.action == Action::Deploy && s.what.as_deref() == Some(name))
            {
                continue;
            }
            let recalls: Vec<_> = source
                .iter()
                .filter(|s| {
                    s.action == Action::Recall
                        && (s.at == format!("unit:{name}") || s.at == "group:charge")
                })
                .collect();
            if recalls.len() == 1 {
                crate::plan_wire::put(
                    &mut step.source,
                    "recall_from",
                    crate::plan_wire::string(&recalls[0].id),
                );
            }
        }
        let hurt: Vec<_> = p
            .at("_hurt")
            .obj()
            .iter()
            .map(|(key, value)| {
                if let Some(group) = key.strip_prefix("engaged_since:") {
                    (
                        HurtKey::Engaged(group.to_owned()),
                        HurtValue::Since(value.f64()),
                    )
                } else {
                    let unit = UnitId(key.parse().expect("unit id in hurt history"));
                    let history = value
                        .arr()
                        .iter()
                        .map(|v| (v.arr()[0].f64(), v.arr()[1].f64()))
                        .collect();
                    (HurtKey::Unit(unit), HurtValue::History(history))
                }
            })
            .collect();
        Self {
            attack: AttackPlan::load(p),
            objectives: SharedVec::default(),
            effect_ends: SharedVec::default(),
            effect_starts: SharedVec::default(),
            objective_jobs: SharedVec::default(),
            entered: p.get("_entered").map_or_else(SharedVec::default, |v| {
                v.arr().iter().map(|v| v.str().to_owned()).collect()
            }),
            charge_closed: flag(p, "_charge_closed"),
            steps: Rc::new(steps),
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
            log_steps: p
                .at("log_steps")
                .arr()
                .iter()
                .map(|v| (v.arr()[0].f64(), v.arr()[1].str().to_owned()))
                .collect(),
            deployed: p.get("_deployed").map_or_else(SharedVec::default, |v| {
                v.arr().iter().map(|v| v.str().to_owned()).collect()
            }),
            aim_since: plans::times(p, "_aim_t").into(),
            siege_landings: p
                .get("_siege_landings")
                .map_or_else(SharedVec::default, |v| {
                    v.obj()
                        .iter()
                        .map(|(id, pos)| (id.clone(), (pos.arr()[0].f64(), pos.arr()[1].f64())))
                        .collect()
                }),
            last_alive: number(p, "_last_alive", 0.0),
            charge_edge: Cell::new(
                p.get("_charge_edge")
                    .map(|v| (v.arr()[0].f64(), v.arr()[1].f64())),
            ),
            next_fallback: number(p, "_next_fallback", 0.0),
            step_spells: p
                .get("_step_spells")
                .map(|v| Rc::new(v.arr().iter().map(|v| v.str().to_owned()).collect())),
            equipment_steps: p
                .get("_equipment_steps")
                .map_or_else(SharedVec::default, |v| {
                    v.obj()
                        .iter()
                        .map(|(id, names)| {
                            (
                                id.clone(),
                                names
                                    .arr()
                                    .iter()
                                    .map(|name| name.str().to_owned())
                                    .collect(),
                            )
                        })
                        .collect()
                }),
            ad_reservations: p
                .get("_ad_reservations")
                .map_or_else(SharedVec::default, |v| {
                    v.obj()
                        .iter()
                        .map(|(id, buildings)| {
                            (
                                id.clone(),
                                buildings
                                    .arr()
                                    .iter()
                                    .map(|b| BuildingId(b.usize()))
                                    .collect(),
                            )
                        })
                        .collect()
                }),
            constructed: Rc::new(Json::Obj(
                p.obj()
                    .iter()
                    .filter(|(name, _)| {
                        // playbook.py:113-123 records opening snipes in runtime log_steps.
                        // output/research/usage/hero-sniping-of-exposed-defenses.md:
                        // https://clashofclans.fandom.com/wiki/Rocket_Spear
                        // Keep that mutable log out of the immutable input snapshot.
                        !name.starts_with('_')
                            && !matches!(
                                name.as_str(),
                                "inventory" | "snipe_log" | "auto_revive" | "log_steps"
                            )
                    })
                    .cloned()
                    .collect(),
            )),
        }
    }

    fn done(&self, id: &str) -> bool {
        self.done.iter().any(|(key, _)| key == id)
    }

    /// Read-only diagnostics for recipe replay witnesses.
    pub fn objective_bindings(&self) -> &[(String, BuildingId)] {
        &self.objectives
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
            if Self::ad_target_count(step) > 0
                && !done
                && !cancelled
                && self.missing_equipment(battle, step, None).is_none()
            {
                context.reserve_lightning = true;
            }
            if cancelled || done && step.every.is_none() || step.completion || step.uncited {
                continue;
            }
            // output/research/usage/grand-warden.md: equipment supplies abilities.
            // https://clashofclans.fandom.com/wiki/Grand_Warden
            if step.action == Action::Ability
                && self.missing_equipment(battle, step, None).is_some()
            {
                continue;
            }
            for name in [
                "Archer Queen",
                "Royal Champion",
                "Flame Flinger",
                "Dragon Duke",
                "Grand Warden",
            ] {
                let reserves = name == "Flame Flinger"
                    && step.action == Action::ReleaseSiege
                    && step.what.as_deref().is_none_or(|what| what == name);
                // playbook.py:_snipe_available: a cited ability, or a step
                // anchored on the hero (its Healers, Invisibility), keeps it.
                let ability = step.action == Action::Ability && step.what.as_deref() == Some(name);
                let suffix = format!(":{name}");
                let anchored = step.at.ends_with(&suffix)
                    || step
                        .aim
                        .as_deref()
                        .is_some_and(|aim| aim.ends_with(&suffix));
                if (reserves || ability || anchored)
                    && !context.unavailable.iter().any(|tool| tool == name)
                {
                    context.unavailable.push(name.to_owned());
                }
            }
        }
        self.attack.scouting_context = Some(context);
    }

    pub fn deployments(&mut self, battle: &mut Battle) -> Vec<Deployment> {
        self.sync_scouting(battle);
        let out = self.attack.opening_deployments(battle);
        if self
            .attack
            .scouting_context
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
        self.attack.has_unreleased_cc()
            || self.inventory.iter().any(|(_, n)| *n != 0)
            || self
                .steps
                .iter()
                .any(|s| matches!(s.action, Action::Deploy | Action::Redeploy) && !self.done(&s.id))
    }

    // playbook.py:127-165.
    pub fn has_offensive_pending(&self, battle: &Battle) -> bool {
        if self.attack.has_deployable_cc(battle) {
            return true;
        }
        // Read the current _step_kinds result even before the first fallback
        // tick; this query runs through an immutable Battle snapshot.
        let auto_revive = self.auto_revive();
        if self.have("revive")
            && battle
                .attackers_pool()
                .any(|h| !h.alive && h.extra.revivable)
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
        if battle
            .portal_units()
            .any(|r| battle.unit(r).name_id != Name::Healer)
        {
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
                && (s.action == Action::Deploy || self.initial_return(s))
                && s.what.as_deref() != Some("Healer")
                && s.what
                    .as_deref()
                    .is_some_and(|name| plans::is_hero(name) || count(&self.inventory, name) > 0)
        })
    }

    // playbook.py:148-154.
    fn edge_angle(&self, which: &str) -> f64 {
        let which = match which {
            "charge" => self.charge_side.as_str(),
            "funnel" => {
                if self.charge_side == "left" {
                    "right"
                } else {
                    "left"
                }
            }
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
        if which == "charge"
            && self.steps.iter().any(|step| {
                step.action == Action::Deploy
                    && step.what.as_deref().is_some_and(plans::is_hero)
                    && step.group == "charge"
            })
        {
            if let Some(point) = self.charge_edge.get() {
                return point;
            }
            let point = self
                .attack
                .charge_point(battle, self.edge_angle(which), 0.0);
            self.charge_edge.set(Some(point));
            return point;
        }
        plans::edge_point(battle, self.edge_angle(which), 0.0)
    }

    // playbook.py:159-163.
    fn unit(&self, battle: &Battle, name: &str) -> Option<UnitRef> {
        battle
            .attackers_pool()
            .find(|u| u.alive && u.name == name && u.kind != Tag::HeroClone)
            .map(Unit::reference)
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
                let units = self.group_units(battle, arg);
                (!units.is_empty()).then(|| plans::centroid(battle, &units))
            }
            "cohort" => {
                let step = self.steps.iter().find(|s| s.id == arg)?;
                let units: Vec<_> = battle
                    .attackers_pool()
                    .filter(|u| u.alive && self.cohort_member(battle, step, u))
                    .map(Unit::reference)
                    .collect();
                (!units.is_empty()).then(|| plans::centroid(battle, &units))
            }
            "th" => battle
                .th
                .map(|id| battle.building(id))
                .filter(|b| b.alive)
                .map(|b| (b.x, b.y)),
            "threat" => {
                let mut units = self.group_units(battle, arg);
                if units.is_empty() {
                    units = self.group_units(battle, "main");
                }
                if units.is_empty() {
                    return None;
                }
                let (x, y) = plans::centroid(battle, &units);
                let mut best = None;
                for (id, _) in plans::threats_near(battle, x, y, 12.0) {
                    // playbook.py:218-226: hidden firing defenses are unavailable.
                    if !battle.building_targetable(id)
                        || unclaimed && self.attack.snipe_claimed.contains(&id)
                    {
                        continue;
                    }
                    let b = battle.building(id);
                    let w = b.weapon.as_ref().expect("weapon");
                    let score = plans::threat(&b.key, 1.0);
                    if (w.target.is_some() || !w.multi.is_empty())
                        && best.is_none_or(|(s, _)| score > s)
                    {
                        best = Some((score, id));
                    }
                }
                best.map(|(_, id)| {
                    let b = battle.building(id);
                    (b.x, b.y)
                })
            }
            "defenders" => {
                let units = self.group_units(battle, if arg.is_empty() { "main" } else { arg });
                if units.is_empty() {
                    return None;
                }
                let (x, y) = plans::centroid(battle, &units);
                let defenders: Vec<_> = battle
                    .defenders_pool()
                    .filter(|u| u.alive && u.target.is_some() && u.dist(x, y) <= 8.0)
                    .map(Unit::reference)
                    .collect();
                (!defenders.is_empty()).then(|| plans::centroid(battle, &defenders))
            }
            "defender" => {
                let (name, group) = arg.split_once(':')?;
                let units = self.group_units(battle, group);
                if units.is_empty() {
                    return None;
                }
                let (x, y) = plans::centroid(battle, &units);
                battle
                    .defenders_pool()
                    .filter(|u| u.alive && u.name == name && u.dist(x, y) <= 8.0)
                    .min_by(|a, b| a.dist(x, y).total_cmp(&b.dist(x, y)))
                    .map(|u| (u.x, u.y))
            }
            "building" => {
                let mut units = self.group_units(battle, "main");
                if units.is_empty() {
                    units = battle
                        .attackers_pool()
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
                for b in battle.visible_buildings() {
                    if b.alive
                        && b.key == arg
                        && !(unclaimed && self.attack.snipe_claimed.contains(&b.id))
                    {
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
    fn totem_anchor(&self, battle: &Battle, at: &str, position: (f64, f64)) -> Option<(f64, f64)> {
        if !self.attack.totem_covered(battle, position.0, position.1) {
            return Some(position);
        }
        let (kind, arg) = at.split_once(':').unwrap_or((at, ""));
        if kind == "defenders" {
            let group = self.group_units(battle, if arg.is_empty() { "main" } else { arg });
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
            let mut group = self.group_units(battle, arg);
            if kind == "threat" && group.is_empty() {
                group = self.group_units(battle, "main");
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
    fn inside(&self, battle: &Battle, unit: UnitRef) -> bool {
        let u = battle.unit(unit);
        let (x, y) = (u.x as i32, u.y as i32);
        // output/research/usage/root-rider.md: Duke follows the Riders' entry.
        // https://www.youtube.com/watch?v=C0lnvxJraoM&t=256
        // Policy: milestones retain the original deployment boundary.
        [-2, 0, 2].iter().all(|dx| {
            [-2, 0, 2]
                .iter()
                .all(|dy| battle.no_deploy.contains(&(x + dx, y + dy)))
        })
    }

    fn initial_return(&self, step: &Step) -> bool {
        step.action == Action::Redeploy
            && step.source.get("recall_from").is_none()
            && step.what.as_deref().is_some_and(|name| {
                plans::is_hero(name) && !self.deployed.iter().any(|n| n == name)
            })
    }

    fn support_troop(name: &str) -> bool {
        matches!(
            name,
            "Healer"
                | "Druid"
                | "Apprentice Warden"
                | "Wall Breaker"
                | "Super Wall Breaker"
                | "Headhunter"
        )
    }

    fn main_started(&self, battle: &Battle) -> bool {
        if self.explicit_primary() {
            return self
                .steps
                .iter()
                .any(|s| flag(&s.source, "primary") && self.done(&s.id) && !self.cancelled(&s.id));
        }
        // output/research/usage/root-rider.md: support follows the main troops.
        // https://www.youtube.com/watch?v=g9UjZ9xFQOU&t=169
        let candidates: Vec<&Step> = self
            .steps
            .iter()
            .filter(|step| {
                step.action == Action::Deploy
                    && step.group == "main"
                    && step.what.as_deref().is_some_and(|name| {
                        self.inventory.iter().any(|(n, _)| n == name)
                            && !Self::support_troop(name)
                            && !crate::content::is_siege(name)
                    })
            })
            .collect();
        let bulk: Vec<&Step> = candidates
            .iter()
            .copied()
            .filter(|step| step.count.is_none_or(|n| n >= 2))
            .collect();
        let steps = if bulk.is_empty() { &candidates } else { &bulk };
        battle.attackers_pool().any(|u| {
            u.group == "main"
                && steps
                    .iter()
                    .any(|step| step.what.as_deref() == Some(u.name.as_str()))
        })
    }

    fn group_units(&self, battle: &Battle, group: &str) -> Vec<UnitRef> {
        if group != "main" || !self.explicit_primary() {
            return plans::main_units(battle, group);
        }
        battle
            .attackers_pool()
            .filter(|u| {
                u.alive
                    && self.steps.iter().any(|s| {
                        flag(&s.source, "primary")
                            && s.what.as_deref() == Some(u.name.as_str())
                            && s.group == u.group
                            && !self.cancelled(&s.id)
                            && self.cohort_member(battle, s, u)
                    })
            })
            .map(Unit::reference)
            .collect()
    }

    fn explicit_primary(&self) -> bool {
        flag(&self.constructed, "primary_cohort")
            || self.steps.iter().any(|s| flag(&s.source, "primary"))
    }

    fn cohort_member(&self, battle: &Battle, step: &Step, unit: &Unit) -> bool {
        self.done
            .iter()
            .find(|(id, _)| id == &step.id)
            .is_some_and(|(_, start)| {
                let count = number(
                    &step.source,
                    "allocated_count",
                    step.count.unwrap_or(1) as f64,
                )
                .max(1.0);
                let end = start + (count - 1.0) * battle.pace_tap * battle.pace + battle.dt;
                unit.name == step.what.as_deref().unwrap_or("")
                    && unit.group == step.group
                    && unit.spawned_at >= *start
                    && unit.spawned_at <= end
                    && unit.kind != Tag::HeroClone
                    && !unit.extra.clone
            })
    }

    fn invisibility_anchor(
        &self,
        battle: &mut Battle,
        step: &Step,
        pos: Option<(f64, f64)>,
    ) -> Option<(f64, f64)> {
        // output/research/usage/invisibility-spell.md: cover advancing heroes.
        // https://clashofclans.fandom.com/wiki/Invisibility_Spell
        if step.what.as_deref() != Some("Invisibility Spell") || step.at != "group:charge" {
            return pos;
        }
        let group: Vec<_> = self
            .group_units(battle, "charge")
            .into_iter()
            .filter(|r| battle.unit(*r).is_hero)
            .collect();
        let first = group.first()?;
        let anchor = format!("unit_ahead:{}", battle.unit(*first).name);
        let lead = self.anchor(battle, &anchor, false)?;
        let (mut x, mut y) = lead;
        for r in group.iter().skip(1) {
            let u = battle.unit(*r);
            let distance = py_hypot(u.x - x, u.y - y);
            if distance > 4.0 {
                let shift = (distance - 4.0) / distance;
                x += (u.x - x) * shift;
                y += (u.y - y) * shift;
            }
        }
        if group.iter().all(|r| {
            let u = battle.unit(*r);
            py_hypot(u.x - x, u.y - y) <= 4.0
        }) {
            Some((x, y))
        } else {
            Some(lead)
        }
    }

    // playbook.py:233-239.
    fn heavy_fire(&self, battle: &Battle, unit: UnitRef, fraction: f64) -> bool {
        let u = battle.unit(unit);
        let history = self.hurt_index(u.id).map(|index| &self.hurt[index]);
        let recent = history.and_then(|(_, value)| {
            if let HurtValue::History(history) = value {
                history
                    .iter()
                    .filter(|(t, _)| battle.t - t <= 2.0)
                    .map(|(_, hp)| *hp)
                    .reduce(f64::max)
            } else {
                None
            }
        });
        let lost = recent.map_or(0.0, |hp| hp - u.hp);
        let locked = battle.visible_buildings().any(|b| {
            b.alive
                && plans::threat(&b.key, 0.0) >= 4.0
                && b.weapon
                    .as_ref()
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
        let generated = name == "Firemite";
        (generated || self.deployed.iter().any(|n| n == name))
            && self.unit(battle, name).is_none()
            && !self.generated_possible(battle, name)
            && !battle.portal_units().any(|r| {
                let u = battle.unit(r);
                u.name == name && u.kind != Tag::HeroClone
            })
            && !battle.deployments[battle.next_deploy..]
                .iter()
                .any(|d| d.name == name)
            && (plans::is_hero(name) || count(&self.inventory, name) <= 0)
    }

    fn generated_possible(&self, battle: &Battle, name: &str) -> bool {
        if name != "Firemite" {
            return false;
        }
        battle
            .attackers_pool()
            .any(|unit| unit.alive && unit.name_id == Name::Furnace && unit.extra.mites > 0)
            || battle.deployments[battle.next_deploy..]
                .iter()
                .any(|deployment| deployment.name == "Furnace" || deployment.name == name)
            || count(&self.inventory, "Furnace") > 0
    }

    /// A scheduled spell opener is useful work even without a living army.
    /// Follow only temporal spell chains; a pressure condition requiring a
    /// not-yet-deployed unit cannot keep a failed opener alive indefinitely.
    fn preparing(&self, battle: &Battle, trigger: &Trigger, seen: &mut Vec<String>) -> bool {
        match trigger {
            Trigger::All(parts) | Trigger::Any(parts) => {
                parts.iter().any(|part| self.preparing(battle, part, seen))
            }
            Trigger::After(id, _) if !self.done(id) && !self.cancelled(id) => {
                if seen.contains(id) {
                    return false;
                }
                let Some(step) = self.steps.iter().find(|step| step.id == *id) else {
                    return false;
                };
                seen.push(id.clone());
                let possible = if step.action == Action::Spell {
                    battle.t < number(&step.source, "timeout", battle.params.late_deployment)
                        && self.scheduled_preparation(battle, &step.when, seen)
                } else {
                    self.preparing(battle, &step.when, seen)
                };
                seen.pop();
                possible
            }
            _ => false,
        }
    }

    fn scheduled_preparation(
        &self,
        battle: &Battle,
        trigger: &Trigger,
        seen: &mut Vec<String>,
    ) -> bool {
        match trigger {
            Trigger::Always | Trigger::Time(_) => true,
            Trigger::After(id, _) => self.done(id) || self.preparing(battle, trigger, seen),
            Trigger::All(parts) => parts
                .iter()
                .all(|part| self.scheduled_preparation(battle, part, seen)),
            Trigger::Any(parts) => parts
                .iter()
                .any(|part| self.scheduled_preparation(battle, part, seen)),
            _ => false,
        }
    }

    /// Runtime reservations belong to unfinished cited deployments. A terminal
    /// skip releases its stock, just as a successful deployment consumes it.
    fn unreserved_inventory(&self) -> Vec<(String, i64)> {
        let mut available = self.inventory.to_vec();
        for step in self.steps.iter().filter(|step| {
            step.action == Action::Deploy
                && !step.uncited
                && !self.done(&step.id)
                && !self.cancelled(&step.id)
        }) {
            if let Some(name) = &step.what {
                let left = count(&available, name);
                let reserved = step.count.unwrap_or(left).max(0).min(left);
                set(&mut available, name.clone(), left - reserved);
            }
        }
        available
    }

    fn opportunity_has_stock(&self, step: &Step) -> bool {
        let Some(kind) = step.spell_kind() else {
            return true;
        };
        let budget = step.source.get("spell_budget").and_then(Json::opt_str);
        if !flag(&step.source, "optional") && budget.is_none() {
            return true;
        }
        let mut mandatory = 0;
        let mut groups: Vec<(&str, i64)> = Vec::new();
        for other in self.steps.iter().filter(|other| {
            other.spell_kind() == Some(kind)
                && other.id != step.id
                && !self.done(&other.id)
                && !self.cancelled(&other.id)
                && !flag(&other.source, "optional")
        }) {
            let amount = other.count.unwrap_or(1).max(0);
            if let Some(group) = other.source.get("spell_budget").and_then(Json::opt_str) {
                if Some(group) == budget {
                    continue;
                }
                if let Some((_, reserved)) = groups.iter_mut().find(|(id, _)| *id == group) {
                    *reserved = (*reserved).max(amount);
                } else {
                    groups.push((group, amount));
                }
            } else {
                mandatory += amount;
            }
        }
        mandatory += groups.iter().map(|(_, amount)| amount).sum::<i64>();
        count(&self.attack.spells, kind) > mandatory
    }

    // playbook.py:251-260.
    fn impossible(&self, battle: &Battle, trigger: &Trigger) -> bool {
        match trigger {
            Trigger::All(parts) => parts.iter().any(|part| self.impossible(battle, part)),
            Trigger::Any(parts) => parts.iter().all(|part| self.impossible(battle, part)),
            Trigger::Inside(name)
                if self.entered.contains(name)
                    || !plans::is_hero(name)
                        && battle.attackers_pool().any(|u| u.name == *name) =>
            {
                false
            }
            _ => trigger
                .unit_condition()
                .is_some_and(|name| self.down(battle, name) && !self.recoverable(battle, name)),
        }
    }

    fn recoverable(&self, battle: &Battle, name: &str) -> bool {
        // output/research/usage/revive-spell.md: unused abilities survive KO.
        // https://clashofclans.fandom.com/wiki/Revive_Spell
        battle
            .attackers_pool()
            .any(|u| u.name == name && u.is_hero && !u.alive && u.extra.revivable)
            && (count(&self.attack.spells, "revive") > 0
                || battle
                    .fields
                    .iter()
                    .any(|f| matches!(f.kind, Tag::ReviveCast | Tag::ReviveDue)))
    }

    fn named_revive_pending(&self, battle: &Battle, name: &str) -> bool {
        let active = battle.fields.iter().any(|field| {
            matches!(field.kind, Tag::ReviveCast | Tag::ReviveDue)
                && field
                    .extra
                    .hero
                    .is_some_and(|hero| battle.unit(hero).name == name)
        });
        active
            || count(&self.attack.spells, "revive") > 0
                && self.steps.iter().any(|step| {
                    if step.what.as_deref() != Some("Revive Spell")
                        || self.done(&step.id)
                        || self.cancelled(&step.id)
                    {
                        return false;
                    }
                    let mut names = Vec::new();
                    step.when.revive_names(&mut names);
                    step.at == format!("unit:{name}") || names.iter().any(|hero| hero == name)
                })
    }

    fn awaiting_revive(&self, battle: &Battle, step: &Step) -> bool {
        let what = step.what.as_deref().unwrap_or("");
        let target = if what != "Revive Spell" {
            step.at
                .strip_prefix("unit:")
                .or_else(|| step.at.strip_prefix("unit_ahead:"))
        } else {
            None
        };
        let target = target.or_else(|| (step.action == Action::Ability).then_some(what));
        target.is_some_and(|name| {
            !name.is_empty() && self.down(battle, name) && self.recoverable(battle, name)
        })
    }

    // playbook.py:262-283.
    fn fallen(&self, battle: &Battle, step: &Step) -> Option<UnitRef> {
        let mut names = Vec::new();
        if let Some(name) = step
            .at
            .strip_prefix("unit:")
            .or_else(|| step.at.strip_prefix("unit_ahead:"))
        {
            names.push(name.to_owned());
        }
        step.when.revive_names(&mut names);
        let mut best = None;
        let mut last = 0.0;
        for u in battle.attackers_pool() {
            if u.is_hero
                && !u.alive
                && u.extra.revivable
                && (names.is_empty() || names.contains(&u.name))
            {
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
                let parts: Vec<_> = parts
                    .iter()
                    .filter(|part| !(relax && self.impossible(battle, part)))
                    .collect();
                parts.is_empty() || parts.iter().any(|part| self.ready(battle, part, relax))
            }
            _ if relax
                && trigger
                    .unit_condition()
                    .is_some_and(|name| self.down(battle, name)) =>
            {
                true
            }
            Trigger::Time(t) => battle.t >= *t,
            Trigger::After(id, delay) => self
                .done
                .iter()
                .find(|(key, _)| key == id)
                .is_some_and(|(_, at)| battle.t >= at + delay),
            Trigger::Inside(name) => {
                if self.entered.contains(name) {
                    return true;
                }
                let matching: Vec<_> = battle
                    .attackers_pool()
                    .filter(|u| u.name == *name && u.kind != Tag::HeroClone)
                    .map(Unit::reference)
                    .collect();
                let inside = matching
                    .iter()
                    .any(|r| battle.unit(*r).alive && self.inside(battle, *r));
                // Policy fallback: five seconds from deployment, never a death gate.
                inside
                    || !plans::is_hero(name)
                        && matching
                            .iter()
                            .map(|r| battle.unit(*r).spawned_at)
                            .reduce(f64::min)
                            .is_some_and(|at| battle.t >= at + 5.0)
            }
            Trigger::GroupInside(group) => {
                if group == "main" && !self.main_started(battle) {
                    return false;
                }
                let units = self.group_units(battle, group);
                if units.is_empty() {
                    return false;
                }
                let needed = 1.max(units.len() / 2);
                let inside = units.iter().filter(|r| self.inside(battle, **r)).count();
                if inside >= needed {
                    return true;
                }
                let engaged = units
                    .iter()
                    .filter(|r| {
                        let u = battle.unit(**r);
                        u.target.is_some_and(|r| {
                            battle.entity_alive(r) && !matches!(r, EntityRef::Unit(_))
                        }) && u.cooldown > 0.0
                    })
                    .count();
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
                let units = self.group_units(battle, group);
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
            Trigger::HeavyFire(name, fraction) => battle.attackers_pool().any(|u| {
                u.alive
                    && u.name == *name
                    && (!self
                        .steps
                        .iter()
                        .any(|s| flag(&s.source, "primary") && s.what.as_deref() == Some(name))
                        || self.group_units(battle, "main").contains(&u.reference()))
                    && u.kind != Tag::HeroClone
                    && self.heavy_fire(battle, u.reference(), *fraction)
            }),
            Trigger::HpBelow(name, fraction) => self.unit(battle, name).is_some_and(|r| {
                let u = battle.unit(r);
                u.hp < fraction * u.max_hp
            }),
            Trigger::SpellsLeft(key, n) => {
                count(&self.attack.spells, key) <= *n
                    || self.charge_closed
                        && self.steps.iter().any(|step| {
                            step.action == Action::Spell
                                && step.group == "charge"
                                && step.what.as_deref() == Some(spell_name(key))
                        })
            }
            Trigger::Dead(name) => {
                self.unit(battle, name).is_none()
                    && self.deployed.contains(name)
                    && !battle.portal_units().any(|r| {
                        let u = battle.unit(r);
                        u.name == *name && u.kind != Tag::HeroClone
                    })
            }
            Trigger::DefendersNear(group) => self
                .anchor(battle, &format!("defenders:{group}"), false)
                .is_some(),
            Trigger::Destruction(amount) => battle.destruction() as f64 >= *amount,
            Trigger::Succeeded(id) => self.done(id) && !self.cancelled(id),
            Trigger::EffectActive(id) => self.effect_ends.iter().any(|(key, end)| {
                key == id
                    && battle.t < *end
                    && self
                        .effect_starts
                        .iter()
                        .find(|(key, _)| key == id)
                        .is_none_or(|(_, start)| battle.t >= *start)
            }),
            Trigger::EffectExpired(id) => self
                .effect_ends
                .iter()
                .any(|(key, end)| key == id && battle.t >= *end),
            Trigger::ObjectiveState(id, state) => {
                if !self.objectives.iter().any(|(key, _)| key == id) {
                    let step = self
                        .steps
                        .iter()
                        .find(|s| text(&s.source, "objective", "") == id)
                        .cloned();
                    if let Some(step) = step {
                        let at = text(&step.source, "objective_at", &step.at).to_owned();
                        self.objective_point(battle, &step, &at);
                    }
                }
                self.objectives
                    .iter()
                    .find(|(key, _)| key == id)
                    .is_some_and(|(_, id)| {
                        let b = battle.building(*id);
                        match state.as_str() {
                            "destroyed" => !b.alive,
                            "damaged" => b.alive && b.hp < b.max_hp,
                            "rage" => b.alive && b.mode.as_deref() == Some("rage"),
                            _ => b.alive,
                        }
                    })
            }
            Trigger::NamedDefenders(name, group) => {
                let units = self.group_units(battle, group);
                !units.is_empty() && {
                    let (x, y) = plans::centroid(battle, &units);
                    battle
                        .defenders_pool()
                        .any(|u| u.alive && u.name == *name && u.dist(x, y) <= 8.0)
                }
            }
            Trigger::CohortAbsent(id) => {
                self.done
                    .iter()
                    .find(|(key, _)| key == id)
                    .is_some_and(|(_, t)| {
                        self.steps.iter().find(|s| s.id == *id).is_some_and(|s| {
                            !battle.attackers_pool().any(|u| {
                                u.alive
                                    && s.what.as_deref() == Some(u.name.as_str())
                                    && u.group == s.group
                                    && u.spawned_at >= *t
                            }) && !battle.deployments[battle.next_deploy..]
                                .iter()
                                .any(|d| s.what.as_deref() == Some(d.name.as_str()) && d.time >= *t)
                        })
                    })
            }
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
            let backpack = what == "Dragon Duke"
                && self.attack.has_backpack(battle)
                && matches!(at, "edge:charge" | "edge:funnel")
                && !flag(&step.source, "at_cite");
            let position = if backpack {
                self.attack.backpack_point(
                    battle,
                    self.edge_angle(at.split_once(':').expect("edge anchor").1),
                    0.0,
                )
            } else {
                position
            };
            let time = battle.t;
            self.attack.drop_fixed_at(
                battle,
                what,
                position.0,
                position.1,
                &step.group,
                0.3,
                time,
                backpack,
            );
            self.deployed.push(what.to_owned());
            return true;
        }
        let left = count(&self.inventory, what);
        let available = if flag(&step.source, "per_target") {
            let surplus = count(&self.unreserved_inventory(), what);
            let own = if self.done(&step.id) {
                0
            } else {
                step.count.unwrap_or(left)
            };
            left.min(surplus + own)
        } else {
            left
        };
        let n = step.count.map_or(available, |n| available.min(n));
        if flag(&step.source, "per_target") && n < step.count.unwrap_or(1) {
            return false;
        }
        if n <= 0 {
            return false;
        }
        let tap = battle.pace_tap * battle.pace;
        let started = battle.t;
        let spread = step.spread.unwrap_or(1.0);
        if let Some(edge) = step
            .at
            .strip_prefix("edge:")
            .filter(|_| n >= 3 && !matches!(what, "Healer" | "Wall Breaker"))
        {
            // output/research/usage/archer.md: spread deployments avoid splash.
            // A spread multiplier scales this formation, never selects a stack.
            // https://clashofclans.fandom.com/wiki/Archer
            let angle = self.edge_angle(edge);
            let width = ((n - 1) as f64).min(8.0) * spread;
            for i in 0..n {
                let (x, y) = plans::edge_point(
                    battle,
                    angle,
                    -width / 2.0 + width * i as f64 / (n - 1) as f64,
                );
                self.attack.drop_at(
                    battle,
                    what,
                    x,
                    y,
                    &step.group,
                    0.3 * spread,
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
                    spread,
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
        let fields_before = battle.fields.len();
        self.attack.cast_spell(
            battle,
            spell_name(kind),
            position.0,
            position.1,
            step.level.as_ref(),
            step.origin.as_deref(),
        );
        for field in &battle.fields[fields_before..] {
            // Status dispatch happens on the first engine tick at/after
            // landing. Persistent area fields retain their scheduled expiry.
            let mut start = battle.t;
            while start < field.started {
                start = crate::geom::round6(start + battle.dt);
            }
            let end = match field.kind {
                Tag::Iceblock => start + field.extra.time,
                Tag::Overgrowth => start + field.value,
                _ => field.until,
            };
            set(&mut self.effect_starts, step.id.clone(), start);
            set(&mut self.effect_ends, step.id.clone(), end);
        }
        true
    }

    fn objective_point(
        &mut self,
        battle: &mut Battle,
        step: &Step,
        at: &str,
    ) -> Option<(f64, f64)> {
        let Some(name) = step.source.get("objective").and_then(Json::opt_str) else {
            return self.anchor(battle, at, step.action == Action::Spell);
        };
        if let Some(goal) = step.source.get("mask_for").and_then(Json::opt_str) {
            if let Some((_, id)) = self.objectives.iter().find(|(key, _)| key == name) {
                let b = battle.building(*id);
                return Some((b.x, b.y));
            }
            if !self.objectives.iter().any(|(key, _)| key == goal) {
                let declaration = self
                    .steps
                    .iter()
                    .find(|s| {
                        text(&s.source, "objective", "") == goal
                            && s.source.get("mask_for").is_none()
                    })
                    .cloned()?;
                let target = text(
                    &declaration.source,
                    "objective_at",
                    declaration.aim.as_deref().unwrap_or(&declaration.at),
                )
                .to_owned();
                self.objective_point(battle, &declaration, &target)?;
            }
            let goal = self.objectives.iter().find(|(key, _)| key == goal)?.1;
            let hero = self.unit(battle, text(&step.source, "mask_hero", "Grand Warden"))?;
            let caster = battle.unit(hero);
            let (x, y) = (caster.x, caster.y);
            // Match Invisibility's existing four-tile cast geometry. Pending
            // circles are already committed input and must not be duplicated.
            let target = heroes::targets(battle, true)
                .into_iter()
                .filter_map(|r| match r {
                    EntityRef::Building(id) => Some(id),
                    _ => None,
                })
                .filter(|id| {
                    *id != goal && {
                        let b = battle.building(*id);
                        battle.building(goal).edge_distance(b.x, b.y) > 4.0
                            && !battle.fields.iter().any(|f| {
                                f.kind == Tag::Invis
                                    && f.until > battle.t
                                    && b.edge_distance(f.x, f.y) <= f.radius
                            })
                    }
                })
                .min_by(|a, b| {
                    heroes::distance(battle, EntityRef::Building(*a), x, y)
                        .total_cmp(&heroes::distance(battle, EntityRef::Building(*b), x, y))
                })?;
            self.objectives.push((name.to_owned(), target));
            let b = battle.building(target);
            return Some((b.x, b.y));
        }
        if at.starts_with("edge:") && step.source.get("objective_at").is_some() {
            return self.anchor(battle, at, false);
        }
        if flag(&step.source, "per_target") {
            self.objectives.retain(|(key, id)| {
                key != name
                    || !self
                        .objective_jobs
                        .iter()
                        .any(|(job, done)| job == &step.id && done == id)
            });
        }
        let target = if let Some((_, id)) = self.objectives.iter().find(|(key, _)| key == name) {
            *id
        } else {
            let candidates = crate::plan_wire::list(&step.source, "target_keys");
            let point = self
                .anchor(battle, at, false)
                .or_else(|| (!candidates.is_empty()).then(|| self.edge(battle, "main")))?;
            let key = at.strip_prefix("building:");
            let level = self
                .attack
                .spell_levels
                .iter()
                .find(|(name, _)| name == "Earthquake Spell")
                .and_then(|(_, level)| level.clone())
                .unwrap_or_else(|| {
                    Level::Int(
                        battle
                            .catalog
                            .stats
                            .max_level("Earthquake Spell", self.attack.town_hall)
                            .unwrap_or(1),
                    )
                });
            let radius = battle
                .catalog
                .resolved
                .at("spell_radii")
                .get(&format!("Earthquake Spell|{level}"))
                .map_or(0.0, Json::f64);
            let value = |center: &Building| {
                battle
                    .visible_buildings()
                    .filter(|b| {
                        b.alive && b.is_defense && b.edge_distance(center.x, center.y) <= radius
                    })
                    .map(|b| plans::threat(&b.key, 1.0))
                    .sum::<f64>()
            };
            let target = battle
                .visible_buildings()
                .filter(|b| {
                    b.alive
                        && (if candidates.is_empty() {
                            key.is_none_or(|key| b.key == key)
                        } else {
                            candidates.iter().any(|key| key.str() == b.key)
                        })
                        && step
                            .source
                            .get("target_mode")
                            .and_then(Json::opt_str)
                            .is_none_or(|mode| b.mode.as_deref() == Some(mode))
                        && (!flag(&step.source, "per_target")
                            || !self
                                .objective_jobs
                                .iter()
                                .any(|(job, id)| job == &step.id && *id == b.id))
                        && step
                            .source
                            .get("route_hero")
                            .and_then(Json::opt_str)
                            .is_none_or(|hero| {
                                self.unit(battle, hero).is_some_and(|r| {
                                    b.weapon.as_ref().is_some_and(|w| {
                                        let u = battle.unit(r);
                                        w.target == Some(r) || b.edge_distance(u.x, u.y) <= w.range
                                    })
                                })
                            })
                })
                .min_by(|a, b| {
                    let cluster = if candidates.is_empty() {
                        std::cmp::Ordering::Equal
                    } else {
                        value(b).total_cmp(&value(a))
                    };
                    cluster.then_with(|| {
                        a.dist(point.0, point.1)
                            .total_cmp(&b.dist(point.0, point.1))
                    })
                })?
                .id;
            self.objectives.push((name.to_owned(), target));
            target
        };
        let b = battle.building(target).clone();
        if flag(&step.source, "snipe") {
            let row = battle.catalog.game_data(
                "special_abilities",
                "SuperMinionSpecialProjectiles",
                None,
            );
            let range = crate::catalog::game_int(row, "AttackRange", 0) as f64 / 100.0;
            return battle
                .deploy_tiles()
                .iter()
                .copied()
                .filter(|(x, y)| b.edge_distance(*x, *y) <= range)
                .min_by(|a, c| b.dist(a.0, a.1).total_cmp(&b.dist(c.0, c.1)));
        }
        Some((b.x, b.y))
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
            let action = step
                .source
                .get("ability")
                .filter(|value| truth(value))
                .map_or(step.id.as_str(), Json::str)
                .replace('_', " ")
                .to_lowercase();
            // A list of items is read below; only a single name seeds `required`.
            let mut required = match step.source.get("equipment") {
                Some(Json::Str(name)) if !name.is_empty() => Some(name.clone()),
                _ => None,
            }
            .or_else(|| {
                battle
                    .catalog
                    .stats
                    .registry
                    .obj()
                    .iter()
                    .find(|(name, record)| {
                        record.at("kind").str() == "equipment"
                            && record
                                .get("attrs")
                                .and_then(|attrs| attrs.get("raw"))
                                .and_then(|raw| raw.get("User"))
                                .and_then(Json::opt_str)
                                == Some(what)
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
            // output/research/usage/grand-warden.md: paired activation names
            // both items. https://clashofclans.fandom.com/wiki/Grand_Warden
            let required = match step.source.get("equipment") {
                Some(Json::Arr(names)) if !names.is_empty() => {
                    names.iter().map(|name| name.str().to_owned()).collect()
                }
                _ => required.into_iter().collect(),
            };
            self.equipment_steps.push((step.id.clone(), required));
        }
        let required = self
            .equipment_steps
            .iter()
            .find(|(id, _)| id == &step.id)
            .map(|(_, required)| required)?;
        let loadout = self
            .attack
            .loadouts
            .iter()
            .find(|(name, _)| name == what)
            .map(|(_, loadout)| loadout.clone())
            .or_else(|| heroes::default_loadout(battle, what));
        let equipped = unit
            .and_then(|reference| battle.unit(reference).kit.as_ref())
            .map(|kit| kit.equip.as_slice())
            .or_else(|| loadout.as_ref().map(|loadout| loadout.equipment.as_slice()))
            .unwrap_or(&[]);
        let unusable = |item: &String| {
            !equipped.contains(item)
                || self.attack.account_equipment
                    && !self
                        .attack
                        .equipment_levels
                        .iter()
                        .any(|(name, _)| name == item)
        };
        // playbook.py _missing_equipment: any-of; one press fires whichever
        // listed item is equipped.
        if !required.is_empty() && required.iter().all(unusable) {
            required.first().cloned()
        } else {
            None
        }
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
            || step
                .source
                .get("equipment")
                .is_some_and(|value| match value {
                    Json::Arr(names) => !names.iter().any(|name| name.opt_str() == Some(equipment)),
                    _ => value.opt_str() != Some(equipment),
                })
        {
            return 0;
        }
        let quotes = ["aim_cite", "cite"]
            .iter()
            .flat_map(|key| step.source.get(key).into_iter().flat_map(Json::arr))
            .map(|cite| text(cite, "quote", ""))
            .collect::<Vec<_>>()
            .join(" ")
            .to_lowercase();
        if aim != "building:ad" && !quotes.contains("air defense") {
            return 0;
        }
        let mut count = number(&step.source, "aim_count", 1.0).max(1.0) as usize;
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
        if u.kit.is_none()
            || u.ability_used
            || self.missing_equipment(battle, step, Some(hero)).is_some()
        {
            return false;
        }
        self.sync_scouting(battle);
        let objectives: Vec<_> = self
            .steps
            .iter()
            .filter(|s| text(&s.source, "bind_before", "") == step.id)
            .cloned()
            .collect();
        for objective in objectives {
            let at = text(&objective.source, "objective_at", &objective.at).to_owned();
            self.objective_point(battle, &objective, &at);
        }
        let bound = step
            .source
            .get("objective")
            .and_then(Json::opt_str)
            .map(str::to_owned);
        if bound.is_some() {
            let at = text(
                &step.source,
                "objective_at",
                step.aim.as_deref().unwrap_or("building:cc"),
            );
            if self.objective_point(battle, step, at).is_none() {
                return false;
            }
        }
        let since = entry_time(&mut self.aim_since, &step.id, battle.t);
        let deadline = since + battle.params.aim_wait;
        if battle.t >= deadline && bound.is_none() {
            return self.attack.fire_aimed(battle, hero, Some(deadline));
        }
        let u = battle.unit(hero);
        let kit = u.kit.as_ref().expect("hero kit");
        let fireball = kit.has("Fireball");
        let line = kit.has("Giant Arrow") || kit.has("Rocket Backpack");
        let champion = u.name_id == Name::RoyalChampion
            && (kit.has("Rocket Spear") || kit.has("Seeking Shield"));
        if Self::ad_target_count(step) > 0
            && !fireball
            && !battle.visible_buildings().any(|b| b.alive && b.key == "ad")
        {
            return false;
        }
        if let Some(key) = step
            .aim
            .as_deref()
            .and_then(|aim| aim.strip_prefix("building:"))
        {
            let count = if key == "ad" {
                Self::ad_target_count(step).max(1)
            } else {
                1
            };
            let target = bound.as_ref().and_then(|name| {
                self.objectives
                    .iter()
                    .find(|(key, _)| key == name)
                    .map(|(_, id)| *id)
            });
            if self.aim_building(battle, hero, key, Some(deadline), count, target) {
                return true;
            }
            if battle.t - since >= battle.params.aim_wait && bound.is_none() {
                return self.attack.fire_aimed(battle, hero, Some(deadline));
            }
            return false;
        }
        if step.aim.as_deref() == Some("arrow") && Self::ad_target_count(step) > 0 {
            if self.aim_building(
                battle,
                hero,
                "ad",
                Some(deadline),
                Self::ad_target_count(step),
                None,
            ) {
                return true;
            }
            if battle.t >= deadline {
                return self.attack.fire_aimed(battle, hero, Some(deadline));
            }
            return false;
        }
        if line {
            return self
                .attack
                .line_ability(battle, hero, false, Some(deadline));
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

    fn aim_building(
        &mut self,
        battle: &mut Battle,
        hero: UnitRef,
        key: &str,
        deadline: Option<f64>,
        count: usize,
        bound: Option<BuildingId>,
    ) -> bool {
        let u = battle.unit(hero);
        let (ux, uy) = (u.x, u.y);
        let target = bound.or_else(|| {
            battle
                .visible_buildings()
                .filter(|b| b.alive && b.key == key)
                .min_by(|a, b| a.dist(ux, uy).total_cmp(&b.dist(ux, uy)))
                .map(|b| b.id)
        });
        let kit = u.kit.as_ref().expect("hero kit");
        let Some(target) = target else {
            if kit.has("Fireball")
                || u.name_id == Name::RoyalChampion
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
        if kit.has("Giant Arrow") || bound.is_some() && kit.has("Rocket Backpack") {
            let Some((band, effect)) = self.attack.ability_band(battle, hero) else {
                return false;
            };
            let hits = battle
                .visible_buildings()
                .filter(|b| {
                    b.key == key
                        && battle.building_targetable(b.id)
                        && plans::band_hit(b, band, &effect.kind, effect.radius)
                })
                .count();
            let bound_hit = bound.is_none_or(|id| {
                battle.building_targetable(id)
                    && plans::band_hit(battle.building(id), band, &effect.kind, effect.radius)
            });
            if hits >= count && bound_hit {
                return self.attack.fire_aimed(battle, hero, deadline);
            }
            return false;
        }
        if kit.has("Fireball") {
            let level = kit.lv("Fireball");
            let near = heroes::targets(battle, true).into_iter().min_by(|a, b| {
                heroes::distance(battle, *a, ux, uy)
                    .total_cmp(&heroes::distance(battle, *b, ux, uy))
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

    fn pendant_possible(&self, battle: &Battle) -> bool {
        // output/research/usage/minion-prince.md: Pendant recalls the Prince
        // and nearby allies for a later redeployment.
        // https://clashofclans.fandom.com/wiki/Portal_Pendant
        let name = "Minion Prince";
        if let Some(reference) = self.unit(battle, name) {
            let unit = battle.unit(reference);
            return !unit.ability_used
                && unit
                    .kit
                    .as_ref()
                    .is_some_and(|kit| kit.has("Portal Pendant"));
        }
        let pending = self.steps.iter().any(|step| {
            step.action == Action::Deploy
                && step.what.as_deref() == Some(name)
                && !self.done(&step.id)
                && !self.cancelled(&step.id)
        }) || battle.deployments[battle.next_deploy..]
            .iter()
            .any(|entry| entry.name == name);
        if !pending || self.down(battle, name) {
            return false;
        }
        let loadout = self
            .attack
            .loadouts
            .iter()
            .find(|(hero, _)| hero == name)
            .map(|(_, loadout)| loadout.clone())
            .or_else(|| heroes::default_loadout(battle, name));
        loadout.is_some_and(|loadout| {
            loadout
                .equipment
                .iter()
                .any(|item| item == "Portal Pendant")
        }) && (!self.attack.account_equipment
            || self
                .attack
                .equipment_levels
                .iter()
                .any(|(item, _)| item == "Portal Pendant"))
    }

    // playbook.py:471-501.
    fn cannot(&mut self, battle: &Battle, step: &Step) -> Option<String> {
        if step.action == Action::Recall {
            let name = step
                .at
                .strip_prefix("unit:")
                .or_else(|| step.what.as_deref().filter(|name| plans::is_hero(name)));
            if name.is_some_and(|name| {
                self.down(battle, name) && !self.named_revive_pending(battle, name)
            }) {
                return Some("Recall opening hero lost".to_owned());
            }
        }
        if step
            .source
            .get("after_success")
            .and_then(Json::opt_str)
            .is_some_and(|id| self.cancelled(id))
        {
            return Some("required prior action failed".to_owned());
        }
        if flag(&step.source, "reserved")
            && battle.t >= number(&step.source, "timeout", battle.params.late_deployment)
        {
            return Some("reservation deadline".to_owned());
        }
        if self.awaiting_revive(battle, step) {
            return None;
        }
        let what = step.what.as_deref().unwrap_or("");
        if step.source.get("objective").is_some()
            && step.action == Action::Ability
            && self
                .aim_since
                .iter()
                .any(|(id, t)| id == &step.id && battle.t >= *t + battle.params.aim_wait)
        {
            return Some("bound objective aim deadline".to_owned());
        }
        fn expired(plan: &PlaybookPlan, battle: &Battle, trigger: &Trigger) -> bool {
            match trigger {
                Trigger::EffectActive(id) => {
                    plan.cancelled(id)
                        || plan
                            .effect_ends
                            .iter()
                            .any(|(key, end)| key == id && battle.t >= *end)
                }
                Trigger::All(parts) => parts.iter().any(|part| expired(plan, battle, part)),
                Trigger::Succeeded(id) => plan.cancelled(id),
                Trigger::ObjectiveState(id, state) if state != "destroyed" => plan
                    .objectives
                    .iter()
                    .find(|(key, _)| key == id)
                    .is_some_and(|(_, id)| {
                        let b = battle.building(*id);
                        !b.alive || state == "rage" && b.mode.as_deref() != Some("rage")
                    }),
                _ => false,
            }
        }
        if expired(self, battle, &step.when) {
            return Some("required objective/effect unavailable".to_owned());
        }
        if self.initial_return(step) {
            return None;
        }
        if self.charge_closed
            && step.group == "charge"
            && matches!(step.action, Action::Spell | Action::Recall)
            && !flag(&step.source, "post_recall")
        {
            return Some("charge closed".to_owned());
        }
        let target = if what != "Revive Spell" {
            step.at
                .strip_prefix("unit:")
                .or_else(|| step.at.strip_prefix("unit_ahead:"))
        } else {
            None
        };
        let target = target.or_else(|| (step.action == Action::Ability).then_some(what));
        if let Some(target) = target.filter(|name| !name.is_empty() && self.down(battle, name)) {
            return Some(format!("{target} down"));
        }
        if step.action == Action::Deploy {
            return (plans::is_hero(what) && self.deployed.iter().any(|name| name == what))
                .then(|| format!("{what} already deployed"));
        }
        let holding =
            step.action == Action::Ability && self.aim_since.iter().any(|(id, _)| id == &step.id);
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
                    if !battle.visible_buildings().any(|b| b.alive && b.key == key) {
                        return Some(format!("{key} gone"));
                    }
                }
                if step.at == "th" && battle.th.is_none_or(|id| !battle.building(id).alive) {
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
                    && !battle.visible_buildings().any(|b| b.alive && b.key == "ad")
                {
                    return Some("ad gone".to_owned());
                }
            }
            Action::Redeploy => {
                if let Some(source) = step.source.get("recall_from").and_then(Json::opt_str) {
                    let stashed = battle.portal_units().any(|r| battle.unit(r).name == what);
                    if self.cancelled(source)
                        || self.done(source)
                            && !stashed
                            && battle.t - self.attack.last("recall") > 0.5
                        || self.down(battle, what)
                            && !stashed
                            && !self.named_revive_pending(battle, what)
                    {
                        return Some(format!("named return unavailable: {what} from {source}"));
                    }
                }
                if battle.portal_stash.is_empty()
                    && count(&self.attack.spells, "recall") <= 0
                    && battle.t - self.attack.last("recall") > 5.0
                    && !self.pendant_possible(battle)
                {
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

    fn release_siege(&mut self, battle: &mut Battle, step: &Step) -> bool {
        if let Some(name) = step.source.get("ahead_of").and_then(Json::opt_str) {
            let Some(hero) = self.unit(battle, name) else {
                return false;
            };
            let hero = battle.unit(hero);
            let Some(target) = hero.target.filter(|r| battle.entity_alive(*r)) else {
                return false;
            };
            let (x, y) = battle.entity_position(target);
            let (dx, dy) = (x - hero.x, y - hero.y);
            let length = dx * dx + dy * dy;
            let ahead = battle.attackers_pool().any(|u| {
                u.alive && step.what.as_deref() == Some(u.name.as_str()) && {
                    let along = if length > 0.0 {
                        ((u.x - hero.x) * dx + (u.y - hero.y) * dy) / length
                    } else {
                        -1.0
                    };
                    (0.0..=1.0).contains(&along)
                        && py_hypot(u.x - hero.x - along * dx, u.y - hero.y - along * dy)
                            <= hero.range
                }
            });
            if !ahead {
                return false;
            }
        }
        if !step.source.get("at").is_some_and(truth) {
            return crate::units::release_siege(battle, step.what.as_deref());
        }
        let unit = battle
            .attackers_pool()
            .find(|u| {
                u.alive
                    && u.kind == Tag::Siege
                    && step
                        .what
                        .as_deref()
                        .filter(|name| !name.is_empty())
                        .is_none_or(|name| u.name == name)
            })
            .map(Unit::reference);
        let Some(unit) = unit else {
            return false;
        };
        // output/research/usage/super-minion.md: release Blimp at the chosen cluster.
        // https://clashofclans.fandom.com/wiki/Battle_Blimp
        // Policy: bind once; half a tile is the arrival tolerance.
        let position = self
            .siege_landings
            .iter()
            .find(|(id, _)| id == &step.id)
            .map(|(_, pos)| *pos);
        let (x, y) = if let Some(position) = position {
            position
        } else {
            let Some(position) = self.anchor(battle, &step.at, false) else {
                return false;
            };
            self.siege_landings.push((step.id.clone(), position));
            position
        };
        if battle.unit(unit).dist(x, y) > 0.5 {
            return false;
        }
        crate::units::release_siege(battle, step.what.as_deref())
    }

    // playbook.py:527-661: skip pass, cited steps, completion steps, rescue drops.
    pub fn on_tick(&mut self, battle: &mut Battle) {
        // output/hunt/r9/s2.out #4: pets, summons and cargo also arrive in battle.
        // output/research/usage/archer-queen.md: Mirror clones are separate heroes.
        // https://clashofclans.fandom.com/wiki/Magic_Mirror
        for unit in battle.attackers_pool() {
            if unit.kind != Tag::HeroClone && !self.deployed.contains(&unit.name) {
                self.deployed.push(unit.name.clone());
            }
        }
        let t = battle.t;
        let living: Vec<_> = battle
            .attackers_pool()
            .filter(|u| u.alive && u.kind != Tag::HeroClone)
            .map(Unit::reference)
            .collect();
        for r in living {
            if self.inside(battle, r) {
                let name = battle.unit(r).name.clone();
                if !self.entered.contains(&name) {
                    self.entered.push(name);
                }
            }
        }
        // output/research/usage/root-rider.md: Recall closes the opener.
        // https://www.youtube.com/watch?v=C0lnvxJraoM&t=165
        // Policy: hero loss closes it too, regardless of surviving cleanup.
        let steps = self.steps.clone();
        let charge: Vec<_> = steps
            .iter()
            .filter(|step| {
                step.action == Action::Deploy
                    && step.group == "charge"
                    && step.what.as_deref().is_some_and(plans::is_hero)
            })
            .collect();
        if !charge.is_empty()
            && !self.charge_closed
            && charge
                .iter()
                .any(|step| self.deployed.contains(step.what.as_ref().unwrap()))
        {
            let active = charge.iter().any(|step| {
                let name = step.what.as_deref().unwrap();
                self.unit(battle, name).is_some() || self.recoverable(battle, name)
            });
            let pending = charge.iter().any(|step| {
                !self.done(&step.id)
                    && !self.cancelled(&step.id)
                    && self.cannot(battle, step).is_none()
                    && !self.impossible(battle, &step.when)
            });
            let stored = charge.iter().any(|step| {
                battle
                    .portal_units()
                    .any(|r| Some(battle.unit(r).name.as_str()) == step.what.as_deref())
            });
            if stored || !active && !pending {
                self.charge_closed = true;
            }
        }
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
        if battle.attackers_pool().any(|u| {
            u.alive && u.name_id != Name::Totem && !matches!(u.kind, Tag::Pet | Tag::SiegeIdle)
        }) {
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
                    // output/research/usage/grand-warden.md: equipped abilities
                    // share activation; a missing item did not perform the step.
                    // https://clashofclans.fandom.com/wiki/Grand_Warden
                    if !why.starts_with("missing ") {
                        entry_time(&mut self.done, &step.id, t);
                    }
                    self.cancelled.push(step.id.clone());
                    self.log_steps
                        .push((round_decimal(t, 1), format!("{} (skipped: {why})", step.id)));
                }
            }
        }
        // playbook.py:570-572: opening Lightning precedes deployment actions.
        if !self.attack.zap_done && self.attack.zap_ad != (0, 0) {
            self.fallback_spells(battle, true);
        }
        let order = steps
            .iter()
            .filter(|s| !(s.completion || s.uncited))
            .chain(steps.iter().filter(|s| s.completion || s.uncited));
        for original in order {
            if t < self.attack.busy_until {
                break;
            }
            let mut returned;
            let step = if self.initial_return(original) {
                returned = original.clone();
                returned.action = Action::Deploy;
                returned.at = "edge:main".to_owned();
                returned.group = "main".to_owned();
                &returned
            } else {
                original
            };
            let done = self.done(&step.id);
            if self.cancelled(&step.id) || done && step.every.is_none() {
                continue;
            }
            if step
                .source
                .get("after_success")
                .and_then(Json::opt_str)
                .is_some_and(|id| !self.done(id) || self.cancelled(id))
            {
                continue;
            }
            // Do not start no-target expiry clocks while revival is possible.
            if self.awaiting_revive(battle, step) {
                continue;
            }
            if step.action == Action::Spell
                && matches!(
                    step.what.as_deref(),
                    Some("Poison Spell" | "Freeze Spell" | "Rage Spell" | "Totem Spell")
                )
                && step.at.ends_with(":main")
                && !self.main_started(battle)
            {
                continue;
            }
            let mut forced = false;
            if let (Some(every), true) = (step.every, done) {
                let next = self
                    .next
                    .iter()
                    .find(|(id, _)| id == &step.id)
                    .map_or(0.0, |(_, at)| *at);
                if t < next
                    || step
                        .until
                        .as_ref()
                        .is_some_and(|until| self.ready(battle, until, false))
                {
                    continue;
                }
                if let Some(fraction) = step.source.get("repeat_effect_remaining").map(Json::f64) {
                    if self
                        .effect_ends
                        .iter()
                        .find(|(id, _)| id == &step.id)
                        .is_some_and(|(_, end)| {
                            let previous = next - every;
                            t < end - (end - previous) * fraction
                        })
                    {
                        continue;
                    }
                }
                if let Some(name) = step
                    .source
                    .get("repeat_units_absent")
                    .and_then(Json::opt_str)
                {
                    let previous = next - every;
                    if battle
                        .attackers_pool()
                        .any(|u| u.alive && u.name == name && u.spawned_at >= previous)
                    {
                        continue;
                    }
                }
                // output/research/usage/invisibility-spell.md: support under
                // pressure. https://clashofclans.fandom.com/wiki/Invisibility_Spell
                if flag(&step.source, "recheck_when") && !self.ready(battle, &step.when, false) {
                    continue;
                }
            } else if !(step.action == Action::Ability
                && self.aim_since.iter().any(|(id, _)| id == &step.id))
                && !self.ready(battle, &step.when, false)
            {
                forced = step.action == Action::Deploy
                    && !flag(&step.source, "reserved")
                    && (stalled && !self.preparing(battle, &step.when, &mut Vec::new())
                        || t >= battle.params.late_deployment
                        || self.impossible(battle, &step.when)
                            && self.ready(battle, &step.when, true));
                if !forced {
                    continue;
                }
            }
            let what = step.what.as_deref().unwrap_or("");
            if !self.opportunity_has_stock(step) {
                continue;
            }
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
                Action::ReleaseSiege => self.release_siege(battle, step),
                Action::Ability => self.ability(battle, step),
                _ => {
                    let mut position = if step.what.as_deref() == Some("Revive Spell") {
                        self.fallen(battle, step).map(|r| {
                            let u = battle.unit(r);
                            (u.x, u.y)
                        })
                    } else {
                        self.objective_point(battle, step, &step.at)
                    };
                    position = self.invisibility_anchor(battle, step, position);
                    if position.is_none() && forced {
                        position = Some(self.edge(battle, "main"));
                    }
                    // playbook.py:839-851: wait when every suitable Totem area is covered.
                    let mut totem_covered = false;
                    if step.action == Action::Spell && step.what.as_deref() == Some("Totem Spell") {
                        if let Some(point) = position {
                            position = self.totem_anchor(battle, &step.at, point);
                            totem_covered = position.is_none();
                        }
                    }
                    let Some(position) = position else {
                        if (matches!(step.action, Action::Spell | Action::Recall)
                            || step.source.get("objective").is_some())
                            && step.what.as_deref() != Some("Revive Spell")
                        {
                            let since = entry_time(&mut self.no_target, &step.id, t);
                            if totem_covered && t == since {
                                self.log_steps.push((
                                    round_decimal(t, 1),
                                    format!("{} (waiting: Totem area covered)", step.id),
                                ));
                            }
                            if t - since >= battle.params.aim_wait {
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
                        Action::Redeploy
                            if !battle.portal_stash.is_empty()
                                && t >= battle.portal_ready_at
                                && step.source.get("recall_from").is_none_or(|id| {
                                    self.done(id.str()) && !self.cancelled(id.str())
                                })
                                && step.what.as_deref().is_none_or(|name| {
                                    battle.portal_units().any(|r| battle.unit(r).name == name)
                                }) =>
                        {
                            // output/research/usage/recall-spell.md: legal drops only.
                            // https://clashofclans.fandom.com/wiki/Recall_Spell
                            // Ordinary deploy's x-major, first-on-ties resolution.
                            let mut position = position;
                            if !battle.can_deploy(position.0, position.1) {
                                let mut best = None;
                                let mut best_distance = f64::INFINITY;
                                for &(x, y) in battle.deploy_tiles() {
                                    let distance = crate::geom::py_pow(x - position.0, 2.0)
                                        + crate::geom::py_pow(y - position.1, 2.0);
                                    if best.is_none() || distance < best_distance {
                                        best = Some((x, y));
                                        best_distance = distance;
                                    }
                                }
                                position = best.expect("no legal deployment tile");
                            }
                            let stamp = step
                                .what
                                .as_deref()
                                .and_then(|name| {
                                    battle.portal_units().find(|r| battle.unit(*r).name == name)
                                })
                                .and_then(|r| battle.unit(r).extra.recalled);
                            let mut unrelated = Vec::new();
                            if step.source.get("recall_from").is_some() {
                                let stash = std::mem::take(&mut battle.portal_stash);
                                for value in stash {
                                    let belongs = match &value {
                                        Value::Ref(EntityRef::Unit(r)) => {
                                            battle.unit(*r).extra.recalled == stamp
                                        }
                                        _ => false,
                                    };
                                    if belongs {
                                        battle.portal_stash.push(value);
                                    } else {
                                        unrelated.push(value);
                                    }
                                }
                            }
                            let recalled: Vec<_> = battle.portal_units().collect();
                            for unit in recalled {
                                battle.unit_mut(unit).group = step.group.clone();
                            }
                            heroes::portal_redeploy(battle, position.0, position.1);
                            battle.portal_stash.extend(unrelated);
                            true
                        }
                        _ => false,
                    }
                }
            };
            if ok {
                if flag(&step.source, "per_target") {
                    if let Some((_, id)) = self
                        .objectives
                        .iter()
                        .find(|(key, _)| key == text(&step.source, "objective", ""))
                    {
                        self.objective_jobs.push((step.id.clone(), *id));
                    }
                }
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
            let left = self
                .inventory
                .iter()
                .find(|(name, n)| {
                    *n > 0
                        && !self.steps.iter().any(|s| {
                            s.action == Action::Deploy
                                && !self.done(&s.id)
                                && s.what.as_ref() == Some(name)
                        })
                })
                .map(|(name, n)| (name.clone(), *n));
            if let Some((name, n)) = left {
                let step =
                    Step::load(&Json::Obj(vec![
                        ("id".to_owned(), Json::Str(format!("late-{name}"))),
                        ("action".to_owned(), Json::Str("deploy".to_owned())),
                        ("what".to_owned(), Json::Str(name.clone())),
                        ("at".to_owned(), Json::Str("edge:main".to_owned())),
                        (
                            "group".to_owned(),
                            Json::Str(
                                if !self.steps.iter().any(|s| {
                                    flag(&s.source, "primary") || flag(&s.source, "reserved")
                                }) {
                                    "main"
                                } else {
                                    self.steps
                                        .iter()
                                        .rev()
                                        .find(|s| {
                                            s.what.as_deref() == Some(&name)
                                                && s.action == Action::Deploy
                                        })
                                        .map_or("cleanup", |s| s.group.as_str())
                                }
                                .to_owned(),
                            ),
                        ),
                    ]));
                let point = self.edge(battle, "main");
                self.deploy(battle, &step, point);
                self.attack.busy_until = t + action_time(battle, Action::Deploy, n);
                self.log_steps
                    .push((round_decimal(t, 1), format!("late-{name}")));
            }
        }
        if t >= self.attack.busy_until
            && self.attack.has_unreleased_cc()
            && (stalled
                || t >= battle.params.late_deployment
                || self.steps.iter().any(|step| {
                    step.action == Action::Deploy
                        && step.group == "main"
                        && self.done(&step.id)
                        && !self.cancelled(&step.id)
                }))
        {
            // output/research/usage/cleanup-troops-and-end-of-attack-play.md:
            // commit unused support with the push, or rescue a stalled attack.
            // https://www.youtube.com/watch?v=ahiJ-bgdmSE&t=2125
            let (x, y) = self.edge(battle, "main");
            crate::units::release_cc_at(battle, x, y, "main", false);
            self.attack.cc_released = true;
            self.attack.busy_until = t + action_time(battle, Action::Deploy, 1);
            self.log_steps
                .push((round_decimal(t, 1), "clan-castle".to_owned()));
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
                && !battle.deployments[battle.next_deploy..]
                    .iter()
                    .any(|d| d.name == what)
            {
                continue;
            }
            if !self.ad_reservations.iter().any(|(id, _)| id == &step.id) {
                let at = steps
                    .iter()
                    .find(|step| {
                        step.action == Action::Deploy && step.what.as_deref() == Some(what)
                    })
                    .map_or("edge:main", |step| step.at.as_str());
                let position = self
                    .anchor(battle, at, false)
                    .unwrap_or_else(|| self.edge(battle, "main"));
                let mut ads: Vec<_> = battle
                    .visible_buildings()
                    .filter(|b| b.alive && b.key == "ad" && !reserved.contains(&b.id))
                    .map(|b| b.id)
                    .collect();
                ads.sort_by(|a, b| {
                    battle
                        .building(*a)
                        .dist(position.0, position.1)
                        .total_cmp(&battle.building(*b).dist(position.0, position.1))
                });
                ads.truncate(count);
                self.ad_reservations.push((step.id.clone(), ads));
            }
            let ads = &self
                .ad_reservations
                .iter()
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
        self.next_fallback = t + battle.params.reaction_delay;
        if !opening {
            // Wiki: Hero abilities, a cited hold never suppresses low-HP rescue.
            // Match Python's one paced emergency action before spare spells.
            let emergency = battle
                .attackers_pool()
                .find(|u| {
                    if !u.alive || !u.is_hero || u.kit.is_none() || u.ability_used {
                        return false;
                    }
                    let threshold = self.attack.p(match u.name_id {
                        Name::GrandWarden => "warden_hp",
                        Name::DragonDuke => "duke_hp",
                        _ => "hero_hp",
                    });
                    u.hp / 1.0_f64.max(u.max_hp) < threshold
                })
                .map(Unit::reference);
            if let Some(hero) = emergency {
                heroes::activate(battle, hero, false);
                if battle.unit(hero).ability_used {
                    self.attack.busy_until = t + action_time(battle, Action::Ability, 1);
                    return;
                }
            }
        }
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
        if !battle.portal_stash.is_empty()
            && t >= battle.portal_ready_at
            && !self
                .steps
                .iter()
                .any(|s| s.action == Action::Redeploy && !self.done(&s.id))
        {
            let (x, y) = self.attack.portal_point(battle);
            heroes::portal_redeploy(battle, x, y);
            self.attack.busy_until = t + action_time(battle, Action::Redeploy, 1);
            return;
        }
        let mut units = if self.main_started(battle) {
            self.group_units(battle, "main")
        } else {
            Vec::new()
        };
        if units.is_empty() {
            units = self.attack.cargo_support(battle).unwrap_or_default();
            if units.is_empty()
                && self.main_started(battle)
                && battle
                    .attackers_pool()
                    .any(|u| u.group == "main" && u.name_id != Name::Totem && u.kind != Tag::Pet)
            {
                // Wiki: Heroes, independent charges and surviving flanks still
                // receive spare support after the main push has fallen.
                // output/research/usage/dragon.md: support follows the push.
                // https://www.youtube.com/watch?v=55I-qks9qdI
                units = battle
                    .attackers_pool()
                    .filter(|u| u.alive && u.name_id != Name::Totem && u.kind != Tag::Pet)
                    .map(Unit::reference)
                    .collect();
            }
        }
        let left = self.attack.spells.iter().map(|(_, n)| n).sum::<i64>();
        if !self.attack.fallback_quakes.is_empty() {
            let (x, y) = self.attack.fallback_quakes.remove(0);
            if have(&self.attack, "eq") {
                self.attack.use_spell(battle, "eq", x, y);
            }
        }
        if self.attack.spells.iter().map(|(_, n)| n).sum::<i64>() == left {
            self.sync_scouting(battle);
            self.attack.fallback = true;
            let unreserved_inventory = self.unreserved_inventory();
            let mut available_inventory = unreserved_inventory.clone();
            self.attack.generic_spells(
                battle,
                &units,
                &have,
                Some(&mut available_inventory),
                true,
                lightning_reserved,
            );
            self.attack.fallback = false;
            for ((name, total), (_, available)) in
                self.inventory.iter_mut().zip(&available_inventory)
            {
                let before = count(&unreserved_inventory, name);
                *total -= before - available;
            }
        }
        if self.attack.spells.iter().map(|(_, n)| n).sum::<i64>() < left {
            self.attack.busy_until = t + action_time(battle, Action::Spell, 1);
            return;
        }
        let held: Vec<_> = battle
            .attackers_pool()
            .filter(|u| {
                u.alive
                    && u.is_hero
                    && !u.ability_used
                    && self.steps.iter().any(|s| {
                        s.action == Action::Ability
                            && !self.done(&s.id)
                            && !self.cancelled(&s.id)
                            && s.what.as_ref() == Some(&u.name)
                    })
            })
            .map(Unit::reference)
            .collect();
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
