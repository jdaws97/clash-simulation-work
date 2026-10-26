use crate::citations::{self, Transcripts};
use crate::{io, schema};
use clash_data::json::Json;
use clash_data::wire::{self, list, obj, put, string, text};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

pub fn source_ids(playbook: &Json) -> BTreeSet<String> {
    list(playbook, "sources")
        .iter()
        .map(|source| match source {
            Json::Str(video) => video.clone(),
            _ => citations::source_id(source),
        })
        .collect()
}

pub fn good_cites(
    item: &Json,
    transcripts: &mut Transcripts,
    sources: Option<&BTreeSet<String>>,
    located: bool,
) -> Result<Vec<Json>, String> {
    let mut good = Vec::new();
    for cite in list(item, "cite") {
        if sources.is_some_and(|sources| {
            !sources.is_empty() && !sources.contains(&citations::source_id(cite))
        }) {
            continue;
        }
        if let Some(time) = transcripts.verify(cite)? {
            let mut cite = cite.clone();
            if located {
                put(&mut cite, "verified_t", Json::Num(time));
            }
            good.push(cite);
        }
    }
    Ok(good)
}

/// Compatibility mode reproduces the saved checker, including its weaker
/// dangling-after diagnostic. Normal writes additionally enforce the executor
/// schema, full dependencies and family-source membership.
pub fn consolidate(
    reply: &str,
    transcripts: &mut Transcripts,
    legacy: bool,
) -> Result<Json, String> {
    let mut playbook = citations::parse_reply(reply).ok_or("no parseable playbook")?;
    let sources = source_ids(&playbook);
    let mut kept = Vec::new();
    let mut reasons = BTreeMap::<String, usize>::new();
    for step in list(&playbook, "steps") {
        let cites = good_cites(step, transcripts, (!legacy).then_some(&sources), false)?;
        let reason = if cites.is_empty() {
            Some("no verified citation".to_owned())
        } else if legacy {
            schema::legacy_step_reason(step)
        } else {
            schema::step_references(step).err()
        };
        if let Some(reason) = reason {
            *reasons.entry(reason).or_default() += 1;
        } else {
            let mut step = step.clone();
            put(&mut step, "cite", Json::Arr(cites));
            kept.push(step);
        }
    }
    let ids: BTreeSet<_> = kept.iter().map(|s| text(s, "id", "")).collect();
    let mut dangling = Vec::new();
    for step in &kept {
        let refs = after_refs(step.get("when"));
        if !refs.is_empty() && !refs.iter().any(|id| ids.contains(id.as_str())) {
            dangling.push(string(text(step, "id", "")));
        }
    }
    let dropped: usize = reasons.values().sum();
    let check = obj([
        ("steps_kept", wire::num(kept.len() as f64)),
        ("steps_dropped", wire::num(dropped as f64)),
        ("reasons", wire::count_map(&reasons)),
        ("dangling_after", Json::Arr(dangling)),
    ]);
    put(&mut playbook, "steps", Json::Arr(kept));
    let mut reading = Vec::new();
    for item in list(&playbook, "base_reading") {
        if !good_cites(item, transcripts, (!legacy).then_some(&sources), false)?.is_empty() {
            // Frozen checker retains all cites on a supported base-reading item.
            // Strict output strips the rejected cites as it does for steps.
            let mut item = item.clone();
            if !legacy {
                let cites = good_cites(&item, transcripts, Some(&sources), false)?;
                put(&mut item, "cite", Json::Arr(cites));
            }
            reading.push(item);
        }
    }
    put(&mut playbook, "base_reading", Json::Arr(reading));
    put(&mut playbook, "check", check);
    if !legacy {
        strip_cites(&mut playbook, transcripts, &sources)?;
        let inspection = inspect_internal(&playbook, transcripts, false, true)?;
        let errors = list(&inspection, "errors")
            .iter()
            .map(|error| error.str())
            .collect::<Vec<_>>();
        if !errors.is_empty() {
            return Err(errors.join("; "));
        }
    }
    Ok(playbook)
}

fn after_refs(value: Option<&Json>) -> Vec<String> {
    let mut refs = Vec::new();
    if let Some(Json::Obj(fields)) = value {
        for (key, value) in fields {
            if key == "after" {
                if let Json::Str(id) = value {
                    refs.push(id.clone());
                }
            } else if let Json::Arr(parts) = value {
                for part in parts {
                    refs.extend(after_refs(Some(part)));
                }
            }
        }
    }
    refs
}

pub fn inspect(playbook: &Json, transcripts: &mut Transcripts) -> Result<Json, String> {
    inspect_internal(playbook, transcripts, true, true)
}

pub fn inspect_legacy(playbook: &Json, transcripts: &mut Transcripts) -> Result<Json, String> {
    inspect_internal(playbook, transcripts, true, false)
}

fn strip_cites(
    value: &mut Json,
    transcripts: &mut Transcripts,
    sources: &BTreeSet<String>,
) -> Result<(), String> {
    match value {
        Json::Obj(fields) => {
            for (key, child) in fields {
                if key == "cite" || key == "aim_cite" {
                    if let Json::Arr(cites) = child {
                        let mut good = Vec::new();
                        for cite in cites.iter() {
                            if (sources.is_empty() || sources.contains(&citations::source_id(cite)))
                                && transcripts.verify(cite)?.is_some()
                            {
                                good.push(cite.clone());
                            }
                        }
                        *cites = good;
                    }
                } else {
                    strip_cites(child, transcripts, sources)?;
                }
            }
        }
        Json::Arr(values) => {
            for child in values {
                strip_cites(child, transcripts, sources)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn cited_items<'a>(value: &'a Json, path: &str, result: &mut Vec<(String, &'a Json)>) {
    match value {
        Json::Obj(fields) => {
            if value.get("cite").is_some()
                || value.get("aim_cite").is_some()
                || value.get("action").is_some()
                || value.get("rule").is_some()
            {
                result.push((path.to_owned(), value));
            }
            for (key, child) in fields {
                if key != "cite" && key != "aim_cite" {
                    cited_items(child, &format!("{path}.{key}"), result);
                }
            }
        }
        Json::Arr(values) => {
            for (index, child) in values.iter().enumerate() {
                cited_items(child, &format!("{path}[{index}]"), result);
            }
        }
        _ => {}
    }
}

fn inspect_internal(
    playbook: &Json,
    transcripts: &mut Transcripts,
    allow_learned: bool,
    expanded: bool,
) -> Result<Json, String> {
    let mut errors = schema::validate(playbook);
    let sources = source_ids(playbook);
    let (mut verified, mut rejected, mut learned) = (0, 0, 0);
    let mut details = Vec::new();
    let mut items = Vec::new();
    if expanded {
        cited_items(playbook, "$", &mut items);
    } else {
        for key in ["steps", "base_reading"] {
            if let Some(value) = playbook.get(key) {
                cited_items(value, &format!("$.{key}"), &mut items);
            }
        }
    }
    for (path, item) in items {
        for key in ["cite", "aim_cite"] {
            if !expanded && key == "aim_cite" {
                continue;
            }
            if key == "aim_cite" && item.get(key).is_none() {
                continue;
            }
            let label = format!("{path}.{key} {}", text(item, "id", ""));
            let mut supported = false;
            for (citation, cite) in list(item, key).iter().enumerate() {
                let time = transcripts.verify(cite)?;
                let family_source =
                    sources.is_empty() || sources.contains(&citations::source_id(cite));
                if time.is_some() {
                    verified += 1;
                } else {
                    rejected += 1;
                }
                supported |= time.is_some() && family_source;
                details.push(obj([
                    ("item", string(&label)),
                    ("citation", wire::num(citation as f64)),
                    ("video", string(text(cite, "video", ""))),
                    ("replay", cite.get("replay").cloned().unwrap_or(Json::Null)),
                    ("verified_t", time.map_or(Json::Null, Json::Num)),
                    ("family_source", Json::Bool(family_source)),
                ]));
            }
            let uncited = allow_learned
                && (item.get("uncited").is_some_and(io::truth)
                    || text(item, "provenance", "") == "learned");
            if uncited {
                learned += 1;
            } else if !supported {
                errors.push(format!("{label}: no verified family-source citation"));
            }
        }
    }
    Ok(obj([
        ("verified_citations", wire::num(verified)),
        ("rejected_citations", wire::num(rejected)),
        ("learned_items", wire::num(learned)),
        (
            "errors",
            Json::Arr(errors.into_iter().map(string).collect()),
        ),
        ("citations", Json::Arr(details)),
    ]))
}

/// Compare reruns to previously saved Python verdicts without executing Python.
pub fn compare_recorded(
    sources: &Path,
    playbooks: &Path,
    transcripts: &mut Transcripts,
) -> Result<Json, String> {
    let mut differences = Vec::new();
    let (mut extracted, mut consolidated, mut kept, mut dropped) = (0, 0, 0.0, 0.0);
    for raw in io::files(&sources.join("playbooks"), "raw")? {
        let saved = raw.with_extension("json");
        if !saved.exists() {
            continue;
        }
        let video = raw
            .file_stem()
            .and_then(|s| s.to_str())
            .ok_or("invalid video name")?;
        let Some(lines) = transcripts.get(video)?.cloned() else {
            differences.push(string(format!("{video}: missing transcript")));
            continue;
        };
        let reply = fs::read_to_string(&raw).map_err(|e| e.to_string())?;
        let result = citations::check_extracted(&reply, video, &lines)?;
        let expected = io::read(&saved)?;
        let keys = [
            "base_reading",
            "steps",
            "rules",
            "spell_policy",
            "ability_policy",
            "check",
            "parse_error",
        ];
        if keys.iter().any(|key| result.get(key) != expected.get(key)) {
            differences.push(string(format!("{video}: extraction differs")));
        }
        if let Some(check) = result.get("check") {
            kept += wire::number(check, "kept", 0.0);
            dropped += wire::number(check, "dropped", 0.0);
        }
        extracted += 1;
    }
    for raw in io::files(&sources.join("consolidated"), "raw")? {
        let saved = playbooks
            .join(raw.file_name().ok_or("invalid family name")?)
            .with_extension("json");
        if !saved.exists() {
            continue;
        }
        let result = consolidate(
            &fs::read_to_string(&raw).map_err(|e| e.to_string())?,
            transcripts,
            true,
        )?;
        let expected = io::read(&saved)?;
        if result.get("check") != expected.get("check") {
            differences.push(obj([
                (
                    "family",
                    string(saved.file_stem().and_then(|s| s.to_str()).unwrap_or("")),
                ),
                (
                    "reproduced",
                    result.get("check").cloned().unwrap_or(Json::Null),
                ),
                (
                    "recorded",
                    expected.get("check").cloned().unwrap_or(Json::Null),
                ),
            ]));
        }
        consolidated += 1;
    }
    Ok(obj([
        ("extracted_replies", wire::num(extracted)),
        ("items_kept", wire::num(kept)),
        ("items_dropped", wire::num(dropped)),
        ("consolidated_replies", wire::num(consolidated)),
        ("differences", Json::Arr(differences)),
    ]))
}
