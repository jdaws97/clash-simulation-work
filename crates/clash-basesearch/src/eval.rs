//! Complete visible scouting groups, paired across layouts. The scorer owns
//! hidden priors, side commitment, seed namespaces and objective formulas.
use std::collections::{BTreeMap, BTreeSet};

use clash_scoring::scoring::{self, Evaluation, Outcome, Scenario, Scorer};
use clash_scoring::scouting::{ScoutPolicy, HIDDEN_SAMPLES};

use crate::json::Json;
use crate::layout::AdmittedLayout;
use crate::util::{fingerprint, num, object, string, usize_field};
use crate::Context;

#[derive(Clone, Debug)]
pub struct Group {
    pub id: String,
    pub stratum: String,
    pub population_weight: f64,
    pub scenarios: Vec<Scenario>,
    pub plans: Vec<Json>,
}

impl Group {
    pub fn to_json(&self) -> Json {
        object([
            ("id", string(&self.id)),
            ("stratum", string(&self.stratum)),
            ("population_weight", Json::Num(self.population_weight)),
            (
                "scenarios",
                Json::Arr(self.scenarios.iter().map(Scenario::to_json).collect()),
            ),
            ("plans", Json::Arr(self.plans.clone())),
        ])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        let group = Self {
            id: value.at("id").str().to_owned(),
            stratum: value.at("stratum").str().to_owned(),
            population_weight: value.at("population_weight").f64(),
            scenarios: value
                .at("scenarios")
                .arr()
                .iter()
                .map(Scenario::from_json)
                .collect(),
            plans: value.at("plans").arr().to_vec(),
        };
        group.validate()?;
        Ok(group)
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.id.is_empty()
            || self.stratum.is_empty()
            || !self.population_weight.is_finite()
            || self.population_weight <= 0.0
            || self.scenarios.len() != 2
            || self.plans.len() != 2
        {
            return Err(
                "a group needs an identity, positive population weight and two prepared candidates"
                    .to_owned(),
            );
        }
        let first = &self.scenarios[0];
        for scenario in &self.scenarios {
            if scenario.army != first.army
                || scenario.group != first.group
                || scenario.town_hall != first.town_hall
                || scenario.modifier != first.modifier
                || !scenario.weight.is_finite()
                || scenario.weight <= 0.0
                || !scenario.full_scout
                || !scenario.angle.is_finite()
            {
                return Err("candidates must form one complete full-scout group".to_owned());
            }
        }
        Ok(())
    }

    pub fn physical_cost(&self) -> usize {
        self.scenarios.len() * HIDDEN_SAMPLES + 1
    }
}

#[derive(Clone, Debug)]
pub struct Manifest {
    pub id: String,
    pub groups: Vec<Group>,
}

impl Manifest {
    pub fn to_json(&self) -> Json {
        object([
            ("id", string(&self.id)),
            (
                "groups",
                Json::Arr(self.groups.iter().map(Group::to_json).collect()),
            ),
        ])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        let manifest = Self {
            id: value.at("id").str().to_owned(),
            groups: value
                .at("groups")
                .arr()
                .iter()
                .map(Group::from_json)
                .collect::<Result<_, _>>()?,
        };
        manifest.validate()?;
        Ok(manifest)
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.groups.is_empty() || self.id.is_empty() {
            return Err("empty scenario manifest".to_owned());
        }
        let mut ids = BTreeSet::new();
        let mut seeds = BTreeSet::new();
        let mut weights = BTreeMap::new();
        for group in &self.groups {
            group.validate()?;
            let scenario = &group.scenarios[0];
            if !ids.insert(&group.id)
                || !seeds.insert(format!(
                    "{}|{}|{:?}|{}",
                    scenario.army, scenario.town_hall, scenario.modifier, scenario.group
                ))
            {
                return Err("duplicate group identity or scouting seed namespace".to_owned());
            }
            if let Some(weight) = weights.insert(&group.stratum, group.population_weight) {
                if weight != group.population_weight {
                    return Err("population weight changes within a stratum".to_owned());
                }
            }
        }
        Ok(())
    }

    pub fn strata(&self) -> BTreeMap<String, f64> {
        self.groups
            .iter()
            .map(|group| (group.stratum.clone(), group.population_weight))
            .collect()
    }
}

#[derive(Clone, Debug)]
pub struct Row {
    pub group_id: String,
    pub stratum: String,
    pub population_weight: f64,
    pub scenario: Scenario,
    pub outcome: Outcome,
    pub source_index: usize,
    pub plan: Json,
}

impl Row {
    pub fn to_json(&self) -> Json {
        object([
            ("group_id", string(&self.group_id)),
            ("stratum", string(&self.stratum)),
            ("population_weight", Json::Num(self.population_weight)),
            ("scenario", self.scenario.to_json()),
            ("outcome", self.outcome.to_json()),
            ("source_index", num(self.source_index)),
            ("plan", self.plan.clone()),
        ])
    }

    pub fn from_json(value: &Json) -> Self {
        Self {
            group_id: value.at("group_id").str().to_owned(),
            stratum: value.at("stratum").str().to_owned(),
            population_weight: value.at("population_weight").f64(),
            scenario: Scenario::from_json(value.at("scenario")),
            outcome: Outcome::from_json(value.at("outcome")),
            source_index: value.at("source_index").usize(),
            plan: value.at("plan").clone(),
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Budget {
    pub limit: usize,
    pub logical_groups: usize,
    pub planning: usize,
    pub execution: usize,
    pub diagnostics: usize,
    pub cache_hits: usize,
    pub oracle_training: usize,
    pub oracle_validation: usize,
}

impl Budget {
    pub fn used(&self) -> usize {
        self.planning + self.execution + self.diagnostics
    }

    pub fn reserve(&self, cost: usize) -> Result<(), String> {
        if self
            .used()
            .checked_add(cost)
            .is_none_or(|total| total > self.limit)
        {
            Err(format!(
                "physical battle budget exhausted: {} + {cost} > {}",
                self.used(),
                self.limit
            ))
        } else {
            Ok(())
        }
    }

    pub fn to_json(&self) -> Json {
        object([
            ("limit", num(self.limit)),
            ("logical_groups", num(self.logical_groups)),
            ("planning", num(self.planning)),
            ("execution", num(self.execution)),
            ("diagnostics", num(self.diagnostics)),
            ("cache_hits", num(self.cache_hits)),
            ("oracle_training", num(self.oracle_training)),
            ("oracle_validation", num(self.oracle_validation)),
        ])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        Ok(Self {
            limit: usize_field(value, "limit")?,
            logical_groups: usize_field(value, "logical_groups")?,
            planning: usize_field(value, "planning")?,
            execution: usize_field(value, "execution")?,
            diagnostics: usize_field(value, "diagnostics")?,
            cache_hits: usize_field(value, "cache_hits")?,
            oracle_training: usize_field(value, "oracle_training")?,
            oracle_validation: usize_field(value, "oracle_validation")?,
        })
    }
}

pub struct Evaluator<'a> {
    pub context: &'a Context,
    pub identity: String,
    pub threads: usize,
    pub budget: Budget,
    pub cache: BTreeMap<String, Row>,
}

impl Evaluator<'_> {
    pub fn evaluate(
        &mut self,
        base: &AdmittedLayout,
        group: &Group,
        archive_version: usize,
    ) -> Result<Row, String> {
        self.context.check(base).map_err(|e| format!("{e:?}"))?;
        group.validate()?;
        if self.threads == 0 {
            return Err("workers must be positive".to_owned());
        }
        let key = fingerprint(&object([
            ("run", string(&self.identity)),
            ("layout", string(base.physical_identity())),
            ("account", string(base.account_identity())),
            ("archive_version", num(archive_version)),
            ("group", group.to_json()),
            ("knowledge", string("visible-three-priors-v1")),
        ]));
        if let Some(row) = self.cache.get(&key) {
            self.budget.logical_groups += 1;
            self.budget.cache_hits += 1;
            return Ok(row.clone());
        }
        // Reserve the entire group before a worker can start. Charge failures
        // conservatively as well, since some battles may already have run.
        self.budget.reserve(group.physical_cost())?;
        self.budget.logical_groups += 1;
        self.budget.planning += group.scenarios.len() * HIDDEN_SAMPLES;
        self.budget.execution += 1;
        let scorer = Scorer::new(
            self.context.catalog.clone(),
            vec![base.engine_json()],
            group.scenarios.clone(),
            group.plans.clone(),
            (0..group.plans.len()).collect(),
        )?;
        let run = scorer.scout(
            self.context.catalog.clone(),
            0,
            self.threads,
            ScoutPolicy::Visible,
            Some(2),
        )?;
        if run.outcomes.len() != 1 || run.planning_battles != 6 || run.evaluation_battles != 1 {
            return Err("scorer violated the complete two-candidate group contract".to_owned());
        }
        let row = Row {
            group_id: group.id.clone(),
            stratum: group.stratum.clone(),
            population_weight: group.population_weight,
            scenario: run.scenarios[0].clone(),
            outcome: run.outcomes[0],
            source_index: run.source_indices[0],
            plan: group.plans[run.source_indices[0]].clone(),
        };
        self.cache.insert(key, row.clone());
        Ok(row)
    }

    pub fn assess(
        &mut self,
        base: &AdmittedLayout,
        manifest: &Manifest,
        version: usize,
    ) -> Result<Vec<Row>, String> {
        manifest.validate()?;
        manifest
            .groups
            .iter()
            .map(|group| self.evaluate(base, group, version))
            .collect()
    }
}

/// Preserve declared population weights even when strata receive unequal
/// simulation allocations. A committed row is summarized with scout=1.
pub fn summarise(rows: &[Row]) -> Result<Evaluation, String> {
    if rows.is_empty() {
        return Err("cannot summarize empty results".to_owned());
    }
    let mut counts = BTreeMap::<&str, usize>::new();
    for row in rows {
        *counts.entry(&row.stratum).or_default() += 1;
    }
    let scenarios: Vec<_> = rows
        .iter()
        .enumerate()
        .map(|(index, row)| {
            let mut scenario = row.scenario.clone();
            scenario.group = index as i64;
            scenario.full_scout = false;
            scenario.weight = row.population_weight / counts[row.stratum.as_str()] as f64;
            scenario
        })
        .collect();
    scoring::summarise(
        &scenarios,
        &rows.iter().map(|row| row.outcome).collect::<Vec<_>>(),
        Some(1),
    )
}

pub fn objective(
    rows: &[Row],
    mode: &str,
    holes: usize,
    penalty: Option<f64>,
) -> Result<f64, String> {
    Ok(scoring::objective(&summarise(rows)?, mode, holes, penalty))
}

pub fn utility(outcome: Outcome, mode: &str) -> f64 {
    // Obtain the per-observation value through the same objective API.
    let evaluation = Evaluation {
        ranked_trophies: scoring::defender_trophies(outcome.stars, outcome.destruction) as f64,
        three_star_rate: f64::from(outcome.stars >= 3),
        avg_stars: outcome.stars as f64,
        avg_destruction: outcome.destruction,
        th_kill_rate: f64::from(outcome.th_destroyed),
        per_army: Vec::new(),
        worst_side: Vec::new(),
    };
    scoring::objective(&evaluation, mode, 0, Some(0.0))
}
