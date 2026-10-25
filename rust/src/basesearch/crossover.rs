//! Spatial cuts copy positions/modes by stable owned ID. Missing parental
//! instances can never duplicate a TH or change the wall-level multiset.
use crate::layout::AdmittedLayout;

use super::repair::{conserved, finish, RepairLimits};
use super::{Context, Proposal, ProposalRng, Rejection};

pub fn crossover(
    context: &Context,
    a: &AdmittedLayout,
    b: &AdmittedLayout,
    seed: u64,
    limits: RepairLimits,
) -> Result<Proposal, Rejection> {
    context.check(a)?;
    context.check(b)?;
    if a.account_identity() != b.account_identity()
        || a.policy() != b.policy()
        || !conserved(a.layout(), b.layout())
    {
        return Err(Rejection::Conservation(
            "crossover requires identical ordered owned IDs, keys and levels".to_owned(),
        ));
    }
    let mut rng = ProposalRng::new(seed);
    let cut = 12 + rng.index(20) as i32;
    let axis = rng.index(4);
    let side = |p: (i32, i32)| match axis {
        0 => p.0 >= cut,
        1 => p.1 >= cut,
        2 => p.0 + p.1 >= 2 * cut,
        _ => p.0 - p.1 >= cut - 22,
    };
    let mut draft = a.layout().clone();
    macro_rules! cut_pieces {
        ($field:ident) => {
            for (piece, other) in draft.$field.iter_mut().zip(&b.layout().$field) {
                if !side(piece.position) && !side(other.position) {
                    *piece = other.clone();
                }
            }
        };
    }
    cut_pieces!(buildings);
    cut_pieces!(traps);
    cut_pieces!(walls);
    let mut proposal = finish(context, a, draft, "spatial_crossover", seed, limits)?;
    proposal.parents.push(b.physical_identity().to_owned());
    Ok(proposal)
}
