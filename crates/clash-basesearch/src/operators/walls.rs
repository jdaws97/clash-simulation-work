use std::collections::BTreeSet;

use crate::layout::model::{Layout, Tile};

use super::{inapplicable, Operator};
use crate::spatial::{distance, size, th, Board};
use crate::{Context, ProposalRng, Rejection};

pub fn rectangle(origin: Tile, extent: i32) -> Vec<Tile> {
    let mut tiles = BTreeSet::new();
    for d in -1..=extent {
        tiles.insert((origin.0 + d, origin.1 - 1));
        tiles.insert((origin.0 + d, origin.1 + extent));
        tiles.insert((origin.0 - 1, origin.1 + d));
        tiles.insert((origin.0 + extent, origin.1 + d));
    }
    tiles.into_iter().collect()
}

pub fn edit(
    context: &Context,
    layout: &mut Layout,
    operator: Operator,
    rng: &mut ProposalRng,
) -> Result<(), Rejection> {
    if layout.walls.is_empty() {
        return Err(inapplicable("no walls"));
    }
    let index = rng.index(layout.walls.len());
    let origin = layout.walls[index].position;
    let occupied: BTreeSet<_> = layout.walls.iter().map(|w| w.position).collect();
    match operator {
        Operator::WallRelocate => {
            layout.walls[index].position = (rng.index(44) as i32, rng.index(44) as i32);
        }
        Operator::WallRunShift | Operator::WallMerge => {
            let horizontal = rng.index(2) == 0;
            let mut run: Vec<_> = layout
                .walls
                .iter()
                .enumerate()
                .filter(|(_, w)| {
                    if horizontal {
                        w.position.1 == origin.1 && (w.position.0 - origin.0).abs() < 6
                    } else {
                        w.position.0 == origin.0 && (w.position.1 - origin.1).abs() < 6
                    }
                })
                .map(|(i, _)| i)
                .collect();
            run.sort_by_key(|&i| layout.walls[i].position);
            if run.len() < 2 {
                return Err(inapplicable("no wall run"));
            }
            if operator == Operator::WallMerge {
                // Remove a partition and use its pieces on the outside seam.
                let target = th(layout);
                let mut edge = rectangle((target.0 - 5, target.1 - 5), 14);
                edge.sort_by_key(|&p| (distance(p, origin), p));
                for (&i, position) in run
                    .iter()
                    .zip(edge.into_iter().filter(|p| !occupied.contains(p)))
                {
                    layout.walls[i].position = position;
                }
            } else {
                let shift = if rng.index(2) == 0 { -1 } else { 1 };
                for i in run {
                    if horizontal {
                        layout.walls[i].position.1 += shift;
                    } else {
                        layout.walls[i].position.0 += shift;
                    }
                }
            }
        }
        Operator::WallSplit => {
            // Draw a partition across the room nearest a sampled free tile.
            let anchor = (6 + rng.index(30) as i32, 6 + rng.index(30) as i32);
            let horizontal = rng.index(2) == 0;
            let mut pieces: Vec<_> = (0..layout.walls.len()).collect();
            pieces.sort_by_key(|&i| {
                (
                    std::cmp::Reverse(distance(layout.walls[i].position, anchor)),
                    i,
                )
            });
            for (d, i) in pieces.into_iter().take(7).enumerate() {
                layout.walls[i].position = if horizontal {
                    (anchor.0 + d as i32 - 3, anchor.1)
                } else {
                    (anchor.0, anchor.1 + d as i32 - 3)
                };
            }
        }
        Operator::TownHallRing => {
            let position = th(layout);
            let mut targets = rectangle(position, 4);
            targets.retain(|p| !occupied.contains(p));
            let mut pieces: Vec<_> = (0..layout.walls.len())
                .filter(|&i| !rectangle(position, 4).contains(&layout.walls[i].position))
                .collect();
            pieces.sort_by_key(|&i| {
                (
                    std::cmp::Reverse(distance(layout.walls[i].position, position)),
                    i,
                )
            });
            for (i, target) in pieces.into_iter().zip(targets) {
                layout.walls[i].position = target;
            }
        }
        Operator::SeamClosure => {
            let mut board = Board::new();
            for b in &layout.buildings {
                board.take(b.position, size(context, &b.key, false)?);
            }
            for t in &layout.traps {
                board.take(t.position, size(context, &t.key, true)?);
            }
            let mut gaps = Vec::new();
            for y in 0..44 {
                for x in 0..44 {
                    if !occupied.contains(&(x, y))
                        && board.fits((x, y), 1)
                        && ((occupied.contains(&(x - 1, y)) && occupied.contains(&(x + 1, y)))
                            || (occupied.contains(&(x, y - 1)) && occupied.contains(&(x, y + 1))))
                    {
                        gaps.push((x, y));
                    }
                }
            }
            if gaps.is_empty() {
                return Err(inapplicable("no one-tile seam"));
            }
            layout.walls[index].position = gaps[rng.index(gaps.len())];
        }
        _ => unreachable!(),
    }
    Ok(())
}
