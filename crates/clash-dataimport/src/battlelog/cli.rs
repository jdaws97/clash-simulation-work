use std::collections::BTreeMap;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use clash_data::wire::*;

use super::provider::*;
use super::{collect, snapshots, Decoder};

const USAGE: &str = "clash dataimport battlelog decode CODE|FILE --root ROOT [--jsonl] | fetch|collect --tag TAG --provider local-json|local-jsonl|stdin|http [--input FILE] [--player FILE] [--endpoint HTTPS_TEMPLATE --provider-name NAME --player-endpoint HTTPS_TEMPLATE --cursor-parameter after] --out PRIVATE_DIR | snapshot add|list|for-battle|report --history FILE [--root ROOT] ...";

struct Options {
    values: BTreeMap<String, String>,
    positional: Vec<String>,
    json_lines: bool,
}

impl Options {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut options = Self {
            values: BTreeMap::new(),
            positional: Vec::new(),
            json_lines: false,
        };
        let mut args = args.iter();
        while let Some(argument) = args.next() {
            if argument == "--jsonl" {
                options.json_lines = true;
            } else if argument == "--json" {
                // Snapshot reports always emit machine-readable JSON.
            } else if argument.starts_with("--") {
                if ![
                    "--tag",
                    "--provider",
                    "--input",
                    "--player",
                    "--endpoint",
                    "--provider-name",
                    "--player-endpoint",
                    "--cursor-parameter",
                    "--out",
                    "--fetched-at",
                    "--root",
                    "--history",
                    "--levels",
                    "--from",
                    "--to",
                    "--period",
                    "--notes",
                    "--source",
                    "--confidence",
                    "--provenance",
                    "--battles",
                ]
                .contains(&argument.as_str())
                {
                    return Err(format!("unknown option {argument}"));
                }
                let value = args
                    .next()
                    .filter(|value| !value.starts_with("--"))
                    .ok_or_else(|| format!("missing value for {argument}"))?;
                if options
                    .values
                    .insert(argument.clone(), value.clone())
                    .is_some()
                {
                    return Err(format!("duplicate option {argument}"));
                }
            } else {
                options.positional.push(argument.clone());
            }
        }
        Ok(options)
    }

    fn required(&self, key: &str) -> Result<&str, String> {
        self.values
            .get(key)
            .map(String::as_str)
            .ok_or_else(|| format!("{key} is required"))
    }

    fn value<'a>(&'a self, key: &str, fallback: &'a str) -> &'a str {
        self.values.get(key).map_or(fallback, String::as_str)
    }

    fn path(&self, key: &str) -> Result<PathBuf, String> {
        Ok(PathBuf::from(self.required(key)?))
    }
}

/// Explicit providers and private output paths; no player, endpoint or output defaults.
pub fn cli(args: &[String]) -> Result<(), String> {
    if args.is_empty() || args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!("{USAGE}");
        return Ok(());
    }
    let options = Options::parse(&args[1..])?;
    match args[0].as_str() {
        "decode" => {
            let root = options.path("--root")?;
            let decoder = Decoder::load(&root)?;
            let input = options.positional.first().ok_or(USAGE)?;
            let path = PathBuf::from(input);
            let output = if path.is_file() {
                let raw = std::fs::read_to_string(&path).map_err(|error| error.to_string())?;
                let battles = parse_battles(&raw, options.json_lines || input.ends_with(".jsonl"))
                    .map_err(|error| error.to_string())?;
                arr(battles
                    .iter()
                    .filter(|battle| text(battle, "battleType", "") == "ranked")
                    .map(|battle| {
                        let battle_id = super::identity(battle)?;
                        let army = decoder.decode(text(battle, "armyShareCode", ""))?;
                        Ok::<_, String>(obj([("battle_id", string(battle_id)), ("army", army)]))
                    })
                    .collect::<Result<Vec<_>, _>>()?)
            } else {
                decoder.decode(input)?
            };
            println!("{}", encode(&output));
            Ok(())
        }
        "fetch" | "collect" => {
            let tag = options.required("--tag")?;
            let directory = options.path("--out")?;
            let player = options.values.get("--player").map(PathBuf::from);
            let mut source: Box<dyn BattleLogSource> = match options.required("--provider")? {
                "local-json" => Box::new(LocalJson {
                    path: options.path("--input")?,
                    player,
                }),
                "local-jsonl" => Box::new(LocalJsonLines {
                    path: options.path("--input")?,
                    player,
                }),
                "stdin" => Box::new(Stdin {
                    json_lines: options.json_lines,
                    player,
                }),
                "http" => {
                    if player.is_some() {
                        return Err("HTTP player capture uses --player-endpoint; import local context with a local provider".to_owned());
                    }
                    Box::new(ConfiguredKeylessHttpProvider {
                        name: options.required("--provider-name")?.to_owned(),
                        endpoint: options.required("--endpoint")?.to_owned(),
                        player_endpoint: options.values.get("--player-endpoint").cloned(),
                        cursor_parameter: options.values.get("--cursor-parameter").cloned(),
                        transport: CurlTransport,
                    })
                }
                name => {
                    return Err(format!(
                        "unsupported provider {name}; only keyless providers are supported"
                    ))
                }
            };
            let fetched_at = if let Some(when) = options.values.get("--fetched-at") {
                when.clone()
            } else {
                let duration = SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .map_err(|error| error.to_string())?;
                snapshots::utc(
                    i64::try_from(duration.as_micros()).map_err(|error| error.to_string())?,
                )?
            };
            let report = collect(source.as_mut(), tag, &directory, &fetched_at)?;
            println!(
                "{}",
                encode(&obj([
                    ("added", num(report.added as f64)),
                    ("total", num(report.total as f64)),
                    (
                        "player_captured",
                        clash_data::json::Json::Bool(report.player_captured)
                    ),
                ]))
            );
            Ok(())
        }
        "snapshot" => snapshot(&options),
        _ => Err(USAGE.to_owned()),
    }
}

fn snapshot(options: &Options) -> Result<(), String> {
    let history_path = options.path("--history")?;
    let command = options
        .positional
        .first()
        .map(String::as_str)
        .ok_or(USAGE)?;
    let output = match command {
        "add" => {
            let root = options
                .path("--root")?
                .canonicalize()
                .map_err(|error| error.to_string())?;
            let layout_path = options
                .positional
                .get(1)
                .ok_or("snapshot add requires a layout file")?;
            let layout = std::fs::read_to_string(layout_path).map_err(|error| error.to_string())?;
            let levels = std::fs::read_to_string(options.path("--levels")?)
                .map_err(|error| error.to_string())?;
            let provenance = options
                .values
                .get("--provenance")
                .map(|path| read(&PathBuf::from(path)))
                .transpose()?;
            snapshots::add_snapshot(
                &root,
                &history_path,
                &layout,
                &levels,
                &snapshots::SnapshotOptions {
                    from: options.required("--from")?,
                    to: options.values.get("--to").map(String::as_str),
                    period: options.value("--period", "tournament"),
                    notes: options.required("--notes")?,
                    source: options.value("--source", "user-entered"),
                    confidence: options.value("--confidence", "unknown"),
                    provenance: provenance.as_ref(),
                },
            )?
        }
        "list" => {
            let history = snapshots::read_history(&history_path)?;
            let mut entries = list(&history, "snapshots").to_vec();
            for entry in &entries {
                super::timestamp(super::required_text(entry, "from")?)?;
            }
            entries.sort_by_key(|entry| {
                super::timestamp(text(entry, "from", "")).expect("validated start")
            });
            arr(entries)
        }
        "for-battle" | "report" => {
            let history = snapshots::read_history(&history_path)?;
            let path = options.path("--battles")?;
            let raw = std::fs::read_to_string(&path).map_err(|error| error.to_string())?;
            let battles = parse_battles(
                &raw,
                path.extension()
                    .is_some_and(|extension| extension == "jsonl"),
            )
            .map_err(|error| error.to_string())?;
            if command == "report" {
                snapshots::report(&history, &battles)?
            } else {
                let when = options
                    .positional
                    .get(1)
                    .ok_or("for-battle requires a timestamp")?;
                let time = super::timestamp(when)?;
                if !battles.iter().any(|battle| {
                    text(battle, "battleType", "") == "ranked"
                        && battle.get("attack") == Some(&clash_data::json::Json::Bool(false))
                        && super::timestamp(text(battle, "battleTimestamp", ""))
                            .is_ok_and(|when| when == time)
                }) {
                    return Err("no ranked defense at the requested timestamp".to_owned());
                }
                let entry = snapshots::snapshot_for_battle(&history, when)?;
                obj([
                    ("battleTimestamp", string(snapshots::utc(time)?)),
                    (
                        "snapshot",
                        entry.cloned().unwrap_or(clash_data::json::Json::Null),
                    ),
                ])
            }
        }
        _ => return Err(USAGE.to_owned()),
    };
    println!("{}", encode(&output));
    Ok(())
}
