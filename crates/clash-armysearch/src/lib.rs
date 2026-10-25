//! Native account army search. See output/rustfirst/b-armysearch.out for design.
//! No Python, subprocess battle runner, external crates, or replay exemptions.
//!
//! Integration owner: add `pub mod armysearch;` to lib.rs. After main.rs has
//! decoded `command` and collected `paths`, add:
//! ```ignore
//! if matches!(command, "armysearch" | "armysearch-proof") {
//!     let mut search_args = vec![PathBuf::from(command)];
//!     search_args.extend(paths);
//!     return baselab_engine::armysearch::main(&search_args);
//! }
//! ```

pub mod account;
pub mod eval;
pub mod genome;
pub mod novelty;
pub mod operators;
pub mod program;
pub mod proof;
pub mod report;
pub mod score;
pub mod search;
pub mod themed;
mod util;

pub use self::util::Random as SearchRandom;

use std::path::{Path, PathBuf};
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::compile::Compiler;
use crate::json::Json;

use self::account::AccountRules;
use self::eval::NativeEvaluator;
use self::score::{Stage, TargetManifest};
use self::search::{Families, Objective, ProposalSettings, SearchState};
use self::util::{encode, hash, number, object, string, write};

const USAGE: &str = concat!(
    "usage: baselab-engine armysearch [--manifest M.json] --out DIR ",
    "--batches N --batch K --seed S --threads T [--quick-budget Q ",
    "--confirm-budget C --top N --resume checkpoint.json ",
    "--objective ranked|stars|destruction --holdout-budget H ",
    "--themed-fraction 0.25 --random-fraction 0.05 ",
    "--families all|playbook|generic --programs on|off ",
    "--program-mutation-rate 0.5 --account ACCOUNT.json --root REPO --catalog C.json]\n",
    "       baselab-engine armysearch-proof [--manifest M.json --fuzz 4096 ",
    "--out DIR --root REPO --catalog C.json]\n",
    "Budgets are per-candidate battle ceilings. Minimum coverage is two sides per base. ",
    "Holdout defaults to 8 sides x 16 fresh seed groups per base. ",
    "Frozen finalists also receive a fresh-seed pass on the search bases at the confirmation budget. ",
    "Immigrant fractions are in [0,1], sum to at most 1, and reserve nearest-whole ",
    "slots in every batch before seeds/offspring. Families default to all. ",
    "Playbook-only mode uses compatible seeds/offspring for every slot. ",
    "Programs default to on; program mutation rate is the fraction of offspring ",
    "attempts devoted to program mutation/crossover (default 0.5).",
);

#[derive(Clone, Debug)]
pub struct Config {
    pub root: PathBuf,
    pub catalog: PathBuf,
    pub account: Option<PathBuf>,
    pub manifest: Option<PathBuf>,
    pub out: PathBuf,
    pub batches: usize,
    pub batch: usize,
    pub seed: u64,
    pub threads: usize,
    pub quick_budget: usize,
    pub confirm_budget: usize,
    pub holdout_budget: Option<usize>,
    pub top: usize,
    pub objective: Objective,
    pub resume: Option<PathBuf>,
    pub fuzz: usize,
    pub proposals: ProposalSettings,
}

fn find_root() -> Result<PathBuf, String> {
    let current = std::env::current_dir().map_err(|error| error.to_string())?;
    for directory in current.ancestors() {
        if directory.join("data/your-levels.json").exists() && directory.join("Cargo.toml").exists()
        {
            return Ok(directory.to_owned());
        }
    }
    let executable = std::env::current_exe().map_err(|error| error.to_string())?;
    for directory in executable.ancestors().skip(1) {
        if directory.join("data/your-levels.json").exists() && directory.join("Cargo.toml").exists()
        {
            return Ok(directory.to_owned());
        }
    }
    Err("repository root not found; pass --root REPO".to_owned())
}

impl Config {
    pub fn parse(args: &[PathBuf]) -> Result<Self, String> {
        let argument = |name: &str| -> Option<&PathBuf> {
            args.windows(2)
                .find(|pair| pair[0] == Path::new(name))
                .map(|pair| &pair[1])
        };
        let root = argument("--root")
            .cloned()
            .map(Ok)
            .unwrap_or_else(find_root)?;
        let root = root.canonicalize().map_err(|error| error.to_string())?;
        let parse = |name: &str, default: usize| -> Result<usize, String> {
            argument(name).map_or(Ok(default), |value| {
                value
                    .to_str()
                    .ok_or("non-UTF8 number")?
                    .parse::<usize>()
                    .map_err(|_| format!("invalid {name}"))
            })
        };
        let mut index = 0;
        while index < args.len() {
            let key = args[index].to_str().ok_or("non-UTF8 option")?;
            if !matches!(
                key,
                "--root"
                    | "--catalog"
                    | "--account"
                    | "--manifest"
                    | "--out"
                    | "--batches"
                    | "--batch"
                    | "--seed"
                    | "--threads"
                    | "--quick-budget"
                    | "--confirm-budget"
                    | "--top"
                    | "--resume"
                    | "--objective"
                    | "--holdout-budget"
                    | "--fuzz"
                    | "--themed-fraction"
                    | "--random-fraction"
                    | "--families"
                    | "--programs"
                    | "--program-mutation-rate"
            ) {
                return Err(format!("unknown option {key}\n{USAGE}"));
            }
            if index + 1 == args.len() {
                return Err(format!("missing value for {key}"));
            }
            if args[..index].iter().any(|prior| prior == &args[index]) {
                return Err(format!("duplicate option {key}"));
            }
            index += 2;
        }
        let seed = argument("--seed").map_or(Ok(20261024), |value| {
            value
                .to_str()
                .ok_or("non-UTF8 seed")?
                .parse::<u64>()
                .map_err(|_| "invalid --seed")
        })?;
        let objective = Objective::parse(
            argument("--objective")
                .and_then(|value| value.to_str())
                .unwrap_or("ranked"),
        )?;
        let fraction = |name: &str, default: f64| -> Result<f64, String> {
            argument(name).map_or(Ok(default), |value| {
                value
                    .to_str()
                    .ok_or("non-UTF8 fraction")?
                    .parse::<f64>()
                    .map_err(|_| format!("invalid {name}"))
            })
        };
        let proposals = ProposalSettings {
            themed_fraction: fraction("--themed-fraction", 0.25)?,
            random_fraction: fraction("--random-fraction", 0.05)?,
            families: Families::parse(
                argument("--families")
                    .map(|value| value.to_str().ok_or("non-UTF8 families"))
                    .transpose()?
                    .unwrap_or("all"),
            )?,
            programs: match argument("--programs")
                .map(|value| value.to_str().ok_or("non-UTF8 programs"))
                .transpose()?
                .unwrap_or("on")
            {
                "on" => true,
                "off" => false,
                _ => return Err("--programs must be on or off".to_owned()),
            },
            program_mutation_rate: fraction("--program-mutation-rate", 0.5)?,
        };
        proposals.validate()?;
        let config = Self {
            catalog: argument("--catalog")
                .cloned()
                .unwrap_or_else(|| root.join("rust/data/catalog.json")),
            manifest: argument("--manifest").cloned(),
            account: argument("--account").cloned(),
            out: argument("--out")
                .cloned()
                .unwrap_or_else(|| root.join("rust/output/armysearch")),
            batches: parse("--batches", 16)?,
            batch: parse("--batch", 32)?,
            seed,
            threads: parse(
                "--threads",
                std::thread::available_parallelism().map_or(1, |count| count.get()),
            )?,
            quick_budget: parse("--quick-budget", 96)?,
            confirm_budget: parse("--confirm-budget", 384)?,
            holdout_budget: argument("--holdout-budget")
                .map(|_| parse("--holdout-budget", 0))
                .transpose()?,
            top: parse("--top", 8)?,
            objective,
            resume: argument("--resume").cloned(),
            fuzz: parse("--fuzz", 4096)?,
            proposals,
            root,
        };
        if config.batches == 0 || config.batch == 0 || config.threads == 0 || config.top == 0 {
            return Err("batches, batch, threads, and top must be positive".to_owned());
        }
        Ok(config)
    }

    pub fn identity_settings(&self) -> Json {
        object([
            ("seed", string(self.seed.to_string())),
            ("batch", number(self.batch)),
            ("quick_budget", number(self.quick_budget)),
            ("confirm_budget", number(self.confirm_budget)),
            ("objective", string(self.objective.name())),
            ("themed_fraction", Json::Num(self.proposals.themed_fraction)),
            ("random_fraction", Json::Num(self.proposals.random_fraction)),
            ("families", string(self.proposals.families.name())),
            ("programs", Json::Bool(self.proposals.programs)),
            (
                "program_mutation_rate",
                Json::Num(self.proposals.program_mutation_rate),
            ),
            ("strength", Json::Num(1.0)),
        ])
    }
}

/// CLI accepts the command name as its first argument, matching compile_cli.
/// With no command prefix it executes the production search.
pub fn main(args: &[PathBuf]) -> Result<(), String> {
    let command = args.first().and_then(|value| value.to_str());
    let (proof, args) = match command {
        Some("armysearch-proof") => (true, &args[1..]),
        Some("armysearch") => (false, &args[1..]),
        _ => (false, args),
    };
    if args
        .iter()
        .any(|arg| arg == Path::new("--help") || arg == Path::new("-h"))
    {
        println!("{USAGE}");
        return Ok(());
    }
    let config = Config::parse(args)?;
    let catalog = Arc::new(Catalog::load(&config.catalog)?);
    let mut compiler = Compiler::load(&config.root, &catalog.stats)?;
    if let Some(path) = &config.account {
        compiler.library.user = self::util::read(path)?;
    }
    compiler
        .playbooks
        .retain(|(family, _)| !family.starts_with("test-"));
    let account = AccountRules::load(&catalog, &compiler)?;
    let manifest = TargetManifest::load(&config.root, config.manifest.as_deref())?;
    let (mut templates, seed_rejections) =
        operators::seeds(&config.root, &account, &compiler, &catalog)?;
    eprintln!(
        "armysearch: {} legal seeds, {} rejected recipes",
        templates.len(),
        seed_rejections.len()
    );
    if proof {
        let result = proof::run(
            &account,
            &compiler,
            Arc::clone(&catalog),
            &config.catalog,
            &manifest,
            &templates,
            config.fuzz,
        )?;
        std::fs::create_dir_all(&config.out).map_err(|error| error.to_string())?;
        write(&config.out.join("armysearch-proof.json"), &result)?;
        println!("{}", encode(&result));
        return Ok(());
    }
    if config.proposals.programs {
        for genome in &mut templates {
            program::enable(&account, &compiler, &catalog, genome)?;
            operators::admit(&account, &compiler, &catalog, genome)?;
        }
        templates.sort_by_key(genome::ArmyGenome::identity);
    }
    run(
        &config,
        &account,
        &compiler,
        Arc::clone(&catalog),
        &manifest,
        &templates,
        &seed_rejections,
    )
}

pub fn run(
    config: &Config,
    account: &AccountRules,
    compiler: &Compiler<'_>,
    catalog: Arc<Catalog>,
    manifest: &TargetManifest,
    templates: &[genome::ArmyGenome],
    seed_rejections: &[String],
) -> Result<(), String> {
    if templates.is_empty() {
        return Err("armysearch requires at least one admitted seed".to_owned());
    }
    config.proposals.validate()?;
    if config.proposals.families == Families::Playbook
        && !templates
            .iter()
            .any(|genome| config.proposals.families.allows(genome))
    {
        return Err("no admitted playbook seeds for --families playbook".to_owned());
    }
    score::allocate(manifest, Stage::Quick, config.quick_budget, config.seed)?;
    score::allocate(manifest, Stage::Confirm, config.confirm_budget, config.seed)?;
    let holdout_count = manifest
        .targets
        .iter()
        .filter(|target| target.split == score::Split::Holdout)
        .count();
    let holdout_budget = config.holdout_budget.unwrap_or(holdout_count * 8 * 16);
    score::allocate(manifest, Stage::Holdout, holdout_budget, config.seed)?;
    let identity = report::input_identity(
        &config.root,
        &config.catalog,
        &{
            let mut settings = config.identity_settings();
            crate::armies::put(&mut settings, "account", compiler.library.user.clone());
            settings
        },
        manifest,
    )?;
    let checkpoint = config.out.join("checkpoint.json");
    if config.resume.is_none()
        && (checkpoint.exists() || checkpoint.with_extension("json.bak").exists())
    {
        return Err(format!(
            "output already contains a checkpoint; use --resume {}",
            checkpoint.display()
        ));
    }
    let mut state = if let Some(path) = &config.resume {
        report::resume(path, &identity, config.objective, account)?
    } else {
        SearchState::new(config.seed)
    };
    report::validate_resumed(&state, |genome| {
        account
            .compile(compiler, &catalog, genome, genome.plan.angle_offset, 0)
            .map(|_| ())
    })?;
    if state
        .archive
        .values()
        .flatten()
        .any(|elite| !config.proposals.families.allows(&elite.genome))
    {
        return Err("checkpoint contains an army excluded by --families".to_owned());
    }
    if config.batches < state.completed_batches {
        return Err("requested batches precede checkpoint progress".to_owned());
    }
    std::fs::create_dir_all(&config.out).map_err(|error| error.to_string())?;
    let (themed_slots, random_slots) = config.proposals.immigrant_counts(config.batch);
    write(&config.out.join("run-manifest.json"), &object([
        ("settings", config.identity_settings()),
        ("targets", manifest.to_json().at("targets").clone()),
        ("input_fingerprint", string(format!("{:016x}", hash(identity.as_bytes())))),
        ("account_assumptions", Json::Arr(account.assumptions.iter().map(string).collect())),
        ("seed_rejections", Json::Arr(seed_rejections.iter().map(string).collect())),
        ("holdout_budget", number(holdout_budget)),
        ("immigrant_slots_per_batch", object([
            ("themed", number(themed_slots)),
            ("random", number(random_slots)),
        ])),
        ("known_limits", string("frozen exported catalog; visible-layout assumptions; seed/base uncertainty cannot establish real-game calibration; Python parity gates external")),
    ]))?;
    let raw_path = config.out.join("battles.jsonl");
    let raw = std::fs::OpenOptions::new()
        .create(true)
        .write(true)
        .open(&raw_path)
        .map_err(|error| error.to_string())?;
    if raw.metadata().map_err(|error| error.to_string())?.len() < state.raw_bytes {
        return Err("raw battle output is shorter than the checkpoint; resume in the original output directory".to_owned());
    }
    // Discard an interrupted wave, or the previous final holdout, before replay.
    raw.set_len(state.raw_bytes)
        .map_err(|error| error.to_string())?;
    drop(raw);
    let mut evaluator = NativeEvaluator::new(
        account,
        compiler,
        Arc::clone(&catalog),
        manifest,
        config.seed,
        config.threads,
        Some(&raw_path),
    )?;
    while state.completed_batches < config.batches {
        let candidates = search::proposals(
            &mut state,
            config.batch,
            templates,
            account,
            compiler,
            &catalog,
            config.proposals,
        );
        if candidates.is_empty() {
            return Err("proposal space exhausted or all mutations rejected; inspect checkpoint rejection reasons".to_owned());
        }
        search::assess_wave(
            &mut state,
            candidates,
            &mut evaluator,
            manifest,
            config.quick_budget,
            config.confirm_budget,
            config.objective,
            account,
        );
        state.raw_bytes = evaluator.raw_len()?;
        report::checkpoint(&checkpoint, &identity, &state)?;
        write(
            &config.out.join("archive.json"),
            &report::archive_json(&state),
        )?;
        eprintln!(
            "armysearch batch {}/{}: {} cells, {} assessments, {} logical battles",
            state.completed_batches,
            config.batches,
            state.archive.len(),
            state.assessments,
            state.logical_battles
        );
    }
    let elites = state.elites(config.objective);
    if elites.is_empty() {
        return Err(format!(
            "no confirmed legal armies; {}",
            encode(&state.to_json().at("rejected").clone())
        ));
    }
    let mut finalists = elites.clone();
    finalists.truncate(config.top);
    write(
        &config.out.join("pareto.json"),
        &Json::Arr(
            search::pareto(&elites)
                .iter()
                .map(search::Elite::to_json)
                .collect(),
        ),
    )?;
    report::frozen_selection(&config.out.join("holdout-frozen.json"), &finalists)?;
    let frozen = encode(&report::archive_json(&state));
    let mut index = Vec::new();
    for (position, elite) in finalists.iter().enumerate() {
        eprintln!(
            "armysearch fresh seeds {}/{}",
            position + 1,
            finalists.len()
        );
        let (fresh_keys, fresh_outcomes) =
            evaluator.evaluate_rows(&elite.genome, Stage::Finalist, config.confirm_budget)?;
        let fresh = score::summarise(
            manifest,
            Stage::Finalist,
            &fresh_keys,
            &fresh_outcomes,
            config.confirm_budget,
        )?;
        eprintln!("armysearch holdout {}/{}", position + 1, finalists.len());
        let (keys, outcomes) =
            evaluator.evaluate_rows(&elite.genome, Stage::Holdout, holdout_budget)?;
        let holdout = score::summarise(manifest, Stage::Holdout, &keys, &outcomes, holdout_budget)?;
        let replay = evaluator.median_replay(&elite.genome, &keys, &outcomes)?;
        let plan = account.compile(
            compiler,
            &catalog,
            &elite.genome,
            elite.genome.plan.angle_offset,
            0,
        )?;
        let mut housing = compiler.housing(&plan)?;
        for (field, cap) in [
            ("camp_cap", 320),
            ("spell_cap", 11),
            ("cc_cap", 50),
            ("cc_spell_cap", 3),
        ] {
            crate::armies::put(&mut housing, field, number(cap));
        }
        let filename = format!(
            "army-{:03}-{:016x}.json",
            position + 1,
            hash(elite.genome.identity().as_bytes())
        );
        report::army_report(
            &config.out.join(&filename),
            position + 1,
            elite,
            &fresh,
            &holdout,
            manifest,
            plan,
            housing,
            replay,
            config.seed,
            account,
            novelty::report(&elite.genome, templates, account),
            program::report(&elite.genome, compiler),
        )?;
        index.push(object([
            ("rank_before_holdout", number(position + 1)),
            ("report", string(filename)),
            ("archive_cell", string(elite.genome.cell(account))),
            ("confirmation", elite.confirm.metrics.to_json()),
            ("confirmation_intervals", string("unadjusted for selection")),
            ("fresh_seed_search_bases", fresh.metrics.to_json()),
            ("holdout", holdout.metrics.to_json()),
        ]));
    }
    if frozen != encode(&report::archive_json(&state)) {
        return Err("finalist evaluation changed the archive".to_owned());
    }
    let summary = object([
        ("objective", string(config.objective.name())),
        ("finalists", Json::Arr(index)),
        ("search_assessments", number(state.assessments)),
        ("search_logical_battles", number(state.logical_battles)),
        ("executed_this_invocation", number(evaluator.executed)),
        ("cache_hits_this_invocation", number(evaluator.cache_hits)),
        ("checkpoint", string(checkpoint.to_string_lossy())),
    ]);
    write(&config.out.join("summary.json"), &summary)?;
    println!("{}", encode(&summary));
    Ok(())
}

pub use clash_engine::*;
pub use clash_plans::{armies, compile};
pub use clash_scoring::{scoring, scouting};
