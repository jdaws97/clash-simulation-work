use super::*;
use buildings::{add_teslas, add_traps, apply_levels, build, Receipt};
use fit::{Anchor, Grid};

fn context() -> Context {
    Context::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")).unwrap()
}

#[test]
fn synthetic_projection_fit_and_conversion_known_answers() {
    let expected = Grid {
        cx: 965.0,
        top: 74.0,
        a: 16.0,
        b: 12.0,
    };
    let anchors = [(0.0, 0.0), (44.0, 0.0), (0.0, 44.0), (44.0, 44.0)].map(|tile| Anchor {
        tile,
        screen: expected.project(tile.0, tile.1),
    });
    let (actual, residual) = Grid::fit(&anchors).unwrap();
    assert_eq!(actual, expected);
    assert_eq!(residual, 0.0);
    assert_eq!(actual.project(10.0, 20.0), (805.0, 434.0));
    assert_eq!(actual.unproject(805.0, 434.0), (10.0, 20.0));
    let p = actual.project(13.0, 23.0);
    assert_eq!(actual.bottom_tip(p.0, p.1, 3, 0.45), (10, 20));
    assert!(Grid::fit(&[anchors[0], anchors[3]]).is_err());
    assert!(Grid::from_json(&obj([
        ("cx", num(0)),
        ("top", num(0)),
        ("a", num(0)),
        ("b", num(1))
    ]))
    .is_err());
}

#[test]
fn synthetic_wall_detector_keeps_runs_and_rejects_grass() {
    let grid = Grid {
        cx: 600.0,
        top: 20.0,
        a: 12.0,
        b: 9.0,
    };
    let mut image = Image::new(1200, 850, [100, 160, 40]).unwrap();
    let expected = Tiles::from([(8, 10), (9, 10), (10, 10)]);
    for &(x, y) in &expected {
        let p = grid.project(f64::from(x) + 0.5, f64::from(y) + 0.5);
        for dy in -2..=2 {
            for dx in -2..=2 {
                image.dot(p.0 as i32 + dx, p.1 as i32 + dy - 6, [240, 210, 160], 255);
            }
        }
    }
    assert_eq!(walls::detect(&image, grid, 12.0, &Tiles::new()), expected);
    let excluded = Tiles::from([(8, 10)]);
    assert_eq!(
        walls::detect(&image, grid, 12.0, &excluded),
        Tiles::from([(9, 10), (10, 10)])
    );
    assert!(walls::segment((0, 0), (3, 3)).is_err());
    let mut walls = Tiles::from([(1, 1), (4, 1), (6, 1)]);
    let added = walls::fill_gaps(&mut walls, &Tiles::from([(5, 1)]), 2);
    assert_eq!(added, Tiles::from([(2, 1), (3, 1)]));
}

#[test]
fn synthetic_build_completion_levels_and_admission() {
    let context = context();
    let mut receipt = Receipt::default();
    let mut walls = Tiles::new();
    for (p, q) in [
        ((5, 5), (35, 5)),
        ((35, 5), (35, 35)),
        ((35, 35), (5, 35)),
        ((5, 35), (5, 5)),
    ] {
        walls.extend(walls::segment(p, q).unwrap());
    }
    let mut layout = build(
        "th 20 20\nad 12 12\ninferno 26 26 multi\nwt 10 25\n",
        walls,
        "declared synthetic digitizer",
        16,
        &context.catalog,
        &mut receipt,
    )
    .unwrap();
    add_teslas(&mut layout, &context.catalog, &context.rules, &mut receipt).unwrap();
    let positions: Vec<_> = layout
        .buildings
        .iter()
        .filter(|b| b.key == "tesla")
        .map(|b| b.position)
        .collect();
    assert_eq!(positions, [(18, 21), (33, 6), (6, 6), (33, 33), (6, 33)]);
    add_traps(&mut layout, &context.catalog, &context.rules, &mut receipt).unwrap();
    assert_eq!(layout.traps.len(), 44);
    let original = layout.clone();
    add_teslas(&mut layout, &context.catalog, &context.rules, &mut receipt).unwrap();
    add_traps(&mut layout, &context.catalog, &context.rules, &mut receipt).unwrap();
    assert_eq!(layout, original);
    let account = obj([
        ("levels", obj([("th", num(16))])),
        ("hero_levels", obj([("Archer Queen", num(95))])),
        ("wall_level", num(16)),
    ]);
    assert!(apply_levels(&mut layout, &account, 18, &mut receipt).is_err());
    assert_eq!(layout, original);
    let mut other_th = layout.clone();
    other_th.town_hall = 18;
    assert!(apply_levels(&mut other_th, &account, 18, &mut receipt).is_err());
    let untyped_account = obj([
        ("levels", obj([("gm", num(16))])),
        ("hero_levels", obj([("Archer Queen", num(95))])),
        ("wall_level", num(16)),
    ]);
    assert!(apply_levels(&mut other_th, &untyped_account, 18, &mut receipt).is_err());
    assert!(other_th.setup.levels.is_empty());
    apply_levels(&mut layout, &account, 16, &mut receipt).unwrap();
    assert_eq!(
        context.admission(&layout, false).at("accepted"),
        &Json::Bool(true)
    );
    assert!(receipt
        .events
        .iter()
        .any(|e| e.at("evidence") == &string("imputed")));
    assert!(build(
        "unknown 1 1",
        Tiles::new(),
        "synthetic",
        16,
        &context.catalog,
        &mut receipt
    )
    .is_err());
    assert!(build(
        "th 1 1 nonsense",
        Tiles::new(),
        "synthetic",
        16,
        &context.catalog,
        &mut receipt
    )
    .is_err());
}

#[test]
fn structural_diff_ignores_object_order_but_records_each_change() {
    let a = obj([("x", num(1)), ("y", arr([num(2), num(3)]))]);
    let b = obj([("y", arr([num(2), num(4)])), ("x", num(1))]);
    let mut differences = Vec::new();
    replay::diff("$", &a, &b, &mut differences);
    assert_eq!(differences.len(), 1);
    assert_eq!(differences[0].at("path").str(), "$.y[1]");
    differences.clear();
    replay::diff(
        "$",
        &obj([("x", Json::Null)]),
        &obj(Vec::<(&str, Json)>::new()),
        &mut differences,
    );
    assert_eq!(differences.len(), 1);
    assert_eq!(differences[0].at("rebuilt_present"), &Json::Bool(false));
}

#[test]
fn compressed_png_fixtures_and_synthetic_lattice_known_answers() {
    for (bytes, size) in [
        (
            include_bytes!("testdata/synthetic-gradient.png").as_slice(),
            32,
        ),
        (
            include_bytes!("testdata/synthetic-gradient-dynamic.png").as_slice(),
            128,
        ),
    ] {
        let image = Image::from_png(bytes).unwrap();
        assert_eq!((image.width, image.height), (size, size));
        assert_eq!(image.get(0, 0), Some([255, 0, 0]));
        assert_eq!(image.get(0, size as i32 - 1), Some([0, 0, 255]));
        for row in image.pixels.chunks(size) {
            assert!(row.iter().all(|p| *p == row[0]));
        }
    }
    let grid = Grid {
        cx: 600.0,
        top: 40.0,
        a: 12.0,
        b: 9.0,
    };
    let mut points = Vec::new();
    for x in 0..30 {
        for y in 0..30 {
            let (sx, sy) = grid.project(f64::from(x) + 0.5, f64::from(y) + 0.5);
            points.push((sx, sy - 12.0));
        }
    }
    let (actual, strength) = lattice::fit(&points, grid, 12.0).unwrap();
    assert!((actual.cx - grid.cx).abs() < 1e-8);
    assert!((actual.top - grid.top).abs() < 1e-8);
    assert!((actual.a - grid.a).abs() < 1e-8);
    assert!((actual.b - grid.b).abs() < 1e-8);
    assert!((strength - 2.0).abs() < 1e-10);
}

#[test]
fn synthetic_seed_completion_preserves_traps_and_records_additions() {
    let context = context();
    let mut receipt = Receipt::default();
    let mut walls = Tiles::new();
    for (p, q) in [
        ((5, 5), (35, 5)),
        ((35, 5), (35, 35)),
        ((35, 35), (5, 35)),
        ((5, 35), (5, 5)),
    ] {
        walls.extend(walls::segment(p, q).unwrap());
    }
    let mut layout = build(
        "th 20 20\nT:bomb 10 10",
        walls,
        "declared synthetic seed",
        16,
        &context.catalog,
        &mut receipt,
    )
    .unwrap();
    let measured_trap = layout.traps[0].clone();
    completion::seed(
        &mut layout,
        &context.catalog,
        &context.rules,
        &[],
        &mut receipt,
    )
    .unwrap();
    assert_eq!(layout.walls.len(), 325);
    assert_eq!(layout.traps.len(), 44);
    assert_eq!(layout.traps[0], measured_trap);
    assert_eq!(
        context.admission(&layout, false).at("accepted"),
        &Json::Bool(true)
    );
    let count = receipt.events.len();
    completion::seed(
        &mut layout,
        &context.catalog,
        &context.rules,
        &[],
        &mut receipt,
    )
    .unwrap();
    assert!(receipt.events[count..]
        .iter()
        .all(|e| e.at("operation").str().contains("fallback")));
}

#[test]
fn cli_keeps_sources_and_rejects_unknown_flags() {
    let directory =
        std::env::temp_dir().join(format!("clash-digitize-contract-{}", std::process::id()));
    fs::create_dir_all(&directory).unwrap();
    let source = directory.join("source.txt");
    let output = directory.join("layout.json");
    let input = "th 10 10\n";
    fs::write(&source, input).unwrap();
    let args = vec![
        "build".to_owned(),
        "--buildings".to_owned(),
        source.display().to_string(),
        "--out".to_owned(),
        output.display().to_string(),
        "--th".to_owned(),
        "16".to_owned(),
    ];
    cli(&args).unwrap();
    assert_eq!(fs::read_to_string(&source).unwrap(), input);
    assert!(load_layout(&output).is_ok());
    assert!(sibling_receipt(&output).is_file());
    let mut overwrite = args.clone();
    overwrite[4] = source.display().to_string();
    assert!(cli(&overwrite).unwrap_err().contains("differ"));
    let mut typo = args;
    typo.extend(["--typo".to_owned(), "yes".to_owned()]);
    assert!(cli(&typo).unwrap_err().contains("unsupported --typo"));
    fs::remove_dir_all(directory).unwrap();
}
