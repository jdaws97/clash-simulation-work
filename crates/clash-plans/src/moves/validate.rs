use std::collections::{BTreeMap, BTreeSet};

use clash_data::json::Json;
use clash_data::wire::{self, list, obj, string};

use super::library::{self, MoveLibrary, SourceBook};
use super::schema::{
    canonical, EvidenceScope, MappingStatus, MoveDefinition, MoveInstance, MoveParameters,
    SCHEMA_VERSION,
};

pub fn check(library: &MoveLibrary, books: &[SourceBook]) -> Result<Json, String> {
    if library.catalog_sha256.len() != 64
        || !library
            .catalog_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        return Err("invalid move library catalog SHA-256".to_owned());
    }
    let mut definitions = BTreeMap::new();
    for definition in &library.definitions {
        if definition.schema_version != SCHEMA_VERSION
            || definition.lowering != "typed_v2"
            || definition.evidence_scope != EvidenceScope::inherited()
            || definition.human_costs != library::human_costs()
            || definition.attribution != library::attribution()
            || definition.completion != library::completion()
            || definition.parameters.get("encoding") != Some(&string("typed_v2"))
        {
            return Err(format!("unsupported move contract: {}", definition.move_id));
        }
        if definitions
            .insert(definition.move_id.as_str(), definition)
            .is_some()
        {
            return Err(format!("duplicate move definition: {}", definition.move_id));
        }
        if definition.static_preconditions.is_empty() || definition.live_preconditions.is_empty() {
            return Err(format!(
                "missing move preconditions: {}",
                definition.move_id
            ));
        }
        super::schema::strings(&definition.parameters, "supported_fields")?;
        super::schema::strings(&definition.actor_bindings, "allowed_kinds")?;
        super::schema::strings(&definition.actor_bindings, "allowed_actors")?;
        super::schema::strings(&definition.control, "allowed_actions")?;
        for dependency in &definition.mechanic_dependencies {
            if !library.mechanic_dependencies.contains(dependency) {
                return Err(format!("unknown mechanic dependency {dependency}"));
            }
        }
    }
    let mut expected = BTreeMap::new();
    for book in books {
        for (pointer, kind, record) in library::records(book) {
            let id = format!("{}#{pointer}", book.source_file);
            if expected.insert(id, (book, pointer, kind, record)).is_some() {
                return Err("duplicate source book".to_owned());
            }
        }
    }
    let mut ids = BTreeSet::new();
    let mut mapped = 0;
    let mut unresolved = 0;
    let mut unsupported = 0;
    let mut kinds = BTreeMap::new();
    let mut family_counts: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for instance in &library.instances {
        let id = &instance.instance_id;
        if !ids.insert(id.as_str()) {
            return Err(format!("duplicate occurrence: {id}"));
        }
        let (book, pointer, kind, source) = expected
            .remove(id)
            .ok_or_else(|| format!("extra occurrence: {id}"))?;
        if instance.schema_version != SCHEMA_VERSION
            || instance.source_file != book.source_file
            || instance.pointer != pointer
            || instance.kind != kind
            || instance.source_hash != super::schema::fingerprint(source)
        {
            return Err(format!(
                "stale/invalid occurrence identity: {id}; refresh index"
            ));
        }
        if instance.parameters != MoveParameters::from_record(source)? {
            return Err(format!("typed source parameters differ: {id}"));
        }
        if instance.applicability != library::applicability(book, &pointer)
            || instance.evidence_scope != EvidenceScope::inherited()
            || instance.human_costs != library::human_costs()
            || instance.attribution != library::attribution()
        {
            return Err(format!(
                "unsupported applicability/evidence/control claim: {id}"
            ));
        }
        let citations = list(source, "cite");
        if instance.evidence.citations.len() != citations.len() {
            return Err(format!("citation coverage differs: {id}"));
        }
        for (index, (evidence, citation)) in instance
            .evidence
            .citations
            .iter()
            .zip(citations)
            .enumerate()
        {
            if evidence.source_file != instance.source_file
                || evidence.pointer != format!("{pointer}/cite/{index}")
                || canonical(&evidence.citation) != canonical(citation)
            {
                return Err(format!("citation differs: {id}/cite/{index}"));
            }
        }
        if canonical(&super::lower::reconstruct(instance)?) != canonical(source) {
            return Err(format!("evidence annotations/reconstruction differ: {id}"));
        }
        for dependency in &instance.mechanic_dependencies {
            if !library.mechanic_dependencies.contains(dependency) {
                return Err(format!("unknown mechanic dependency {dependency}: {id}"));
            }
        }
        match instance.status {
            MappingStatus::Mapped => {
                let definition = instance
                    .move_id
                    .as_deref()
                    .and_then(|id| definitions.get(id))
                    .ok_or_else(|| format!("unknown/missing move reference: {id}"))?;
                if instance.definition_version != Some(definition.definition_version)
                    || !instance.reason.is_empty()
                    || citations.is_empty()
                    || citations.iter().any(|citation| !video_citation(citation))
                    || citations.iter().any(|citation| {
                        !list(&book.value, "sources")
                            .contains(citation.get("video").unwrap_or(&Json::Null))
                    })
                    || !definition.evidence.contains(id)
                {
                    return Err(format!("invalid mapped version/evidence/status: {id}"));
                }
                check_parameters(definition, instance)?;
                if instance.scope_unverified != scope_violations(definition, instance)? {
                    return Err(format!("stale scope_unverified marker: {id}"));
                }
                mapped += 1;
                family_counts
                    .entry(definition.family.clone())
                    .or_default()
                    .insert(definition.move_id.clone());
            }
            MappingStatus::Unresolved | MappingStatus::Unsupported => {
                if !instance.scope_unverified.is_empty() {
                    return Err(format!("unmapped record has no definition scope: {id}"));
                }
                if instance.reason.trim().is_empty()
                    || instance.move_id.is_some()
                    || instance.definition_version.is_some()
                {
                    return Err(format!(
                        "unresolved/unsupported needs a reason and no move reference: {id}"
                    ));
                }
                if instance.status == MappingStatus::Unresolved {
                    unresolved += 1;
                } else {
                    unsupported += 1;
                }
            }
        }
        *kinds.entry(instance.kind.clone()).or_insert(0usize) += 1;
    }
    if let Some((id, _)) = expected.first_key_value() {
        return Err(format!("missing occurrence: {id}"));
    }
    for definition in &library.definitions {
        let mut seen = BTreeSet::new();
        let mut actors = BTreeSet::new();
        for evidence in &definition.evidence {
            if !seen.insert(evidence)
                || !library.instances.iter().any(|instance| {
                    instance.instance_id == *evidence
                        && instance.move_id.as_deref() == Some(&definition.move_id)
                })
            {
                return Err(format!(
                    "invalid definition evidence reference: {} -> {evidence}",
                    definition.move_id
                ));
            }
            let instance = library
                .instances
                .iter()
                .find(|instance| instance.instance_id == *evidence)
                .expect("checked evidence reference");
            if let Some(actor) = instance.parameters.actor.what.value() {
                if cites_name(instance, actor) {
                    actors.insert(actor.clone());
                }
            }
        }
        if definition.evidence.is_empty() {
            return Err(format!("unused definition: {}", definition.move_id));
        }
        if super::schema::strings(&definition.actor_bindings, "allowed_actors")?
            != actors.into_iter().collect::<Vec<_>>()
        {
            return Err(format!(
                "definition actor scope differs from cited bindings: {}",
                definition.move_id
            ));
        }
    }
    let by_book = books.iter().map(|book| {
        let instances = library
            .instances
            .iter()
            .filter(|instance| instance.source_file == book.source_file)
            .collect::<Vec<_>>();
        let definitions = instances
            .iter()
            .filter_map(|instance| instance.move_id.as_deref())
            .collect::<BTreeSet<_>>();
        let unresolved = instances
            .iter()
            .filter(|instance| instance.status == MappingStatus::Unresolved)
            .count();
        let unsupported = instances
            .iter()
            .filter(|instance| instance.status == MappingStatus::Unsupported)
            .count();
        (
            book.source_file.clone(),
            obj([
                ("occurrences", wire::num(instances.len() as f64)),
                (
                    "mapped",
                    wire::num((instances.len() - unresolved - unsupported) as f64),
                ),
                ("unresolved", wire::num(unresolved as f64)),
                ("unsupported", wire::num(unsupported as f64)),
                ("distinct_definitions", wire::num(definitions.len() as f64)),
                (
                    "variants",
                    wire::num(list(&book.value, "variants").len() as f64),
                ),
            ]),
        )
    });
    Ok(obj([
        ("books", wire::num(books.len() as f64)),
        ("occurrences", wire::num(library.instances.len() as f64)),
        ("mapped", wire::num(mapped as f64)),
        ("unresolved", wire::num(unresolved as f64)),
        ("unsupported", wire::num(unsupported as f64)),
        ("definitions", wire::num(library.definitions.len() as f64)),
        ("typed_v2", residual_report(library)),
        ("book_families", obj(by_book)),
        ("kinds", wire::count_map(&kinds)),
        (
            "definitions_per_family",
            obj(family_counts
                .into_iter()
                .map(|(family, values)| (family, wire::num(values.len() as f64)))),
        ),
        (
            "evidence_verification",
            string("source identity checked; transcripts not reverified"),
        ),
    ]))
}

/// Shared parameter/action/kind validation, independent of source equality.
/// An operator can use it before compilation without editing source books.
pub fn check_parameters(
    definition: &MoveDefinition,
    instance: &MoveInstance,
) -> Result<(), String> {
    if definition.lowering != "typed_v2"
        || instance.definition_version != Some(definition.definition_version)
    {
        return Err("unsupported lowering/definition version".to_owned());
    }
    let source = instance.parameters.executable();
    // Round-trip validates even manually constructed Rust values and prevents
    // typed fields or evidence being smuggled through the residual map.
    if MoveParameters::from_json(&instance.parameters.to_json())? != instance.parameters {
        return Err("noncanonical typed parameter value".to_owned());
    }
    let allowed_fields = super::schema::strings(&definition.parameters, "supported_fields")?;
    let allowed_actions = super::schema::strings(&definition.control, "allowed_actions")?;
    let allowed_kinds = super::schema::strings(&definition.actor_bindings, "allowed_kinds")?;
    if executable_paths(&source)
        .keys()
        .any(|key| !allowed_fields.contains(key))
        || source.get("action").is_some_and(|action| {
            action
                .opt_str()
                .is_none_or(|action| !allowed_actions.iter().any(|allowed| allowed == action))
        })
        || source.get("what").is_some_and(|actor| {
            actor.opt_str().is_some_and(|actor| {
                !allowed_kinds.contains(&library::entity_kind(actor).to_owned())
            })
        })
    {
        return Err(format!(
            "instance exceeds definition parameter/action/actor scope: {}",
            instance.instance_id
        ));
    }
    if source.get("action").is_some() {
        if instance
            .parameters
            .control
            .id
            .value()
            .is_none_or(|id| id.trim().is_empty())
        {
            return Err("executable move needs a nonempty control.id".to_owned());
        }
        if source.get("action") != Some(&string("release_siege"))
            && instance
                .parameters
                .actor
                .what
                .value()
                .is_none_or(|actor| actor.is_empty())
        {
            return Err("executable move needs an actor".to_owned());
        }
    }
    for key in ["every", "timeout", "spread", "repeat_effect_remaining"] {
        let Some(value) = source.get(key) else {
            continue;
        };
        if value.is_null() && ["spread", "repeat_effect_remaining"].contains(&key) {
            return Err(format!("{key} cannot be null"));
        }
        let Json::Num(number) = value else {
            continue;
        };
        if *number < 0.0 || key == "repeat_effect_remaining" && *number > 1.0 {
            return Err(format!("invalid {key} bound"));
        }
    }
    if source.get("level").is_some_and(
        |value| matches!(value, Json::Num(number) if *number < 1.0 || number.fract() != 0.0),
    ) {
        return Err("level needs a positive integer".to_owned());
    }
    Ok(())
}

/// Strict admission. Archival scope markers never authorize new bindings.
pub fn check_instance(definition: &MoveDefinition, instance: &MoveInstance) -> Result<(), String> {
    if instance.status != MappingStatus::Mapped
        || instance.move_id.as_deref() != Some(&definition.move_id)
    {
        return Err("strict admission requires a mapped definition".to_owned());
    }
    check_parameters(definition, instance)?;
    let violations = scope_violations(definition, instance)?;
    if !violations.is_empty() {
        return Err(format!("evidence actor scope: {}", violations.join("; ")));
    }
    if !residual_keys(instance).is_empty() {
        return Err("unreviewed residual parameters cannot be composed".to_owned());
    }
    Ok(())
}

/// Conservative textual scope: only names actually present in the exact cited
/// quotes establish an actor/equipment binding. No synonym or role inference.
pub fn cites_name(instance: &MoveInstance, name: &str) -> bool {
    let name = name.strip_suffix(" Spell").unwrap_or(name).to_lowercase();
    let normalize = |value: &str| {
        value
            .chars()
            .map(|ch| if ch.is_alphanumeric() { ch } else { ' ' })
            .collect::<String>()
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ")
    };
    let name = normalize(&name);
    let mut citations = instance
        .evidence
        .citations
        .iter()
        .map(|evidence| &evidence.citation)
        .chain(
            instance
                .evidence
                .annotations
                .iter()
                .filter(|(key, _)| ["aim_cite", "origin_cite"].contains(&key.as_str()))
                .flat_map(|(_, value)| value.arr()),
        );
    citations.any(|citation| {
        let quote = normalize(&wire::text(citation, "quote", "").to_lowercase());
        quote
            .split_whitespace()
            .collect::<Vec<_>>()
            .windows(name.split_whitespace().count().max(1))
            .any(|words| {
                let phrase = words.join(" ");
                phrase == name || phrase == format!("{name}s")
            })
    })
}

pub fn scope_violations(
    definition: &MoveDefinition,
    instance: &MoveInstance,
) -> Result<Vec<String>, String> {
    let mut problems = Vec::new();
    if instance.parameters.action.value().is_none() {
        problems.push("prose-only rule has no executable actor/purpose binding".to_owned());
    }
    let actors = super::schema::strings(&definition.actor_bindings, "allowed_actors")?;
    if let Some(actor) = instance.parameters.actor.what.value() {
        if !actors.contains(actor) {
            problems.push(format!("actor outside definition's cited names: {actor}"));
        }
        if !cites_name(instance, actor) {
            problems.push(format!("actor not named in occurrence citations: {actor}"));
        }
    }
    if let Some(equipment) = instance.parameters.activation.equipment.value() {
        let names = match equipment {
            super::schema::EquipmentSelection::One(name) => vec![name],
            super::schema::EquipmentSelection::AnyOf(names) => names.iter().collect(),
        };
        for name in names {
            if !cites_name(instance, name) {
                problems.push(format!(
                    "equipment not named in occurrence citations: {name}"
                ));
            }
        }
    }
    Ok(problems)
}

pub fn executable_paths(value: &Json) -> BTreeMap<String, usize> {
    fn visit(value: &Json, prefix: &str, paths: &mut BTreeMap<String, usize>) {
        if let Json::Obj(fields) = value {
            for (key, value) in fields {
                let path = format!("{prefix}{key}");
                *paths.entry(path.clone()).or_default() += 1;
                match value {
                    Json::Obj(_) => visit(value, &format!("{path}."), paths),
                    Json::Arr(values) => {
                        for value in values {
                            visit(value, &format!("{path}[]."), paths);
                        }
                    }
                    _ => {}
                }
            }
        }
    }
    let mut paths = BTreeMap::new();
    visit(value, "", &mut paths);
    paths
}

fn residual_keys(instance: &MoveInstance) -> BTreeMap<String, usize> {
    fn condition(
        value: &super::schema::Condition,
        prefix: &str,
        counts: &mut BTreeMap<String, usize>,
    ) {
        if let super::schema::Condition::Predicate(value) = value {
            for key in value.residual.keys() {
                *counts.entry(format!("{prefix}.{key}")).or_default() += 1;
            }
            for (key, parts) in [("all", &value.fields.all), ("any", &value.fields.any)] {
                if let Some(parts) = parts.value() {
                    for part in parts {
                        condition(part, &format!("{prefix}.{key}[]"), counts);
                    }
                }
            }
        }
    }
    let mut counts = instance
        .parameters
        .residual
        .keys()
        .map(|key| (key.clone(), 1))
        .collect();
    for (key, value) in [
        ("when", &instance.parameters.control.when),
        ("until", &instance.parameters.control.until),
    ] {
        if let Some(value) = value.value() {
            condition(value, key, &mut counts);
        }
    }
    counts
}

pub fn residual_report(library: &MoveLibrary) -> Json {
    let mut rows = BTreeMap::new();
    let mut typed = BTreeMap::new();
    let mut residual = BTreeMap::new();
    for id in library
        .definitions
        .iter()
        .map(|definition| definition.move_id.as_str())
        .chain(["unresolved", "unsupported"])
    {
        let instances: Vec<_> = library
            .instances
            .iter()
            .filter(|instance| {
                instance.move_id.as_deref().unwrap_or(
                    if instance.status == MappingStatus::Unsupported {
                        "unsupported"
                    } else {
                        "unresolved"
                    },
                ) == id
            })
            .collect();
        let mut keys = BTreeMap::new();
        let mut typed_count = 0;
        for instance in &instances {
            let unknown = residual_keys(instance);
            for (key, count) in executable_paths(&instance.parameters.executable()) {
                if !unknown.contains_key(&key) {
                    typed_count += count;
                    *typed.entry(key).or_insert(0usize) += count;
                }
            }
            for (key, count) in unknown {
                *residual.entry(key.clone()).or_insert(0usize) += count;
                *keys.entry(key).or_insert(0usize) += count;
            }
        }
        rows.insert(
            id.to_owned(),
            obj([
                ("occurrences", wire::num(instances.len() as f64)),
                ("typed_key_uses", wire::num(typed_count as f64)),
                ("residual_keys", wire::count_map(&keys)),
                (
                    "scope_unverified",
                    wire::num(
                        instances
                            .iter()
                            .filter(|instance| !instance.scope_unverified.is_empty())
                            .count() as f64,
                    ),
                ),
            ]),
        );
    }
    obj([
        ("typed_distinct_paths", wire::num(typed.len() as f64)),
        (
            "typed_key_uses",
            wire::num(typed.values().sum::<usize>() as f64),
        ),
        ("residual_distinct_paths", wire::num(residual.len() as f64)),
        (
            "residual_key_uses",
            wire::num(residual.values().sum::<usize>() as f64),
        ),
        (
            "scope_unverified",
            wire::num(
                library
                    .instances
                    .iter()
                    .filter(|instance| !instance.scope_unverified.is_empty())
                    .count() as f64,
            ),
        ),
        ("by_definition", obj(rows)),
    ])
}

pub fn video_citation(value: &Json) -> bool {
    matches!(value.get("video"), Some(Json::Str(video)) if !video.is_empty())
        && matches!(value.get("t"), Some(Json::Num(time)) if time.is_finite() && *time >= 0.0)
        && matches!(value.get("quote"), Some(Json::Str(quote)) if !quote.trim().is_empty())
}
