use std::collections::BTreeMap;
use std::io::{BufRead, BufReader};
use std::path::Path;

use clash_data::json::{self, Json};
use clash_data::wire::{self, obj, string, text};

use super::library::{records, MoveLibrary, SourceBook};
use super::schema::{canonical, required, MoveInstance};
use crate::compile::{CompileOptions, Compiler};

/// Reconstruct every inventoried array from stored occurrence parameters. The
/// source book supplies only its envelope (roster, variant selection metadata,
/// etc.). An unresolved occurrence is an archived source record, not a move
/// admitted for future composition.
pub fn lower_book(book: &SourceBook, library: &MoveLibrary) -> Result<Json, String> {
    let mut instances = BTreeMap::new();
    for instance in library
        .instances
        .iter()
        .filter(|value| value.source_file == book.source_file)
    {
        if instances
            .insert(instance.pointer.as_str(), instance)
            .is_some()
        {
            return Err(format!("duplicate occurrence {}", instance.instance_id));
        }
        if let Some(id) = &instance.move_id {
            let definition = library
                .definition(id)
                .ok_or_else(|| format!("unknown move {id}"))?;
            if definition.lowering != "typed_v2"
                || Some(definition.definition_version) != instance.definition_version
            {
                return Err(format!(
                    "unsupported lowering/version for {}",
                    instance.instance_id
                ));
            }
        }
    }
    let mut lowered = book.value.clone();
    for (pointer, _, _) in records(book) {
        let instance = instances
            .remove(pointer.as_str())
            .ok_or_else(|| format!("missing {}#{pointer}", book.source_file))?;
        *pointer_mut(&mut lowered, &pointer)? = reconstruct(instance)?;
    }
    if !instances.is_empty() {
        return Err(format!("extra occurrences for {}", book.source_file));
    }
    Ok(lowered)
}

/// Archive reconstruction also covers unresolved and scope-unverified records.
/// Search/composition must call `lower_instance`, which enforces strict scope.
pub fn reconstruct(instance: &MoveInstance) -> Result<Json, String> {
    let mut record = instance.parameters.executable();
    for (key, value) in &instance.evidence.annotations {
        if !super::schema::annotation_key(key) {
            return Err(format!("executable/unknown annotation: {key}"));
        }
        wire::put(&mut record, key, value.clone());
    }
    if instance.evidence.cite_present {
        wire::put(
            &mut record,
            "cite",
            Json::Arr(
                instance
                    .evidence
                    .citations
                    .iter()
                    .map(|evidence| evidence.citation.clone())
                    .collect(),
            ),
        );
    } else if !instance.evidence.citations.is_empty() {
        return Err("citations without a source cite field".to_owned());
    }
    Ok(record)
}

pub fn lower_instance(instance: &MoveInstance, library: &MoveLibrary) -> Result<Json, String> {
    let definition = instance
        .move_id
        .as_deref()
        .and_then(|id| library.definition(id))
        .ok_or("unmapped move cannot be composed")?;
    super::validate::check_instance(definition, instance)?;
    reconstruct(instance)
}

fn pointer_mut<'a>(value: &'a mut Json, pointer: &str) -> Result<&'a mut Json, String> {
    let mut current = value;
    for token in pointer
        .strip_prefix('/')
        .ok_or("invalid occurrence pointer")?
        .split('/')
    {
        current = match current {
            Json::Obj(fields) => fields
                .iter_mut()
                .find(|(key, _)| key == token)
                .map(|(_, value)| value),
            Json::Arr(values) => token
                .parse::<usize>()
                .ok()
                .and_then(|index| values.get_mut(index)),
            _ => None,
        }
        .ok_or_else(|| format!("invalid occurrence pointer {pointer}"))?;
    }
    Ok(current)
}

pub fn check_books(books: &[SourceBook], library: &MoveLibrary) -> Result<usize, String> {
    for book in books {
        let lowered = lower_book(book, library)?;
        if canonical(&lowered) != canonical(&book.value) {
            return Err(format!("lowering differs: {}", book.source_file));
        }
    }
    Ok(books.len())
}

/// Compare both compiler paths against the frozen full-plan oracle, including
/// failed feasibility cases. No fixture or expectation is generated or updated.
pub fn check_compiled_plans(
    root: &Path,
    catalog_path: &Path,
    books: &[SourceBook],
    library: &MoveLibrary,
) -> Result<Json, String> {
    let catalog = crate::catalog::Catalog::load(catalog_path)?;
    let mut compiler = Compiler::load(root, &catalog.stats)?;
    compiler.library.user = wire::read(&root.join(clash_data::private::PUBLIC_ACCOUNT))?;
    let mut reconstructed_compiler = Compiler::load(root, &catalog.stats)?;
    reconstructed_compiler.library.user = compiler.library.user.clone();
    for book in books {
        let family = Path::new(&book.source_file)
            .file_stem()
            .and_then(|stem| stem.to_str())
            .ok_or("invalid source filename")?;
        let target = reconstructed_compiler
            .playbooks
            .iter_mut()
            .find(|(name, _)| name == family)
            .ok_or_else(|| format!("compiler missing book {family}"))?;
        target.1 = lower_book(book, library)?;
    }
    let file = std::fs::File::open(root.join("fixtures/golden/plans.jsonl"))
        .map_err(|error| error.to_string())?;
    let mut total = 0;
    let mut errors = 0;
    let mut production_cases = 0;
    for (index, line) in BufReader::new(file).lines().enumerate() {
        let row = json::parse(&line.map_err(|error| error.to_string())?)
            .map_err(|error| error.to_string())?;
        let fixture = required(&row, "case")?;
        let playbooks = row.get("playbooks") == Some(&Json::Bool(true));
        let options = case_options(fixture, playbooks)?;
        let original = outcome(&compiler, fixture, &options)?;
        let reconstructed = outcome(&reconstructed_compiler, fixture, &options)?;
        let expected = required(&row, "outcome")?;
        if canonical(&original) != canonical(&reconstructed)
            || canonical(&original) != canonical(expected)
        {
            return Err(format!(
                "move lowering compiled-plan difference at row {} ({})",
                index + 1,
                text(fixture, "id", "")
            ));
        }
        if original.get("error").is_some_and(|value| !value.is_null()) {
            errors += 1;
        }
        let family = crate::armies::family_of(required(fixture, "build")?);
        if playbooks
            && books.iter().any(|book| {
                let book_family = text(&book.value, "family", "");
                family == Some(book_family)
                    || (family == Some("super-dragon") && book_family == "dragon")
            })
        {
            production_cases += 1;
        }
        total += 1;
    }
    if total == 0 || production_cases == 0 {
        return Err("no compiled-plan proof coverage".to_owned());
    }
    Ok(obj([
        ("golden_cases", wire::num(total as f64)),
        (
            "production_playbook_cases",
            wire::num(production_cases as f64),
        ),
        ("identical_rejections", wire::num(errors as f64)),
        ("differences", wire::num(0)),
    ]))
}

fn case_options(case: &Json, playbooks: bool) -> Result<CompileOptions, String> {
    let mut options = CompileOptions {
        playbooks,
        ..CompileOptions::default()
    };
    if let Some(value) = case.get("options") {
        options.overrides = value
            .get("overrides")
            .cloned()
            .unwrap_or_else(|| obj([] as [(&str, Json); 0]));
        options.flank_offset = wire::number(value, "flank_offset", 0.9);
        options.charge_side = match value.get("charge_side") {
            Some(Json::Str(side)) => Some(side.clone()),
            None | Some(Json::Null) => None,
            _ => return Err("invalid golden charge_side".to_owned()),
        };
        if let Some(values) = value.get("tactics") {
            options.tactics = Some(values.arr().iter().map(Json::f64).collect());
        }
    }
    Ok(options)
}

fn outcome(
    compiler: &Compiler<'_>,
    fixture: &Json,
    options: &CompileOptions,
) -> Result<Json, String> {
    let mut outcome = obj([] as [(&str, Json); 0]);
    match compiler.plan_for_build(
        required(fixture, "build")?,
        required(fixture, "angle")?.f64(),
        required(fixture, "seed")?.i64(),
        options,
    ) {
        Err(error) => wire::put(&mut outcome, "error", string(error)),
        Ok(mut plan) => {
            if let Some(overrides) = fixture.get("plan_overrides") {
                for (key, value) in overrides.obj() {
                    wire::put(&mut plan, key, value.clone());
                }
            }
            let problems = compiler.legal(&plan);
            let error = compiler.require_legal(&mut plan).err();
            wire::put(&mut outcome, "plan", plan);
            wire::put(
                &mut outcome,
                "legal",
                Json::Arr(problems.into_iter().map(string).collect()),
            );
            wire::put(&mut outcome, "error", error.map_or(Json::Null, string));
        }
    }
    Ok(outcome)
}
