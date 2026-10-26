//! Negative cases below are declared synthetic mutations of the pinned registry.
//! They test extraction contracts, not real-game behavior or human calibration.
use std::path::Path;

use clash_data::json::Json;
use clash_data::wire::{self, list, string};

use super::{library, lower, schema, validate, MoveLibrary};

fn inputs() -> (Json, Json, Vec<library::SourceBook>) {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let directory = root.join("data/source/moves");
    (
        wire::read(&directory.join("library.json")).unwrap(),
        wire::read(&directory.join("occurrences.json")).unwrap(),
        library::read_books(&root.join("data/source/playbooks")).unwrap(),
    )
}

#[test]
fn production_registry_reconstructs_every_array_and_refreshes_without_drift() {
    let (definitions, occurrences, books) = inputs();
    let registry = MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    let result = validate::check(&registry, &books).unwrap();
    assert_eq!(result.at("books"), &wire::num(11));
    assert_eq!(result.at("occurrences"), &wire::num(740));
    assert_eq!(lower::check_books(&books, &registry).unwrap(), 11);
    assert_eq!(
        schema::canonical(&library::index(&books, Some(&occurrences)).unwrap()),
        schema::canonical(&occurrences)
    );
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let roles = wire::read(&root.join("data/source/moves/roles.json")).unwrap();
    assert_eq!(
        schema::canonical(&roles),
        schema::canonical(&library::roles(
            &books,
            &registry,
            &wire::read(&root.join("data/generated/catalog.json")).unwrap()
        ))
    );
}

#[test]
fn missing_duplicate_and_unknown_move_references_are_rejected() {
    let (definitions, occurrences, books) = inputs();
    let mut rows = list(&occurrences, "occurrences").to_vec();
    rows.remove(0);
    let mut changed = occurrences.clone();
    wire::put(&mut changed, "occurrences", Json::Arr(rows));
    assert!(validate::check(
        &MoveLibrary::from_json(&definitions, &changed).unwrap(),
        &books
    )
    .unwrap_err()
    .contains("missing occurrence"));
    let mut rows = list(&occurrences, "occurrences").to_vec();
    rows.push(rows[0].clone());
    wire::put(&mut changed, "occurrences", Json::Arr(rows));
    assert!(validate::check(
        &MoveLibrary::from_json(&definitions, &changed).unwrap(),
        &books
    )
    .unwrap_err()
    .contains("duplicate occurrence"));
    let mut registry = MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    registry.instances[0].move_id = Some("synthetic-unknown".to_owned());
    assert!(validate::check(&registry, &books)
        .unwrap_err()
        .contains("unknown/missing move"));
}

#[test]
fn changed_quotes_scopes_bindings_and_versions_are_rejected() {
    let (definitions, occurrences, books) = inputs();
    let load = || MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    let mut registry = load();
    wire::put(
        &mut registry.instances[0].evidence.citations[0].citation,
        "quote",
        string("synthetic replacement quote"),
    );
    assert!(validate::check(&registry, &books)
        .unwrap_err()
        .contains("citation differs"));
    let mut registry = load();
    registry.instances[0].evidence_scope.timing = "measured".to_owned();
    assert!(validate::check(&registry, &books)
        .unwrap_err()
        .contains("unsupported applicability"));
    let mut registry = load();
    registry.instances[0].parameters.actor.what = schema::Field::Value("Archer".to_owned());
    assert!(validate::check(&registry, &books)
        .unwrap_err()
        .contains("typed source parameters differ"));
    let mut registry = load();
    registry.instances[0].definition_version = Some(999);
    assert!(validate::check(&registry, &books)
        .unwrap_err()
        .contains("invalid mapped version"));
}

#[test]
fn unresolved_needs_reason_and_nonvideo_evidence_cannot_be_promoted() {
    let (definitions, occurrences, books) = inputs();
    let mut registry = MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    let index = registry
        .instances
        .iter()
        .position(|instance| instance.status == schema::MappingStatus::Unresolved)
        .unwrap();
    registry.instances[index].reason.clear();
    assert!(validate::check(&registry, &books)
        .unwrap_err()
        .contains("needs a reason"));
    let mut registry = MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    let index = registry
        .instances
        .iter()
        .position(|instance| instance.status == schema::MappingStatus::Unsupported)
        .unwrap();
    let instance = &mut registry.instances[index];
    instance.status = schema::MappingStatus::Mapped;
    instance.reason.clear();
    instance.move_id = Some("protection-window".to_owned());
    instance.definition_version = Some(2);
    assert!(validate::check(&registry, &books)
        .unwrap_err()
        .contains("invalid mapped version/evidence"));
}

#[test]
fn index_invalidates_a_changed_record_and_lower_does_not_read_its_source_value() {
    let (definitions, occurrences, mut books) = inputs();
    let mut steps = list(&books[0].value, "steps").to_vec();
    wire::put(&mut steps[0], "count", wire::num(99));
    wire::put(&mut books[0].value, "steps", Json::Arr(steps));
    let refreshed = library::index(&books, Some(&occurrences)).unwrap();
    let first = &list(&refreshed, "occurrences")[0];
    assert_eq!(first.at("status"), &string("unresolved"));
    assert_eq!(first.at("move_id"), &Json::Null);
    let registry = MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    let lowered = lower::lower_book(&books[0], &registry).unwrap();
    assert_ne!(
        schema::canonical(&books[0].value),
        schema::canonical(&lowered)
    );
    assert!(lower::check_books(&books, &registry)
        .unwrap_err()
        .contains("lowering differs"));
}

#[test]
fn malformed_schema_is_an_error_without_unwinding() {
    let (definitions, occurrences, _) = inputs();
    for value in [Json::Null, wire::num(2), Json::Arr(Vec::new())] {
        let mut changed = definitions.clone();
        wire::put(&mut changed, "definitions", value);
        assert!(MoveLibrary::from_json(&changed, &occurrences).is_err());
    }
    let mut changed = definitions;
    wire::put(&mut changed, "schema_version", wire::num(0.5));
    assert!(MoveLibrary::from_json(&changed, &occurrences).is_err());
}

#[test]
fn supporting_videos_are_deduplicated_and_loadout_context_is_separate() {
    let (definitions, occurrences, _) = inputs();
    let mut registry = MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    let book = library::SourceBook {
        source_file: "data/source/playbooks/synthetic-roles.json".to_owned(),
        value: clash_data::json::parse(
            r#"{
            "army":{"loadouts":{"Grand Warden":["Fireball","Rage Gem","Electro Owl"]}},
            "steps":[{"id":"shot","action":"ability","what":"Grand Warden","equipment":"Fireball",
                "cite":[{"video":"synthetic-video","t":1,"quote":"activate the fireball now"},
                        {"video":"synthetic-video","t":2,"quote":"activate the fireball now"}]}]
        }"#,
        )
        .unwrap(),
    };
    let indexed = library::index(std::slice::from_ref(&book), None).unwrap();
    let mut instance = list(&indexed, "occurrences")[0].clone();
    wire::put(&mut instance, "move_id", string("fireball"));
    wire::put(&mut instance, "definition_version", wire::num(2));
    wire::put(&mut instance, "status", string("mapped"));
    wire::put(&mut instance, "reason", string(""));
    let instance = schema::MoveInstance::from_json(&instance).unwrap();
    registry.instances = vec![instance.clone(), instance];
    let matrix = library::roles(&[book], &registry, &wire::obj([] as [(&str, Json); 0]));
    let find = |name: &str| {
        let row = list(&matrix, "entities")
            .iter()
            .find(|row| row.get("name") == Some(&string(name)))
            .unwrap();
        &list(row, "purposes")[0]
    };
    assert_eq!(
        find("Fireball").at("distinct_supporting_videos"),
        &wire::num(1)
    );
    assert_eq!(
        find("Electro Owl").at("distinct_supporting_videos"),
        &wire::num(0)
    );
    assert_eq!(
        find("Electro Owl").at("distinct_context_videos"),
        &wire::num(1)
    );
}

#[test]
fn typed_side_mutation_changes_exactly_one_compiled_placement() {
    let (definitions, occurrences, books) = inputs();
    let mut registry = MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let catalog = crate::test_support::catalog();
    let mut compiler = crate::compile::Compiler::load(&root, &catalog.stats).unwrap();
    compiler.library.user = wire::read(&root.join(clash_data::private::PUBLIC_ACCOUNT)).unwrap();
    let row = std::fs::read_to_string(root.join("fixtures/golden/plans.jsonl"))
        .unwrap()
        .lines()
        .map(|line| clash_data::json::parse(line).unwrap())
        .find(|row| {
            row.get("playbooks") == Some(&Json::Bool(true))
                && wire::text(row.at("case"), "id", "")
                    == "meta-armies-2026-10-15.json:mass-dragons-18-1"
                && row.at("case").at("angle") == &wire::num(0)
                && row.at("case").at("seed") == &wire::num(0)
        })
        .unwrap();
    let build = row.at("case").at("build");
    let options = crate::compile::CompileOptions::default();
    let original = compiler.compile(build, 0.0, 0, &options).unwrap();
    assert_eq!(
        schema::canonical(&original),
        schema::canonical(row.at("outcome").at("plan"))
    );

    let book = books
        .iter()
        .find(|book| book.source_file.ends_with("/dragon.json"))
        .unwrap();
    let instance = registry
        .instances
        .iter_mut()
        .find(|instance| {
            instance.source_file == book.source_file
                && instance.kind == "default_step"
                && instance.parameters.control.id.value().map(String::as_str) == Some("warden")
        })
        .unwrap();
    assert_eq!(
        instance.parameters.objective.at.value().unwrap().side(),
        Some(schema::EdgeSide::Main)
    );
    instance.parameters.objective.at =
        schema::Field::Value(schema::Selector::edge(schema::EdgeSide::Left));
    let instance = instance.clone();
    assert_eq!(
        lower::lower_instance(&instance, &registry)
            .unwrap()
            .at("at"),
        &string("edge:left")
    );
    let lowered = lower::lower_book(book, &registry).unwrap();
    compiler
        .playbooks
        .iter_mut()
        .find(|(name, _)| name == "dragon")
        .unwrap()
        .1 = lowered;
    let mutated = compiler.compile(build, 0.0, 0, &options).unwrap();

    let mut expected = original.clone();
    let mut steps = list(&expected, "steps").to_vec();
    let index = steps
        .iter()
        .position(|step| wire::text(step, "id", "") == "warden")
        .unwrap();
    assert_eq!(index, 7);
    assert_eq!(steps[index].at("at"), &string("edge:main"));
    wire::put(&mut steps[index], "at", string("edge:left"));
    wire::put(&mut expected, "steps", Json::Arr(steps));
    assert_ne!(schema::canonical(&original), schema::canonical(&mutated));
    assert_eq!(schema::canonical(&mutated), schema::canonical(&expected));
    println!("CONFIRMED: typed warden side Main -> Left; only /steps/{index}/at changes (edge:main -> edge:left); entire compiled plan equals the known answer");
}

#[test]
fn strict_scope_rejects_actor_laundering_and_unsupported_typed_parameters() {
    let (definitions, occurrences, _) = inputs();
    let registry = MoveLibrary::from_json(&definitions, &occurrences).unwrap();
    let instance = registry
        .instances
        .iter()
        .find(|instance| {
            instance.move_id.as_deref() == Some("defense-snipe")
                && instance.parameters.actor.what.value().map(String::as_str)
                    == Some("Rocket Balloon")
                && instance.scope_unverified.is_empty()
        })
        .unwrap();
    let definition = registry.definition("defense-snipe").unwrap();
    validate::check_instance(definition, instance).unwrap();
    let mut changed = instance.clone();
    changed.parameters.actor.what = schema::Field::Value("Dragon".to_owned());
    changed.scope_unverified.clear();
    assert!(validate::check_instance(definition, &changed)
        .unwrap_err()
        .contains("evidence actor scope"));
    assert!(lower::lower_instance(&changed, &registry).is_err());
    let mut changed = instance.clone();
    changed.parameters.placement.spread = schema::Field::Value(2.0);
    assert!(validate::check_instance(definition, &changed)
        .unwrap_err()
        .contains("parameter/action/actor scope"));
}

#[test]
fn unknown_fields_are_explicit_residuals_and_cannot_hide_typed_values() {
    let source = crate::test_support::json(
        r#"{
        "id":"synthetic", "action":"deploy", "what":"Dragon", "count":2,
        "when":{"t":0,"future_modifier":0.25}, "future_control":{"enabled":true},
        "note":"evidence-only", "support":1, "cite":[]
    }"#,
    );
    let parameters = schema::MoveParameters::from_record(&source).unwrap();
    assert_eq!(parameters.residual.len(), 1);
    assert!(parameters.residual.contains_key("future_control"));
    let encoded = parameters.to_json();
    assert!(encoded
        .at("control")
        .at("when")
        .at("residual")
        .get("future_modifier")
        .is_some());
    let decoded = schema::MoveParameters::from_json(&encoded).unwrap();
    assert_eq!(decoded, parameters);
    assert_eq!(
        schema::canonical(decoded.executable().at("when")),
        schema::canonical(source.at("when"))
    );
    assert!(decoded.executable().get("note").is_none());
    let mut changed = encoded;
    let mut residual = changed.at("residual").clone();
    wire::put(
        &mut residual,
        "count",
        wire::obj([
            ("value", wire::num(9)),
            ("reason", string("synthetic bypass")),
        ]),
    );
    wire::put(&mut changed, "residual", residual);
    assert!(schema::MoveParameters::from_json(&changed)
        .unwrap_err()
        .contains("typed/evidence field in residual"));
    let invalid = crate::test_support::json(r#"{"when":{"after":null}}"#);
    assert!(schema::MoveParameters::from_record(&invalid)
        .unwrap_err()
        .contains("predicate fields cannot be null"));
    let invalid = crate::test_support::json(r#"{"when":{"delay":0}}"#);
    assert!(schema::MoveParameters::from_record(&invalid)
        .unwrap_err()
        .contains("trigger modifiers need a predicate"));
}
