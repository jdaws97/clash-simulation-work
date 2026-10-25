//! Winner identities/order are frozen before independent final data is read.
//! The report preserves failures and small-sample limitations explicitly.
use std::collections::BTreeMap;
use std::path::Path;

use crate::diagnostics;
use crate::eval::{self, Evaluator, Manifest, Row};
use crate::json::Json;
use crate::layout::{geometry, AdmittedLayout};
use crate::oracle::{self, OracleContext};
use crate::search::{Settings, State};
use crate::util::{encode, fingerprint, num, object, string, write};
use crate::Context;

pub fn distribution(rows: &[Row]) -> Json {
    let mut counts = BTreeMap::<&str, usize>::new();
    for row in rows {
        *counts.entry(&row.stratum).or_default() += 1;
    }
    let total: f64 = rows
        .iter()
        .map(|row| row.population_weight / counts[row.stratum.as_str()] as f64)
        .sum();
    let mut bins = BTreeMap::<String, f64>::new();
    for row in rows {
        let key = format!(
            "{} stars / {}-{}%",
            row.outcome.stars,
            (row.outcome.destruction as usize / 10 * 10).min(100),
            ((row.outcome.destruction as usize / 10 * 10) + 9).min(100)
        );
        *bins.entry(key).or_default() +=
            row.population_weight / counts[row.stratum.as_str()] as f64 / total;
    }
    Json::Obj(
        bins.into_iter()
            .map(|(key, weight)| (key, Json::Num(weight)))
            .collect(),
    )
}

/// Stratified paired bootstrap: complete committed groups are resampled
/// together, retaining declared population weights at every draw.
pub fn paired_bootstrap(a: &[Row], b: &[Row], mode: &str, seed: u64) -> Result<Json, String> {
    let other: BTreeMap<_, _> = b.iter().map(|row| (&row.group_id, row)).collect();
    let mut strata = BTreeMap::<String, Vec<(&Row, &Row)>>::new();
    for row in a {
        let paired = other
            .get(&row.group_id)
            .ok_or("missing paired final group")?;
        if paired.stratum != row.stratum || paired.population_weight != row.population_weight {
            return Err("paired population identity differs".to_owned());
        }
        strata
            .entry(row.stratum.clone())
            .or_default()
            .push((row, *paired));
    }
    let mean = eval::objective(a, mode, 0, Some(0.0))? - eval::objective(b, mode, 0, Some(0.0))?;
    if strata.values().any(|rows| rows.len() < 2) {
        return Ok(object([
            ("mean", Json::Num(mean)),
            ("interval", Json::Null),
            (
                "status",
                string("insufficient independent replication in a stratum"),
            ),
        ]));
    }
    let mut rng = crate::ProposalRng::new(seed);
    let mut draws = Vec::new();
    for _ in 0..512 {
        let mut child = Vec::new();
        let mut parent = Vec::new();
        for pairs in strata.values() {
            for _ in 0..pairs.len() {
                let (a, b) = pairs[rng.index(pairs.len())];
                child.push(a.clone());
                parent.push(b.clone());
            }
        }
        draws.push(
            eval::objective(&child, mode, 0, Some(0.0))?
                - eval::objective(&parent, mode, 0, Some(0.0))?,
        );
    }
    draws.sort_by(f64::total_cmp);
    Ok(object([
        ("mean", Json::Num(mean)), ("interval", Json::Arr(vec![Json::Num(draws[12]), Json::Num(draws[499])])),
        ("method", string("512 stratified complete-group paired bootstrap replicates; percentile 95%; uncalibrated model")),
    ]))
}

fn xml(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

pub fn svg(context: &Context, base: &AdmittedLayout) -> Result<String, String> {
    let mut output = String::from("<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"-1 -1 46 46\"><rect x=\"-1\" y=\"-1\" width=\"46\" height=\"46\" fill=\"#eef2df\"/>");
    for wall in &base.layout().walls {
        output.push_str(&format!(
            "<rect x=\"{}\" y=\"{}\" width=\"1\" height=\"1\" fill=\"#596164\"/>",
            wall.position.0, wall.position.1
        ));
    }
    for building in &base.layout().buildings {
        let size = crate::spatial::size(context, &building.key, false)
            .map_err(|error| format!("{error:?}"))?;
        let fill = if building.key == "th" {
            "#bd6b32"
        } else if crate::archive::is_defense(&building.key) {
            "#637ca3"
        } else {
            "#b1b397"
        };
        output.push_str(&format!("<g><title>{}</title><rect x=\"{}\" y=\"{}\" width=\"{size}\" height=\"{size}\" fill=\"{fill}\" stroke=\"#303740\" stroke-width=\".08\"/><text x=\"{}\" y=\"{}\" font-size=\".75\" text-anchor=\"middle\">{}</text></g>", xml(&building.id), building.position.0, building.position.1, building.position.0 as f64 + size as f64 / 2.0, building.position.1 as f64 + size as f64 / 2.0, xml(&building.key)));
    }
    for trap in &base.layout().traps {
        output.push_str(&format!(
            "<circle cx=\"{}\" cy=\"{}\" r=\".4\" fill=\"#c53859\"><title>{}: {}</title></circle>",
            trap.position.0 as f64 + 0.5,
            trap.position.1 as f64 + 0.5,
            xml(&trap.id),
            xml(&trap.key)
        ));
    }
    output.push_str("</svg>\n");
    Ok(output)
}

pub fn prepared_jobs(bases: &[&AdmittedLayout], rows: &[Vec<Row>]) -> Json {
    let mut plans = Vec::new();
    let mut jobs = Vec::new();
    for (layout, rows) in rows.iter().enumerate() {
        for row in rows {
            let plan = plans.len();
            plans.push(row.plan.clone());
            jobs.push(object([
                ("layout", num(layout)),
                ("plan", num(plan)),
                ("seed", Json::Num(row.scenario.seed as f64)),
                (
                    "town_hall",
                    Json::Num(bases[layout].layout().town_hall as f64),
                ),
                (
                    "modifier",
                    row.scenario.modifier.clone().map_or(Json::Null, string),
                ),
            ]));
        }
    }
    object([
        (
            "layouts",
            Json::Arr(bases.iter().map(|base| base.engine_json()).collect()),
        ),
        ("plans", Json::Arr(plans)),
        ("jobs", Json::Arr(jobs)),
    ])
}

pub fn finish(
    out: &Path,
    context: &Context,
    settings: &Settings,
    state: &State,
    evaluator: &mut Evaluator<'_>,
    gate: &Manifest,
    final_manifest: &Manifest,
    reference: &AdmittedLayout,
    oracle_context: &OracleContext<'_, '_>,
) -> Result<Json, String> {
    let development_identity = fingerprint(&state.to_json());
    let mut gate_results = Vec::new();
    for elite in state.archive.frontier().into_iter().take(3) {
        let rows = evaluator.assess(&elite.base, gate, state.attacks.version)?;
        let score = eval::objective(
            &rows,
            &settings.mode,
            elite.base.hole_tiles(),
            settings.hole_penalty,
        )?;
        gate_results.push((elite, rows, score));
    }
    gate_results.sort_by(|a, b| {
        b.2.total_cmp(&a.2).then(
            a.0.base
                .physical_identity()
                .cmp(b.0.base.physical_identity()),
        )
    });
    let (winner, _, _) = gate_results.first().ok_or("no confirmed finalist")?;
    let frozen = object([
        ("winner", string(winner.base.physical_identity())),
        (
            "ordered_finalists",
            Json::Arr(
                gate_results
                    .iter()
                    .map(|(elite, _, _)| string(elite.base.physical_identity()))
                    .collect(),
            ),
        ),
        (
            "gate_results",
            Json::Arr(
                gate_results
                    .iter()
                    .map(|(elite, rows, score)| {
                        object([
                            ("layout", string(elite.base.physical_identity())),
                            ("objective", Json::Num(*score)),
                            ("rows", Json::Arr(rows.iter().map(Row::to_json).collect())),
                        ])
                    })
                    .collect(),
            ),
        ),
        ("attack_archive", state.attacks.to_json()),
        (
            "thresholds",
            object([
                ("recommended_gate_groups", num(400)),
                ("recommended_archive_replicates", num(100)),
                ("minimum_archive_paired_difference", Json::Num(0.0)),
            ]),
        ),
        ("development_identity", string(&development_identity)),
    ]);
    crate::checkpoint::atomic_write(
        &out.join("frozen-finalists.json"),
        format!("{}\n", encode(&frozen)).as_bytes(),
    )?;
    // No final outcomes have been read before the frozen artifact exists.
    let final_rows = evaluator.assess(&winner.base, final_manifest, state.attacks.version)?;
    let reference_rows = evaluator.assess(reference, final_manifest, state.attacks.version)?;
    let paired = paired_bootstrap(
        &final_rows,
        &reference_rows,
        &settings.mode,
        settings.seed ^ 0x66696e616c,
    )?;
    let selected = diagnostics::representative(&final_rows);
    let diagnostic_rows: Vec<_> = selected
        .iter()
        .map(|&index| final_rows[index].clone())
        .collect();
    let diagnosis = diagnostics::collect(
        context,
        &winner.base,
        &diagnostic_rows,
        &evaluator.identity.clone(),
        evaluator,
    )?;
    write(&out.join("diagnostics.json"), &diagnosis.to_json())?;
    let mut attack_final = Vec::new();
    for entry in state.attacks.entries.values().filter(|entry| entry.active) {
        let mut rows = Vec::new();
        let mut refs = Vec::new();
        for replicate in 0..settings.archive_groups {
            let seed = (4 << 44)
                + replicate as i64
                + final_manifest.groups[0].scenarios[0]
                    .group
                    .rem_euclid(1 << 40);
            let group = oracle::group_for(
                oracle_context,
                &entry.genome,
                "archive-final-frozen",
                seed,
                1.0,
                settings.modifier.clone(),
            )?;
            rows.push(evaluator.evaluate(&winner.base, &group, state.attacks.version)?);
            refs.push(evaluator.evaluate(reference, &group, state.attacks.version)?);
        }
        attack_final.push(object([
            ("attack", string(&entry.id)),
            ("winner", eval::summarise(&rows)?.to_json()),
            ("reference", eval::summarise(&refs)?.to_json()),
            (
                "paired",
                paired_bootstrap(&rows, &refs, &settings.mode, settings.seed)?,
            ),
            ("rows", Json::Arr(rows.iter().map(Row::to_json).collect())),
        ]));
    }
    let base_ids: Vec<_> = state
        .archive
        .cells
        .values()
        .map(|elite| elite.base.physical_identity().to_owned())
        .collect();
    let (attack_ids, matrix) = state.attacks.matrix(&base_ids, &settings.mode)?;
    let game = if attack_ids.is_empty() {
        Json::Null
    } else {
        crate::psro::solve(&matrix, 4096)?.to_json()
    };
    let sizes: Vec<_> = context
        .catalog
        .building_types
        .iter()
        .map(|(key, building)| (key.clone(), building.size))
        .collect();
    let holes = geometry::holes(&geometry::blocked(winner.base.layout(), &sizes), 44, 3);
    let identity_unchanged = development_identity == fingerprint(&state.to_json());
    if !identity_unchanged {
        return Err("final evaluation changed development selection".to_owned());
    }
    let receipt = object([
        ("schema", num(1)), ("executable_input_identity", string(&evaluator.identity)),
        ("frozen_identity", string(fingerprint(&frozen))), ("winner", string(winner.base.physical_identity())),
        ("admission_verified", Json::Bool(true)), ("replay_outcomes_verified", num(diagnostic_rows.len())),
        ("development_unchanged", Json::Bool(identity_unchanged)),
        ("paired_group_identity_verified", num(final_rows.len())),
        ("scope", string("runtime winner/report gates; independent regression proof receipt is proof-completion.json")),
    ]);
    write(&out.join("winner-proof.json"), &receipt)?;
    write(&out.join("winner.json"), &winner.base.engine_json())?;
    std::fs::write(out.join("winner.svg"), svg(context, &winner.base)?)
        .map_err(|error| error.to_string())?;
    write(
        &out.join("prepared-jobs.json"),
        &prepared_jobs(
            &[&winner.base, reference],
            &[final_rows.clone(), reference_rows.clone()],
        ),
    )?;
    let summary = eval::summarise(&final_rows)?;
    let th_survival = (1.0 - summary.th_kill_rate).clamp(0.0, 1.0);
    let robustness_pass = !attack_final.is_empty()
        && attack_final.iter().all(|attack| {
            attack.at("paired").get("interval").is_some_and(|interval| {
            matches!(interval, Json::Arr(values) if values.len() == 2 && values[0].f64() >= 0.0)
        })
        });
    let robustness_gate = object([
        ("status", string(if settings.archive_groups < 100 { "insufficient-replication" } else if robustness_pass { "passed" } else { "failed" })),
        ("minimum_paired_difference", Json::Num(0.0)),
        ("replicates_per_attack", num(settings.archive_groups)),
        ("recommended_replicates", num(100)),
        ("scope", string("fresh frozen discovered attacks relative to reference; ordinary prevalence is separate")),
    ]);
    let family_names: std::collections::BTreeSet<_> =
        final_rows.iter().map(|row| row.stratum.clone()).collect();
    let family_breakdown = family_names
        .into_iter()
        .map(|family| {
            let rows: Vec<_> = final_rows
                .iter()
                .filter(|row| row.stratum == family)
                .cloned()
                .collect();
            Ok(object([
                ("family_and_program", string(family)),
                ("attacker_th", Json::Num(rows[0].scenario.town_hall as f64)),
                ("summary", eval::summarise(&rows)?.to_json()),
            ]))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let mut errors = Vec::new();
    if gate.groups.len() < 400 {
        errors.push(string(
            "finalist gate has fewer than 400 groups; smoke/development result only",
        ));
    }
    if state.attacks.entries.is_empty() {
        errors.push(string("no discovered attacks; robustness gate incomplete"));
    }
    if settings.archive_groups < 100 {
        errors.push(string("archive attacks have fewer than 100 fresh replicates; robustness gate has insufficient replication"));
    }
    let hole_map = holes
        .iter()
        .map(|region| {
            Json::Arr(
                region
                    .iter()
                    .map(|&(x, y)| Json::Arr(vec![Json::Num(x as f64), Json::Num(y as f64)]))
                    .collect(),
            )
        })
        .collect();
    let penalized_objective = eval::objective(
        &final_rows,
        &settings.mode,
        winner.base.hole_tiles(),
        settings.hole_penalty,
    )?;
    let penalty_per_tile = settings
        .hole_penalty
        .unwrap_or(if settings.mode == "ranked" { 0.25 } else { 0.8 });
    let population_weights = final_manifest
        .strata()
        .into_iter()
        .map(|(key, weight)| (key, Json::Num(weight)))
        .collect();
    let restricted_game = object([
        ("bases", Json::Arr(base_ids.iter().map(string).collect())),
        (
            "attacks",
            Json::Arr(attack_ids.iter().map(string).collect()),
        ),
        (
            "payoffs",
            Json::Arr(
                matrix
                    .iter()
                    .map(|row| Json::Arr(row.iter().copied().map(Json::Num).collect()))
                    .collect(),
            ),
        ),
        ("solution", game),
    ]);
    let representative_traces = selected
        .iter()
        .enumerate()
        .map(|(position, index)| {
            object([
                (
                    "label",
                    string(if position == 0 {
                        "weighted-median"
                    } else {
                        "failure-tail"
                    }),
                ),
                ("group", string(&final_rows[*index].group_id)),
            ])
        })
        .collect();
    let status = if errors.is_empty() {
        "complete-model-report"
    } else {
        "limited-model-report"
    };
    let report = object([
        ("schema", num(1)),
        ("status", string(status)),
        ("evidence", string("declared synthetic layouts and model simulations; not real-game calibration")),
        ("winner", winner.base.receipt()),
        ("levels_modes_facings_cc_heroes_guardian", winner.base.engine_json()),
        ("hole_map", Json::Arr(hole_map)),
        ("ordinary_meta", summary.to_json()),
        ("ordinary_final_rows", Json::Arr(final_rows.iter().map(Row::to_json).collect())),
        ("reference_final_rows", Json::Arr(reference_rows.iter().map(Row::to_json).collect())),
        ("family_attacker_th_breakdown", Json::Arr(family_breakdown)),
        ("final_manifest_identity", string(fingerprint(&final_manifest.to_json()))),
        ("penalized_objective", Json::Num(penalized_objective)),
        ("deterministic_hole_penalty", Json::Num(winner.base.hole_tiles() as f64 * penalty_per_tile)),
        ("population_weights", Json::Obj(population_weights)),
        ("policy", string("visible; two sampled sides, three hidden priors, frozen skill quantiles; uncalibrated strength=1")),
        ("mode", string(&settings.mode)),
        ("modifier", settings.modifier.clone().map_or(Json::Null, string)),
        ("paired_difference_from_reference", paired),
        ("star_destruction_distribution", distribution(&final_rows)),
        ("TH_survival", Json::Num(th_survival)),
        ("discovered_attacks", Json::Arr(attack_final)),
        ("robustness_gate", robustness_gate),
        ("restricted_game", restricted_game),
        ("budget", evaluator.budget.to_json()),
        ("descriptors", winner.descriptor.to_json()),
        ("representative_traces", Json::Arr(representative_traces)),
        ("trap_polish_and_interventions", Json::Arr(state.polish_log.clone())),
        ("proof", receipt),
        ("input_identity", string(&evaluator.identity)),
        ("mechanic_sensitivities", string("v29 model; uniform hidden prior and stat-based execution skill; damage totals are descriptive")),
        ("incomplete_sections", Json::Arr(errors)),
    ]);
    write(&out.join("report.json"), &report)?;
    let markdown = format!(
        concat!(
        "# Synthetic TH{} base-search winner\n\n",
        "Winner `{}` was frozen before final evaluation. ",
        "Evidence is model/synthetic correctness, not real-game calibration.\n\n",
        "Ordinary defender trophies: {:.4}. Penalized {} objective: {:.4}. TH survival: {:.3}.\n\n",
        "{} independent final groups; {} discovered attacks. ",
        "Physical battles: {} planning + {} execution + {} diagnostic.\n\n",
        "Paired comparison: `{}`.\n\n",
        "See winner.svg, diagnostics.json, prepared-jobs.json, winner-proof.json and report.json ",
        "for legality, levels, population weights, replay identity, attribution, interventions, ",
        "archive attacks and restricted-game residual.\n\nLimitations: {}\n",
    ),
        settings.town_hall,
        winner.base.physical_identity(),
        summary.ranked_trophies,
        settings.mode,
        report.at("penalized_objective").f64(),
        th_survival,
        final_rows.len(),
        state.attacks.entries.len(),
        evaluator.budget.planning,
        evaluator.budget.execution,
        evaluator.budget.diagnostics,
        encode(report.at("paired_difference_from_reference")),
        encode(report.at("incomplete_sections"))
    );
    std::fs::write(out.join("report.md"), markdown).map_err(|error| error.to_string())?;
    Ok(report)
}
