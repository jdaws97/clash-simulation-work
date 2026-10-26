//! Declared synthetic fixtures. No provider, media download or private transcript
//! is needed for these known-answer checks.
use clash_data::json::{self, Json};
use clash_data::wire::{self, list, obj, string, text};
use clash_playbook_tools::{
    citations, complete, gaps, harvest, research, schema, transcripts, verify,
};
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);
struct Temporary(PathBuf);
impl Temporary {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "clash-playbook-synthetic-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        Self(path)
    }
    fn path(&self) -> &Path {
        &self.0
    }
    fn write(&self, name: &str, contents: &str) -> PathBuf {
        let path = self.0.join(name);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, contents).unwrap();
        path
    }
}
impl Drop for Temporary {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn parse(source: &str) -> Json {
    json::parse(source).unwrap()
}
fn captions() -> citations::Lines {
    vec![
        (10.0, "Release the synthetic knights".to_owned()),
        (20.0, "then cast a frosty spell".to_owned()),
        (30.0, "beside the center".to_owned()),
        (40.0, "and save the final charge".to_owned()),
        (70.0, "Release the synthetic knights".to_owned()),
    ]
}
fn save_transcript(directory: &Temporary, video: &str) {
    directory.write(&format!("{video}.json"), r#"{"lines":[[10,"Release the synthetic knights"],[20,"then cast a frosty spell"],[30,"beside the center"],[40,"and save the final charge"]]}"#);
}

#[test]
fn frozen_normalization_location_and_timing_answers() {
    assert_eq!(
        citations::norm("  İCE—The QUEEN\t42% / café! "),
        "i ce the queen 42 caf"
    );
    assert!(
        citations::locate(&vec![(0.0, "twice the queen".to_owned())], "ice the queen").is_empty()
    );
    assert!(citations::locate(&captions(), "cast").is_empty());
    assert_eq!(
        citations::locate(
            &captions(),
            "knights then cast a frosty spell beside the center and save"
        ),
        vec![10.0]
    );
    assert_eq!(
        citations::locate(&captions(), "then cast a frosty spell"),
        vec![20.0]
    );
    assert_eq!(
        citations::verified_time(&captions(), "release the synthetic knights", Some(40.0)),
        Some(10.0)
    );
    assert_eq!(
        citations::verified_time(&captions(), "release the synthetic knights", Some(40.1)),
        Some(70.0)
    );
    assert_eq!(
        citations::verified_time(&captions(), "then cast a frosty spell", Some(50.0)),
        Some(20.0)
    );
    assert_eq!(
        citations::verified_time(&captions(), "then cast a frosty spell", Some(50.001)),
        None
    );
    let five: citations::Lines = (0..5).map(|i| (i as f64, format!("word{i}"))).collect();
    assert!(citations::locate(&five, "word0 word1 word2 word3 word4").is_empty());
    assert_eq!(
        citations::locate(&five, "word1 word2 word3 word4"),
        vec![1.0]
    );
}

#[test]
fn frozen_reply_parser_and_extraction_verdict() {
    let raw = r#"prose {bad} ```json
    {"video_id":"synthetic","steps":[{"quote":"release the synthetic knights","t":40},{"quote":"not in this transcript","t":10}],"rules":[{"quote":"then cast a frosty spell","t":"20"}],"spell_policy":[{"quote":"beside the center","t":100}]}
    ```"#;
    let checked = citations::check_extracted(raw, "synthetic", &captions()).unwrap();
    assert_eq!(
        checked.get("check"),
        Some(&parse(r#"{"kept":2,"dropped":2}"#))
    );
    assert_eq!(
        list(&checked, "steps")[0].get("verified_t"),
        Some(&Json::Num(10.0))
    );
    assert_eq!(
        list(&checked, "rules")[0].get("verified_t"),
        Some(&Json::Num(20.0))
    );
    assert_eq!(
        citations::check_extracted("no json", "synthetic", &captions()).unwrap(),
        parse(r#"{"video_id":"synthetic","parse_error":true}"#)
    );
    assert!(citations::parse_reply(r#"{"note":"}"}"#).is_none());
}

#[test]
fn vocabulary_tracks_actual_rust_executor() {
    let source = include_str!("../../clash-engine/src/playbook.rs");
    let action = source
        .split("impl Action {")
        .nth(1)
        .unwrap()
        .split("#[derive")
        .next()
        .unwrap();
    let anchor = source
        .split("fn anchor(")
        .nth(1)
        .unwrap()
        .split("fn totem_anchor(")
        .next()
        .unwrap();
    fn match_keys(source: &str) -> Vec<String> {
        let mut keys = source
            .lines()
            .filter_map(|line| {
                let line = line.trim().strip_prefix('"')?;
                let (key, suffix) = line.split_once('"')?;
                suffix
                    .trim_start()
                    .starts_with("=>")
                    .then(|| key.to_owned())
            })
            .collect::<Vec<_>>();
        keys.sort();
        keys
    }
    let mut actions: Vec<_> = schema::ACTIONS.iter().map(|s| s.to_string()).collect();
    actions.sort();
    assert_eq!(match_keys(action), actions);
    let mut anchors: Vec<_> = schema::ANCHORS.iter().map(|s| s.to_string()).collect();
    anchors.sort();
    assert_eq!(match_keys(anchor), anchors);
    let trigger = source
        .split("impl Trigger {")
        .nth(1)
        .unwrap()
        .split("fn unit_condition")
        .next()
        .unwrap();
    let mut predicates = trigger
        .split("w.get(\"")
        .skip(1)
        .map(|s| s.split('"').next().unwrap().to_owned())
        .collect::<Vec<_>>();
    predicates.sort();
    let mut expected: Vec<_> = schema::PREDICATES.iter().map(|s| s.to_string()).collect();
    expected.sort();
    assert_eq!(predicates, expected);
}

#[test]
fn nested_dependencies_duplicates_and_cycles_are_checked() {
    let valid = parse(
        r#"{"steps":[{"id":"a","action":"deploy","at":"cohort:b","when":{"t":0}},{"id":"b","action":"ability","when":{"all":[{"succeeded":"a"},{"effect_active":"a"}]},"until":{"any":[{"after":"a"},{"objective":"townhall","state":"dead"}]}}]}"#,
    );
    assert!(schema::validate(&valid).is_empty());
    let invalid = parse(
        r#"{"steps":[{"id":"a","action":"deploy","when":{"after":"b"}},{"id":"b","action":"spell","when":{"after":"a"},"until":{"all":[{"after":"lost"}]}},{"id":"b","action":"ability"}]}"#,
    );
    let errors = schema::validate(&invalid).join(";");
    assert!(errors.contains("unknown dependency lost"));
    assert!(errors.contains("duplicate id"));
    assert!(errors.contains("cyclic"));
    let unknown_effect = parse(
        r#"{"steps":[{"id":"a","action":"spell","when":{"effect_expired":"missing"},"recall_from":"lost","after_success":"absent"}]}"#,
    );
    let errors = schema::validate(&unknown_effect).join(";");
    for name in ["missing", "lost", "absent"] {
        assert!(errors.contains(&format!("unknown dependency {name}")));
    }
    assert!(
        schema::validate(&parse(
            r#"{"steps":[{"id":"a","action":"wait","when":{"typo":1}}]}"#
        ))
        .len()
            > 0
    );
}

#[test]
fn every_committed_playbook_uses_executor_vocabulary_and_valid_dependencies() {
    let directory = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../data/playbooks");
    let mut checked = 0;
    for entry in fs::read_dir(directory).unwrap() {
        let path = entry.unwrap().path();
        if path.extension().and_then(|s| s.to_str()) != Some("json") {
            continue;
        }
        let playbook = parse(&fs::read_to_string(&path).unwrap());
        assert_eq!(
            schema::validate(&playbook),
            Vec::<String>::new(),
            "{}",
            path.display()
        );
        checked += 1;
    }
    assert!(checked >= 12);
}

#[test]
fn consolidated_known_verdict_and_source_only_strict_output() {
    let directory = Temporary::new();
    save_transcript(&directory, "v1");
    save_transcript(&directory, "v2");
    let raw = r#"{"sources":["v1"],"steps":[
        {"id":"a","action":"deploy","cite":[{"video":"v1","quote":"release the synthetic knights","t":10}]},
        {"id":"b","action":"wait","cite":[{"video":"v1","quote":"release the synthetic knights","t":10}]},
        {"id":"c","action":"spell","cite":[{"video":"v1","quote":"absent quotation","t":10}]},
        {"id":"d","action":"spell","when":{"after":"a"},"cite":[{"video":"v2","quote":"then cast a frosty spell","t":20}]}],
        "base_reading":[]}"#;
    let mut transcripts = citations::Transcripts::new(directory.path());
    let legacy = verify::consolidate(raw, &mut transcripts, true).unwrap();
    assert_eq!(
        legacy.get("check"),
        Some(&parse(
            r#"{"steps_kept":2,"steps_dropped":2,"reasons":{"action wait":1,"no verified citation":1},"dangling_after":[]}"#
        ))
    );
    let strict = verify::consolidate(raw, &mut transcripts, false).unwrap();
    assert_eq!(list(&strict, "steps").len(), 1);
    assert!(schema::validate(&strict).is_empty());
    let dangling = raw.replace(r#""after":"a""#, r#""after":"lost""#);
    assert_eq!(
        list(
            verify::consolidate(&dangling, &mut transcripts, true)
                .unwrap()
                .get("check")
                .unwrap(),
            "dangling_after"
        ),
        &[string("d")]
    );
}

#[test]
fn transcript_json3_and_timedtext_known_answers() {
    let xml = r#"<timedtext><body><p t="12250"><s>Synthetic &amp; </s><s>frost</s></p><p t="20000"> a  second &#x63;aption </p></body></timedtext>"#;
    let parsed = transcripts::parse_timedtext(xml, "v1").unwrap();
    assert_eq!(
        citations::lines(&parsed).unwrap(),
        vec![
            (12.2, "Synthetic & frost".to_owned()),
            (20.0, "a second caption".to_owned())
        ]
    );
    let json3 = parse(
        r#"{"events":[{"tStartMs":12250,"segs":[{"utf8":"Synthetic & "},{"utf8":"frost"}]},{"tStartMs":20000,"segs":[{"utf8":" a\n second caption "}]},{"tStartMs":21000}]}"#,
    );
    assert_eq!(
        citations::lines(&transcripts::normalize(&json3, "v1").unwrap()).unwrap(),
        citations::lines(&parsed).unwrap()
    );
    assert_eq!(transcripts::normalize(&parsed, "v1").unwrap(), parsed);
    assert!(transcripts::parse_timedtext("<other/>", "v1").is_err());
}

#[test]
fn video_discovery_age_filter_and_family_union_match_frozen_behavior() {
    assert_eq!(harvest::age_days("Streamed 2 months ago"), Some(60.8));
    assert_eq!(harvest::age_days("1 year ago"), Some(365.0));
    assert_eq!(harvest::age_days("yesterday"), None);
    let response = parse(
        r#"{"contents":[{"videoRenderer":{"videoId":"v1","title":{"runs":[{"text":"Synthetic "},{"text":"guide"}]},"ownerText":{"runs":[{"text":"Synthetic channel"}]},"publishedTimeText":{"simpleText":"2 weeks ago"},"lengthText":{"simpleText":"3:20"}}}]}"#,
    );
    let rows = harvest::discover(&response);
    let mut index = Vec::new();
    assert_eq!(
        harvest::merge(
            &mut index,
            rows.clone(),
            "dragon",
            "first",
            "2026-10-25",
            183.0
        )
        .unwrap(),
        1
    );
    assert_eq!(
        harvest::merge(&mut index, rows, "yeti", "second", "2026-10-25", 183.0).unwrap(),
        0
    );
    assert_eq!(
        list(&index[0], "families"),
        &[string("dragon"), string("yeti")]
    );
    assert_eq!(text(&index[0], "query", ""), "first");
    assert_eq!(wire::number(&index[0], "age_days", 0.0), 14.0);
    assert_eq!(
        harvest::merge(
            &mut index,
            vec![
                parse(r#"{"id":"old","age":"1 year ago"}"#),
                parse(r#"{"id":"unknown"}"#)
            ],
            "dragon",
            "q",
            "2026-10-25",
            183.0
        )
        .unwrap(),
        0
    );
    let directory = Temporary::new();
    let path = directory.path().join("videos.jsonl");
    harvest::save(&path, &index).unwrap();
    assert_eq!(harvest::read_index(&path).unwrap(), index);
}

#[test]
fn completion_order_and_rejection_preserve_cited_provenance() {
    let directory = Temporary::new();
    save_transcript(&directory, "v1");
    let playbook = parse(
        r#"{"sources":["v1"],"steps":[{"id":"a","action":"deploy","when":{"t":0}},{"id":"sibling","action":"spell","when":{"after":"a"}},{"id":"end","action":"ability"}]}"#,
    );
    let reply = r#"{"add_steps":[{"id":"added","action":"deploy","when":{"after":"a"},"cite":[{"video":"v1","quote":"release the synthetic knights","t":10}]},{"id":"foreign","action":"deploy","cite":[{"video":"other","quote":"release the synthetic knights","t":10}]}]}"#;
    let mut transcripts = citations::Transcripts::new(directory.path());
    let (merged, receipt) = complete::merge(&playbook, reply, &mut transcripts).unwrap();
    assert_eq!(
        list(&merged, "steps")
            .iter()
            .map(|s| text(s, "id", ""))
            .collect::<Vec<_>>(),
        ["a", "sibling", "added", "end"]
    );
    assert_eq!(list(&receipt, "kept"), &[string("added")]);
    assert_eq!(list(&receipt, "rejected").len(), 1);
    assert_eq!(
        list(&merged, "steps")[2].get("completion"),
        Some(&Json::Bool(true))
    );
    let (unchanged, rejected) = complete::merge(&merged, reply, &mut transcripts).unwrap();
    assert!(list(&rejected, "kept").is_empty());
    assert_eq!(unchanged, merged);
}

#[test]
fn timing_gap_medians_and_exclusive_quartiles_match_recorded_algorithm() {
    let directory = Temporary::new();
    directory.write("transcripts/v1.json", r#"{"lines":[[0,"synthetic caption zero"],[2,"synthetic caption first"],[8,"synthetic caption second"],[16,"synthetic caption third"],[30,"synthetic caption fourth"]]}"#);
    let times = [0.0, 2.0, 8.0, 16.0, 30.0];
    let quotes = ["zero", "first", "second", "third", "fourth"];
    let groups = ["main", "main", "charge", "charge", "main"];
    let steps = (0..5)
        .map(|i| {
            obj([
                ("id", string(format!("s{i}"))),
                ("group", string(groups[i])),
                (
                    "when",
                    if i == 0 {
                        obj([("t", wire::num(0))])
                    } else {
                        obj([("after", string(format!("s{}", i - 1)))])
                    },
                ),
                (
                    "cite",
                    Json::Arr(vec![obj([
                        ("video", string("v1")),
                        ("t", wire::num(times[i])),
                        ("quote", string(format!("synthetic caption {}", quotes[i]))),
                    ])]),
                ),
            ])
        })
        .collect();
    directory.write(
        "playbooks/synthetic.json",
        &wire::encode(&obj([("steps", Json::Arr(steps))])),
    );
    let mut transcripts = citations::Transcripts::new(&directory.path().join("transcripts"));
    let (output, tally) =
        gaps::measure(&directory.path().join("playbooks"), &mut transcripts).unwrap();
    assert_eq!(
        output.get("same_group"),
        Some(&parse(r#"{"median":5,"n":2,"quartiles":[0.5,5,9.5]}"#))
    );
    assert_eq!(
        output.get("group_change"),
        Some(&parse(r#"{"median":10,"n":2,"quartiles":[4,10,16]}"#))
    );
    assert_eq!(tally, obj([("located in transcript", wire::num(5))]));
}

#[test]
fn queue_names_thresholds_and_audit_skips_are_preserved() {
    let directory = Temporary::new();
    let queue = directory.write(
        "queue.tsv",
        "technique\tQueen charge / Queen walk\r\nspell\tFrost / spell\n",
    );
    let jobs =
        research::usage_jobs(&queue, "{KIND}: {NAME}", &directory.path().join("usage")).unwrap();
    assert_eq!(jobs[0].id, "queen-charge-queen-walk");
    assert_eq!(jobs[0].prompt, "technique: Queen charge / Queen walk");
    directory.write("usage/queen-charge-queen-walk.md", &"a".repeat(1500));
    assert_eq!(
        research::status(&jobs).arr()[0].get("complete"),
        Some(&Json::Bool(false))
    );
    directory.write(
        "usage/queen-charge-queen-walk.md",
        &format!("# Synthetic title\n{}", "a".repeat(1501)),
    );
    let skip = directory.write("skip-event.txt", "queen-charge-queen-walk\n");
    assert!(research::audit_jobs(
        &directory.path().join("usage"),
        "{SLUG} {NAME}",
        &directory.path().join("gaps"),
        Some(&skip)
    )
    .unwrap()
    .is_empty());
    directory.write("collision.tsv", "a\tFrost / spell\nb\tFrost spell\n");
    assert!(research::usage_jobs(
        &directory.path().join("collision.tsv"),
        "",
        directory.path()
    )
    .is_err());
}

#[cfg(unix)]
#[test]
fn external_jobs_resume_reject_failures_and_invalidate_changed_inputs() {
    let directory = Temporary::new();
    let queue = directory.write("queue.tsv", "synthetic\tSample subject\n");
    let mut jobs = research::usage_jobs(&queue, "{NAME}", directory.path()).unwrap();
    jobs[0].minimum_bytes = 3;
    let provider = research::Provider {
        executable: "sh".to_owned(),
        arguments: vec!["-c".to_owned(), "printf 'synthetic answer'".to_owned()],
    };
    let first = research::run(&jobs, &provider, 2, 1).unwrap();
    assert_eq!(first.arr()[0].get("resumed"), Some(&Json::Bool(false)));
    let second = research::run(&jobs, &provider, 2, 1).unwrap();
    assert_eq!(second.arr()[0].get("resumed"), Some(&Json::Bool(true)));
    jobs[0].input_hash = "changed".to_owned();
    let third = research::run(&jobs, &provider, 1, 1).unwrap();
    assert_eq!(third.arr()[0].get("resumed"), Some(&Json::Bool(false)));
    let failing = research::Provider {
        executable: "sh".to_owned(),
        arguments: vec!["-c".to_owned(), "printf 'bad'; exit 1".to_owned()],
    };
    let failure = research::run(&jobs, &failing, 1, 2).unwrap();
    assert_eq!(text(&failure.arr()[0], "status", ""), "failed");
    assert_eq!(
        fs::read_to_string(&jobs[0].output).unwrap(),
        "synthetic answer"
    );
    assert_eq!(
        research::status(&jobs).arr()[0].get("complete"),
        Some(&Json::Bool(false))
    );
}

#[test]
fn cli_offline_import_consolidate_verify_and_queue_import() {
    let directory = Temporary::new();
    let captions = directory.write(
        "synthetic.json3",
        r#"{"events":[{"tStartMs":10000,"segs":[{"utf8":"Release the synthetic knights"}]}]}"#,
    );
    let transcript_dir = directory.path().join("transcripts");
    let run = |arguments: Vec<String>| clash_playbook_tools::cli(&arguments).unwrap();
    run(vec![
        "transcript".to_owned(),
        "v1".to_owned(),
        "--input".to_owned(),
        captions.display().to_string(),
        "--transcripts".to_owned(),
        transcript_dir.display().to_string(),
    ]);
    let raw = directory.write("synthetic.raw", r#"{"family":"synthetic","sources":["v1"],"steps":[{"id":"first","action":"deploy","when":{"t":0},"cite":[{"video":"v1","t":10,"quote":"Release the synthetic knights"}]}]}"#);
    let playbooks = directory.path().join("playbooks");
    run(vec![
        "consolidate".to_owned(),
        "--input".to_owned(),
        raw.display().to_string(),
        "--transcripts".to_owned(),
        transcript_dir.display().to_string(),
        "--out".to_owned(),
        playbooks.join("synthetic.json").display().to_string(),
    ]);
    run(vec![
        "verify".to_owned(),
        "--all".to_owned(),
        "--transcripts".to_owned(),
        transcript_dir.display().to_string(),
        "--playbooks".to_owned(),
        playbooks.display().to_string(),
    ]);
    let queue = directory.write("subjects.tsv", "technique\tSynthetic knights\r\n");
    let out = directory.path().join("queue.tsv");
    run(vec![
        "queue".to_owned(),
        "import".to_owned(),
        "--input".to_owned(),
        queue.display().to_string(),
        "--out".to_owned(),
        out.display().to_string(),
    ]);
    assert_eq!(
        fs::read_to_string(out).unwrap(),
        "technique\tSynthetic knights\n"
    );
}
