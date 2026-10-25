use super::*;
use crate::test_support::{json, with_compiler};

#[test]
fn frozen_synthetic_executor_inputs_compile_identically() {
    with_compiler(|mut compiler| {
        for line in include_str!("../../../fixtures/playbooks/executor.jsonl").lines() {
            let fixture = json(line);
            assert_eq!(fixture.at("synthetic"), &Json::Bool(true));
            compiler.playbooks = vec![("dragon".to_owned(), fixture.at("book").clone())];
            let mut prepared = compiler
                .compile(fixture.at("build"), 0.0, 2, &Default::default())
                .unwrap();
            put(&mut prepared, "snipe_mode", string("off"));
            put(&mut prepared, "snipe_exposed", Json::Bool(false));
            assert_eq!(&prepared, fixture.at("prepared"));
        }
    });
}

#[test]
fn unavailable_equipment_is_removed_and_nested_dependents_keep_delays() {
    with_compiler(|compiler| {
        let build = json(
            r#"{"th":18,"archetype":"mass-dragons","build":1,"troops":{"Dragon":1},"spells":{},"cc":{},"heroes":["Archer Queen"],"loadouts":{"Archer Queen":["Magic Mirror","Healer Puppet"]}}"#,
        );
        let book = json(
            r#"{"family":"synthetic","steps":[
            {"id":"queen","action":"deploy","what":"Archer Queen","count":1,"when":{"t":2}},
            {"id":"shot","action":"ability","what":"Archer Queen","equipment":"Giant Arrow","when":{"after":"queen","delay":3}},
            {"id":"dragons","action":"deploy","what":"Dragon","count":"all","when":{"all":[{"after":"shot","delay":4},{"t":1}]}}
        ]}"#,
        );
        let base = armies::compose(&compiler.library, compiler.stats, &build, 0.0, 2).unwrap();
        let plan = compiler
            .from_playbook(&book, &build, base.clone(), 2, &CompileOptions::default())
            .unwrap();
        let steps = list(&plan, "steps");
        assert!(!steps.iter().any(|step| text(step, "id", "") == "shot"));
        let dragons = steps
            .iter()
            .find(|step| text(step, "id", "") == "dragons")
            .unwrap();
        assert_eq!(dragons.at("when").at("all").arr()[0], after("queen", 7.0));
        assert_eq!(
            plan.at("unavailable_steps").arr()[0].at("id"),
            &string("shot")
        );
        let mut required = book.clone();
        let mut steps = list(&required, "steps").to_vec();
        put(&mut steps[1], "required", Json::Bool(true));
        put(&mut required, "steps", array(steps));
        assert!(compiler
            .from_playbook(&required, &build, base, 2, &CompileOptions::default())
            .unwrap_err()
            .contains("Required ability shot"));
    });
}

#[test]
fn shared_and_optional_spells_do_not_waive_mandatory_combinations() {
    with_compiler(|compiler| {
        let mut steps = json(r#"[
            {"id":"first","action":"spell","what":"Freeze Spell","count":1,"when":{"heavy_fire":"Dragon"}},
            {"id":"second","action":"spell","what":"Freeze Spell","count":1,"when":{"heavy_fire":"Dragon"}}
        ]"#).arr().to_vec();
        let inventory = object();
        let spells = json(r#"{"freeze":1}"#);
        let added = vec!["first".to_owned(), "second".to_owned()];
        let feasible = |steps: &[Json], stock: &Json| {
            compiler
                .feasible(steps, &added, &inventory, &[], stock, &object(), true)
                .unwrap()
        };
        assert!(
            !feasible(&steps, &spells),
            "pressure alone cannot share a mandatory budget"
        );
        for step in &mut steps {
            put(step, "spell_budget", string("frost"));
        }
        assert!(feasible(&steps, &spells));
        let mut third = steps[0].clone();
        put(&mut third, "id", string("mandatory"));
        remove(&mut third, "spell_budget");
        steps.push(third);
        assert!(!feasible(&steps, &spells));
        assert!(feasible(&steps, &json(r#"{"freeze":2}"#)));
        for step in &mut steps {
            put(step, "optional", Json::Bool(true));
        }
        assert!(
            feasible(&steps, &object()),
            "absent discretionary support cannot veto a recipe"
        );
    });
}

#[test]
fn inherited_deployments_clip_and_zero_all_steps_relink() {
    with_compiler(|compiler| {
        let source = json(
            r#"[
            {"id":"balloons","action":"deploy","what":"Balloon","count":2,"when":{"t":0}},
            {"id":"cleanup","action":"deploy","what":"Balloon","count":"all","when":{"after":"balloons","delay":2}},
            {"id":"new","action":"deploy","what":"Wizard","count":1,"when":{"after":"cleanup","delay":3}}
        ]"#,
        );
        let inventory = json(r#"{"Balloon":1,"Wizard":1}"#);
        assert!(compiler
            .feasible(
                source.arr(),
                &["new".to_owned()],
                &inventory,
                &[],
                &object(),
                &object(),
                true
            )
            .unwrap());
        let fitted = fit_steps(source.arr(), &inventory, &[], &object(), &[]).unwrap();
        assert_eq!(fitted[0].at("count"), &Json::Num(1.0));
        assert!(!fitted.iter().any(|step| text(step, "id", "") == "cleanup"));
        assert_eq!(fitted[1].at("when"), &after("balloons", 5.0));
        let mut excessive = source.arr().to_vec();
        put(&mut excessive[2], "count", Json::Num(2.0));
        assert!(!compiler
            .feasible(
                &excessive,
                &["new".to_owned()],
                &inventory,
                &[],
                &object(),
                &object(),
                true
            )
            .unwrap());
        put(&mut excessive[2], "optional", Json::Bool(true));
        assert!(
            !compiler
                .feasible(
                    &excessive,
                    &["new".to_owned()],
                    &inventory,
                    &[],
                    &object(),
                    &object(),
                    true
                )
                .unwrap(),
            "spell optionality cannot waive a troop packet"
        );
        let packets = (0..6)
            .map(|index| {
                json(&format!(
                    r#"{{"id":"packet-{index}","action":"deploy","what":"Balloon","count":7}}"#
                ))
            })
            .collect::<Vec<_>>();
        let ids = packets
            .iter()
            .map(|step| text(step, "id", "").to_owned())
            .collect::<Vec<_>>();
        assert!(!compiler
            .feasible(
                &packets,
                &ids,
                &json(r#"{"Balloon":38}"#),
                &[],
                &object(),
                &object(),
                true
            )
            .unwrap());
    });
}

#[test]
fn dependencies_reject_missing_duplicate_and_nested_cycles() {
    for (source, message) in [
        (r#"[{}]"#, "empty or missing id"),
        (r#"[{"id":"a"},{"id":"a"}]"#, "Duplicate"),
        (
            r#"[{"id":"a","when":{"any":[{"t":150},{"after":"missing"}]}}]"#,
            "unknown predecessor missing",
        ),
        (
            r#"[{"id":"a","until":{"all":[{"after":"b"}]}},{"id":"b","when":{"after":"a"}}]"#,
            "Cyclic",
        ),
        (
            r#"[{"id":"warden_invisibility","when":{"after":"ice_block"}}]"#,
            "unknown predecessor ice_block",
        ),
    ] {
        assert!(validate_dependencies(json(source).arr())
            .unwrap_err()
            .contains(message));
    }
}

#[test]
fn fitting_cannot_conceal_a_duplicate_siege_commitment() {
    with_compiler(|compiler| {
        for reverse in [false, true] {
            let mut steps = json(
                r#"[
                {"id":"new","action":"deploy","what":"Log Launcher","count":1},
                {"id":"inherited","action":"deploy","what":"Log Launcher","count":1}
            ]"#,
            )
            .arr()
            .to_vec();
            if reverse {
                steps.reverse();
            }
            assert!(!compiler
                .feasible(
                    &steps,
                    &["new".to_owned()],
                    &json(r#"{"Log Launcher":1}"#),
                    &[],
                    &object(),
                    &object(),
                    true
                )
                .unwrap());
        }
    });
}

#[test]
fn relinking_compound_predecessors_preserves_temporal_delays() {
    let source = json(
        r#"[
        {"id":"missing","action":"deploy","what":"Balloon","when":{"any":[{"t":2},{"t":4}]}},
        {"id":"kept","action":"deploy","what":"Wizard","when":{"after":"missing","delay":3}}
    ]"#,
    );
    let fitted = fit_steps(source.arr(), &json(r#"{"Wizard":1}"#), &[], &object(), &[]).unwrap();
    assert_eq!(fitted[0].at("when"), &json(r#"{"any":[{"t":5},{"t":7}]}"#));
}

#[test]
fn expansion_rewires_known_removed_predecessors_before_fitting() {
    with_compiler(|compiler| {
        let book = json(
            r#"{"steps":[
            {"id":"old","action":"deploy","what":"Balloon","count":1,"when":{"t":2}},
            {"id":"child","action":"deploy","what":"Wizard","count":1,"when":{"any":[{"after":"old","delay":3},{"t":150}]},"until":{"after":"old","delay":8}}
        ],"variants":[{"name":"replace","replaces":["old"],"steps":[
            {"id":"new","action":"deploy","what":"Balloon","count":1,"when":{"t":4}}
        ]}]}"#,
        );
        let steps = compiler
            .pick_variants(
                &book,
                &json(r#"{"Balloon":1,"Wizard":1}"#),
                &[],
                &object(),
                &object(),
                Some(&array([string("replace")])),
            )
            .unwrap();
        let child = steps
            .iter()
            .find(|step| text(step, "id", "") == "child")
            .unwrap();
        assert_eq!(child.at("when"), &json(r#"{"any":[{"t":5},{"t":150}]}"#));
        assert_eq!(child.at("until"), &time(10.0));
        validate_dependencies(&steps).unwrap();
    });
}

#[test]
fn declared_recipe_selects_additive_branch_and_enforces_all_loadout_items() {
    with_compiler(|compiler| {
        let mut build = json(
            r#"{"th":18,"archetype":"mass-dragons","build":1,"troops":{"Dragon":1},"spells":{},"cc":{},"heroes":["Dragon Duke"],"loadouts":{"Dragon Duke":["Rocket Backpack","Fire Heart"]},"recipe":"flame"}"#,
        );
        let book = json(
            r#"{"family":"synthetic","recipes":{"flame":["Flame"]},"steps":[{"id":"dragons","action":"deploy","what":"Dragon","count":"all","when":{"t":0}}],"variants":[{"name":"Flame","required_loadouts":{"Dragon Duke":["Flame Blower","Rocket Backpack"]},"steps":[{"id":"duke","action":"deploy","what":"Dragon Duke","when":{"t":0}}]}]}"#,
        );
        let base = armies::compose(&compiler.library, compiler.stats, &build, 0.0, 2).unwrap();
        assert!(compiler
            .from_playbook(&book, &build, base, 2, &Default::default())
            .unwrap_err()
            .contains("required loadout"));
        put(
            &mut build,
            "loadouts",
            json(r#"{"Dragon Duke":["Rocket Backpack","Flame Blower"]}"#),
        );
        let base = armies::compose(&compiler.library, compiler.stats, &build, 0.0, 2).unwrap();
        let plan = compiler
            .from_playbook(&book, &build, base, 2, &Default::default())
            .unwrap();
        assert!(list(&plan, "steps")
            .iter()
            .any(|s| text(s, "variant", "") == "Flame"));
    });
}

#[test]
fn packets_keep_input_pacing_and_explicit_waits_across_roles() {
    let mut steps=json(r#"[
        {"id":"tank","action":"deploy","what":"Ice Golem","group":"tank","packet":"entry","when":{"t":0}},
        {"id":"left","action":"deploy","what":"Super Yeti","group":"left","packet":"entry","when":{"after":"tank","delay":0}},
        {"id":"bulk","action":"deploy","what":"Super Yeti","group":"main","packet":"entry","when":{"after":"left","delay":2}},
        {"id":"later","action":"deploy","what":"Archer Queen","group":"flank","when":{"after":"bulk","delay":0}}
    ]"#).arr().to_vec();
    add_waits(&mut steps, (4.5, 16.6), 1.0);
    assert_eq!(number(steps[1].at("when"), "delay", -1.0), 0.0);
    assert_eq!(number(steps[2].at("when"), "delay", -1.0), 2.0);
    assert!(number(steps[3].at("when"), "delay", 0.0) > 15.0);
}

#[test]
fn cited_roles_and_remainder_order_survive_generic_hints() {
    let mut steps=json(r#"[{"id":"queen","action":"deploy","what":"Archer Queen","at":"edge:charge","group":"charge","when":{"t":0},"cite":[{"quote":"charge"}]}]"#).arr().to_vec();
    let build = json(r#"{"heroes":["Archer Queen"],"push":["Archer Queen"]}"#);
    apply_roles(&mut steps, &build, &object());
    assert_eq!(text(&steps[0], "group", ""), "charge");
    let source = json(
        r#"[{"id":"bulk","action":"deploy","what":"Thrower","count":"all","group":"main","primary":true,"when":{"t":10}}]"#,
    );
    let a = fit_steps(
        source.arr(),
        &json(r#"{"Thrower":3,"Balloon":1,"Super Barbarian":1}"#),
        &[],
        &object(),
        &[],
    )
    .unwrap();
    let b = fit_steps(
        source.arr(),
        &json(r#"{"Super Barbarian":1,"Balloon":1,"Thrower":3}"#),
        &[],
        &object(),
        &[],
    )
    .unwrap();
    assert_eq!(a, b);
    assert!(a
        .iter()
        .filter(|s| flag(s, "uncited"))
        .all(|s| text(s, "group", "") != "main"));
}

#[test]
fn siege_repair_preserves_a_different_id_and_its_cited_dependency() {
    with_compiler(|compiler| {
        let book = json(
            r#"{"steps":[{"id":"backpack","action":"ability","what":"Dragon Duke","when":{"t":3}},{"id":"flinger","action":"deploy","what":"Flame Flinger","when":{"t":0}}],"variants":[{"name":"Launcher","replaces":["flinger"],"steps":[{"id":"launcher","action":"deploy","what":"Troop Launcher","when":{"after":"backpack"}}]}]}"#,
        );
        let result = compiler
            .pick_variants(
                &book,
                &json(r#"{"Troop Launcher":1}"#),
                &[string("Dragon Duke")],
                &object(),
                &json(r#"{"loadouts":{}}"#),
                None,
            )
            .unwrap();
        let siege = result
            .iter()
            .find(|s| text(s, "id", "") == "launcher")
            .unwrap();
        assert_eq!(text(siege.at("when"), "after", ""), "backpack");
        assert!(!result.iter().any(|s| text(s, "id", "") == "flinger"));
    });
}

#[test]
fn missing_recall_keeps_the_opening_hero_and_healers_in_one_package() {
    let source = json(
        r#"[
        {"id":"hero","action":"deploy","what":"Archer Queen","group":"charge","at":"edge:charge","when":{"t":0}},
        {"id":"healers","action":"deploy","what":"Healer","count":"all","group":"charge","at":"edge:charge","when":{"after":"hero"}},
        {"id":"recall","action":"recall","what":"Recall Spell","at":"unit:Archer Queen","when":{"after":"healers"}},
        {"id":"return","action":"redeploy","what":"Archer Queen","when":{"after":"recall"}}
    ]"#,
    );
    let mut steps = fit_steps(
        source.arr(),
        &json(r#"{"Healer":5}"#),
        &[string("Archer Queen")],
        &object(),
        &[],
    )
    .unwrap();
    normalize_recall_package(&mut steps, &object()).unwrap();
    assert!(!steps.iter().any(|s| text(s, "action", "") == "redeploy"));
    for id in ["hero", "healers"] {
        let step = steps.iter().find(|s| text(s, "id", "") == id).unwrap();
        assert_eq!(text(step, "group", ""), "main");
        assert_eq!(text(step, "at", ""), "edge:main");
    }
    validate_dependencies(&steps).unwrap();
}
