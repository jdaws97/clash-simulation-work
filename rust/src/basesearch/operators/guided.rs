//! Diagnostics are supplied by later Rust evaluation; M2 uses explicitly
//! synthetic maps. They cannot be reused across a layout or policy change.
use std::collections::BTreeMap;

use crate::layout::model::{Layout, Mode, Tile};
use crate::layout::AdmittedLayout;

use super::{inapplicable, swap, Operator};
use crate::basesearch::spatial::{distance, role, size, th};
use crate::basesearch::{Context, ProposalRng, Rejection};

#[derive(Clone, Debug)]
pub struct Guidance {
    pub layout_identity: String,
    pub account_identity: String,
    pub policy_identity: String,
    pub ground: BTreeMap<Tile, u64>,
    pub air: BTreeMap<Tile, u64>,
    pub heroes: BTreeMap<Tile, u64>,
    pub breaches: BTreeMap<Tile, u64>,
    pub early_loss: BTreeMap<String, u64>,
}

#[derive(Clone, Copy)]
pub struct Guide<'a> {
    pub diagnostics: &'a Guidance,
    pub policy_identity: &'a str,
}

impl Guide<'_> {
    pub fn validate(self, parent: &AdmittedLayout) -> Result<(), Rejection> {
        if self.diagnostics.layout_identity != parent.physical_identity()
            || self.diagnostics.account_identity != parent.account_identity()
            || self.diagnostics.policy_identity != self.policy_identity
        {
            return Err(Rejection::StaleGuidance);
        }
        Ok(())
    }
}

fn hottest(map: &BTreeMap<Tile, u64>) -> Option<Tile> {
    map.iter()
        .max_by_key(|(tile, heat)| (**heat, std::cmp::Reverse(**tile)))
        .map(|(&tile, _)| tile)
}

fn heat(map: &BTreeMap<Tile, u64>, position: Tile) -> u64 {
    map.iter()
        .filter(|(&tile, _)| distance(tile, position) <= 25)
        .fold(0u64, |total, (_, heat)| total.saturating_add(*heat))
}

pub fn edit(
    context: &Context,
    layout: &mut Layout,
    operator: Operator,
    rng: &mut ProposalRng,
    guide: &Guidance,
) -> Result<(), Rejection> {
    match operator {
        Operator::TrafficTraps => {
            if layout.traps.is_empty() {
                return Err(inapplicable("no traps"));
            }
            let i = rng.index(layout.traps.len());
            let trap = &mut layout.traps[i];
            let map = if matches!(trap.key.as_str(), "airbomb" | "seeking")
                || trap.mode == Some(Mode::Air)
            {
                &guide.air
            } else if trap.key == "tornado" {
                &guide.heroes
            } else {
                &guide.ground
            };
            trap.position = hottest(map).ok_or_else(|| inapplicable("no matching traffic"))?;
        }
        Operator::BusyDefenses | Operator::EarlyLostDeeper => {
            let mut candidates: Vec<_> = (0..layout.buildings.len())
                .filter(|&i| {
                    role(&layout.buildings[i].key) <= 55 && layout.buildings[i].key != "th"
                })
                .collect();
            candidates.sort_by_key(|&i| {
                let b = &layout.buildings[i];
                if operator == Operator::BusyDefenses {
                    (heat(&guide.ground, b.position), i)
                } else {
                    (
                        u64::MAX - guide.early_loss.get(&b.id).copied().unwrap_or(0),
                        i,
                    )
                }
            });
            let center = th(layout);
            for i in candidates {
                let b = &layout.buildings[i];
                let s = size(context, &b.key, false)?;
                let mut partners: Vec<_> = (0..layout.buildings.len())
                    .filter(|&j| {
                        let other = &layout.buildings[j];
                        j != i
                            && other.key != "th"
                            && role(&other.key) > role(&b.key)
                            && size(context, &other.key, false) == Ok(s)
                            && if operator == Operator::BusyDefenses {
                                heat(&guide.ground, other.position)
                                    > heat(&guide.ground, b.position)
                            } else {
                                guide.early_loss.get(&other.id).copied().unwrap_or(0)
                                    < guide.early_loss.get(&b.id).copied().unwrap_or(0)
                                    && distance(other.position, center)
                                        < distance(b.position, center)
                            }
                    })
                    .collect();
                partners.sort_by_key(|&j| {
                    let other = &layout.buildings[j];
                    if operator == Operator::BusyDefenses {
                        (-(heat(&guide.ground, other.position) as i128), j)
                    } else {
                        (distance(other.position, center) as i128, j)
                    }
                });
                if let Some(&j) = partners.first() {
                    swap(layout, i, j);
                    return Ok(());
                }
            }
            return Err(inapplicable("no guided same-size improvement"));
        }
        Operator::BreachReinforcement => {
            let breach =
                hottest(&guide.breaches).ok_or_else(|| inapplicable("no observed breach"))?;
            if layout.walls.is_empty() {
                return Err(inapplicable("no walls"));
            }
            let center = th(layout);
            let step = (
                (center.0 - breach.0).signum(),
                (center.1 - breach.1).signum(),
            );
            let mut walls: Vec<_> = (0..layout.walls.len()).collect();
            walls.sort_by_key(|&i| {
                (
                    guide
                        .breaches
                        .get(&layout.walls[i].position)
                        .copied()
                        .unwrap_or(0),
                    std::cmp::Reverse(distance(layout.walls[i].position, breach)),
                    i,
                )
            });
            for (offset, i) in walls.into_iter().take(3).enumerate() {
                layout.walls[i].position = (
                    breach.0 + step.0 + if step.1 != 0 { offset as i32 - 1 } else { 0 },
                    breach.1 + step.1 + if step.1 == 0 { offset as i32 - 1 } else { 0 },
                );
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
