//! Checkpoints contain complete raw development results and cache entries.
//! Writes use pending/fsync/backup/rename; inputs and payload are validated.
use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;
use std::path::Path;

use crate::archive::{Archive, Elite};
use crate::eval::{Budget, Evaluator, Row};
use crate::json::Json;
use crate::layout::{admit, AdmissionPolicy, Layout};
use crate::oracle::AttackArchive;
use crate::search::{Settings, State};
use crate::util::{encode, fingerprint, num, object, read, string, u64_string, usize_field};
use crate::{Context, ProposalRng};

pub const SCHEMA: usize = 3;

pub fn save(
    path: &Path,
    identity: &str,
    state: &State,
    evaluator: &Evaluator<'_>,
) -> Result<(), String> {
    let payload = object([
        ("state", state.to_json()),
        ("budget", evaluator.budget.to_json()),
        (
            "cache",
            Json::Obj(
                evaluator
                    .cache
                    .iter()
                    .map(|(key, row)| (key.clone(), row.to_json()))
                    .collect(),
            ),
        ),
    ]);
    let envelope = object([
        ("schema", num(SCHEMA)),
        ("identity", string(identity)),
        ("payload_identity", string(fingerprint(&payload))),
        ("payload", payload),
    ]);
    atomic_write(path, format!("{}\n", encode(&envelope)).as_bytes())
}

pub fn atomic_write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let pending = path.with_extension("json.pending");
    let backup = path.with_extension("json.bak");
    let mut file = std::fs::File::create(&pending).map_err(|error| error.to_string())?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|error| error.to_string())?;
    drop(file);
    if path.exists() {
        if backup.exists() {
            std::fs::remove_file(&backup).map_err(|error| error.to_string())?;
        }
        std::fs::rename(path, &backup).map_err(|error| error.to_string())?;
    }
    std::fs::rename(&pending, path).map_err(|error| error.to_string())?;
    #[cfg(unix)]
    std::fs::File::open(path.parent().unwrap_or(Path::new(".")))
        .and_then(|directory| directory.sync_all())
        .map_err(|error| error.to_string())?;
    Ok(())
}

fn decode_elite(
    value: &Json,
    context: &Context,
    settings: &Settings,
    policy: &AdmissionPolicy,
) -> Result<Elite, String> {
    let layout = Layout::from_json(value.at("layout")).map_err(|error| encode(&error.to_json()))?;
    let base = admit(layout, &context.rules, context.catalog.clone(), policy)
        .map_err(|error| encode(&error.to_json()))?;
    if base.receipt() != *value.at("admission") {
        return Err("checkpoint admission receipt differs".to_owned());
    }
    let descriptor = settings.descriptors.describe(context, &base)?;
    if descriptor.to_json() != *value.at("descriptor") {
        return Err("checkpoint descriptor differs".to_owned());
    }
    let confirmation = value
        .at("confirmation")
        .arr()
        .iter()
        .map(Row::from_json)
        .collect::<Vec<_>>();
    let objective = crate::eval::objective(
        &confirmation,
        &settings.mode,
        base.hole_tiles(),
        settings.hole_penalty,
    )?;
    if objective.to_bits() != value.at("objective").f64().to_bits() {
        return Err("checkpoint objective differs".to_owned());
    }
    Ok(Elite {
        base,
        descriptor,
        lineage: value.at("lineage").clone(),
        screen: value
            .at("screen")
            .arr()
            .iter()
            .map(Row::from_json)
            .collect(),
        confirmation,
        objective,
        robustness: value.at("robustness").f64(),
        archive_version: value.at("archive_version").usize(),
    })
}

pub fn resume(
    path: &Path,
    identity: &str,
    context: &Context,
    settings: &Settings,
    policy: &AdmissionPolicy,
) -> Result<(State, Budget, BTreeMap<String, Row>), String> {
    let backup = path.with_extension("json.bak");
    let path = if path.exists() { path } else { &backup };
    // The JSON reader is shared with trusted prepared inputs. Convert malformed
    // checkpoint shape panics into an explicit error at this untrusted boundary.
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let envelope = read(path)?;
        if usize_field(&envelope, "schema")? != SCHEMA
            || envelope.at("identity").opt_str() != Some(identity)
        {
            return Err("checkpoint schema or executable/input identities differ".to_owned());
        }
        let payload = envelope.at("payload");
        if envelope.at("payload_identity").str() != fingerprint(payload) {
            return Err("checkpoint payload checksum differs".to_owned());
        }
        let value = payload.at("state");
        let mut state = State::new(0);
        state.rng = ProposalRng::new(u64_string(value, "rng")?);
        state.completed_waves = usize_field(value, "completed_waves")?;
        state.candidate_cursor = usize_field(value, "candidate_cursor")?;
        state.race_looks = usize_field(value, "race_looks")?;
        state.race_eliminated = usize_field(value, "race_eliminated")?;
        state.polished = value.at("polished").bool();
        state.polish_log = value.at("polish_log").arr().to_vec();
        state.annealing_temperature = value.at("annealing_temperature").f64();
        state.seen = value
            .at("seen")
            .arr()
            .iter()
            .map(|value| value.str().to_owned())
            .collect::<BTreeSet<_>>();
        state.rejected = value
            .at("rejected")
            .obj()
            .iter()
            .map(|(key, count)| (key.clone(), count.usize()))
            .collect();
        state.attacks = AttackArchive::from_json(value.at("attacks"))?;
        state.archive = Archive::default();
        for value in value.at("archive").at("cells").arr() {
            let elite = decode_elite(value, context, settings, policy)?;
            if elite.archive_version != state.attacks.version {
                return Err("checkpoint contains stale attack scores".to_owned());
            }
            if state
                .archive
                .cells
                .insert(elite.descriptor.cell, elite)
                .is_some()
            {
                return Err("duplicate archive cell".to_owned());
            }
        }
        state.archive.pareto = value
            .at("archive")
            .at("pareto")
            .arr()
            .iter()
            .map(|value| decode_elite(value, context, settings, policy))
            .collect::<Result<_, _>>()?;
        let budget = Budget::from_json(payload.at("budget"))?;
        budget.reserve(0)?;
        let cache = payload
            .at("cache")
            .obj()
            .iter()
            .map(|(key, value)| (key.clone(), Row::from_json(value)))
            .collect();
        Ok((state, budget, cache))
    }))
    .map_err(|_| "malformed checkpoint".to_owned())?
}
