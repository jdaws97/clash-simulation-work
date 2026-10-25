//! Original synthetic layouts, with one inventory resolver and packing board.
//! Structural plans are placed before buildings; remaining owned walls are
//! packed only after all footprints, never created or discarded.
use std::collections::BTreeSet;

use crate::json::Json;
use crate::layout::json::{number, object, string};
use crate::layout::model::{AdmissionPolicy, InventoryPolicy, Layout, Mode, Tile};
use crate::layout::{admit, AdmittedLayout};

use super::operators::walls::rectangle;
use super::repair::{finish, RepairLimits};
use super::spatial::{distance, role, size, Board};
use super::{Context, Proposal, ProposalRng, Rejection};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Style {
    Grid,
    Offset,
    Rings,
    Wide,
    Freeform,
    Organic,
    Cram,
    Onion,
    Scatter,
}

impl Style {
    pub const ALL: [Self; 9] = [
        Self::Grid,
        Self::Offset,
        Self::Rings,
        Self::Wide,
        Self::Freeform,
        Self::Organic,
        Self::Cram,
        Self::Onion,
        Self::Scatter,
    ];
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TownHallZone {
    Central,
    Mid,
    Edge,
}

impl TownHallZone {
    pub const ALL: [Self; 3] = [Self::Central, Self::Mid, Self::Edge];

    fn target(self, rng: &mut ProposalRng) -> Tile {
        let radius = match self {
            Self::Central => 0,
            Self::Mid => 10,
            Self::Edge => 18,
        };
        match rng.index(4) {
            0 => (20 + radius, 20),
            1 => (20, 20 + radius),
            2 => (20 - radius, 20),
            _ => (20, 20 - radius),
        }
    }
}

fn wall_plan(style: Style, rng: &mut ProposalRng) -> Vec<Tile> {
    let mut walls = BTreeSet::new();
    match style {
        Style::Grid | Style::Offset | Style::Wide => {
            let (left, right, top, bottom) = if style == Style::Wide {
                (3, 40, 10, 33)
            } else {
                (6, 37, 6, 37)
            };
            for x in left..=right {
                walls.insert((x, top));
                walls.insert((x, bottom));
            }
            for y in top..=bottom {
                walls.insert((left, y));
                walls.insert((right, y));
            }
            for y in (top + 7..bottom).step_by(8) {
                for x in left..=right {
                    walls.insert((x, y));
                }
            }
            for (band, y) in (top..bottom).step_by(8).enumerate() {
                let shift = if band % 2 == 0 { 0 } else { 4 };
                for x in (left + 8 + shift..right).step_by(9) {
                    for dy in 0..=8.min(bottom - y) {
                        walls.insert((x, y + dy));
                    }
                }
            }
        }
        Style::Rings | Style::Onion => {
            for extent in [8, 20, 32] {
                walls.extend(rectangle((22 - extent / 2, 22 - extent / 2), extent));
            }
        }
        Style::Freeform => {
            walls.extend(rectangle((5, 5), 32));
            let mut rooms = vec![(6, 6, 36, 36)];
            for _ in 0..5 {
                let i = rng.index(rooms.len());
                let (x0, y0, x1, y1) = rooms.remove(i);
                if x1 - x0 >= y1 - y0 && x1 - x0 >= 14 {
                    let cut = (x0 + x1) / 2 + rng.index(3) as i32 - 1;
                    for y in y0..=y1 {
                        walls.insert((cut, y));
                    }
                    rooms.push((x0, y0, cut - 1, y1));
                    rooms.push((cut + 1, y0, x1, y1));
                } else if y1 - y0 >= 14 {
                    let cut = (y0 + y1) / 2 + rng.index(3) as i32 - 1;
                    for x in x0..=x1 {
                        walls.insert((x, cut));
                    }
                    rooms.push((x0, y0, x1, cut - 1));
                    rooms.push((x0, cut + 1, x1, y1));
                } else {
                    rooms.push((x0, y0, x1, y1));
                }
            }
        }
        Style::Organic => {
            let seeds: Vec<_> = (0..8)
                .map(|_| (7 + rng.index(30) as i32, 7 + rng.index(30) as i32))
                .collect();
            let owner = |p: Tile| {
                seeds
                    .iter()
                    .enumerate()
                    .min_by_key(|(i, q)| (distance(p, **q), *i))
                    .unwrap()
                    .0
            };
            for y in 5..39 {
                for x in 5..39 {
                    let p = (x, y);
                    // Voronoi boundaries; axis-neighbor edges avoid diagonal
                    // facing assumptions and leave room for larger footprints.
                    if owner(p) != owner((x + 1, y)) || owner(p) != owner((x, y + 1)) {
                        walls.insert(p);
                    }
                }
            }
        }
        Style::Cram | Style::Scatter => {
            for y in (2..42).step_by(3) {
                for x in 1..43 {
                    if x % 6 < 4 && (x < 7 || x > 36 || y < 7 || y > 36) {
                        walls.insert((x, y));
                    }
                }
            }
        }
    }
    if style == Style::Offset {
        walls.into_iter().map(|(x, y)| (x + 3, y - 2)).collect()
    } else {
        walls.into_iter().collect()
    }
}

/// Resolve a declared fully-merged synthetic inventory, admit it, then repack.
/// Owned-account generation uses generate() on its admitted account template.
pub fn preset(
    context: &Context,
    th: i64,
    style: Style,
    zone: TownHallZone,
    seed: u64,
) -> Result<AdmittedLayout, Rejection> {
    let inventory = context
        .rules
        .town_halls
        .get(&th)
        .ok_or_else(|| Rejection::InvalidConfig("TH must be 16..18".to_owned()))?;
    let mut board = Board::new();
    let mut budget = 2_000_000;
    let mut buildings = Vec::new();
    let mut building_keys: Vec<_> = inventory.buildings.iter().collect();
    building_keys
        .sort_by_key(|(k, _)| (std::cmp::Reverse(size(context, k, false).unwrap_or(0)), *k));
    for (key, count) in building_keys {
        for _ in 0..*count {
            let p = board.near((0, 0), size(context, key, false)?, &mut budget)?;
            let mut fields = vec![
                ("key".to_owned(), string(key)),
                ("x".to_owned(), number(p.0)),
                ("y".to_owned(), number(p.1)),
            ];
            if key == "crafting" {
                fields.push(("mode".to_owned(), string("cake")));
            }
            buildings.push(Json::Obj(fields));
        }
    }
    let mut traps = Vec::new();
    for (key, count) in &inventory.traps {
        for _ in 0..*count {
            let p = board.near((0, 0), size(context, key, true)?, &mut budget)?;
            traps.push(object([
                ("key", string(key)),
                ("x", number(p.0)),
                ("y", number(p.1)),
            ]));
        }
    }
    let mut walls = Vec::new();
    for _ in 0..inventory.walls {
        let p = board.near((0, 0), 1, &mut budget)?;
        walls.push(Json::Arr(vec![number(p.0), number(p.1)]));
    }
    let raw = object([
        (
            "name",
            string("declared synthetic M2 generator; no real-game calibration"),
        ),
        ("town_hall", number(th as i32)),
        ("buildings", Json::Arr(buildings)),
        ("traps", Json::Arr(traps)),
        ("walls", Json::Arr(walls)),
        ("heroes", Json::Arr(Vec::new())),
        ("cc_troops", Json::Arr(Vec::new())),
        ("guardian", Json::Null),
    ]);
    let template = Layout::from_json(&raw).map_err(Rejection::Admission)?;
    let policy = AdmissionPolicy {
        require_all_walls: true,
        inventory: InventoryPolicy::FullyMerged,
        ..AdmissionPolicy::default()
    };
    let template = admit(template, &context.rules, context.catalog.clone(), &policy)
        .map_err(Rejection::Admission)?;
    Ok(generate(context, &template, style, zone, seed)?.candidate)
}

pub fn generate(
    context: &Context,
    parent: &AdmittedLayout,
    style: Style,
    zone: TownHallZone,
    seed: u64,
) -> Result<Proposal, Rejection> {
    context.check(parent)?;
    let mut rng = ProposalRng::new(seed);
    let mut draft = parent.layout().clone();
    let target = zone.target(&mut rng);
    let mut plan = wall_plan(style, &mut rng);
    // Leave the TH footprint and its immediate ring free in every zone.
    plan.retain(|&(x, y)| {
        !(target.0 - 1..=target.0 + 4).contains(&x) || !(target.1 - 1..=target.1 + 4).contains(&y)
    });
    plan.sort_by_key(|&p| (distance(p, (22, 22)), p));
    let mut board = Board::new();
    let structural = draft.walls.len().min(plan.len()).min(240);
    for (wall, position) in draft
        .walls
        .iter_mut()
        .zip(plan.into_iter())
        .take(structural)
    {
        board.take(position, 1);
        wall.position = position;
    }
    let mut order: Vec<_> = (0..draft.buildings.len()).collect();
    order.sort_by_key(|&i| {
        let b = &draft.buildings[i];
        (
            b.key != "th",
            std::cmp::Reverse(size(context, &b.key, false).unwrap_or(0)),
            role(&b.key),
            i,
        )
    });
    let mut budget = 2_000_000;
    for i in order {
        let b = &mut draft.buildings[i];
        let s = size(context, &b.key, false)?;
        let aim = if b.key == "th" {
            target
        } else if style == Style::Scatter {
            (rng.index(41) as i32, rng.index(41) as i32)
        } else if matches!(style, Style::Cram | Style::Onion) {
            (20, 20)
        } else {
            let radius = role(&b.key).clamp(0, 120) / 6 + rng.index(4) as i32;
            let (dx, dy) = [
                (1, 0),
                (0, 1),
                (-1, 0),
                (0, -1),
                (1, 1),
                (-1, 1),
                (-1, -1),
                (1, -1),
            ][rng.index(8)];
            (target.0 + radius * dx, target.1 + radius * dy)
        };
        b.position = board.near(aim, s, &mut budget)?;
        if b.key == "firespitter" {
            b.mode = Some(if b.position.0 < target.0 {
                Mode::W
            } else if b.position.0 > target.0 {
                Mode::E
            } else if b.position.1 < target.1 {
                Mode::N
            } else {
                Mode::S
            });
        }
    }
    for t in &mut draft.traps {
        let aim = (
            target.0 + rng.index(19) as i32 - 8,
            target.1 + rng.index(19) as i32 - 8,
        );
        t.position = board.near(aim, size(context, &t.key, true)?, &mut budget)?;
    }
    for (i, wall) in draft.walls.iter_mut().enumerate().skip(structural) {
        let aim = if style == Style::Onion {
            (22 - (i % 33) as i32, 22 + (i % 17) as i32)
        } else {
            ((i % 44) as i32, if i % 2 == 0 { 2 } else { 41 })
        };
        wall.position = board.near(aim, 1, &mut budget)?;
    }
    finish(
        context,
        parent,
        draft,
        &format!("generate/{style:?}/{zone:?}"),
        seed,
        RepairLimits::default(),
    )
}
