//! Explicit, independently seedable operator families.
pub mod guided;
pub mod macro_ops;
pub mod setup;
pub mod walls;

use crate::layout::AdmittedLayout;

use super::repair::{finish, RepairLimits};
use super::spatial::size;
use super::{Context, Proposal, ProposalRng, Rejection};
use guided::Guide;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Operator {
    Nudge,
    Swap,
    Relocate,
    TrapRelocate,
    BuildingMode,
    SkeletonMode,
    HeroPermutation,
    HeroSelection,
    CcPackage,
    Guardian,
    WallRelocate,
    WallRunShift,
    WallSplit,
    WallMerge,
    TownHallRing,
    SeamClosure,
    RoleRepack,
    TownHallDeepest,
    StrongestInward,
    SplashInward,
    AirDefenseSpread,
    FireballSpread,
    OuterScreen,
    CoreRotation,
    CoreFlank,
    Transpose,
    TrapsToCore,
    TrafficTraps,
    BusyDefenses,
    EarlyLostDeeper,
    BreachReinforcement,
}

impl Operator {
    pub const ALL: [Self; 31] = [
        Self::Nudge,
        Self::Swap,
        Self::Relocate,
        Self::TrapRelocate,
        Self::BuildingMode,
        Self::SkeletonMode,
        Self::HeroPermutation,
        Self::HeroSelection,
        Self::CcPackage,
        Self::Guardian,
        Self::WallRelocate,
        Self::WallRunShift,
        Self::WallSplit,
        Self::WallMerge,
        Self::TownHallRing,
        Self::SeamClosure,
        Self::RoleRepack,
        Self::TownHallDeepest,
        Self::StrongestInward,
        Self::SplashInward,
        Self::AirDefenseSpread,
        Self::FireballSpread,
        Self::OuterScreen,
        Self::CoreRotation,
        Self::CoreFlank,
        Self::Transpose,
        Self::TrapsToCore,
        Self::TrafficTraps,
        Self::BusyDefenses,
        Self::EarlyLostDeeper,
        Self::BreachReinforcement,
    ];

    pub fn name(self) -> String {
        format!("{self:?}")
    }
}

pub fn propose(
    context: &Context,
    parent: &AdmittedLayout,
    operator: Operator,
    seed: u64,
    guide: Option<Guide<'_>>,
    limits: RepairLimits,
) -> Result<Proposal, Rejection> {
    context.check(parent)?;
    let mut draft = parent.layout().clone();
    let mut rng = ProposalRng::new(seed);
    use Operator::*;
    match operator {
        Nudge | Relocate => {
            if draft.buildings.is_empty() {
                return Err(inapplicable("no buildings"));
            }
            let index = rng.index(draft.buildings.len());
            let building = &mut draft.buildings[index];
            if operator == Nudge {
                let (dx, dy) = [(1, 0), (-1, 0), (0, 1), (0, -1)][rng.index(4)];
                building.position.0 += dx;
                building.position.1 += dy;
            } else {
                let s = size(context, &building.key, false)?;
                building.position = (
                    rng.index((45 - s) as usize) as i32,
                    rng.index((45 - s) as usize) as i32,
                );
            }
        }
        Swap => {
            if draft.buildings.len() < 2 {
                return Err(inapplicable("fewer than two buildings"));
            }
            let a = rng.index(draft.buildings.len());
            let s = size(context, &draft.buildings[a].key, false)?;
            let partners: Vec<_> = (0..draft.buildings.len())
                .filter(|&i| i != a && size(context, &draft.buildings[i].key, false) == Ok(s))
                .collect();
            if partners.is_empty() {
                return Err(inapplicable("no same-footprint partner"));
            }
            swap(&mut draft, a, partners[rng.index(partners.len())]);
        }
        TrapRelocate => {
            if draft.traps.is_empty() {
                return Err(inapplicable("no traps"));
            }
            let index = rng.index(draft.traps.len());
            let s = size(context, &draft.traps[index].key, true)?;
            draft.traps[index].position = (
                rng.index((45 - s) as usize) as i32,
                rng.index((45 - s) as usize) as i32,
            );
        }
        BuildingMode | SkeletonMode | HeroPermutation | HeroSelection | CcPackage | Guardian => {
            setup::edit(context, &mut draft, operator, &mut rng)?;
        }
        WallRelocate | WallRunShift | WallSplit | WallMerge | TownHallRing | SeamClosure => {
            walls::edit(context, &mut draft, operator, &mut rng)?;
        }
        TrafficTraps | BusyDefenses | EarlyLostDeeper | BreachReinforcement => {
            let guide = guide.ok_or_else(|| inapplicable("diagnostics required"))?;
            guide.validate(parent)?;
            guided::edit(context, &mut draft, operator, &mut rng, guide.diagnostics)?;
        }
        _ => macro_ops::edit(context, &mut draft, operator, &mut rng)?,
    }
    finish(context, parent, draft, &operator.name(), seed, limits)
}

pub(super) fn inapplicable(reason: &str) -> Rejection {
    Rejection::NotApplicable(reason.to_owned())
}

pub(super) fn swap(layout: &mut crate::layout::model::Layout, a: usize, b: usize) {
    let position = layout.buildings[a].position;
    layout.buildings[a].position = layout.buildings[b].position;
    layout.buildings[b].position = position;
}
