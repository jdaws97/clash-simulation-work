//! Composition reporting over admitted recipes (meta_armies.py:61-69,330-343).
//! Search distance is an explicit heuristic, not a Python battle calculation.

use std::collections::BTreeMap;

use crate::json::Json;

use super::account::{AccountRules, EligibleUnit};
use super::genome::{ArmyGenome, UnitCount};
use super::util::{hash, number, object, string};

pub const VARIATION_LIMIT: f64 = 0.20;
pub const GENERIC_VALIDATION: &str = "generic attacker — no real-player playbook; less validated";

fn compartment(first: &[UnitCount], second: &[UnitCount], roster: &[EligibleUnit]) -> usize {
    let mut counts = BTreeMap::<&str, (usize, usize)>::new();
    for unit in first {
        counts.entry(&unit.name).or_default().0 += unit.count;
    }
    for unit in second {
        counts.entry(&unit.name).or_default().1 += unit.count;
    }
    counts
        .into_iter()
        .map(|(name, (a, b))| {
            let housing = roster
                .iter()
                .find(|unit| unit.name == name)
                .expect("admitted composition unit")
                .housing;
            a.abs_diff(b) * housing
        })
        .sum()
}

/// Keep brewed/donated inventories separate, as in meta_armies.py:132-143.
/// Heroes, equipment, siege, levels and plan genes do not affect composition.
pub fn distance(first: &ArmyGenome, second: &ArmyGenome, account: &AccountRules) -> usize {
    compartment(&first.troops, &second.troops, &account.roster.troops)
        + compartment(&first.spells, &second.spells, &account.roster.spells)
        + compartment(&first.cc_troops, &second.cc_troops, &account.roster.troops)
        + compartment(&first.cc_spells, &second.cc_spells, &account.roster.spells)
}

pub fn label(distance: usize) -> &'static str {
    if distance == 0 {
        "real"
    } else if normalized(distance) <= VARIATION_LIMIT {
        "variation"
    } else {
        "new composition"
    }
}

fn normalized(distance: usize) -> f64 {
    distance as f64 / (2 * (320 + 11 + 50 + 3)) as f64
}

pub fn report(genome: &ArmyGenome, seeds: &[ArmyGenome], account: &AccountRules) -> Json {
    let nearest = seeds
        .iter()
        .map(|seed| (distance(genome, seed, account), seed.identity(), seed))
        .min_by(|(ad, ai, _), (bd, bi, _)| ad.cmp(bd).then_with(|| ai.cmp(bi)));
    let (distance, nearest_seed, label) = if let Some((distance, identity, seed)) = nearest {
        (
            Json::Num(normalized(distance)),
            object([
                ("id", string(format!("{:016x}", hash(identity.as_bytes())))),
                ("genome", seed.to_json()),
                ("housing_l1", number(distance)),
            ]),
            label(distance),
        )
    } else {
        (Json::Null, Json::Null, "new composition")
    };
    let cited = genome.plan.family != "generic";
    object([
        ("label", string(label)),
        ("distance", distance),
        ("nearest_seed", nearest_seed),
        ("metric", string("housing-weighted L1 over camp troops, brewed spells, CC troops and CC spells separately; normalized by 2*(320+11+50+3)")),
        ("variation_max_distance", Json::Num(VARIATION_LIMIT)),
        ("seed_scope", string("all account-repaired admitted meta/observed/custom/playbook seeds, before --families filtering")),
        ("label_scope", string("real means an exact seed composition, not real-game validation or a matching hero/loadout/plan")),
        ("cited_playbook", Json::Bool(cited)),
        (
            "plan_validation",
            if cited {
                string(format!("cited playbook: {}", genome.plan.family))
            } else {
                string(GENERIC_VALIDATION)
            },
        ),
    ])
}
