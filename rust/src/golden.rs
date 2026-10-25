//! Rust-only regression cases from the python-frozen (d774e17) parity exports.
//! tools/baselab/rust_export.py:875-967 and trace::write_trace define the oracle.
//! These are synthetic simulations, not evidence of real-game calibration.

use std::collections::HashSet;
use std::fs::File;
use std::io::{self, BufRead, BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Instant;

use crate::catalog::Catalog;
use crate::compile_cli::to_json;
use crate::json::{self, Json};
use crate::load::Node;
use crate::{setup, trace};

const USAGE: &str = "golden record|check <cases.jsonl> <expected.jsonl> [--threads N]";
const FNV128_OFFSET: u128 = 0x6c62272e07bb014262b821756295c58d;
const FNV128_PRIME: u128 = 0x0000000001000000000000000000013b;
const FNV64_OFFSET: u64 = 0xcbf29ce484222325;
const FNV64_PRIME: u64 = 0x100000001b3;
const BASE64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

fn hash128(bytes: &[u8]) -> String {
    let mut hash = FNV128_OFFSET;
    for byte in bytes {
        hash = (hash ^ u128::from(*byte)).wrapping_mul(FNV128_PRIME);
    }
    format!("{hash:032x}")
}

struct Case {
    id: String,
    fingerprint: String,
    layout: Json,
    plan: Json,
    options: Json,
}

impl Case {
    fn parse(value: &Json) -> Self {
        Node::new(value, "golden case").keys(&["id", "synthetic", "layout", "plan", "options"]);
        assert!(
            value.at("synthetic").bool(),
            "case must declare synthetic=true"
        );
        let id = value.at("id").str().to_owned();
        assert!(!id.trim().is_empty(), "case id must not be empty");
        value.at("layout").obj();
        value.at("plan").obj();
        value.at("options").obj();
        Self {
            id,
            fingerprint: hash128(to_json(value).as_bytes()),
            layout: value.at("layout").clone(),
            plan: value.at("plan").clone(),
            options: value.at("options").clone(),
        }
    }
}

#[derive(Debug)]
struct Outcome {
    id: String,
    case_hash: String,
    stars: usize,
    destruction_bits: String,
    raw_destruction_bits: String,
    time_bits: String,
    end_reason: String,
    trace_hash: String,
    trace_events: Vec<u64>,
}

impl Outcome {
    fn parse(value: &Json) -> Self {
        Node::new(value, "golden expected").keys(&[
            "schema",
            "id",
            "case_hash",
            "stars",
            "destruction_bits",
            "raw_destruction_bits",
            "time_bits",
            "end_reason",
            "trace_hash",
            "trace_events",
        ]);
        assert_eq!(value.at("schema").usize(), 1, "unsupported golden schema");
        Self {
            id: value.at("id").str().to_owned(),
            case_hash: value.at("case_hash").str().to_owned(),
            stars: value.at("stars").usize(),
            destruction_bits: value.at("destruction_bits").str().to_owned(),
            raw_destruction_bits: value.at("raw_destruction_bits").str().to_owned(),
            time_bits: value.at("time_bits").str().to_owned(),
            end_reason: value.at("end_reason").str().to_owned(),
            trace_hash: value.at("trace_hash").str().to_owned(),
            trace_events: decode_events(value.at("trace_events").str())
                .expect("invalid trace_events base64url"),
        }
    }

    fn json(&self) -> Json {
        Json::Obj(vec![
            ("schema".to_owned(), Json::Num(1.0)),
            ("id".to_owned(), Json::Str(self.id.clone())),
            ("case_hash".to_owned(), Json::Str(self.case_hash.clone())),
            ("stars".to_owned(), Json::Num(self.stars as f64)),
            (
                "destruction_bits".to_owned(),
                Json::Str(self.destruction_bits.clone()),
            ),
            (
                "raw_destruction_bits".to_owned(),
                Json::Str(self.raw_destruction_bits.clone()),
            ),
            ("time_bits".to_owned(), Json::Str(self.time_bits.clone())),
            ("end_reason".to_owned(), Json::Str(self.end_reason.clone())),
            ("trace_hash".to_owned(), Json::Str(self.trace_hash.clone())),
            (
                "trace_events".to_owned(),
                Json::Str(encode_events(&self.trace_events)),
            ),
        ])
    }
}

fn encode_events(events: &[u64]) -> String {
    let mut out = String::new();
    let mut bits = 0_u32;
    let mut count = 0;
    for byte in events.iter().flat_map(|event| event.to_le_bytes()) {
        bits = (bits << 8) | u32::from(byte);
        count += 8;
        while count >= 6 {
            count -= 6;
            out.push(BASE64[((bits >> count) & 63) as usize] as char);
        }
    }
    if count != 0 {
        out.push(BASE64[((bits << (6 - count)) & 63) as usize] as char);
    }
    out
}

fn decode_events(text: &str) -> Result<Vec<u64>, String> {
    let mut events = Vec::new();
    let mut word = Vec::with_capacity(8);
    let mut bits = 0_u32;
    let mut count = 0;
    for byte in text.bytes() {
        let value = BASE64
            .iter()
            .position(|item| *item == byte)
            .ok_or("bad alphabet")?;
        bits = (bits << 6) | value as u32;
        count += 6;
        if count >= 8 {
            count -= 8;
            word.push((bits >> count) as u8);
            if word.len() == 8 {
                events.push(u64::from_le_bytes(word.as_slice().try_into().unwrap()));
                word.clear();
            }
        }
    }
    if !word.is_empty() || encode_events(&events) != text || events.is_empty() {
        return Err("noncanonical or empty event stream".to_owned());
    }
    Ok(events)
}

/// Hash every byte of the existing trace, including LF. A diagnostic event is
/// one complete tick (T/U/B/W/E lines); the final R line is a separate event.
/// Tick fingerprints make the ~1 GB oracle small enough to keep in Git. They
/// identify the first changed tick, without pretending to retain old U/E text.
struct TraceSink {
    hash: u128,
    event_hash: u64,
    line: Vec<u8>,
    events: Vec<u64>,
    in_event: bool,
    capture: Option<usize>,
    captured: Vec<u8>,
    result: Option<String>,
}

impl TraceSink {
    fn new(capture: Option<usize>) -> Self {
        Self {
            hash: FNV128_OFFSET,
            event_hash: FNV64_OFFSET,
            line: Vec::new(),
            events: Vec::new(),
            in_event: false,
            capture,
            captured: Vec::new(),
            result: None,
        }
    }

    fn finish_event(&mut self) {
        if self.in_event {
            self.events.push(self.event_hash);
            self.event_hash = FNV64_OFFSET;
            self.in_event = false;
        }
    }

    fn finish_line(&mut self) {
        if self.line.starts_with(b"T ") || self.line.starts_with(b"R ") {
            self.finish_event();
        }
        if self.line.starts_with(b"R ") {
            self.result = Some(String::from_utf8(self.line.clone()).expect("trace is UTF-8"));
        }
        self.in_event = true;
        for byte in &self.line {
            self.event_hash = (self.event_hash ^ u64::from(*byte)).wrapping_mul(FNV64_PRIME);
        }
        if self.capture == Some(self.events.len()) {
            self.captured.extend_from_slice(&self.line);
        }
        self.line.clear();
    }
}

impl Write for TraceSink {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        for byte in bytes {
            self.hash = (self.hash ^ u128::from(*byte)).wrapping_mul(FNV128_PRIME);
            self.line.push(*byte);
            if *byte == b'\n' {
                self.finish_line();
            }
        }
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn simulate(
    case: &Case,
    catalog: Arc<Catalog>,
    capture: Option<usize>,
) -> Result<(Outcome, String), String> {
    // setup::build is the same path Runner::build uses for prepared jobs.
    // No state, RNG, mutable plan, or iteration order is shared across workers.
    let mut battle = setup::build(&case.layout, &case.plan, &case.options, catalog);
    let mut sink = TraceSink::new(capture);
    trace::write_trace(&mut battle, &mut sink).map_err(|error| error.to_string())?;
    sink.finish_event();
    assert!(sink.line.is_empty(), "trace ended without LF");
    let end_reason = if battle.ended {
        "plan_ended"
    } else if battle.destroyed_counted >= battle.total_counted {
        "all_destroyed"
    } else if battle.offense_finished() {
        "offense_finished"
    } else if battle.t >= battle.max_time {
        "time_limit"
    } else {
        return Err("trace stopped without an end reason".to_owned());
    };
    // Read the R record rather than calling result() twice: result() can log
    // onboard cargo. Its time is rounded to 0.1 s; retain those exact f64 bits.
    let result: Vec<_> = sink
        .result
        .as_deref()
        .ok_or("trace omitted final R")?
        .split_whitespace()
        .collect();
    if result.len() != 5 {
        return Err("invalid trace R record".to_owned());
    }
    let stars = result[1]
        .parse::<usize>()
        .map_err(|_| "invalid trace stars")?;
    let destruction = result[2]
        .parse::<f64>()
        .map_err(|_| "invalid trace destruction")?;
    let time = u64::from_str_radix(result[3], 16).map_err(|_| "invalid trace time bits")?;
    let outcome = Outcome {
        id: case.id.clone(),
        case_hash: case.fingerprint.clone(),
        stars,
        destruction_bits: format!("{:016x}", destruction.to_bits()),
        raw_destruction_bits: format!("{:016x}", battle.raw_destruction().to_bits()),
        time_bits: format!("{time:016x}"),
        end_reason: end_reason.to_owned(),
        trace_hash: format!("{:032x}", sink.hash),
        trace_events: sink.events,
    };
    Ok((
        outcome,
        String::from_utf8(sink.captured).expect("trace is UTF-8"),
    ))
}

fn panic_message(error: Box<dyn std::any::Any + Send>) -> String {
    if let Some(message) = error.downcast_ref::<String>() {
        message.clone()
    } else if let Some(message) = error.downcast_ref::<&str>() {
        (*message).to_owned()
    } else {
        "case panicked".to_owned()
    }
}

fn read_rows<T>(path: &Path, parse: impl Fn(&Json) -> T) -> Result<Vec<T>, String> {
    let file = File::open(path).map_err(|error| format!("{}: {error}", path.display()))?;
    let mut rows = Vec::new();
    let mut ids = HashSet::new();
    for (index, line) in BufReader::new(file).lines().enumerate() {
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let line = line.map_err(|error| error.to_string())?;
            let value = json::parse(&line).map_err(|error| error.to_string())?;
            let row = parse(&value);
            let id = value.at("id").str();
            if !ids.insert(id.to_owned()) {
                return Err(format!("duplicate case id {id:?}"));
            }
            Ok(row)
        }))
        .map_err(panic_message)
        .and_then(|result| result);
        rows.push(result.map_err(|error| format!("{}:{}: {error}", path.display(), index + 1))?);
    }
    if rows.is_empty() {
        return Err(format!("{}: no cases", path.display()));
    }
    Ok(rows)
}

fn run_cases(
    cases: &[Case],
    catalog: &Arc<Catalog>,
    threads: usize,
) -> Vec<Result<Outcome, String>> {
    let next = AtomicUsize::new(0);
    let mut results: Vec<_> = (0..cases.len())
        .map(|_| Err("worker omitted case".to_owned()))
        .collect();
    std::thread::scope(|scope| {
        let mut handles = Vec::new();
        for _ in 0..threads.min(cases.len()) {
            let next = &next;
            handles.push(scope.spawn(move || {
                let mut batch = Vec::new();
                loop {
                    let index = next.fetch_add(1, Ordering::Relaxed);
                    let Some(case) = cases.get(index) else {
                        break;
                    };
                    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                        simulate(case, Arc::clone(catalog), None).map(|(outcome, _)| outcome)
                    }))
                    .map_err(panic_message)
                    .and_then(|result| result);
                    batch.push((index, result));
                }
                batch
            }));
        }
        for handle in handles {
            for (index, result) in handle.join().expect("golden worker panicked outside case") {
                results[index] = result;
            }
        }
    });
    results
}

fn differences(expected: &Outcome, actual: &Outcome) -> Vec<String> {
    let mut fields = Vec::new();
    macro_rules! compare {
        ($($field:ident),* $(,)?) => {
            $(if expected.$field != actual.$field {
                fields.push(format!("{}: {:?} -> {:?}", stringify!($field), expected.$field, actual.$field));
            })*
        };
    }
    compare!(
        case_hash,
        stars,
        destruction_bits,
        raw_destruction_bits,
        time_bits,
        end_reason,
        trace_hash
    );
    if expected.trace_events != actual.trace_events {
        fields.push(format!(
            "trace_events: {} -> {} events (fingerprints differ)",
            expected.trace_events.len(),
            actual.trace_events.len()
        ));
    }
    fields
}

fn diagnose(
    case: &Case,
    expected: &Outcome,
    actual: &Outcome,
    catalog: &Arc<Catalog>,
) -> Result<(), String> {
    let index = (0..expected.trace_events.len().max(actual.trace_events.len()))
        .find(|&index| expected.trace_events.get(index) != actual.trace_events.get(index));
    let Some(index) = index else {
        println!("  per-tick trace events unchanged");
        return Ok(());
    };
    let fingerprint = |value: Option<&u64>| {
        value.map_or_else(|| "<missing>".to_owned(), |value| format!("{value:016x}"))
    };
    println!(
        "  first differing trace event {} (one tick, or final R):",
        index + 1
    );
    println!(
        "    expected fingerprint={}",
        fingerprint(expected.trace_events.get(index))
    );
    println!(
        "    actual   fingerprint={}",
        fingerprint(actual.trace_events.get(index))
    );
    let (rerun, text) = simulate(case, Arc::clone(catalog), Some(index))?;
    if rerun.trace_hash != actual.trace_hash || rerun.trace_events != actual.trace_events {
        return Err(format!(
            "{}: diagnostic rerun was nondeterministic",
            case.id
        ));
    }
    if text.is_empty() {
        println!("    actual: <end of trace>");
    } else {
        for line in text.lines() {
            println!("    actual: {line}");
        }
    }
    Ok(())
}

pub fn command(paths: &[PathBuf], catalog: Arc<Catalog>) -> Result<(), String> {
    if paths.len() != 3 && paths.len() != 5 {
        return Err(USAGE.to_owned());
    }
    let action = paths[0].to_str().ok_or(USAGE)?;
    if !matches!(action, "record" | "check") {
        return Err(USAGE.to_owned());
    }
    let threads = if paths.len() == 5 {
        if paths[3].as_os_str() != "--threads" {
            return Err(USAGE.to_owned());
        }
        paths[4]
            .to_str()
            .ok_or("invalid thread count")?
            .parse::<usize>()
            .map_err(|_| "invalid thread count")?
    } else {
        std::thread::available_parallelism().map_or(1, usize::from)
    };
    if threads == 0 {
        return Err("thread count must be positive".to_owned());
    }
    let cases = read_rows(&paths[1], Case::parse)?;
    let expected = if action == "check" {
        let rows = read_rows(&paths[2], Outcome::parse)?;
        // Require the exact case list, including order: adding, dropping or
        // renaming fixtures must not silently reduce regression coverage.
        if rows.len() != cases.len() || rows.iter().zip(&cases).any(|(row, case)| row.id != case.id)
        {
            return Err(
                "expected case IDs/order differ from fixtures; review and re-record".to_owned(),
            );
        }
        rows
    } else {
        if paths[1] == paths[2]
            || (paths[2].exists()
                && std::fs::canonicalize(&paths[1]).ok() == std::fs::canonicalize(&paths[2]).ok())
        {
            return Err("expected output must not overwrite cases".to_owned());
        }
        Vec::new()
    };
    let started = Instant::now();
    let results = run_cases(&cases, &catalog, threads);
    let mut failed = 0;
    for (index, result) in results.iter().enumerate() {
        match result {
            Err(error) => {
                failed += 1;
                println!("{} FAILED: {error}", cases[index].id);
            }
            Ok(actual) if action == "check" => {
                let fields = differences(&expected[index], actual);
                if !fields.is_empty() {
                    failed += 1;
                    println!("{} DIFFERS:", cases[index].id);
                    for field in fields {
                        println!("  {field}");
                    }
                    diagnose(&cases[index], &expected[index], actual, &catalog)?;
                }
            }
            _ => {}
        }
    }
    if action == "record" && failed == 0 {
        let file =
            File::create(&paths[2]).map_err(|error| format!("{}: {error}", paths[2].display()))?;
        let mut out = BufWriter::new(file);
        for result in &results {
            writeln!(out, "{}", to_json(&result.as_ref().unwrap().json()))
                .map_err(|error| error.to_string())?;
        }
        out.flush().map_err(|error| error.to_string())?;
    }
    println!(
        "golden {action}: cases={} passed={} failed={failed} threads={threads} wall_seconds={:.6}",
        cases.len(),
        cases.len() - failed,
        started.elapsed().as_secs_f64()
    );
    if failed != 0 {
        return Err(format!("{failed}/{} golden cases failed", cases.len()));
    }
    Ok(())
}
