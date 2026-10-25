//! Weighted targets and complete scouting groups; evaluate.py:467,723-762.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use crate::json::Json;
use crate::scoring::{self, Outcome, Scenario};

use super::util::{array, encode, hash, number, numeric, object, read, string, text};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Split {
    Search,
    Holdout,
}

impl Split {
    pub fn name(self) -> &'static str {
        match self {
            Self::Search => "search",
            Self::Holdout => "holdout",
        }
    }
}

#[derive(Clone, Debug)]
pub struct Target {
    pub id: String,
    pub path: PathBuf,
    pub weight: f64,
    pub split: Split,
    pub lineage: String,
    pub provenance: String,
    pub layout: Json,
    pub town_hall: i64,
}

#[derive(Clone, Debug)]
pub struct TargetManifest {
    pub targets: Vec<Target>,
}

impl TargetManifest {
    pub fn load(root: &Path, manifest: Option<&Path>) -> Result<Self, String> {
        let source = if let Some(path) = manifest {
            read(path)?
        } else {
            Self::default_json()
        };
        let entries = match &source {
            Json::Arr(entries) => entries.as_slice(),
            _ => source
                .get("targets")
                .or_else(|| source.get("bases"))
                .ok_or("manifest requires targets")?
                .arr(),
        };
        let mut targets = Vec::new();
        let mut ids = BTreeSet::new();
        let mut paths = BTreeSet::new();
        let mut lineages = BTreeMap::new();
        let mut layouts = BTreeMap::new();
        for entry in entries {
            let path = PathBuf::from(text(entry, "path", ""));
            if path.as_os_str().is_empty() {
                return Err("target requires a path".to_owned());
            }
            let path = if path.is_absolute() {
                path
            } else {
                let rooted = root.join(&path);
                if rooted.exists() {
                    rooted
                } else {
                    manifest.and_then(Path::parent).unwrap_or(root).join(path)
                }
            };
            let path = path
                .canonicalize()
                .map_err(|error| format!("{}: {error}", path.display()))?;
            let fallback = path
                .file_stem()
                .and_then(|name| name.to_str())
                .unwrap_or("base");
            let id = text(entry, "id", fallback).to_owned();
            if !ids.insert(id.clone()) || !paths.insert(path.clone()) {
                return Err(format!("duplicate target id or path: {id}"));
            }
            let split = match text(entry, "split", "") {
                "search" => Split::Search,
                "holdout" => Split::Holdout,
                _ => return Err(format!("{id}: split must be search or holdout")),
            };
            let weight = numeric(entry, "weight", 1.0);
            if !weight.is_finite() || weight <= 0.0 {
                return Err(format!("{id}: weight must be finite and positive"));
            }
            let lineage = text(entry, "lineage", &id).to_owned();
            if lineages
                .insert(lineage.clone(), split)
                .is_some_and(|old| old != split)
            {
                return Err(format!("lineage crosses search/holdout: {lineage}"));
            }
            let layout = read(&path)?;
            let town_hall = numeric(&layout, "town_hall", 16.0) as i64;
            if !(16..=18).contains(&town_hall) {
                return Err(format!("{id}: defender TH must be 16..18"));
            }
            let geometry = layout_identity(&layout);
            if layouts
                .insert(geometry, split)
                .is_some_and(|old| old != split)
            {
                return Err(format!("duplicate layout crosses search/holdout: {id}"));
            }
            let provenance = text(
                entry,
                "provenance",
                text(entry, "label", "unspecified layout provenance"),
            )
            .to_owned();
            targets.push(Target {
                id,
                path,
                weight,
                split,
                lineage,
                provenance,
                layout,
                town_hall,
            });
        }
        if !targets.iter().any(|target| target.split == Split::Search)
            || !targets.iter().any(|target| target.split == Split::Holdout)
        {
            return Err("manifest needs independent search and holdout targets".to_owned());
        }
        for split in [Split::Search, Split::Holdout] {
            let weight: f64 = targets
                .iter()
                .filter(|target| target.split == split)
                .map(|target| target.weight)
                .sum();
            if !weight.is_finite() || weight <= 0.0 {
                return Err(format!("{} weights cannot be normalized", split.name()));
            }
        }
        Ok(Self { targets })
    }

    pub fn default_json() -> Json {
        let mut targets = Vec::new();
        for index in 1..=10 {
            targets.push(object([
                ("id", string(format!("rb{index:02}"))),
                ("path", string(format!("data/reference-bases/ranked-2026-10-24/rb{index:02}.json"))),
                ("weight", Json::Num(1.0)),
                ("split", string(if index <= 8 {
                    "search"
                } else {
                    "holdout"
                })),
                ("provenance", string("real ranked screenshot transcription; visible layout, omitted hidden defenses/traps and geometric uncertainty")),
            ]));
        }
        for (id, path, weight, provenance) in [
            (
                "your-base",
                "data/reference-bases/your-base.json",
                1.0,
                "account layout",
            ),
            (
                "target17",
                "output/bases/target17-winner.json",
                0.25,
                "generated TH17 target; synthetic",
            ),
            (
                "target18",
                "output/bases/target18-winner.json",
                0.25,
                "generated TH18 target; synthetic",
            ),
        ] {
            targets.push(object([
                ("id", string(id)),
                ("path", string(path)),
                ("weight", Json::Num(weight)),
                ("split", string("search")),
                ("provenance", string(provenance)),
            ]));
        }
        object([("targets", Json::Arr(targets))])
    }

    pub fn to_json(&self) -> Json {
        object([(
            "targets",
            Json::Arr(
                self.targets
                    .iter()
                    .map(|target| {
                        object([
                            ("id", string(&target.id)),
                            ("path", string(target.path.to_string_lossy())),
                            ("weight", Json::Num(target.weight)),
                            ("split", string(target.split.name())),
                            ("lineage", string(&target.lineage)),
                            ("provenance", string(&target.provenance)),
                            ("town_hall", Json::Num(target.town_hall as f64)),
                        ])
                    })
                    .collect(),
            ),
        )])
    }
}

pub(super) fn layout_identity(layout: &Json) -> String {
    let mut geometry = layout.clone();
    if let Json::Obj(items) = &mut geometry {
        items
            .retain(|(key, _)| !matches!(key.as_str(), "name" | "notes" | "source" | "provenance"));
        // setup.rs:514 and Layout.from_json: walls are a sorted, deduplicated
        // tile set. Buildings and traps retain their execution/tie-break order.
        if let Some((_, Json::Arr(walls))) = items.iter_mut().find(|(key, _)| key == "walls") {
            let mut tiles: Vec<_> = walls
                .iter()
                .map(|wall| {
                    let pair = wall.arr();
                    (pair[0].i64(), pair[1].i64())
                })
                .collect();
            tiles.sort();
            tiles.dedup();
            *walls = tiles
                .into_iter()
                .map(|(x, y)| Json::Arr(vec![Json::Num(x as f64), Json::Num(y as f64)]))
                .collect();
        }
    }
    // evaluate.py:467 groups the same battlefield independently of labels.
    // Sort object keys recursively; other arrays retain their execution order.
    encode(&super::program::canonical(&geometry))
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Stage {
    Quick,
    Confirm,
    Finalist,
    Holdout,
}

impl Stage {
    pub fn name(self) -> &'static str {
        match self {
            Self::Quick => "quick",
            Self::Confirm => "confirm",
            Self::Finalist => "finalist",
            Self::Holdout => "holdout",
        }
    }

    pub fn split(self) -> Split {
        if self == Self::Holdout {
            Split::Holdout
        } else {
            Split::Search
        }
    }
}

#[derive(Clone, Debug)]
pub struct ScenarioKey {
    pub target: usize,
    pub replicate: usize,
    pub side: usize,
    pub sides: usize,
    pub seed: i64,
    pub angle: f64,
}

/// A budget is a per-candidate battle ceiling. Start with two sides per base,
/// allocate quick sides proportional to weight, then add complete replicate
/// groups. Unspendable remainders are reported, never charged as battles.
pub fn allocate(
    manifest: &TargetManifest,
    stage: Stage,
    budget: usize,
    seed: u64,
) -> Result<Vec<ScenarioKey>, String> {
    let bases: Vec<usize> = manifest
        .targets
        .iter()
        .enumerate()
        .filter(|(_, target)| target.split == stage.split())
        .map(|(index, _)| index)
        .collect();
    if bases.is_empty() || budget < bases.len() * scoring::SCOUT {
        return Err(format!(
            "{} budget requires at least {} battles",
            stage.name(),
            bases.len() * scoring::SCOUT
        ));
    }
    let max_weight = bases
        .iter()
        .map(|index| manifest.targets[*index].weight)
        .fold(0.0_f64, f64::max);
    let limits: Vec<usize> = bases
        .iter()
        .map(|index| {
            if stage == Stage::Quick {
                ((4.0 * manifest.targets[*index].weight / max_weight).ceil() as usize)
                    .clamp(scoring::SCOUT, 4)
            } else {
                8
            }
        })
        .collect();
    let mut sides = vec![scoring::SCOUT; bases.len()];
    let mut used = sides.iter().sum::<usize>();
    while used < budget {
        let choice = (0..bases.len())
            .filter(|index| sides[*index] < limits[*index])
            .max_by(|a, b| {
                let left = manifest.targets[bases[*a]].weight / sides[*a] as f64;
                let right = manifest.targets[bases[*b]].weight / sides[*b] as f64;
                left.total_cmp(&right).then_with(|| b.cmp(a))
            });
        let Some(index) = choice else {
            break;
        };
        sides[index] += 1;
        used += 1;
    }
    let mut replicates = vec![1usize; bases.len()];
    // Two groups make paired uncertainty usable even for low-weight targets.
    // Keep the one-group contract for deliberately tiny proof/smoke budgets.
    if used <= budget / 2 {
        replicates.fill(2);
        used *= 2;
    }
    while used < budget {
        let choice = (0..bases.len())
            .filter(|index| used + sides[*index] <= budget)
            .max_by(|a, b| {
                let left = manifest.targets[bases[*a]].weight / replicates[*a] as f64;
                let right = manifest.targets[bases[*b]].weight / replicates[*b] as f64;
                left.total_cmp(&right).then_with(|| b.cmp(a))
            });
        let Some(index) = choice else {
            break;
        };
        replicates[index] += 1;
        used += sides[index];
    }
    let mut result = Vec::new();
    for (position, target) in bases.into_iter().enumerate() {
        for replicate in 0..replicates[position] {
            let seed_key = format!(
                "armysearch-v1|{seed}|{}|{}|{replicate}",
                stage.name(),
                manifest.targets[target].id
            );
            // Exactly representable in Json's f64 and disjoint stage domains.
            let domain = match stage {
                Stage::Quick => 0,
                Stage::Confirm => 1,
                Stage::Holdout => 2,
                // output/hunt/r16/v2.out #1: frozen finalists, same search bases,
                // fresh seeds whose high bits cannot collide with quick/confirm.
                Stage::Finalist => 3,
            };
            let battle_seed =
                ((hash(seed_key.as_bytes()) & ((1_u64 << 48) - 1)) | (domain << 48)) as i64;
            let offset = if stage == Stage::Holdout {
                std::f64::consts::PI / sides[position] as f64
            } else {
                0.0
            };
            for (side, angle) in scoring::angles(sides[position], offset)
                .into_iter()
                .enumerate()
            {
                result.push(ScenarioKey {
                    target,
                    replicate,
                    side,
                    sides: sides[position],
                    seed: battle_seed,
                    angle,
                });
            }
        }
    }
    Ok(result)
}

#[derive(Clone, Copy, Debug, Default)]
pub struct BattleMetrics {
    pub trophies: f64,
    pub three_star_rate: f64,
    pub destruction: f64,
    pub stars: f64,
}

impl BattleMetrics {
    pub fn to_json(self) -> Json {
        object([
            ("attacker_trophies", Json::Num(self.trophies)),
            ("three_star_rate", Json::Num(self.three_star_rate)),
            ("destruction", Json::Num(self.destruction)),
            ("stars", Json::Num(self.stars)),
        ])
    }

    pub fn from_json(value: &Json) -> Self {
        Self {
            trophies: value.at("attacker_trophies").f64(),
            three_star_rate: value.at("three_star_rate").f64(),
            destruction: value.at("destruction").f64(),
            stars: value.at("stars").f64(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct BaseEstimate {
    pub target: usize,
    pub metrics: BattleMetrics,
    pub groups: Vec<BattleMetrics>,
    pub standard_error: f64,
}

#[derive(Clone, Debug)]
pub struct CandidateEstimate {
    pub stage: Stage,
    pub metrics: BattleMetrics,
    pub bases: Vec<BaseEstimate>,
    pub battles: usize,
    pub unused_budget: usize,
    pub standard_error: f64,
}

fn average(values: &[BattleMetrics]) -> BattleMetrics {
    let mut result = BattleMetrics::default();
    for value in values {
        result.trophies += value.trophies;
        result.three_star_rate += value.three_star_rate;
        result.destruction += value.destruction;
        result.stars += value.stars;
    }
    let n = values.len() as f64;
    result.trophies /= n;
    result.three_star_rate /= n;
    result.destruction /= n;
    result.stars /= n;
    result
}

fn standard_error(groups: &[BattleMetrics]) -> f64 {
    if groups.len() < 2 {
        return 0.0;
    }
    let mean = average(groups).trophies;
    let mut variance = 0.0;
    for group in groups {
        variance += (group.trophies - mean) * (group.trophies - mean);
    }
    (variance / (groups.len() - 1) as f64 / groups.len() as f64).sqrt()
}

pub fn summarise(
    manifest: &TargetManifest,
    stage: Stage,
    keys: &[ScenarioKey],
    outcomes: &[Outcome],
    budget: usize,
) -> Result<CandidateEstimate, String> {
    if keys.len() != outcomes.len() {
        return Err("scenario/result count differs".to_owned());
    }
    let mut bases = Vec::new();
    for (target, base) in manifest
        .targets
        .iter()
        .enumerate()
        .filter(|(_, base)| base.split == stage.split())
    {
        let indices: Vec<usize> = keys
            .iter()
            .enumerate()
            .filter(|(_, key)| key.target == target)
            .map(|(index, _)| index)
            .collect();
        let max_group = indices
            .iter()
            .map(|index| keys[*index].replicate)
            .max()
            .ok_or("missing base coverage")?;
        let mut groups = Vec::new();
        for replicate in 0..=max_group {
            let group: Vec<usize> = indices
                .iter()
                .copied()
                .filter(|index| keys[*index].replicate == replicate)
                .collect();
            if group.is_empty() {
                return Err("missing replicate".to_owned());
            }
            let scenarios: Vec<Scenario> = group
                .iter()
                .map(|index| Scenario {
                    army: base.id.clone(),
                    town_hall: base.town_hall,
                    angle: keys[*index].angle,
                    seed: keys[*index].seed,
                    weight: 1.0 / group.len() as f64,
                    modifier: None,
                    group: replicate as i64,
                    tactic: Json::Null,
                    charge: None,
                    full_scout: false,
                })
                .collect();
            let outcomes: Vec<Outcome> = group.iter().map(|index| outcomes[*index]).collect();
            let selected = scoring::scouted(&scenarios, &outcomes, Some(scoring::SCOUT));
            let mut metrics = BattleMetrics::default();
            for selection in selected {
                let outcome = outcomes[selection.scenario];
                metrics.trophies += selection.weight
                    * scoring::attacker_trophies(outcome.stars, outcome.destruction) as f64;
                metrics.three_star_rate +=
                    selection.weight * f64::from(u8::from(outcome.stars == 3));
                metrics.destruction += selection.weight * outcome.destruction;
                metrics.stars += selection.weight * outcome.stars as f64;
            }
            groups.push(metrics);
        }
        bases.push(BaseEstimate {
            target,
            metrics: average(&groups),
            standard_error: standard_error(&groups),
            groups,
        });
    }
    let mut weight = 0.0;
    let mut metrics = BattleMetrics::default();
    let mut variance = 0.0;
    for base in &bases {
        let w = manifest.targets[base.target].weight;
        weight += w;
        metrics.trophies += w * base.metrics.trophies;
        metrics.three_star_rate += w * base.metrics.three_star_rate;
        metrics.destruction += w * base.metrics.destruction;
        metrics.stars += w * base.metrics.stars;
        variance += w * w * base.standard_error * base.standard_error;
    }
    metrics.trophies /= weight;
    metrics.three_star_rate /= weight;
    metrics.destruction /= weight;
    metrics.stars /= weight;
    Ok(CandidateEstimate {
        stage,
        metrics,
        bases,
        battles: keys.len(),
        unused_budget: budget - keys.len(),
        standard_error: variance.sqrt() / weight,
    })
}

impl CandidateEstimate {
    pub fn to_json(&self) -> Json {
        object([
            ("stage", string(self.stage.name())),
            ("metrics", self.metrics.to_json()),
            ("battles", number(self.battles)),
            ("unused_budget", number(self.unused_budget)),
            ("standard_error", Json::Num(self.standard_error)),
            (
                "bases",
                Json::Arr(
                    self.bases
                        .iter()
                        .map(|base| {
                            object([
                                ("target", number(base.target)),
                                ("metrics", base.metrics.to_json()),
                                ("standard_error", Json::Num(base.standard_error)),
                                (
                                    "groups",
                                    Json::Arr(
                                        base.groups.iter().map(|group| group.to_json()).collect(),
                                    ),
                                ),
                            ])
                        })
                        .collect(),
                ),
            ),
        ])
    }

    pub fn from_json(value: &Json) -> Result<Self, String> {
        let stage = match value.at("stage").str() {
            "quick" => Stage::Quick,
            "confirm" => Stage::Confirm,
            "finalist" => Stage::Finalist,
            "holdout" => Stage::Holdout,
            _ => return Err("unknown checkpoint stage".to_owned()),
        };
        Ok(Self {
            stage,
            metrics: BattleMetrics::from_json(value.at("metrics")),
            battles: value.at("battles").usize(),
            unused_budget: value.at("unused_budget").usize(),
            standard_error: value.at("standard_error").f64(),
            bases: array(value, "bases")
                .iter()
                .map(|base| BaseEstimate {
                    target: base.at("target").usize(),
                    metrics: BattleMetrics::from_json(base.at("metrics")),
                    standard_error: base.at("standard_error").f64(),
                    groups: array(base, "groups")
                        .iter()
                        .map(BattleMetrics::from_json)
                        .collect(),
                })
                .collect(),
        })
    }
}

/// Paired groups, never individual side pairs, are the independent units.
/// This normal interval is diagnostic; report.rs also bootstraps whole groups.
pub fn paired_interval(
    manifest: &TargetManifest,
    first: &CandidateEstimate,
    second: &CandidateEstimate,
) -> (f64, f64) {
    let mut mean = 0.0;
    let mut variance = 0.0;
    let mut weight = 0.0;
    for base in &first.bases {
        let Some(other) = second
            .bases
            .iter()
            .find(|other| other.target == base.target)
        else {
            continue;
        };
        if base.groups.len() != other.groups.len() {
            continue;
        }
        let differences: Vec<BattleMetrics> = base
            .groups
            .iter()
            .zip(&other.groups)
            .map(|(a, b)| BattleMetrics {
                trophies: a.trophies - b.trophies,
                ..BattleMetrics::default()
            })
            .collect();
        let w = manifest.targets[base.target].weight;
        let error = standard_error(&differences);
        mean += w * average(&differences).trophies;
        variance += w * w * error * error;
        weight += w;
    }
    if weight == 0.0 {
        return (f64::NEG_INFINITY, f64::INFINITY);
    }
    let mean = mean / weight;
    let error = 1.96 * variance.sqrt() / weight;
    (mean - error, mean + error)
}
