//! Declared synthetic inputs only. No network calls or personal observations.

use std::collections::{BTreeMap, VecDeque};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use clash_data::json::{self, Json};
use clash_data::wire::*;

use super::provider::*;
use super::snapshots::*;
use super::*;

static TEST_SERIAL: AtomicU64 = AtomicU64::new(0);

struct Directory(PathBuf);

impl Directory {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "clash-lc-synthetic-{}-{}",
            std::process::id(),
            TEST_SERIAL.fetch_add(1, Ordering::Relaxed)
        ));
        std::fs::create_dir(&path).unwrap();
        Self(path)
    }
}

impl Drop for Directory {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).unwrap();
    }
}

fn battle(opponent: &str, attack: bool) -> Json {
    obj([
        ("battleTimestamp", string("20261021T000000Z")),
        ("opponentPlayerTag", string(opponent)),
        ("attack", Json::Bool(attack)),
        ("battleType", string("ranked")),
        ("opponentTownHallLevel", num(16.0)),
        ("armyShareCode", string("u1x0")),
        ("stars", num(0.0)),
        ("destructionPercentage", num(0.0)),
    ])
}

struct SyntheticSource {
    battles: Vec<Json>,
    player: Option<Json>,
    error: Option<ProviderError>,
}

impl BattleLogSource for SyntheticSource {
    fn name(&self) -> &str {
        "declared-synthetic"
    }
    fn fetch(&mut self, _: &str) -> Result<Collection, ProviderError> {
        if let Some(error) = &self.error {
            return Err(error.clone());
        }
        Ok(Collection {
            battles: self.battles.clone(),
            player: self.player.clone(),
            raw_payloads: vec![encode(&arr(self.battles.clone()))],
        })
    }
}

#[test]
fn share_code_known_answer_and_rejection_use_the_shared_decoder() {
    let names: BTreeMap<_, _> = [
        (("troop".to_owned(), 0), "Barbarian".to_owned()),
        (("spell".to_owned(), 0), "Lightning Spell".to_owned()),
        (("hero".to_owned(), 2), "Grand Warden".to_owned()),
        (("pet".to_owned(), 2), "Electro Owl".to_owned()),
        (("equipment".to_owned(), 4), "Eternal Tome".to_owned()),
        (("equipment".to_owned(), 34), "Healing Tome".to_owned()),
    ]
    .into_iter()
    .collect();
    let decoder = Decoder::from_names(names);
    let army = decoder.decode("h2m1p2e4_34u10x0s2x0i1x0d1x0").unwrap();
    let expected = json::parse(r#"{"heroes":[{"hero":"Grand Warden","mode":1,"pet":"Electro Owl","equipment":["Eternal Tome","Healing Tome"]}],"troops":[[10,"Barbarian"]],"spells":[[2,"Lightning Spell"]],"cc_troops":[[1,"Barbarian"]],"cc_spells":[[1,"Lightning Spell"]]}"#).unwrap();
    assert_eq!(army, expected);
    for invalid in ["u0x0", "u-1x0", "u1x-1", "u1x", "u1x0x1"] {
        assert!(decoder.decode(invalid).is_err(), "{invalid}");
    }
    assert_eq!(
        text(
            &list(&decoder.decode("h2q1u1x0").unwrap(), "heroes")[0],
            "hero",
            ""
        ),
        "unparsed:2q1"
    );
    assert_eq!(
        list(&decoder.decode("u1x999").unwrap(), "troops")[0].arr()[1],
        string("troop#999")
    );
}

#[test]
fn collector_preserves_tuple_dedupe_context_and_existing_bytes() {
    let directory = Directory::new();
    let player = obj([
        ("tag", string("#P0")),
        ("leagueTier", obj([("name", string("Legend I"))])),
        ("trophies", num(5000.0)),
        ("name", string("declared synthetic player")),
    ]);
    let defense = battle("#Q0", false);
    let another_opponent = battle("#Y0", false);
    assert_eq!(
        identity(&defense).unwrap(),
        identity(&another_opponent).unwrap()
    );
    let mut source = SyntheticSource {
        battles: vec![
            defense.clone(),
            defense,
            another_opponent,
            battle("#Q0", true),
        ],
        player: Some(player.clone()),
        error: None,
    };
    let report = collect(&mut source, "p0", &directory.0, "2026-10-21T04:00:00-04:00").unwrap();
    assert_eq!(
        (report.added, report.total, report.player_captured),
        (3, 3, true)
    );
    let archive = directory.0.join("battles.jsonl");
    let before = std::fs::read(&archive).unwrap();
    let report = collect(&mut source, "#P0", &directory.0, "2026-10-22").unwrap();
    assert_eq!((report.added, report.total), (0, 3));
    assert_eq!(std::fs::read(&archive).unwrap(), before);
    let rows = clash_data::snapshots::battles(&archive).unwrap();
    assert_eq!(text(&rows[0], "fetched_at", ""), "2026-10-21T08:00:00Z");
    assert_eq!(text(&rows[0], "player_league", ""), "Legend I");
    assert_eq!(text(&rows[0], "provider", ""), "declared-synthetic");
    assert_eq!(
        read(&directory.0.join("player-latest.json")).unwrap(),
        player
    );
    assert_eq!(
        std::fs::read_dir(directory.0.join("players"))
            .unwrap()
            .count(),
        2
    );
    source.player = None;
    assert!(collect(&mut source, "#OTHER", &directory.0, "2026-10-22").is_err());
    assert_eq!(std::fs::read(&archive).unwrap(), before);
    source.error = Some(ProviderError::Unavailable("offline".to_owned()));
    assert!(collect(&mut source, "#P0", &directory.0, "2026-10-22")
        .unwrap_err()
        .contains("unavailable"));
    assert_eq!(std::fs::read(&archive).unwrap(), before);
    source.error = None;
    source.battles = vec![battle("#NEW", false), obj([("attack", num(1.0))])];
    assert!(collect(&mut source, "#P0", &directory.0, "2026-10-22").is_err());
    assert_eq!(std::fs::read(&archive).unwrap(), before);
    std::fs::write(&archive, "malformed existing archive\n").unwrap();
    source.battles.clear();
    assert!(collect(&mut source, "#P0", &directory.0, "2026-10-22").is_err());
    assert_eq!(
        std::fs::read_to_string(archive).unwrap(),
        "malformed existing archive\n"
    );
}

#[test]
fn local_sources_reject_bad_shapes_and_player_mismatches() {
    let directory = Directory::new();
    let path = directory.0.join("input.json");
    let player = directory.0.join("player.json");
    let row = battle("#Q0", false);
    std::fs::write(&path, encode(&obj([("items", arr([row.clone()]))]))).unwrap();
    std::fs::write(&player, r##"{"tag":"#P0"}"##).unwrap();
    let mut source = LocalJson {
        path: path.clone(),
        player: Some(player.clone()),
    };
    let result = source.fetch("#P0").unwrap();
    assert_eq!(result.battles, vec![row.clone()]);
    assert_eq!(
        result.raw_payloads[0],
        std::fs::read_to_string(&path).unwrap()
    );
    assert_eq!(
        result.raw_payloads[1],
        std::fs::read_to_string(&player).unwrap()
    );
    assert_eq!(
        json::parse(&result.raw_payloads[1]).unwrap(),
        result.player.unwrap()
    );
    assert!(source.fetch("#Q0").is_err());
    std::fs::write(&path, format!("{}\n\n{}\n", encode(&row), encode(&row))).unwrap();
    let mut source = LocalJsonLines { path, player: None };
    assert_eq!(source.fetch("#P0").unwrap().battles.len(), 2);
    for invalid in ["null", "{}", r#"{"items":{}}"#, "[null]"] {
        assert!(parse_battles(invalid, false).is_err());
    }
    assert!(parse_battles("{}\nnot-json", true).is_err());
    assert!(parse_battles("null", true).is_err());
    assert!(normalize_tag("#P0?token=x").is_err());
}

struct OfflineTransport {
    responses: VecDeque<Result<HttpResponse, ProviderError>>,
    urls: Vec<String>,
    waits: Vec<Duration>,
}

impl HttpTransport for OfflineTransport {
    fn get(&mut self, url: &str) -> Result<HttpResponse, ProviderError> {
        self.urls.push(url.to_owned());
        self.responses
            .pop_front()
            .expect("unexpected HTTP request in offline test")
    }
    fn wait(&mut self, duration: Duration) {
        self.waits.push(duration);
    }
}

fn response(status: u16, body: &str) -> Result<HttpResponse, ProviderError> {
    Ok(HttpResponse {
        status,
        body: body.to_owned(),
        retry_after: Some(Duration::from_secs(7)),
    })
}

fn http(
    responses: Vec<Result<HttpResponse, ProviderError>>,
) -> ConfiguredKeylessHttpProvider<OfflineTransport> {
    ConfiguredKeylessHttpProvider {
        name: "synthetic-http".to_owned(),
        endpoint: "https://example.invalid/player/{tag}/history".to_owned(),
        player_endpoint: None,
        cursor_parameter: Some("after".to_owned()),
        transport: OfflineTransport {
            responses: responses.into(),
            urls: Vec::new(),
            waits: Vec::new(),
        },
    }
}

#[test]
fn http_retries_paginates_and_reports_keyless_failures_offline() {
    let mut source = http(vec![
        response(429, "limited"),
        response(
            200,
            r#"{"items":[],"paging":{"cursors":{"after":"a+b/="}}}"#,
        ),
        response(200, &encode(&obj([("items", arr([battle("#Q0", false)]))]))),
        response(200, r##"{"tag":"#P0","trophies":42}"##),
    ]);
    source.player_endpoint = Some("https://example.invalid/players/{tag}".to_owned());
    let result = source.fetch("#P0").unwrap();
    assert_eq!(result.battles.len(), 1);
    assert!(result.player.is_some());
    assert!(source.transport.urls[0].contains("%23P0"));
    assert!(source.transport.urls[2].ends_with("?after=a%2Bb%2F%3D"));
    assert_eq!(source.transport.waits, vec![Duration::from_secs(7)]);
    for status in [401, 403, 404, 410] {
        let mut source = http(vec![response(status, "no access")]);
        assert!(matches!(
            source.fetch("#P0"),
            Err(ProviderError::Unsupported(_))
        ));
        assert!(source.transport.waits.is_empty());
    }
    for status in [522, 429] {
        let mut source = http((0..3).map(|_| response(status, "unavailable")).collect());
        let error = source.fetch("#P0").err().unwrap();
        assert!(if status == 522 {
            matches!(error, ProviderError::Unavailable(_))
        } else {
            matches!(error, ProviderError::RateLimited(_))
        });
        assert_eq!(source.transport.urls.len(), 3);
        assert_eq!(source.transport.waits.len(), 2);
    }
    let mut source = http(vec![response(200, "not JSON")]);
    assert!(matches!(
        source.fetch("#P0"),
        Err(ProviderError::InvalidData(_))
    ));
    let mut source = http(Vec::new());
    source.endpoint = "https://user:secret@example.invalid/{tag}".to_owned();
    assert!(matches!(
        source.fetch("#P0"),
        Err(ProviderError::Unsupported(_))
    ));
    assert!(source.transport.urls.is_empty());
    let page = r#"{"items":[],"paging":{"cursors":{"after":"same"}}}"#;
    let mut source = http(vec![response(200, page), response(200, page)]);
    assert!(matches!(
        source.fetch("#P0"),
        Err(ProviderError::InvalidData(_))
    ));
}

const LAYOUT: &str = r#"{"name":"declared synthetic setup","buildings":[{"key":"banner","x":1,"y":2},{"key":"cannon","x":3.5,"y":4}],"heroes":["Barbarian King"],"cc_troops":{},"walls":[[5,6]],"traps":[{"key":"bomb","x":7,"y":8}],"trap_levels":{"bomb":1}}"#;
const LEVELS: &str = r#"{"levels":{"cannon":2,"trap:bomb":2},"hero_levels":{"Barbarian King":3},"wall_level":null,"wall_levels":[{"x":5,"y":6,"level":4}],"trap_levels":{"bomb":3}}"#;

fn snapshot_options(from: &str) -> SnapshotOptions<'_> {
    SnapshotOptions {
        from,
        to: None,
        period: "league-day",
        source: "screenshot",
        confidence: "medium",
        notes: "declared synthetic fixture",
        provenance: None,
    }
}

#[test]
fn frozen_setup_matches_recorded_contract_and_preserves_numeric_tokens() {
    let frozen = freeze_layout(LAYOUT, LEVELS).unwrap();
    // Independently written expected canonical payload for the frozen Python contract.
    let expected = r#"{"buildings":[{"key":"banner","x":1,"y":2},{"key":"cannon","x":3.5,"y":4}],"cc_troops":{},"guardian":"Longshot","hero_banners":[{"hero":"Barbarian King","x":1,"y":2}],"hero_levels":{"Barbarian King":3},"heroes":["Barbarian King"],"levels":{"cannon":2,"trap:bomb":3},"name":"declared synthetic setup","town_hall":16,"trap_levels":{"bomb":3},"traps":[{"key":"bomb","x":7,"y":8}],"wall_level":null,"wall_levels":[{"level":4,"x":5,"y":6}],"walls":[[5,6]]}"#;
    assert_eq!(frozen, expected);
    assert_ne!(
        sha256(frozen.as_bytes()),
        sha256(
            canonical(&encode(&json::parse(&frozen).unwrap()))
                .unwrap()
                .as_bytes()
        )
    );
    for invalid in [
        LEVELS.replace("\"cannon\":2", "\"cannon\":2.0"),
        LEVELS.replace("\"cannon\":2", "\"cannon\":true"),
        LEVELS.replace("\"level\":4", "\"level\":0"),
        LEVELS.replace("\"x\":5", "\"x\":9"),
    ] {
        assert!(freeze_layout(LAYOUT, &invalid).is_err());
    }
    assert!(freeze_layout(
        &LAYOUT.replace(
            "[\"Barbarian King\"]",
            "[\"Barbarian King\",\"Barbarian King\"]"
        ),
        LEVELS
    )
    .is_err());
}

#[test]
fn snapshot_recording_closes_periods_and_shared_reader_verifies_hashes() {
    let directory = Directory::new();
    let history_path = directory.0.join("history.json");
    let first = add_snapshot(
        &directory.0,
        &history_path,
        LAYOUT,
        LEVELS,
        &snapshot_options("2026-10-21T04:00:00-04:00"),
    )
    .unwrap();
    assert_eq!(text(&first, "from", ""), "2026-10-21T08:00:00Z");
    let second = add_snapshot(
        &directory.0,
        &history_path,
        LAYOUT,
        LEVELS,
        &snapshot_options("2026-10-22T08:00:00Z"),
    )
    .unwrap();
    let history = read_history(&history_path).unwrap();
    assert_eq!(
        text(&list(&history, "snapshots")[0], "to", ""),
        "2026-10-22T08:00:00Z"
    );
    assert_eq!(
        snapshot_for_battle(&history, "20261022T080000Z").unwrap(),
        Some(&list(&history, "snapshots")[1])
    );
    let loaded =
        clash_data::snapshots::setup(&directory.0, &history, "20261022T080000Z", None, true)
            .unwrap();
    assert_eq!(loaded.2, "frozen_snapshot");
    assert_eq!(text(&loaded.0, "name", ""), "declared synthetic setup");
    assert!(snapshot_for_battle(&history, "20261021T075959Z")
        .unwrap()
        .is_none());
    let bytes = std::fs::read(&history_path).unwrap();
    assert!(add_snapshot(
        &directory.0,
        &history_path,
        LAYOUT,
        LEVELS,
        &snapshot_options("2026-10-21T12:00:00Z")
    )
    .is_err());
    assert_eq!(std::fs::read(&history_path).unwrap(), bytes);
    let archive = resolve(&directory.0, text(&second, "layout", ""));
    std::fs::write(&archive, "{}").unwrap();
    assert_eq!(
        clash_data::snapshots::setup(&directory.0, &history, "20261022T080000Z", None, true)
            .unwrap_err(),
        "snapshot_hash_mismatch"
    );
    for when in [
        "1969-12-31T23:59:59.123456Z",
        "2000-02-29",
        "20261021T183738.123Z",
    ] {
        assert_eq!(
            timestamp(&utc(timestamp(when).unwrap()).unwrap()).unwrap(),
            timestamp(when).unwrap()
        );
    }
}

#[test]
fn snapshot_provenance_and_report_exclude_uncovered_and_duplicate_defenses() {
    let directory = Directory::new();
    let path = directory.0.join("history.json");
    let missing = LEVELS.replace("\"cannon\":2,", "");
    let entry = add_snapshot(
        &directory.0,
        &path,
        LAYOUT,
        &missing,
        &snapshot_options("2026-10-21"),
    )
    .unwrap();
    assert_eq!(
        text(entry.at("fields").at("levels"), "confidence", ""),
        "unknown"
    );
    let override_fields = obj([(
        "levels",
        obj([
            ("source", string("screenshot")),
            ("confidence", string("high")),
        ]),
    )]);
    let mut options = snapshot_options("2026-10-22");
    options.provenance = Some(&override_fields);
    assert!(add_snapshot(&directory.0, &path, LAYOUT, &missing, &options).is_err());
    let history = read_history(&path).unwrap();
    let first = battle("#Q0", false);
    let mut second = battle("#Y0", false);
    put(&mut second, "stars", num(3.0));
    put(&mut second, "destructionPercentage", num(100.0));
    let mut uncovered = battle("#OLD", false);
    put(
        &mut uncovered,
        "battleTimestamp",
        string("20261020T000000Z"),
    );
    let result = report(
        &history,
        &[first.clone(), first, second, uncovered, battle("#Q0", true)],
    )
    .unwrap();
    let row = &list(&result, "snapshots")[0];
    assert_eq!(number(row, "ranked_defenses", -1.0), 2.0);
    assert_eq!(number(row, "mean_defender_trophies", -1.0), 20.0);
    assert_eq!(row.at("interval_95"), &arr([num(0.0), num(40.0)]));
    assert_eq!(number(&result, "uncovered_defenses", -1.0), 1.0);
}

#[test]
fn share_codes_require_content_and_unique_sections() {
    let decoder = Decoder::from_names(BTreeMap::new());
    for code in [
        "",
        "garbage",
        "u1x0u2x1",
        "s1x0u1x0s2x1",
        "h1h2",
        "u",
        "hiuds",
        "junku1x0",
    ] {
        assert!(decoder.decode(code).is_err(), "accepted {code:?}");
    }
    assert!(decoder.decode("u1x0").is_ok());
}

#[test]
fn decode_cli_propagates_missing_or_invalid_battle_identity() {
    let directory = Directory::new();
    let input = directory.0.join("battles.json");
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    for timestamp in [None, Some(num(42.0)), Some(string(""))] {
        let mut record = obj([
            ("battleType", string("ranked")),
            ("armyShareCode", string("u1x0")),
        ]);
        if let Some(timestamp) = timestamp {
            put(&mut record, "battleTimestamp", timestamp);
        }
        write(&input, &arr([record])).unwrap();
        let error = super::cli::cli(&[
            "decode".to_owned(),
            input.display().to_string(),
            "--root".to_owned(),
            root.display().to_string(),
        ])
        .unwrap_err();
        assert!(error.contains("timestamp"), "{error}");
    }
}
