//! Search-only role heuristics using meta_armies.py:112-178 and the catalog.
//! These proposals are generic attacks, never newly claimed player playbooks.

use crate::catalog::Catalog;
use crate::labels::Tag;
use crate::stats::Level;

use super::account::{AccountRules, EligibleUnit};
use super::genome::{ArmyGenome, UnitCount};
use super::operators::empty_immigrant;
use super::util::Random;

fn flying(catalog: &Catalog, unit: &EligibleUnit) -> bool {
    let spec = &catalog.unit(&unit.name).spec;
    spec.flying_override
        .unwrap_or_else(|| catalog.numbers(&unit.name, &Level::Int(unit.level)).flying)
}

fn can_add(values: &[UnitCount], roster: &[EligibleUnit], unit: &EligibleUnit) -> bool {
    if !unit.boosted {
        return true;
    }
    let mut boosted_types = 0;
    for value in values {
        if value.count == 0 {
            continue;
        }
        if value.name == unit.name {
            return true;
        }
        if roster.iter().any(|item| item.name == value.name && item.boosted) {
            boosted_types += 1;
        }
    }
    boosted_types < 2
}

fn add(values: &mut Vec<UnitCount>, unit: &EligibleUnit, count: usize) {
    if let Some(value) = values.iter_mut().find(|value| value.name == unit.name) {
        value.count += count;
    } else {
        values.push(UnitCount {
            name: unit.name.clone(),
            count,
        });
    }
}

fn used(values: &[UnitCount], roster: &[EligibleUnit]) -> usize {
    values
        .iter()
        .map(|value| {
            let unit = roster
                .iter()
                .find(|unit| unit.name == value.name)
                .expect("eligible troop");
            value.count * unit.housing
        })
        .sum()
}

fn support(
    genome: &mut ArmyGenome,
    account: &AccountRules,
    pool: &[&EligibleUnit],
    budget: usize,
    main_space: usize,
    rng: &mut Random,
) {
    let budget = budget.min(320 - used(&genome.troops, &account.roster.troops));
    let eligible: Vec<_> = pool
        .iter()
        .copied()
        .filter(|unit| {
            let count = genome
                .troops
                .iter()
                .find(|value| value.name == unit.name)
                .map_or(0, |value| value.count);
            unit.housing <= budget
                && (count + 1) * unit.housing < main_space
                && can_add(&genome.troops, &account.roster.troops, unit)
        })
        .collect();
    if eligible.is_empty() {
        return;
    }
    let unit = eligible[rng.index(eligible.len())];
    let existing = genome
        .troops
        .iter()
        .find(|value| value.name == unit.name)
        .map_or(0, |value| value.count);
    let maximum = (budget / unit.housing).min((main_space - 1) / unit.housing - existing);
    add(&mut genome.troops, unit, 1 + rng.index(maximum));
}

/// Every feasible owned spell remains selectable; three quarters of draws
/// prefer common pairings. This is a proposal bias, not an oracle restriction.
fn spells(
    roster: &[EligibleUnit],
    cap: usize,
    preferred: &[&str],
    rng: &mut Random,
) -> Vec<UnitCount> {
    let mut values = Vec::new();
    let mut free = cap;
    loop {
        let eligible: Vec<_> = roster
            .iter()
            .filter(|unit| unit.housing <= free)
            .collect();
        if eligible.is_empty() {
            break;
        }
        let paired: Vec<_> = eligible
            .iter()
            .copied()
            .filter(|unit| preferred.contains(&unit.name.as_str()))
            .collect();
        let pool = if !paired.is_empty() && rng.index(4) != 0 {
            &paired
        } else {
            &eligible
        };
        let unit = pool[rng.index(pool.len())];
        add(&mut values, unit, 1);
        free -= unit.housing;
    }
    values
}

pub fn immigrant(
    account: &AccountRules,
    catalog: &Catalog,
    rng: &mut Random,
) -> Result<ArmyGenome, String> {
    let main = &account.roster.troops[rng.index(account.roster.troops.len())];
    for_main(account, catalog, main, rng)
}

pub(super) fn for_main(
    account: &AccountRules,
    catalog: &Catalog,
    main: &EligibleUnit,
    rng: &mut Random,
) -> Result<ArmyGenome, String> {
    // Integral counts keep the main at 45-80% of the 320-space camp.
    let minimum = (144 + main.housing - 1) / main.housing;
    let maximum = 256 / main.housing;
    if minimum > maximum {
        return Err(format!("no 45-80% themed count for {}", main.name));
    }
    let count = minimum + rng.index(maximum - minimum + 1);
    let main_space = count * main.housing;
    let air = flying(catalog, main);
    let mut genome = empty_immigrant(account, rng);
    add(&mut genome.troops, main, count);
    let others: Vec<_> = account
        .roster
        .troops
        .iter()
        .filter(|unit| unit.name != main.name)
        .collect();
    let breakers: Vec<_> = others
        .iter()
        .copied()
        .filter(|unit| catalog.unit(&unit.name).spec.prefer == Tag::Wall)
        .collect();
    if !air {
        support(
            &mut genome,
            account,
            &breakers,
            8 + rng.index(9),
            main_space,
            rng,
        );
    }
    let healers: Vec<_> = others
        .iter()
        .copied()
        .filter(|unit| {
            let spec = &catalog.unit(&unit.name).spec;
            matches!(spec.attack, Tag::Heal | Tag::HealChain) && (!air || spec.heal_air)
        })
        .collect();
    support(
        &mut genome,
        account,
        &healers,
        20 + rng.index(23),
        main_space,
        rng,
    );
    let tanks: Vec<_> = others
        .iter()
        .copied()
        .filter(|unit| {
            let spec = &catalog.unit(&unit.name).spec;
            let numbers = catalog.numbers(&unit.name, &Level::Int(unit.level));
            flying(catalog, unit) == air
                && numbers.hp / unit.housing as f64 >= 130.0
                && !matches!(spec.attack, Tag::Heal | Tag::HealChain)
        })
        .collect();
    support(
        &mut genome,
        account,
        &tanks,
        30 + rng.index(19),
        main_space,
        rng,
    );
    let funnel: Vec<_> = others
        .iter()
        .copied()
        .filter(|unit| {
            let spec = &catalog.unit(&unit.name).spec;
            flying(catalog, unit) == air
                && spec.prefer == Tag::Any
                && !matches!(spec.attack, Tag::Heal | Tag::HealChain)
        })
        .collect();
    support(
        &mut genome,
        account,
        &funnel,
        16 + rng.index(17),
        main_space,
        rng,
    );
    let matching: Vec<_> = others
        .iter()
        .copied()
        .filter(|unit| {
            let spec = &catalog.unit(&unit.name).spec;
            flying(catalog, unit) == air
                && spec.prefer != Tag::Wall
                && !matches!(spec.attack, Tag::Heal | Tag::HealChain)
        })
        .collect();
    // Small bundles keep the remaining camp mixed, with the selected main
    // still the largest share. Exact residual repair follows below.
    loop {
        let before = used(&genome.troops, &account.roster.troops);
        support(&mut genome, account, &matching, 32, main_space, rng);
        if used(&genome.troops, &account.roster.troops) == before {
            break;
        }
    }
    let preferred: &[&str] = if air {
        &[
            "Rage Spell",
            "Freeze Spell",
            "Haste Spell",
            "Invisibility Spell",
        ]
    } else {
        &["Healing Spell", "Rage Spell", "Freeze Spell", "Jump Spell"]
    };
    genome.spells = spells(&account.roster.spells, 11, preferred, rng);
    genome.cc_spells = spells(&account.roster.spells, 3, preferred, rng);
    let mut free = 50;
    loop {
        let eligible: Vec<_> = account
            .roster
            .troops
            .iter()
            .filter(|unit| unit.housing <= free)
            .collect();
        if eligible.is_empty() {
            break;
        }
        let unit = eligible[rng.index(eligible.len())];
        let count = 1 + rng.index(free / unit.housing);
        add(&mut genome.cc_troops, unit, count);
        free -= count * unit.housing;
    }
    account.repair(&mut genome)?;
    let repaired_space = genome
        .troops
        .iter()
        .find(|unit| unit.name == main.name)
        .map_or(0, |unit| unit.count * main.housing);
    if !(144..=256).contains(&repaired_space)
        || genome.main_troop(account) != Some(main.name.as_str())
    {
        return Err("repair changed the themed main troop or its housing range".to_owned());
    }
    Ok(genome)
}
