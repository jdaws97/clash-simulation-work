//! Explicit search-seed completion and merging of unmerged defense inventories.
use super::buildings::{self, footprint, occupied, size, tile_json, trap_size, Receipt};
use super::random::PyRandom;
use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_data::wire::{arr, num, obj, string};
use clash_layout::geometry::{outside, Tiles};
use clash_layout::model::{BuildingPlacement, Layout, Mode, Tile, TrapPlacement};
use clash_layout::rules::BaseRules;
use std::collections::BTreeSet;

#[derive(Clone, Debug)]
pub struct TrapBox {
    pub keys: BTreeSet<String>,
    pub lo: Tile,
    pub hi: Tile,
}

fn hull(points: &Tiles) -> Vec<Tile> {
    fn cross(o: Tile, a: Tile, b: Tile) -> i64 {
        i64::from(a.0 - o.0) * i64::from(b.1 - o.1) - i64::from(a.1 - o.1) * i64::from(b.0 - o.0)
    }
    let mut lower = Vec::new();
    let mut upper = Vec::new();
    for &point in points {
        while lower.len() >= 2 && cross(lower[lower.len() - 2], lower[lower.len() - 1], point) <= 0
        {
            lower.pop();
        }
        lower.push(point);
    }
    for &point in points.iter().rev() {
        while upper.len() >= 2 && cross(upper[upper.len() - 2], upper[upper.len() - 1], point) <= 0
        {
            upper.pop();
        }
        upper.push(point);
    }
    lower.pop();
    upper.pop();
    lower.extend(upper);
    lower
}
fn in_hull(points: &[Tile], q: Tile) -> bool {
    points.len() >= 3
        && (0..points.len()).all(|i| {
            let (a, b) = (points[i], points[(i + 1) % points.len()]);
            i64::from(b.0 - a.0) * i64::from(q.1 - a.1)
                - i64::from(b.1 - a.1) * i64::from(q.0 - a.0)
                >= 0
        })
}

/// Seed completion preserves measured traps, adds inventory walls, and spreads
/// the missing traps inside the walls or their convex hull. Candidate traversal
/// is sorted, replacing Python set-order dependence with a portable contract.
pub fn seed(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    boxes: &[TrapBox],
    receipt: &mut Receipt,
) -> Result<(), String> {
    buildings::top_up_walls(layout, catalog, rules, receipt)?;
    let walls: Tiles = layout.walls.iter().map(|w| w.position).collect();
    let outer = outside(&walls);
    let mut inside: Tiles = (0..44)
        .flat_map(|x| (0..44).map(move |y| (x, y)))
        .filter(|p| !walls.contains(p) && !outer.contains(p))
        .collect();
    if inside.len() < 300 {
        let polygon = hull(&walls);
        inside = (0..44)
            .flat_map(|x| (0..44).map(move |y| (x, y)))
            .filter(|p| !walls.contains(p) && in_hull(&polygon, *p))
            .collect();
        receipt.record(
            "imputed",
            "seed interior: convex hull fallback for leaking wall ring",
            Json::Null,
            arr(polygon.into_iter().map(tile_json)),
        );
    }
    let inventory = &rules
        .town_halls
        .get(&layout.town_hall)
        .ok_or("unsupported Town Hall")?
        .traps;
    let mut taken = occupied(layout, catalog, true)?;
    let mut rng = PyRandom::new(16);
    let mut centers: Vec<_> = layout
        .traps
        .iter()
        .map(|t| (f64::from(t.position.0) + 0.5, f64::from(t.position.1) + 0.5))
        .collect();
    for key in [
        "giant", "giga", "bomb", "spring", "airbomb", "seeking", "skeleton", "tornado",
    ] {
        let have = layout.traps.iter().filter(|t| t.key == key).count();
        let need = inventory
            .get(key)
            .copied()
            .unwrap_or(0)
            .saturating_sub(have);
        let s = trap_size(catalog, key)?;
        for _ in 0..need {
            let candidates: Vec<_> = inside
                .iter()
                .copied()
                .filter(|&p| {
                    let tiles = footprint(p, s);
                    tiles.is_disjoint(&taken) && tiles.is_subset(&inside)
                })
                .collect();
            let preferred: Vec<_> = candidates
                .iter()
                .copied()
                .filter(|p| {
                    boxes.iter().any(|b| {
                        (b.keys.is_empty() || b.keys.contains(key))
                            && p.0 >= b.lo.0
                            && p.0 <= b.hi.0
                            && p.1 >= b.lo.1
                            && p.1 <= b.hi.1
                    })
                })
                .collect();
            let mut pool = if preferred.is_empty() {
                candidates
            } else {
                preferred
            };
            for i in (1..pool.len()).rev() {
                let j = rng.below(i + 1);
                pool.swap(i, j);
            }
            let mut best = None;
            let mut score = f64::NEG_INFINITY;
            for p in pool.into_iter().take(400) {
                let gap = centers
                    .iter()
                    .map(|&(x, y)| {
                        (f64::from(p.0) + f64::from(s) / 2.0 - x)
                            .hypot(f64::from(p.1) + f64::from(s) / 2.0 - y)
                    })
                    .fold(99.0, f64::min)
                    + rng.random() * 0.5;
                if gap > score {
                    best = Some(p);
                    score = gap;
                }
            }
            let p = best.ok_or_else(|| format!("no seed interior space for {key}"))?;
            let mut id = format!("seed-trap{}", layout.traps.len());
            while layout.traps.iter().any(|t| t.id == id) {
                id.push('_');
            }
            layout.traps.push(TrapPlacement {
                id,
                key: key.to_owned(),
                position: p,
                mode: (key == "skeleton").then_some(Mode::Ground),
            });
            taken.extend(footprint(p, s));
            centers.push((
                f64::from(p.0) + f64::from(s) / 2.0,
                f64::from(p.1) + f64::from(s) / 2.0,
            ));
            receipt.record(
                "imputed",
                &format!("seed {key}: farthest-point spread, sorted candidates, seed 16"),
                Json::Null,
                tile_json(p),
            );
        }
    }
    Ok(())
}

/// Merge closest pairs, then optionally fill missing building inventory.
/// All quantities come from TH rules rather than catalog-global counts.
pub fn merge(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    receipt: &mut Receipt,
) -> Result<(), String> {
    let inventory = &rules
        .town_halls
        .get(&layout.town_hall)
        .ok_or("unsupported Town Hall")?
        .buildings;
    for (old, new) in [("cannon", "ric"), ("at", "mat")] {
        let target = inventory.get(new).copied().unwrap_or(0);
        while layout.buildings.iter().filter(|b| b.key == new).count() < target {
            let indices: Vec<_> = layout
                .buildings
                .iter()
                .enumerate()
                .filter(|(_, b)| b.key == old)
                .map(|(i, _)| i)
                .collect();
            if indices.len() < 2 {
                break;
            }
            let mut pairs = Vec::new();
            for (i, &a) in indices.iter().enumerate() {
                for &b in &indices[i + 1..] {
                    let (p, q) = (layout.buildings[a].position, layout.buildings[b].position);
                    pairs.push(((p.0 - q.0).pow(2) + (p.1 - q.1).pow(2), a, b));
                }
            }
            pairs.sort_unstable();
            let (_, a, b) = pairs[0];
            receipt.record(
                "imputed",
                "merge nearest same-key defense pair",
                obj([
                    ("key", string(old)),
                    (
                        "positions",
                        arr([
                            tile_json(layout.buildings[a].position),
                            tile_json(layout.buildings[b].position),
                        ]),
                    ),
                ]),
                obj([
                    ("key", string(new)),
                    ("position", tile_json(layout.buildings[a].position)),
                ]),
            );
            layout.buildings[a].key = new.to_owned();
            layout.buildings[a].mode = None;
            layout.buildings.remove(b);
        }
    }
    buildings::repair(layout, catalog, receipt)
}

pub fn inventory(
    layout: &mut Layout,
    catalog: &Catalog,
    rules: &BaseRules,
    receipt: &mut Receipt,
) -> Result<(), String> {
    let inventory = &rules
        .town_halls
        .get(&layout.town_hall)
        .ok_or("unsupported Town Hall")?
        .buildings;
    let th = layout
        .buildings
        .iter()
        .find(|b| b.key == "th")
        .ok_or("inventory completion needs a Town Hall")?;
    let center = (
        f64::from(th.position.0) + 2.0,
        f64::from(th.position.1) + 2.0,
    );
    let mut taken = occupied(layout, catalog, true)?;
    let mut rng = PyRandom::new(16);
    for (key, building_type) in &catalog.building_types {
        let have = layout.buildings.iter().filter(|b| &b.key == key).count();
        for _ in have..inventory.get(key).copied().unwrap_or(0) {
            let s = size(catalog, key)?;
            let near = building_type.kind.as_str() == "defense" || key == "banner";
            let mut spots = Vec::new();
            for x in 0..=44 - s {
                for y in 0..=44 - s {
                    if !footprint((x, y), s).is_disjoint(&taken) {
                        continue;
                    }
                    let score = if near {
                        (f64::from(x) + f64::from(s) / 2.0 - center.0)
                            .hypot(f64::from(y) + f64::from(s) / 2.0 - center.1)
                    } else {
                        rng.random()
                    };
                    spots.push((score, (x, y)));
                }
            }
            spots.sort_by(|a, b| a.0.total_cmp(&b.0).then_with(|| a.1.cmp(&b.1)));
            if spots.is_empty() {
                return Err(format!("no space to impute inventory building {key}"));
            }
            let index = if near {
                rng.below(6).min(spots.len() - 1)
            } else {
                0
            };
            let p = spots[index].1;
            let mut id = format!("inventory{}", layout.buildings.len());
            while layout.buildings.iter().any(|b| b.id == id) {
                id.push('_');
            }
            layout.buildings.push(BuildingPlacement {
                id,
                key: key.clone(),
                position: p,
                mode: (key == "inferno").then_some(Mode::Single),
            });
            taken.extend(footprint(p, s));
            receipt.record(
                "imputed",
                "missing TH inventory building, seed 16",
                Json::Null,
                obj([
                    ("key", string(key)),
                    ("position", tile_json(p)),
                    ("town_hall", num(layout.town_hall as i32)),
                ]),
            );
        }
    }
    Ok(())
}
