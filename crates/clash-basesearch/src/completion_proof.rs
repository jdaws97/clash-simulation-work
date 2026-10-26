//! Executable, dependency-free acceptance checks. The receipt records checks
//! actually executed here; the workspace tests add native battle/resume gates.
use std::collections::{BTreeMap, BTreeSet};

use clash_scoring::scoring::{Outcome, Scenario};

use crate::eval::Row;
use crate::json::Json;
use crate::util::{num, object, string};

pub(crate) fn synthetic_row(
    group: usize,
    stratum: &str,
    weight: f64,
    stars: i64,
    destruction: f64,
) -> Row {
    Row {
        group_id: format!("{stratum}/{group}"),
        stratum: stratum.to_owned(),
        population_weight: weight,
        scenario: Scenario {
            army: stratum.to_owned(),
            town_hall: 16,
            angle: 0.0,
            seed: group as i64,
            weight: 1.0,
            modifier: None,
            group: group as i64,
            tactic: Json::Null,
            charge: None,
            full_scout: false,
        },
        outcome: Outcome {
            stars,
            destruction,
            th_destroyed: stars >= 2,
            time: 30.0,
        },
        source_index: 0,
        plan: Json::Null,
    }
}

/// An adaptive family containing every subset of a finite sample domain. The
/// selected incumbent memorizes training draws and is strong only there. Its
/// exact population utility is below the fixed challenger in every trial.
pub(crate) fn adaptive_racing_check() -> Result<Json, String> {
    const TRIALS: usize = 32;
    const GROUPS: usize = 4096;
    const DOMAIN: usize = 1 << 20;
    let strata = BTreeMap::from([("adaptive".to_owned(), 1.0)]);
    let mut reused_false = 0;
    let mut fresh_false = 0;
    for trial in 0..TRIALS {
        let mut training_rng = crate::ProposalRng::new(137 + trial as u64);
        let mut validation_rng = crate::ProposalRng::new(99823 + trial as u64);
        let training: Vec<_> = (0..GROUPS).map(|_| training_rng.index(DOMAIN)).collect();
        let memorized: BTreeSet<_> = training.iter().copied().collect();
        let child = (0..GROUPS)
            .map(|group| synthetic_row(group, "adaptive", 1.0, 2, 50.0))
            .collect::<Vec<_>>();
        let child_utility = crate::eval::utility(child[0].outcome, "ranked");
        let incumbent_mean = 40.0 * memorized.len() as f64 / DOMAIN as f64;
        if child_utility <= incumbent_mean {
            return Err("adaptive synthetic challenger must be better in population".to_owned());
        }
        for (reuse, false_count) in [(true, &mut reused_false), (false, &mut fresh_false)] {
            let incumbent = (0..GROUPS)
                .map(|group| {
                    let draw = if reuse {
                        training[group]
                    } else {
                        validation_rng.index(DOMAIN)
                    };
                    let (stars, destruction) = if memorized.contains(&draw) {
                        (0, 0.0)
                    } else {
                        (3, 100.0)
                    };
                    synthetic_row(group, "adaptive", 1.0, stars, destruction)
                })
                .collect::<Vec<_>>();
            for look in [512, 1024, 2048, GROUPS] {
                if crate::race::paired(
                    &child[..look],
                    &incumbent[..look],
                    &strata,
                    "ranked",
                    0.0,
                    0.0125,
                    look,
                )?
                .is_some_and(|interval| interval.upper < 0.0)
                {
                    *false_count += 1;
                    break;
                }
            }
        }
    }
    if reused_false != TRIALS || fresh_false != 0 {
        return Err(format!(
            "adaptive race regression: reused={reused_false}, fresh={fresh_false}, trials={TRIALS}"
        ));
    }
    Ok(object([
        ("evidence", string("declared synthetic adaptive subset family; exact finite-domain population means; not real-game calibration")),
        ("trials", num(TRIALS)),
        ("groups_per_trial", num(GROUPS)),
        ("domain", num(DOMAIN)),
        ("reused_false_eliminations", num(reused_false)),
        ("fresh_false_eliminations", num(fresh_false)),
        ("reused_false_elimination_rate", Json::Num(reused_false as f64 / TRIALS as f64)),
        ("fresh_false_elimination_rate", Json::Num(fresh_false as f64 / TRIALS as f64)),
    ]))
}

pub fn run() -> Result<Json, String> {
    let require = |condition: bool, message: &str| -> Result<(), String> {
        if condition {
            Ok(())
        } else {
            Err(message.to_owned())
        }
    };
    let cycle = vec![
        vec![0.0, -1.0, 1.0],
        vec![1.0, 0.0, -1.0],
        vec![-1.0, 1.0, 0.0],
    ];
    let solution = crate::psro::solve(&cycle, 4096)?;
    require(
        solution.upper - solution.lower < 1e-9,
        "cyclic restricted-game residual",
    )?;
    let pure = crate::psro::solve(&[vec![1.0, 2.0], vec![-2.0, -1.0]], 16_384)?;
    require(
        pure.defender[0] > 0.98 && pure.attacker[0] > 0.98 && pure.upper - pure.lower < 0.1,
        "restricted-game signs",
    )?;
    let strata = BTreeMap::from([("ordinary".to_owned(), 1.0)]);
    let mut cases = 0;
    let mut false_eliminations = 0;
    for mask in 0..256 {
        let mut a = Vec::new();
        let mut b = Vec::new();
        let mut eliminated = false;
        for group in 0..8 {
            a.push(synthetic_row(
                group,
                "ordinary",
                1.0,
                if mask & (1 << group) == 0 { 0 } else { 3 },
                50.0,
            ));
            b.push(synthetic_row(group, "ordinary", 1.0, 1, 50.0));
            if let Some(interval) =
                crate::race::paired(&a, &b, &strata, "ranked", 0.0, 0.05, group + 1)?
            {
                if interval.upper < 0.0 {
                    eliminated = true;
                }
                require(
                    interval.upper > interval.lower,
                    "zero observed variance lost uncertainty",
                )?;
            }
        }
        let complete = crate::eval::objective(&a, "ranked", 0, Some(0.0))?
            - crate::eval::objective(&b, "ranked", 0, Some(0.0))?;
        if eliminated && complete >= 0.0 {
            false_eliminations += 1;
        }
        cases += 1;
    }
    require(false_eliminations == 0, "enumerable race false elimination")?;
    let clear_loss: Vec<_> = (0..512)
        .map(|group| synthetic_row(group, "ordinary", 1.0, 3, 100.0))
        .collect();
    let clear_win: Vec<_> = (0..512)
        .map(|group| synthetic_row(group, "ordinary", 1.0, 0, 0.0))
        .collect();
    require(
        crate::race::paired(&clear_loss, &clear_win, &strata, "ranked", 0.0, 0.05, 1)?
            .is_some_and(|interval| interval.upper < 0.0),
        "race failed to eliminate a sufficiently replicated clear loss",
    )?;
    let a = vec![synthetic_row(0, "ordinary", 1.0, 0, 0.0)];
    require(
        crate::race::paired(&a, &a, &strata, "ranked", 0.0, 0.05, 1)?.is_none(),
        "sparse race did not continue",
    )?;
    let unequal = vec![
        synthetic_row(0, "majority", 0.75, 0, 0.0),
        synthetic_row(0, "minority", 0.25, 3, 100.0),
        synthetic_row(1, "minority", 0.25, 3, 100.0),
    ];
    let summary = crate::eval::summarise(&unequal)?;
    require(
        (summary.avg_stars - 0.75).abs() < 1e-12,
        "allocation changed population weights",
    )?;
    let known = crate::eval::objective(
        &[synthetic_row(0, "known", 1.0, 3, 100.0)],
        "war",
        0,
        Some(0.0),
    )?;
    require(known == -35.0, "war known-answer objective")?;
    let promotions = crate::race::halve(
        &[1.0, 4.0, 2.0, 3.0, 0.0, -1.0],
        &[false, false, false, false, true, false],
        0,
    );
    require(
        promotions == vec![1, 4],
        "halving/protected-cell known answer",
    )?;
    let executable = std::fs::read(std::env::current_exe().map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    Ok(object([
        ("adaptive_racing", adaptive_racing_check()?),
        ("schema", num(1)), ("evidence", string("declared enumerable synthetic outcomes; not real-game calibration")),
        ("executable_identity", string(crate::layout::json::identity(&executable))),
        ("enumerable_races", num(cases)), ("false_eliminations", num(false_eliminations)),
        ("zero_variance_sparse_unequal_weights_late_reversals", Json::Bool(true)),
        ("known_answer_objectives_halving", Json::Bool(true)),
        ("cyclic_game", solution.to_json()), ("pure_game", pure.to_json()),
        ("additional_workspace_test_gates", string("native scorer equivalence/hidden isolation, 1/4/16 workers, exact checkpoint continuation, tiny archive optimum, archive invalidation, report replay")),
    ]))
}
