//! Tile geometry (44 village + 3 margin), distinct from half-tile runtime
//! navigation. Flooding uses all eight neighbors, including diagonal wall gaps.
use std::collections::{BTreeSet, VecDeque};

use super::model::{Layout, Tile};
use crate::json::Json;

pub const VILLAGE: i32 = 44;
pub const MARGIN: i32 = 3;
pub const NEIGHBORS: [Tile; 8] = [
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
];
pub type Tiles = BTreeSet<Tile>;

pub fn flood(seeds: &Tiles, legal: &Tiles, corner_blocked: Option<&Tiles>) -> Tiles {
    let mut seen: Tiles = seeds.intersection(legal).copied().collect();
    let mut queue: VecDeque<_> = seen.iter().copied().collect();
    while let Some((x, y)) = queue.pop_front() {
        for (dx, dy) in NEIGHBORS {
            let next = (x + dx, y + dy);
            if dx != 0
                && dy != 0
                && corner_blocked.is_some_and(|blocked| {
                    blocked.contains(&(x, y + dy)) || blocked.contains(&(x + dx, y))
                })
            {
                continue;
            }
            if legal.contains(&next) && seen.insert(next) {
                queue.push_back(next);
            }
        }
    }
    seen
}

fn square(lo: i32, hi: i32) -> Tiles {
    (lo..hi)
        .flat_map(|x| (lo..hi).map(move |y| (x, y)))
        .collect()
}

fn edges(legal: &Tiles, lo: i32, hi: i32) -> Tiles {
    legal
        .iter()
        .copied()
        .filter(|&(x, y)| x == lo || y == lo || x == hi - 1 || y == hi - 1)
        .collect()
}

pub fn groups(mut legal: Tiles) -> Vec<Tiles> {
    let mut result = Vec::new();
    while let Some(&seed) = legal.first() {
        let group = flood(&Tiles::from([seed]), &legal, None);
        legal = legal.difference(&group).copied().collect();
        result.push(group);
    }
    result.sort_by(|a, b| b.len().cmp(&a.len()).then_with(|| a.cmp(b)));
    result
}

pub fn dilate(occupied: &Tiles) -> Tiles {
    occupied
        .iter()
        .flat_map(|&(x, y)| (-1..=1).flat_map(move |dx| (-1..=1).map(move |dy| (x + dx, y + dy))))
        .collect()
}

pub fn blocked(layout: &Layout, sizes: &[(String, usize)]) -> Tiles {
    blocked_json(&layout.to_json(), sizes)
}

/// Engine-compatible raw adapter for scoring; callers supply validated layouts.
pub fn blocked_json(layout: &Json, sizes: &[(String, usize)]) -> Tiles {
    let mut occupied = Tiles::new();
    for building in layout.at("buildings").arr() {
        let key = building.at("key").str();
        if key == "tesla" {
            continue;
        }
        let size = sizes
            .iter()
            .find(|(k, _)| k == key)
            .expect("known building size")
            .1 as i32;
        let x = building.at("x").i64() as i32;
        let y = building.at("y").i64() as i32;
        for dx in 0..size {
            for dy in 0..size {
                occupied.insert((x + dx, y + dy));
            }
        }
    }
    for wall in layout.get("walls").map_or(&[][..], Json::arr) {
        occupied.insert((wall.arr()[0].i64() as i32, wall.arr()[1].i64() as i32));
    }
    dilate(&occupied)
}

pub fn deployable(blocked: &Tiles) -> Tiles {
    square(0, VILLAGE).difference(blocked).copied().collect()
}

pub fn outside(walls: &Tiles) -> Tiles {
    let legal: Tiles = square(0, VILLAGE).difference(walls).copied().collect();
    flood(&edges(&legal, 0, VILLAGE), &legal, None)
}

pub fn compartments(walls: &Tiles) -> Vec<Tiles> {
    let outside = outside(walls);
    let enclosed: Tiles = square(0, VILLAGE)
        .difference(walls)
        .copied()
        .filter(|p| !outside.contains(p))
        .collect();
    groups(enclosed)
}

pub fn holes(blocked: &Tiles, village: i32, margin: i32) -> Vec<Tiles> {
    let lo = -margin;
    let hi = village + margin;
    let legal: Tiles = square(lo, hi).difference(blocked).copied().collect();
    let exterior = flood(&edges(&legal, lo, hi), &legal, None);
    groups(legal.difference(&exterior).copied().collect())
}

pub fn hole_tiles_json(
    layout: &Json,
    sizes: &[(String, usize)],
    village: i64,
    margin: i64,
) -> usize {
    holes(&blocked_json(layout, sizes), village as i32, margin as i32)
        .iter()
        .map(Tiles::len)
        .sum()
}
