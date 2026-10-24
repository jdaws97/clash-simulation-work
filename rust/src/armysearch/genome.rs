//! Heritable account choices, separate from runtime plans (meta_armies.py:330).

use std::collections::BTreeMap;

use crate::armies;
use crate::compile::TACTIC_DEFAULTS;
use crate::json::Json;

use super::account::AccountRules;
use super::program::AttackProgram;
use super::util::{array, encode, number, numeric, object, string, text};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnitCount {
    pub name: String,
    pub count: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HeroChoice {
    pub hero: String,
    pub equipment: [String; 2],
    pub pet: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PlanGenes {
    /// Canonical playbook filename, or the explicit uncited `generic` family.
    pub family: String,
    pub angle_offset: f64,
    pub charge_side: String,
    pub flank_offset: f64,
    pub snipe_mode: String,
    pub tactics: [f64; 19],
    /// Relative offsets on fitted, cited dependency delays; redteam.py:360-383.
    pub step_timing: BTreeMap<String, f64>,
    pub program: Option<AttackProgram>,
}

impl Default for PlanGenes {
    fn default() -> Self {
        Self {
            family: "generic".to_owned(),
            angle_offset: 0.0,
            charge_side: "left".to_owned(),
            flank_offset: 0.9,
            snipe_mode: "value".to_owned(),
            tactics: TACTIC_DEFAULTS,
            step_timing: BTreeMap::new(),
            program: None,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ArmyGenome {
    pub troops: Vec<UnitCount>,
    pub spells: Vec<UnitCount>,
    pub cc_troops: Vec<UnitCount>,
    pub cc_spells: Vec<UnitCount>,
    pub siege: Option<String>,
    pub heroes: Vec<HeroChoice>,
    pub plan: PlanGenes,
}

fn counts(value: Option<&Json>) -> Vec<UnitCount> {
    value.map_or_else(Vec::new, |value| {
        value.obj().iter().filter_map(|(name, count)| {
            let count = count.f64();
            (count.is_finite() && count > 0.0 && count.fract() == 0.0 && count <= 10000.0)
                .then(|| UnitCount {
                    name: name.clone(),
                    count: count as usize
                })
        }).collect()
    })
}

pub fn counts_json(values: &[UnitCount]) -> Json {
    Json::Obj(values.iter().map(|unit| (unit.name.clone(), number(unit.count))).collect())
}

pub fn normalize(values: &mut Vec<UnitCount>) {
    let mut merged = BTreeMap::<String, usize>::new();
    for unit in values.iter() {
        *merged.entry(unit.name.clone()).or_default() += unit.count;
    }
    *values = merged.into_iter().filter(|(_, count)| *count > 0)
        .map(|(name, count)| UnitCount {
            name,
            count
        }).collect();
}

impl ArmyGenome {
    /// Seed recipes are suggestions. observed and all replay metadata are lost.
    /// plans.py:658 replay bypasses are deliberately never represented here.
    pub fn from_build(build: &Json) -> Self {
        let mut troops = counts(build.get("troops"));
        let mut cc = counts(build.get("cc"));
        let siege = troops.iter().chain(&cc).find(|unit| armies::is_siege(&unit.name))
            .map(|unit| unit.name.clone());
        troops.retain(|unit| !armies::is_siege(&unit.name));
        cc.retain(|unit| !armies::is_siege(&unit.name));
        let (cc_spells, cc_troops) = cc.into_iter()
            .partition(|unit| crate::plans::spell_key(&unit.name).is_some());
        let heroes = array(build, "heroes").iter().map(|hero| {
            let name = hero.str();
            let spec = build.get("loadouts").and_then(|loadouts| loadouts.get(name));
            let parts = spec.map_or(&[][..], Json::arr);
            HeroChoice {
                hero: name.to_owned(),
                equipment: [0, 1].map(|index| parts.get(index).and_then(Json::opt_str).unwrap_or("")
                    .to_owned()),
                pet: parts.get(2).and_then(Json::opt_str).unwrap_or("").to_owned(),
            }
        }).collect();
        Self {
            troops,
            spells: counts(build.get("spells")),
            cc_troops,
            cc_spells,
            siege,
            heroes,
            plan: PlanGenes {
                family: armies::family_of(build).unwrap_or("generic").to_owned(),
                ..PlanGenes::default()
            },
        }
    }

    pub fn normalize(&mut self) {
        for values in [&mut self.troops, &mut self.spells, &mut self.cc_troops, &mut self.cc_spells] {
            normalize(values);
        }
        self.heroes.sort_by(|a, b| a.hero.cmp(&b.hero));
        for hero in &mut self.heroes {
            hero.equipment.sort();
        }
        if self.plan.angle_offset == 0.0 {
            self.plan.angle_offset = 0.0;
        }
        for value in &mut self.plan.tactics {
            if *value == 0.0 {
                *value = 0.0;
            }
        }
        self.plan.step_timing.retain(|_, offset| *offset != 0.0);
        if let Some(program) = &mut self.plan.program {
            program.normalize();
        }
    }

    pub fn identity(&self) -> String {
        let mut canonical = self.clone();
        canonical.normalize();
        let mut identity = canonical.to_json();
        if let Some(program) = &canonical.plan.program {
            let mut genes = identity.at("plan_genes").clone();
            armies::put(&mut genes, "program", program.identity_json());
            armies::put(&mut identity, "plan_genes", genes);
        }
        encode(&identity)
    }

    /// meta_armies.py:150-158 selects bulk by housing. Search additionally
    /// breaks equal shares by name, independent of inventory iteration order.
    pub fn main_troop(&self, account: &AccountRules) -> Option<&str> {
        let mut shares = BTreeMap::<&str, usize>::new();
        for unit in &self.troops {
            if let Some(eligible) = account
                .roster
                .troops
                .iter()
                .find(|item| item.name == unit.name)
            {
                *shares.entry(&unit.name).or_default() += unit.count * eligible.housing;
            }
        }
        shares
            .into_iter()
            .filter(|(_, housing)| *housing > 0)
            .max_by(|(a, ah), (b, bh)| ah.cmp(bh).then_with(|| b.cmp(a)))
            .map(|(name, _)| name)
    }

    pub fn cell(&self, account: &AccountRules) -> String {
        let mut heroes: Vec<&str> = self.heroes.iter().map(|hero| hero.hero.as_str()).collect();
        heroes.sort_unstable();
        let family = if self.plan.family == "generic" {
            format!("generic:{}", self.main_troop(account).unwrap_or("empty"))
        } else {
            self.plan.family.clone()
        };
        format!("{}|{}", family, heroes.join("+"))
    }

    pub fn to_build(&self) -> Json {
        let archetype = match self.plan.family.as_str() {
            "thrower" => "mass-thrower",
            "dragon" => "mass-dragons",
            "electro-dragon" => "e-drag-spam",
            "super-bowler" => "super-bowler-smash",
            "yeti" => "mass-super-yeti",
            "meteor-golem" => "mass-meteor-golem",
            "super-minion-air" => "user-air",
            "fireball-warden" => "user-fireball-warden",
            "druid-ruin-witch" => "user-druid-ruin",
            family => family,
        };
        let mut cc = self.cc_troops.clone();
        cc.extend(self.cc_spells.clone());
        // The selected siege is home-owned. This avoids the donated-siege
        // path's implicit maximum level (setup.rs, battle.py:101-122).
        let mut troops = self.troops.clone();
        if let Some(siege) = &self.siege {
            troops.push(UnitCount {
                name: siege.clone(),
                count: 1
            });
        }
        object([
            ("archetype", string(archetype)),
            ("build", number(1)),
            ("th", number(16)),
            ("own_levels", Json::Bool(true)),
            ("observed", Json::Bool(false)),
            ("troops", counts_json(&troops)),
            ("spells", counts_json(&self.spells)),
            ("cc", counts_json(&cc)),
            ("heroes", Json::Arr(self.heroes.iter().map(|hero| string(&hero.hero)).collect())),
            ("loadouts", Json::Obj(self.heroes.iter().map(|hero| {
                (hero.hero.clone(), Json::Arr(vec![string(&hero.equipment[0]), string(&hero.equipment[1]), string(&hero.pet)]))
            }).collect())),
        ])
    }

    pub fn to_json(&self) -> Json {
        object([
            ("army", self.to_build()),
            ("plan_genes", object([
                ("family", string(&self.plan.family)),
                ("angle_offset", Json::Num(self.plan.angle_offset)),
                ("charge_side", string(&self.plan.charge_side)),
                ("flank_offset", Json::Num(self.plan.flank_offset)),
                ("snipe_mode", string(&self.plan.snipe_mode)),
                ("tactics", Json::Arr(self.plan.tactics.iter().copied().map(Json::Num).collect())),
                ("step_timing", Json::Obj(self.plan.step_timing.iter().map(|(key, value)| (key
                    .clone(), Json::Num(*value))).collect())),
                ("program", self.plan.program.as_ref().map_or(Json::Null, AttackProgram::to_json)),
            ])),
        ])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        let mut genome = Self::from_build(value.at("army"));
        let plan = value.at("plan_genes");
        genome.plan.family = text(plan, "family", "generic").to_owned();
        genome.plan.angle_offset = numeric(plan, "angle_offset", 0.0);
        genome.plan.charge_side = text(plan, "charge_side", "left").to_owned();
        genome.plan.flank_offset = numeric(plan, "flank_offset", 0.9);
        genome.plan.snipe_mode = text(plan, "snipe_mode", "value").to_owned();
        if let Some(values) = plan.get("tactics") {
            if values.arr().len() != 19 {
                return Err("checkpoint requires 19 tactic genes".to_owned());
            }
            for (target, value) in genome.plan.tactics.iter_mut().zip(values.arr()) {
                *target = value.f64();
            }
        }
        if let Some(values) = plan.get("step_timing") {
            genome.plan.step_timing = values.obj().iter().map(|(key, value)| (key.clone(), value
                .f64())).collect();
        }
        if let Some(value) = plan.get("program").filter(|value| !value.is_null()) {
            let program = AttackProgram::from_json(value)?;
            program.validate(&genome)?;
            genome.plan.program = Some(program);
        }
        genome.normalize();
        Ok(genome)
    }
}
