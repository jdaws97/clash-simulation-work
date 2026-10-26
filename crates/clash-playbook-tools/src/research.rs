//! Resumable bounded process jobs. Providers receive one prompt argument;
//! no shell evaluation, user-home scripts or Python runtime is implicit.
use crate::{citations, io};
use clash_data::json::Json;
use clash_data::wire::{self, obj, string, text};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

#[derive(Clone, Debug)]
pub struct Job {
    pub id: String,
    pub kind: String,
    pub name: String,
    pub prompt: String,
    pub input_hash: String,
    pub output: PathBuf,
    pub minimum_bytes: usize,
}

#[derive(Clone, Debug)]
pub struct Provider {
    pub executable: String,
    pub arguments: Vec<String>,
}

pub fn slug(name: &str) -> String {
    let mut out = String::new();
    let mut separator = false;
    for byte in name.bytes() {
        if byte.is_ascii_alphanumeric() {
            if separator && !out.is_empty() {
                out.push('-');
            }
            out.push(byte.to_ascii_lowercase() as char);
            separator = false;
        } else {
            separator = true;
        }
    }
    out
}

pub fn usage_jobs(queue: &Path, brief: &str, output: &Path) -> Result<Vec<Job>, String> {
    let queue_text = fs::read_to_string(queue).map_err(|e| e.to_string())?;
    let mut jobs = Vec::new();
    for (line, row) in queue_text.lines().enumerate() {
        if row.trim().is_empty() {
            continue;
        }
        let (kind, name) = row
            .split_once('\t')
            .ok_or_else(|| format!("queue line {} needs kind<TAB>name", line + 1))?;
        if kind.is_empty() || name.is_empty() {
            return Err(format!("empty queue subject on line {}", line + 1));
        }
        let id = slug(name);
        io::safe_name(&id)?;
        jobs.push(Job {
            output: output.join(format!("{id}.md")),
            id,
            kind: kind.to_owned(),
            name: name.to_owned(),
            prompt: brief.replace("{KIND}", kind).replace("{NAME}", name),
            input_hash: wire::sha256(row.as_bytes()),
            minimum_bytes: 1500,
        });
    }
    unique(&jobs)?;
    Ok(jobs)
}

pub fn audit_jobs(
    usage: &Path,
    brief: &str,
    output: &Path,
    skip: Option<&Path>,
) -> Result<Vec<Job>, String> {
    let skip = match skip {
        Some(path) if path.exists() => fs::read_to_string(path).map_err(|e| e.to_string())?,
        _ => String::new(),
    };
    let mut jobs = Vec::new();
    for path in io::files(usage, "md")? {
        let id = path
            .file_stem()
            .and_then(|s| s.to_str())
            .ok_or("invalid usage filename")?
            .to_owned();
        io::safe_name(&id)?;
        if skip.lines().any(|line| line.trim() == id) {
            continue;
        }
        let content = fs::read_to_string(&path).map_err(|e| e.to_string())?;
        let name = content
            .lines()
            .next()
            .unwrap_or("")
            .trim_start_matches('#')
            .trim()
            .to_owned();
        jobs.push(Job {
            output: output.join(format!("{id}.md")),
            prompt: brief.replace("{SLUG}", &id).replace("{NAME}", &name),
            id,
            kind: "audit".to_owned(),
            name,
            input_hash: wire::sha256(content.as_bytes()),
            minimum_bytes: 800,
        });
    }
    unique(&jobs)?;
    Ok(jobs)
}

pub fn extract_jobs(directory: &Path, brief: &str, output: &Path) -> Result<Vec<Job>, String> {
    let mut jobs = Vec::new();
    for path in io::files(directory, "json")? {
        let record = io::read(&path)?;
        if citations::lines(&record)?.is_empty() {
            continue;
        }
        let id = path
            .file_stem()
            .and_then(|s| s.to_str())
            .ok_or("invalid transcript filename")?
            .to_owned();
        io::safe_name(&id)?;
        let input_hash = wire::file_hash(&path)?;
        let prompt = format!(
            "{brief}\n\nRead the transcript file {}. Reply with only the JSON object for video_id {id}.",
            path.display()
        );
        jobs.push(Job {
            output: output.join(format!("{id}.raw")),
            prompt,
            id,
            name: text(&record, "title", "").to_owned(),
            kind: "extract".to_owned(),
            input_hash,
            minimum_bytes: 0,
        });
    }
    unique(&jobs)?;
    Ok(jobs)
}

fn unique(jobs: &[Job]) -> Result<(), String> {
    let mut ids = BTreeMap::new();
    for job in jobs {
        if let Some(previous) = ids.insert(&job.id, &job.name) {
            return Err(format!(
                "queue slug collision {}: {previous:?} / {:?}",
                job.id, job.name
            ));
        }
    }
    Ok(())
}

fn identity(job: &Job, provider: &Provider) -> String {
    wire::sha256(
        wire::encode(&obj([
            ("schema", wire::num(1)),
            ("prompt", string(&job.prompt)),
            ("input_hash", string(&job.input_hash)),
            ("executable", string(&provider.executable)),
            (
                "arguments",
                Json::Arr(provider.arguments.iter().map(string).collect()),
            ),
            ("minimum_bytes", wire::num(job.minimum_bytes as f64)),
        ]))
        .as_bytes(),
    )
}

fn manifest_path(job: &Job) -> PathBuf {
    job.output
        .parent()
        .unwrap_or(Path::new("."))
        .join(".jobs")
        .join(format!("{}.json", job.id))
}

pub fn status(jobs: &[Job]) -> Json {
    Json::Arr(
        jobs.iter()
            .map(|job| {
                let bytes = fs::metadata(&job.output).map_or(0, |m| m.len());
                let path = manifest_path(job);
                let receipt = io::read(&path).ok();
                let hash_matches = receipt.as_ref().map_or(!path.exists(), |receipt| {
                    wire::file_hash(&job.output)
                        .is_ok_and(|hash| hash == text(receipt, "output_hash", ""))
                        && text(receipt, "status", "") == "complete"
                        && receipt.get("job").is_some_and(|saved| {
                            text(saved, "input_hash", "") == job.input_hash
                                && matches!(saved.get("prompt"), Some(Json::Str(prompt))
                                    if wire::sha256(prompt.as_bytes()) == wire::sha256(job.prompt.as_bytes()))
                        })
                });
                let complete = bytes > job.minimum_bytes as u64 && hash_matches;
                obj([
                    ("id", string(&job.id)),
                    ("kind", string(&job.kind)),
                    ("name", string(&job.name)),
                    ("prompt_hash", string(wire::sha256(job.prompt.as_bytes()))),
                    ("output", string(job.output.to_string_lossy())),
                    ("bytes", wire::num(bytes as f64)),
                    ("complete", Json::Bool(complete)),
                    (
                        "status",
                        string(if complete { "complete" } else { "pending" }),
                    ),
                ])
            })
            .collect(),
    )
}

fn run_one(job: &Job, provider: &Provider, passes: usize) -> Result<Json, String> {
    let fingerprint = identity(job, provider);
    let manifest = manifest_path(job);
    let specification = obj([
        ("schema", wire::num(1)),
        ("id", string(&job.id)),
        ("kind", string(&job.kind)),
        ("name", string(&job.name)),
        ("prompt", string(&job.prompt)),
        ("prompt_hash", string(wire::sha256(job.prompt.as_bytes()))),
        ("input_hash", string(&job.input_hash)),
        ("provider", string(&provider.executable)),
        (
            "provider_arguments",
            Json::Arr(provider.arguments.iter().map(string).collect()),
        ),
        ("output", string(job.output.to_string_lossy())),
        ("minimum_bytes", wire::num(job.minimum_bytes as f64)),
    ]);
    let saved = if manifest.exists() {
        Some(io::read(&manifest)?)
    } else {
        None
    };
    let bytes = fs::metadata(&job.output).map_or(0, |m| m.len());
    let compatible = saved.as_ref().is_none_or(|saved| {
        text(saved, "identity", "") == fingerprint && text(saved, "status", "") == "complete"
    });
    let parseable = job.kind != "extract"
        || fs::read_to_string(&job.output)
            .ok()
            .is_some_and(|s| citations::parse_reply(&s).is_some());
    if bytes > job.minimum_bytes as u64 && compatible && parseable {
        let receipt = obj([
            ("id", string(&job.id)),
            ("identity", string(&fingerprint)),
            ("status", string("complete")),
            ("resumed", Json::Bool(true)),
            ("imported_legacy", Json::Bool(saved.is_none())),
            ("output_hash", string(wire::file_hash(&job.output)?)),
            ("job", specification.clone()),
        ]);
        // A changed result is never accepted under an existing saved receipt.
        if saved
            .as_ref()
            .is_none_or(|saved| text(saved, "output_hash", "") == text(&receipt, "output_hash", ""))
        {
            io::write(&manifest, &receipt)?;
            return Ok(receipt);
        }
    }
    let mut failure = String::new();
    for attempt in 1..=passes {
        let response = Command::new(&provider.executable)
            .args(&provider.arguments)
            .arg(&job.prompt)
            .output();
        match response {
            Ok(response)
                if response.status.success()
                    && response.stdout.len() > job.minimum_bytes
                    && (job.kind != "extract"
                        || citations::parse_reply(&String::from_utf8_lossy(&response.stdout))
                            .is_some()) =>
            {
                io::atomic_write(&job.output, &response.stdout)?;
                let receipt = obj([
                    ("id", string(&job.id)),
                    ("identity", string(&fingerprint)),
                    ("status", string("complete")),
                    ("attempt", wire::num(attempt as f64)),
                    ("resumed", Json::Bool(false)),
                    ("output_hash", string(wire::sha256(&response.stdout))),
                    ("job", specification.clone()),
                ]);
                io::write(&manifest, &receipt)?;
                return Ok(receipt);
            }
            Ok(response) => {
                failure = format!(
                    "provider exited {}; stdout {} bytes (must exceed {})",
                    response.status,
                    response.stdout.len(),
                    job.minimum_bytes
                )
            }
            Err(error) => failure = format!("{}: {error}", provider.executable),
        }
    }
    let receipt = obj([
        ("id", string(&job.id)),
        ("identity", string(fingerprint)),
        ("status", string("failed")),
        ("error", string(failure)),
        ("attempts", wire::num(passes as f64)),
        ("job", specification),
    ]);
    io::write(&manifest, &receipt)?;
    Ok(receipt)
}

pub fn run(
    jobs: &[Job],
    provider: &Provider,
    workers: usize,
    passes: usize,
) -> Result<Json, String> {
    unique(jobs)?;
    if !(1..=32).contains(&workers) || !(1..=10).contains(&passes) {
        return Err("workers must be 1..32 and passes 1..10".to_owned());
    }
    let next = AtomicUsize::new(0);
    let results = Mutex::new(Vec::new());
    std::thread::scope(|scope| {
        for _ in 0..workers.min(jobs.len()) {
            scope.spawn(|| loop {
                let index = next.fetch_add(1, Ordering::Relaxed);
                let Some(job) = jobs.get(index) else {
                    break;
                };
                let result = run_one(job, provider, passes);
                results
                    .lock()
                    .expect("job results lock")
                    .push((index, result));
            });
        }
    });
    let mut results = results.into_inner().map_err(|e| e.to_string())?;
    results.sort_by_key(|(index, _)| *index);
    Ok(Json::Arr(
        results
            .into_iter()
            .map(|(_, result)| result)
            .collect::<Result<Vec<_>, _>>()?,
    ))
}
