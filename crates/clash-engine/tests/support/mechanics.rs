use std::sync::Arc;

use clash_engine::battle::SpawnOptions;
use clash_engine::catalog::Catalog;
use clash_engine::json::{self, Json};
use clash_engine::labels::Tag;
use clash_engine::setup;
use clash_engine::state::{Battle, BuildingId, EntityRef, Team, UnitRef};
use clash_engine::wire::to_json;

pub fn catalog() -> Arc<Catalog> {
    let path = std::env::var_os("BASELAB_CATALOG")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| {
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../rust/data/catalog.json")
        });
    Arc::new(Catalog::load(&path).expect("mechanics proof catalog"))
}

pub fn fixtures() -> Json {
    let fixtures = json::parse(include_str!("../../../../fixtures/mechanics/demos.json"))
        .expect("declared synthetic mechanics fixtures");
    assert_eq!(fixtures.at("synthetic"), &Json::Bool(true));
    fixtures
}

pub fn build(case: &Json, enabled: bool, catalog: Arc<Catalog>) -> (Battle, Vec<UnitRef>) {
    let plan = json::parse(
        r#"{"$type":"Stage","drops":[],"ticks":[],"town_hall":16,
        "strength":1,"loadouts":{},"revives_left":0}"#,
    )
    .unwrap();
    let options = json::parse(&format!(
        r#"{{"town_hall":16,"seed":123,"max_time":90,"record":true,
        "env":{{"params":{{"{}":{enabled}}}}}}}"#,
        case.at("flag").str()
    ))
    .unwrap();
    let mut battle = setup::build(case.at("layout"), &plan, &options, catalog).unwrap();
    let mut references = Vec::new();
    for u in case.at("units").arr() {
        let team = match u.at("team").str() {
            "atk" => Team::Atk,
            "def" => Team::Def,
            _ => panic!("synthetic unit team"),
        };
        let reference = battle.spawn(
            u.at("name").str(),
            team,
            u.at("x").f64(),
            u.at("y").f64(),
            SpawnOptions::default(),
        );
        if let Some(id) = u.get("target") {
            let unit = battle.unit_mut(reference);
            unit.target = Some(EntityRef::Building(BuildingId(id.usize())));
            unit.target_kind = Some(Tag::Building);
        }
        references.push(reference);
    }
    battle.rebuild_buckets();
    (battle, references)
}

pub fn object(entries: Vec<(&str, Json)>) -> Json {
    Json::Obj(
        entries
            .into_iter()
            .map(|(key, value)| (key.to_owned(), value))
            .collect(),
    )
}

fn target(value: Option<EntityRef>) -> Json {
    value.map_or(Json::Null, |value| Json::Str(format!("{value:?}")))
}

pub fn demonstrate(case: &Json, enabled: bool, catalog: Arc<Catalog>) -> Json {
    let (mut battle, references) = build(case, enabled, catalog);
    let observed = references[case.at("observe").usize()];
    let visible_before = battle.visible_buildings().count();
    let hidden_traps_before = battle
        .traps
        .iter()
        .filter(|trap| !battle.attacker_knows_trap(trap))
        .count();
    let mut samples = Vec::new();
    let mut first_damage = Json::Null;
    let mut first_wall_damage = Json::Null;
    let initial_hp: Vec<_> = battle.buildings.iter().map(|b| b.hp).collect();
    let initial_wall_hp: Vec<_> = battle.walls.iter().map(|w| w.hp).collect();
    let mut ticks = 0;
    let mut hash = 0xcbf29ce484222325_u64;
    while battle.t < battle.max_time && !battle.ended {
        battle.step();
        ticks += 1;
        let unit = battle.unit(observed);
        // Include every observed tick, beyond the human-readable path samples.
        let state = format!(
            "{:.6},{:016x},{:016x},{:?},{:?}",
            battle.t,
            unit.x.to_bits(),
            unit.y.to_bits(),
            unit.target,
            unit.wall_target
        );
        for byte in state.bytes() {
            hash = (hash ^ u64::from(byte)).wrapping_mul(0x100000001b3);
        }
        if [1, 10, 30, 50, 100].contains(&ticks) {
            samples.push(object(vec![
                ("time", Json::Num(battle.t)),
                (
                    "position",
                    Json::Arr(vec![Json::Num(unit.x), Json::Num(unit.y)]),
                ),
                ("target", target(unit.target)),
                (
                    "wall_target",
                    unit.wall_target
                        .map_or(Json::Null, |id| Json::Num(id.0 as f64)),
                ),
            ]));
        }
        if first_damage.is_null() {
            if let Some((index, _)) = battle
                .buildings
                .iter()
                .enumerate()
                .find(|(index, b)| b.hp < initial_hp[*index])
            {
                first_damage = object(vec![
                    ("time", Json::Num(battle.t)),
                    ("building", Json::Num(index as f64)),
                ]);
            }
        }
        if first_wall_damage.is_null() {
            if let Some((index, _)) = battle
                .walls
                .iter()
                .enumerate()
                .find(|(index, w)| w.hp < initial_wall_hp[*index])
            {
                first_wall_damage = object(vec![
                    ("time", Json::Num(battle.t)),
                    ("wall", Json::Num(index as f64)),
                ]);
            }
        }
        if battle.destroyed_counted >= battle.total_counted || battle.offense_finished() {
            break;
        }
    }
    let result = battle.result();
    object(vec![
        ("enabled", Json::Bool(enabled)),
        ("visible_buildings_before", Json::Num(visible_before as f64)),
        (
            "unknown_traps_before",
            Json::Num(hidden_traps_before as f64),
        ),
        ("samples", Json::Arr(samples)),
        ("first_building_damage", first_damage),
        ("first_wall_damage", first_wall_damage),
        (
            "observed_path_hash_fnv64",
            Json::Str(format!("{hash:016x}")),
        ),
        ("stars", Json::Num(result.stars as f64)),
        ("destruction", Json::Num(result.destruction as f64)),
        ("end_time", Json::Num(result.time)),
    ])
}

pub fn evidence(catalog: Arc<Catalog>) -> Json {
    let fixture = fixtures();
    let mut cases = Vec::new();
    for case in fixture.at("cases").arr() {
        let before = demonstrate(case, false, Arc::clone(&catalog));
        let after = demonstrate(case, true, Arc::clone(&catalog));
        assert_ne!(
            before.at("observed_path_hash_fnv64"),
            after.at("observed_path_hash_fnv64"),
            "{} must change behavior: before={} after={}",
            case.at("id").str(),
            to_json(&before),
            to_json(&after)
        );
        cases.push(object(vec![
            ("id", case.at("id").clone()),
            ("flag", case.at("flag").clone()),
            ("before", before),
            ("after", after),
        ]));
    }
    object(vec![
        ("synthetic", Json::Bool(true)),
        ("calibration", Json::Bool(false)),
        ("cases", Json::Arr(cases)),
    ])
}

pub fn evidence_text(catalog: Arc<Catalog>) -> String {
    to_json(&evidence(catalog))
}
