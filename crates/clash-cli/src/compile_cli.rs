//! Native compilation and Rust compiled-plan regression checks. Explicit saved
//! reference comparisons retain the historical wire-oracle adapter.
//!
//! Wiring (the integration owner edits lib.rs/main.rs):
//! lib.rs: `pub mod armies; pub mod compile; pub mod compile_cli;`
//! main.rs, after decoding command and paths:
//! ```ignore
//! if matches!(command, "compile" | "compile-check") {
//!     let mut compile_args = vec![PathBuf::from(command)];
//!     compile_args.extend(paths);
//!     return baselab_engine::compile_cli::main(&compile_args);
//! }
//! ```
//! `compile ID|FILE|JSON [ANGLE SEED [OUTPUT]] [--root ROOT] [--account]`
//! `compile-check [--reference FILE] [--python PYTHON] [--playbooks 0|1]`
//! `compile-check --write-reference-script PATH` writes the embedded exporter;
//! the reviewer can place it at tools/baselab/plan_reference.py. Keeping it here
//! allows this task to touch only its three assigned Rust source files.

use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::armies::{self, array, field, object, put, string};
use crate::compile::{CompileOptions, Compiler};
use crate::json::{self, Json};
use crate::plans::{flag, number, text};
use crate::stats::Stats;
pub use crate::wire::to_json;

const USAGE: &str = "compile <build-id|build.json|JSON> [angle seed [output.json]] [--root ROOT] [--catalog FILE] [--playbooks 0|1] [--account] [--overrides FILE|JSON] [--tactics FILE|JSON] | compile-check [--root ROOT] [--catalog FILE] [--reference FILE] [--python PYTHON] [--playbooks 0|1] [--write-reference-script PATH]";

struct Arguments {
    command: String,
    root: Option<PathBuf>,
    catalog: Option<PathBuf>,
    reference: Option<PathBuf>,
    python: Option<PathBuf>,
    exporter: Option<PathBuf>,
    output: Option<PathBuf>,
    angle: Option<f64>,
    seed: Option<i64>,
    options: CompileOptions,
    positional: Vec<PathBuf>,
}

fn json_argument(value: &Path) -> Result<Json, String> {
    let source = value.to_str().ok_or("Argument is not valid UTF-8")?;
    if source.trim_start().starts_with('{') || source.trim_start().starts_with('[') {
        json::parse(source).map_err(|error| error.to_string())
    } else {
        armies::read_json(value)
    }
}

fn arguments(args: &[PathBuf]) -> Result<Arguments, String> {
    let command = args
        .first()
        .and_then(|value| value.to_str())
        .ok_or(USAGE)?
        .to_owned();
    let mut options = CompileOptions::default();
    if let Ok(value) = std::env::var("BASELAB_PLAYBOOKS") {
        options.playbooks = value == "1";
    }
    let mut out = Arguments {
        command,
        root: None,
        catalog: None,
        reference: None,
        python: None,
        exporter: None,
        output: None,
        angle: None,
        seed: None,
        options,
        positional: Vec::new(),
    };
    let mut index = 1;
    while index < args.len() {
        let argument = args[index].to_str().ok_or("Argument is not valid UTF-8")?;
        if argument == "--account" {
            out.options.account = true;
            index += 1;
            continue;
        }
        if !argument.starts_with("--") {
            out.positional.push(args[index].clone());
            index += 1;
            continue;
        }
        let value = args
            .get(index + 1)
            .ok_or_else(|| format!("Missing value for {argument}"))?;
        let value_text = value.to_str().ok_or("Argument is not valid UTF-8")?;
        match argument {
            "--root" => out.root = Some(value.clone()),
            "--catalog" => out.catalog = Some(value.clone()),
            "--reference" => out.reference = Some(value.clone()),
            "--python" => out.python = Some(value.clone()),
            "--write-reference-script" => out.exporter = Some(value.clone()),
            "--output" => out.output = Some(value.clone()),
            "--angle" => out.angle = Some(value_text.parse().map_err(|_| "Invalid angle")?),
            "--seed" => out.seed = Some(value_text.parse().map_err(|_| "Invalid seed")?),
            "--playbooks" => match value_text {
                "0" => out.options.playbooks = false,
                "1" => out.options.playbooks = true,
                _ => return Err("--playbooks requires 0 or 1".to_owned()),
            },
            "--flank-offset" => {
                out.options.flank_offset = value_text.parse().map_err(|_| "Invalid flank offset")?
            }
            "--charge-side" => out.options.charge_side = Some(value_text.to_owned()),
            "--overrides" => out.options.overrides = json_argument(value)?,
            "--tactics" => {
                out.options.tactics =
                    Some(json_argument(value)?.arr().iter().map(Json::f64).collect())
            }
            _ => return Err(format!("Unknown option {argument}; {USAGE}")),
        }
        index += 2;
    }
    Ok(out)
}

pub(crate) fn repo_root(explicit: Option<&Path>) -> Result<PathBuf, String> {
    if let Some(path) = explicit {
        return Ok(path.to_owned());
    }
    if let Some(path) = std::env::var_os("BASELAB_ROOT") {
        return Ok(PathBuf::from(path));
    }
    let mut candidates = vec![std::env::current_dir().map_err(|error| error.to_string())?];
    if let Ok(executable) = std::env::current_exe() {
        candidates.push(executable);
    }
    for candidate in candidates {
        for ancestor in candidate.ancestors() {
            if ancestor.join("data").join(armies::META_FILE).exists() {
                return Ok(ancestor.to_owned());
            }
        }
    }
    Err("Cannot find repository data; pass --root ROOT or BASELAB_ROOT".to_owned())
}

/// Arguments include `compile`/`compile-check` as the first element, preserving
/// the binary's existing PathBuf argument convention (main.rs:43-49).
pub fn main(args: &[PathBuf]) -> Result<(), String> {
    let args = arguments(args)?;
    if !matches!(args.command.as_str(), "compile" | "compile-check") {
        return Err(USAGE.to_owned());
    }
    if let Some(path) = &args.exporter {
        std::fs::write(path, REFERENCE_EXPORTER)
            .map_err(|error| format!("{}: {error}", path.display()))?;
        return Ok(());
    }
    let root = repo_root(args.root.as_deref())?;
    let catalog = args
        .catalog
        .clone()
        .or_else(|| std::env::var_os("BASELAB_CATALOG").map(PathBuf::from))
        .unwrap_or_else(|| root.join("rust/data/catalog.json"));
    // Only the processed registry is needed: avoid loading all runtime tables.
    let catalog = armies::read_json(&catalog)?;
    let stats = Stats::new(field(&catalog, "registry"));
    let compiler = Compiler::load(&root, &stats)?;
    if args.command == "compile-check" {
        if args.reference.is_none() && args.python.is_none() {
            account_fixtures(&compiler)?;
            return crate::plan_golden::check(
                &root.join("fixtures/golden/plans.jsonl"),
                &compiler,
                Some(args.options.playbooks),
            );
        }
        return compile_check(&args, &compiler);
    }
    let input = args.positional.first().ok_or(USAGE)?;
    let input_text = input.to_str().ok_or("Build argument is not valid UTF-8")?;
    let build = if input.is_file() || input_text.trim_start().starts_with('{') {
        json_argument(input)?
    } else {
        compiler.library.build_by_id(input_text)?.clone()
    };
    let angle = args
        .angle
        .or_else(|| {
            args.positional
                .get(1)
                .and_then(|value| value.to_str())
                .and_then(|value| value.parse().ok())
        })
        .unwrap_or(0.0);
    let seed = args
        .seed
        .or_else(|| {
            args.positional
                .get(2)
                .and_then(|value| value.to_str())
                .and_then(|value| value.parse().ok())
        })
        .unwrap_or(0);
    if args.positional.len() > 4 {
        return Err(USAGE.to_owned());
    }
    for (index, kind) in [(1, "angle"), (2, "seed")] {
        if let Some(value) = args.positional.get(index) {
            let valid = if index == 1 {
                value
                    .to_str()
                    .is_some_and(|value| value.parse::<f64>().is_ok())
            } else {
                value
                    .to_str()
                    .is_some_and(|value| value.parse::<i64>().is_ok())
            };
            if !valid {
                return Err(format!("Invalid positional {kind}"));
            }
        }
    }
    let plan = compiler.compile(&build, angle, seed, &args.options)?;
    let output = args.output.as_ref().or_else(|| args.positional.get(3));
    let mut serialized = to_json(&plan);
    serialized.push('\n');
    if let Some(path) = output {
        std::fs::write(path, serialized).map_err(|error| format!("{}: {error}", path.display()))?;
    } else {
        io::stdout()
            .lock()
            .write_all(serialized.as_bytes())
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

/// Dictionary order is unspecified in plans.py:549-552's set union. Compare
/// keys by name, arrays in order, and floating-point values by all 64 bits.
pub fn first_difference(native: &Json, reference: &Json, path: &str) -> Option<String> {
    match (native, reference) {
        (Json::Obj(left), Json::Obj(right)) => {
            for (key, value) in right {
                let next = format!("{path}[{}]", to_json(&string(key)));
                let Some(other) = left
                    .iter()
                    .find(|(name, _)| name == key)
                    .map(|(_, value)| value)
                else {
                    return Some(format!("{next}: missing native field"));
                };
                if let Some(difference) = first_difference(other, value, &next) {
                    return Some(difference);
                }
            }
            for (key, _) in left {
                if !right.iter().any(|(name, _)| name == key) {
                    return Some(format!(
                        "{path}[{}]: unexpected native field",
                        to_json(&string(key))
                    ));
                }
            }
            None
        }
        (Json::Arr(left), Json::Arr(right)) => {
            for (index, (left, right)) in left.iter().zip(right).enumerate() {
                if let Some(difference) = first_difference(left, right, &format!("{path}[{index}]"))
                {
                    return Some(difference);
                }
            }
            (left.len() != right.len()).then(|| {
                format!(
                    "{path}.length: native={} reference={}",
                    left.len(),
                    right.len()
                )
            })
        }
        (Json::Num(left), Json::Num(right)) if left.to_bits() != right.to_bits() => Some(format!(
            "{path}: native={} ({:016x}) reference={} ({:016x})",
            crate::trace::py_float_repr(*left),
            left.to_bits(),
            crate::trace::py_float_repr(*right),
            right.to_bits()
        )),
        _ if native != reference => Some(format!(
            "{path}: native={} reference={}",
            to_json(native),
            to_json(reference)
        )),
        _ => None,
    }
}

fn reference(args: &Arguments, compiler: &Compiler<'_>) -> Result<Json, String> {
    if let Some(path) = &args.reference {
        return armies::read_json(path);
    }
    let python = args
        .python
        .clone()
        .or_else(|| std::env::var_os("BASELAB_PYTHON").map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from(if cfg!(windows) { "python" } else { "python3" }));
    let exporter = compiler
        .library
        .root
        .join("tools/baselab/plan_reference.py");
    let mut command = Command::new(python);
    command.arg("-B");
    if exporter.exists() {
        command.arg(exporter);
    } else {
        command.arg("-c").arg(REFERENCE_EXPORTER);
    }
    let output = command
        .arg("--root")
        .arg(&compiler.library.root)
        .arg("--playbooks")
        .arg(if args.options.playbooks { "1" } else { "0" })
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .output()
        .map_err(|error| {
            format!("Reference exporter: {error}; use --python PYTHON or --reference FILE")
        })?;
    if !output.status.success() {
        return Err(format!(
            "Reference exporter failed: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }
    let output = std::str::from_utf8(&output.stdout).map_err(|error| error.to_string())?;
    json::parse(output.trim_start_matches('\u{feff}')).map_err(|error| error.to_string())
}

pub(crate) fn case_options(case: &Json, playbooks: bool) -> CompileOptions {
    let mut options = CompileOptions {
        playbooks,
        ..CompileOptions::default()
    };
    if let Some(value) = case.get("options") {
        options.overrides = value.get("overrides").cloned().unwrap_or_else(object);
        options.tactics = value
            .get("tactics")
            .map(|values| values.arr().iter().map(Json::f64).collect());
        options.flank_offset = number(value, "flank_offset", 0.9);
        options.charge_side = value
            .get("charge_side")
            .and_then(Json::opt_str)
            .map(str::to_owned);
    }
    options
}

pub(crate) fn outcome(
    compiler: &Compiler<'_>,
    build: &Json,
    case: &Json,
    options: &CompileOptions,
) -> Json {
    let mut out = object();
    match compiler.plan_for_build(
        build,
        case.at("angle").f64(),
        case.at("seed").i64(),
        options,
    ) {
        Err(error) => {
            put(&mut out, "error", string(&error));
        }
        Ok(mut plan) => {
            if let Some(overrides) = case.get("plan_overrides") {
                for (key, value) in overrides.obj() {
                    put(&mut plan, key, value.clone());
                }
            }
            let problems = compiler.legal(&plan);
            let error = compiler.require_legal(&mut plan).err();
            put(&mut out, "plan", plan);
            put(
                &mut out,
                "legal",
                array(problems.iter().map(|problem| string(problem))),
            );
            put(
                &mut out,
                "error",
                error.as_deref().map_or(Json::Null, string),
            );
        }
    }
    out
}

fn compile_check(args: &Arguments, compiler: &Compiler<'_>) -> Result<(), String> {
    let account_fixtures = account_fixtures(compiler)?;
    let reference = reference(args, compiler)?;
    if number(&reference, "schema_version", 0.0) != 1.0 {
        return Err("Unsupported plan-reference schema".to_owned());
    }
    if flag(&reference, "playbooks") != args.options.playbooks {
        return Err("Reference playbook mode differs; pass matching --playbooks 0|1".to_owned());
    }
    let cases = reference.at("cases").arr();
    let angles = [
        0.0,
        std::f64::consts::PI / 2.0,
        std::f64::consts::PI,
        3.0 * std::f64::consts::PI / 2.0,
    ];
    // Require complete coverage even when supplied a hand-edited reference.
    for build in &compiler.library.builds {
        for angle in angles {
            for seed in [0, 1] {
                let matches = cases
                    .iter()
                    .filter(|case| {
                        text(case, "library", "") == build.library
                            && text(case, "id", "") == build.id
                            && case.at("angle").f64().to_bits() == angle.to_bits()
                            && case.at("seed").i64() == seed
                    })
                    .count();
                if matches != 1 {
                    return Err(format!("Reference must contain exactly one case for {} angle={angle} seed={seed} (found {matches})", build.id));
                }
            }
        }
    }
    let mut failures = 0;
    let mut illegal = 0;
    for case in cases {
        let id = case.at("id").str();
        let entry = compiler
            .library
            .builds
            .iter()
            .find(|build| build.id == id && build.library == text(case, "library", ""));
        let build = if text(case, "library", "") == "fixtures" {
            case.at("build")
        } else {
            &entry
                .ok_or_else(|| format!("Unknown reference build {id}"))?
                .value
        };
        let mut difference = first_difference(build, case.at("build"), "build");
        let native = outcome(
            compiler,
            build,
            case,
            &case_options(case, args.options.playbooks),
        );
        if difference.is_none() {
            difference = first_difference(&native, case.at("outcome"), "outcome");
        }
        if !native.at("error").is_null() {
            illegal += 1;
        }
        if let Some(difference) = difference {
            failures += 1;
            println!(
                "FAIL {id} angle={} seed={}: {difference}",
                crate::trace::py_float_repr(case.at("angle").f64()),
                case.at("seed").i64()
            );
        }
    }
    println!("compile-check: cases={} matched={} differing={} rejected={} libraries={} builds={} angles=4 seeds=2 account_fixtures={account_fixtures}", cases.len(), cases.len() - failures, failures, illegal, 3, compiler.library.builds.len());
    if failures > 0 {
        Err(format!("{failures} native plan cases differ"))
    } else {
        Ok(())
    }
}

// Account admission has stricter requirements than the replay oracle. Exercise
// them here, alongside reference parity, without creating separate test files.
fn account_fixtures(compiler: &Compiler<'_>) -> Result<usize, String> {
    let source = compiler
        .library
        .build_by_id("custom:user-fireball-warden")?;
    let options = CompileOptions {
        account: true,
        ..CompileOptions::default()
    };
    let baseline = compiler.plan_for_build(source, 0.0, 0, &options)?;
    let problems = compiler.account_legal(source, &baseline);
    if !problems.is_empty() {
        return Err(format!("Account fixture baseline: {}", problems.join("; ")));
    }
    let cases = [
        ("troops", "Archer", 1.0, "account camp 321 > 320"),
        ("cc", "Archer", 1.0, "account cc 51 > 50"),
        ("spells", "Freeze Spell", 1.0, "account spells 12 > 11"),
        (
            "troops",
            "Meteor Golem",
            1.0,
            "Meteor Golem requires Barracks level 19",
        ),
        ("cc", "Battle Blimp", 1.0, "account siege 2 > 1"),
    ];
    for (stock, name, amount, expected) in cases {
        let mut build = source.clone();
        let mut inventory = field(&build, stock);
        let count = number(&inventory, name, 0.0) + amount;
        put(&mut inventory, name, Json::Num(count));
        put(&mut build, stock, inventory);
        let plan = compiler.plan_for_build(&build, 0.0, 0, &options)?;
        let problems = compiler.account_legal(&build, &plan);
        if !problems.iter().any(|problem| problem.starts_with(expected)) {
            return Err(format!(
                "Account fixture {name}: expected {expected}; got {}",
                problems.join("; ")
            ));
        }
    }
    for (key, name, expected) in [
        (
            "equipment",
            "Meteor Staff",
            "Account does not own Meteor Staff",
        ),
        ("pet", "Greedy Raven", "Account does not own Greedy Raven"),
    ] {
        let mut plan = baseline.clone();
        let mut loadouts = field(&plan, "loadouts");
        let mut queen = field(&loadouts, "Archer Queen");
        let value = if key == "equipment" {
            array([string(name)])
        } else {
            string(name)
        };
        put(&mut queen, key, value);
        put(&mut loadouts, "Archer Queen", queen);
        put(&mut plan, "loadouts", loadouts);
        let problems = compiler.account_legal(source, &plan);
        if !problems.iter().any(|problem| problem == expected) {
            return Err(format!("Account fixture {key}: expected {expected}"));
        }
    }
    Ok(8)
}

/// Standalone exporter, deliberately embedded to respect this task's write
/// boundary. It imports the actual Python constructors, not a second port.
pub const REFERENCE_EXPORTER: &str = r#""""Export Python construction/legality fixtures for baselab-engine compile-check.

python -B tools/baselab/plan_reference.py --root REPO --output plans.json
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import sys
import warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--playbooks", choices=("0", "1"), default="1")
    args = parser.parse_args()
    root = args.root.resolve()
    if (
        not (root / "src" / "baselab").is_dir()
        and (root.parent / "src" / "baselab").is_dir()
    ):
        root = root.parent
    sys.path.insert(0, str(root / "src"))
    os.environ["BASELAB_PLAYBOOKS"] = args.playbooks
    from baselab import meta_armies
    from baselab.rust_bridge import dump

    rows = []
    count = len(json.loads(meta_armies.DATA.read_text(encoding="utf-8"))["builds"])
    for index, build in enumerate(meta_armies.data()["builds"]):
        library = meta_armies.DATA.name if index < count else "observed-armies.json"
        bid = f"{build['archetype']}-{build['th']}-{build['build']}"
        rows.append((library, bid, build))
    for build in meta_armies.custom()["builds"]:
        rows.append(("custom-armies.json", "custom:" + build["archetype"], build))

    def export_case(
        library, bid, build, angle, seed, options=None, plan_overrides=None
    ):
        case = {
            "library": library,
            "id": bid,
            "build": copy.deepcopy(build),
            "angle": angle,
            "seed": seed,
        }
        options = options or {}
        if options:
            # tactics.py:144-153 rejects the nondefault generic knob used by
            # the next fixture. Snapshot the vector before that fixture edits it.
            case["options"] = copy.deepcopy(options)
        if plan_overrides:
            case["plan_overrides"] = plan_overrides
        try:
            family = meta_armies.family_of(build) if args.playbooks == "1" else None
            pb = meta_armies._playbook(family) if family else None
            if pb is not None:
                from baselab.engine.playbook import from_playbook

                plan = from_playbook(
                    pb,
                    build=build,
                    angle=angle,
                    seed=seed,
                    flank_offset=options.get("flank_offset", 0.9),
                    charge_side=options.get(
                        "charge_side", "left" if seed % 2 == 0 else "right"
                    ),
                    overrides=options.get("overrides"),
                )
            else:
                plan = meta_armies.compose(build, angle=angle, seed=seed)
            if "tactics" in options:
                from baselab.tactics import apply

                apply(plan, options["tactics"])
            for key, value in (plan_overrides or {}).items():
                setattr(plan, key, copy.deepcopy(value))
            problems = plan.legal()
            error = None
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    plan.require_legal()
            except (KeyError, TypeError, ValueError) as exc:
                error = str(exc)
            case["outcome"] = {"plan": dump(plan), "legal": problems, "error": error}
        except (KeyError, TypeError, ValueError) as exc:
            case["outcome"] = {"error": str(exc)}
        return case

    cases = []
    for library, bid, build in rows:
        for angle in (0.0, math.pi / 2.0, math.pi, 3.0 * math.pi / 2.0):
            for seed in (0, 1):
                cases.append(export_case(library, bid, build, angle, seed))

    # Verification fixtures live in this CLI, not separate test files. Include
    # illegal inputs and every family's roster substitutions/variant controls.
    seen = set()
    for _, bid, build in rows:
        family = meta_armies.family_of(build)
        if family is None or family in seen:
            continue
        seen.add(family)
        replacement = copy.deepcopy(build)
        for old, new in (
            ("Barbarian King", "Royal Champion"),
            ("Archer Queen", "Minion Prince"),
        ):
            if old in replacement["heroes"] and new not in replacement["heroes"]:
                replacement["heroes"] = [
                    new if hero == old else hero for hero in replacement["heroes"]
                ]
                for role in ("funnel", "push"):
                    if role in replacement:
                        replacement[role] = [
                            new if hero == old else hero for hero in replacement[role]
                        ]
        cases.append(export_case("fixtures", "roster-" + family, replacement, 0.37, 1))
        pb = meta_armies._playbook(family)
        if pb is None:
            continue
        for variant in pb.get("variants", []):
            options = {"overrides": {"__variants__": {"names": [variant["name"]]}}}
            cases.append(
                export_case(
                    "fixtures",
                    family + ":variant:" + variant["name"],
                    build,
                    0.37,
                    1,
                    options,
                )
            )
        if pb.get("steps"):
            options = {
                "overrides": {
                    pb["steps"][0]["id"]: {
                        "at": "edge:right",
                        "aim": None,
                        "delay": 0.37,
                    },
                    "__opening__": {"snipe_mode": "off", "snipe_exposed": False},
                }
            }
            cases.append(
                export_case("fixtures", "overrides-" + family, build, 0.37, 1, options)
            )
        if args.playbooks == "1":
            tactics = [
                7.0,
                1.3,
                0.0,
                0.0,
                0.8,
                1.2,
                8.0,
                10.0,
                0.0,
                6.0,
                2.3,
                0.0,
                0.0,
                0.0,
                0.0,
                0.35,
                25.0,
                0.0,
                0.0,
            ]
            cases.append(
                export_case(
                    "fixtures",
                    "tactics-" + family,
                    build,
                    0.37,
                    1,
                    {"tactics": tactics},
                )
            )
            tactics[2] = 1.0
            cases.append(
                export_case(
                    "fixtures",
                    "unsupported-tactics-" + family,
                    build,
                    0.37,
                    1,
                    {"tactics": tactics},
                )
            )

    base = copy.deepcopy(rows[0][2])
    five = copy.deepcopy(base)
    five["heroes"].append("Minion Prince")
    cases.append(export_case("fixtures", "five-hero-slots", five, 0.0, 0))
    boosts = copy.deepcopy(base)
    boosts["troops"].update({"Super Minion": 1, "Super Bowler": 1, "Super Dragon": 1})
    cases.append(export_case("fixtures", "three-super-boosts", boosts, 0.0, 0))
    duplicate = copy.deepcopy(base)
    duplicate["heroes"].append(duplicate["heroes"][0])
    cases.append(export_case("fixtures", "duplicate-build-hero", duplicate, 0.0, 0))
    equipment = copy.deepcopy(base)
    equipment["loadouts"] = {
        "Archer Queen": ["Rocket Spear", "Rocket Spear", "Spirit Fox"]
    }
    cases.append(
        export_case("fixtures", "equipment-owner-duplicate-pet", equipment, 0.0, 0)
    )
    cases.append(
        export_case(
            "fixtures",
            "unknown-spell-event",
            base,
            0.0,
            0,
            plan_overrides={"spell_levels": {"Yellow Card": 1}},
        )
    )
    cases.append(
        export_case(
            "fixtures",
            "donation-level-cap",
            base,
            0.0,
            0,
            plan_overrides={"cc_spell_levels": {"Rage Spell": 999}},
        )
    )
    result = {
        "schema_version": 1,
        "playbooks": args.playbooks == "1",
        "gaps": os.environ.get("BASELAB_GAPS", "1"),
        "pace": float(os.environ.get("BASELAB_PACE", "1.0")),
        "cases": cases,
    }
    serialized = json.dumps(result, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        sys.stdout.write(serialized)


if __name__ == "__main__":
    main()
"#;
