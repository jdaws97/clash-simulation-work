//! Verified source-only completion merging, preserving executor list order.
use crate::citations::{parse_reply, Transcripts};
use crate::{io, schema, verify};
use clash_data::json::Json;
use clash_data::wire::{list, obj, put, string, text};
use std::collections::BTreeSet;

fn completion(step: &Json) -> bool {
    step.get("completion").is_some_and(io::truth)
}

pub fn place(steps: Vec<Json>) -> Vec<Json> {
    let mut base: Vec<_> = steps.iter().filter(|s| !completion(s)).cloned().collect();
    for step in steps.into_iter().filter(completion) {
        let when = step.get("when").unwrap_or(&Json::Null);
        let reference = when
            .get("after")
            .or_else(|| {
                list(when, "all")
                    .iter()
                    .chain(list(when, "any"))
                    .find_map(|w| w.get("after"))
            })
            .and_then(|v| match v {
                Json::Str(id) => Some(id.as_str()),
                _ => None,
            });
        let mut index = if let Some(position) =
            reference.and_then(|id| base.iter().position(|s| text(s, "id", "") == id))
        {
            let last_sibling = base
                .iter()
                .enumerate()
                .filter(|(_, s)| {
                    !completion(s)
                        && s.get("when")
                            .and_then(|w| w.get("after"))
                            .is_some_and(|v| Some(v.str()) == reference)
                })
                .map(|(i, _)| i)
                .last();
            let mut index = last_sibling.map_or(position + 1, |i| (position + 1).max(i + 1));
            while index < base.len() && completion(&base[index]) {
                index += 1;
            }
            index
        } else if when.get("t").is_some() {
            0
        } else {
            base.len()
        };
        index = index.min(base.len());
        base.insert(index, step);
    }
    base
}

pub fn merge(
    playbook: &Json,
    reply: &str,
    transcripts: &mut Transcripts,
) -> Result<(Json, Json), String> {
    let reply = parse_reply(reply).ok_or("unparseable completion reply")?;
    let sources = verify::source_ids(playbook);
    let mut ids: BTreeSet<_> = list(playbook, "steps")
        .iter()
        .map(|s| text(s, "id", "").to_owned())
        .collect();
    let mut steps = list(playbook, "steps").to_vec();
    let mut rejected = Vec::new();
    let mut kept = Vec::new();
    for step in list(&reply, "add_steps") {
        let id = text(step, "id", "");
        let mut reasons = Vec::new();
        if ids.contains(id) {
            reasons.push("id clash".to_owned());
        }
        match schema::step_references(step) {
            Ok(refs) => {
                for reference in refs {
                    if !ids.contains(&reference) {
                        reasons.push(format!("unknown dependency {reference}"));
                    }
                }
            }
            Err(error) => reasons.push(error),
        }
        let cites = verify::good_cites(step, transcripts, Some(&sources), true)?;
        if cites.is_empty() {
            reasons.push("no verified quote".to_owned());
        }
        if reasons.is_empty() {
            let mut step = step.clone();
            put(&mut step, "cite", Json::Arr(cites));
            put(&mut step, "completion", Json::Bool(true));
            ids.insert(id.to_owned());
            kept.push(string(id));
            steps.push(step);
        } else {
            rejected.push(obj([
                ("id", string(id)),
                (
                    "reasons",
                    Json::Arr(reasons.into_iter().map(string).collect()),
                ),
            ]));
        }
    }
    let mut result = playbook.clone();
    if !kept.is_empty() {
        put(&mut result, "steps", Json::Arr(place(steps)));
    }
    let errors = schema::validate(&result);
    if !errors.is_empty() {
        return Err(errors.join("; "));
    }
    if !kept.is_empty() {
        let mut notes = list(&result, "notes").to_vec();
        notes.push(string("Steps marked completion: true were verified against this playbook's source transcripts by clash playbook complete."));
        put(&mut result, "notes", Json::Arr(notes));
    }
    Ok((
        result,
        obj([("kept", Json::Arr(kept)), ("rejected", Json::Arr(rejected))]),
    ))
}
