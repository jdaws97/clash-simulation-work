//! Ports the frozen macro_moves.py design ideas using inventory-preserving
//! same-footprint slot matching. Role tables include TH17/18 merged defenses.
use std::collections::{BTreeMap, BTreeSet, VecDeque};

use crate::layout::model::{Layout, Mode, Tile};

use super::{inapplicable, swap, Operator};
use crate::basesearch::spatial::{distance, role, size, th};
use crate::basesearch::{Context, ProposalRng, Rejection};

pub fn wall_depth(layout: &Layout) -> BTreeMap<Tile, i32> {
    let walls: BTreeSet<_> = layout.walls.iter().map(|w| w.position).collect();
    let mut depth = BTreeMap::new();
    let mut queue = VecDeque::new();
    for y in 0..44 {
        for x in 0..44 {
            depth.insert((x, y), 10_000);
            if x == 0 || y == 0 || x == 43 || y == 43 {
                depth.insert((x, y), i32::from(walls.contains(&(x, y))));
                queue.push_back((x, y));
            }
        }
    }
    while let Some(p) = queue.pop_front() {
        for dy in -1..=1 {
            for dx in -1..=1 {
                let next = (p.0 + dx, p.1 + dy);
                if let Some(&old) = depth.get(&next) {
                    let cost = i32::from(walls.contains(&next));
                    let value = depth[&p] + cost;
                    if value < old {
                        depth.insert(next, value);
                        if cost == 0 {
                            queue.push_front(next);
                        } else {
                            queue.push_back(next);
                        }
                    }
                }
            }
        }
    }
    depth
}

pub fn transpose(layout: &mut Layout) {
    for b in &mut layout.buildings {
        b.position = (b.position.1, b.position.0);
        if matches!(b.key.as_str(), "sweeper" | "firespitter") {
            // Materialize engine defaults before changing orientation.
            b.mode = Some(match b.mode.unwrap_or(Mode::E) {
                Mode::N => Mode::W,
                Mode::W => Mode::N,
                Mode::S => Mode::E,
                Mode::E => Mode::S,
                Mode::NE => Mode::SW,
                Mode::SW => Mode::NE,
                other => other,
            });
        }
    }
    for t in &mut layout.traps {
        t.position = (t.position.1, t.position.0);
    }
    for w in &mut layout.walls {
        w.position = (w.position.1, w.position.0);
    }
}

pub fn edit(
    context: &Context,
    layout: &mut Layout,
    operator: Operator,
    rng: &mut ProposalRng,
) -> Result<(), Rejection> {
    if operator == Operator::Transpose {
        transpose(layout);
        return Ok(());
    }
    let center = th(layout);
    if operator == Operator::TrapsToCore {
        if layout.traps.is_empty() {
            return Err(inapplicable("no traps"));
        }
        for trap in &mut layout.traps {
            trap.position = (
                center.0 + rng.index(11) as i32 - 3,
                center.1 + rng.index(11) as i32 - 3,
            );
        }
        return Ok(());
    }
    let mut groups = BTreeMap::<i32, Vec<usize>>::new();
    for (i, b) in layout.buildings.iter().enumerate() {
        groups
            .entry(size(context, &b.key, false)?)
            .or_default()
            .push(i);
    }
    if operator == Operator::RoleRepack {
        let depth = wall_depth(layout);
        for (s, mut group) in groups {
            let mut slots: Vec<_> = group
                .iter()
                .map(|&i| layout.buildings[i].position)
                .collect();
            let protected = |p: Tile| {
                let d = (0..s)
                    .flat_map(|dy| (0..s).map(move |dx| (p.0 + dx, p.1 + dy)))
                    .map(|t| depth[&t])
                    .min()
                    .unwrap_or(0);
                (std::cmp::Reverse(d), distance(p, center), p)
            };
            slots.sort_by_key(|&p| protected(p));
            group.sort_by_key(|&i| {
                (
                    role(&layout.buildings[i].key),
                    protected(layout.buildings[i].position),
                    i,
                )
            });
            for (i, p) in group.into_iter().zip(slots) {
                layout.buildings[i].position = p;
            }
        }
        return Ok(());
    }
    if matches!(operator, Operator::CoreRotation | Operator::CoreFlank) {
        let side = rng.index(4);
        let quarter = 1 + rng.index(3);
        let direction = [(1, 0), (0, 1), (-1, 0), (0, -1)][side];
        for (_, group) in groups {
            let members: Vec<_> = group
                .iter()
                .copied()
                .filter(|&i| {
                    let p = layout.buildings[i].position;
                    let dx = p.0 - center.0;
                    let dy = p.1 - center.1;
                    let projection = dx * direction.0 + dy * direction.1;
                    let perpendicular = dx * direction.1 - dy * direction.0;
                    layout.buildings[i].key != "th"
                        && if operator == Operator::CoreRotation {
                            distance(p, center) <= 144
                        } else {
                            distance(p, center) <= 64
                                || (projection > 8 && perpendicular.abs() <= projection)
                        }
                })
                .collect();
            let mut available = members.clone();
            let originals = layout.buildings.clone();
            for &i in &members {
                let b = &originals[i];
                if b.key == "th" {
                    continue;
                }
                let p = b.position;
                let core = distance(p, center)
                    <= if operator == Operator::CoreFlank {
                        64
                    } else {
                        144
                    };
                let target = if operator == Operator::CoreRotation {
                    let dx = p.0 - center.0;
                    let dy = p.1 - center.1;
                    match quarter {
                        1 => (center.0 - dy, center.1 + dx),
                        2 => (center.0 - dx, center.1 - dy),
                        _ => (center.0 + dy, center.1 - dx),
                    }
                } else {
                    let shift = (12 * direction.0, 12 * direction.1);
                    if core {
                        (p.0 + shift.0, p.1 + shift.1)
                    } else {
                        (p.0 - shift.0, p.1 - shift.1)
                    }
                };
                if available.is_empty() {
                    break;
                }
                let j = *available
                    .iter()
                    .min_by_key(|&&j| (distance(originals[j].position, target), j))
                    .unwrap();
                layout.buildings[i].position = originals[j].position;
                available.retain(|&k| k != j);
            }
        }
        return Ok(());
    }
    let high = |key: &str| role(key) <= 20 && key != "th" && key != "banner";
    let selected: Vec<_> = (0..layout.buildings.len())
        .filter(|&i| {
            let key = layout.buildings[i].key.as_str();
            match operator {
                Operator::TownHallDeepest => key == "th",
                Operator::SplashInward => {
                    matches!(key, "wt" | "swt" | "bt" | "mortar" | "scatter" | "revenge")
                }
                Operator::AirDefenseSpread => key == "ad",
                _ => high(key),
            }
        })
        .collect();
    let depth = if matches!(operator, Operator::OuterScreen | Operator::TownHallDeepest) {
        Some(wall_depth(layout))
    } else {
        None
    };
    for i in selected {
        let b = &layout.buildings[i];
        let s = size(context, &b.key, false)?;
        let current = b.position;
        let peers: Vec<_> = layout
            .buildings
            .iter()
            .enumerate()
            .filter(|(j, other)| {
                *j != i
                    && if operator == Operator::AirDefenseSpread {
                        other.key == "ad"
                    } else {
                        high(&other.key)
                    }
            })
            .map(|(_, b)| b.position)
            .collect();
        let spread = |p: Tile| peers.iter().map(|&q| distance(p, q)).min().unwrap_or(0);
        if operator == Operator::FireballSpread && spread(current) >= 56 {
            continue;
        }
        let mut partners: Vec<_> = (0..layout.buildings.len())
            .filter(|&j| {
                j != i
                    && layout.buildings[j].key != "th"
                    && role(&layout.buildings[j].key) > role(&b.key)
                    && size(context, &layout.buildings[j].key, false) == Ok(s)
            })
            .collect();
        partners.sort_by_key(|&j| {
            let p = layout.buildings[j].position;
            match operator {
                Operator::AirDefenseSpread | Operator::FireballSpread => {
                    (-spread(p), distance(p, current), j)
                }
                Operator::OuterScreen | Operator::TownHallDeepest => {
                    (-depth.as_ref().unwrap()[&p] as i64, distance(p, center), j)
                }
                _ => (distance(p, center), 0, j),
            }
        });
        if let Some(&j) = partners.first() {
            let p = layout.buildings[j].position;
            let improves = match operator {
                Operator::AirDefenseSpread | Operator::FireballSpread => {
                    spread(p) > spread(current) + 4
                }
                Operator::OuterScreen | Operator::TownHallDeepest => {
                    depth.as_ref().unwrap()[&p] > depth.as_ref().unwrap()[&current]
                }
                _ => distance(p, center) + 4 < distance(current, center),
            };
            if improves {
                swap(layout, i, j);
            }
        }
    }
    Ok(())
}
