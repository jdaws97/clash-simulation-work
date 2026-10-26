//! Vocabulary mirrors clash-engine/src/playbook.rs; the contract test detects drift.
use crate::io::truth;
use clash_data::json::Json;
use clash_data::wire::{list, text};
use std::collections::{BTreeMap, BTreeSet};

pub const ACTIONS: &[&str] = &[
    "deploy",
    "spell",
    "ability",
    "recall",
    "redeploy",
    "release_siege",
];
pub const ANCHORS: &[&str] = &[
    "edge",
    "unit",
    "unit_ahead",
    "group",
    "cohort",
    "th",
    "threat",
    "defenders",
    "defender",
    "building",
];
pub const PREDICATES: &[&str] = &[
    "t",
    "after",
    "inside",
    "group_inside",
    "near_th",
    "heavy_fire",
    "hp_below",
    "spells_left",
    "dead",
    "defenders_near",
    "destruction",
    "all",
    "any",
    "effect_active",
    "effect_expired",
    "objective",
    "defender",
    "cohort_absent",
    "succeeded",
];
const LEGACY_TRIGGERS: &[&str] = &[
    "t",
    "after",
    "inside",
    "group_inside",
    "near_th",
    "heavy_fire",
    "hp_below",
    "spells_left",
    "dead",
    "defenders_near",
    "destruction",
    "all",
    "any",
];
const MODIFIERS: &[&str] = &["delay", "r", "frac", "n", "state", "group"];

pub fn legacy_trigger_ok(value: Option<&Json>) -> bool {
    let Some(value) = value.filter(|value| truth(value)) else {
        return true;
    };
    let Json::Obj(fields) = value else {
        return false;
    };
    fields.iter().all(|(key, value)| {
        if key == "all" || key == "any" {
            return matches!(value, Json::Arr(items) if items.iter().all(|item| legacy_trigger_ok(Some(item))));
        }
        LEGACY_TRIGGERS.contains(&key.as_str()) || ["delay", "r", "frac", "n"].contains(&key.as_str())
    })
}

pub fn legacy_step_reason(step: &Json) -> Option<String> {
    let action = text(step, "action", "None");
    if !ACTIONS.contains(&action) {
        return Some(format!("action {action}"));
    }
    let anchor = text(step, "at", "edge:main");
    let legacy_anchors = [
        "edge:",
        "unit:",
        "unit_ahead:",
        "group:",
        "th",
        "threat:",
        "defenders:",
        "building:",
    ];
    if !["ability", "release_siege"].contains(&action)
        && !legacy_anchors
            .iter()
            .any(|prefix| anchor.starts_with(prefix))
    {
        return Some(format!("anchor {anchor}"));
    }
    if !legacy_trigger_ok(step.get("when")) || !legacy_trigger_ok(step.get("until")) {
        return Some("trigger vocabulary".to_owned());
    }
    None
}

fn trigger(value: Option<&Json>, references: &mut Vec<String>) -> Result<(), String> {
    let Some(value) = value.filter(|value| truth(value)) else {
        return Ok(());
    };
    let Json::Obj(fields) = value else {
        return Err("trigger must be an object".to_owned());
    };
    let predicates: Vec<_> = fields
        .iter()
        .filter(|(key, _)| PREDICATES.contains(&key.as_str()))
        .collect();
    if predicates.len() != 1 {
        return Err("trigger needs exactly one predicate (combine with all/any)".to_owned());
    }
    for (key, value) in fields {
        if !PREDICATES.contains(&key.as_str()) && !MODIFIERS.contains(&key.as_str()) {
            return Err(format!("unknown trigger {key}"));
        }
        if ["all", "any"].contains(&key.as_str()) {
            let Json::Arr(parts) = value else {
                return Err(format!("{key} needs an array"));
            };
            for part in parts {
                trigger(Some(part), references)?;
            }
        } else if ["t", "destruction", "delay", "r", "frac", "n"].contains(&key.as_str()) {
            if !matches!(value, Json::Num(n) if n.is_finite()) {
                return Err(format!("{key} needs a finite number"));
            }
        } else if !matches!(value, Json::Str(_)) {
            return Err(format!("{key} needs a string"));
        }
        if [
            "after",
            "effect_active",
            "effect_expired",
            "succeeded",
            "cohort_absent",
        ]
        .contains(&key.as_str())
        {
            references.push(value.str().to_owned());
        }
    }
    Ok(())
}

pub fn step_references(step: &Json) -> Result<Vec<String>, String> {
    clash_data::content::validate_playbook_step_types(step).map_err(|error| error.to_string())?;
    if !matches!(step, Json::Obj(_)) {
        return Err("step must be an object".to_owned());
    }
    if text(step, "id", "").is_empty() {
        return Err("step needs a nonempty id".to_owned());
    }
    let action = text(step, "action", "");
    if !ACTIONS.contains(&action) {
        return Err(format!("unknown action {action:?}"));
    }
    let mut references = Vec::new();
    for key in ["at", "origin", "aim"] {
        if key != "at" && step.get(key).is_none_or(|v| !truth(v)) {
            continue;
        }
        let anchor = text(step, key, "edge:main");
        if key == "aim" && ["arrow", "dash"].contains(&anchor) {
            continue;
        }
        let (kind, argument) = anchor.split_once(':').unwrap_or((anchor, ""));
        if !ANCHORS.contains(&kind) {
            return Err(format!("unknown {key} anchor {anchor:?}"));
        }
        if kind == "cohort" {
            references.push(argument.to_owned());
        }
    }
    references.extend(dependencies(step)?);
    for key in ["every", "spread", "level"] {
        if let Some(value) = step.get(key).filter(|v| !v.is_null()) {
            if !matches!(value, Json::Num(n) if n.is_finite()) {
                return Err(format!("{key} needs a finite number"));
            }
        }
    }
    if let Some(value) = step.get("count").filter(|v| !v.is_null()) {
        match value {
            Json::Num(n) if n.is_finite() && n.fract() == 0.0 => {}
            Json::Str(s) if s == "all" || s.parse::<i64>().is_ok() => {}
            _ => return Err("count needs an integer or all".to_owned()),
        }
    }
    Ok(references)
}

fn dependencies(step: &Json) -> Result<Vec<String>, String> {
    let mut references = Vec::new();
    for key in ["when", "until"] {
        trigger(step.get(key), &mut references)?;
    }
    for key in ["recall_from", "after_success"] {
        if let Some(value) = step.get(key) {
            let Json::Str(id) = value else {
                return Err(format!("{key} must name a step"));
            };
            references.push(id.clone());
        }
    }
    Ok(references)
}

pub fn validate(playbook: &Json) -> Vec<String> {
    let Some(Json::Arr(steps)) = playbook.get("steps") else {
        return vec!["playbook needs a steps array".to_owned()];
    };
    let mut base = steps.clone();
    base.extend_from_slice(list(playbook, "spell_support"));
    let mut errors = validate_steps(&base);
    for variant in list(playbook, "variants") {
        let mut context = base.clone();
        let additions = list(variant, "steps");
        let mut seen = BTreeSet::new();
        for step in additions {
            let id = text(step, "id", "");
            if !seen.insert(id) {
                errors.push(format!(
                    "variant {}: duplicate id {id}",
                    text(variant, "name", "")
                ));
            }
        }
        context.retain(|step| !seen.contains(text(step, "id", "")));
        context.extend_from_slice(additions);
        // Removed base IDs are still declared dependency targets: the compiler
        // relinks them to their prerequisites when selecting a variant. Actual
        // inventory, recipe selection and transformed-plan validation stay there.
        errors.extend(
            validate_steps(&context)
                .into_iter()
                .map(|error| format!("variant {}: {error}", text(variant, "name", ""))),
        );
    }
    errors
}

fn validate_steps(steps: &[Json]) -> Vec<String> {
    let mut errors = Vec::new();
    let mut graph = BTreeMap::new();
    let ids: BTreeSet<_> = steps.iter().map(|s| text(s, "id", "").to_owned()).collect();
    for step in steps {
        let id = text(step, "id", "");
        match step_references(step) {
            Ok(references) => {
                for reference in &references {
                    if !ids.contains(reference) {
                        errors.push(format!("{id}: unknown dependency {reference}"));
                    }
                }
                if graph.contains_key(id) {
                    errors.push(format!("{id}: duplicate id"));
                } else {
                    graph.insert(id.to_owned(), dependencies(step).unwrap_or_default());
                }
            }
            Err(reason) => errors.push(format!("{id}: {reason}")),
        }
    }
    // Match clash-plans::compile::validate_dependencies: inspect every branch,
    // when/until, effect/cohort/success references and recall linkage. Anchor
    // cohort references require an existing ID but do not form wait cycles.
    let mut done = BTreeSet::new();
    for id in graph.keys() {
        let mut active = BTreeSet::new();
        if cycle(id, &graph, &mut active, &mut done) {
            errors.push(format!("{id}: cyclic execution dependency"));
        }
    }
    errors
}

fn cycle(
    id: &str,
    graph: &BTreeMap<String, Vec<String>>,
    active: &mut BTreeSet<String>,
    done: &mut BTreeSet<String>,
) -> bool {
    if done.contains(id) {
        return false;
    }
    if !active.insert(id.to_owned()) {
        return true;
    }
    if graph
        .get(id)
        .is_some_and(|refs| refs.iter().any(|r| cycle(r, graph, active, done)))
    {
        return true;
    }
    active.remove(id);
    done.insert(id.to_owned());
    false
}
