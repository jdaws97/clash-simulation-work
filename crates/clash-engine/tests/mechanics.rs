//! Declared-synthetic mechanics proofs. These test hypotheses, not game accuracy.
#[path = "support/mechanics.rs"]
mod support;

use std::sync::{Arc, OnceLock};

use clash_engine::catalog::Catalog;
use clash_engine::json::{self, Json};
use clash_engine::params::Params;
use clash_engine::state::{BuildingId, EntityRef, UnitRef, WallId};
use clash_engine::targeting::{ForcedRetarget, TargetMemory};
use clash_engine::{defense, plans, units};

fn catalog() -> Arc<Catalog> {
    static CATALOG: OnceLock<Arc<Catalog>> = OnceLock::new();
    Arc::clone(CATALOG.get_or_init(support::catalog))
}

fn fixture(index: usize, enabled: bool) -> (clash_engine::state::Battle, Vec<UnitRef>) {
    support::build(
        &support::fixtures().at("cases").arr()[index],
        enabled,
        catalog(),
    )
}

#[test]
fn all_flags_change_declared_synthetic_battles() {
    let text = support::evidence_text(catalog());
    let evidence = json::parse(&text).unwrap();
    assert_eq!(evidence.at("cases").arr().len(), 4);
    assert_eq!(evidence.at("synthetic"), &Json::Bool(true));
    assert_eq!(evidence.at("calibration"), &Json::Bool(false));
}

#[test]
fn committed_demo_evidence_is_reproducible() {
    let expected = json::parse(include_str!("../../../fixtures/mechanics/evidence.json")).unwrap();
    assert_eq!(support::evidence(catalog()), expected);
}

#[test]
fn registry_rejects_invalid_overrides_atomically() {
    for text in [
        r#"{"wall_cost":3,"unknown":1}"#,
        r#"{"target_list":1}"#,
        r#"{"wall_cost":true}"#,
        r#"{"ground_radius":-1}"#,
        r#"{"ground_radius":NaN}"#,
        r#"{"wall_cost":1,"wall_cost":2}"#,
        r#"{"internal_units_per_tile":0}"#,
        r#"{"poison_ramp":0}"#,
        r#"{"target_list_size":0}"#,
        r#"{"target_list_size":3.5}"#,
        r#"{"max_target_list_size":2}"#,
        r#"{"max_target_list_size":1025}"#,
        r#"{"new_target_delay.Unknown troop":2}"#,
    ] {
        let mut params = Params::default();
        assert!(params.apply(&json::parse(text).unwrap()).is_err(), "{text}");
        assert_eq!(params.wall_cost.to_bits(), 12.0_f64.to_bits());
    }
}

#[test]
fn game_csv_globals_match_registry_values() {
    let csv = include_str!("../../../data/source/gamecsv/v18.200.9/globals.csv");
    let params = Params::default();
    for (name, value) in [
        ("TARGET_LIST_SIZE", params.target_list_size),
        ("MAX_TARGET_LIST_SIZE", params.max_target_list_size),
        (
            "EXTRA_TARGET_PATH_COST_PENALTY",
            params.extra_target_path_cost_penalty,
        ),
        ("WALL_COST_BASE", params.wall_cost_base),
        ("FORGET_TARGET_TIME", params.forget_target_time),
        ("SELECTED_WALL_TIME", params.selected_wall_time),
        (
            "FORCE_NEW_TARGET_DEFAULT_MAX_NOISE",
            params.force_new_target_default_max_noise,
        ),
        (
            "FORCE_NEW_TARGET_JUMP_MAX_NOISE",
            params.force_new_target_jump_max_noise,
        ),
        (
            "FORCE_NEW_TARGET_TESLA_MAX_NOISE",
            params.force_new_target_tesla_max_noise,
        ),
    ] {
        let row = csv
            .lines()
            .find(|line| line.starts_with(&format!("{name},")))
            .unwrap();
        assert_eq!(
            row.split(',').nth(1).unwrap().parse::<f64>().unwrap(),
            value,
            "{name}"
        );
    }
    for (name, value) in [
        ("REMEMBER_ORIGINAL_TARGET", params.remember_original_target),
        (
            "RETARGET_AFTER_DESTROYING_WALL",
            params.retarget_after_destroying_wall,
        ),
        (
            "STICK_TO_TARGETED_BUILDING_WHEN_FORCING_RETARGET",
            params.stick_to_targeted_building_when_forcing_retarget,
        ),
        (
            "WARDEN_WAITS_FOR_GROUP_RETARGETING",
            params.warden_waits_for_group_retargeting,
        ),
    ] {
        let row = csv
            .lines()
            .find(|line| line.starts_with(&format!("{name},")))
            .unwrap();
        assert_eq!(row.split(',').nth(2).unwrap() == "TRUE", value, "{name}");
    }
}

#[test]
fn job_parameters_are_isolated_between_concurrent_battles() {
    let fixture = support::fixtures().at("cases").arr()[0].clone();
    let handles: Vec<_> = [false, true, false, true]
        .into_iter()
        .map(|enabled| {
            let case = fixture.clone();
            let catalog = catalog();
            std::thread::spawn(move || {
                let (battle, _) = support::build(&case, enabled, catalog);
                assert_eq!(battle.params.target_list, enabled);
                battle.params.wall_cost
            })
        })
        .collect();
    for handle in handles {
        assert_eq!(handle.join().unwrap(), 12.0);
    }
}

#[test]
fn catalog_delays_have_named_overrides() {
    let (mut battle, _) = fixture(0, false);
    let (name, &default) = battle.params.new_target_delays.iter().next().unwrap();
    let name = name.clone();
    battle
        .params
        .apply(&support::object(vec![(
            &format!("new_target_delay.{name}"),
            Json::Num(default + 0.1),
        )]))
        .unwrap();
    assert_eq!(
        units::new_target_delays(&battle).get(&name),
        Some(&(default + 0.1))
    );
    assert_eq!(catalog().new_target_delays.get(&name), Some(&default));
}

#[test]
fn nearest_candidate_cap_excludes_cheaper_fourth_target() {
    let (mut old, references) = fixture(0, false);
    let before = old.choose_target(references[0]).0;
    let (mut new, references) = fixture(0, true);
    let after = new.choose_target(references[0]).0;
    assert_eq!(before, Some(EntityRef::Building(BuildingId(3))));
    assert_ne!(after, before);
}

#[test]
fn forced_expansion_penalty_and_cap_change_target_choice() {
    let (mut battle, references) = fixture(0, true);
    let unit = references[0];
    battle.params.target_list_size = 1.0;
    battle.params.max_target_list_size = 4.0;
    battle
        .params
        .stick_to_targeted_building_when_forcing_retarget = false;
    battle.params.remember_original_target = false;
    battle.params.force_new_target_default_max_noise = 0.0;
    battle.params.extra_target_path_cost_penalty = 0.0;
    let primary = battle.choose_target(unit).0;
    battle.force_retarget(unit, ForcedRetarget::Default);
    let expanded = battle.choose_target(unit).0;
    assert_ne!(primary, expanded);
    assert_eq!(expanded, Some(EntityRef::Building(BuildingId(3))));
    battle.params.extra_target_path_cost_penalty = 100.0;
    battle.force_retarget(unit, ForcedRetarget::Default);
    assert_eq!(battle.choose_target(unit).0, primary);
    battle.params.max_target_list_size = 1.0;
    battle.params.extra_target_path_cost_penalty = 0.0;
    battle.force_retarget(unit, ForcedRetarget::Default);
    assert_eq!(battle.choose_target(unit).0, primary);
}

#[test]
fn remember_and_forced_stickiness_have_separate_effects() {
    let (mut battle, references) = fixture(0, true);
    let unit = references[0];
    let original = BuildingId(3);
    battle.target_memory.insert(
        unit,
        TargetMemory {
            original: Some(original),
            ..Default::default()
        },
    );
    assert_eq!(
        battle.choose_target(unit).0,
        Some(EntityRef::Building(original))
    );
    battle.params.remember_original_target = false;
    assert_ne!(
        battle.choose_target(unit).0,
        Some(EntityRef::Building(original))
    );
    battle.target_memory.get_mut(&unit).unwrap().original = Some(original);
    battle.force_retarget(unit, ForcedRetarget::Default);
    assert_eq!(
        battle.choose_target(unit).0,
        Some(EntityRef::Building(original))
    );
}

#[test]
fn forget_timer_excludes_a_target_without_progress() {
    let (mut battle, references) = fixture(0, true);
    let unit = references[0];
    let target = battle.choose_target(unit).0.unwrap();
    battle.unit_mut(unit).target = Some(target);
    battle.target_memory_tick(unit);
    battle.t = battle.params.forget_target_time / 1000.0 + 0.1;
    battle.target_memory_tick(unit);
    assert_eq!(battle.unit(unit).target, None);
    assert_ne!(battle.choose_target(unit).0, Some(target));
}

#[test]
fn damage_to_selected_wall_resets_forget_timer() {
    let (mut battle, references) = fixture(0, true);
    let unit = references[0];
    battle.unit_mut(unit).target = battle.choose_target(unit).0;
    battle.unit_mut(unit).wall_target = Some(WallId(0));
    battle.target_memory_tick(unit);
    battle.t = 5.0;
    battle.walls[0].hp -= 1.0;
    battle.target_memory_tick(unit);
    battle.t = 7.0;
    battle.target_memory_tick(unit);
    assert!(battle.unit(unit).target.is_some());
}

#[test]
fn wall_hold_expires_and_wall_destruction_retarget_is_optional() {
    for retarget in [false, true] {
        let (mut battle, references) = fixture(0, true);
        let unit = references[0];
        let target = battle.choose_target(unit).0;
        battle.unit_mut(unit).target = target;
        battle.unit_mut(unit).wall_target = Some(WallId(0));
        battle.target_memory.get_mut(&unit).unwrap().selected_wall = Some(WallId(0));
        battle.target_memory.get_mut(&unit).unwrap().wall_until = 4.0;
        battle.t = 4.1;
        battle.target_memory_tick(unit);
        assert_eq!(battle.target_memory.get(&unit).unwrap().selected_wall, None);
        battle.params.retarget_after_destroying_wall = retarget;
        battle.walls[0].alive = false;
        battle.target_memory_tick(unit);
        assert_eq!(battle.unit(unit).target.is_none(), retarget);
    }
}

#[test]
fn forced_noise_is_seeded_and_cause_specific() {
    for cause in [
        ForcedRetarget::Default,
        ForcedRetarget::Jump,
        ForcedRetarget::Tesla,
    ] {
        let mut pair = Vec::new();
        for _ in 0..2 {
            let (mut battle, references) = fixture(0, true);
            battle
                .params
                .stick_to_targeted_building_when_forcing_retarget = false;
            battle.force_retarget(references[0], cause);
            let chosen = battle.choose_target(references[0]).0;
            pair.push((chosen, battle.rng_mut().random().to_bits()));
        }
        assert_eq!(pair[0], pair[1]);
    }
    // Only the selected event's bound is nonzero. With the same seed, another
    // event must retain the cheapest route, while this one can choose a detour.
    for noisy_cause in [0, 1, 2] {
        let mut changed = false;
        for seed in 0..8 {
            let mut choices = Vec::new();
            for event in [noisy_cause, (noisy_cause + 1) % 3] {
                let (mut battle, references) = fixture(0, true);
                battle.rng = Some(clash_engine::pyrandom::PyRandom::new(seed));
                battle.params.extra_target_path_cost_penalty = 0.0;
                battle.params.force_new_target_default_max_noise = 0.0;
                battle.params.force_new_target_jump_max_noise = 0.0;
                battle.params.force_new_target_tesla_max_noise = 0.0;
                match noisy_cause {
                    0 => battle.params.force_new_target_default_max_noise = 100_000.0,
                    1 => battle.params.force_new_target_jump_max_noise = 100_000.0,
                    _ => battle.params.force_new_target_tesla_max_noise = 100_000.0,
                }
                let cause = match event {
                    0 => ForcedRetarget::Default,
                    1 => ForcedRetarget::Jump,
                    _ => ForcedRetarget::Tesla,
                };
                battle.force_retarget(references[0], cause);
                choices.push(battle.choose_target(references[0]).0);
            }
            changed |= choices[0] != choices[1];
        }
        assert!(changed, "event {noisy_cause} must use its own noise bound");
    }
}

#[test]
fn spatial_group_wait_is_optional_and_does_not_attack_during_wait() {
    let (mut battle, references) = fixture(1, true);
    let warden = references[0];
    for &ally in &references[1..] {
        battle.unit_mut(ally).target = None;
    }
    let position = (battle.unit(warden).x, battle.unit(warden).y);
    assert_eq!(battle.spatial_follow_target(warden), (None, true));
    battle.act_attacker(warden);
    assert_eq!(battle.unit(warden).target, None);
    assert_eq!((battle.unit(warden).x, battle.unit(warden).y), position);
    battle.params.warden_waits_for_group_retargeting = false;
    battle.act_attacker(warden);
    assert!(battle.unit(warden).target.is_some());
}

#[test]
fn defender_separation_and_ground_push_are_independent_controls() {
    for enabled in [false, true] {
        let (mut battle, references) = fixture(2, enabled);
        let a = references[1];
        let b = references[2];
        battle.separate();
        let separated =
            battle.unit(a).x != battle.unit(b).x || battle.unit(a).y != battle.unit(b).y;
        assert_eq!(separated, enabled);
        if enabled {
            battle.unit_mut(a).x = 20.0;
            battle.unit_mut(a).y = 20.0;
            battle.unit_mut(b).x = 20.0;
            battle.unit_mut(b).y = 20.0;
            battle.params.separation_push = 0.0;
            battle.separate();
            assert_eq!(battle.unit(a).x, battle.unit(b).x);
            assert_eq!(battle.unit(a).y, battle.unit(b).y);
        }
    }
}

#[test]
fn hidden_tesla_is_excluded_from_plan_and_navigation_until_reveal() {
    let (mut battle, references) = fixture(3, true);
    let tesla = BuildingId(1);
    let b = battle.building(tesla);
    let (x, y) = (b.x, b.y);
    let (i, j) = battle.grid.cell(x, y);
    let cell = battle.grid.index(i, j);
    assert!(!battle.grid.blocked[cell]);
    assert!(!battle.visible_buildings().any(|b| b.id == tesla));
    assert!(plans::threats_near(&battle, x, y, 50.0).is_empty());
    assert!(!battle.attacker_knows_trap(&battle.traps[0]));
    let _ = battle.choose_target(references[0]);
    let version = battle.grid.version;
    defense::reveal_tesla(&mut battle, tesla);
    assert!(battle.grid.version > version);
    assert!(battle.grid.blocked[cell]);
    assert!(battle.visible_buildings().any(|b| b.id == tesla));
    assert!(plans::threats_near(&battle, x, y, 50.0)
        .iter()
        .any(|(id, _)| *id == tesla));
    battle.traps[0].fuse_at = battle.t + 0.5;
    assert!(battle.attacker_knows_trap(&battle.traps[0]));
}

#[test]
fn override_precedence_is_explicit() {
    let env =
        json::parse(r#"{"pace_switch":0.6,"params":{"wall_cost":11,"pace_switch":0.7}}"#).unwrap();
    let job = json::parse(
        r#"{"env":{"pace_switch":0.8,"params":{"wall_cost":9}},"params":{"wall_cost":7}}"#,
    )
    .unwrap();
    let params = Params::resolve(&catalog(), &env, &job).unwrap();
    assert_eq!(params.wall_cost, 7.0);
    assert_eq!(params.pace_switch, 0.8);
}

#[test]
fn process_file_overrides_are_read_without_global_mutation() {
    let path = std::env::temp_dir().join(format!("rm1-params-{}.json", std::process::id()));
    std::fs::write(&path, r#"{"ground_radius":0.6,"target_list":true}"#).unwrap();
    let output = std::process::Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "process_file_override_child"])
        .env("BASELAB_PARAMS_FILE", &path)
        .env("RM1_PARAMS_CHILD", "1")
        .output()
        .unwrap();
    std::fs::remove_file(path).unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
}

#[test]
fn process_file_override_child() {
    if std::env::var("RM1_PARAMS_CHILD").as_deref() != Ok("1") {
        return;
    }
    let (battle, _) = fixture(0, false);
    assert_eq!(battle.params.ground_radius, 0.6);
    assert!(
        !battle.params.target_list,
        "job env takes precedence over process file"
    );
}

#[test]
fn spatial_scales_match_character_and_hero_rows() {
    let catalog = catalog();
    let params = Params::default();
    let apprentice = catalog.game_unit_data("Apprentice Warden", None);
    let warden = catalog.game_unit_data("Grand Warden", None);
    for row in [apprentice, warden] {
        assert_eq!(
            clash_engine::catalog::game_int(row, "TargetGroupsRadius", 0) as f64,
            params.target_groups_radius
        );
        assert_eq!(
            clash_engine::catalog::game_int(row, "TargetGroupsRange", 0) as f64
                / params.internal_units_per_tile,
            13.0
        );
    }
    assert_eq!(
        clash_engine::catalog::game_int(apprentice, "TargetGroupsMinWeight", 0) as f64,
        params.apprentice_target_groups_min_weight
    );
    assert_eq!(
        clash_engine::catalog::game_int(warden, "TargetGroupsMinWeight", 0) as f64,
        params.target_groups_min_weight
    );
}
