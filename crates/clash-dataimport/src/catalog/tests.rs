//! Recorded-export equivalence and small declared synthetic precedence cases.

use clash_data::json::{self, Json};
use clash_data::wire::{self, num};

use super::*;

fn sources() -> Sources {
    Sources::new(Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."))
}

fn differences(actual: &Json, expected: &Json, path: &str, errors: &mut Vec<String>) {
    if errors.len() >= 30 {
        return;
    }
    match (actual, expected) {
        (Json::Obj(actual), Json::Obj(expected)) => {
            for (key, value) in expected {
                let path = format!("{path}/{key}");
                if let Some((_, actual)) = actual.iter().find(|(name, _)| name == key) {
                    differences(actual, value, &path, errors);
                } else {
                    errors.push(format!("{path}: missing"));
                }
            }
            for (key, _) in actual {
                if !expected.iter().any(|(name, _)| name == key) {
                    errors.push(format!("{path}/{key}: unexpected"));
                }
            }
        }
        (Json::Arr(actual), Json::Arr(expected)) => {
            if actual.len() != expected.len() {
                errors.push(format!(
                    "{path}: array lengths {} != {}",
                    actual.len(),
                    expected.len()
                ));
            }
            for (index, (actual, expected)) in actual.iter().zip(expected).enumerate() {
                differences(actual, expected, &format!("{path}/{index}"), errors);
            }
        }
        _ if actual == expected => {}
        _ => errors.push(format!("{path}: {actual:?} != {expected:?}")),
    }
}

fn equivalent(actual: &Json, expected: &Json) {
    let mut errors = Vec::new();
    differences(actual, expected, "", &mut errors);
    assert!(errors.is_empty(), "{}", errors.join("\n"));
}

#[test]
fn csv_matches_recorded_export() {
    let source = sources();
    let catalog = wire::read(&source.root.join("rust/data/catalog.json")).unwrap();
    let tables = csv::Tables::load(&source.root).unwrap();
    equivalent(&tables.data, field(&catalog, "game_data"));
    equivalent(&tables.ranges, field(&catalog, "game_ranges"));
    equivalent(&tables.delays, field(&catalog, "new_target_delays"));
    // Positional clamp and inheritance are part of the exporter contract.
    assert_eq!(
        tables.row("characters", "Barbarian", 0),
        tables.row("characters", "Barbarian", 1)
    );
    assert_eq!(
        tables.row("characters", "Barbarian", 999),
        tables.row("characters", "Barbarian", 12)
    );
    assert_eq!(
        csv::parse("a,b\r\n\"x,y\",\"two\"\"quotes\nnext\"\r\n").unwrap()[1],
        ["x,y", "two\"quotes\nnext"]
    );
}

#[test]
fn specs_and_numbers_match_recorded_export() {
    let source = sources();
    let catalog = wire::read(&source.root.join("rust/data/catalog.json")).unwrap();
    let reg = field(&catalog, "registry");
    let raw = wire::read(&source.root.join("data/clashking-static-data.json")).unwrap();
    let overrides = wire::read(&source.root.join("data/balance-overrides.json")).unwrap();
    let mut ck = stats::ck_entries(&raw);
    stats::apply_overrides(&mut ck, &overrides, true).unwrap();
    let csv = csv::Tables::load(&source.root).unwrap();
    for (name, value) in entries(field(&catalog, "units")) {
        let spec = specs::spec(name, field(reg, name)).unwrap();
        equivalent(&spec, field(value, "spec"));
        equivalent(&specs::summon(name, &spec), field(value, "summon_spec"));
    }
    for (key, expected) in entries(field(&catalog, "unit_numbers")) {
        let (name, level) = key.rsplit_once('|').unwrap();
        let actual = specs::unit_numbers(
            name,
            field(reg, name),
            stats::ck(reg, &ck, name),
            &csv,
            level.parse().unwrap(),
            "gamedata",
        );
        let mut errors = Vec::new();
        differences(&actual, expected, key, &mut errors);
        assert!(errors.is_empty(), "{}", errors.join("\n"));
    }
    assert!(specs::spec("Royal Ghost", &EMPTY).is_none());
    assert!(specs::spec("Battle Ram", &EMPTY).is_none());
    assert!(specs::spec("M.E.C.H.A", &EMPTY).is_none());
}

#[test]
fn synthetic_overrides_and_exact_levels() {
    let mut reg = json::parse(r#"{"Example":{"attrs":{"housing":2},"levels":[{"level":2,"hitpoints":100,"dps":10,"wiki":{"Hitpoints":"90","Damage per Second":"9","Damage per Attack":"9"}}]}}"#).unwrap();
    let changes = json::parse(r#"{"schema_version":1,"overrides":[{"entity":"Example","level":2,"field":"hitpoints","new_value":120},{"entity":"Example","level":"all","field":"movement_speed","new_value":24}]}"#).unwrap();
    stats::apply_overrides(&mut reg, &changes, false).unwrap();
    let record = field(&reg, "Example");
    assert_eq!(stats::get(record, &num(2), &["hitpoints"]), Some(120.0));
    assert_eq!(stats::get(record, &num(2), &["dps"]), Some(10.0));
    assert_eq!(field(field(record, "attrs"), "speed"), &num(3));
    assert!(stats::exact(record, &num(1)).obj().is_empty());
    assert_eq!(stats::numeric(&wire::string("−1,234.5 HP")), Some(-1234.5));
    assert_eq!(stats::numeric(&wire::string("N/A")), None);
}

#[test]
fn missing_wiki_is_explicit() {
    let result = registry::build(
        &EMPTY,
        &Path::new("/tmp").join("clash-lB-deliberately-absent-wiki"),
    );
    assert!(result.unwrap_err().contains("missing required wiki input"));
}

#[test]
#[ignore = "requires the explicit local ignored wiki mirror; see DATA_PIPELINE.md"]
fn complete_source_pipeline_matches_recorded_exports() {
    let mut sources = sources();
    sources.wiki = std::env::var_os("CLASH_CATALOG_WIKI")
        .expect("set CLASH_CATALOG_WIKI")
        .into();
    for (hash, name) in registry::wiki_inputs() {
        assert_eq!(
            wire::file_hash(&sources.wiki.join(name)).unwrap(),
            hash,
            "wiki input {name}"
        );
    }
    let registry = build_registry(&sources).unwrap();
    let serialized = encoding::registry(&registry);
    let pinned = required_text(&sources.root.join("data/registry.json")).unwrap();
    assert_eq!(
        wire::sha256(serialized.as_bytes()),
        wire::sha256(pinned.replace("\r\n", "\n").as_bytes()),
        "registry intermediate encoding"
    );
    equivalent(
        &registry,
        &wire::read(&sources.root.join("data/registry.json")).unwrap(),
    );
    let actual = build_catalog(&sources).unwrap();
    equivalent(
        &actual,
        &wire::read(&sources.root.join("rust/data/catalog.json")).unwrap(),
    );

    // Declared source perturbation: neither generated JSON exists in this root.
    // This proves the pipeline consumes sources and respects replacement totals.
    let scratch = std::env::temp_dir().join(format!(
        "clash-lB-catalog-source-proof-{}",
        std::process::id()
    ));
    struct Cleanup(PathBuf);
    impl Drop for Cleanup {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    let _cleanup = Cleanup(scratch.clone());
    std::fs::create_dir_all(scratch.join("data/gamecsv/v18.200.9")).unwrap();
    for name in [
        "clashking-static-data.json",
        "balance-overrides.json",
        "warden-weights.json",
    ] {
        std::fs::copy(
            sources.root.join("data").join(name),
            scratch.join("data").join(name),
        )
        .unwrap();
    }
    for name in [
        "buildings",
        "characters",
        "heroes",
        "pets",
        "projectiles",
        "special_abilities",
        "spells",
    ] {
        let path = format!("data/gamecsv/v18.200.9/{name}.csv");
        std::fs::copy(sources.root.join(&path), scratch.join(&path)).unwrap();
    }
    let mut overrides = wire::read(&scratch.join("data/balance-overrides.json")).unwrap();
    let Json::Arr(changes) = get_mut(&mut overrides, "overrides") else {
        unreachable!()
    };
    changes.push(
        json::parse(r#"{"entity":"Barbarian","level":1,"field":"hitpoints","new_value":77}"#)
            .unwrap(),
    );
    wire::write(&scratch.join("data/balance-overrides.json"), &overrides).unwrap();
    let changed = build_catalog(&Sources {
        root: scratch.clone(),
        wiki: sources.wiki.clone(),
    })
    .unwrap();
    assert_eq!(
        field(field(field(&changed, "unit_numbers"), "Barbarian|1"), "hp"),
        &num(77)
    );
    assert!(!scratch.join("data/registry.json").exists());
    assert!(!scratch.join("rust/data/catalog.json").exists());
}
