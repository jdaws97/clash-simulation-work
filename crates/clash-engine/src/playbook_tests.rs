use super::*;
use crate::battle::SpawnOptions;
use crate::plan_wire::{array, put, string};
use crate::test_support::{battle, json};

fn plan(steps: &str, inventory: &str) -> PlaybookPlan {
    // Prepared by the accepted compiler before the workspace split. Compiler
    // tests separately verify these synthetic inputs against their frozen plans.
    let steps = json(steps);
    let inventory = json(inventory);
    let fixture = include_str!("../../../fixtures/playbooks/executor.jsonl")
        .lines()
        .map(json)
        .find(|fixture| fixture.at("steps") == &steps && fixture.at("inventory") == &inventory)
        .expect("declared synthetic executor fixture");
    PlaybookPlan::load(fixture.at("prepared"))
}

#[test]
fn spell_preparation_protects_transitive_deployments_and_has_a_deadline() {
    let mut plan = plan(
        r#"[
        {"id":"quake","action":"spell","what":"Freeze Spell","when":{"t":8},"timeout":20},
        {"id":"duke","action":"deploy","what":"Dragon Duke","when":{"after":"quake","delay":2}},
        {"id":"main","action":"deploy","what":"Dragon","count":"all","when":{"after":"duke"}}
    ]"#,
        r#"{"Dragon":1}"#,
    );
    let mut battle = battle();
    battle.t = 3.1;
    let main = Trigger::After("duke".to_owned(), 0.0);
    assert!(plan.preparing(&battle, &main, &mut Vec::new()));
    plan.on_tick(&mut battle);
    assert!(!plan.done("duke"));
    assert!(!plan.done("main"));
    battle.t = 20.0;
    assert!(!plan.preparing(&battle, &main, &mut Vec::new()));
    battle.t = 4.0;
    plan.cancelled.push("quake".to_owned());
    assert!(!plan.preparing(&battle, &main, &mut Vec::new()));
}

#[test]
fn pressure_without_a_possible_opening_unit_does_not_block_recovery() {
    let plan = plan(
        r#"[
        {"id":"freeze","action":"spell","what":"Freeze Spell","when":{"heavy_fire":"Dragon Duke"}},
        {"id":"duke","action":"deploy","what":"Dragon Duke","when":{"after":"freeze"}}
    ]"#,
        r#"{"Dragon":1}"#,
    );
    assert!(!plan.preparing(
        &battle(),
        &Trigger::After("freeze".to_owned(), 0.0),
        &mut Vec::new()
    ));
}

#[test]
fn firemite_absence_is_temporary_while_a_producer_can_spawn() {
    let mut plan = plan(
        r#"[
        {"id":"furnace","action":"deploy","what":"Furnace","count":"all","when":{"t":0}},
        {"id":"clone","action":"spell","what":"Clone Spell","at":"unit:Firemite","when":{"inside":"Firemite"}}
    ]"#,
        r#"{"Furnace":1}"#,
    );
    let mut battle = battle();
    let furnace = battle.spawn("Furnace", Team::Atk, 20.0, 20.0, SpawnOptions::default());
    plan.inventory.clear();
    plan.done.push(("furnace".to_owned(), 0.0));
    plan.deployed.push("Firemite".to_owned());
    plan.entered.push("Firemite".to_owned());
    let step = plan
        .steps
        .iter()
        .find(|step| step.id == "clone")
        .unwrap()
        .clone();
    assert!(plan.generated_possible(&battle, "Firemite"));
    assert!(!plan.down(&battle, "Firemite"));
    assert!(plan.cannot(&battle, &step).is_none());
    plan.on_tick(&mut battle);
    assert!(!plan.cancelled("clone"));
    battle.t = 0.7;
    battle.spawn("Firemite", Team::Atk, 20.5, 20.5, SpawnOptions::default());
    plan.on_tick(&mut battle);
    assert!(plan.done("clone"));
    assert_eq!(count(&plan.attack.spells, "clone"), 0);
    battle.unit_mut(furnace).alive = false;
    let mites = battle
        .attackers_pool()
        .filter(|unit| unit.name_id == Name::Firemite)
        .map(Unit::reference)
        .collect::<Vec<_>>();
    for mite in mites {
        battle.unit_mut(mite).alive = false;
    }
    assert!(plan.down(&battle, "Firemite"));
    assert_eq!(
        plan.cannot(&battle, &step).as_deref(),
        Some("Firemite down")
    );
}

#[test]
fn troop_reservations_leave_surplus_and_release_terminal_steps() {
    let mut plan = plan(
        r#"[
        {"id":"front","action":"deploy","what":"Super Wall Breaker","count":1,"when":{"t":10}},
        {"id":"hero","action":"deploy","what":"Super Wall Breaker","count":1,"when":{"t":20}}
    ]"#,
        r#"{"Super Wall Breaker":3}"#,
    );
    // fit_steps adds an all-count completion for the genuine remainder.
    plan.steps = Rc::new(
        plan.steps
            .iter()
            .filter(|step| !step.uncited)
            .cloned()
            .collect(),
    );
    assert_eq!(count(&plan.unreserved_inventory(), "Super Wall Breaker"), 1);
    plan.cancelled.push("hero".to_owned());
    assert_eq!(count(&plan.unreserved_inventory(), "Super Wall Breaker"), 2);
    plan.done.push(("front".to_owned(), 10.0));
    set(&mut plan.inventory, "Super Wall Breaker".to_owned(), 2);
    assert_eq!(count(&plan.unreserved_inventory(), "Super Wall Breaker"), 2);
    let mut all = plan.steps[0].clone();
    all.id = "all".to_owned();
    all.count = None;
    plan.steps = Rc::new(vec![all]);
    assert_eq!(count(&plan.unreserved_inventory(), "Super Wall Breaker"), 0);
}

#[test]
fn explicit_air_defense_aim_uses_numeric_and_cited_counts() {
    let mut source = json(
        r#"{"id":"arrow","action":"ability","what":"Archer Queen","aim":"building:ad","equipment":"Giant Arrow","cite":[{"quote":"take two air defenses"}]}"#,
    );
    assert_eq!(PlaybookPlan::ad_target_count(&Step::load(&source)), 2);
    put(&mut source, "aim_count", Json::Num(3.0));
    assert_eq!(PlaybookPlan::ad_target_count(&Step::load(&source)), 3);
    put(&mut source, "cite", array([]));
    assert_eq!(PlaybookPlan::ad_target_count(&Step::load(&source)), 3);
}

#[test]
fn optional_support_preserves_stock_committed_to_mandatory_casts() {
    let mut plan = plan(
        r#"[
        {"id":"optional","action":"spell","what":"Freeze Spell","optional":true,"when":{"t":0}},
        {"id":"mandatory","action":"spell","what":"Freeze Spell","when":{"t":10}}
    ]"#,
        r#"{"Dragon":1}"#,
    );
    let step = plan
        .steps
        .iter()
        .find(|step| step.id == "optional")
        .unwrap()
        .clone();
    assert!(!plan.opportunity_has_stock(&step));
    plan.cancelled.push("mandatory".to_owned());
    assert!(plan.opportunity_has_stock(&step));
}

#[test]
fn impossible_multi_air_defense_geometry_keeps_the_aim_deadline() {
    let mut plan = plan(
        r#"[{"id":"duke","action":"deploy","what":"Dragon Duke","when":{"t":0}}]"#,
        r#"{"Dragon":1}"#,
    );
    let mut battle = battle();
    let hero = battle.spawn(
        "Archer Queen",
        Team::Atk,
        10.0,
        10.0,
        SpawnOptions {
            kind: Tag::Hero,
            ..Default::default()
        },
    );
    crate::heroes::equip(&mut battle, hero);
    let step = Step::load(&json(
        r#"{"id":"arrow","action":"ability","what":"Archer Queen","equipment":"Giant Arrow","aim":"building:ad","aim_count":2}"#,
    ));
    assert!(!plan.ability(&mut battle, &step));
    battle.t = battle.params.aim_wait;
    assert!(plan.ability(&mut battle, &step));
    assert!(battle.unit(hero).ability_used);
}

#[test]
fn primary_milestone_excludes_tanks_flanks_and_same_named_reserves() {
    let mut p = plan(
        r#"[
        {"id":"tank","action":"deploy","what":"Ice Golem","group":"main","when":{"t":0}},
        {"id":"flank","action":"deploy","what":"Dragon","count":1,"group":"funnel","when":{"t":0}},
        {"id":"bulk","action":"deploy","what":"Dragon","primary":true,"group":"main","when":{"t":20}}
    ]"#,
        r#"{"Dragon":3,"Ice Golem":1}"#,
    );
    let mut b = battle();
    let tank = b.spawn("Ice Golem", Team::Atk, 20.0, 20.0, SpawnOptions::default());
    b.unit_mut(tank).group = "main".to_owned();
    let flank = b.spawn("Dragon", Team::Atk, 20.0, 20.0, SpawnOptions::default());
    b.unit_mut(flank).group = "funnel".to_owned();
    p.done.push(("tank".to_owned(), 0.0));
    p.done.push(("flank".to_owned(), 0.0));
    assert!(!p.main_started(&b));
    assert!(p.group_units(&b, "main").is_empty());
    p.done.push(("bulk".to_owned(), 20.0));
    b.t = 20.0;
    let bulk = b.spawn("Dragon", Team::Atk, 21.0, 21.0, SpawnOptions::default());
    b.unit_mut(bulk).group = "main".to_owned();
    assert!(p.main_started(&b));
    assert_eq!(p.group_units(&b, "main"), vec![bulk]);
}

#[test]
fn named_return_fails_without_borrowing_another_hero_stash() {
    let mut p = plan(
        r#"[{"id":"recall","action":"recall","what":"Dragon Duke","at":"unit:Dragon Duke","when":{"t":0}},{"id":"return","action":"redeploy","what":"Dragon Duke","recall_from":"recall","when":{"after":"recall"}}]"#,
        r#"{}"#,
    );
    let mut b = battle();
    p.deployed.push("Dragon Duke".into());
    p.cancelled.push("recall".into());
    let other = b.spawn(
        "Archer Queen",
        Team::Atk,
        20.0,
        20.0,
        SpawnOptions::default(),
    );
    heroes::stash(&mut b, vec![other], (0.0, 0.0, 0.0));
    let step = Step::load(&json(
        r#"{"id":"return","action":"redeploy","what":"Dragon Duke","recall_from":"recall"}"#,
    ));
    assert!(p
        .cannot(&b, &step)
        .unwrap()
        .contains("named return unavailable"));
    assert_eq!(b.portal_units().count(), 1);
}

#[test]
fn effect_prerequisites_use_recorded_expiry_and_do_not_refresh_on_poll() {
    let mut p = plan(
        r#"[{"id":"bulk","action":"deploy","what":"Dragon","when":{"t":0}}]"#,
        r#"{"Dragon":1}"#,
    );
    let mut b = battle();
    p.effect_ends.push(("mask".into(), 4.0));
    b.t = 3.9;
    assert!(p.ready(&mut b, &Trigger::EffectActive("mask".into()), false));
    b.t = 4.0;
    assert!(!p.ready(&mut b, &Trigger::EffectActive("mask".into()), false));
    assert!(p.ready(&mut b, &Trigger::EffectExpired("mask".into()), false));
}

#[test]
fn objective_identity_and_real_effect_windows_survive_target_changes() {
    let mut p = plan(
        r#"[{"id":"bulk","action":"deploy","what":"Dragon","when":{"t":0}}]"#,
        r#"{"Dragon":1}"#,
    );
    let mut b = battle();
    let step = Step::load(&json(
        r#"{"id":"quake","action":"spell","what":"Freeze Spell","objective":"core","at":"building:gs"}"#,
    ));
    let first = p.objective_point(&mut b, &step, &step.at).unwrap();
    let target = p.objectives[0].1;
    let mut replacement = b.building(target).clone();
    replacement.id = BuildingId(b.buildings.len());
    replacement.x = 35.0;
    replacement.y = 35.0;
    b.buildings.push(replacement);
    b.building_mut(target).alive = false;
    assert_eq!(p.objective_point(&mut b, &step, &step.at), Some(first));
    assert_eq!(p.objectives[0].1, target);
    assert!(p.ready(
        &mut b,
        &Trigger::ObjectiveState("core".into(), "destroyed".into()),
        false
    ));
    assert!(p.spell(&mut b, &step, first));
    let end = p
        .effect_ends
        .iter()
        .find(|(id, _)| id == "quake")
        .unwrap()
        .1;
    assert_eq!(end, b.fields.last().unwrap().until);
}

#[test]
fn recalled_opening_hero_closes_charge_support_even_with_live_allies() {
    let mut p = plan(
        r#"[{"id":"hero","action":"deploy","what":"Dragon Duke","group":"charge","when":{"t":0}}]"#,
        r#"{}"#,
    );
    let mut b = battle();
    let hero = b.spawn(
        "Dragon Duke",
        Team::Atk,
        20.0,
        20.0,
        SpawnOptions::default(),
    );
    p.deployed.push("Dragon Duke".into());
    p.done.push(("hero".into(), 0.0));
    heroes::stash(&mut b, vec![hero], (0.0, 0.0, 0.0));
    p.on_tick(&mut b);
    assert!(p.charge_closed);
    let support = Step::load(&json(
        r#"{"id":"rage","action":"spell","what":"Rage Spell","group":"charge","at":"unit:Healer"}"#,
    ));
    assert_eq!(p.cannot(&b, &support).as_deref(), Some("charge closed"));
}

#[test]
fn one_shot_dispatch_records_the_lasting_block_and_overgrowth_status() {
    let mut p = plan(
        r#"[{"id":"bulk","action":"deploy","what":"Dragon","when":{"t":0}}]"#,
        r#"{"Dragon":1}"#,
    );
    let mut b = battle();
    b.t = 1.2;
    let hero = b.spawn(
        "Dragon Duke",
        Team::Atk,
        20.0,
        20.0,
        SpawnOptions::default(),
    );
    for (id, name, key) in [
        ("block", "Ice Block Spell", "iceblock"),
        ("growth", "Overgrowth Spell", "overgrowth"),
    ] {
        p.attack.spells.push((key.into(), 1));
        p.attack.stock.push(plans::SpellStock {
            name: name.into(),
            origin: "brewed".into(),
            remaining: 1,
            level: Some(Level::Int(b.catalog.stats.max_level(name, 18).unwrap())),
        });
        let step = Step::load(&Json::Obj(vec![
            ("id".into(), string(id)),
            ("action".into(), string("spell")),
            ("what".into(), string(name)),
        ]));
        assert!(p.spell(&mut b, &step, (20.0, 20.0)));
    }
    let block = p
        .effect_ends
        .iter()
        .find(|(id, _)| id == "block")
        .unwrap()
        .1;
    let growth = p
        .effect_ends
        .iter()
        .find(|(id, _)| id == "growth")
        .unwrap()
        .1;
    assert!(block > b.t);
    assert!(growth > b.t);
    assert!(!p.ready(&mut b, &Trigger::EffectActive("block".into()), false));
    b.t = p
        .effect_starts
        .iter()
        .find(|(id, _)| id == "block")
        .unwrap()
        .1;
    b.rebuild_buckets();
    crate::spells::tick(&mut b);
    assert_eq!(b.unit(hero).frozen_until, block);
    assert_eq!(b.building(BuildingId(0)).overgrown_until, growth);
}

#[test]
fn per_target_packets_do_not_take_another_cited_deployments_stock() {
    let mut p = plan(
        r#"[
        {"id":"packet","action":"deploy","what":"Rocket Balloon","count":2,"per_target":true,"group":"charge","when":{"t":0}},
        {"id":"reserved","action":"deploy","what":"Rocket Balloon","count":3,"group":"reserve","when":{"t":30}}
    ]"#,
        r#"{"Rocket Balloon":5}"#,
    );
    let mut b = battle();
    let step = p.steps.iter().find(|s| s.id == "packet").unwrap().clone();
    assert!(p.deploy(&mut b, &step, (10.0, 10.0)));
    p.done.push(("packet".into(), b.t));
    assert_eq!(count(&p.inventory, "Rocket Balloon"), 3);
    assert!(!p.deploy(&mut b, &step, (10.0, 10.0)));
    assert_eq!(count(&p.inventory, "Rocket Balloon"), 3);
}

#[test]
fn unrelated_revive_stock_does_not_hold_a_failed_named_return() {
    let mut p = plan(
        r#"[{"id":"hero","action":"deploy","what":"Dragon Duke","group":"charge","when":{"t":0}}]"#,
        r#"{}"#,
    );
    let mut b = battle();
    let hero = b.spawn(
        "Dragon Duke",
        Team::Atk,
        20.0,
        20.0,
        SpawnOptions {
            kind: Tag::Hero,
            ..Default::default()
        },
    );
    b.unit_mut(hero).alive = false;
    b.unit_mut(hero).extra.revivable = true;
    p.deployed.push("Dragon Duke".into());
    p.attack.spells.push(("revive".into(), 1));
    assert!(p.recoverable(&b, "Dragon Duke"));
    let recall = Step::load(&json(
        r#"{"id":"recall","action":"recall","what":"Dragon Duke","at":"unit:Dragon Duke"}"#,
    ));
    assert_eq!(
        p.cannot(&b, &recall).as_deref(),
        Some("Recall opening hero lost")
    );
    let returned = Step::load(&json(
        r#"{"id":"return","action":"redeploy","what":"Dragon Duke","recall_from":"recall","at":"edge:main"}"#,
    ));
    assert!(p
        .cannot(&b, &returned)
        .unwrap()
        .contains("named return unavailable"));
}

#[test]
fn offensive_masks_select_distinct_buildings_without_hiding_the_goal() {
    let mut p = plan(
        r#"[{"id":"bulk","action":"deploy","what":"Dragon","when":{"t":0}}]"#,
        r#"{"Dragon":1}"#,
    );
    let mut b = crate::setup::build(
        &json(r#"{"buildings":[{"key":"gs","x":20,"y":20},{"key":"gs","x":8,"y":8},{"key":"gs","x":14,"y":8}],"walls":[],"traps":[],"heroes":[],"cc_troops":[],"levels":{"gs":1}}"#),
        &json(r#"{"$type":"Stage","drops":[],"ticks":[],"town_hall":18,"strength":1,"loadouts":{},"revives_left":0}"#),
        &json(r#"{"seed":2,"town_hall":18,"record":true}"#),
        crate::test_support::catalog(),
    ).unwrap();
    for building in &mut b.buildings {
        building.is_defense = true;
    }
    let first_point = (b.building(BuildingId(1)).x, b.building(BuildingId(1)).y);
    let second_point = (b.building(BuildingId(2)).x, b.building(BuildingId(2)).y);
    p.objectives.push(("core".into(), BuildingId(0)));
    b.spawn("Dragon Duke", Team::Atk, 3.0, 8.0, SpawnOptions::default());
    let first = Step::load(&json(
        r#"{"id":"mask1","action":"spell","what":"Invisibility Spell","objective":"mask1","mask_for":"core","mask_hero":"Dragon Duke","at":"threat:main"}"#,
    ));
    let second = Step::load(&json(
        r#"{"id":"mask2","action":"spell","what":"Invisibility Spell","objective":"mask2","mask_for":"core","mask_hero":"Dragon Duke","at":"threat:main"}"#,
    ));
    let point = p.objective_point(&mut b, &first, &first.at).unwrap();
    assert_eq!(point, first_point);
    let mut pending = Field::new("invis", point.0, point.1, 4.0, 10.0);
    pending.started = 2.0;
    b.fields.push(pending);
    assert_eq!(
        p.objective_point(&mut b, &second, &second.at),
        Some(second_point)
    );
    assert_eq!(p.objective_point(&mut b, &first, &first.at), Some(point));
    assert!(p
        .objectives
        .iter()
        .filter(|(name, _)| name.starts_with("mask"))
        .all(|(_, id)| *id != BuildingId(0)));
}
