//! Text transcription import, conservative repair and explicit completion.
use super::random::PyRandom;
use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_data::wire::{arr, num, obj, string};
use clash_layout::geometry::{outside, Tiles};
use clash_layout::model::{BuildingPlacement, Layout, Mode, Tile, TrapPlacement, WallPiece};
use clash_layout::rules::BaseRules;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Default)]
pub struct Receipt {
    pub events: Vec<Json>,
}
impl Receipt {
    pub fn record(&mut self, evidence: &str, operation: &str, before: Json, after: Json) {
        self.events.push(obj([
            ("evidence", string(evidence)),
            ("operation", string(operation)),
            ("before", before),
            ("after", after),
        ]));
    }
    pub fn to_json(&self) -> Json {
        obj([
            ("schema_version", num(1)),
            (
                "scope",
                string(
                    "screenshot transcription and explicit assumptions; not real-game calibration",
                ),
            ),
            ("events", arr(self.events.clone())),
        ])
    }
}
pub fn tile_json((x, y): Tile) -> Json {
    arr([num(x), num(y)])
}
pub fn tiles_json(tiles: &Tiles) -> Json {
    arr(tiles.iter().copied().map(tile_json))
}
pub fn footprint((x, y): Tile, size: i32) -> Tiles {
    (0..size)
        .flat_map(|dx| (0..size).map(move |dy| (x + dx, y + dy)))
        .collect()
}
pub fn size(catalog: &Catalog, key: &str) -> Result<i32, String> {
    catalog
        .building_types
        .iter()
        .find(|(k, _)| k == key)
        .map(|(_, b)| b.size as i32)
        .ok_or_else(|| format!("unknown building {key}"))
}
pub fn trap_size(catalog: &Catalog, key: &str) -> Result<i32, String> {
    if !catalog.trap_names.iter().any(|(k, _)| k == key) {
        return Err(format!("unknown trap {key}"));
    }
    Ok(catalog
        .trap_sizes
        .iter()
        .find(|(k, _)| k == key)
        .map(|(_, s)| *s as i32)
        .unwrap_or(1))
}
pub fn occupied(layout: &Layout, catalog: &Catalog, traps: bool) -> Result<Tiles, String> {
    let mut out: Tiles = layout.walls.iter().map(|w| w.position).collect();
    for b in &layout.buildings {
        out.extend(footprint(b.position, size(catalog, &b.key)?));
    }
    if traps {
        for t in &layout.traps {
            out.extend(footprint(t.position, trap_size(catalog, &t.key)?));
        }
    }
    Ok(out)
}
fn fits(position: Tile, size: i32, occupied: &Tiles) -> bool {
    position.0 >= 0
        && position.1 >= 0
        && position.0 + size <= 44
        && position.1 + size <= 44
        && footprint(position, size).is_disjoint(occupied)
}
fn positions(size: i32) -> impl Iterator<Item = Tile> {
    (0..=44 - size).flat_map(move |x| (0..=44 - size).map(move |y| (x, y)))
}
fn distance(a: Tile, b: Tile) -> i64 {
    (i64::from(a.0) - i64::from(b.0)).pow(2) + (i64::from(a.1) - i64::from(b.1)).pow(2)
}
fn next_id(layout: &Layout, prefix: &str) -> String {
    let ids: BTreeSet<_> = layout
        .buildings
        .iter()
        .map(|b| b.id.as_str())
        .chain(layout.traps.iter().map(|t| t.id.as_str()))
        .chain(layout.walls.iter().map(|w| w.id.as_str()))
        .collect();
    let mut n = 0;
    loop {
        let candidate = format!("{prefix}{n:04}");
        if !ids.contains(candidate.as_str()) {
            return candidate;
        }
        n += 1;
    }
}

pub fn build(
    text: &str,
    walls: Tiles,
    name: &str,
    town_hall: i64,
    catalog: &Catalog,
    receipt: &mut Receipt,
) -> Result<Layout, String> {
    let mut buildings = Vec::new();
    let mut traps = Vec::new();
    for (index, line) in text.lines().enumerate() {
        let (body, comment) = line.split_once('#').unwrap_or((line, ""));
        let parts: Vec<_> = body.split_whitespace().collect();
        if parts.is_empty() {
            continue;
        }
        if !(3..=4).contains(&parts.len()) {
            return Err(format!(
                "buildings line {}: expected key x y [mode]",
                index + 1
            ));
        }
        let key = parts[0];
        let coord = |part: &str| {
            part.parse::<i32>()
                .map_err(|_| format!("buildings line {}: invalid tile", index + 1))
        };
        let position = (coord(parts[1])?, coord(parts[2])?);
        let mode = parts
            .get(3)
            .map(|v| {
                Mode::parse(v).ok_or_else(|| format!("line {}: unsupported mode {v}", index + 1))
            })
            .transpose()?;
        if let Some(key) = key.strip_prefix("T:") {
            trap_size(catalog, key)?;
            traps.push(TrapPlacement {
                id: format!("t{:04}", traps.len()),
                key: key.to_owned(),
                position,
                mode,
            });
        } else {
            size(catalog, key)?;
            buildings.push(BuildingPlacement {
                id: format!("b{:04}", buildings.len()),
                key: key.to_owned(),
                position,
                mode,
            });
        }
        receipt.record(
            "measured",
            "transcribed position",
            Json::Null,
            obj([
                ("line", num(index as i32 + 1)),
                ("key", string(key)),
                ("position", tile_json(position)),
                ("comment", string(comment.trim())),
            ]),
        );
    }
    let document = obj([
        ("name", string(name)),
        ("town_hall", num(town_hall as i32)),
        ("buildings", arr([])),
        ("heroes", arr([])),
        ("cc_troops", arr([])),
        ("guardian", Json::Null),
    ]);
    let mut layout =
        Layout::from_json(&document).map_err(|r| clash_data::wire::encode(&r.to_json()))?;
    layout.buildings = buildings;
    layout.traps = traps;
    let mut taken = Tiles::new();
    for b in &layout.buildings {
        taken.extend(footprint(b.position, size(catalog, &b.key)?));
    }
    let dropped: Tiles = walls.intersection(&taken).copied().collect();
    receipt.record(
        "measured",
        "reviewed wall input",
        Json::Null,
        tiles_json(&walls),
    );
    if !dropped.is_empty() {
        receipt.record(
            "imputed",
            "remove walls under transcribed building footprints",
            tiles_json(&dropped),
            arr([]),
        );
    }
    layout.walls = walls
        .difference(&taken)
        .enumerate()
        .map(|(i, &position)| WallPiece {
            id: format!("w{i:04}"),
            position,
            level: None,
        })
        .collect();
    layout.notes = "Screenshot transcription; positions may be uncertain by about one tile. Hidden structures and unobserved troops are unknown. See digitization receipt.".to_owned();
    Ok(layout)
}

/// Add only missing Teslas, using the original interior/farthest-point rule.
pub fn add_teslas(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    receipt: &mut Receipt,
) -> Result<(), String> {
    add_teslas_with_policy(layout, catalog, rules, receipt, false, None)
}

pub(super) fn add_teslas_with_connectivity(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    receipt: &mut Receipt,
    four_way: bool,
) -> Result<(), String> {
    add_teslas_with_policy(layout, catalog, rules, receipt, four_way, None)
}

pub fn add_teslas_near_th(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    receipt: &mut Receipt,
    radius: f64,
) -> Result<(), String> {
    if !radius.is_finite() || radius <= 0.0 {
        return Err("Tesla radius must be finite and positive".to_owned());
    }
    receipt.record(
        "imputed",
        "explicit Tesla radius fallback instead of enclosure requirement",
        Json::Null,
        num(radius),
    );
    add_teslas_with_policy(layout, catalog, rules, receipt, false, Some(radius))
}

fn add_teslas_with_policy(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    receipt: &mut Receipt,
    four_way: bool,
    radius: Option<f64>,
) -> Result<(), String> {
    let wanted = rules
        .town_halls
        .get(&layout.town_hall)
        .ok_or("unsupported Town Hall")?
        .buildings
        .get("tesla")
        .copied()
        .unwrap_or(0);
    let need = wanted.saturating_sub(layout.buildings.iter().filter(|b| b.key == "tesla").count());
    if need == 0 {
        return Ok(());
    }
    let walls = layout.walls.iter().map(|w| w.position).collect();
    let outer = if four_way {
        outside_four_way(&walls)
    } else {
        outside(&walls)
    };
    let taken = occupied(layout, catalog, true)?;
    let th = layout
        .buildings
        .iter()
        .find(|b| b.key == "th")
        .ok_or("Tesla completion needs a Town Hall position")?;
    let half = f64::from(size(catalog, "th")?) / 2.0;
    let center = (
        f64::from(th.position.0) + half,
        f64::from(th.position.1) + half,
    );
    let spots: Vec<_> = positions(2)
        .filter(|&t| {
            let allowed = if let Some(radius) = radius {
                (f64::from(t.0) + 1.0 - center.0).hypot(f64::from(t.1) + 1.0 - center.1) <= radius
            } else {
                footprint(t, 2).is_disjoint(&outer)
            };
            fits(t, 2, &taken) && allowed
        })
        .collect();
    let mut placed: Vec<Tile> = Vec::new();
    for _ in 0..need {
        let free = spots.iter().copied().filter(|s| {
            !placed
                .iter()
                .any(|p| (s.0 - p.0).abs() < 2 && (s.1 - p.1).abs() < 2)
        });
        let mut best = None;
        let mut best_score = f64::NEG_INFINITY;
        for p in free {
            let score = if placed.is_empty() {
                -(f64::from(p.0) + 1.0 - center.0).hypot(f64::from(p.1) + 1.0 - center.1)
            } else {
                placed
                    .iter()
                    .map(|q| f64::from(p.0 - q.0).hypot(f64::from(p.1 - q.1)))
                    .fold(f64::INFINITY, f64::min)
            };
            if score > best_score {
                best = Some(p);
                best_score = score;
            }
        }
        let Some(position) = best else {
            receipt.record(
                "unresolved",
                "missing Teslas without a free enclosed 2x2 footprint",
                num(need as i32),
                num(placed.len() as i32),
            );
            break;
        };
        placed.push(position);
    }
    for position in placed {
        let id = next_id(layout, "tesla");
        layout.buildings.push(BuildingPlacement {
            id,
            key: "tesla".to_owned(),
            position,
            mode: None,
        });
        receipt.record(
            "imputed",
            "hidden Tesla: farthest-point heuristic in declared region",
            Json::Null,
            tile_json(position),
        );
    }
    Ok(())
}

fn outside_four_way(walls: &Tiles) -> Tiles {
    let legal: Tiles = positions(1).filter(|p| !walls.contains(p)).collect();
    let mut seen: Tiles = legal
        .iter()
        .copied()
        .filter(|&(x, y)| x == 0 || x == 43 || y == 0 || y == 43)
        .collect();
    let mut stack: Vec<_> = seen.iter().copied().collect();
    while let Some((x, y)) = stack.pop() {
        for p in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)] {
            if legal.contains(&p) && seen.insert(p) {
                stack.push(p);
            }
        }
    }
    seen
}

/// Relocate conflicting buildings; utility buildings stay outside wall rings.
/// Unlike the legacy script, lack of room fails explicitly instead of dropping
/// a measured structure. Work is transactional at the CLI boundary.
pub fn repair(layout: &mut Layout, catalog: &Catalog, receipt: &mut Receipt) -> Result<(), String> {
    let walls: Tiles = layout.walls.iter().map(|w| w.position).collect();
    let outer = outside(&walls);
    for _ in 0..80 {
        let mut seen = walls.clone();
        let mut bad = None;
        for (i, b) in layout.buildings.iter().enumerate() {
            let s = size(catalog, &b.key)?;
            if !fits(b.position, s, &seen) {
                bad = Some(i);
                break;
            }
            seen.extend(footprint(b.position, s));
        }
        let Some(index) = bad else {
            return Ok(());
        };
        let b = &layout.buildings[index];
        let s = size(catalog, &b.key)?;
        let mut others = walls.clone();
        for (i, other) in layout.buildings.iter().enumerate() {
            if i != index {
                others.extend(footprint(other.position, size(catalog, &other.key)?));
            }
        }
        for trap in &layout.traps {
            others.extend(footprint(trap.position, trap_size(catalog, &trap.key)?));
        }
        let kind = catalog
            .building_types
            .iter()
            .find(|(k, _)| k == &b.key)
            .expect("validated building")
            .1
            .kind
            .as_str();
        let trash = !matches!(kind, "defense" | "townhall" | "castle");
        let pick = positions(s)
            .filter(|&p| fits(p, s, &others) && (!trash || footprint(p, s).is_subset(&outer)))
            .min_by_key(|&p| (distance(p, b.position), p));
        let position = pick
            .ok_or_else(|| format!("no free repair position for {} at {:?}", b.key, b.position))?;
        receipt.record(
            "imputed",
            &format!("repair overlap/bounds: {}", b.id),
            tile_json(b.position),
            tile_json(position),
        );
        layout.buildings[index].position = position;
    }
    Err("repair did not converge in 80 moves".to_owned())
}

fn shuffle<T>(values: &mut [T], rng: &mut PyRandom) {
    for i in (1..values.len()).rev() {
        let j = rng.below(i + 1);
        values.swap(i, j);
    }
}

/// Preserve observed traps; fill the missing inventory using generator.py's
/// role neighborhoods, CPython MT19937 shuffle and Random(7) call ordering.
pub fn add_traps(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    receipt: &mut Receipt,
) -> Result<(), String> {
    let inventory = &rules
        .town_halls
        .get(&layout.town_hall)
        .ok_or("unsupported Town Hall")?
        .traps;
    let mut centers: BTreeMap<&str, Vec<(f64, f64)>> = BTreeMap::new();
    for b in &layout.buildings {
        let half = f64::from(size(catalog, &b.key)?) / 2.0;
        centers.entry(&b.key).or_default().push((
            f64::from(b.position.0) + half,
            f64::from(b.position.1) + half,
        ));
    }
    let mut rng = PyRandom::new(7);
    let plans: [(&str, &[&str], f64); 8] = [
        ("seeking", &["ad", "inferno", "eagle", "xbow"], 6.0),
        ("airbomb", &["ad", "scatter", "th"], 7.0),
        ("giant", &["mat", "ric", "wt", "bt", "th"], 5.0),
        ("spring", &["at", "cannon", "xbow", "mortar"], 4.0),
        ("bomb", &["wt", "mat", "cannon"], 4.0),
        ("skeleton", &["th", "inferno", "eagle"], 7.0),
        ("tornado", &["th"], 6.0),
        ("giga", &["th", "inferno"], 6.0),
    ];
    let mut spots = BTreeMap::new();
    for (key, keys, radius) in plans {
        let mut near = Vec::new();
        for x in 0..44 {
            for y in 0..44 {
                if keys
                    .iter()
                    .flat_map(|k| centers.get(k).into_iter().flatten())
                    .any(|&(px, py)| {
                        (f64::from(x) + 0.5 - px).hypot(f64::from(y) + 0.5 - py) <= radius
                    })
                {
                    near.push((x, y));
                }
            }
        }
        shuffle(&mut near, &mut rng);
        spots.insert(key, near);
    }
    let mut taken = occupied(layout, catalog, true)?;
    let mut air_left = 2_usize.saturating_sub(
        layout
            .traps
            .iter()
            .filter(|t| t.key == "skeleton" && t.mode == Some(Mode::Air))
            .count(),
    );
    for key in [
        "bomb", "spring", "giant", "airbomb", "seeking", "skeleton", "tornado", "giga",
    ] {
        let have = layout.traps.iter().filter(|t| t.key == key).count();
        let need = inventory
            .get(key)
            .copied()
            .unwrap_or(0)
            .saturating_sub(have);
        let s = trap_size(catalog, key)?;
        let mut placed = 0;
        let mut used: Vec<Tile> = layout
            .traps
            .iter()
            .filter(|t| t.key == key)
            .map(|t| t.position)
            .collect();
        let mut candidates = spots[key].clone().into_iter();
        let mut fallback_draws = 0;
        while placed < need {
            let position = if let Some(p) = candidates.next() {
                if used
                    .iter()
                    .any(|q| (p.0 - q.0).abs() + (p.1 - q.1).abs() < 3)
                {
                    continue;
                }
                p
            } else {
                fallback_draws += 1;
                if fallback_draws > 100_000 {
                    return Err(format!("no space for {key} completion"));
                }
                (rng.below(44) as i32, rng.below(44) as i32)
            };
            if !fits(position, s, &taken) {
                continue;
            }
            taken.extend(footprint(position, s));
            let mode = if key == "skeleton" {
                let mode = if air_left > 0 {
                    Mode::Air
                } else {
                    Mode::Ground
                };
                air_left = air_left.saturating_sub(1);
                Some(mode)
            } else {
                None
            };
            let id = next_id(layout, "trap");
            layout.traps.push(TrapPlacement {
                id,
                key: key.to_owned(),
                position,
                mode,
            });
            used.push(position);
            placed += 1;
            receipt.record(
                "imputed",
                &format!("invisible {key}: role heuristic, seed 7"),
                Json::Null,
                obj([
                    ("position", tile_json(position)),
                    (
                        "mode",
                        mode.map(|m| string(m.as_str())).unwrap_or(Json::Null),
                    ),
                ]),
            );
        }
    }
    Ok(())
}

pub fn apply_levels(
    layout: &mut Layout,
    account: &Json,
    account_th: i64,
    receipt: &mut Receipt,
) -> Result<(), String> {
    if account_th != layout.town_hall {
        return Err(format!(
            "refusing TH{account_th} account levels on TH{} layout",
            layout.town_hall
        ));
    }
    if account
        .get("town_hall")
        .is_some_and(|th| th.opt_f64() != Some(account_th as f64))
    {
        return Err("account Town Hall disagrees with declared --levels-th".to_owned());
    }
    if account
        .get("levels")
        .and_then(|levels| levels.get("th"))
        .is_some_and(|th| th.opt_f64() != Some(account_th as f64))
    {
        return Err("account levels.th disagrees with declared --levels-th".to_owned());
    }
    let has_embedded_th = account.get("town_hall").is_some()
        || account
            .get("levels")
            .and_then(|levels| levels.get("th"))
            .is_some();
    if !has_embedded_th && account_th != 16 {
        return Err("legacy untyped account levels are TH16-only; other Town Halls require town_hall metadata in the account document".to_owned());
    }
    let mut document = layout.to_json();
    for field in ["levels", "hero_levels", "wall_level"] {
        let value = account
            .get(field)
            .ok_or_else(|| format!("account missing {field}"))?;
        clash_data::wire::put(&mut document, field, value.clone());
    }
    let candidate =
        Layout::from_json(&document).map_err(|r| clash_data::wire::encode(&r.to_json()))?;
    receipt.record(
        "imputed",
        "explicit account levels, Town Hall matched",
        obj([
            ("levels", layout.to_json().at("levels").clone()),
            ("hero_levels", layout.to_json().at("hero_levels").clone()),
            ("wall_level", layout.to_json().at("wall_level").clone()),
        ]),
        obj([
            ("town_hall", num(account_th as i32)),
            ("levels", candidate.to_json().at("levels").clone()),
            ("hero_levels", candidate.to_json().at("hero_levels").clone()),
            ("wall_level", candidate.to_json().at("wall_level").clone()),
        ]),
    );
    layout.setup.levels = candidate.setup.levels;
    layout.setup.hero_levels = candidate.setup.hero_levels;
    layout.setup.wall_level = candidate.setup.wall_level;
    Ok(())
}

pub fn top_up_walls(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    receipt: &mut Receipt,
) -> Result<(), String> {
    let target = rules
        .town_halls
        .get(&layout.town_hall)
        .ok_or("unsupported Town Hall")?
        .walls;
    if layout.walls.len() > target {
        return Err("wall count exceeds Town Hall inventory".to_owned());
    }
    let mut taken = occupied(layout, catalog, true)?;
    let mut walls: Tiles = layout.walls.iter().map(|w| w.position).collect();
    let mut rng = PyRandom::new(16);
    let original: Vec<_> = walls.iter().copied().collect();
    let mut additions = Vec::new();
    if !original.is_empty() {
        for _ in 0..300 {
            let left = target - walls.len();
            if left < 2 {
                break;
            }
            let (x, y) = original[rng.below(original.len())];
            let (dx, dy) = [(1, 0), (-1, 0), (0, 1), (0, -1)][rng.below(4)];
            let n = rng.below(4.min(left) - 1) as i32 + 2;
            let segment: Vec<_> = (1..=n).map(|i| (x + dx * i, y + dy * i)).collect();
            if segment.iter().all(|&p| fits(p, 1, &taken))
                && !walls.contains(&(x + dx * (n + 1), y + dy * (n + 1)))
            {
                for p in segment {
                    walls.insert(p);
                    taken.insert(p);
                    additions.push(p);
                }
            }
        }
    }
    let near: Tiles = walls
        .iter()
        .flat_map(|&(x, y)| [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)])
        .collect();
    let mut candidates: Vec<_> = near.into_iter().collect();
    shuffle(&mut candidates, &mut rng);
    for p in candidates.into_iter().chain(positions(1)) {
        if walls.len() == target {
            break;
        }
        if fits(p, 1, &taken) {
            walls.insert(p);
            taken.insert(p);
            additions.push(p);
        }
    }
    if walls.len() != target {
        return Err("no room for remaining walls".to_owned());
    }
    for p in additions {
        let id = next_id(layout, "added-wall");
        layout.walls.push(WallPiece {
            id,
            position: p,
            level: None,
        });
        receipt.record(
            "imputed",
            "inventory wall top-up, seed 16; not observed design",
            Json::Null,
            tile_json(p),
        );
    }
    layout.walls.sort_by_key(|w| w.position);
    Ok(())
}
