//! Bounded transactional repair. Restore only known parent instances; never
//! invent inventory, change levels, or turn unknown content into known content.
use std::collections::BTreeSet;

use crate::layout::admit::content_problems;
use crate::layout::model::{Layout, Mode};
use crate::layout::{admit, AdmittedLayout};

use super::spatial::{size, Board};
use super::{Context, Proposal, ProposalRng, Rejection, RepairAction};

#[derive(Clone, Copy, Debug)]
pub struct RepairLimits {
    pub tile_checks: usize,
    pub relocations: usize,
}

impl Default for RepairLimits {
    fn default() -> Self {
        Self {
            tile_checks: 200_000,
            relocations: 512,
        }
    }
}

pub fn conserved(parent: &Layout, child: &Layout) -> bool {
    parent.town_hall == child.town_hall
        && parent.setup.levels == child.setup.levels
        && parent.setup.hero_levels == child.setup.hero_levels
        && parent.setup.wall_level == child.setup.wall_level
        && parent
            .buildings
            .iter()
            .map(|b| (&b.id, &b.key))
            .eq(child.buildings.iter().map(|b| (&b.id, &b.key)))
        && parent
            .traps
            .iter()
            .map(|t| (&t.id, &t.key))
            .eq(child.traps.iter().map(|t| (&t.id, &t.key)))
        && parent
            .walls
            .iter()
            .map(|w| (&w.id, &w.level))
            .eq(child.walls.iter().map(|w| (&w.id, &w.level)))
}

fn restore(
    parent: &Layout,
    child: &mut Layout,
    actions: &mut Vec<RepairAction>,
) -> Result<(), Rejection> {
    // Order is engine-observable. Restore the parent's order as well as IDs.
    macro_rules! restore_pieces {
        ($field:ident, $same:expr) => {{
            let ordered = parent
                .$field
                .iter()
                .map(|p| &p.id)
                .eq(child.$field.iter().map(|p| &p.id));
            if ordered {
                for (original, piece) in parent.$field.iter().zip(&child.$field) {
                    if !($same)(original, piece) {
                        return Err(Rejection::Conservation(format!(
                            "changed key/level {}",
                            piece.id
                        )));
                    }
                }
            } else {
                let mut ids = BTreeSet::new();
                for piece in &child.$field {
                    if !ids.insert(&piece.id) {
                        return Err(Rejection::Conservation("duplicate instance".to_owned()));
                    }
                    let original =
                        parent
                            .$field
                            .iter()
                            .find(|p| p.id == piece.id)
                            .ok_or_else(|| {
                                Rejection::Conservation(format!("unknown instance {}", piece.id))
                            })?;
                    if !($same)(original, piece) {
                        return Err(Rejection::Conservation(format!(
                            "changed key/level {}",
                            piece.id
                        )));
                    }
                }
                child.$field = parent
                    .$field
                    .iter()
                    .map(|original| {
                        child
                            .$field
                            .iter()
                            .find(|p| p.id == original.id)
                            .cloned()
                            .unwrap_or_else(|| {
                                actions.push(RepairAction {
                                    instance: original.id.clone(),
                                    description:
                                        "restored missing owned piece at parental position"
                                            .to_owned(),
                                });
                                original.clone()
                            })
                    })
                    .collect();
            }
        }};
    }
    restore_pieces!(
        buildings,
        |a: &crate::layout::model::BuildingPlacement,
         b: &crate::layout::model::BuildingPlacement| a.key == b.key
    );
    restore_pieces!(
        traps,
        |a: &crate::layout::model::TrapPlacement, b: &crate::layout::model::TrapPlacement| a.key
            == b.key
    );
    restore_pieces!(
        walls,
        |a: &crate::layout::model::WallPiece, b: &crate::layout::model::WallPiece| a.level
            == b.level
    );
    if !conserved(parent, child) {
        return Err(Rejection::Conservation(
            "fixed inventory or level ledger changed".to_owned(),
        ));
    }
    Ok(())
}

pub fn finish(
    context: &Context,
    parent: &AdmittedLayout,
    mut draft: Layout,
    operator: &str,
    seed: u64,
    limits: RepairLimits,
) -> Result<Proposal, Rejection> {
    context.check(parent)?;
    let mut actions = Vec::new();
    restore(parent.layout(), &mut draft, &mut actions)?;
    if actions.len() > limits.relocations {
        return Err(Rejection::RepairBudget);
    }
    // Mode repair is deliberately narrow. Keep the first geared copy; all
    // other content errors (including illegal levels) go to admission unchanged.
    for key in ["at", "cannon", "mortar"] {
        let mut geared = false;
        let forbidden = key == "at" && draft.buildings.iter().any(|b| b.key == "mgt");
        for building in &mut draft.buildings {
            if building.key == key && building.mode.is_some_and(Mode::geared) {
                if geared || forbidden {
                    building.mode = Some(Mode::Normal);
                    actions.push(RepairAction {
                        instance: building.id.clone(),
                        description: "removed duplicate or merged gear allocation".to_owned(),
                    });
                } else {
                    geared = true;
                }
            }
        }
    }
    let content = content_problems(&draft, &context.catalog);
    if !content.issues.is_empty() {
        return Err(Rejection::Admission(content));
    }
    let mut board = Board::new();
    let mut pending = Vec::new();
    // Retain unaffected pieces first, then take proposed positions. This
    // prevents a nudge from displacing the rest of an otherwise legal base.
    for unchanged in [true, false] {
        for (i, building) in draft.buildings.iter().enumerate() {
            if (building.position == parent.layout().buildings[i].position) == unchanged {
                let s = size(context, &building.key, false)?;
                if !board.take(building.position, s) {
                    pending.push((0, i, s, building.position));
                }
            }
        }
        for (i, wall) in draft.walls.iter().enumerate() {
            if (wall.position == parent.layout().walls[i].position) == unchanged
                && !board.take(wall.position, 1)
            {
                pending.push((1, i, 1, wall.position));
            }
        }
        for (i, trap) in draft.traps.iter().enumerate() {
            if (trap.position == parent.layout().traps[i].position) == unchanged {
                let s = size(context, &trap.key, true)?;
                if !board.take(trap.position, s) {
                    pending.push((2, i, s, trap.position));
                }
            }
        }
    }
    if pending.len() + actions.len() > limits.relocations {
        return Err(Rejection::RepairBudget);
    }
    // Large seam conflicts first, deterministic seeded ties.
    let mut rng = ProposalRng::new(seed);
    let mut pending: Vec<_> = pending.into_iter().map(|p| (p, rng.next_u64())).collect();
    pending.sort_by_key(|(p, tie)| (-p.2, *tie));
    let mut budget = limits.tile_checks;
    for ((kind, index, s, target), _) in pending {
        let position = board.near(target, s, &mut budget)?;
        let id = match kind {
            0 => {
                draft.buildings[index].position = position;
                draft.buildings[index].id.clone()
            }
            1 => {
                draft.walls[index].position = position;
                draft.walls[index].id.clone()
            }
            _ => {
                draft.traps[index].position = position;
                draft.traps[index].id.clone()
            }
        };
        actions.push(RepairAction {
            instance: id,
            description: format!("relocated seam/footprint conflict {target:?} -> {position:?}"),
        });
    }
    if actions.len() > limits.relocations {
        return Err(Rejection::RepairBudget);
    }
    let candidate = admit(
        draft,
        &context.rules,
        context.catalog.clone(),
        parent.policy(),
    )
    .map_err(Rejection::Admission)?;
    if !conserved(parent.layout(), candidate.layout())
        || candidate.account_identity() != parent.account_identity()
    {
        return Err(Rejection::Conservation(
            "admission changed fixed account".to_owned(),
        ));
    }
    let mut changed_instances = Vec::new();
    macro_rules! changes {
        ($field:ident) => {
            for (a, b) in parent
                .layout()
                .$field
                .iter()
                .zip(&candidate.layout().$field)
            {
                if a != b {
                    changed_instances.push(a.id.clone());
                }
            }
        };
    }
    changes!(buildings);
    changes!(walls);
    changes!(traps);
    if parent.layout().setup != candidate.layout().setup {
        changed_instances.push("defense_setup".to_owned());
    }
    if candidate.physical_identity() == parent.physical_identity() {
        return Err(Rejection::NotApplicable(
            "proposal leaves physical state unchanged".to_owned(),
        ));
    }
    Ok(Proposal {
        candidate,
        operator: operator.to_owned(),
        seed,
        parents: vec![parent.physical_identity().to_owned()],
        changed_instances,
        repair_actions: actions,
    })
}
