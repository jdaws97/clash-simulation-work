use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

use clash_data::content;
use clash_data::json::Json;
use clash_data::wire::{self, list, obj, string, text};

use super::schema::{self, EvidenceScope, MoveDefinition, MoveInstance};

pub struct MoveLibrary {
    pub definitions: Vec<MoveDefinition>,
    pub instances: Vec<MoveInstance>,
    pub mechanic_dependencies: BTreeSet<String>,
    pub catalog_sha256: String,
}

impl MoveLibrary {
    pub fn load(directory: &Path) -> Result<Self, String> {
        Self::from_json(
            &wire::read(&directory.join("library.json"))?,
            &wire::read(&directory.join("occurrences.json"))?,
        )
    }

    pub fn from_json(library: &Json, occurrences: &Json) -> Result<Self, String> {
        if schema::version(library, "schema_version")? != schema::SCHEMA_VERSION
            || schema::version(occurrences, "schema_version")? != schema::SCHEMA_VERSION
        {
            return Err("unsupported move registry schema version".to_owned());
        }
        if schema::array(library, "definitions")?.is_empty() {
            return Err("move library needs at least one definition".to_owned());
        }
        Ok(Self {
            catalog_sha256: schema::required_text(library, "catalog_sha256")?,
            definitions: schema::array(library, "definitions")?
                .iter()
                .map(MoveDefinition::from_json)
                .collect::<Result<_, _>>()?,
            instances: schema::array(occurrences, "occurrences")?
                .iter()
                .map(MoveInstance::from_json)
                .collect::<Result<_, _>>()?,
            mechanic_dependencies: schema::strings(library, "mechanic_dependencies")?
                .into_iter()
                .collect(),
        })
    }

    pub fn definition(&self, id: &str) -> Option<&MoveDefinition> {
        self.definitions.iter().find(|value| value.move_id == id)
    }
}

#[derive(Clone, Debug)]
pub struct SourceBook {
    pub source_file: String,
    pub value: Json,
}

/// Read only production books, using stable repository-relative evidence paths.
pub fn read_books(directory: &Path) -> Result<Vec<SourceBook>, String> {
    let mut paths = std::fs::read_dir(directory)
        .map_err(|error| format!("{}: {error}", directory.display()))?
        .map(|entry| {
            entry
                .map(|entry| entry.path())
                .map_err(|error| error.to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    paths.sort();
    let mut books = Vec::new();
    for path in paths {
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("");
        if path.extension().and_then(|extension| extension.to_str()) != Some("json")
            || name.starts_with("test-")
        {
            continue;
        }
        let value = wire::read(&path)?;
        schema::array(&value, "steps")?;
        for key in ["spell_support", "base_reading", "variants"] {
            if value.get(key).is_some() {
                schema::array(&value, key)?;
            }
        }
        for variant in list(&value, "variants") {
            if variant.get("steps").is_some() {
                schema::array(variant, "steps")?;
            }
        }
        books.push(SourceBook {
            source_file: format!("data/source/playbooks/{name}"),
            value,
        });
    }
    if books.is_empty() {
        return Err("no production playbooks selected".to_owned());
    }
    Ok(books)
}

pub fn records(book: &SourceBook) -> Vec<(String, String, &Json)> {
    let mut records = Vec::new();
    for (key, kind) in [
        ("steps", "default_step"),
        ("spell_support", "spell_support"),
        ("base_reading", "base_reading"),
    ] {
        for (index, record) in list(&book.value, key).iter().enumerate() {
            records.push((format!("/{key}/{index}"), kind.to_owned(), record));
        }
    }
    for (variant, value) in list(&book.value, "variants").iter().enumerate() {
        for (index, record) in list(value, "steps").iter().enumerate() {
            records.push((
                format!("/variants/{variant}/steps/{index}"),
                "variant_step".to_owned(),
                record,
            ));
        }
    }
    records
}

pub fn select_fields(value: &Json, keys: &[&str]) -> Json {
    obj(keys
        .iter()
        .filter_map(|key| value.get(key).map(|value| (*key, value.clone()))))
}

pub fn entity_kind(name: &str) -> &'static str {
    if ["Logger", "Longshot", "Smasher"].contains(&name) {
        "guardian"
    } else if content::equipment(name) {
        "equipment"
    } else if content::pet(name) {
        "pet"
    } else if content::is_siege(name) {
        "siege"
    } else if name.ends_with(" Spell") {
        "spell"
    } else if crate::plans::is_hero(name) {
        "hero"
    } else {
        "troop"
    }
}

pub fn applicability(book: &SourceBook, pointer: &str) -> Json {
    let mut context = select_fields(&book.value, &["th", "mode", "patch", "catalog"]);
    for key in ["attacker_town_hall", "mode", "patch"] {
        if context.get(key).is_none() {
            wire::put(&mut context, key, Json::Null);
        }
    }
    wire::put(
        &mut context,
        "availability",
        string("original_book_compiler_inventory_checks"),
    );
    wire::put(
        &mut context,
        "army_hash",
        string(schema::fingerprint(
            book.value.get("army").unwrap_or(&Json::Null),
        )),
    );
    wire::put(
        &mut context,
        "catalog_identity",
        string("data/generated/catalog.json; not a new compatibility claim"),
    );
    if let Some(index) = pointer
        .strip_prefix("/variants/")
        .and_then(|rest| rest.split('/').next())
        .and_then(|index| index.parse::<usize>().ok())
    {
        if let Some(variant) = list(&book.value, "variants").get(index) {
            wire::put(
                &mut context,
                "variant",
                select_fields(
                    variant,
                    &[
                        "name",
                        "required_loadouts",
                        "requires",
                        "army",
                        "troops",
                        "spells",
                        "cc",
                        "heroes",
                        "loadouts",
                    ],
                ),
            );
        }
    }
    context
}

pub fn completion() -> Json {
    obj([
        ("success", string("existing_executor_action_success")),
        (
            "cancellation",
            string("existing_executor_terminal_skip_or_failure"),
        ),
        (
            "tactical_success",
            string("not_established_by_action_completion"),
        ),
    ])
}

pub fn human_costs() -> Json {
    obj([
        (
            "input_sequence",
            string("original_record; serialized by existing executor"),
        ),
        ("slots", Json::Null),
        ("taps", Json::Null),
        ("hold_duration", Json::Null),
        ("gesture_path", Json::Null),
        ("attention_region", Json::Null),
        (
            "observation_requirements",
            string("source predicates; M2 observation permissions pending"),
        ),
        (
            "status",
            string("unmeasured; existing executor pacing retained"),
        ),
    ])
}

pub fn attribution() -> Json {
    obj([
        ("sequence", string("exact_source_record")),
        ("parameter_adaptation", Json::Bool(false)),
        ("novel_composition", Json::Bool(false)),
        ("real_play_validation", string("not_established")),
    ])
}

/// Refresh the inventory while retaining reviewed decisions only for unchanged
/// records. New or changed records become explicit unresolved entries.
pub fn index(books: &[SourceBook], previous: Option<&Json>) -> Result<Json, String> {
    let old: BTreeMap<_, _> = previous
        .into_iter()
        .flat_map(|value| list(value, "occurrences"))
        .map(|value| (text(value, "instance_id", ""), value))
        .collect();
    let mut occurrences = Vec::new();
    for book in books {
        for (pointer, kind, record) in records(book) {
            let id = format!("{}#{pointer}", book.source_file);
            let hash = schema::fingerprint(record);
            let reviewed = old.get(id.as_str()).filter(|value| {
                text(value, "source_hash", "") == hash
                    && value.get("applicability") == Some(&applicability(book, &pointer))
            });
            if let Some(previous) = reviewed.filter(|value| {
                value.get("schema_version") == Some(&wire::num(schema::SCHEMA_VERSION))
            }) {
                occurrences.push((*previous).clone());
                continue;
            }
            let evidence = list(record, "cite")
                .iter()
                .enumerate()
                .map(|(index, citation)| {
                    obj([
                        ("source_file", string(&book.source_file)),
                        ("pointer", string(format!("{pointer}/cite/{index}"))),
                        ("citation", citation.clone()),
                    ])
                })
                .collect();
            let mut instance = obj([
                ("schema_version", wire::num(schema::SCHEMA_VERSION)),
                ("instance_id", string(id)),
                ("source_file", string(&book.source_file)),
                ("pointer", string(&pointer)),
                ("kind", string(kind)),
                ("source_hash", string(hash)),
                ("status", string("unresolved")),
                (
                    "reason",
                    string("New or changed source occurrence; technique assignment needs review."),
                ),
                ("move_id", Json::Null),
                ("definition_version", Json::Null),
                ("applicability", applicability(book, &pointer)),
                (
                    "parameters",
                    schema::MoveParameters::from_record(record)?.to_json(),
                ),
                ("scope_unverified", Json::Arr(Vec::new())),
                (
                    "evidence",
                    obj([
                        ("citations", Json::Arr(evidence)),
                        ("cite_present", Json::Bool(record.get("cite").is_some())),
                        (
                            "annotations",
                            obj(record
                                .obj()
                                .iter()
                                .filter(|(key, _)| schema::annotation_key(key))
                                .cloned()),
                        ),
                    ]),
                ),
                ("evidence_scope", EvidenceScope::inherited().to_json()),
                ("human_costs", human_costs()),
                ("mechanic_dependencies", Json::Arr(Vec::new())),
                ("attribution", attribution()),
            ]);
            // Schema migration preserves reviewed identities and ancestry, never
            // reclassifies a changed source record or fabricates evidence.
            if let Some(previous) = reviewed {
                for key in [
                    "status",
                    "reason",
                    "move_id",
                    "definition_version",
                    "mechanic_dependencies",
                    "attribution",
                ] {
                    if let Some(value) = previous.get(key) {
                        wire::put(&mut instance, key, value.clone());
                    }
                }
            }
            occurrences.push(instance);
        }
    }
    Ok(obj([
        ("schema_version", wire::num(schema::SCHEMA_VERSION)),
        ("occurrences", Json::Arr(occurrences)),
    ]))
}

/// A role is source support, never an assertion that actors are interchangeable.
/// Loadout co-occurrence is counted separately from item-specific video support.
pub fn roles(books: &[SourceBook], library: &MoveLibrary, catalog: &Json) -> Json {
    let mut entities = BTreeSet::new();
    for book in books {
        collect_entities(&book.value, "", &mut entities);
    }
    // Notes retain source alternatives and embedded roster JSON. Include named
    // catalog mentions without inventing a role for an item mentioned in prose.
    let mut names = BTreeSet::new();
    if let Some(Json::Obj(units)) = catalog.get("units") {
        names.extend(units.iter().map(|(name, _)| name.clone()));
    }
    if let Some(Json::Obj(registry)) = catalog.get("registry") {
        names.extend(
            registry
                .iter()
                .filter(|(name, _)| {
                    content::equipment(name) || content::pet(name) || name.ends_with(" Spell")
                })
                .map(|(name, _)| name.clone()),
        );
    }
    let mut names = names
        .into_iter()
        .map(|name| (normalize(&name), name))
        .collect::<Vec<_>>();
    names.sort_by(|left, right| {
        right
            .0
            .len()
            .cmp(&left.0.len())
            .then_with(|| left.1.cmp(&right.1))
    });
    for book in books {
        collect_mentions(&book.value, &names, &mut entities);
    }
    entities.retain(|name| entity_kind(name) != "guardian");
    let mut rows = Vec::new();
    for name in entities {
        let mut purposes: BTreeMap<String, (BTreeSet<String>, BTreeSet<String>, BTreeSet<String>)> =
            BTreeMap::new();
        for instance in &library.instances {
            let Some(definition) = instance
                .move_id
                .as_deref()
                .and_then(|id| library.definition(id))
            else {
                continue;
            };
            let source = instance.parameters.executable();
            let actor = text(&source, "what", "");
            let explicit = actor == name
                || unit_recipient(&source) == Some(name.as_str())
                || contains_name(source.get("equipment"), &name);
            let context = books
                .iter()
                .find(|book| book.source_file == instance.source_file)
                .is_some_and(|book| {
                    loadout_contains(&book.value, actor, &name)
                        || loadout_contains(&instance.applicability, actor, &name)
                });
            if !explicit && !context {
                continue;
            }
            let (videos, context_videos, occurrences) =
                purposes.entry(definition.move_id.clone()).or_default();
            occurrences.insert(instance.instance_id.clone());
            for evidence in &instance.evidence.citations {
                if !super::validate::video_citation(&evidence.citation) {
                    continue;
                }
                let video = text(&evidence.citation, "video", "").to_owned();
                if explicit || quote_mentions(&evidence.citation, &name) {
                    videos.insert(video);
                } else if context {
                    context_videos.insert(video);
                }
            }
        }
        let purposes = purposes
            .into_iter()
            .map(|(id, (videos, context, occurrences))| {
                let definition = library.definition(&id).expect("known definition");
                obj([
                    ("move_id", string(id)),
                    ("purpose", string(&definition.purpose)),
                    ("distinct_supporting_videos", wire::num(videos.len() as f64)),
                    (
                        "videos",
                        Json::Arr(videos.into_iter().map(string).collect()),
                    ),
                    ("distinct_context_videos", wire::num(context.len() as f64)),
                    (
                        "context_videos",
                        Json::Arr(context.into_iter().map(string).collect()),
                    ),
                    (
                        "occurrences",
                        Json::Arr(occurrences.into_iter().map(string).collect()),
                    ),
                ])
            })
            .collect::<Vec<_>>();
        rows.push(obj([
            ("name", string(&name)),
            ("kind", string(entity_kind(&name))),
            (
                "status",
                string(if purposes.is_empty() {
                    "referenced_without_mapped_role"
                } else {
                    "source_supported_or_loadout_context"
                }),
            ),
            ("purposes", Json::Arr(purposes)),
        ]));
    }
    obj([
        ("schema_version", wire::num(schema::SCHEMA_VERSION)),
        ("support_scope", string("explicit source actor/recipient/equipment binding, or literal item quote within a bound hero loadout; inferred purpose; video IDs deduplicated per role")),
        ("context_scope", string("hero loadout association alone supplies no item-specific supporting-video count")),
        ("entities", Json::Arr(rows)),
    ])
}

fn contains_name(value: Option<&Json>, name: &str) -> bool {
    match value {
        Some(Json::Str(value)) => value == name,
        Some(Json::Arr(values)) => values.iter().any(|value| contains_name(Some(value), name)),
        _ => false,
    }
}

fn unit_recipient(record: &Json) -> Option<&str> {
    let anchor = text(record, "at", "");
    anchor
        .strip_prefix("unit:")
        .or_else(|| anchor.strip_prefix("unit_ahead:"))
}

fn loadout_contains(value: &Json, actor: &str, name: &str) -> bool {
    if actor.is_empty() || entity_kind(actor) != "hero" {
        return false;
    }
    match value {
        Json::Obj(fields) => fields.iter().any(|(key, value)| {
            (key == actor && contains_name(Some(value), name))
                || loadout_contains(value, actor, name)
        }),
        Json::Arr(values) => values
            .iter()
            .any(|value| loadout_contains(value, actor, name)),
        _ => false,
    }
}

fn quote_mentions(citation: &Json, name: &str) -> bool {
    mentions(text(citation, "quote", ""), name)
}

fn mentions(value: &str, name: &str) -> bool {
    let value = format!(" {} ", normalize(value));
    let name = normalize(name);
    value.contains(&format!(" {name} ")) || value.contains(&format!(" {name}s "))
}

fn normalize(value: &str) -> String {
    value
        .to_lowercase()
        .split(|character: char| !character.is_alphanumeric())
        .filter(|word| !word.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

fn collect_mentions(value: &Json, names: &[(String, String)], entities: &mut BTreeSet<String>) {
    match value {
        Json::Str(value) => {
            let mut remaining = format!(" {} ", normalize(value));
            // Prefer complete names: Giant Arrow is not a reference to Giant.
            for (normalized, name) in names {
                let singular = format!(" {normalized} ");
                let plural = format!(" {normalized}s ");
                if remaining.contains(&singular) || remaining.contains(&plural) {
                    entities.insert(name.clone());
                    remaining = remaining.replace(&singular, " ").replace(&plural, " ");
                }
            }
        }
        Json::Arr(values) => {
            for value in values {
                collect_mentions(value, names, entities);
            }
        }
        Json::Obj(fields) => {
            for (_, value) in fields {
                collect_mentions(value, names, entities);
            }
        }
        _ => {}
    }
}

fn collect_entities(value: &Json, parent: &str, entities: &mut BTreeSet<String>) {
    match value {
        Json::Obj(fields) => {
            for (key, value) in fields {
                if [
                    "troops",
                    "spells",
                    "cc",
                    "loadouts",
                    "required_loadouts",
                    "pets",
                ]
                .contains(&parent)
                {
                    entities.insert(key.clone());
                }
                collect_entities(value, key, entities);
            }
        }
        Json::Arr(values) => {
            for value in values {
                collect_entities(value, parent, entities);
            }
        }
        Json::Str(name) => {
            if (name.chars().next().is_some_and(char::is_uppercase)
                && [
                    "what",
                    "heroes",
                    "equipment",
                    "pets",
                    "spells_left",
                    "inside",
                    "heavy_fire",
                    "hp_below",
                    "dead",
                    "near_th",
                    "defender",
                    "mask_hero",
                ]
                .contains(&parent))
                || content::equipment(name)
                || content::pet(name)
                || crate::plans::is_hero(name)
                || content::is_siege(name)
            {
                entities.insert(name.clone());
            }
            if parent == "at" {
                if let Some(actor) = name
                    .strip_prefix("unit:")
                    .or_else(|| name.strip_prefix("unit_ahead:"))
                {
                    entities.insert(actor.to_owned());
                }
            }
        }
        _ => {}
    }
}
