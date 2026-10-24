//! MAP-Elites over family/main troop x hero set, fixed waves and paired racing.

use std::cmp::Ordering;
use std::collections::{BTreeMap, BTreeSet};

use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::Json;

use super::account::AccountRules;
use super::eval::Evaluator;
use super::genome::ArmyGenome;
use super::operators;
use super::program;
use super::score::{paired_interval, CandidateEstimate, Stage, TargetManifest};
use super::themed;
use super::util::{array, number, object, string, text, Random};

pub const CELL_CAPACITY: usize = 3;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Families {
    All,
    Playbook,
    Generic,
}

impl Families {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "all" => Ok(Self::All),
            "playbook" => Ok(Self::Playbook),
            "generic" => Ok(Self::Generic),
            _ => Err("families must be all, playbook, or generic".to_owned()),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::All => "all",
            Self::Playbook => "playbook",
            Self::Generic => "generic",
        }
    }

    pub fn allows(self, genome: &ArmyGenome) -> bool {
        match self {
            Self::All => true,
            Self::Playbook => genome.plan.family != "generic",
            Self::Generic => genome.plan.family == "generic",
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct ProposalSettings {
    pub themed_fraction: f64,
    pub random_fraction: f64,
    pub families: Families,
    pub programs: bool,
    pub program_mutation_rate: f64,
}

impl Default for ProposalSettings {
    fn default() -> Self {
        Self {
            themed_fraction: 0.25,
            random_fraction: 0.05,
            families: Families::All,
            programs: true,
            program_mutation_rate: 0.5,
        }
    }
}

impl ProposalSettings {
    pub fn validate(self) -> Result<(), String> {
        if !self.program_mutation_rate.is_finite()
            || !(0.0..=1.0).contains(&self.program_mutation_rate)
        {
            return Err("program mutation rate must be finite and in [0,1]".to_owned());
        }
        if !self.themed_fraction.is_finite()
            || !self.random_fraction.is_finite()
            || !(0.0..=1.0).contains(&self.themed_fraction)
            || !(0.0..=1.0).contains(&self.random_fraction)
            || self.themed_fraction + self.random_fraction > 1.0
        {
            return Err(
                "immigrant fractions must be finite, in [0,1], and sum to at most 1".to_owned(),
            );
        }
        Ok(())
    }

    /// Nearest whole slots per batch, with themed slots allocated first.
    /// Playbook-only searches devote all slots to compatible seeds/offspring.
    pub fn immigrant_counts(self, count: usize) -> (usize, usize) {
        if self.families == Families::Playbook {
            return (0, 0);
        }
        let themed = ((count as f64 * self.themed_fraction).round() as usize).min(count);
        let random = ((count as f64 * self.random_fraction).round() as usize).min(count - themed);
        (themed, random)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Objective {
    Ranked,
    Stars,
    Destruction
}

impl Objective {
    pub fn parse(value: &str) -> Result<Self, String> {
        match value {
            "ranked" => Ok(Self::Ranked),
            "stars" => Ok(Self::Stars),
            "destruction" => Ok(Self::Destruction),
            _ => Err("objective must be ranked, stars, or destruction".to_owned()),
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Self::Ranked => "ranked",
            Self::Stars => "stars",
            Self::Destruction => "destruction"
        }
    }
}

#[derive(Clone, Debug)]
pub struct Elite {
    pub genome: ArmyGenome,
    pub quick: CandidateEstimate,
    pub confirm: CandidateEstimate,
}

impl Elite {
    pub fn to_json(&self) -> Json {
        object([("genome", self.genome.to_json()), ("quick", self.quick.to_json()), ("confirm", self.confirm.to_json())])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        Ok(Self {
            genome: ArmyGenome::from_json(value.at("genome"))?,
            quick: CandidateEstimate::from_json(value.at("quick"))?,
            confirm: CandidateEstimate::from_json(value.at("confirm"))?
        })
    }
}

#[derive(Clone, Debug)]
pub struct SearchState {
    pub completed_batches: usize,
    pub seed_cursor: usize,
    pub rng: Random,
    pub archive: BTreeMap<String, Vec<Elite>>,
    pub seen: BTreeSet<String>,
    pub rejected: BTreeMap<String, usize>,
    pub assessments: usize,
    pub logical_battles: usize,
    pub raced_out: usize,
    pub raw_bytes: u64,
}

impl SearchState {
    pub fn new(seed: u64) -> Self {
        Self {
            completed_batches: 0,
            seed_cursor: 0,
            rng: Random(seed),
            archive: BTreeMap::new(),
            seen: BTreeSet::new(),
            rejected: BTreeMap::new(),
            assessments: 0,
            logical_battles: 0,
            raced_out: 0,
            raw_bytes: 0,
        }
    }

    pub fn rejection(&mut self, reason: String) {
        *self.rejected.entry(reason).or_default() += 1;
    }

    pub fn elites(&self, objective: Objective) -> Vec<Elite> {
        let mut result: Vec<Elite> = self.archive.values().flatten().cloned().collect();
        result.sort_by(|a, b| compare(a, b, objective));
        result
    }

    pub fn insert(&mut self, elite: Elite, objective: Objective, account: &AccountRules) {
        let cell = self.archive.entry(elite.genome.cell(account)).or_default();
        let identity = elite.genome.identity();
        cell.retain(|old| old.genome.identity() != identity);
        cell.push(elite);
        cell.sort_by(|a, b| compare(a, b, objective));
        cell.truncate(CELL_CAPACITY);
    }

    pub fn to_json(&self) -> Json {
        object([
            ("completed_batches", number(self.completed_batches)),
            ("seed_cursor", number(self.seed_cursor)),
            ("rng", string(self.rng.0.to_string())),
            ("archive", Json::Arr(self.archive.values().flatten().map(Elite::to_json).collect())),
            ("seen", Json::Arr(self.seen.iter().map(string).collect())),
            ("rejected", Json::Obj(self.rejected.iter().map(|(key, count)| (key
                .clone(), number(*count))).collect())),
            ("assessments", number(self.assessments)),
            ("logical_battles", number(self.logical_battles)),
            ("raced_out", number(self.raced_out)),
            ("raw_bytes", string(self.raw_bytes.to_string())),
        ])
    }

    pub fn from_json(
        value: &Json,
        objective: Objective,
        account: &AccountRules,
    ) -> Result<Self, String> {
        let rng = text(value, "rng", "").parse::<u64>().map_err(|_| "bad checkpoint RNG state")?;
        let mut result = Self::new(rng);
        result.completed_batches = value.at("completed_batches").usize();
        result.seed_cursor = value.at("seed_cursor").usize();
        result.assessments = value.at("assessments").usize();
        result.logical_battles = value.at("logical_battles").usize();
        result.raced_out = value.at("raced_out").usize();
        result.raw_bytes = value.at("raw_bytes").str().parse::<u64>()
            .map_err(|_| "bad checkpoint raw output offset")?;
        result.seen = array(value, "seen").iter().map(|value| value.str().to_owned()).collect();
        result.rejected = value.at("rejected").obj().iter().map(|(key, value)| (key.clone(), value
            .usize())).collect();
        for elite in array(value, "archive") {
            result.insert(Elite::from_json(elite)?, objective, account);
        }
        Ok(result)
    }
}

pub fn compare(first: &Elite, second: &Elite, objective: Objective) -> Ordering {
    compare_estimates(&first.confirm, &second.confirm, objective)
        .then_with(|| first.genome.identity().cmp(&second.genome.identity()))
}

fn compare_estimates(
    first: &CandidateEstimate,
    second: &CandidateEstimate,
    objective: Objective,
) -> Ordering {
    let a = first.metrics;
    let b = second.metrics;
    let primary = match objective {
        Objective::Ranked => b.trophies.total_cmp(&a.trophies),
        Objective::Stars => b.stars.total_cmp(&a.stars),
        Objective::Destruction => b.destruction.total_cmp(&a.destruction),
    };
    primary.then_with(|| b.stars.total_cmp(&a.stars))
        .then_with(|| b.destruction.total_cmp(&a.destruction))
        .then_with(|| b.trophies.total_cmp(&a.trophies))
}

pub fn proposals(
    state: &mut SearchState,
    count: usize,
    templates: &[ArmyGenome],
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: &Catalog,
    settings: ProposalSettings,
) -> Vec<ArmyGenome> {
    // Archive is frozen for the entire wave, independent of worker completion.
    let parents: Vec<ArmyGenome> = state
        .archive
        .values()
        .flatten()
        .filter(|elite| settings.families.allows(&elite.genome))
        .map(|elite| elite.genome.clone())
        .collect();
    let templates: Vec<ArmyGenome> = templates
        .iter()
        .filter(|genome| settings.families.allows(genome))
        .cloned()
        .collect();
    let (themed_count, random_count) = settings.immigrant_counts(count);
    let mut result = Vec::new();
    let mut attempts = 0;
    while result.len() < count && attempts < count.saturating_mul(100).max(100) {
        attempts += 1;
        let candidate = if result.len() < themed_count + random_count {
            let immigrant = if result.len() < themed_count {
                themed::immigrant(account, catalog, &mut state.rng)
            } else {
                operators::immigrant(account, &mut state.rng)
            };
            immigrant.and_then(|mut genome| {
                operators::admit(account, compiler, catalog, &mut genome)?;
                Ok(genome)
            })
        } else if state.seed_cursor < templates.len() {
            let candidate = templates[state.seed_cursor].clone();
            state.seed_cursor += 1;
            Ok(candidate)
        } else {
            let pool = if parents.is_empty() {
                &templates
            } else {
                &parents
            };
            if pool.is_empty() {
                state.rejection(
                    "no seeds or parents for selected families and immigrant mix".to_owned(),
                );
                break;
            }
            let parent = &pool[state.rng.index(pool.len())];
            if settings.programs && state.rng.unit() < settings.program_mutation_rate {
                let mut parent = parent.clone();
                let enabled = program::enable(account, compiler, catalog, &mut parent);
                enabled.and_then(|()| {
                    let compatible: Vec<_> = pool.iter().filter(|other| {
                        other.plan.program.is_some()
                            && program::army_identity(other) == program::army_identity(&parent)
                    }).collect();
                    if !compatible.is_empty() && state.rng.index(5) == 0 {
                        program::mutate::crossover(&parent, compatible[state.rng.index(compatible.len())], &mut state.rng)
                    } else {
                        program::mutate::random(&parent, &mut state.rng)
                    }
                })
            } else if state.rng.index(5) == 0 {
                let compatible: Vec<&ArmyGenome> = pool.iter().filter(|other| other.plan.family == parent.plan.family).collect();
                let other = compatible[state.rng.index(compatible.len())];
                operators::crossover(parent, other, account, compiler, catalog, &mut state.rng)
            } else {
                let mutation_templates = if templates.is_empty() {
                    pool
                } else {
                    &templates
                };
                operators::mutate(
                    parent,
                    mutation_templates,
                    account,
                    compiler,
                    catalog,
                    &mut state.rng,
                )
            }
        };
        let candidate = candidate.and_then(|mut genome| {
            if settings.programs {
                program::enable(account, compiler, catalog, &mut genome)?;
            } else {
                genome.plan.program = None;
            }
            operators::admit(account, compiler, catalog, &mut genome)?;
            Ok(genome)
        });
        match candidate {
            Ok(candidate) => {
                if settings.families.allows(&candidate) && state.seen.insert(candidate.identity()) {
                    result.push(candidate);
                }
            }
            Err(reason) => state.rejection(reason),
        }
    }
    result.sort_by_key(ArmyGenome::identity);
    result
}

/// Both the real runner and proof evaluator pass through these admission,
/// promotion and archive operations. All decisions happen in canonical order.
pub fn assess_wave(
    state: &mut SearchState,
    candidates: Vec<ArmyGenome>,
    evaluator: &mut impl Evaluator,
    manifest: &TargetManifest,
    quick_budget: usize,
    confirm_budget: usize,
    objective: Objective,
    account: &AccountRules,
) {
    let mut quick = Vec::new();
    for candidate in candidates {
        state.assessments += 1;
        match evaluator.evaluate(&candidate, Stage::Quick, quick_budget) {
            Ok(estimate) => {
                state.logical_battles += estimate.battles;
                quick.push((candidate, estimate));
            }
            Err(reason) => state.rejection(format!("quick: {reason}")),
        }
    }
    quick.sort_by(|(a, ae), (b, be)| compare_estimates(ae, be, objective).then_with(|| a.identity()
        .cmp(&b.identity())));
    let mut promotions = Vec::new();
    let mut promoted_per_cell = BTreeMap::<String, usize>::new();
    for (candidate, estimate) in quick {
        let cell = candidate.cell(account);
        let count = promoted_per_cell.entry(cell.clone()).or_default();
        if *count >= CELL_CAPACITY {
            state.raced_out += 1;
            continue;
        }
        if objective == Objective::Ranked {
            if let Some(incumbents) = state.archive.get(&cell).filter(|entries| entries
                .len() == CELL_CAPACITY) {
                let incumbent = incumbents.last().expect("full cell");
                let enough_groups = estimate.bases.iter().all(|base| base.groups.len() >= 2);
                let (_, upper) = paired_interval(manifest, &estimate, &incumbent.quick);
                if enough_groups && upper < 0.0 {
                    state.raced_out += 1;
                    continue;
                }
            }
        }
        *count += 1;
        promotions.push((candidate, estimate));
    }
    promotions.sort_by_key(|(candidate, _)| candidate.identity());
    let mut confirmed = Vec::new();
    for (candidate, quick) in promotions {
        match evaluator.evaluate(&candidate, Stage::Confirm, confirm_budget) {
            Ok(confirm) => {
                state.logical_battles += confirm.battles;
                confirmed.push(Elite {
                    genome: candidate,
                    quick,
                    confirm
                });
            }
            Err(reason) => state.rejection(format!("confirm: {reason}")),
        }
    }
    for elite in confirmed {
        state.insert(elite, objective, account);
    }
    state.completed_batches += 1;
}

pub fn pareto(elites: &[Elite]) -> Vec<Elite> {
    elites.iter().filter(|elite| {
        let a = elite.confirm.metrics;
        !elites.iter().any(|other| {
            let b = other.confirm.metrics;
            b.trophies >= a.trophies && b.three_star_rate >= a.three_star_rate && b.destruction >= a.destruction
                && (b.trophies > a.trophies || b.three_star_rate > a.three_star_rate || b.destruction > a.destruction)
        })
    }).cloned().collect()
}
