use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use clash_armysearch::{account::AccountRules, genome::ArmyGenome};
use clash_plans::compile::Compiler;

use crate::archive::DescriptorDefinition;
use crate::eval::{Budget, Evaluator, Manifest};
use crate::generate::{Style, TownHallZone};
use crate::json::Json;
use crate::layout::{model::AdmissionPolicy, BaseRules};
use crate::oracle::{self, OracleContext};
use crate::search::{self, Settings, State};
use crate::util::{fingerprint, num, object, read, source_identity, string, write};
use crate::Context;

const USAGE: &str = concat!(
    "clash basesearch run --config RUN.json --out DIR [--threads N --resume CHECKPOINT]\n",
    "clash basesearch smoke --out /tmp/NAME [--threads N --resume CHECKPOINT]\n",
    "clash basesearch proof-completion --out DIR\n",
    "RUN fields: root, synthetic_account:true or account:path, town_hall (16..18), ",
    "mode (ranked|war), modifier, seed, waves, batch, physical_battles, screen_groups, ",
    "confirm_groups, gate_groups, final_groups, oracle_budget, oracle_every, archive_groups, ",
    "polish_attempts, racing, immigrant_every, crossover_every, operator_weights, ",
    "optional population:[{genome,weight}]. Counts are complete seven-battle visible scouting groups. ",
    "Budgets include oracle and diagnostic battles. All input/plan/profile identities are frozen. ",
    "Final data never ranks winners.",
);

pub(crate) fn default_operators() -> Vec<(crate::operators::Operator, usize)> {
    use crate::operators::Operator;
    [
        Operator::Swap,
        Operator::Nudge,
        Operator::TrapRelocate,
        Operator::BuildingMode,
        Operator::WallRunShift,
        Operator::AirDefenseSpread,
        Operator::StrongestInward,
        Operator::CoreRotation,
        Operator::HeroPermutation,
        Operator::CcPackage,
        Operator::SkeletonMode,
        Operator::OuterScreen,
    ]
    .into_iter()
    .map(|operator| (operator, 1))
    .collect()
}

/// Derive a declared synthetic maximum account from the frozen public catalog.
/// No personal profile or memory-derived inventory is used for smoke/proofs.
pub fn synthetic_account(catalog: &crate::catalog::Catalog, th: i64) -> Json {
    let levels = [
        ("gm", "Town Hall"),
        ("camp", "Army Camp"),
        ("sf", "Spell Factory"),
        ("dsf", "Dark Spell Factory"),
        ("cc", "Clan Castle"),
        ("lab", "Laboratory"),
        ("barracks", "Barracks"),
        ("dbarracks", "Dark Barracks"),
        ("workshop", "Workshop"),
        ("pethouse", "Pet House"),
        ("herohall", "Hero Hall"),
        ("smith", "Blacksmith"),
    ]
    .iter()
    .map(|(key, name)| {
        (
            (*key).to_owned(),
            Json::Num(if *key == "gm" {
                th
            } else {
                catalog.stats.max_level(name, th).unwrap_or(1)
            } as f64),
        )
    })
    .collect();
    let mut fields = BTreeMap::<&str, Vec<(String, Json)>>::new();
    for (name, record) in catalog.stats.registry.obj() {
        if record.get("seasonal").is_some_and(Json::bool) {
            continue;
        }
        // These supported event spells require an explicit dated event
        // version. The permanent-content synthetic preset supplies none.
        if matches!(
            name.as_str(),
            "Santa's Surprise" | "Bag of Frostmites" | "Birthday Boom" | "Yellow Card"
        ) {
            continue;
        }
        let kind = record.get("kind").and_then(Json::opt_str).unwrap_or("");
        if matches!(kind, "troop" | "super_troop" | "siege" | "siege_machine")
            && !catalog.units.contains_key(name)
        {
            continue;
        }
        if kind == "spell" && crate::plans::spell_key(name).is_none() {
            continue;
        }
        if kind == "equipment" && !crate::content::equipment(name) {
            continue;
        }
        if kind == "pet" && !crate::content::pet(name) {
            continue;
        }
        let target = match record.get("kind").and_then(Json::opt_str) {
            Some("hero") => "hero_levels",
            Some("equipment") => "equipment_levels",
            Some("pet") => "pet_levels",
            Some("troop" | "super_troop" | "spell" | "siege" | "siege_machine") => "attack_levels",
            _ => continue,
        };
        if let Some(level) = catalog.stats.max_level(name, th) {
            fields
                .entry(target)
                .or_default()
                .push((name.clone(), Json::Num(level as f64)));
        }
    }
    object([
        (
            "source",
            string("declared synthetic fully researched account; public frozen catalog"),
        ),
        ("levels", Json::Obj(levels)),
        (
            "hero_levels",
            Json::Obj(fields.remove("hero_levels").unwrap_or_default()),
        ),
        (
            "attack_levels",
            Json::Obj(fields.remove("attack_levels").unwrap_or_default()),
        ),
        (
            "equipment_levels",
            Json::Obj(fields.remove("equipment_levels").unwrap_or_default()),
        ),
        (
            "pet_levels",
            Json::Obj(fields.remove("pet_levels").unwrap_or_default()),
        ),
    ])
}

pub fn manifests(
    context: &OracleContext<'_, '_>,
    population: &[(ArmyGenome, f64)],
    namespace: &str,
    groups: usize,
    seed: i64,
    modifier: Option<String>,
) -> Result<Manifest, String> {
    if population.is_empty() || groups / 5 < population.len() {
        return Err(
            "group budget must cover all five skill bins for every population entry".to_owned(),
        );
    }
    let mut rows = Vec::new();
    let stream = crate::eval::manifest_seed(namespace, seed);
    for index in 0..groups {
        let (genome, weight) = &population[index % population.len()];
        let mut group = oracle::group_for(
            context,
            genome,
            namespace,
            (stream + index as i64).rem_euclid(1 << 48),
            *weight,
            modifier.clone(),
        )?;
        // Cross army identity with skill: each complete population pass
        // advances one bin, even when the population size is divisible by five.
        let skill_bin = (seed.rem_euclid(5) + (index / population.len()) as i64) % 5;
        for plan in &mut group.plans {
            clash_plans::armies::put(
                plan,
                "strength",
                Json::Num(clash_scoring::scoring::skill(skill_bin)),
            );
        }
        rows.push(group);
    }
    let manifest = Manifest {
        id: namespace.to_owned(),
        groups: rows,
    };
    manifest.validate()?;
    Ok(manifest)
}

fn integer(config: &Json, key: &str, default: usize) -> Result<usize, String> {
    if config.get(key).is_none() {
        return Ok(default);
    }
    crate::util::usize_field(config, key)
}

pub fn main(args: &[PathBuf]) -> Result<(), String> {
    if args
        .iter()
        .any(|arg| arg == Path::new("--help") || arg == Path::new("-h"))
    {
        println!("{USAGE}");
        return Ok(());
    }
    let args = if args
        .first()
        .is_some_and(|arg| arg == Path::new("basesearch"))
    {
        &args[1..]
    } else {
        args
    };
    let command = args.first().and_then(|arg| arg.to_str()).ok_or(USAGE)?;
    let mut options = BTreeMap::new();
    let mut cursor = 1;
    while cursor < args.len() {
        let flag = args[cursor].to_str().ok_or("non-UTF8 option")?;
        if !matches!(
            flag,
            "--config" | "--out" | "--threads" | "--resume" | "--root"
        ) {
            return Err(format!("unknown basesearch option {flag}"));
        }
        let value = args
            .get(cursor + 1)
            .ok_or_else(|| format!("{flag} requires a value"))?;
        if options.insert(flag, value.clone()).is_some() {
            return Err(format!("duplicate {flag}"));
        }
        cursor += 2;
    }
    let out = options.get("--out").ok_or("--out is required")?;
    std::fs::create_dir_all(out).map_err(|error| error.to_string())?;
    if command == "proof-completion" {
        let receipt = crate::completion_proof::run()?;
        write(&out.join("proof-completion.json"), &receipt)?;
        println!("{}", crate::util::encode(&receipt));
        return Ok(());
    }
    if !matches!(command, "run" | "smoke") {
        return Err(USAGE.to_owned());
    }
    let config = if command == "smoke" {
        object([
            ("synthetic_account", Json::Bool(true)),
            ("town_hall", num(16)),
            ("waves", num(2)),
            ("batch", num(3)),
            ("physical_battles", num(2400)),
            ("screen_groups", num(10)),
            ("confirm_groups", num(10)),
            ("gate_groups", num(10)),
            ("final_groups", num(10)),
            ("oracle_budget", num(28)),
            ("archive_groups", num(2)),
            ("polish_attempts", num(1)),
        ])
    } else {
        read(
            options
                .get("--config")
                .ok_or("run requires --config; use smoke for a short synthetic run")?,
        )?
    };
    let root = options
        .get("--root")
        .cloned()
        .or_else(|| {
            config
                .get("root")
                .and_then(Json::opt_str)
                .map(PathBuf::from)
        })
        .unwrap_or_else(|| {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .unwrap()
                .parent()
                .unwrap()
                .to_owned()
        });
    let catalog_path = config
        .get("catalog")
        .and_then(Json::opt_str)
        .map(PathBuf::from)
        .unwrap_or_else(|| clash_data::catalog::path(&root));
    let catalog = Arc::new(crate::catalog::Catalog::load(&catalog_path)?);
    let context = Context {
        rules: Arc::new(BaseRules::load(
            &root.join("data/generated/base_rules.json"),
        )?),
        catalog: catalog.clone(),
    };
    let th = integer(&config, "town_hall", 16)? as i64;
    let mut compiler = Compiler::load(&root, &catalog.stats)?;
    compiler.library.user = if config.get("synthetic_account") == Some(&Json::Bool(true)) {
        synthetic_account(&catalog, th)
    } else {
        let path = config
            .get("account")
            .and_then(Json::opt_str)
            .ok_or("select an explicit account path or synthetic_account:true")?;
        read(Path::new(path))?
    };
    compiler
        .playbooks
        .retain(|(name, _)| !name.starts_with("test-"));
    // Freeze options rather than consulting pace/gaps environment on resume.
    compiler.pace = config.get("pace").map_or(1.0, Json::f64);
    compiler.gaps = Some((0.0, 0.0));
    let account = AccountRules::load(&catalog, &compiler)?;
    let (mut seeds, rejections) =
        clash_armysearch::operators::seeds(&root, &account, &compiler, &catalog)?;
    seeds.sort_by(|a, b| {
        a.plan
            .family
            .cmp(&b.plan.family)
            .then(a.identity().cmp(&b.identity()))
    });
    if seeds.is_empty() {
        return Err("no native account-legal attack seeds".to_owned());
    }
    let population = if let Some(population) = config.get("population") {
        population
            .arr()
            .iter()
            .map(|entry| {
                let mut genome = ArmyGenome::from_json(entry.at("genome"))?;
                clash_armysearch::operators::admit(&account, &compiler, &catalog, &mut genome)?;
                Ok((genome, entry.at("weight").f64()))
            })
            .collect::<Result<Vec<_>, String>>()?
    } else {
        let cited: Vec<_> = seeds
            .iter()
            .filter(|genome| genome.plan.family != "generic")
            .collect();
        let selected: Vec<_> = if cited.is_empty() {
            seeds.iter().take(2).collect()
        } else {
            cited.into_iter().take(2).collect()
        };
        selected
            .into_iter()
            .map(|genome| (genome.clone(), 1.0))
            .collect()
    };
    let mut corpus = Vec::new();
    let mut corpus_attempts = Vec::new();
    for (style_index, style) in [Style::Grid, Style::Wide, Style::Scatter]
        .into_iter()
        .enumerate()
    {
        for (zone_index, zone) in TownHallZone::ALL.into_iter().enumerate() {
            let seed = 600 + (3 * style_index + zone_index) as u64;
            let result = crate::generate::preset(&context, th, style, zone, seed);
            corpus_attempts.push(object([
                ("style", string(format!("{style:?}"))),
                ("zone", string(format!("{zone:?}"))),
                ("seed", string(seed.to_string())),
                (
                    "result",
                    string(match &result {
                        Ok(base) => base.physical_identity().to_owned(),
                        Err(error) => format!("rejected: {error:?}"),
                    }),
                ),
            ]));
            if let Ok(base) = result {
                corpus.push(base);
            }
        }
    }
    let (mut descriptors, corpus_values) = DescriptorDefinition::from_corpus(&context, &corpus)?;
    let descriptor_corpus = object([
        ("recipe", string("TH-specific Grid/Wide/Scatter x Central/Mid/Edge; fixed seeds 600..608; admitted members only")),
        ("attempts", Json::Arr(corpus_attempts)),
        ("values", corpus_values),
    ]);
    descriptors.corpus_identity = fingerprint(&descriptor_corpus);
    let operator_weights = if let Some(weights) = config.get("operator_weights") {
        weights
            .obj()
            .iter()
            .map(|(name, weight)| {
                let operator = crate::operators::Operator::ALL
                    .into_iter()
                    .find(|operator| operator.name() == *name)
                    .ok_or_else(|| format!("unknown proposal operator {name}"))?;
                let value = object([("weight", weight.clone())]);
                Ok((operator, crate::util::usize_field(&value, "weight")?))
            })
            .collect::<Result<Vec<_>, String>>()?
    } else {
        default_operators()
    };
    let settings = Settings {
        town_hall: th,
        mode: config
            .get("mode")
            .and_then(Json::opt_str)
            .unwrap_or("ranked")
            .to_owned(),
        modifier: config
            .get("modifier")
            .and_then(Json::opt_str)
            .map(str::to_owned),
        hole_penalty: config.get("hole_penalty").and_then(Json::opt_f64),
        seed: integer(&config, "seed", 137)? as u64,
        batch: integer(&config, "batch", 12)?,
        oracle_budget: integer(&config, "oracle_budget", 112)?,
        oracle_every: integer(&config, "oracle_every", 1)?,
        archive_groups: integer(&config, "archive_groups", 4)?,
        polish_attempts: integer(&config, "polish_attempts", 4)?,
        alpha: 0.05,
        descriptors,
        racing: config.get("racing") != Some(&Json::Bool(false)),
        operator_weights,
        immigrant_every: integer(&config, "immigrant_every", 5)?,
        crossover_every: integer(&config, "crossover_every", 7)?,
    };
    settings.validate()?;
    if settings.mode == "war" && account.town_hall != th {
        return Err("war attacker TH must equal the defender/run TH".to_owned());
    }
    let oracle_context = OracleContext {
        account: &account,
        compiler: &compiler,
        catalog: &catalog,
    };
    let battle_seed = integer(&config, "battle_seed", 8191)? as i64;
    let screen = manifests(
        &oracle_context,
        &population,
        "screen-development",
        integer(&config, "screen_groups", 20)?,
        battle_seed,
        settings.modifier.clone(),
    )?;
    let confirmation = manifests(
        &oracle_context,
        &population,
        "confirmation-development",
        integer(&config, "confirm_groups", 68)?,
        battle_seed + (1 << 40),
        settings.modifier.clone(),
    )?;
    let gate = manifests(
        &oracle_context,
        &population,
        "finalist-gate-development",
        integer(&config, "gate_groups", 400)?,
        battle_seed + (2 << 40),
        settings.modifier.clone(),
    )?;
    let final_manifest = manifests(
        &oracle_context,
        &population,
        "final-untouched",
        integer(&config, "final_groups", 400)?,
        integer(&config, "final_seed", 99823)? as i64 + (3 << 40),
        settings.modifier.clone(),
    )?;
    let waves = integer(&config, "waves", 4)?;
    let wave_screens = (0..waves)
        .map(|wave| {
            manifests(
                &oracle_context,
                &population,
                &format!("screen-development/wave/{wave}"),
                screen.groups.len(),
                battle_seed,
                settings.modifier.clone(),
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    Manifest::ensure_disjoint(
        &[&screen, &confirmation, &gate, &final_manifest]
            .into_iter()
            .chain(wave_screens.iter())
            .collect::<Vec<_>>(),
    )?;
    let limit = integer(&config, "physical_battles", 100_000)?;
    // Final manifests have a separate identity and never enter development
    // selection or checkpoint compatibility. Their outcomes are report-only.
    let executable = std::fs::read(std::env::current_exe().map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    let identity = fingerprint(&object([
        ("schema", num(crate::checkpoint::SCHEMA)),
        ("settings", settings.to_json()),
        (
            "catalog_bytes",
            string(crate::layout::json::identity(
                &std::fs::read(&catalog_path).map_err(|e| e.to_string())?,
            )),
        ),
        ("rules", string(&context.rules.identity)),
        ("source", string(source_identity(&root)?)),
        (
            "executable",
            string(crate::layout::json::identity(&executable)),
        ),
        ("account", compiler.library.user.clone()),
        ("compiler_policy", compiler.library.policy.clone()),
        ("compiler_pace", Json::Num(compiler.pace)),
        ("playbooks", Json::Obj(compiler.playbooks.clone())),
        (
            "castle",
            read(&root.join("data/generated/clan_castle.json"))?,
        ),
        ("screen", screen.to_json()),
        ("confirmation", confirmation.to_json()),
        ("gate", gate.to_json()),
        (
            "oracle_seeds",
            Json::Arr(seeds.iter().map(ArmyGenome::to_json).collect()),
        ),
        ("limit", num(limit)),
    ]));
    let checkpoint = out.join("checkpoint.json");
    let policy = AdmissionPolicy {
        require_all_walls: true,
        ..AdmissionPolicy::default()
    };
    let (mut state, budget, cache) = if let Some(path) = options.get("--resume") {
        crate::checkpoint::resume(path, &identity, &context, &settings, &policy)?
    } else {
        if checkpoint.exists() || checkpoint.with_extension("json.bak").exists() {
            return Err("output contains a checkpoint; use --resume".to_owned());
        }
        (
            State::new(settings.seed),
            Budget {
                limit,
                ..Budget::default()
            },
            BTreeMap::new(),
        )
    };
    if state.completed_waves > waves {
        return Err("requested waves precede checkpoint progress".to_owned());
    }
    if state.polished && state.completed_waves < waves {
        return Err("cannot extend a polished run; resume only its original wave count".to_owned());
    }
    for attack in state.attacks.entries.values() {
        account.check(&attack.genome)?;
    }
    let threads = options
        .get("--threads")
        .map(|value| {
            value
                .to_str()
                .ok_or("invalid workers")?
                .parse::<usize>()
                .map_err(|_| "invalid workers")
        })
        .transpose()?
        .unwrap_or(4);
    if threads == 0 {
        return Err("workers must be positive".to_owned());
    }
    let mut evaluator = Evaluator {
        context: &context,
        identity: identity.clone(),
        threads,
        budget,
        cache,
    };
    write(&out.join("run-manifest.json"), &object([
        ("identity", string(&identity)), ("config", config.clone()), ("settings", settings.to_json()),
        ("descriptor_corpus", descriptor_corpus),
        ("account", compiler.library.user.clone()), ("population", Json::Arr(population.iter().map(|(genome, weight)| object([
            ("genome", genome.to_json()), ("weight", Json::Num(*weight)),
        ])).collect())),
        ("screen", screen.to_json()), ("confirmation", confirmation.to_json()), ("gate", gate.to_json()), ("final", final_manifest.to_json()),
        ("seed_rejections", Json::Arr(rejections.iter().map(string).collect())),
        ("evidence", string("declared synthetic generator layouts; selected population is a model scenario set, not observed prevalence")),
    ]))?;
    let proof = crate::completion_proof::run()?;
    write(&out.join("proof-completion.json"), &proof)?;
    while state.completed_waves < waves {
        let wave_screen = &wave_screens[state.completed_waves];
        write(
            &out.join(format!("screen-wave-{}.json", state.completed_waves)),
            &wave_screen.to_json(),
        )?;
        search::wave(
            &context,
            &settings,
            &mut state,
            &mut evaluator,
            wave_screen,
            &confirmation,
            &oracle_context,
            &seeds,
        )?;
        crate::checkpoint::save(&checkpoint, &identity, &state, &evaluator)?;
        write(&out.join("archive.json"), &state.archive.to_json())?;
        write(&out.join("attack-archive.json"), &state.attacks.to_json())?;
        eprintln!(
            "basesearch wave {waves_done}/{waves}: {} cells, {} attacks, {} physical battles",
            state.archive.cells.len(),
            state.attacks.entries.len(),
            evaluator.budget.used(),
            waves_done = state.completed_waves
        );
    }
    if !state.polished {
        if let Some(elite) = state.archive.ranked().first() {
            let initial = elite.base.clone();
            let (base, log) = crate::diagnostics::polish(
                &context,
                &initial,
                &mut evaluator,
                &screen,
                &confirmation,
                &settings,
                state.attacks.version,
            )?;
            state.polish_log = log;
            if base.physical_identity() != initial.physical_identity() {
                let mut elite = state.archive.ranked()[0].clone();
                elite.base = base;
                elite.descriptor = settings.descriptors.describe(&context, &elite.base)?;
                elite.screen = evaluator.assess(&elite.base, &screen, state.attacks.version)?;
                elite.confirmation =
                    evaluator.assess(&elite.base, &confirmation, state.attacks.version)?;
                crate::archive::score(&mut elite, &settings.mode, settings.hole_penalty)?;
                elite.robustness = search::evaluate_attacks(
                    &settings,
                    &mut state.attacks,
                    &elite.base,
                    &mut evaluator,
                    &oracle_context,
                )?;
                state.archive.insert(elite)?;
            }
        }
        state.polished = true;
        crate::checkpoint::save(&checkpoint, &identity, &state, &evaluator)?;
        write(&out.join("archive.json"), &state.archive.to_json())?;
        write(&out.join("attack-archive.json"), &state.attacks.to_json())?;
    }
    let reference = crate::generate::preset(&context, th, Style::Grid, TownHallZone::Central, 73)
        .map_err(|error| format!("reference: {error:?}"))?;
    match crate::report::finish(
        out,
        &context,
        &settings,
        &state,
        &mut evaluator,
        &gate,
        &final_manifest,
        &reference,
        &oracle_context,
    ) {
        Ok(report) => println!(
            "{}",
            crate::util::encode(&object([
                ("report", string(out.join("report.md").to_string_lossy())),
                ("status", report.at("status").clone()),
                ("budget", evaluator.budget.to_json()),
            ]))
        ),
        Err(error) => {
            write(
                &out.join("report.json"),
                &object([
                    ("status", string("incomplete")),
                    ("error", string(&error)),
                    ("budget", evaluator.budget.to_json()),
                ]),
            )?;
            return Err(error);
        }
    }
    Ok(())
}
