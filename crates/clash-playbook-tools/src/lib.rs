//! Deterministic playbook/research tooling. Provider processes are opt-in;
//! citation validation and saved-result review always work offline.
pub mod citations;
pub mod complete;
pub mod gaps;
pub mod harvest;
mod io;
pub mod research;
pub mod schema;
pub mod transcripts;
pub mod verify;

use clash_data::json::Json;
use clash_data::wire::{self, list, obj, string, text};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

const HELP: &str =
    "clash playbook verify|consolidate|queue|harvest|transcript|extract|complete|gaps ...
  verify [FAMILY|FILE ...] [--all] [--transcripts DIR] [--report FILE]
         [--check-recorded --sources DIR] [--extracted] [--legacy]
  consolidate [FAMILY ...] [--input RAW] [--out FILE] [--dry] [--legacy]
  queue usage|audit [--queue TSV] [--brief FILE] [--out DIR]
         [--run --provider EXE] [--workers N] [--passes N] [--report FILE]
  extract [--brief FILE] [--out DIR] [--run --provider EXE] [--workers N]
  complete FAMILY --input RAW [--out FILE] [--dry]
  gaps [--playbooks DIR] [--transcripts DIR] [--out FILE]
  queue import --input TSV --out TSV
  harvest --family FAMILY [--input JSON|JSONL | --provider EXE]
         [--query TEXT] [--pages N] [--max-age-days N] [--date YYYY-MM-DD]
         [--out INDEX.jsonl] [--fetch] [--transcripts DIR]
  transcript VIDEO --input JSON|JSON3|XML [--out FILE]
  transcript VIDEO --fetch [--provider yt-dlp.exe] [--transcripts DIR]
Common: --root DIR, --sources DIR, --playbooks DIR, --provider-arg ARG (repeatable).
No provider runs without --run (research/extract), --fetch (subtitles), or an
explicit --provider for discovery. No Python, downloads or installs in tests.";

#[derive(Default)]
struct Options {
    values: BTreeMap<String, Vec<String>>,
    positional: Vec<String>,
}

impl Options {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut result = Self::default();
        let mut arguments = args.iter();
        let flags = [
            "all",
            "dry",
            "legacy",
            "fetch",
            "run",
            "check-recorded",
            "extracted",
            "help",
            "h",
        ];
        let values = [
            "root",
            "sources",
            "transcripts",
            "playbooks",
            "report",
            "input",
            "out",
            "queue",
            "brief",
            "provider",
            "provider-arg",
            "workers",
            "passes",
            "skip",
            "family",
            "query",
            "pages",
            "max-age-days",
            "date",
        ];
        while let Some(argument) = arguments.next() {
            if argument == "--" {
                result.positional.extend(arguments.cloned());
                break;
            }
            if let Some(key) = argument.strip_prefix("--") {
                if flags.contains(&key) {
                    result.values.entry(key.to_owned()).or_default();
                } else if values.contains(&key) {
                    let value = arguments
                        .next()
                        .ok_or_else(|| format!("--{key} needs a value"))?;
                    result
                        .values
                        .entry(key.to_owned())
                        .or_default()
                        .push(value.clone());
                } else {
                    return Err(format!("unknown option {argument}"));
                }
            } else if argument == "-h" {
                result.values.entry("help".to_owned()).or_default();
            } else {
                result.positional.push(argument.clone());
            }
        }
        Ok(result)
    }
    fn has(&self, key: &str) -> bool {
        self.values.contains_key(key)
    }
    fn get(&self, key: &str) -> Option<&str> {
        self.values
            .get(key)
            .and_then(|v| v.last())
            .map(String::as_str)
    }
    fn many(&self, key: &str) -> Vec<String> {
        self.values.get(key).cloned().unwrap_or_default()
    }
    fn path(&self, key: &str, default: impl AsRef<Path>) -> PathBuf {
        self.get(key)
            .map(PathBuf::from)
            .unwrap_or_else(|| default.as_ref().to_owned())
    }
    fn number(&self, key: &str, default: usize) -> Result<usize, String> {
        self.get(key).map_or(Ok(default), |v| {
            v.parse().map_err(|_| format!("--{key} needs an integer"))
        })
    }
    fn root(&self) -> PathBuf {
        self.path("root", Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."))
    }
    fn sources(&self) -> PathBuf {
        self.path("sources", self.root().join("local/sources"))
    }
    fn transcripts(&self) -> PathBuf {
        self.path("transcripts", self.sources().join("transcripts"))
    }
    fn playbooks(&self) -> PathBuf {
        self.path("playbooks", self.root().join("data/playbooks"))
    }
    fn provider(&self) -> Result<research::Provider, String> {
        Ok(research::Provider {
            executable: self
                .get("provider")
                .ok_or("--run requires --provider EXE")?
                .to_owned(),
            arguments: self.many("provider-arg"),
        })
    }
}

pub fn cli(args: &[String]) -> Result<(), String> {
    let Some(command) = args.first() else {
        println!("{HELP}");
        return Ok(());
    };
    if ["help", "--help", "-h"].contains(&command.as_str()) {
        println!("{HELP}");
        return Ok(());
    }
    let options = Options::parse(&args[1..])?;
    if options.has("help") {
        println!("{HELP}");
        return Ok(());
    }
    match command.as_str() {
        "verify" => verify_command(&options),
        "consolidate" => consolidate_command(&options),
        "queue" => queue_command(&options, false),
        "extract" => queue_command(&options, true),
        "harvest" => harvest_command(&options),
        "transcript" => transcript_command(&options),
        "complete" => complete_command(&options),
        "gaps" => gaps_command(&options),
        _ => Err(format!("unknown playbook command {command}; use --help")),
    }
}

fn report(options: &Options, value: &Json) -> Result<(), String> {
    if let Some(path) = options.get("report") {
        io::write(Path::new(path), value)?;
    }
    Ok(())
}

fn verify_command(options: &Options) -> Result<(), String> {
    let mut transcripts = citations::Transcripts::new(&options.transcripts());
    if options.has("extracted") {
        let paths = raw_inputs(options, "playbooks")?;
        if paths.is_empty() {
            return Err("no extraction replies selected".to_owned());
        }
        if paths.len() > 1 && options.has("out") {
            return Err("--out needs exactly one input".to_owned());
        }
        let mut reports = Vec::new();
        for path in paths {
            let video = stem(&path)?;
            let captions = transcripts
                .get(&video)?
                .ok_or_else(|| format!("{video}: missing transcript"))?;
            let result = citations::check_extracted(
                &fs::read_to_string(&path).map_err(|e| e.to_string())?,
                &video,
                captions,
            )?;
            if !options.has("dry") {
                let out = options
                    .get("out")
                    .map(PathBuf::from)
                    .unwrap_or_else(|| path.with_extension("json"));
                io::write(&out, &result)?;
            }
            println!(
                "{video}: {}",
                wire::encode(result.get("check").unwrap_or(&result))
            );
            reports.push(result);
        }
        return report(options, &Json::Arr(reports));
    }
    let paths = if options.positional.is_empty() {
        io::files(&options.playbooks(), "json")?
    } else {
        options
            .positional
            .iter()
            .map(|name| {
                if Path::new(name).is_file() {
                    Ok(PathBuf::from(name))
                } else {
                    Ok(options
                        .playbooks()
                        .join(format!("{}.json", io::safe_name(name)?)))
                }
            })
            .collect::<Result<Vec<_>, String>>()?
    };
    if paths.is_empty() {
        return Err("no playbooks selected".to_owned());
    }
    let mut families = Vec::new();
    let (mut failed, mut verified, mut rejected) = (0, 0.0, 0.0);
    for path in paths {
        let playbook = io::read(&path)?;
        let mut result = if options.has("legacy") {
            verify::inspect_legacy(&playbook, &mut transcripts)?
        } else {
            verify::inspect(&playbook, &mut transcripts)?
        };
        let family = stem(&path)?;
        let errors = list(&result, "errors");
        failed += errors.len();
        let good = wire::number(&result, "verified_citations", 0.0);
        let bad = wire::number(&result, "rejected_citations", 0.0);
        verified += good;
        rejected += bad;
        println!(
            "{family}: {good} verified, {bad} rejected citations, {} validation errors",
            errors.len()
        );
        for error in errors {
            eprintln!("  {}", error.str());
        }
        wire::put(&mut result, "family", string(family));
        families.push(result);
    }
    let mut result = obj([
        ("playbooks", Json::Arr(families)),
        ("verified_citations", wire::num(verified)),
        ("rejected_citations", wire::num(rejected)),
        ("validation_errors", wire::num(failed as f64)),
    ]);
    if options.has("check-recorded") {
        let comparison =
            verify::compare_recorded(&options.sources(), &options.playbooks(), &mut transcripts)?;
        let differences = list(&comparison, "differences");
        println!(
            "Recorded checker comparison: {} extracted, {} consolidated, {} differences",
            wire::number(&comparison, "extracted_replies", 0.0),
            wire::number(&comparison, "consolidated_replies", 0.0),
            differences.len()
        );
        for difference in differences {
            eprintln!("  {}", wire::encode(difference));
        }
        failed += differences.len();
        wire::put(&mut result, "recorded_comparison", comparison);
    }
    report(options, &result)?;
    println!(
        "TOTAL: {verified} verified, {rejected} rejected citations; {failed} errors/differences"
    );
    if failed == 0 {
        Ok(())
    } else {
        Err(format!(
            "playbook verification found {failed} errors/differences; see report"
        ))
    }
}

fn stem(path: &Path) -> Result<String, String> {
    path.file_stem()
        .and_then(|s| s.to_str())
        .map(str::to_owned)
        .ok_or_else(|| format!("invalid file name {}", path.display()))
}

fn raw_inputs(options: &Options, folder: &str) -> Result<Vec<PathBuf>, String> {
    let inputs = options.many("input");
    if !inputs.is_empty() {
        return Ok(inputs.into_iter().map(PathBuf::from).collect());
    }
    if options.positional.is_empty() {
        return io::files(&options.sources().join(folder), "raw");
    }
    options
        .positional
        .iter()
        .map(|family| {
            Ok(options
                .sources()
                .join(folder)
                .join(format!("{}.raw", io::safe_name(family)?)))
        })
        .collect()
}

fn consolidate_command(options: &Options) -> Result<(), String> {
    let inputs = raw_inputs(options, "consolidated")?;
    if inputs.is_empty() {
        return Err("no consolidation replies selected".to_owned());
    }
    if inputs.len() > 1 && options.has("out") {
        return Err("--out needs exactly one input".to_owned());
    }
    let mut transcripts = citations::Transcripts::new(&options.transcripts());
    let mut reports = Vec::new();
    for path in inputs {
        let family = stem(&path)?;
        let playbook = verify::consolidate(
            &fs::read_to_string(&path).map_err(|e| e.to_string())?,
            &mut transcripts,
            options.has("legacy"),
        )?;
        let out = options.path("out", options.playbooks().join(format!("{family}.json")));
        if !options.has("dry") {
            io::write(&out, &playbook)?;
        }
        let check = playbook.get("check").cloned().unwrap_or(Json::Null);
        println!("{family}: {}", wire::encode(&check));
        reports.push(obj([("family", string(family)), ("check", check)]));
    }
    report(options, &Json::Arr(reports))
}

fn transcript_command(options: &Options) -> Result<(), String> {
    let video = options.positional.first().ok_or("transcript needs VIDEO")?;
    io::safe_name(video)?;
    let record = if options.has("fetch") {
        transcripts::fetch(
            video,
            &options.transcripts(),
            options.get("provider").unwrap_or("yt-dlp.exe"),
        )?
    } else {
        let path = options
            .get("input")
            .ok_or("transcript needs --input FILE or --fetch")?;
        let record = transcripts::import(Path::new(path), video)?;
        let out = options.path("out", options.transcripts().join(format!("{video}.json")));
        io::write(&out, &record)?;
        record
    };
    println!(
        "{video}: {} caption lines",
        citations::lines(&record)?.len()
    );
    Ok(())
}

fn harvest_command(options: &Options) -> Result<(), String> {
    let families = options.many("family");
    if families.len() != 1 {
        return Err(
            "harvest needs one --family (repeat the command for other families)".to_owned(),
        );
    }
    let family = &families[0];
    let out = options.path("out", options.sources().join("videos.jsonl"));
    let mut index = harvest::read_index(&out)?;
    let date = options
        .get("date")
        .map(str::to_owned)
        .map_or_else(harvest::today, Ok)?;
    let max_age = options
        .get("max-age-days")
        .unwrap_or("183")
        .parse::<f64>()
        .map_err(|_| "invalid maximum age")?;
    if !max_age.is_finite() || max_age < 0.0 {
        return Err("maximum age must be finite and nonnegative".to_owned());
    }
    let inputs = options.many("input");
    let mut added = 0;
    if inputs.is_empty() {
        let provider = options
            .get("provider")
            .ok_or("discovery needs --input FILE or explicit --provider EXE")?;
        let queries = if let Some(query) = options.get("query") {
            vec![query]
        } else {
            harvest::queries(family)?.to_vec()
        };
        for query in queries {
            let rows = harvest::search(query, options.number("pages", 2)?, provider)?;
            added += harvest::merge(&mut index, rows, family, query, &date, max_age)?;
        }
    } else {
        for input in inputs {
            let rows = harvest::read_rows(Path::new(&input))?;
            added += harvest::merge(
                &mut index,
                rows,
                family,
                options.get("query").unwrap_or("local import"),
                &date,
                max_age,
            )?;
        }
    }
    harvest::save(&out, &index)?;
    println!("{family}: {added} new videos; {} indexed", index.len());
    if options.has("fetch") {
        harvest::fetch_missing(
            &index,
            &options.transcripts(),
            options.get("provider").unwrap_or("yt-dlp.exe"),
        )?;
    }
    Ok(())
}

fn queue_command(options: &Options, extraction: bool) -> Result<(), String> {
    let mode = if extraction {
        "extract"
    } else {
        options
            .positional
            .first()
            .map(String::as_str)
            .unwrap_or("usage")
    };
    if mode == "import" {
        let input = options
            .get("input")
            .ok_or("queue import needs --input TSV")?;
        let out = options.get("out").ok_or("queue import needs --out TSV")?;
        let jobs = research::usage_jobs(Path::new(input), "", Path::new("."))?;
        let content: String = jobs
            .iter()
            .map(|job| format!("{}\t{}\n", job.kind, job.name))
            .collect();
        io::atomic_write(Path::new(out), content.as_bytes())?;
        println!("{} queue subjects", jobs.len());
        return Ok(());
    }
    let root = options.root();
    let default_brief = match mode {
        "extract" => root.join("docs/playbook-extraction.md"),
        "usage" | "status" | "run" => root.join("local/research/brief-entity.txt"),
        "audit" => root.join("local/research/brief-gap.txt"),
        _ => return Err("queue mode must be usage|audit|status|run".to_owned()),
    };
    let brief_path = options.path("brief", default_brief);
    let brief = if brief_path.exists() {
        fs::read_to_string(&brief_path).map_err(|e| e.to_string())?
    } else if options.has("run") || mode == "run" {
        return Err(format!(
            "missing brief {}; supply --brief FILE",
            brief_path.display()
        ));
    } else {
        String::new()
    };
    let jobs = match mode {
        "extract" => research::extract_jobs(
            &options.transcripts(),
            &brief,
            &options.path("out", options.sources().join("playbooks")),
        )?,
        "audit" => research::audit_jobs(
            &options.path("input", root.join("local/research/usage")),
            &brief,
            &options.path("out", root.join("local/research/gaps")),
            Some(&options.path("skip", root.join("local/research/gaps/skip-event.txt"))),
        )?,
        _ => research::usage_jobs(
            &options.path("queue", root.join("local/research/queue.tsv")),
            &brief,
            &options.path("out", root.join("local/research/usage")),
        )?,
    };
    let running = options.has("run") || mode == "run";
    let result = if running {
        research::run(
            &jobs,
            &options.provider()?,
            options.number("workers", if mode == "usage" { 4 } else { 3 })?,
            options.number("passes", if mode == "usage" { 2 } else { 1 })?,
        )?
    } else {
        research::status(&jobs)
    };
    report(options, &result)?;
    println!("{}", wire::encode(&result));
    let mut failures = result
        .arr()
        .iter()
        .filter(|receipt| text(receipt, "status", "") == "failed")
        .count();
    if mode == "extract" && running {
        let mut transcripts = citations::Transcripts::new(&options.transcripts());
        for job in &jobs {
            if !job.output.exists() {
                continue;
            }
            let captions = transcripts.get(&job.id)?.ok_or("missing transcript")?;
            let reply = fs::read_to_string(&job.output).map_err(|e| e.to_string())?;
            let checked = citations::check_extracted(&reply, &job.id, captions)?;
            if checked.get("parse_error").is_some() {
                failures += 1;
            }
            io::write(&job.output.with_extension("json"), &checked)?;
        }
    }
    if failures == 0 {
        Ok(())
    } else {
        Err(format!("{failures} jobs failed; rerun to retry"))
    }
}

fn complete_command(options: &Options) -> Result<(), String> {
    let family = options.positional.first().ok_or("complete needs FAMILY")?;
    io::safe_name(family)?;
    let playbook_path = options.playbooks().join(format!("{family}.json"));
    let input = options.path(
        "input",
        options
            .sources()
            .join("completion")
            .join(format!("{family}.raw")),
    );
    let reply = fs::read_to_string(input).map_err(|e| e.to_string())?;
    let mut transcripts = citations::Transcripts::new(&options.transcripts());
    let (playbook, receipt) =
        complete::merge(&io::read(&playbook_path)?, &reply, &mut transcripts)?;
    if !options.has("dry") && !list(&receipt, "kept").is_empty() {
        io::write(&options.path("out", &playbook_path), &playbook)?;
    }
    println!("{}", wire::encode(&receipt));
    report(options, &receipt)
}

fn gaps_command(options: &Options) -> Result<(), String> {
    let mut transcripts = citations::Transcripts::new(&options.transcripts());
    let (output, tally) = gaps::measure(&options.playbooks(), &mut transcripts)?;
    if !options.has("dry") {
        io::write(
            &options.path("out", options.root().join("data/playbook-gaps.json")),
            &output,
        )?;
    }
    println!("cite times: {}", wire::encode(&tally));
    println!("{}", wire::encode(&output));
    report(options, &obj([("output", output), ("cite_times", tally)]))
}
