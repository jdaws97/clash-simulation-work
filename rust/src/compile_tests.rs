use super::*;
use crate::test_support::{json, with_compiler};

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
