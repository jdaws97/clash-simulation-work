//! Rust compiler regression oracle. Inputs and complete plans are stored together
//! so source/library changes and fitter changes both require explicit review.

use std::collections::HashSet;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};

use crate::armies::{array, field, list, put, string};
use crate::compile::Compiler;
use crate::compile_cli::{case_options, first_difference, outcome, to_json};
use crate::json::{self, Json};
use crate::plans::{flag, text};
use crate::stats::Stats;

const USAGE: &str = "golden plans record|check [plans.jsonl] [--root ROOT]";

pub fn command(args: &[PathBuf], stats: &Stats) -> Result<(), String> {
    let mode = args.first().and_then(|value| value.to_str()).ok_or(USAGE)?;
    if !matches!(mode, "record" | "check") {
        return Err(USAGE.to_owned());
    }
    let mut root = None;
    let mut path = None;
    let mut index = 1;
    while index < args.len() {
        if args[index].as_os_str() == "--root" {
            root = Some(args.get(index + 1).ok_or(USAGE)?.clone());
            index += 2;
        } else if path.is_none() {
            path = Some(args[index].clone());
            index += 1;
        } else {
            return Err(USAGE.to_owned());
        }
    }
    let root = crate::compile_cli::repo_root(root.as_deref())?;
    let path = path.unwrap_or_else(|| root.join("fixtures/golden/plans.jsonl"));
    let compiler = Compiler::load(&root, stats)?;
    if mode == "check" {
        return check(&path, &compiler, None);
    }
    let temporary = path.with_extension("jsonl.tmp");
    let file = std::fs::File::create(&temporary).map_err(|error| error.to_string())?;
    let mut writer = BufWriter::new(file);
    let cases = cases(&compiler);
    for case in &cases {
        let row = evaluate(&compiler, case);
        writeln!(writer, "{}", to_json(&row)).map_err(|error| error.to_string())?;
    }
    writer.flush().map_err(|error| error.to_string())?;
    std::fs::rename(&temporary, &path).map_err(|error| error.to_string())?;
    println!(
        "golden plans record: cases={} path={}",
        cases.len(),
        path.display()
    );
    Ok(())
}

fn fixture(id: &str, build: &Json, angle: f64, seed: i64) -> Json {
    Json::Obj(vec![
        ("id".to_owned(), string(id)),
        ("build".to_owned(), build.clone()),
        ("angle".to_owned(), Json::Num(angle)),
        ("seed".to_owned(), Json::Num(seed as f64)),
    ])
}

fn variant_options(names: impl IntoIterator<Item = Json>) -> Json {
    Json::Obj(vec![(
        "overrides".to_owned(),
        Json::Obj(vec![(
            "__variants__".to_owned(),
            Json::Obj(vec![("names".to_owned(), array(names))]),
        )]),
    )])
}

fn cases(compiler: &Compiler<'_>) -> Vec<Json> {
    let mut out = Vec::new();
    for playbooks in [false, true] {
        let mut fixtures = Vec::new();
        for entry in &compiler.library.builds {
            let id = format!("{}:{}", entry.library, entry.id);
            for angle in [
                0.0,
                std::f64::consts::FRAC_PI_2,
                std::f64::consts::PI,
                3.0 * std::f64::consts::FRAC_PI_2,
            ] {
                for seed in [0, 1] {
                    fixtures.push(fixture(&id, &entry.value, angle, seed));
                }
            }
        }
        let mut seen = HashSet::new();
        for entry in &compiler.library.builds {
            let Some(family) = crate::armies::family_of(&entry.value) else {
                continue;
            };
            if !seen.insert(family) {
                continue;
            }
            let mut roster = entry.value.clone();
            let mut heroes = list(&roster, "heroes").to_vec();
            for (old, new) in [
                ("Barbarian King", "Royal Champion"),
                ("Archer Queen", "Minion Prince"),
            ] {
                if heroes.contains(&string(old)) && !heroes.contains(&string(new)) {
                    for hero in &mut heroes {
                        if *hero == string(old) {
                            *hero = string(new);
                        }
                    }
                    for key in ["funnel", "push"] {
                        if roster.get(key).is_some() {
                            let values = list(&roster, key)
                                .iter()
                                .map(|hero| {
                                    if *hero == string(old) {
                                        string(new)
                                    } else {
                                        hero.clone()
                                    }
                                })
                                .collect::<Vec<_>>();
                            put(&mut roster, key, array(values));
                        }
                    }
                }
            }
            put(&mut roster, "heroes", array(heroes));
            fixtures.push(fixture(&format!("roster-{family}"), &roster, 0.37, 1));
            let Some((_, book)) = compiler.playbooks.iter().find(|(name, _)| name == family) else {
                continue;
            };
            for variant in list(book, "variants") {
                let mut case = fixture(
                    &format!("{family}:variant:{}", text(variant, "name", "")),
                    &entry.value,
                    0.37,
                    1,
                );
                put(
                    &mut case,
                    "options",
                    variant_options([field(variant, "name")]),
                );
                fixtures.push(case);
                if !list(variant, "steps").is_empty() {
                    let mut recipe_build = entry.value.clone();
                    put(&mut recipe_build, "recipe", field(variant, "name"));
                    fixtures.push(fixture(
                        &format!("{family}:recipe:{}", text(variant, "name", "")),
                        &recipe_build,
                        0.37,
                        1,
                    ));
                }
            }
            if let Some(step) = list(book, "steps").first() {
                let mut case = fixture(&format!("overrides-{family}"), &entry.value, 0.37, 1);
                let overrides = Json::Obj(vec![
                    (
                        text(step, "id", "").to_owned(),
                        Json::Obj(vec![
                            ("at".to_owned(), string("edge:right")),
                            ("aim".to_owned(), Json::Null),
                            ("delay".to_owned(), Json::Num(0.37)),
                        ]),
                    ),
                    (
                        "__opening__".to_owned(),
                        Json::Obj(vec![
                            ("snipe_mode".to_owned(), string("off")),
                            ("snipe_exposed".to_owned(), Json::Bool(false)),
                        ]),
                    ),
                ]);
                put(
                    &mut case,
                    "options",
                    Json::Obj(vec![("overrides".to_owned(), overrides)]),
                );
                fixtures.push(case);
            }
            if playbooks {
                let mut tactics = vec![
                    7.0, 1.3, 0.0, 0.0, 0.8, 1.2, 8.0, 10.0, 0.0, 6.0, 2.3, 0.0, 0.0, 0.0, 0.0,
                    0.35, 25.0, 0.0, 0.0,
                ];
                for unsupported in [false, true] {
                    tactics[2] = if unsupported { 1.0 } else { 0.0 };
                    let prefix = if unsupported {
                        "unsupported-tactics"
                    } else {
                        "tactics"
                    };
                    let mut case = fixture(&format!("{prefix}-{family}"), &entry.value, 0.37, 1);
                    put(
                        &mut case,
                        "options",
                        Json::Obj(vec![(
                            "tactics".to_owned(),
                            array(tactics.iter().copied().map(Json::Num)),
                        )]),
                    );
                    fixtures.push(case);
                }
            }
        }
        if let Some(entry) = compiler.library.builds.first() {
            let mut build = entry.value.clone();
            let mut heroes = list(&build, "heroes").to_vec();
            heroes.push(string("Minion Prince"));
            put(&mut build, "heroes", array(heroes));
            fixtures.push(fixture("five-hero-slots", &build, 0.0, 0));
            let mut build = entry.value.clone();
            let mut troops = field(&build, "troops");
            for name in ["Super Minion", "Super Bowler", "Super Dragon"] {
                put(&mut troops, name, Json::Num(1.0));
            }
            put(&mut build, "troops", troops);
            fixtures.push(fixture("three-super-boosts", &build, 0.0, 0));
            let mut build = entry.value.clone();
            let mut heroes = list(&build, "heroes").to_vec();
            heroes.push(heroes[0].clone());
            put(&mut build, "heroes", array(heroes));
            fixtures.push(fixture("duplicate-build-hero", &build, 0.0, 0));
            let mut build = entry.value.clone();
            put(
                &mut build,
                "loadouts",
                Json::Obj(vec![(
                    "Archer Queen".to_owned(),
                    array([
                        string("Rocket Spear"),
                        string("Rocket Spear"),
                        string("Spirit Fox"),
                    ]),
                )]),
            );
            fixtures.push(fixture("equipment-owner-duplicate-pet", &build, 0.0, 0));
            for (id, key, name, level) in [
                ("unknown-spell-event", "spell_levels", "Yellow Card", 1.0),
                ("donation-level-cap", "cc_spell_levels", "Rage Spell", 999.0),
            ] {
                let mut case = fixture(id, &entry.value, 0.0, 0);
                put(
                    &mut case,
                    "plan_overrides",
                    Json::Obj(vec![(
                        key.to_owned(),
                        Json::Obj(vec![(name.to_owned(), Json::Num(level))]),
                    )]),
                );
                fixtures.push(case);
            }
        }
        for case in fixtures {
            out.push(Json::Obj(vec![
                ("schema".to_owned(), Json::Num(1.0)),
                ("synthetic".to_owned(), Json::Bool(true)),
                ("playbooks".to_owned(), Json::Bool(playbooks)),
                ("case".to_owned(), case),
            ]));
        }
    }
    out
}

fn evaluate(compiler: &Compiler<'_>, case: &Json) -> Json {
    let mut row = case.clone();
    let fixture = case.at("case");
    let options = case_options(fixture, flag(case, "playbooks"));
    put(
        &mut row,
        "outcome",
        outcome(compiler, fixture.at("build"), fixture, &options),
    );
    row
}

pub fn check(path: &Path, compiler: &Compiler<'_>, playbooks: Option<bool>) -> Result<(), String> {
    let file = std::fs::File::open(path).map_err(|error| {
        format!(
            "{}: {error}; record with golden plans record",
            path.display()
        )
    })?;
    let mut expected = Vec::new();
    for (index, line) in BufReader::new(file).lines().enumerate() {
        let line = line.map_err(|error| error.to_string())?;
        let row = json::parse(&line)
            .map_err(|error| format!("{}:{}: {error}", path.display(), index + 1))?;
        if row.get("schema") != Some(&Json::Num(1.0))
            || row.get("synthetic") != Some(&Json::Bool(true))
            || !matches!(row.get("playbooks"), Some(Json::Bool(_)))
            || !matches!(row.get("case"), Some(Json::Obj(_)))
            || !matches!(row.get("outcome"), Some(Json::Obj(_)))
        {
            return Err(format!("Invalid plan golden row {}", index + 1));
        }
        if playbooks.is_none_or(|mode| mode == flag(&row, "playbooks")) {
            expected.push(row);
        }
    }
    let cases = cases(compiler)
        .into_iter()
        .filter(|case| playbooks.is_none_or(|mode| mode == flag(case, "playbooks")))
        .collect::<Vec<_>>();
    if expected.len() != cases.len() || cases.is_empty() {
        return Err(format!(
            "Plan golden coverage differs: expected={} current={}",
            expected.len(),
            cases.len()
        ));
    }
    let mut failures = 0;
    for (case, expected) in cases.iter().zip(&expected) {
        let actual = evaluate(compiler, case);
        if let Some(difference) = first_difference(&actual, expected, "plan_golden") {
            failures += 1;
            println!(
                "FAIL playbooks={} {} angle={} seed={}: {difference}",
                flag(case, "playbooks"),
                text(case.at("case"), "id", ""),
                case.at("case").at("angle").f64(),
                case.at("case").at("seed").i64()
            );
        }
    }
    println!(
        "golden plans check: cases={} passed={} failed={failures}",
        cases.len(),
        cases.len() - failures
    );
    if failures == 0 {
        Ok(())
    } else {
        Err(format!("{failures} Rust compiled plans differ"))
    }
}
