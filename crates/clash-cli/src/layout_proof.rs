//! Deterministic synthetic proofs, with every accepted candidate built through
//! setup::build. The reference corpus is read-only and never repaired.
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::path::Path;
use std::sync::Arc;

use crate::catalog::Catalog;
use crate::json::Json;

use clash_layout::admit::{admit, AdmissionReport, AdmittedLayout};
use clash_layout::geometry::{self, Tiles};
use clash_layout::json::{encode, identity, number, object, read, string};
use clash_layout::model::*;
use clash_layout::rules::{self, BaseRules};

fn require(condition: bool, message: impl Into<String>) -> Result<(), String> {
    if condition {
        Ok(())
    } else {
        Err(message.into())
    }
}

fn set(value: &mut Json, key: &str, new: Json) {
    let Json::Obj(fields) = value else {
        panic!("proof expected object")
    };
    if let Some((_, old)) = fields.iter_mut().find(|(k, _)| k == key) {
        *old = new;
    } else {
        fields.push((key.to_owned(), new));
    }
}

fn placement(key: &str, x: i32, y: i32) -> Json {
    object([("key", string(key)), ("x", number(x)), ("y", number(y))])
}

fn tiny(th: i64) -> Json {
    object([
        ("name", string("declared synthetic admission fixture")),
        ("town_hall", number(th as i32)),
        (
            "buildings",
            Json::Arr(vec![
                placement("th", 4, 4),
                placement("st", 10, 4),
                placement("cc", 15, 4),
                placement("herohall", 20, 4),
                placement("banner", 26, 4),
                placement("tesla", 30, 4),
            ]),
        ),
        (
            "walls",
            Json::Arr(vec![Json::Arr(vec![number(10), number(10)])]),
        ),
        ("traps", Json::Arr(vec![placement("bomb", 13, 10)])),
        ("heroes", Json::Arr(vec![string("Archer Queen")])),
        ("cc_troops", Json::Arr(vec![string("Dragon")])),
        (
            "guardian",
            if th >= 18 {
                string("Longshot")
            } else {
                Json::Null
            },
        ),
    ])
}

fn full(th: i64, rules: &BaseRules, catalog: &Catalog) -> Result<Json, String> {
    let inventory = &rules.town_halls[&th];
    let mut occupied = Tiles::new();
    let mut place = |size: usize| -> Result<Tile, String> {
        for y in 0..44 - size as i32 + 1 {
            for x in 0..44 - size as i32 + 1 {
                let footprint: Tiles = (0..size as i32)
                    .flat_map(|dx| (0..size as i32).map(move |dy| (x + dx, y + dy)))
                    .collect();
                if footprint.is_disjoint(&occupied) {
                    occupied.extend(footprint);
                    return Ok((x, y));
                }
            }
        }
        Err("synthetic fixture packing exhausted board".to_owned())
    };
    let mut buildings = Vec::new();
    for (key, count) in &inventory.buildings {
        let size = catalog
            .building_types
            .iter()
            .find(|(k, _)| k == key)
            .unwrap()
            .1
            .size;
        for _ in 0..*count {
            let (x, y) = place(size)?;
            let mut b = placement(key, x, y);
            if key == "crafting" {
                set(&mut b, "mode", string("cake"));
            }
            buildings.push(b);
        }
    }
    let mut traps = Vec::new();
    for (key, count) in &inventory.traps {
        let size = catalog
            .trap_sizes
            .iter()
            .find(|(k, _)| k == key)
            .map_or(1, |(_, s)| *s);
        for _ in 0..*count {
            let (x, y) = place(size)?;
            traps.push(placement(key, x, y));
        }
    }
    let mut walls = Vec::new();
    for _ in 0..inventory.walls {
        let (x, y) = place(1)?;
        walls.push(Json::Arr(vec![number(x), number(y)]));
    }
    Ok(object([
        (
            "name",
            string("synthetic fully merged packing; not a real base"),
        ),
        ("town_hall", number(th as i32)),
        ("buildings", Json::Arr(buildings)),
        ("traps", Json::Arr(traps)),
        ("walls", Json::Arr(walls)),
    ]))
}

fn evaluate(
    raw: &Json,
    rules: &BaseRules,
    catalog: Arc<Catalog>,
    policy: &AdmissionPolicy,
) -> Result<AdmittedLayout, AdmissionReport> {
    Layout::from_json(raw).and_then(|layout| admit(layout, rules, catalog, policy))
}

fn build_and_geometry(admitted: &AdmittedLayout, catalog: Arc<Catalog>) -> Result<(), String> {
    let plan = object([
        ("$type", string("Stage")),
        ("drops", Json::Arr(Vec::new())),
        ("ticks", Json::Arr(Vec::new())),
        ("revives_left", number(0)),
        ("strength", number(1)),
        ("loadouts", Json::Obj(Vec::new())),
        ("town_hall", number(admitted.layout().town_hall as i32)),
    ]);
    let options = object([("town_hall", number(admitted.layout().town_hall as i32))]);
    let mut battle = crate::setup::build(
        &admitted.engine_json(),
        &plan,
        &options,
        Arc::clone(&catalog),
    )
    .map_err(|e| format!("accepted layout failed setup: {e}"))?;
    let sizes: Vec<_> = catalog
        .building_types
        .iter()
        .map(|(k, bt)| (k.clone(), bt.size))
        .collect();
    let expected: Tiles = geometry::blocked(admitted.layout(), &sizes)
        .into_iter()
        .map(|(x, y)| (x + 3, y + 3))
        .collect();
    let actual: Tiles = battle.live_no_deploy().iter().copied().collect();
    require(
        expected == actual,
        "deploy mask differs from engine live_no_deploy",
    )?;
    require(
        crate::scoring::hole_tiles(&admitted.engine_json(), &sizes, 44, 3) == admitted.hole_tiles(),
        "scoring did not use shared eight-way hole count",
    )?;
    Ok(())
}

fn inventory_proof(root: &Path, rules: &BaseRules) -> Result<(), String> {
    let fixture = read(&root.join("fixtures/layout/inventory.json"))?;
    for th in 16..=18 {
        let expected = fixture.at("town_halls").at(&th.to_string());
        let mut buildings = fixture.at("common").obj().to_vec();
        buildings.extend(expected.at("buildings").obj().to_vec());
        let buildings: BTreeMap<_, _> =
            buildings.into_iter().map(|(k, v)| (k, v.usize())).collect();
        let traps: BTreeMap<_, _> = expected
            .at("traps")
            .obj()
            .iter()
            .map(|(k, v)| (k.clone(), v.usize()))
            .collect();
        require(
            buildings == rules.town_halls[&th].buildings,
            format!("TH{th} inventory differs from frozen count fixture"),
        )?;
        require(
            traps == rules.town_halls[&th].traps,
            format!("TH{th} trap inventory differs"),
        )?;
        require(
            expected.at("walls").usize() == rules.town_halls[&th].walls,
            "wall inventory differs",
        )?;
    }
    Ok(())
}

fn boundary_proof(root: &Path, rules: &BaseRules, catalog: Arc<Catalog>) -> Result<Json, String> {
    let fixture = read(&root.join("fixtures/layout/admission.json"))?;
    let partial = AdmissionPolicy {
        require_full: false,
        ..AdmissionPolicy::default()
    };
    let mut results = Vec::new();
    for case in fixture.at("cases").arr() {
        let id = case.at("id").str();
        let result = evaluate(case.at("layout"), rules, Arc::clone(&catalog), &partial);
        if let Some(expected_code) = case.get("code") {
            let report = result
                .as_ref()
                .err()
                .ok_or_else(|| format!("boundary {id} accepted unexpectedly"))?;
            require(
                report.issues.iter().any(|i| i.code == expected_code.str()),
                format!(
                    "boundary {id}: expected {} got {}",
                    expected_code.str(),
                    encode(&report.to_json())
                ),
            )?;
        } else {
            let admitted = result
                .as_ref()
                .map_err(|r| format!("boundary {id}: {}", encode(&r.to_json())))?;
            build_and_geometry(admitted, Arc::clone(&catalog))?;
            let copy =
                Layout::from_json(&admitted.engine_json()).map_err(|r| encode(&r.to_json()))?;
            require(
                copy == *admitted.layout(),
                format!("roundtrip changed {id}"),
            )?;
        }
        results.push(object([("id", string(id)), ("passed", Json::Bool(true))]));
    }
    // Explicitly prove the full/partial distinction and independent wall policy.
    let raw = tiny(16);
    require(
        evaluate(
            &raw,
            rules,
            Arc::clone(&catalog),
            &AdmissionPolicy::default(),
        )
        .is_err(),
        "full inventory waived missing items",
    )?;
    let all_walls = AdmissionPolicy {
        require_full: false,
        require_all_walls: true,
        ..AdmissionPolicy::default()
    };
    require(
        evaluate(&raw, rules, Arc::clone(&catalog), &all_walls)
            .err()
            .is_some_and(|r| r.issues.iter().any(|i| i.code == "walls_missing")),
        "wall placement requirement not independent",
    )?;
    // A low Hero Hall cannot house a maximum-level hero.
    let mut low_hall = tiny(16);
    set(&mut low_hall, "levels", object([("herohall", number(1))]));
    require(
        evaluate(&low_hall, rules, Arc::clone(&catalog), &partial)
            .err()
            .is_some_and(|r| r.issues.iter().any(|i| i.code == "hero_unlock")),
        "Hero Hall unlock ignored",
    )?;
    Ok(Json::Arr(results))
}

fn geometry_proof(catalog: Arc<Catalog>) -> Result<Json, String> {
    let mut results = Vec::new();
    let ring: Tiles = (10..=20)
        .flat_map(|n| [(10, n), (20, n), (n, 10), (n, 20)])
        .collect();
    require(
        geometry::compartments(&ring)
            .iter()
            .map(Tiles::len)
            .collect::<Vec<_>>()
            == vec![81],
        "sealed wall ring",
    )?;
    let mut diagonal = ring.clone();
    diagonal.remove(&(10, 10));
    require(
        geometry::compartments(&diagonal).is_empty(),
        "diagonal wall gap must leak",
    )?;
    require(
        geometry::outside(&diagonal).contains(&(15, 15)),
        "outside cannot reach diagonal gap",
    )?;
    require(
        !geometry::outside(&ring).contains(&(15, 15)),
        "outside crossed sealed ring",
    )?;
    let holes = geometry::holes(&geometry::dilate(&ring), 44, 3);
    require(
        holes.iter().map(Tiles::len).collect::<Vec<_>>() == vec![49],
        "sealed deploy pocket",
    )?;
    // The eight-way correction has a known minimal counterexample to four-way
    // flooding: a ring in blocked space with only its corner removed.
    let leak = geometry::holes(&diagonal, 44, 3);
    require(
        leak.is_empty(),
        "diagonal deploy pocket must connect to margin",
    )?;
    let legal = Tiles::from([(0, 0), (1, 1)]);
    let blocked = Tiles::from([(1, 0)]);
    require(
        geometry::flood(&Tiles::from([(0, 0)]), &legal, None).len() == 2,
        "wall diagonal connectivity",
    )?;
    require(
        geometry::flood(&Tiles::from([(0, 0)]), &legal, Some(&blocked)).len() == 1,
        "building hitbox corner restriction",
    )?;
    let mut grid = crate::grid::Grid::new(6);
    // Runtime half-tile wall cells do not obstruct diagonal corners.
    grid.set_wall(1, 0, true);
    grid.set_wall(0, 1, true);
    let field = grid.source_field(0.75, 0.75, f64::INFINITY);
    let (i, j) = grid.cell(1.25, 1.25);
    let cell = grid.index(i, j);
    require(
        grid.distance(field, cell).is_finite() && grid.distance(field, cell) < 1e9,
        "runtime wall corner differs",
    )?;
    let wall_corner_distance = grid.distance(field, cell);
    let mut hitbox_grid = crate::grid::Grid::new(6);
    hitbox_grid.block_square(1.25, 0.75, 0.2, true);
    hitbox_grid.block_square(0.75, 1.25, 0.2, true);
    let field = hitbox_grid.source_field(0.75, 0.75, f64::INFINITY);
    let (i, j) = hitbox_grid.cell(1.25, 1.25);
    let cell = hitbox_grid.index(i, j);
    require(
        hitbox_grid.distance(field, cell) > wall_corner_distance,
        "runtime building hitboxes allowed a diagonal corner cut",
    )?;
    let sizes: Vec<_> = catalog
        .building_types
        .iter()
        .map(|(k, bt)| (k.clone(), bt.size))
        .collect();
    let mut layout = Layout::from_json(&object([
        ("buildings", Json::Arr(vec![placement("tesla", 0, 0)])),
        ("traps", Json::Arr(vec![placement("bomb", 10, 10)])),
        ("heroes", Json::Arr(Vec::new())),
        ("cc_troops", Json::Arr(Vec::new())),
    ]))
    .map_err(|r| encode(&r.to_json()))?;
    require(
        geometry::blocked(&layout, &sizes).is_empty(),
        "Tesla/trap deployment exclusion",
    )?;
    layout.buildings[0].key = "banner".to_owned();
    let red = geometry::blocked(&layout, &sizes);
    require(
        red.len() == 16 && red.contains(&(-1, -1)) && red.contains(&(2, 2)),
        "banner footprint dilation and edge margin",
    )?;
    require(
        geometry::holes(&red, 44, 3).is_empty(),
        "edge margin access",
    )?;
    for id in [
        "sealed_ring",
        "diagonal_wall_leak",
        "outside",
        "sealed_drop_hole",
        "diagonal_drop_leak",
        "hitbox_corners",
        "runtime_half_tile_walls",
        "runtime_hitbox_corners",
        "tesla_trap_exclusion",
        "banner_footprint",
        "edge_margin",
    ] {
        results.push(object([("id", string(id)), ("passed", Json::Bool(true))]));
    }
    Ok(Json::Arr(results))
}

fn mutate(mut raw: Json, index: usize, bits: u64) -> Json {
    // Vary the near-legal parent as well as the malformed field.
    let offset = (((bits >> 16) % 5) as i32, ((bits >> 24) % 18) as i32);
    if let Json::Obj(fields) = &mut raw {
        for (key, value) in fields {
            if matches!(key.as_str(), "buildings" | "traps") {
                if let Json::Arr(items) = value {
                    for item in items {
                        let x = item.at("x").i64() as i32 + offset.0;
                        let y = item.at("y").i64() as i32 + offset.1;
                        set(item, "x", number(x));
                        set(item, "y", number(y));
                    }
                }
            } else if key == "walls" {
                *value = Json::Arr(vec![Json::Arr(vec![
                    number(10 + offset.0),
                    number(10 + offset.1),
                ])]);
            }
        }
    }
    set(
        &mut raw,
        "wall_level",
        number(14 + ((bits >> 32) % 3) as i32),
    );
    set(
        &mut raw,
        "heroes",
        Json::Arr(vec![string(
            [
                "Archer Queen",
                "Barbarian King",
                "Grand Warden",
                "Minion Prince",
            ][(bits % 4) as usize],
        )]),
    );
    set(
        &mut raw,
        "cc_troops",
        Json::Arr(vec![object([
            ("name", string("Archer")),
            ("count", number(1 + ((bits >> 40) % 45) as i32)),
        ])]),
    );
    let b = |raw: &mut Json, key: &str, value: Json| {
        let Json::Obj(fields) = raw else {
            unreachable!()
        };
        let Json::Arr(buildings) =
            &mut fields.iter_mut().find(|(k, _)| k == "buildings").unwrap().1
        else {
            unreachable!()
        };
        set(&mut buildings[0], key, value);
    };
    match index % 64 {
        0 => b(&mut raw, "x", Json::Bool(true)),
        1 => b(&mut raw, "x", string("4")),
        2 => b(&mut raw, "x", Json::Num(4.25)),
        3 => b(&mut raw, "x", Json::Num(1e100)),
        4 => b(&mut raw, "x", number(-1)),
        5 => b(&mut raw, "x", number(43)),
        6 => set(
            &mut raw,
            "walls",
            Json::Arr(vec![Json::Arr(vec![
                number(4 + offset.0),
                number(4 + offset.1),
            ])]),
        ),
        7 => set(
            &mut raw,
            "traps",
            Json::Arr(vec![placement("giant", 4 + offset.0, 4 + offset.1)]),
        ),
        8 => b(&mut raw, "key", string("invented")),
        9 => b(&mut raw, "mode", string("invented")),
        10 => set(
            &mut raw,
            "traps",
            Json::Arr(vec![placement("invented", 12, 12)]),
        ),
        11 => set(
            &mut raw,
            "heroes",
            Json::Arr(vec![string("Archer Queen"), string("Archer Queen")]),
        ),
        12 => set(&mut raw, "heroes", Json::Arr(vec![string("Invented")])),
        13 => set(&mut raw, "levels", object([("st", number(0))])),
        14 => set(&mut raw, "levels", object([("st", number(999))])),
        15 => set(&mut raw, "levels", object([("trap:bomb", number(999))])),
        16 => set(
            &mut raw,
            "walls",
            Json::Arr(vec![Json::Arr(vec![number(10), number(10)]); 326]),
        ),
        17 => set(
            &mut raw,
            "wall_levels",
            Json::Arr(vec![object([
                ("x", number(43)),
                ("y", number(43)),
                ("level", number(16)),
            ])]),
        ),
        18 => set(
            &mut raw,
            "hero_levels",
            object([("Archer Queen", number(0))]),
        ),
        19 => set(
            &mut raw,
            "cc_troops",
            Json::Arr(vec![object([
                ("name", string("Dragon")),
                ("count", number(99)),
            ])]),
        ),
        20 => set(&mut raw, "cc_troops", Json::Arr(vec![string("Invented")])),
        21 => set(&mut raw, "guardian", string("Invented")),
        22 => set(&mut raw, "town_hall", number(19)),
        23 => set(&mut raw, "buildings", Json::Null),
        24 => {
            let Json::Obj(fields) = &mut raw else {
                unreachable!()
            };
            fields.push(("town_hall".to_owned(), number(16)));
        }
        25 => b(&mut raw, "x", Json::Num(f64::NAN)),
        26 => set(&mut raw, "levels", object([("st", Json::Bool(true))])),
        27 => set(&mut raw, "heroes", Json::Arr(vec![Json::Obj(Vec::new())])),
        28 => set(&mut raw, "wall_level", number(999)),
        29 => set(
            &mut raw,
            "traps",
            Json::Arr(vec![object([
                ("key", string("skeleton")),
                ("x", number(12)),
                ("y", number(12)),
                ("mode", string("both")),
            ])]),
        ),
        30 => set(&mut raw, "levels", object([("typo", number(1))])),
        31 => set(&mut raw, "levels", object([("herohall", number(1))])),
        32 => b(&mut raw, "y", Json::Num(f64::INFINITY)),
        33 => b(&mut raw, "y", Json::Num(f64::NEG_INFINITY)),
        34 => set(
            &mut raw,
            "walls",
            Json::Arr(vec![Json::Arr(vec![Json::Bool(false), number(1)])]),
        ),
        35 => set(
            &mut raw,
            "walls",
            Json::Arr(vec![Json::Arr(vec![number(1)])]),
        ),
        36 => set(
            &mut raw,
            "cc_troops",
            Json::Arr(vec![object([
                ("name", string("Archer")),
                ("count", number(-1)),
            ])]),
        ),
        37 => set(
            &mut raw,
            "cc_troops",
            Json::Arr(vec![string("Barbarian King")]),
        ),
        38 => set(
            &mut raw,
            "cc_troops",
            Json::Arr(vec![object([
                ("name", string("Archer")),
                ("level", string("unknown")),
            ])]),
        ),
        39 => set(&mut raw, "layout_schema", number(2)),
        40 => set(&mut raw, "traps", Json::Arr(vec![placement("bomb", -1, 0)])),
        41 => set(
            &mut raw,
            "traps",
            Json::Arr(vec![placement("giant", 43, 43)]),
        ),
        42 => b(&mut raw, "x", number(i32::MAX)),
        43 => b(&mut raw, "x", number(i32::MIN)),
        44 => set(&mut raw, "wall_levels", Json::Bool(false)),
        45 => set(&mut raw, "levels", object([("st", string("unknown"))])),
        46 => set(&mut raw, "hero_levels", object([("Invented", number(1))])),
        47 => set(
            &mut raw,
            "instance_ids",
            object([("walls", Json::Arr(vec![string("")]))]),
        ),
        48 => set(
            &mut raw,
            "instance_ids",
            object([("buildings", Json::Arr(vec![string("bad")]))]),
        ),
        49 => b(&mut raw, "mode", Json::Num(1.0)),
        50 => set(&mut raw, "heroes", Json::Bool(false)),
        51 => set(&mut raw, "levels", Json::Arr(Vec::new())),
        52 => set(&mut raw, "hero_levels", Json::Arr(Vec::new())),
        53 => set(
            &mut raw,
            "walls",
            Json::Arr(vec![Json::Arr(vec![number(-1), number(0)])]),
        ),
        54 => set(&mut raw, "guardian", Json::Arr(Vec::new())),
        55 => set(
            &mut raw,
            "cc_troops",
            Json::Arr(vec![object([
                ("name", string("Dragon")),
                ("count", Json::Num(0.5)),
            ])]),
        ),
        56 => set(&mut raw, "town_hall", string("16")),
        57 => set(&mut raw, "town_hall", Json::Bool(true)),
        58 => set(&mut raw, "town_hall", Json::Num(16.5)),
        59 => set(&mut raw, "traps", Json::Arr(vec![Json::Null])),
        60 => set(
            &mut raw,
            "walls",
            Json::Arr(vec![
                Json::Arr(vec![number(10), number(10)]),
                Json::Arr(vec![number(10), number(10)]),
            ]),
        ),
        61 => set(
            &mut raw,
            "buildings",
            Json::Arr(vec![placement("th", 4, 4), placement("th", 20, 20)]),
        ),
        62 => {
            // Valid independent metadata change; must have no physical effect.
            set(
                &mut raw,
                "notes",
                string(format!("synthetic mutation {bits}")),
            );
        }
        _ => {
            // Some relocations are legal, others collide; admission decides.
            b(&mut raw, "x", number((bits % 40) as i32));
            b(&mut raw, "y", number(((bits >> 8) % 40) as i32));
        }
    }
    raw
}

fn fuzz_one(
    index: usize,
    rules: &BaseRules,
    catalog: Arc<Catalog>,
    build: bool,
) -> Result<(bool, String), String> {
    let bits = (index as u64)
        .wrapping_mul(0x9e3779b97f4a7c15)
        .rotate_left(23)
        ^ 0x4d315f61646d6974;
    let raw = mutate(tiny(16 + (index % 3) as i64), index, bits);
    let policy = AdmissionPolicy {
        require_full: false,
        ..AdmissionPolicy::default()
    };
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        evaluate(&raw, rules, Arc::clone(&catalog), &policy)
    }))
    .map_err(|_| format!("admission panicked for synthetic mutation {index}"))?;
    match outcome {
        Ok(layout) => {
            if build {
                build_and_geometry(&layout, catalog)?;
            }
            Ok((true, layout.physical_identity().to_owned()))
        }
        Err(report) => {
            require(
                !report.issues.is_empty()
                    && report.issues.iter().all(|i| {
                        !i.code.is_empty() && !i.path.is_empty() && !i.expected.is_empty()
                    }),
                format!("mutation {index} has no structured reason"),
            )?;
            Ok((false, identity(encode(&report.to_json()).as_bytes())))
        }
    }
}

fn corpus_proof(root: &Path, rules: &BaseRules, catalog: Arc<Catalog>) -> Result<Json, String> {
    let git = std::process::Command::new("git")
        .current_dir(root)
        .args([
            "ls-files",
            "-z",
            "--",
            "data/reference-bases/*.json",
            "data/reference-bases/**/*.json",
        ])
        .output()
        .map_err(|e| e.to_string())?;
    require(
        git.status.success(),
        "git ls-files failed for committed corpus",
    )?;
    let mut paths: BTreeSet<_> = String::from_utf8(git.stdout)
        .map_err(|e| e.to_string())?
        .split('\0')
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect();
    paths.extend([
        "rust/data/target17.json".to_owned(),
        "rust/data/target18.json".to_owned(),
    ]);
    let mut reports = Vec::new();
    for path in paths {
        let raw = read(&root.join(&path))?;
        let mut verdicts = Vec::new();
        for full in [true, false] {
            let policy = AdmissionPolicy {
                require_full: full,
                ..AdmissionPolicy::default()
            };
            let result = evaluate(&raw, rules, Arc::clone(&catalog), &policy);
            let receipt = match result {
                Ok(layout) => {
                    build_and_geometry(&layout, Arc::clone(&catalog))?;
                    layout.receipt()
                }
                Err(report) => report.to_json(),
            };
            verdicts.push(object([
                ("require_full", Json::Bool(full)),
                ("report", receipt),
            ]));
        }
        reports.push(object([
            ("path", string(path)),
            ("input_identity", string(identity(encode(&raw).as_bytes()))),
            ("verdicts", Json::Arr(verdicts)),
            ("geometry", corpus_geometry(&raw, &catalog)),
        ]));
    }
    Ok(Json::Arr(reports))
}

pub fn run(
    root: &Path,
    output: &Path,
    catalog: Arc<Catalog>,
    catalog_bytes: &[u8],
) -> Result<(), String> {
    let rules = BaseRules::load(&root.join("rust/data/base_rules.json"))?;
    require(
        rules.catalog_identity == identity(catalog_bytes),
        "rules/catalog identity mismatch",
    )?;
    let derived = crate::layout_rules::derive(root, &catalog, catalog_bytes)?;
    require(
        derived == rules.document,
        "tracked base_rules.json differs from Rust importer",
    )?;
    require(
        crate::layout_rules::derive(root, &catalog, catalog_bytes)? == derived,
        "rule import is nondeterministic",
    )?;
    inventory_proof(root, &rules)?;
    println!("layout proof: importer and TH16/17/18 inventory snapshots passed");
    let boundaries = boundary_proof(root, &rules, Arc::clone(&catalog))?;
    let geometry = geometry_proof(Arc::clone(&catalog))?;
    let geometry_goldens = geometry_fixture_proof(root, &rules, Arc::clone(&catalog))?;
    account_proof(&rules, Arc::clone(&catalog))?;
    let partial = AdmissionPolicy {
        require_full: false,
        ..AdmissionPolicy::default()
    };
    for th in 16..=18 {
        let raw = full(th, &rules, &catalog)?;
        let admitted = evaluate(
            &raw,
            &rules,
            Arc::clone(&catalog),
            &AdmissionPolicy {
                require_all_walls: true,
                ..AdmissionPolicy::default()
            },
        )
        .map_err(|r| format!("full TH{th} fixture rejected: {}", encode(&r.to_json())))?;
        let roundtrip =
            Layout::from_json(&admitted.engine_json()).map_err(|r| encode(&r.to_json()))?;
        require(
            roundtrip == *admitted.layout(),
            format!("full TH{th} export changed modes, hero/banner order, CC, guardian or levels"),
        )?;
        build_and_geometry(&admitted, Arc::clone(&catalog))?;
        let mut renamed = admitted.layout().clone();
        renamed.name = "renamed".to_owned();
        renamed.notes = "changed notes".to_owned();
        let again = admit(renamed, &rules, Arc::clone(&catalog), &partial)
            .map_err(|r| encode(&r.to_json()))?;
        require(
            again.physical_identity() == admitted.physical_identity(),
            "metadata changed physical identity",
        )?;
        let mut reordered = admitted.layout().clone();
        reordered.buildings.swap(0, 1);
        // Rebind heroes after changing array order, as JSON import does.
        let reordered =
            Layout::from_json(&reordered.to_json()).map_err(|r| encode(&r.to_json()))?;
        let changed = admit(reordered, &rules, Arc::clone(&catalog), &partial)
            .map_err(|r| encode(&r.to_json()))?;
        require(
            changed.physical_identity() != admitted.physical_identity(),
            "building order omitted from physical identity",
        )?;
    }
    println!("layout proof: boundary fixtures, full synthetic packings and geometry passed");
    let corpus = corpus_proof(root, &rules, Arc::clone(&catalog))?;
    let mutations = 100_000;
    let mut accepted = 0usize;
    let mut fingerprints = String::new();
    for index in 0..mutations {
        let (ok, fingerprint) = fuzz_one(index, &rules, Arc::clone(&catalog), true)?;
        accepted += usize::from(ok);
        fingerprints.push_str(&fingerprint);
        if (index + 1) % 10_000 == 0 {
            println!(
                "layout proof: mutations={} accepted={} rejected={}",
                index + 1,
                accepted,
                index + 1 - accepted
            );
        }
    }
    require(
        accepted >= 1000,
        "too few accepted mutations to exercise setup",
    )?;
    let count = 4096;
    let reference: Vec<_> = (0..count)
        .map(|i| fuzz_one(i, &rules, Arc::clone(&catalog), false))
        .collect::<Result<_, _>>()?;
    for workers in [4, 16] {
        let result = std::thread::scope(|scope| {
            let handles: Vec<_> = (0..workers)
                .map(|worker| {
                    let rules = &rules;
                    let catalog = Arc::clone(&catalog);
                    scope.spawn(move || {
                        (worker..count)
                            .step_by(workers)
                            .map(|i| {
                                fuzz_one(i, rules, Arc::clone(&catalog), true)
                                    .map(|result| (i, result))
                            })
                            .collect::<Result<Vec<_>, _>>()
                    })
                })
                .collect();
            let mut rows = Vec::new();
            for handle in handles {
                rows.extend(
                    handle
                        .join()
                        .map_err(|_| "determinism worker panicked".to_owned())??,
                );
            }
            rows.sort_by_key(|(i, _)| *i);
            Ok::<_, String>(rows.into_iter().map(|(_, row)| row).collect::<Vec<_>>())
        })?;
        require(
            result == reference,
            format!("admission/setup determinism differs at {workers} workers"),
        )?;
    }
    let executable = std::env::current_exe().map_err(|e| e.to_string())?;
    let executable_bytes = std::fs::read(executable).map_err(|e| e.to_string())?;
    let mut fixture_identities = Vec::new();
    for name in ["admission.json", "geometry.json", "inventory.json"] {
        let bytes =
            std::fs::read(root.join("fixtures/layout").join(name)).map_err(|e| e.to_string())?;
        fixture_identities.push((name.to_owned(), string(identity(&bytes))));
    }
    let evidence =
        "Model legality and regression proof. No Python execution or real-game calibration.";
    let report = object([
        ("schema_version", number(1)),
        ("synthetic", Json::Bool(true)),
        ("evidence", string(evidence)),
        ("executable_identity", string(identity(&executable_bytes))),
        ("rules_identity", string(&rules.identity)),
        ("catalog_identity", string(&rules.catalog_identity)),
        ("fixture_identities", Json::Obj(fixture_identities)),
        ("boundaries", boundaries),
        ("geometry", geometry),
        ("geometry_goldens", geometry_goldens),
        ("full_inventory_packings", number(3)),
        ("mutations", number(mutations as i32)),
        ("accepted", number(accepted as i32)),
        ("rejected", number((mutations - accepted) as i32)),
        (
            "outcome_identity",
            string(identity(fingerprints.as_bytes())),
        ),
        ("determinism_cases", number(count as i32)),
        (
            "determinism_workers",
            Json::Arr(vec![number(1), number(4), number(16)]),
        ),
        ("corpus", corpus),
    ]);
    std::fs::write(output, rules::pretty(&report)).map_err(|e| e.to_string())?;
    println!("layout proof passed: 100000 mutations; {accepted} accepted and built; {} structured rejections; corpus={} report={}",mutations-accepted,report.at("corpus").arr().len(),output.display());
    Ok(())
}

// Preserve the old algorithm only as an explicit scoring-regression diagnostic.
fn four_way_hole_tiles(blocked: &Tiles) -> usize {
    let mut legal = Tiles::new();
    let mut queue = VecDeque::new();
    for x in -3..47 {
        for y in -3..47 {
            if !blocked.contains(&(x, y)) {
                legal.insert((x, y));
                if x == -3 || y == -3 || x == 46 || y == 46 {
                    queue.push_back((x, y));
                }
            }
        }
    }
    let mut seen: Tiles = queue.iter().copied().collect();
    while let Some((x, y)) = queue.pop_front() {
        for (dx, dy) in [(1, 0), (-1, 0), (0, 1), (0, -1)] {
            let next = (x + dx, y + dy);
            if legal.contains(&next) && seen.insert(next) {
                queue.push_back(next);
            }
        }
    }
    legal.len() - seen.len()
}

fn corpus_geometry(raw: &Json, catalog: &Catalog) -> Json {
    let Ok(layout) = Layout::from_json(raw) else {
        return Json::Null;
    };
    let sizes: Vec<_> = catalog
        .building_types
        .iter()
        .map(|(k, bt)| (k.clone(), bt.size))
        .collect();
    if layout
        .buildings
        .iter()
        .any(|b| !sizes.iter().any(|(key, _)| key == &b.key))
    {
        return Json::Null;
    }
    let blocked = geometry::blocked(&layout, &sizes);
    let four = four_way_hole_tiles(&blocked);
    let eight: usize = geometry::holes(&blocked, 44, 3)
        .iter()
        .map(Tiles::len)
        .sum();
    object([
        ("four_way_hole_tiles", number(four as i32)),
        ("eight_way_hole_tiles", number(eight as i32)),
        (
            "scoring_correction_tiles",
            number(four as i32 - eight as i32),
        ),
    ])
}

fn geometry_fixture_proof(
    root: &Path,
    rules: &BaseRules,
    catalog: Arc<Catalog>,
) -> Result<Json, String> {
    let fixture = read(&root.join("fixtures/layout/geometry.json"))?;
    for (path, expected) in fixture.at("corpus_holes").obj() {
        let raw = read(&root.join(path))?;
        let actual = corpus_geometry(&raw, &catalog);
        for (field, value) in expected.obj() {
            require(
                actual.get(field) == Some(value),
                format!("reviewed scoring correction changed for {path}.{field}"),
            )?;
        }
    }
    let partial = AdmissionPolicy {
        require_full: false,
        ..AdmissionPolicy::default()
    };
    let mut rows = Vec::new();
    for case in fixture.at("cases").arr() {
        let lo = case.at("ring").arr()[0].i64() as i32;
        let hi = case.at("ring").arr()[1].i64() as i32;
        let mut walls: Tiles = (lo..=hi)
            .flat_map(|n| [(lo, n), (hi, n), (n, lo), (n, hi)])
            .collect();
        for tile in case.at("remove").arr() {
            walls.remove(&(tile.arr()[0].i64() as i32, tile.arr()[1].i64() as i32));
        }
        let sizes: Vec<_> = geometry::compartments(&walls)
            .iter()
            .map(|g| number(g.len() as i32))
            .collect();
        require(
            Json::Arr(sizes) == *case.at("compartments"),
            format!("geometry {} compartment sizes", case.at("id").str()),
        )?;
        let center = (lo + (hi - lo) / 2, lo + (hi - lo) / 2);
        require(
            geometry::outside(&walls).contains(&center) == case.at("center_outside").bool(),
            "geometry outside region",
        )?;
        let raw = object([
            ("buildings", Json::Arr(Vec::new())),
            (
                "walls",
                Json::Arr(
                    walls
                        .iter()
                        .map(|&(x, y)| Json::Arr(vec![number(x), number(y)]))
                        .collect(),
                ),
            ),
            ("heroes", Json::Arr(Vec::new())),
            ("cc_troops", Json::Arr(Vec::new())),
            ("guardian", Json::Null),
        ]);
        let admitted = evaluate(&raw, rules, Arc::clone(&catalog), &partial)
            .map_err(|r| encode(&r.to_json()))?;
        build_and_geometry(&admitted, Arc::clone(&catalog))?;
        let holes = geometry::holes(&geometry::dilate(&walls), 44, 3);
        require(
            Json::Arr(holes.iter().map(|g| number(g.len() as i32)).collect()) == *case.at("holes"),
            "geometry drop-hole sizes",
        )?;
        let four = four_way_hole_tiles(&geometry::dilate(&walls));
        require(
            four == case.at("four_way_hole_tiles").usize(),
            "old scoring counterexample changed",
        )?;
        let no_holes = AdmissionPolicy {
            holes: HolePolicy::Forbid,
            ..partial.clone()
        };
        require(
            evaluate(&raw, rules, Arc::clone(&catalog), &no_holes).is_ok() == holes.is_empty(),
            "hole policy did not match geometry",
        )?;
        rows.push(object([
            ("id", case.at("id").clone()),
            ("passed", Json::Bool(true)),
            ("four_way_hole_tiles", number(four as i32)),
            ("eight_way_hole_tiles", number(admitted.hole_tiles() as i32)),
        ]));
    }
    Ok(Json::Arr(rows))
}

fn account_proof(rules: &BaseRules, catalog: Arc<Catalog>) -> Result<(), String> {
    let raw = object([
        ("buildings", Json::Arr(vec![placement("th", 4, 4)])),
        (
            "walls",
            Json::Arr(vec![
                Json::Arr(vec![number(10), number(10)]),
                Json::Arr(vec![number(11), number(11)]),
            ]),
        ),
        ("wall_level", number(16)),
        (
            "wall_levels",
            Json::Arr(vec![object([
                ("x", number(11)),
                ("y", number(11)),
                ("level", number(15)),
            ])]),
        ),
        ("heroes", Json::Arr(Vec::new())),
        ("cc_troops", Json::Arr(Vec::new())),
        ("guardian", Json::Null),
    ]);
    let owned = InventoryPolicy::Owned {
        snapshot_id: "synthetic-owned-mixed-walls".to_owned(),
        buildings: BTreeMap::from([("th".to_owned(), 1)]),
        traps: BTreeMap::new(),
        walls: 2,
        levels: BTreeMap::new(),
        hero_levels: BTreeMap::new(),
        wall_level: crate::stats::Level::Int(16),
        wall_levels: vec![crate::stats::Level::Int(16), crate::stats::Level::Int(15)],
        geared: BTreeSet::new(),
    };
    let policy = AdmissionPolicy {
        require_all_walls: true,
        inventory: owned,
        ..AdmissionPolicy::default()
    };
    let parent =
        evaluate(&raw, rules, Arc::clone(&catalog), &policy).map_err(|r| encode(&r.to_json()))?;
    let mut moved = parent.layout().clone();
    moved.walls[0].position = (12, 12);
    let child =
        admit(moved, rules, Arc::clone(&catalog), &policy).map_err(|r| encode(&r.to_json()))?;
    require(
        parent.account_identity() == child.account_identity(),
        "wall relocation changed account identity",
    )?;
    require(
        parent.physical_identity() != child.physical_identity(),
        "wall relocation omitted from physical identity",
    )?;
    build_and_geometry(&child, Arc::clone(&catalog))?;
    let mut upgraded = child.layout().clone();
    upgraded.walls[1].level = Some(crate::stats::Level::Int(16));
    require(
        admit(upgraded, rules, Arc::clone(&catalog), &policy)
            .err()
            .is_some_and(|r| r.issues.iter().any(|i| i.code == "account_wall_levels")),
        "owned mixed wall multiset not preserved",
    )?;
    let mut invented = child.layout().clone();
    invented.traps.push(TrapPlacement {
        id: "invented-trap".to_owned(),
        key: "bomb".to_owned(),
        position: (20, 20),
        mode: None,
    });
    require(
        admit(invented, rules, catalog, &policy).is_err(),
        "omitted owned inventory key allowed an extra trap",
    )?;
    Ok(())
}
