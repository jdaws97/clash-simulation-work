//! Opt-in jobs-only path-field measurements. No simulation state is changed.

use std::cell::RefCell;
use std::collections::{BTreeMap, HashSet};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use crate::grid::CacheKey;

pub fn enabled() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    *ENABLED.get_or_init(|| std::env::var_os("BASELAB_PROFILE_FIELDS").is_some_and(|v| v == "1"))
}

#[derive(Clone, Copy, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub(crate) struct Row {
    pub kind: &'static str,
    pub source: &'static str,
    pub initial: bool,
}

#[derive(Clone, Copy, Eq, Hash, PartialEq)]
pub(crate) struct GoalKey {
    pub cache: Option<CacheKey>,
    pub geometry: (u64, u64, u64, u64),
    pub wall_extra: u64,
}

#[derive(Default)]
struct Counters {
    builds: u64,
    pops: u64,
    repairs: u64,
    wall: Duration,
    battle_distinct_initial: u64,
}

struct Job {
    index: usize,
    layout: usize,
    started: Instant,
    battle_started: Option<(Instant, Duration)>,
    battle_finished: Option<Instant>,
    measured: Duration,
    rows: BTreeMap<Row, Counters>,
    initial_fields: HashSet<(Row, u64, GoalKey)>,
}

thread_local! {
    static JOB: RefCell<Option<Job>> = const { RefCell::new(None) };
}

pub fn begin_job(index: usize) {
    JOB.with(|job| {
        *job.borrow_mut() = Some(Job {
            index,
            layout: usize::MAX,
            started: Instant::now(),
            battle_started: None,
            battle_finished: None,
            measured: Duration::ZERO,
            rows: BTreeMap::new(),
            initial_fields: HashSet::new(),
        });
    });
}

pub fn set_layout(layout: usize) {
    JOB.with(|job| {
        if let Some(job) = job.borrow_mut().as_mut() {
            job.layout = layout;
        }
    });
}

pub fn begin_battle() {
    JOB.with(|job| {
        if let Some(job) = job.borrow_mut().as_mut() {
            job.battle_started = Some((Instant::now(), job.measured));
        }
    });
}

pub fn end_battle() {
    JOB.with(|job| {
        if let Some(job) = job.borrow_mut().as_mut() {
            job.battle_finished = Some(Instant::now());
        }
    });
}

// Nested measurements subtract their children's measured time, so metadata,
// topology, seeding, repairs and lazy expansion can be summed without overlap.
pub(crate) struct Span {
    row: Row,
    started: Instant,
    measured_before: Duration,
}

impl Span {
    pub fn start(row: Row) -> Option<Self> {
        JOB.with(|job| {
            job.borrow().as_ref().map(|job| Self {
                row,
                started: Instant::now(),
                measured_before: job.measured,
            })
        })
    }
}

impl Drop for Span {
    fn drop(&mut self) {
        let elapsed = self.started.elapsed();
        JOB.with(|job| {
            if let Some(job) = job.borrow_mut().as_mut() {
                let children = job.measured.saturating_sub(self.measured_before);
                let exclusive = elapsed.saturating_sub(children);
                job.rows.entry(self.row).or_default().wall += exclusive;
                job.measured += exclusive;
            }
        });
    }
}

pub(crate) fn build(row: Row, initial_version: Option<u64>, key: GoalKey) {
    JOB.with(|job| {
        if let Some(job) = job.borrow_mut().as_mut() {
            job.rows.entry(row).or_default().builds += 1;
            if row.initial {
                job.initial_fields.insert((
                    row,
                    initial_version.expect("initial grid version"),
                    key,
                ));
            }
        }
    });
}

pub(crate) fn work(row: Row, pops: u64, repairs: u64) {
    JOB.with(|job| {
        if let Some(job) = job.borrow_mut().as_mut() {
            let counters = job.rows.entry(row).or_default();
            counters.pops += pops;
            counters.repairs += repairs;
        }
    });
}

struct JobResult {
    index: usize,
    layout: usize,
    failed: bool,
    job_wall: Duration,
    battle_wall: Duration,
    fields_wall: Duration,
    battle_fields_wall: Duration,
}

#[derive(Default)]
struct Summary {
    rows: BTreeMap<Row, Counters>,
    initial_fields: HashSet<(usize, Row, u64, GoalKey)>,
    jobs: Vec<JobResult>,
}

#[derive(Default)]
pub struct Session {
    summary: Mutex<Summary>,
}

impl Session {
    pub fn finish_job(&self, failed: bool) {
        let Some(mut job) = JOB.with(|job| job.borrow_mut().take()) else {
            return;
        };
        let job_wall = job.started.elapsed();
        let (battle_wall, battle_fields_wall) =
            job.battle_started
                .map_or((Duration::ZERO, Duration::ZERO), |(started, measured)| {
                    let finished = job.battle_finished.unwrap_or_else(Instant::now);
                    (
                        finished.duration_since(started),
                        job.measured.saturating_sub(measured),
                    )
                });
        // One lock per completed job, never per query or frontier pop.
        let mut summary = self
            .summary
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        for &(row, _, _) in &job.initial_fields {
            job.rows.entry(row).or_default().battle_distinct_initial += 1;
        }
        for (row, counters) in job.rows {
            let total = summary.rows.entry(row).or_default();
            total.builds += counters.builds;
            total.pops += counters.pops;
            total.repairs += counters.repairs;
            total.wall += counters.wall;
            total.battle_distinct_initial += counters.battle_distinct_initial;
        }
        for (row, version, key) in job.initial_fields {
            summary
                .initial_fields
                .insert((job.layout, row, version, key));
        }
        summary.jobs.push(JobResult {
            index: job.index,
            layout: job.layout,
            failed,
            job_wall,
            battle_wall,
            fields_wall: job.measured,
            battle_fields_wall,
        });
    }

    fn print(&self) {
        let mut summary = self
            .summary
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        eprintln!("fields_profile format=1 time_unit=ms layout=input_index pops=including_stale state=version_at_work timings=exclusive");
        for (row, counters) in &summary.rows {
            let distinct = summary
                .initial_fields
                .iter()
                .filter(|(_, key, _, _)| key == row)
                .count() as u64;
            let within = if row.initial {
                counters
                    .builds
                    .saturating_sub(counters.battle_distinct_initial)
            } else {
                0
            };
            let across = counters.battle_distinct_initial.saturating_sub(distinct);
            eprintln!(
                "fields_profile kind={} source={} state={} builds={} pops={} repairs={} wall_ms={:.6} distinct_initial={} battle_distinct_initial={} within_battle_rebuilds={} cross_battle_reuses={}",
                row.kind,
                row.source,
                if row.initial { "initial" } else { "changed" },
                counters.builds,
                counters.pops,
                counters.repairs,
                ms(counters.wall),
                distinct,
                counters.battle_distinct_initial,
                within,
                across,
            );
        }
        summary.jobs.sort_by_key(|job| job.index);
        for job in &summary.jobs {
            eprintln!(
                "fields_profile job={} layout={} failed={} job_wall_ms={:.6} battle_wall_ms={:.6} fields_wall_ms={:.6} battle_fields_wall_ms={:.6} battle_fields_pct={:.3}",
                job.index,
                job.layout,
                job.failed,
                ms(job.job_wall),
                ms(job.battle_wall),
                ms(job.fields_wall),
                ms(job.battle_fields_wall),
                percent(job.battle_fields_wall, job.battle_wall),
            );
        }
        let battle_wall: Duration = summary.jobs.iter().map(|job| job.battle_wall).sum();
        let battle_fields: Duration = summary.jobs.iter().map(|job| job.battle_fields_wall).sum();
        let initial_wall: Duration = summary
            .rows
            .iter()
            .filter(|(row, _)| row.initial)
            .map(|(_, counters)| counters.wall)
            .sum();
        let fields_wall: Duration = summary.rows.values().map(|counters| counters.wall).sum();
        let builds: u64 = summary.rows.values().map(|counters| counters.builds).sum();
        let initial_builds: u64 = summary
            .rows
            .iter()
            .filter(|(row, _)| row.initial)
            .map(|(_, counters)| counters.builds)
            .sum();
        let pops: u64 = summary.rows.values().map(|counters| counters.pops).sum();
        let initial_pops: u64 = summary
            .rows
            .iter()
            .filter(|(row, _)| row.initial)
            .map(|(_, counters)| counters.pops)
            .sum();
        eprintln!(
            "fields_profile total jobs={} builds={} initial_builds={} pops={} initial_pops={} fields_wall_ms={:.6} initial_fields_wall_ms={:.6} initial_fields_pct={:.3} battle_wall_ms={:.6} battle_fields_wall_ms={:.6} battle_fields_pct={:.3}",
            summary.jobs.len(),
            builds,
            initial_builds,
            pops,
            initial_pops,
            ms(fields_wall),
            ms(initial_wall),
            percent(initial_wall, fields_wall),
            ms(battle_wall),
            ms(battle_fields),
            percent(battle_fields, battle_wall),
        );
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        self.print();
    }
}

fn ms(duration: Duration) -> f64 {
    duration.as_secs_f64() * 1000.0
}

fn percent(part: Duration, total: Duration) -> f64 {
    if total.is_zero() {
        0.0
    } else {
        part.as_secs_f64() / total.as_secs_f64() * 100.0
    }
}
