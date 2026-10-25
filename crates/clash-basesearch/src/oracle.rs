//! Bounded adapters use native compilation and visible-state training. Actual
//! hidden layouts are used only after the proposed program is frozen.
use std::collections::BTreeMap;

use clash_armysearch::{account::AccountRules, genome::ArmyGenome};
use clash_plans::compile::Compiler;
use clash_scoring::scoring::{self, Scenario, Scorer};
use clash_scoring::scouting::{hidden_sample, ScoutPolicy};

use crate::eval::{self, Evaluator, Group, Row};
use crate::json::Json;
use crate::layout::AdmittedLayout;
use crate::util::{fingerprint, num, object, string};
use crate::ProposalRng;

pub struct OracleContext<'a, 'b> {
    pub account: &'a AccountRules,
    pub compiler: &'a Compiler<'b>,
    pub catalog: &'a crate::catalog::Catalog,
}

pub trait AttackOracle {
    fn name(&self) -> &'static str;
    fn proposals(
        &self,
        context: &OracleContext<'_, '_>,
        seeds: &[ArmyGenome],
        seed: u64,
        count: usize,
    ) -> Vec<ArmyGenome>;
}

pub struct PlaybookOracle;

impl AttackOracle for PlaybookOracle {
    fn name(&self) -> &'static str {
        "cited-playbook-tuner-v1"
    }

    fn proposals(
        &self,
        context: &OracleContext<'_, '_>,
        seeds: &[ArmyGenome],
        seed: u64,
        count: usize,
    ) -> Vec<ArmyGenome> {
        let cited: Vec<_> = seeds
            .iter()
            .filter(|genome| genome.plan.family != "generic")
            .collect();
        if cited.is_empty() {
            return Vec::new();
        }
        let mut rng = ProposalRng::new(seed);
        let mut proposals = Vec::new();
        for index in 0..count {
            let mut genome = cited[rng.index(cited.len())].clone();
            genome.plan.angle_offset = std::f64::consts::TAU * (index % 8) as f64 / 8.0;
            genome.plan.tactics[0] = genome.plan.angle_offset;
            genome.plan.tactics[1] = [0.85, 1.0, 1.15][index % 3];
            genome.plan.tactics[4] = [0.8, 1.0, 1.2][index % 3];
            genome.plan.tactics[9] = (index % 8) as f64;
            genome.plan.charge_side = if index % 2 == 0 { "left" } else { "right" }.to_owned();
            genome.plan.program = None;
            if let Ok(plan) =
                context
                    .account
                    .compile(context.compiler, context.catalog, &genome, 0.0, 0)
            {
                if let Some(step) = plan.get("steps").and_then(|steps| {
                    steps.arr().iter().find(|step| {
                        step.get("cite").is_some_and(|cite| !cite.arr().is_empty())
                            && step
                                .get("when")
                                .is_some_and(|when| when.get("after").is_some())
                            && step.get("uncited") != Some(&Json::Bool(true))
                    })
                }) {
                    if let Some(id) = step.get("id").and_then(Json::opt_str) {
                        genome
                            .plan
                            .step_timing
                            .insert(id.to_owned(), if index % 2 == 0 { -0.5 } else { 0.5 });
                    }
                }
            }
            if clash_armysearch::operators::admit(
                context.account,
                context.compiler,
                context.catalog,
                &mut genome,
            )
            .is_ok()
            {
                proposals.push(genome);
            }
        }
        proposals
    }
}

pub struct ArmyProgramOracle;

impl AttackOracle for ArmyProgramOracle {
    fn name(&self) -> &'static str {
        "native-army-program-adapter-v1"
    }

    fn proposals(
        &self,
        context: &OracleContext<'_, '_>,
        seeds: &[ArmyGenome],
        seed: u64,
        count: usize,
    ) -> Vec<ArmyGenome> {
        if seeds.is_empty() {
            return Vec::new();
        }
        let mut rng = clash_armysearch::SearchRandom(seed);
        let mut proposals = Vec::new();
        for index in 0..count {
            let mut genome = seeds[index % seeds.len()].clone();
            if clash_armysearch::program::enable(
                context.account,
                context.compiler,
                context.catalog,
                &mut genome,
            )
            .is_err()
            {
                continue;
            }
            // The native operator mutates composition, loadout or program while
            // retaining AccountRules admission and the existing executor.
            if let Ok(mut mutated) = clash_armysearch::operators::mutate(
                &genome,
                seeds,
                context.account,
                context.compiler,
                context.catalog,
                &mut rng,
            ) {
                if clash_armysearch::program::enable(
                    context.account,
                    context.compiler,
                    context.catalog,
                    &mut mutated,
                )
                .is_ok()
                {
                    genome = mutated;
                }
            }
            if let Ok(mut program_mutation) =
                clash_armysearch::program::mutate::random(&genome, &mut rng)
            {
                if clash_armysearch::operators::admit(
                    context.account,
                    context.compiler,
                    context.catalog,
                    &mut program_mutation,
                )
                .is_ok()
                {
                    genome = program_mutation;
                }
            }
            if clash_armysearch::operators::admit(
                context.account,
                context.compiler,
                context.catalog,
                &mut genome,
            )
            .is_ok()
            {
                proposals.push(genome);
            }
        }
        proposals
    }
}

/// Plan/profile draws depend on the group manifest, never the target layout.
pub fn group_for(
    context: &OracleContext<'_, '_>,
    genome: &ArmyGenome,
    namespace: &str,
    group_seed: i64,
    weight: f64,
    modifier: Option<String>,
) -> Result<Group, String> {
    let army = format!("native:{}", fingerprint(&genome.to_json()));
    let mut rng = ProposalRng::new(group_seed as u64);
    let first = rng.index(8);
    let second = (first + 1 + rng.index(7)) % 8;
    let mut scenarios = Vec::new();
    let mut plans = Vec::new();
    // Side-pair draws integrate the ordinary two-side policy. An oracle's
    // angle offset is a frozen policy parameter, not a hindsight decision.
    for side in [first, second] {
        let angle = std::f64::consts::TAU * side as f64 / 8.0 + genome.plan.angle_offset;
        let seed = group_seed.rem_euclid(1 << 48);
        let mut plan =
            context
                .account
                .compile(context.compiler, context.catalog, genome, angle, seed)?;
        clash_plans::armies::put(&mut plan, "strength", Json::Num(scoring::skill(seed)));
        scenarios.push(Scenario {
            army: army.clone(),
            town_hall: context.account.town_hall,
            angle,
            seed,
            weight: 0.5,
            modifier: modifier.clone(),
            group: group_seed,
            tactic: Json::Null,
            charge: None,
            full_scout: true,
        });
        plans.push(plan);
    }
    let group = Group {
        id: format!("{namespace}/{army}/{group_seed}"),
        stratum: format!("{}:{army}", genome.plan.family),
        population_weight: weight,
        scenarios,
        plans,
    };
    group.validate()?;
    Ok(group)
}

#[derive(Clone, Debug)]
pub struct AttackEntry {
    pub id: String,
    pub genome: ArmyGenome,
    pub metadata: Json,
    pub validation: Vec<Row>,
    pub active: bool,
}

impl AttackEntry {
    pub fn to_json(&self) -> Json {
        object([
            ("id", string(&self.id)),
            ("genome", self.genome.to_json()),
            ("metadata", self.metadata.clone()),
            (
                "validation",
                Json::Arr(self.validation.iter().map(Row::to_json).collect()),
            ),
            ("active", Json::Bool(self.active)),
        ])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        Ok(Self {
            id: value.at("id").str().to_owned(),
            genome: ArmyGenome::from_json(value.at("genome"))?,
            metadata: value.at("metadata").clone(),
            validation: value
                .at("validation")
                .arr()
                .iter()
                .map(Row::from_json)
                .collect(),
            active: value.at("active").bool(),
        })
    }
}

#[derive(Clone, Debug, Default)]
pub struct AttackArchive {
    pub version: usize,
    /// Permanent hall of fame, including entries outside the active subset.
    pub entries: BTreeMap<String, AttackEntry>,
    /// Keys bind a base physical identity and a frozen attack identity.
    pub payoffs: BTreeMap<String, BTreeMap<String, Vec<Row>>>,
}

impl AttackArchive {
    pub fn compatible(&self, entry: &AttackEntry) -> Result<(), String> {
        let partition = |metadata: &Json| {
            fingerprint(&object([
                (
                    "account",
                    metadata.get("account").cloned().unwrap_or(Json::Null),
                ),
                ("mode", metadata.get("mode").cloned().unwrap_or(Json::Null)),
                (
                    "town_hall",
                    metadata.get("town_hall").cloned().unwrap_or(Json::Null),
                ),
                (
                    "modifier",
                    metadata.get("modifier").cloned().unwrap_or(Json::Null),
                ),
            ]))
        };
        if self
            .entries
            .values()
            .any(|current| partition(&current.metadata) != partition(&entry.metadata))
        {
            return Err(
                "attack archive mixes incompatible TH/account/mode/modifier partitions".to_owned(),
            );
        }
        Ok(())
    }

    pub fn insert(&mut self, entry: AttackEntry) -> bool {
        if self.entries.contains_key(&entry.id) {
            return false;
        }
        self.entries.insert(entry.id.clone(), entry);
        self.version += 1;
        true
    }

    pub fn to_json(&self) -> Json {
        object([
            ("version", num(self.version)),
            (
                "entries",
                Json::Arr(self.entries.values().map(AttackEntry::to_json).collect()),
            ),
            (
                "payoffs",
                Json::Obj(
                    self.payoffs
                        .iter()
                        .map(|(base, attacks)| {
                            (
                                base.clone(),
                                Json::Obj(
                                    attacks
                                        .iter()
                                        .map(|(attack, rows)| {
                                            (
                                                attack.clone(),
                                                Json::Arr(rows.iter().map(Row::to_json).collect()),
                                            )
                                        })
                                        .collect(),
                                ),
                            )
                        })
                        .collect(),
                ),
            ),
        ])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        let mut archive = Self {
            version: value.at("version").usize(),
            ..Self::default()
        };
        for value in value.at("entries").arr() {
            let entry = AttackEntry::from_json(value)?;
            if archive.entries.insert(entry.id.clone(), entry).is_some() {
                return Err("duplicate archived attack".to_owned());
            }
        }
        for (base, attacks) in value.at("payoffs").obj() {
            archive.payoffs.insert(
                base.clone(),
                attacks
                    .obj()
                    .iter()
                    .map(|(attack, rows)| {
                        (
                            attack.clone(),
                            rows.arr().iter().map(Row::from_json).collect(),
                        )
                    })
                    .collect(),
            );
        }
        Ok(archive)
    }

    pub fn matrix(
        &self,
        bases: &[String],
        mode: &str,
    ) -> Result<(Vec<String>, Vec<Vec<f64>>), String> {
        let attacks: Vec<_> = self
            .entries
            .values()
            .filter(|entry| entry.active)
            .map(|entry| entry.id.clone())
            .collect();
        let matrix = bases
            .iter()
            .map(|base| {
                attacks
                    .iter()
                    .map(|attack| {
                        let rows = self
                            .payoffs
                            .get(base)
                            .and_then(|values| values.get(attack))
                            .ok_or("missing payoff; elite requires reevaluation")?;
                        eval::objective(rows, mode, 0, Some(0.0))
                    })
                    .collect::<Result<Vec<_>, String>>()
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok((attacks, matrix))
    }
}

/// Each adapter gets an all-in physical budget. All selection feedback is from
/// independent plausible hidden states; actual target traps never train it.
pub fn discover(
    oracle: &dyn AttackOracle,
    context: &OracleContext<'_, '_>,
    seeds: &[ArmyGenome],
    target: &AdmittedLayout,
    evaluator: &mut Evaluator<'_>,
    archive: &AttackArchive,
    seed: u64,
    physical_budget: usize,
    mode: &str,
    modifier: Option<String>,
) -> Result<Option<AttackEntry>, String> {
    let group_cost = 7;
    let validation_groups = 2;
    let candidates = (physical_budget / group_cost).saturating_sub(validation_groups) / 2;
    if candidates == 0 {
        return Ok(None);
    }
    evaluator.budget.reserve(physical_budget)?;
    let proposals = oracle.proposals(context, seeds, seed, candidates);
    let mut best: Option<(f64, ArmyGenome)> = None;
    let start = evaluator.budget.used();
    let mut evaluated = 0;
    for genome in proposals {
        let id = fingerprint(&genome.to_json());
        if archive.entries.contains_key(&id) {
            continue;
        }
        let mut values = Vec::new();
        for replicate in 0..2 {
            let group_seed = ((seed & ((1 << 40) - 1)) + replicate) as i64 + (1 << 44);
            let group = group_for(
                context,
                &genome,
                "oracle-training",
                group_seed,
                1.0,
                modifier.clone(),
            )?;
            evaluator.budget.reserve(group.physical_cost())?;
            evaluator.budget.planning += 6;
            evaluator.budget.execution += 1;
            evaluator.budget.oracle_training += 7;
            evaluator.budget.logical_groups += 1;
            let hidden = hidden_sample(
                &target.engine_json(),
                &evaluator.context.catalog,
                group_seed,
            )?;
            let scorer = Scorer::new(
                evaluator.context.catalog.clone(),
                vec![hidden],
                group.scenarios,
                group.plans,
                vec![0, 1],
            )?;
            let run = scorer.scout(
                evaluator.context.catalog.clone(),
                0,
                evaluator.threads,
                ScoutPolicy::Visible,
                Some(2),
            )?;
            values.push(eval::utility(run.outcomes[0], mode));
        }
        evaluated += 1;
        let mean = values.iter().sum::<f64>() / values.len() as f64;
        if best.as_ref().is_none_or(|(value, current)| {
            mean < *value || (mean == *value && genome.identity() < current.identity())
        }) {
            best = Some((mean, genome));
        }
    }
    let Some((training, genome)) = best else {
        return Ok(None);
    };
    // Freeze before fresh actual-state validation. No program changes follow.
    let id = fingerprint(&genome.to_json());
    let mut validation = Vec::new();
    for replicate in 0..validation_groups {
        let group_seed = ((seed & ((1 << 40) - 1)) + replicate as u64) as i64 + (2 << 44);
        let group = group_for(
            context,
            &genome,
            "oracle-fresh-validation",
            group_seed,
            1.0,
            modifier.clone(),
        )?;
        let before = evaluator.budget.used();
        validation.push(evaluator.evaluate(target, &group, archive.version)?);
        evaluator.budget.oracle_validation += evaluator.budget.used() - before;
    }
    let cost = evaluator.budget.used() - start;
    if cost > physical_budget {
        return Err("oracle exceeded its all-in battle budget".to_owned());
    }
    let metadata = object([
        ("adapter", string(oracle.name())),
        (
            "knowledge",
            string(
                "visible; three independent hidden priors; program frozen before actual validation",
            ),
        ),
        (
            "evidence",
            string("synthetic/model discovery; uncalibrated execution profiles"),
        ),
        ("compiler", string(&evaluator.identity)),
        ("account", context.compiler.library.user.clone()),
        ("town_hall", Json::Num(context.account.town_hall as f64)),
        ("mode", string(mode)),
        ("modifier", modifier.map_or(Json::Null, string)),
        ("target_lineage", string(target.physical_identity())),
        ("seed", string(seed.to_string())),
        ("physical_budget", num(physical_budget)),
        ("physical_cost", num(cost)),
        ("candidates_evaluated", num(evaluated)),
        ("training_defender_utility", Json::Num(training)),
        (
            "fresh_defender_utility",
            Json::Num(eval::objective(&validation, mode, 0, Some(0.0))?),
        ),
        (
            "mechanic_sensitivities",
            string("frozen v29 combat, stat skill model, uniform hidden placement prior"),
        ),
    ]);
    Ok(Some(AttackEntry {
        id,
        genome,
        metadata,
        validation,
        active: true,
    }))
}
