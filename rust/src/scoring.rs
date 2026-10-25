//! Native evaluate.py scoring. Ordered vectors mirror Python 3.10 dictionaries
//! and sums; plans are supplied separately so M2 can replace prepared JSON.

use std::collections::{BTreeSet, HashSet, VecDeque};
use std::path::Path;
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::geom;
use crate::json::{self, Json};
use crate::runner::{Job, JobResult, PreparedInputs, Runner};

pub const SCOUT: usize = 2;
pub const MAX_SIDES: usize = 64;
pub const SKILL_ORDER: [i64; 5] = [1, 3, 2, 0, 4];

pub(crate) fn sum(values: impl IntoIterator<Item = f64>) -> f64 {
    let mut total = 0.0;
    for value in values {
        total += value;
    }
    total
}

pub(crate) fn number(value: &Json, key: &str, default: f64) -> f64 {
    value.get(key).map_or(default, Json::f64)
}

pub(crate) fn string(value: &Json, key: &str) -> Option<String> {
    value.get(key).and_then(Json::opt_str).map(str::to_owned)
}

pub(crate) fn object(entries: Vec<(&str, Json)>) -> Json {
    Json::Obj(
        entries
            .into_iter()
            .map(|(k, v)| (k.to_owned(), v))
            .collect(),
    )
}

fn put<T>(entries: &mut Vec<(String, T)>, key: String, value: T) {
    if let Some((_, old)) = entries.iter_mut().find(|(name, _)| name == &key) {
        *old = value;
    } else {
        entries.push((key, value));
    }
}

fn lookup(entries: &[(String, f64)], key: &str) -> f64 {
    entries
        .iter()
        .find(|(name, _)| name == key)
        .map_or(0.0, |(_, value)| *value)
}

fn increment(entries: &mut Vec<(String, f64)>, key: &str, value: f64) {
    let next = lookup(entries, key) + value;
    put(entries, key.to_owned(), next);
}

fn floor_div(value: f64, divisor: f64) -> i64 {
    // evaluate.py:101-107 uses CPython float_divmod, whose remainder-based
    // quotient also handles division rounding just below an integer.
    let remainder = value % divisor;
    let mut quotient = (value - remainder) / divisor;
    if remainder < 0.0 {
        quotient -= 1.0;
    }
    let floor = quotient.floor();
    if quotient - floor > 0.5 {
        (floor + 1.0) as i64
    } else {
        floor as i64
    }
}

// evaluate.py:95-113: floor division precedes int(), including negative input.
pub fn attacker_trophies(stars: i64, pct: f64) -> i64 {
    if stars >= 3 {
        40
    } else if stars == 2 {
        16 + floor_div(pct - 50.0, 3.0).max(0)
    } else if stars == 1 {
        (5 + floor_div((pct - 1.0).max(0.0), 9.0)).min(15)
    } else {
        floor_div(pct, 10.0).min(4)
    }
}

pub fn defender_trophies(stars: i64, pct: f64) -> i64 {
    if stars == 0 {
        40
    } else {
        40 - attacker_trophies(stars, pct)
    }
}

// evaluate.py:182-187: exp remains distinct from pow(e, x).
pub fn skill(seed: i64) -> f64 {
    const Z: [f64; 5] = [-1.28, -0.52, 0.0, 0.52, 1.28];
    crate::detmath::exp(0.15 * Z[seed.rem_euclid(5) as usize])
}

pub fn group_seed(j: i64, s: i64, k: i64, n: i64) -> i64 {
    5 * (s * n + k) + SKILL_ORDER[j.rem_euclid(5) as usize]
}

#[derive(Clone, Debug, PartialEq)]
pub struct Scenario {
    pub army: String,
    pub town_hall: i64,
    pub angle: f64,
    pub seed: i64,
    pub weight: f64,
    pub modifier: Option<String>,
    pub group: i64,
    pub tactic: Json,
    pub charge: Option<(String, i64)>,
    pub full_scout: bool,
}

impl Scenario {
    pub fn from_json(value: &Json) -> Self {
        Self {
            army: value.at("army").str().to_owned(),
            town_hall: value.at("town_hall").i64(),
            angle: value.at("angle").f64(),
            seed: number(value, "seed", 0.0) as i64,
            weight: number(value, "weight", 1.0),
            modifier: string(value, "modifier"),
            group: number(value, "group", 0.0) as i64,
            tactic: value.get("tactic").cloned().unwrap_or(Json::Null),
            charge: value.get("charge").filter(|v| !v.is_null()).map(|v| {
                let pair = v.arr();
                (pair[0].str().to_owned(), pair[1].i64())
            }),
            full_scout: value.get("full_scout").is_some_and(Json::bool),
        }
    }

    pub fn to_json(&self) -> Json {
        object(vec![
            ("army", Json::Str(self.army.clone())),
            ("town_hall", Json::Num(self.town_hall as f64)),
            ("angle", Json::Num(self.angle)),
            ("seed", Json::Num(self.seed as f64)),
            ("weight", Json::Num(self.weight)),
            (
                "modifier",
                self.modifier.clone().map_or(Json::Null, Json::Str),
            ),
            ("group", Json::Num(self.group as f64)),
            ("tactic", self.tactic.clone()),
            (
                "charge",
                self.charge.as_ref().map_or(Json::Null, |(hero, count)| {
                    Json::Arr(vec![Json::Str(hero.clone()), Json::Num(*count as f64)])
                }),
            ),
            ("full_scout", Json::Bool(self.full_scout)),
        ])
    }
}

// evaluate.py:207-223: each input row expands before moving to the next side.
pub fn assign_skill(scenarios: &[Scenario]) -> Vec<Scenario> {
    let mut out = Vec::with_capacity(scenarios.len() * 5);
    for scenario in scenarios {
        for q in 0..5 {
            let mut next = scenario.clone();
            next.seed = 5 * scenario.seed + q;
            next.group = 5 * scenario.group + q;
            next.weight = scenario.weight / 5.0;
            out.push(next);
        }
    }
    out
}

// evaluate.py:274-275: preserve multiply, multiply, divide, then offset order.
pub fn angles(n: usize, offset: f64) -> Vec<f64> {
    (0..n)
        .map(|k| offset + 2.0 * std::f64::consts::PI * k as f64 / n as f64)
        .collect()
}

#[derive(Clone, Debug)]
pub struct Strength(pub Vec<(String, f64)>);

impl Strength {
    pub fn get(&self, army: &str) -> f64 {
        self.0
            .iter()
            .find(|(key, _)| key == army)
            .map_or(1.0, |(_, value)| *value)
    }

    // evaluate.py:33-87: the environment selects only the meta file, and an
    // empty value selects the default. Missing/invalid files are independent.
    pub fn load(root: &Path) -> Self {
        let directory = root.join("data");
        let meta_path = std::env::var_os("BASELAB_CALIBRATION")
            .filter(|value| !value.is_empty())
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| directory.join("meta-calibration-r8.json"));
        Self::from_sources(
            &read(&directory.join("baselab-calibration.json")).unwrap_or(Json::Null),
            &read(&meta_path).unwrap_or(Json::Null),
            &read(&directory.join("observed-armies.json")).unwrap_or(Json::Null),
            &read(&directory.join("custom-armies.json")).unwrap_or(Json::Null),
        )
    }

    // evaluate.py:29-89: dict comprehensions commit only when fully built;
    // observed/custom loops retain entries preceding a missing key.
    pub fn from_sources(base: &Json, meta: &Json, observed: &Json, custom: &Json) -> Self {
        let mut out = Self(
            ["hydra", "throwers", "edrag", "rootrider"]
                .into_iter()
                .map(|key| (key.to_owned(), 1.0))
                .collect(),
        );
        for (source, prefix, skip_notes) in [(base, "", false), (meta, "meta:", true)] {
            if let Json::Obj(entries) = source {
                let mut updates = Vec::new();
                let mut valid = true;
                for (key, entry) in entries {
                    if let Some(Json::Num(value)) = entry.get("strength") {
                        updates.push((format!("{prefix}{key}"), *value));
                    } else if !skip_notes {
                        valid = false;
                        break;
                    }
                }
                if valid {
                    for (key, value) in updates {
                        put(&mut out.0, key, value);
                    }
                }
            }
        }
        let observed = match observed {
            Json::Arr(builds) => Some(builds.as_slice()),
            Json::Obj(_) => observed.get("builds").map(Json::arr),
            _ => None,
        };
        for build in observed.into_iter().flatten() {
            let (Some(archetype), Some(th), Some(index)) =
                (build.get("archetype"), build.get("th"), build.get("build"))
            else {
                break;
            };
            let key = format!("meta:{}-{}-{}", archetype.str(), th.i64(), index.i64());
            if out.0.iter().any(|(name, _)| name == &key) {
                continue;
            }
            let prefix = format!("meta:{}-16-", archetype.str());
            let mut family: Vec<f64> = out
                .0
                .iter()
                .filter(|(name, _)| name.starts_with(&prefix))
                .map(|(_, value)| *value)
                .collect();
            if family.is_empty() {
                let prefix = format!("meta:{}-", archetype.str());
                family = out
                    .0
                    .iter()
                    .filter(|(name, _)| name.starts_with(&prefix) && !name.starts_with(&key))
                    .map(|(_, value)| *value)
                    .collect();
            }
            let value = if family.is_empty() {
                1.0
            } else {
                sum(family.iter().copied()) / family.len() as f64
            };
            put(&mut out.0, key, value);
        }
        for build in custom.get("builds").map(Json::arr).into_iter().flatten() {
            let Some(archetype) = build.get("archetype") else {
                break;
            };
            let family = string(build, "family").unwrap_or_else(|| "None".to_owned());
            let prefix = format!("meta:{family}-16-");
            let values: Vec<f64> = out
                .0
                .iter()
                .filter(|(name, _)| name.starts_with(&prefix))
                .map(|(_, value)| *value)
                .collect();
            let value = if values.is_empty() {
                1.0
            } else {
                sum(values.iter().copied()) / values.len() as f64
            };
            put(&mut out.0, format!("custom:{}", archetype.str()), value);
        }
        out
    }

    pub fn to_json(&self) -> Json {
        Json::Obj(
            self.0
                .iter()
                .map(|(k, v)| (k.clone(), Json::Num(*v)))
                .collect(),
        )
    }
}

// meta_armies.py:282-298,315-343: explicit archetype mappings precede troops.
pub fn playbook_family(archetype: &str) -> Option<&'static str> {
    match archetype {
        "root-rider" | "user-rr" => Some("root-rider"),
        "mass-thrower" => Some("thrower"),
        "mass-dragons" => Some("dragon"),
        "e-drag-spam" => Some("electro-dragon"),
        "super-bowler-smash" => Some("super-bowler"),
        "mass-super-yeti" => Some("yeti"),
        "mass-meteor-golem" => Some("meteor-golem"),
        "user-air" => Some("super-minion-air"),
        "user-fireball-warden" => Some("fireball-warden"),
        "user-druid-ruin" => Some("druid-ruin-witch"),
        "mass-dragon-rider" => Some("dragon-rider"),
        "mass-super-dragon" => Some("super-dragon"),
        _ => None,
    }
}

pub fn family_of(build: &Json) -> Option<String> {
    if let Some(family) = playbook_family(build.at("archetype").str()) {
        return Some(family.to_owned());
    }
    let troops = build.get("troops");
    for (troop, family) in [
        ("Root Rider", "root-rider"),
        ("Thrower", "thrower"),
        ("Electro Dragon", "electro-dragon"),
        ("Super Bowler", "super-bowler"),
        ("Meteor Golem", "meteor-golem"),
        ("Super Yeti", "yeti"),
        ("Yeti", "yeti"),
        ("Ruin Witch", "druid-ruin-witch"),
        ("Super Minion", "super-minion-air"),
        ("Lava Hound", "lavaloon"),
        ("Dragon", "dragon"),
        ("Witch", "witch"),
        ("Electro Titan", "electro-titan"),
        ("P.E.K.K.A", "pekka"),
        ("Super Dragon", "super-dragon"),
        ("Dragon Rider", "dragon-rider"),
    ] {
        if troops
            .and_then(|v| v.get(troop))
            .is_some_and(|v| v.f64() >= 2.0)
        {
            return Some(family.to_owned());
        }
    }
    None
}

#[derive(Clone, Debug)]
pub struct Observations {
    pub available: bool,
    pub th_counts: [f64; 3],
    pub family_counts: [Vec<(String, f64)>; 3],
    pub unclassified: [f64; 3],
    pub decode_failures: [f64; 3],
    pub invalid_rows: usize,
}

impl Default for Observations {
    fn default() -> Self {
        Self {
            available: false,
            th_counts: [0.0; 3],
            family_counts: Default::default(),
            unclassified: [0.0; 3],
            decode_failures: [0.0; 3],
            invalid_rows: 0,
        }
    }
}

impl Observations {
    pub fn from_json(value: &Json) -> Self {
        let mut out = Self::default();
        out.available = value.at("available").bool();
        out.invalid_rows = value.at("invalid_rows").usize();
        for (i, th) in ["16", "17", "18"].into_iter().enumerate() {
            out.th_counts[i] = value.at("th_counts").at(th).f64();
            out.family_counts[i] = value
                .at("family_counts")
                .at(th)
                .obj()
                .iter()
                .map(|(key, count)| (key.clone(), count.f64()))
                .collect();
            out.unclassified[i] = value.at("unclassified").at(th).f64();
            out.decode_failures[i] = value.at("decode_failures").at(th).f64();
        }
        out
    }

    pub fn to_json(&self) -> Json {
        let counts = |values: &[f64; 3]| {
            Json::Obj(
                (0..3)
                    .map(|i| ((16 + i).to_string(), Json::Num(values[i])))
                    .collect(),
            )
        };
        let families = (0..3)
            .map(|i| {
                let entries = self.family_counts[i]
                    .iter()
                    .map(|(key, value)| (key.clone(), Json::Num(*value)))
                    .collect();
                ((16 + i).to_string(), Json::Obj(entries))
            })
            .collect();
        object(vec![
            ("available", Json::Bool(self.available)),
            ("th_counts", counts(&self.th_counts)),
            ("family_counts", Json::Obj(families)),
            ("unclassified", counts(&self.unclassified)),
            ("decode_failures", counts(&self.decode_failures)),
            ("invalid_rows", Json::Num(self.invalid_rows as f64)),
        ])
    }

    // meta_armies.py:388-455: parse only camp troops; raw identities/codes
    // never leave this function. Section matching mirrors the Python regexp.
    pub fn from_lines(lines: &str, troop_names: &[(i64, String)]) -> Self {
        let mut out = Self {
            available: true,
            ..Self::default()
        };
        for line in lines.lines().filter(|line| !line.trim().is_empty()) {
            let value = match json::parse(line).map(python_objects) {
                Ok(Json::Obj(entries)) => Json::Obj(entries),
                _ => {
                    out.invalid_rows += 1;
                    continue;
                }
            };
            if value.get("battleType") != Some(&Json::Str("ranked".to_owned()))
                || value.get("attack") != Some(&Json::Bool(false))
            {
                continue;
            }
            let th = match value.get("opponentTownHallLevel") {
                Some(Json::Num(th))
                    if th.fract() == 0.0
                        && *th >= 1.0
                        && integer_field(line, "opponentTownHallLevel") =>
                {
                    *th as i64
                }
                _ => {
                    out.invalid_rows += 1;
                    continue;
                }
            };
            let index = (th.clamp(16, 18) - 16) as usize;
            out.th_counts[index] += 1.0;
            let code = value
                .get("armyShareCode")
                .and_then(|value| match value {
                    Json::Str(text) => Some(text.as_str()),
                    _ => None,
                })
                .unwrap_or("");
            let mut section = "";
            let mut start = None;
            for (position, character) in code.char_indices() {
                if "hiuds".contains(character) {
                    if let Some(begin) = start.take() {
                        section = &code[begin..position];
                    }
                    if character == 'u' {
                        start = Some(position + 1);
                    }
                }
            }
            if let Some(begin) = start {
                section = &code[begin..];
            }
            let mut troops = Vec::new();
            let decoded = section.split('-').all(|part| {
                let Some((count, id)) = part.split_once('x') else {
                    return false;
                };
                if count.starts_with('0')
                    || count.is_empty()
                    || id.is_empty()
                    || !count.bytes().all(|c| c.is_ascii_digit())
                    || !id.bytes().all(|c| c.is_ascii_digit())
                {
                    return false;
                }
                let (Ok(count), Ok(id)) = (count.parse::<f64>(), id.parse::<i64>()) else {
                    return false;
                };
                let Some((_, name)) = troop_names.iter().find(|(key, _)| *key == id) else {
                    return false;
                };
                increment(&mut troops, name, count);
                true
            });
            if !decoded {
                out.decode_failures[index] += 1.0;
                continue;
            }
            let build = object(vec![
                ("archetype", Json::Str("observed".to_owned())),
                (
                    "troops",
                    Json::Obj(
                        troops
                            .into_iter()
                            .map(|(key, count)| (key, Json::Num(count)))
                            .collect(),
                    ),
                ),
            ]);
            if let Some(family) = family_of(&build) {
                increment(&mut out.family_counts[index], &family, 1.0);
            } else {
                out.unclassified[index] += 1.0;
            }
        }
        out
    }
}

// meta_armies.py:440: type(th) is int rejects JSON 16.0 and 1.6e1. Json::Num
// intentionally erases that distinction, so inspect the original top-level
// token after the JSON parser has validated the line.
fn integer_field(text: &str, field: &str) -> bool {
    let bytes = text.as_bytes();
    let mut index = 0;
    let mut depth = 0;
    let mut integer = false;
    while index < bytes.len() {
        match bytes[index] {
            b'{' | b'[' => depth += 1,
            b'}' | b']' => depth -= 1,
            b'"' => {
                let start = index;
                index += 1;
                while index < bytes.len() && bytes[index] != b'"' {
                    if bytes[index] == b'\\' {
                        index += 1;
                    }
                    index += 1;
                }
                let end = index + 1;
                if depth == 1
                    && matches!(json::parse(&text[start..end]), Ok(Json::Str(key)) if key == field)
                {
                    let rest = text[end..].trim_start();
                    if let Some(rest) = rest.strip_prefix(':') {
                        let token = rest
                            .trim_start()
                            .split([',', '}', ' ', '\t', '\r', '\n'])
                            .next()
                            .unwrap_or("");
                        let digits = token.strip_prefix('-').unwrap_or(token);
                        integer = !digits.is_empty() && digits.bytes().all(|c| c.is_ascii_digit());
                    }
                }
            }
            _ => {}
        }
        index += 1;
    }
    integer
}

/// File snapshots may also be embedded in a portable verification bundle.
#[derive(Clone, Debug)]
pub struct ScoringData {
    pub strength: Strength,
    pub meta: Json,
    pub builds: Vec<Json>,
    pub observations: Observations,
    pub playbooks: Vec<String>,
}

pub(crate) fn read(path: &Path) -> Result<Json, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    json::parse(&text)
        .map(python_objects)
        .map_err(|e| format!("{}: {e}", path.display()))
}

fn python_objects(value: Json) -> Json {
    // evaluate.py:36,51 and meta_armies.py:425 use json.loads: duplicate
    // object keys replace the value while retaining the first key's position.
    match value {
        Json::Obj(entries) => {
            let mut output = Vec::new();
            for (key, value) in entries {
                put(&mut output, key, python_objects(value));
            }
            Json::Obj(output)
        }
        Json::Arr(values) => Json::Arr(values.into_iter().map(python_objects).collect()),
        value => value,
    }
}

impl ScoringData {
    pub fn from_json(value: &Json) -> Self {
        let empty = Json::Null;
        let source = |key| value.get(key).unwrap_or(&empty);
        let meta = source("meta").clone();
        let observed = source("observed");
        let mut builds = meta.get("builds").map_or(Vec::new(), |v| v.arr().to_vec());
        if let Some(entries) = observed.get("builds") {
            builds.extend_from_slice(entries.arr());
        }
        let observations = if let Some(observations) = value.get("observations") {
            Observations::from_json(observations)
        } else if let Some(lines) = value.get("battle_lines") {
            let names = value.get("troop_names").map_or_else(Vec::new, |names| {
                names
                    .obj()
                    .iter()
                    .map(|(id, name)| {
                        (
                            id.parse::<i64>().expect("troop share ID"),
                            name.str().to_owned(),
                        )
                    })
                    .collect()
            });
            Observations::from_lines(lines.str(), &names)
        } else {
            Observations::default()
        };
        Self {
            strength: Strength::from_sources(
                source("base_calibration"),
                source("meta_calibration"),
                observed,
                source("custom"),
            ),
            meta,
            builds,
            observations,
            playbooks: value.get("playbooks").map_or_else(Vec::new, |values| {
                values
                    .arr()
                    .iter()
                    .map(|value| value.str().to_owned())
                    .collect()
            }),
        }
    }

    // evaluate.py:33-87 and meta_armies.py:61-68,301-304,405-455.
    pub fn load(root: &Path) -> Result<Self, String> {
        let directory = root.join("data");
        let calibration = std::env::var_os("BASELAB_CALIBRATION")
            .filter(|value| !value.is_empty())
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| directory.join("meta-calibration-r8.json"));
        let observed = directory.join("observed-armies.json");
        let mut sources = vec![
            (
                "base_calibration".to_owned(),
                read(&directory.join("baselab-calibration.json")).unwrap_or(Json::Null),
            ),
            (
                "meta_calibration".to_owned(),
                read(&calibration).unwrap_or(Json::Null),
            ),
            (
                "observed".to_owned(),
                if observed.exists() {
                    read(&observed)?
                } else {
                    Json::Null
                },
            ),
            (
                "custom".to_owned(),
                read(&directory.join("custom-armies.json")).unwrap_or(Json::Null),
            ),
            (
                "meta".to_owned(),
                read(&directory.join("meta-armies-2026-10-15.json"))?,
            ),
        ];
        let mut playbooks = Vec::new();
        for entry in std::fs::read_dir(directory.join("playbooks")).map_err(|e| e.to_string())? {
            let path = entry.map_err(|e| e.to_string())?.path();
            if path
                .extension()
                .is_some_and(|extension| extension == "json")
                && !read(&path)?.is_null()
            {
                if let Some(name) = path.file_stem().and_then(|s| s.to_str()) {
                    playbooks.push(Json::Str(name.to_owned()));
                }
            }
        }
        sources.push(("playbooks".to_owned(), Json::Arr(playbooks)));
        let mut out = Self::from_json(&Json::Obj(sources));
        let battles = directory.join("live/battles.jsonl");
        match std::fs::read_to_string(&battles) {
            Ok(lines) => {
                let raw = read(&directory.join("clashking-static-data.json"))?;
                let names = raw
                    .at("troops")
                    .arr()
                    .iter()
                    .map(|troop| {
                        (
                            troop.at("_id").i64() - 4_000_000,
                            troop.at("name").str().to_owned(),
                        )
                    })
                    .collect::<Vec<_>>();
                out.observations = Observations::from_lines(&lines, &names);
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(format!("{}: {error}", battles.display())),
        }
        Ok(out)
    }

    // meta_armies.py:458-509: preserve arithmetic order and build-file order.
    pub fn library(&self, th: i64, ranked: bool) -> Vec<(&Json, f64)> {
        let rows: Vec<&Json> = self
            .builds
            .iter()
            .filter(|build| build.at("th").i64() == th)
            .collect();
        let mut coverage = Vec::new();
        for build in &rows {
            increment(
                &mut coverage,
                build.at("archetype").str(),
                build.at("share").f64(),
            );
        }
        let prior = self.meta.at("archetype_share_th18");
        let mut weights: Vec<f64> = rows
            .iter()
            .map(|build| {
                let archetype = build.at("archetype").str();
                let share = prior.get(archetype).map_or(0.02, |v| v.arr()[0].f64());
                share * build.at("share").f64() / lookup(&coverage, archetype)
            })
            .collect();
        if ranked {
            let shares = self.ranked_family_shares(th);
            let mut coverage: Vec<(Option<String>, f64)> = Vec::new();
            for (build, weight) in rows.iter().zip(&weights) {
                let family = family_of(build);
                if let Some((_, old)) = coverage.iter_mut().find(|(key, _)| key == &family) {
                    *old += weight;
                } else {
                    coverage.push((family, *weight));
                }
            }
            for (build, weight) in rows.iter().zip(&mut weights) {
                let family = family_of(build);
                let total = coverage.iter().find(|(key, _)| key == &family).unwrap().1;
                *weight = family.as_ref().map_or(0.0, |f| lookup(&shares, f)) * *weight / total;
            }
        }
        let total = sum(weights.iter().copied());
        let total = if total == 0.0 { 1.0 } else { total };
        rows.into_iter()
            .zip(weights.into_iter().map(|weight| weight / total))
            .collect()
    }

    pub fn ranked_family_shares(&self, th: i64) -> Vec<(String, f64)> {
        let mut prior = Vec::new();
        for (archetype, values) in self.meta.at("archetype_share_th18").obj() {
            increment(
                &mut prior,
                playbook_family(archetype).unwrap_or(archetype),
                values.arr()[0].f64(),
            );
        }
        let total = sum(prior.iter().map(|(_, w)| *w));
        for (_, weight) in &mut prior {
            *weight /= total;
        }
        let counts: &[(String, f64)] = if (16..=18).contains(&th) {
            &self.observations.family_counts[(th - 16) as usize]
        } else {
            &[]
        };
        let n = sum(counts.iter().map(|(_, count)| *count));
        let local = n / (n + 10.0);
        let families: BTreeSet<String> =
            prior.iter().chain(counts).map(|(k, _)| k.clone()).collect();
        let size = families.len() as f64;
        families
            .into_iter()
            .map(|family| {
                let weight = (1.0 - local) * lookup(&prior, &family)
                    + local * (lookup(counts, &family) + 1.0) / (n + size);
                (family, weight)
            })
            .collect()
    }

    // evaluate.py:142-159: playbooks already encode their own charges.
    pub fn techniques(&self, build: &Json, playbooks_on: bool) -> Vec<Option<(String, i64)>> {
        let mut out = vec![None];
        if playbooks_on && family_of(build).is_some_and(|family| self.playbooks.contains(&family)) {
            return out;
        }
        for (hero, healers) in [
            ("Royal Champion", 0),
            ("Archer Queen", 4),
            ("Dragon Duke", 0),
        ] {
            if build
                .get("heroes")
                .is_some_and(|values| values.arr().iter().any(|name| name.str() == hero))
            {
                let available = build
                    .get("troops")
                    .map_or(0, |v| number(v, "Healer", 0.0) as i64);
                out.push(Some((hero.to_owned(), healers.min(available))));
            }
        }
        out
    }
}

#[derive(Clone, Debug)]
pub struct MetaOptions {
    pub mode: String,
    pub n_angles: usize,
    pub seeds: Vec<i64>,
    pub modifier: Option<String>,
    pub th_mix: Option<Vec<(i64, f64)>>,
    pub th_mix_env: Option<String>,
    pub techniques_on: bool,
    pub angle_offset: f64,
    pub budget: Option<f64>,
    pub playbooks: bool,
}

impl Default for MetaOptions {
    fn default() -> Self {
        Self {
            mode: "ranked".to_owned(),
            n_angles: 8,
            seeds: vec![0],
            modifier: None,
            th_mix: None,
            th_mix_env: std::env::var("BASELAB_TH_MIX").ok(),
            techniques_on: false,
            angle_offset: 0.0,
            budget: None,
            playbooks: std::env::var("BASELAB_PLAYBOOKS").as_deref() == Ok("1"),
        }
    }
}

impl MetaOptions {
    pub fn from_json(value: &Json) -> Result<Self, String> {
        let mut out = Self::default();
        out.mode = string(value, "mode").unwrap_or(out.mode);
        out.n_angles = number(value, "n_angles", 8.0) as usize;
        if let Some(seeds) = value.get("seeds") {
            out.seeds = seeds.arr().iter().map(Json::i64).collect();
        }
        out.modifier = string(value, "modifier");
        if let Some(mix) = value.get("th_mix").filter(|v| !v.is_null()) {
            let mut entries = Vec::new();
            for (key, weight) in mix.obj() {
                let th = key
                    .parse::<i64>()
                    .map_err(|_| "th_mix needs integer Town Halls")?;
                entries.push((th, weight.f64()));
            }
            out.th_mix = Some(entries);
        }
        if value.get("th_mix_env").is_some() {
            out.th_mix_env = string(value, "th_mix_env");
        }
        out.techniques_on = value.get("techniques_on").is_some_and(Json::bool);
        out.angle_offset = number(value, "angle_offset", 0.0);
        out.budget = value.get("budget").and_then(Json::opt_f64);
        if let Some(on) = value.get("playbooks") {
            out.playbooks = on.bool();
        }
        Ok(out)
    }
}

// evaluate.py:343-381: explicit argument > war > environment > battle log.
pub fn meta_th_mix(
    options: &MetaOptions,
    observed: &Observations,
) -> Result<(Vec<(i64, f64)>, String), String> {
    let (mix, source) = if let Some(mix) = &options.th_mix {
        (mix.clone(), "th_mix argument")
    } else if options.mode != "ranked" {
        (vec![(16, 1.0)], "same-TH war")
    } else if let Some(text) = &options.th_mix_env {
        let mut mix = Vec::new();
        let error = "BASELAB_TH_MIX must look like '16:0.3,17:0.7'";
        for item in text.split(',') {
            let parts: Vec<&str> = item.split(':').collect();
            if parts.len() != 2 {
                return Err(error.to_owned());
            }
            let th = parts[0].trim().parse::<i64>().map_err(|_| error)?;
            let weight = parts[1].trim().parse::<f64>().map_err(|_| error)?;
            if mix.iter().any(|(key, _)| *key == th) {
                return Err(error.to_owned());
            }
            mix.push((th, weight));
        }
        (mix, "BASELAB_TH_MIX")
    } else if observed.available {
        (
            (0..3)
                .map(|i| (16 + i as i64, observed.th_counts[i] + 1.0))
                .collect(),
            "ranked defenses + one per TH",
        )
    } else {
        (vec![(18, 0.65), (17, 0.35)], "default (battle log missing)")
    };
    if mix.is_empty() {
        return Err("th_mix must contain a positive Town Hall weight".to_owned());
    }
    if mix.iter().any(|(_, w)| !w.is_finite() || *w < 0.0) {
        return Err("th_mix needs integer Town Halls and finite nonnegative weights".to_owned());
    }
    let total = sum(mix.iter().map(|(_, w)| *w));
    if !total.is_finite() || total <= 0.0 {
        return Err("th_mix must have a finite positive total weight".to_owned());
    }
    let normalized = mix
        .into_iter()
        .filter(|(_, weight)| *weight > 0.0)
        .map(|(th, weight)| (th, weight / total))
        .collect();
    Ok((normalized, source.to_owned()))
}

#[derive(Clone, Debug)]
pub struct MetaScenarios {
    pub scenarios: Vec<Scenario>,
    pub th_mix: Vec<(i64, f64)>,
    pub source: String,
    pub build_shares: Vec<(i64, Vec<(String, f64)>)>,
}

// evaluate.py:441-555: no sorting of Town Halls, builds, techniques or seeds.
pub fn meta_scenarios(data: &ScoringData, options: &MetaOptions) -> Result<MetaScenarios, String> {
    let (th_mix, source) = meta_th_mix(options, &data.observations)?;
    if options.seeds.is_empty() && options.budget.is_some() {
        return Err("division by zero".to_owned());
    }
    let mut scenarios = Vec::new();
    let mut build_shares = Vec::new();
    for (th, tw) in &th_mix {
        let mut builds = data.library(*th, options.mode == "ranked");
        if builds.is_empty() {
            return Err(format!("no saved meta builds for attacker TH{th}"));
        }
        if options.playbooks {
            let kept: Vec<_> = builds
                .iter()
                .copied()
                .filter(|(build, _)| {
                    playbook_family(build.at("archetype").str())
                        .is_some_and(|family| data.playbooks.iter().any(|name| name == family))
                })
                .collect();
            // evaluate.py:517: an empty filter deliberately retains all builds.
            if !kept.is_empty() {
                let total = sum(kept.iter().map(|(_, w)| *w));
                builds = kept.into_iter().map(|(b, w)| (b, w / total)).collect();
            }
        }
        let mut shares = Vec::new();
        for (build, weight) in &builds {
            let id = format!(
                "{}-{}-{}",
                build.at("archetype").str(),
                build.at("th").i64(),
                build.at("build").i64(),
            );
            put(&mut shares, id, *weight);
        }
        build_shares.push((*th, shares));
        for (build, weight) in builds {
            let army = format!(
                "meta:{}-{}-{}",
                build.at("archetype").str(),
                build.at("th").i64(),
                build.at("build").i64(),
            );
            let techniques = if options.techniques_on {
                data.techniques(build, options.playbooks)
            } else {
                vec![None]
            };
            let (sides, stride) = if let Some(budget) = options.budget {
                let units = budget / (5 * options.seeds.len()) as f64;
                let requested = units * tw * weight / techniques.len() as f64;
                if !requested.is_finite() {
                    return Err("budget side allocation must be finite".to_owned());
                }
                let sides = geom::round_half_even(requested);
                (
                    sides.max(SCOUT as f64).min(MAX_SIDES as f64) as usize,
                    MAX_SIDES,
                )
            } else {
                (options.n_angles, options.n_angles)
            };
            let offset =
                0.31 * *th as f64 + 0.07 * army.chars().count() as f64 + options.angle_offset;
            for (k, angle) in angles(sides, offset).into_iter().enumerate() {
                for seed in &options.seeds {
                    for charge in &techniques {
                        scenarios.push(Scenario {
                            army: army.clone(),
                            town_hall: *th,
                            angle,
                            seed: seed * stride as i64 + k as i64,
                            weight: tw * weight
                                / (sides * options.seeds.len() * techniques.len()) as f64,
                            modifier: options.modifier.clone(),
                            group: *seed,
                            tactic: Json::Null,
                            charge: charge.clone(),
                            full_scout: false,
                        });
                    }
                }
            }
        }
    }
    Ok(MetaScenarios {
        scenarios: assign_skill(&scenarios),
        th_mix,
        source,
        build_shares,
    })
}

#[derive(Clone, Copy, Debug)]
pub struct Outcome {
    pub stars: i64,
    pub destruction: f64,
    pub th_destroyed: bool,
    pub time: f64,
}

impl Outcome {
    pub fn from_json(value: &Json) -> Self {
        let values = value.arr();
        Self {
            stars: values[0].i64(),
            destruction: values[1].f64(),
            th_destroyed: values[2].bool(),
            time: values[3].f64(),
        }
    }

    pub fn to_json(&self) -> Json {
        Json::Arr(vec![
            Json::Num(self.stars as f64),
            Json::Num(self.destruction),
            Json::Bool(self.th_destroyed),
            Json::Num(self.time),
        ])
    }
}

impl From<JobResult> for Outcome {
    fn from(result: JobResult) -> Self {
        Self {
            stars: result.stars as i64,
            destruction: result.destruction as f64,
            th_destroyed: result.th_destroyed,
            time: result.time,
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct Selection {
    pub scenario: usize,
    pub weight: f64,
}

// evaluate.py:723-762: insertion-ordered groups/sides, lexicographic
// itertools.combinations, and Python max's first occurrence on ties.
/// Oracle upper bound: uses completed real-state battles. Visible scouting
/// must call `scouted_by` with independent hidden-ensemble predictions instead.
pub fn scouted(
    scenarios: &[Scenario],
    results: &[Outcome],
    scout: Option<usize>,
) -> Vec<Selection> {
    let utility: Vec<_> = results
        .iter()
        .map(|row| {
            (
                attacker_trophies(row.stars, row.destruction) as f64,
                row.destruction,
            )
        })
        .collect();
    scouted_by(scenarios, &utility, scout)
}

pub fn scouted_by(
    scenarios: &[Scenario],
    utility: &[(f64, f64)],
    scout: Option<usize>,
) -> Vec<Selection> {
    let count = scenarios.len().min(utility.len());
    let scout = scout.unwrap_or(SCOUT);
    if scout <= 1 {
        return (0..count)
            .map(|index| Selection {
                scenario: index,
                weight: scenarios[index].weight,
            })
            .collect();
    }
    let mut groups: Vec<Vec<usize>> = Vec::new();
    for index in 0..count {
        let sc = &scenarios[index];
        let existing = groups.iter_mut().find(|rows| {
            let first = &scenarios[rows[0]];
            first.army == sc.army
                && first.town_hall == sc.town_hall
                && first.modifier == sc.modifier
                && first.group == sc.group
                && first.full_scout == sc.full_scout
        });
        if let Some(group) = existing {
            group.push(index);
        } else {
            groups.push(vec![index]);
        }
    }
    let mut out = Vec::new();
    for rows in groups {
        let weight = sum(rows.iter().map(|i| scenarios[*i].weight));
        let mut sides: Vec<(f64, Vec<usize>)> = Vec::new();
        for index in &rows {
            let angle = geom::round6(scenarios[*index].angle);
            if let Some((_, side)) = sides.iter_mut().find(|(a, _)| *a == angle) {
                side.push(*index);
            } else {
                sides.push((angle, vec![*index]));
            }
        }
        let k = if scenarios[rows[0]].full_scout {
            sides.len()
        } else {
            scout.min(sides.len())
        };
        let mut combinations = Vec::new();
        let mut indices: Vec<usize> = (0..k).collect();
        loop {
            let mut best = sides[indices[0]].1[0];
            for side in &indices {
                for candidate in &sides[*side].1 {
                    if utility[*candidate] > utility[best] {
                        best = *candidate;
                    }
                }
            }
            combinations.push(best);
            let Some(position) = (0..k).rev().find(|i| indices[*i] != *i + sides.len() - k) else {
                break;
            };
            indices[position] += 1;
            for i in position + 1..k {
                indices[i] = indices[i - 1] + 1;
            }
        }
        let per = weight / combinations.len() as f64;
        out.extend(combinations.into_iter().map(|scenario| Selection {
            scenario,
            weight: per,
        }));
    }
    out
}

// evaluate.py:791,796: decimal formatting rounds the exact binary input,
// unlike multiplying by a power of ten before rounding.
fn round_decimal(value: f64, digits: usize) -> f64 {
    if !value.is_finite() {
        return value;
    }
    format!("{value:.digits$}")
        .parse()
        .expect("rounded decimal")
}

#[derive(Clone, Debug)]
pub struct ArmySummary {
    pub stars: f64,
    pub pct: f64,
    pub three: f64,
    pub troph: f64,
}

#[derive(Default)]
struct ArmyTotals {
    weight: f64,
    stars: f64,
    pct: f64,
    three: f64,
    troph: f64,
}

#[derive(Clone, Debug)]
pub struct Evaluation {
    pub ranked_trophies: f64,
    pub three_star_rate: f64,
    pub avg_stars: f64,
    pub avg_destruction: f64,
    pub th_kill_rate: f64,
    pub per_army: Vec<(String, ArmySummary)>,
    pub worst_side: Vec<(String, (i64, f64, f64))>,
}

impl Evaluation {
    pub fn to_json(&self) -> Json {
        let per_army = self
            .per_army
            .iter()
            .map(|(key, values)| {
                let values = object(vec![
                    ("stars", Json::Num(values.stars)),
                    ("pct", Json::Num(values.pct)),
                    ("three", Json::Num(values.three)),
                    ("troph", Json::Num(values.troph)),
                ]);
                (key.clone(), values)
            })
            .collect();
        let worst_side = self
            .worst_side
            .iter()
            .map(|(key, (stars, pct, angle))| {
                let values = Json::Arr(vec![
                    Json::Num(*stars as f64),
                    Json::Num(*pct),
                    Json::Num(*angle),
                ]);
                (key.clone(), values)
            })
            .collect();
        object(vec![
            ("ranked_trophies", Json::Num(self.ranked_trophies)),
            ("three_star_rate", Json::Num(self.three_star_rate)),
            ("avg_stars", Json::Num(self.avg_stars)),
            ("avg_destruction", Json::Num(self.avg_destruction)),
            ("th_kill_rate", Json::Num(self.th_kill_rate)),
            ("per_army", Json::Obj(per_army)),
            ("worst_side", Json::Obj(worst_side)),
        ])
    }
}

// evaluate.py:765-797: normalize only aggregate weights; per-army sums use
// original scouting weights and are rounded after division.
pub fn summarise(
    scenarios: &[Scenario],
    results: &[Outcome],
    scout: Option<usize>,
) -> Result<Evaluation, String> {
    let rows = scouted(scenarios, results, scout);
    let total = sum(rows.iter().map(|row| row.weight));
    if !rows.is_empty() && total == 0.0 {
        return Err("summary weights sum to zero".to_owned());
    }
    let mut ev = Evaluation {
        ranked_trophies: 0.0,
        three_star_rate: 0.0,
        avg_stars: 0.0,
        avg_destruction: 0.0,
        th_kill_rate: 0.0,
        per_army: Vec::new(),
        worst_side: Vec::new(),
    };
    let mut armies: Vec<(String, ArmyTotals)> = Vec::new();
    for row in rows {
        let sc = &scenarios[row.scenario];
        let r = &results[row.scenario];
        let weight = row.weight / total;
        let trophies = defender_trophies(r.stars, r.destruction) as f64;
        let three = f64::from(u8::from(r.stars >= 3));
        ev.ranked_trophies += weight * trophies;
        ev.three_star_rate += weight * three;
        ev.avg_stars += weight * r.stars as f64;
        ev.avg_destruction += weight * r.destruction;
        ev.th_kill_rate += weight * f64::from(u8::from(r.th_destroyed));
        let key = format!("{}@TH{}", sc.army, sc.town_hall);
        if !armies.iter().any(|(name, _)| name == &key) {
            armies.push((key.clone(), ArmyTotals::default()));
        }
        let values = &mut armies.iter_mut().find(|(name, _)| name == &key).unwrap().1;
        values.weight += row.weight;
        values.stars += row.weight * r.stars as f64;
        values.pct += row.weight * r.destruction;
        values.three += row.weight * three;
        values.troph += row.weight * trophies;
        let current = ev.worst_side.iter().find(|(name, _)| name == &key);
        if current
            .is_none_or(|(_, (s, p, _))| r.stars > *s || (r.stars == *s && r.destruction > *p))
        {
            put(
                &mut ev.worst_side,
                key,
                (r.stars, r.destruction, round_decimal(sc.angle, 2)),
            );
        }
    }
    for (key, values) in armies {
        if values.weight == 0.0 {
            return Err(format!("summary army {key} has zero weight"));
        }
        let averages = ArmySummary {
            stars: round_decimal(values.stars / values.weight, 3),
            pct: round_decimal(values.pct / values.weight, 3),
            three: round_decimal(values.three / values.weight, 3),
            troph: round_decimal(values.troph / values.weight, 3),
        };
        ev.per_army.push((key, averages));
    }
    Ok(ev)
}

// deploy.py:22-34,63-95: expand only buildings other than Teslas and walls;
// traps do not block deployment. Flood the full margin, then count pockets.
pub fn hole_tiles(layout: &Json, sizes: &[(String, usize)], village: i64, margin: i64) -> usize {
    let mut occupied = HashSet::new();
    for building in layout.at("buildings").arr() {
        let key = building.at("key").str();
        if key == "tesla" {
            continue;
        }
        let size = sizes
            .iter()
            .find(|(name, _)| name == key)
            .unwrap_or_else(|| panic!("unknown building {key}"))
            .1 as i64;
        let x = building.at("x").i64();
        let y = building.at("y").i64();
        for dx in 0..size {
            for dy in 0..size {
                occupied.insert((x + dx, y + dy));
            }
        }
    }
    if let Some(walls) = layout.get("walls") {
        for wall in walls.arr() {
            occupied.insert((wall.arr()[0].i64(), wall.arr()[1].i64()));
        }
    }
    let mut blocked = HashSet::new();
    for (x, y) in occupied {
        for dx in -1..=1 {
            for dy in -1..=1 {
                blocked.insert((x + dx, y + dy));
            }
        }
    }
    let lo = -margin;
    let hi = village + margin;
    let mut legal = HashSet::new();
    let mut queue = VecDeque::new();
    for x in lo..hi {
        for y in lo..hi {
            if !blocked.contains(&(x, y)) {
                legal.insert((x, y));
                if x == lo || x == hi - 1 || y == lo || y == hi - 1 {
                    queue.push_back((x, y));
                }
            }
        }
    }
    let mut seen: HashSet<_> = queue.iter().copied().collect();
    while let Some((x, y)) = queue.pop_front() {
        for (dx, dy) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
            let next = (x + dx, y + dy);
            if legal.contains(&next) && seen.insert(next) {
                queue.push_back(next);
            }
        }
    }
    legal.len() - seen.len()
}

// optimize.py:42-65: destruction is a ranked tie-breaker; war prioritizes 3*.
pub fn objective(ev: &Evaluation, mode: &str, holes: usize, per_tile: Option<f64>) -> f64 {
    let per = per_tile.unwrap_or(if mode == "ranked" { 0.25 } else { 0.8 });
    let penalty = holes as f64 * per;
    if mode == "ranked" {
        ev.ranked_trophies - 0.00005 * ev.avg_destruction - penalty
    } else {
        100.0 * (1.0 - ev.three_star_rate)
            - 10.0 * ev.avg_stars
            - 0.05 * ev.avg_destruction
            - penalty
    }
}

/// M2 implements this trait with native plan construction. A plan must already
/// include tactics, charges and strength * skill, as rust_bridge.py:129-149.
pub trait PlanProvider {
    fn prepare(&mut self, scenario: &Scenario, strength: f64) -> Result<Json, String>;
}

pub struct PreparedPlans {
    pub scenarios: Vec<Scenario>,
    pub plans: Vec<Json>,
    pub indices: Vec<usize>,
}

impl PlanProvider for PreparedPlans {
    fn prepare(&mut self, scenario: &Scenario, strength: f64) -> Result<Json, String> {
        let index = self
            .scenarios
            .iter()
            .position(|candidate| candidate == scenario)
            .ok_or("scenario has no prepared plan")?;
        let plan = self
            .indices
            .get(index)
            .ok_or("scenario has no prepared plan index")?;
        let plan = self
            .plans
            .get(*plan)
            .ok_or("prepared plan index out of range")?;
        let expected = strength * skill(scenario.seed);
        if plan.at("strength").f64().to_bits() != expected.to_bits() {
            return Err("prepared plan strength differs from calibration * skill".to_owned());
        }
        Ok(plan.clone())
    }
}

/// Construct once, reuse for batches of layout indices without serialization.
pub struct Scorer {
    pub runner: Runner,
    pub scenarios: Vec<Scenario>,
    pub plan_indices: Vec<usize>,
}

impl Scorer {
    pub fn new(
        catalog: Arc<Catalog>,
        layouts: Vec<Json>,
        scenarios: Vec<Scenario>,
        plans: Vec<Json>,
        plan_indices: Vec<usize>,
    ) -> Result<Self, String> {
        if scenarios.len() != plan_indices.len() || plan_indices.iter().any(|i| *i >= plans.len()) {
            return Err("each scenario needs a valid prepared plan index".to_owned());
        }
        Ok(Self {
            runner: Runner::new(catalog, PreparedInputs::new(layouts, plans)),
            scenarios,
            plan_indices,
        })
    }

    pub fn with_provider(
        catalog: Arc<Catalog>,
        layouts: Vec<Json>,
        scenarios: Vec<Scenario>,
        strength: &Strength,
        provider: &mut impl PlanProvider,
    ) -> Result<Self, String> {
        let plans = scenarios
            .iter()
            .map(|sc| provider.prepare(sc, strength.get(&sc.army)))
            .collect::<Result<Vec<_>, _>>()?;
        let indices = (0..plans.len()).collect();
        Self::new(catalog, layouts, scenarios, plans, indices)
    }

    pub fn run(&self, layouts: &[usize], threads: usize) -> Result<Vec<Vec<Outcome>>, String> {
        let mut jobs = Vec::new();
        for index in layouts {
            let layout = self
                .runner
                .inputs()
                .layouts
                .get(*index)
                .ok_or("layout index out of range")?;
            let th = number(layout, "town_hall", 16.0) as i64;
            for (sc, plan) in self.scenarios.iter().zip(&self.plan_indices) {
                jobs.push(Job::new(*index, *plan, sc.seed, th, sc.modifier.clone()));
            }
        }
        let outcomes = self
            .runner
            .run(&jobs, threads)
            .map_err(|error| format!("scoring battles: {error:?}"))?;
        if self.scenarios.is_empty() {
            return Ok(layouts.iter().map(|_| Vec::new()).collect());
        }
        Ok(outcomes
            .chunks(self.scenarios.len())
            .map(|rows| rows.iter().copied().map(Outcome::from).collect())
            .collect())
    }
}
