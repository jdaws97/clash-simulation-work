//! Shared prepared inputs, worker-local battles, ordered in-memory results.

use std::any::Any;
use std::fmt;
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, OnceLock};

use crate::catalog::Catalog;
use crate::field_profile;
use crate::json::{self, Json};
use crate::load::Node;
use crate::setup;
use crate::state::{Battle, BattleResult};

/// A job refers to cached layouts and plans; all setup options are retained.
#[derive(Clone, Debug)]
pub struct Job {
    indices: OnceLock<(usize, usize)>,
    options: Json,
}

impl Job {
    pub fn new(
        layout_idx: usize,
        plan_idx: usize,
        seed: i64,
        town_hall: i64,
        modifier: Option<String>,
    ) -> Self {
        Self {
            indices: OnceLock::from((layout_idx, plan_idx)),
            options: Json::Obj(vec![
                ("seed".to_owned(), Json::Num(seed as f64)),
                ("town_hall".to_owned(), Json::Num(town_hall as f64)),
                (
                    "modifier".to_owned(),
                    modifier.map_or(Json::Null, Json::Str),
                ),
            ]),
        }
    }

    /// Indices are validated and cached on first use. Keeping validation on the
    /// worker lets malformed jobs become indexed failures, as in the CLI.
    pub fn from_json(value: &Json) -> Self {
        Self {
            indices: OnceLock::new(),
            options: value.clone(),
        }
    }

    pub fn layout_idx(&self) -> usize {
        self.indices().0
    }

    pub fn plan_idx(&self) -> usize {
        self.indices().1
    }

    pub fn options(&self) -> &Json {
        &self.options
    }

    fn indices(&self) -> (usize, usize) {
        *self.indices.get_or_init(|| {
            (
                Node::new(self.options.at("layout"), "job.layout").usize(),
                Node::new(self.options.at("plan"), "job.plan").usize(),
            )
        })
    }
}

/// Parsed JSON is cached by index. Mutable runtime plans are built per battle.
#[derive(Clone, Debug)]
pub struct PreparedInputs {
    pub layouts: Vec<Json>,
    pub plans: Vec<Json>,
    pub jobs: Vec<Job>,
}

impl PreparedInputs {
    pub fn new(layouts: Vec<Json>, plans: Vec<Json>) -> Self {
        Self {
            layouts,
            plans,
            jobs: Vec::new(),
        }
    }

    pub fn load(path: &Path) -> Result<Self, String> {
        let text = std::fs::read_to_string(path)
            .map_err(|error| format!("{}: {error}", path.display()))?;
        Self::parse(&text).map_err(|error| format!("{}: {error}", path.display()))
    }

    pub fn parse(text: &str) -> Result<Self, String> {
        let value = json::parse(text).map_err(|error| error.to_string())?;
        Ok(Self::from_json(&value))
    }

    /// Uses the existing strict loader; malformed prepared inputs panic.
    pub fn from_json(value: &Json) -> Self {
        Node::new(value, "jobs").keys(&["layouts", "plans", "jobs"]);
        Self {
            layouts: value.at("layouts").arr().to_vec(),
            plans: value.at("plans").arr().to_vec(),
            jobs: value.at("jobs").arr().iter().map(Job::from_json).collect(),
        }
    }
}

/// Scalar results cross worker boundaries; the battle remains on its worker.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct JobResult {
    pub stars: usize,
    pub destruction: usize,
    pub th_destroyed: bool,
    pub time: f64,
    pub units_left: usize,
}

impl From<&BattleResult> for JobResult {
    fn from(result: &BattleResult) -> Self {
        Self {
            stars: result.stars,
            destruction: result.destruction,
            th_destroyed: result.th_destroyed,
            time: result.time,
            units_left: result.units_left,
        }
    }
}

/// Called after each successful battle, before its state is dropped. Calls may
/// overlap and arrive out of order; use the batch index to store diagnostics.
/// A hook panic is reported as a failure of that job.
pub type SummaryHook<'a> = dyn Fn(usize, &Job, &Battle, &BattleResult) + Sync + 'a;

#[derive(Clone, Debug)]
pub struct JobFailure {
    pub index: usize,
    pub message: String,
}

#[derive(Debug)]
pub enum RunError {
    InvalidThreadCount,
    Worker(String),
    Jobs(Vec<JobFailure>),
}

impl fmt::Display for RunError {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidThreadCount => out.write_str("thread count must be positive"),
            Self::Worker(message) => out.write_str(message),
            Self::Jobs(failures) => write!(out, "{} jobs failed", failures.len()),
        }
    }
}

impl std::error::Error for RunError {}

/// Owns one catalog and one prepared-input cache for any number of batches.
pub struct Runner {
    catalog: Arc<Catalog>,
    inputs: PreparedInputs,
}

impl Runner {
    pub fn load(catalog_path: &Path, inputs: PreparedInputs) -> Result<Self, String> {
        let catalog = Arc::new(Catalog::load(catalog_path)?);
        Ok(Self::new(catalog, inputs))
    }

    pub fn new(catalog: Arc<Catalog>, inputs: PreparedInputs) -> Self {
        Self { catalog, inputs }
    }

    pub fn inputs(&self) -> &PreparedInputs {
        &self.inputs
    }

    /// Builds fresh state on the calling thread, also used by setup and trace.
    pub fn build(&self, job: &Job) -> Result<Battle, crate::content::ContentError> {
        let (layout_idx, plan_idx) = job.indices();
        let layout = self
            .inputs
            .layouts
            .get(layout_idx)
            .expect("job layout index out of range");
        let plan = self
            .inputs
            .plans
            .get(plan_idx)
            .expect("job plan index out of range");
        if field_profile::enabled() {
            field_profile::set_layout(layout_idx);
        }
        setup::build(layout, plan, job.options(), Arc::clone(&self.catalog))
    }

    pub fn build_job(&self, index: usize) -> Result<Battle, crate::content::ContentError> {
        let jobs = &self.inputs.jobs;
        let job = jobs
            .get(index)
            .unwrap_or_else(|| panic!("job index {index} outside {} jobs", jobs.len()));
        self.build(job)
    }

    pub fn run(&self, jobs: &[Job], threads: usize) -> Result<Vec<JobResult>, RunError> {
        self.run_with_summary(jobs, threads, None)
    }

    pub fn run_with_summary(
        &self,
        jobs: &[Job],
        threads: usize,
        summary: Option<&SummaryHook<'_>>,
    ) -> Result<Vec<JobResult>, RunError> {
        if threads == 0 {
            return Err(RunError::InvalidThreadCount);
        }
        let count = jobs.len();
        let counter = AtomicUsize::new(0);
        let profiling = field_profile::enabled().then(field_profile::Session::default);
        // Only read-only JSON and the catalog are shared. Rc plan vectors and
        // all mutable simulation state are created and dropped on their worker.
        let batches = std::thread::scope(|scope| {
            let mut handles = Vec::new();
            for _ in 0..threads.min(count) {
                let counter = &counter;
                let profiling = &profiling;
                handles.push(scope.spawn(move || {
                    let mut results = Vec::new();
                    loop {
                        let index = counter.fetch_add(1, Ordering::Relaxed);
                        if index >= count {
                            break;
                        }
                        if profiling.is_some() {
                            field_profile::begin_job(index);
                        }
                        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                            let job = &jobs[index];
                            let mut battle = self.build(job).map_err(|error| error.to_string())?;
                            if profiling.is_some() {
                                field_profile::begin_battle();
                            }
                            let result = battle.run();
                            if profiling.is_some() {
                                field_profile::end_battle();
                            }
                            if let Some(summary) = summary {
                                summary(index, job, &battle, &result);
                            }
                            Ok(JobResult::from(&result))
                        }))
                        .map_err(panic_message)
                        .and_then(|result| result);
                        if let Some(profiling) = profiling {
                            profiling.finish_job(result.is_err());
                        }
                        results.push((index, result));
                    }
                    results
                }));
            }
            handles
                .into_iter()
                .map(|handle| handle.join().map_err(panic_message))
                .collect::<Result<Vec<_>, _>>()
        })
        .map_err(RunError::Worker)?;
        let mut results: Vec<Option<JobResult>> = (0..count).map(|_| None).collect();
        let mut failures = Vec::new();
        for batch in batches {
            for (index, result) in batch {
                match result {
                    Ok(result) => results[index] = Some(result),
                    Err(message) => failures.push(JobFailure { index, message }),
                }
            }
        }
        failures.sort_by_key(|failure| failure.index);
        if !failures.is_empty() {
            return Err(RunError::Jobs(failures));
        }
        Ok(results
            .into_iter()
            .map(|result| result.expect("worker omitted a job"))
            .collect())
    }
}

fn panic_message(error: Box<dyn Any + Send>) -> String {
    if let Some(message) = error.downcast_ref::<String>() {
        message.clone()
    } else if let Some(message) = error.downcast_ref::<&str>() {
        (*message).to_owned()
    } else {
        "battle panicked".to_owned()
    }
}
