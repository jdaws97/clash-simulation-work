use super::*;
use crate::armies::{array, put, string};
use crate::battle::SpawnOptions;
use crate::test_support::{battle, json, with_compiler};

fn plan(steps: &str, inventory: &str) -> PlaybookPlan {
    with_compiler(|mut compiler| {
        let mut book = json(r#"{"family":"synthetic","steps":[]}"#);
        put(&mut book, "steps", json(steps));
        compiler.playbooks = vec![("dragon".to_owned(), book)];
        let mut build = json(
            r#"{"th":18,"archetype":"mass-dragons","build":1,"troops":{},"spells":{"Clone Spell":1,"Freeze Spell":1},"cc":{},"heroes":["Dragon Duke"],"snipe_mode":"off","snipe_exposed":false}"#,
        );
        put(&mut build, "troops", json(inventory));
        let mut source = compiler
            .compile(&build, 0.0, 2, &Default::default())
            .unwrap();
        put(&mut source, "snipe_mode", string("off"));
        put(&mut source, "snipe_exposed", Json::Bool(false));
        PlaybookPlan::load(&source)
    })
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
