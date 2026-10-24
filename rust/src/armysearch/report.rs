//! Resumable development state and independent final reports.
//! uncertainty.py:93: resample complete scouting groups, retaining pairing.

use std::path::Path;

use crate::json::Json;

use super::account::AccountRules;
use super::genome::ArmyGenome;
use super::score::{CandidateEstimate, TargetManifest};
use super::search::{Elite, Objective, SearchState};
use super::util::{encode, hash, number, object, read, string, text, write, Random};

pub const CHECKPOINT_VERSION: usize = 2;

/// Write an adjacent temporary file and retain the previous complete snapshot.
/// On Windows rename cannot replace an existing file, so resume accepts .bak.
pub fn checkpoint(path: &Path, identity: &str, state: &SearchState) -> Result<(), String> {
    let value = object([
        ("version", number(CHECKPOINT_VERSION)),
        ("input_identity", string(identity)),
        ("development", state.to_json()),
    ]);
    let pending = path.with_extension("json.pending");
    let backup = path.with_extension("json.bak");
    write(&pending, &value)?;
    std::fs::OpenOptions::new().write(true).open(&pending).and_then(|file| file.sync_all())
        .map_err(|error| error.to_string())?;
    if path.exists() {
        if backup.exists() {
            std::fs::remove_file(&backup).map_err(|error| error.to_string())?;
        }
        std::fs::rename(path, &backup).map_err(|error| error.to_string())?;
    }
    std::fs::rename(&pending, path).map_err(|error| error.to_string())
}

pub fn resume(
    path: &Path,
    identity: &str,
    objective: Objective,
    account: &AccountRules,
) -> Result<SearchState, String> {
    let backup = path.with_extension("json.bak");
    let path = if path.exists() {
        path
    } else {
        &backup
    };
    let value = read(path)?;
    if value.at("version").usize() != CHECKPOINT_VERSION || text(&value, "input_identity", "") != identity {
        return Err("checkpoint version or inputs differ (account, catalog, targets, compiler, seed, batch, budgets, objective, immigrant fractions, families)".to_owned());
    }
    SearchState::from_json(value.at("development"), objective, account)
}

pub fn input_identity(
    root: &Path,
    catalog: &Path,
    settings: &Json,
    manifest: &TargetManifest,
) -> Result<String, String> {
    let mut paths = vec![catalog.to_owned(), std::env::current_exe().map_err(|error| error.to_string())?];
    for directory in [root.join("rust/src"), root.join("data")] {
        collect(&directory, &mut paths, directory.ends_with("src"))?;
    }
    paths.sort();
    paths.dedup();
    let mut signatures = Vec::new();
    for path in paths {
        let content = std::fs::read(&path).map_err(|error| format!("{}: {error}", path.display()))?;
        signatures.push(object([
            ("path", string(path.strip_prefix(root).unwrap_or(&path).to_string_lossy())),
            ("bytes", number(content.len())),
            ("hash", string(format!("{:016x}", hash(&content)))),
        ]));
    }
    // Include complete layouts: target paths may be outside the repository.
    Ok(encode(&object([
        ("settings", settings.clone()),
        ("files", Json::Arr(signatures)),
        ("manifest", manifest.to_json()),
        ("layouts", Json::Arr(manifest.targets.iter().map(|target| target.layout.clone()).collect())),
        ("environment", Json::Arr(["BASELAB_GAPS", "BASELAB_PACE"].iter().map(|key| object([
            ("name", string(*key)),
            ("value", std::env::var(key).map_or(Json::Null, string)),
        ])).collect())),
    ])))
}

fn collect(
    directory: &Path,
    paths: &mut Vec<std::path::PathBuf>,
    recursive: bool,
) -> Result<(), String> {
    for entry in std::fs::read_dir(directory).map_err(|error| error.to_string())? {
        let path = entry.map_err(|error| error.to_string())?.path();
        if path.is_dir() && recursive {
            collect(&path, paths, true)?;
        }
        if path.is_file() && matches!(path.extension().and_then(|value| value
            .to_str()), Some("json" | "rs")) {
            paths.push(path);
        }
    }
    Ok(())
}

pub fn frozen_selection(path: &Path, elites: &[Elite]) -> Result<(), String> {
    write(path, &object([
        ("selection_source", string("confirmation on search split only; order frozen before holdout")),
        ("armies", Json::Arr(elites.iter().map(|elite| elite.genome.to_json()).collect())),
    ]))
}

fn uncertainty(manifest: &TargetManifest, estimate: &CandidateEstimate, seed: u64) -> Json {
    let mut rng = Random(seed);
    let mut bootstrap = Vec::new();
    for _ in 0..512 {
        let mut total = 0.0;
        let mut weight = 0.0;
        for base in &estimate.bases {
            let w = manifest.targets[base.target].weight;
            let mut mean = 0.0;
            for _ in &base.groups {
                mean += base.groups[rng.index(base.groups.len())].trophies;
            }
            total += w * (mean / base.groups.len() as f64);
            weight += w;
        }
        bootstrap.push(total / weight);
    }
    bootstrap.sort_by(f64::total_cmp);
    let insufficient = estimate.bases.iter().any(|base| base.groups.len() < 2);
    let mut cluster_bootstrap = Vec::new();
    let mut sparse_strata = Vec::new();
    for th in 16..=18 {
        let count = estimate.bases.iter().filter(|base| manifest.targets[base.target].town_hall == th).count();
        if count == 1 {
            sparse_strata.push(Json::Num(th as f64));
        }
    }
    for _ in 0..512 {
        let mut total = 0.0;
        let mut total_weight = 0.0;
        for th in 16..=18 {
            let stratum: Vec<_> = estimate.bases.iter().filter(|base| manifest.targets[base.target].town_hall == th).collect();
            if stratum.is_empty() {
                continue;
            }
            let stratum_weight: f64 = stratum.iter().map(|base| manifest.targets[base.target].weight).sum();
            let mut sampled_weight = 0.0;
            let mut sampled_total = 0.0;
            for _ in &stratum {
                let base = stratum[rng.index(stratum.len())];
                let weight = manifest.targets[base.target].weight;
                let mut mean = 0.0;
                for _ in &base.groups {
                    mean += base.groups[rng.index(base.groups.len())].trophies;
                }
                sampled_total += weight * (mean / base.groups.len() as f64);
                sampled_weight += weight;
            }
            total += stratum_weight * (sampled_total / sampled_weight);
            total_weight += stratum_weight;
        }
        cluster_bootstrap.push(total / total_weight);
    }
    cluster_bootstrap.sort_by(f64::total_cmp);
    object([
        ("seed_group_standard_error", Json::Num(estimate.standard_error)),
        ("seed_group_bootstrap_95", if insufficient {
            Json::Null
        } else {
            Json::Arr(vec![Json::Num(bootstrap[12]), Json::Num(bootstrap[499])])
        }),
        ("replicates", number(512)),
        ("insufficient_seed_replicates", Json::Bool(insufficient)),
        ("scope", string("seed uncertainty on this fixed target bank; whole scouting groups resampled; not real-game calibration")),
        ("base_sampling_uncertainty", object([
            ("stratified_base_and_seed_bootstrap_95", Json::Arr(vec![
                Json::Num(cluster_bootstrap[12]),
                Json::Num(cluster_bootstrap[499]),
            ])),
            ("single_base_th_strata", Json::Arr(sparse_strata)),
            ("scope", string("TH mixture fixed; base clusters resampled within TH, then whole seed groups; a one-base stratum cannot estimate base variation")),
        ])),
        ("layout_assumptions", Json::Arr(estimate.bases.iter().map(|base| string(&manifest.targets[base.target].provenance)).collect())),
    ])
}

pub fn stage_report(manifest: &TargetManifest, estimate: &CandidateEstimate, seed: u64) -> Json {
    let mut result = estimate.to_json();
    let per_base = estimate.bases.iter().map(|base| {
        let target = &manifest.targets[base.target];
        object([
            ("base", string(&target.id)),
            ("split", string(target.split.name())),
            ("town_hall", Json::Num(target.town_hall as f64)),
            ("weight", Json::Num(target.weight)),
            ("provenance", string(&target.provenance)),
            ("lineage", string(&target.lineage)),
            ("metrics", base.metrics.to_json()),
            ("groups", number(base.groups.len())),
            ("seed_group_standard_error", Json::Num(base.standard_error)),
        ])
    }).collect();
    crate::armies::put(&mut result, "per_base", Json::Arr(per_base));
    let mut th_rows = Vec::new();
    for th in 16..=18 {
        let bases: Vec<_> = estimate.bases.iter().filter(|base| manifest.targets[base.target].town_hall == th).collect();
        if bases.is_empty() {
            continue;
        }
        let mut weight = 0.0;
        let mut trophies = 0.0;
        let mut three = 0.0;
        let mut destruction = 0.0;
        for base in bases {
            let w = manifest.targets[base.target].weight;
            weight += w;
            trophies += w * base.metrics.trophies;
            three += w * base.metrics.three_star_rate;
            destruction += w * base.metrics.destruction;
        }
        th_rows.push(object([
            ("town_hall", Json::Num(th as f64)),
            ("attacker_trophies", Json::Num(trophies / weight)),
            ("three_star_rate", Json::Num(three / weight)),
            ("destruction", Json::Num(destruction / weight)),
        ]));
    }
    crate::armies::put(&mut result, "per_town_hall", Json::Arr(th_rows));
    crate::armies::put(&mut result, "uncertainty", uncertainty(manifest, estimate, seed));
    let mut tail = Vec::new();
    for base in &estimate.bases {
        let weight = manifest.targets[base.target].weight / base.groups.len() as f64;
        for group in &base.groups {
            tail.push((group.trophies, weight));
        }
    }
    tail.sort_by(|a, b| a.0.total_cmp(&b.0));
    let weight: f64 = tail.iter().map(|(_, weight)| weight).sum();
    let mut cumulative = 0.0;
    for (trophies, sample_weight) in tail {
        cumulative += sample_weight;
        if cumulative >= weight * 0.1 {
            crate::armies::put(&mut result, "weighted_seed_group_trophies_p10", Json::Num(trophies));
            break;
        }
    }
    result
}

pub fn army_report(
    path: &Path,
    rank: usize,
    elite: &Elite,
    holdout: &CandidateEstimate,
    manifest: &TargetManifest,
    plan: Json,
    housing: Json,
    replay: Json,
    seed: u64,
    account: &AccountRules,
    novelty: Json,
) -> Result<(), String> {
    write(path, &object([
        ("rank_before_holdout", number(rank)),
        ("archive_cell", string(elite.genome.cell(account))),
        ("novelty", novelty),
        ("genome", elite.genome.to_json()),
        ("identity", string(elite.genome.identity())),
        ("strength", Json::Num(1.0)),
        ("housing", housing),
        ("compiled_plan", plan),
        ("quick", stage_report(manifest, &elite.quick, seed)),
        ("confirmation", stage_report(manifest, &elite.confirm, seed ^ 1)),
        ("holdout", stage_report(manifest, holdout, seed ^ 2)),
        ("median_battle", replay),
        ("holdout_policy", string("frozen army and general plan; fresh disjoint seed domain and offset sides; results never update archive or order")),
    ]))
}

pub fn validate_resumed(
    state: &SearchState,
    validate: impl Fn(&ArmyGenome) -> Result<(), String>,
) -> Result<(), String> {
    for elite in state.archive.values().flatten() {
        validate(&elite.genome)?;
        if elite.quick.stage != super::score::Stage::Quick || elite.confirm.stage != super::score::Stage::Confirm {
            return Err("checkpoint archive contains a nondevelopment score".to_owned());
        }
    }
    Ok(())
}

pub fn archive_json(state: &SearchState) -> Json {
    object([
        ("cell_capacity", number(super::search::CELL_CAPACITY)),
        ("cells", Json::Obj(state.archive.iter().map(|(cell, elites)| (cell
            .clone(), Json::Arr(elites.iter().map(Elite::to_json).collect()))).collect())),
        ("completed_batches", number(state.completed_batches)),
        ("assessments", number(state.assessments)),
        ("logical_battles", number(state.logical_battles)),
        ("raced_out", number(state.raced_out)),
    ])
}

pub fn roundtrip_state(
    state: &SearchState,
    objective: Objective,
    account: &AccountRules,
) -> Result<SearchState, String> {
    let value = crate::json::parse(&encode(&state.to_json())).map_err(|error| error.to_string())?;
    let restored = SearchState::from_json(&value, objective, account)?;
    if encode(&state.to_json()) != encode(&restored.to_json()) {
        return Err("checkpoint roundtrip changed search state".to_owned());
    }
    Ok(restored)
}
