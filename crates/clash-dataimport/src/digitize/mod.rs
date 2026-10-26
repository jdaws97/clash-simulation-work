//! Offline screenshot digitization with explicit measurement/imputation receipts.
//! See README.md in this directory for CLI contracts and port limitations.
pub mod buildings;
pub mod completion;
pub mod fit;
pub mod lattice;
pub mod pads;
pub mod presentation;
mod random;
pub mod replay;
pub mod walls;

use buildings::Receipt;
use clash_data::catalog::Catalog;
use clash_data::json::Json;
use clash_data::wire::{arr, num, obj, read, string, write};
use clash_layout::geometry::Tiles;
use clash_layout::model::{AdmissionPolicy, Layout, Tile};
use clash_layout::render::Image;
use clash_layout::rules::BaseRules;
use fit::Grid;
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;

pub const HELP: &str = "clash dataimport digitize <build|fit|refine|lattice|diagnostics|walls|trace|pads|snap|overlay|guide|crop|dewm|windows|gallery|convert|complete|finish|repair|impute|symmetry|merge|inventory|seed|inspect|ascii|diff|replay> [--key value]\n\
Common: --root DIR --out PATH; build: --buildings TXT --walls JSON --th N [--metadata JSON] [--draft yes];\n\
fit: --anchors JSON; refine: --grid JSON --points JSON [--center yes];\n\
walls/overlay: --image PNG/PPM --grid JSON [--layout JSON] [--mask legacy|pale|bright|gold|dark|cyan];\n\
complete/finish: --layout JSON [--levels JSON --levels-th N] [--top-up yes] [--replace-traps yes] [--tesla-radius N];\n\
trace: --walls JSON [--add JSON] [--delete JSON] [--gap N] [--buildings TXT];\n\
replay: --inputs DIR --references DIR --account JSON --account-th 16 --out DIR.\n\
Every layout output has a .receipt.json sibling. Existing input files are never overwritten.";

pub(crate) struct Context {
    pub catalog: Arc<Catalog>,
    pub rules: BaseRules,
}
impl Context {
    fn load(root: &Path) -> Result<Self, String> {
        Ok(Self {
            catalog: Arc::new(Catalog::load(&clash_data::catalog::path(root))?),
            rules: BaseRules::load(&root.join("data/generated/base_rules.json"))?,
        })
    }
    pub(crate) fn admission(&self, layout: &Layout, full: bool) -> Json {
        let policy = AdmissionPolicy {
            require_full: full,
            ..AdmissionPolicy::default()
        };
        match clash_layout::admit(layout.clone(), &self.rules, self.catalog.clone(), &policy) {
            Ok(admitted) => admitted.receipt(),
            Err(report) => report.to_json(),
        }
    }
}

struct Options {
    values: BTreeMap<String, String>,
}
impl Options {
    fn parse(args: &[String]) -> Result<Self, String> {
        let mut values = BTreeMap::new();
        for pair in args.chunks(2) {
            if pair.len() != 2 || !pair[0].starts_with("--") || pair[1].starts_with("--") {
                return Err(format!("expected --key value; {HELP}"));
            }
            if values
                .insert(pair[0][2..].to_owned(), pair[1].clone())
                .is_some()
            {
                return Err(format!("duplicate option {}", pair[0]));
            }
        }
        Ok(Self { values })
    }
    fn get(&self, key: &str) -> Option<&str> {
        self.values.get(key).map(String::as_str)
    }
    fn required(&self, key: &str) -> Result<&str, String> {
        self.get(key).ok_or_else(|| format!("missing --{key}"))
    }
    fn path(&self, key: &str) -> Result<&Path, String> {
        self.required(key).map(Path::new)
    }
    fn number<T: std::str::FromStr>(&self, key: &str, fallback: T) -> Result<T, String> {
        self.get(key)
            .map(|v| v.parse().map_err(|_| format!("invalid --{key}")))
            .unwrap_or(Ok(fallback))
    }
    fn yes(&self, key: &str) -> Result<bool, String> {
        match self.get(key) {
            None | Some("no") => Ok(false),
            Some("yes") => Ok(true),
            _ => Err(format!("--{key} must be yes or no")),
        }
    }
    fn validate(&self, command: &str) -> Result<(), String> {
        let specific = match command {
            "fit" => "anchors",
            "refine" => "grid points center",
            "lattice" | "diagnostics" => "image grid mask lift",
            "walls" => "image grid buildings lift mask bx by threshold min-run strong scores",
            "trace" => "walls buildings add delete gap",
            "pads" => "image grid buildings threshold",
            "snap" => "image grid layout",
            "build" => "buildings walls name th metadata full draft",
            "complete" => "layout levels levels-th top-up replace-traps tesla-radius full draft",
            "finish" => "layout levels levels-th top-up replace-traps full draft",
            "repair" | "merge" | "inventory" => "layout levels levels-th full draft",
            "impute" => "layout levels levels-th full draft hints",
            "symmetry" => "layout levels levels-th full draft pairs",
            "seed" => "layout levels levels-th full draft boxes",
            "overlay" => "image grid layout",
            "guide" => "layout",
            "crop" | "dewm" => "image x y width height zoom ruler alpha",
            "windows" => "image width height zoom stride-x stride-y",
            "gallery" => "images columns width height",
            "convert" => "grid windows raw margin",
            "inspect" => "layout full",
            "ascii" => "layout",
            "diff" => "before after",
            "replay" => "inputs references account account-th",
            _ => return Err(format!("unknown digitize command {command}; {HELP}")),
        };
        for key in self.values.keys() {
            if !matches!(key.as_str(), "root" | "out")
                && !specific.split_whitespace().any(|allowed| allowed == key)
            {
                return Err(format!("unsupported --{key} for digitize {command}"));
            }
        }
        Ok(())
    }
}

pub(crate) fn load_layout(path: &Path) -> Result<Layout, String> {
    // Some reviewed digitizers wrote notes as a list. Normalize only that legacy
    // representation; all content and placement checks still use clash-layout.
    let mut value = read(path)?;
    if let Some(Json::Arr(notes)) = value.get("notes") {
        let notes = notes
            .iter()
            .map(|v| {
                v.opt_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| clash_data::wire::encode(v))
            })
            .collect::<Vec<_>>()
            .join(" ");
        clash_data::wire::put(&mut value, "notes", string(notes));
    }
    Layout::from_json(&value).map_err(|r| clash_data::wire::encode(&r.to_json()))
}
pub(crate) fn parse_tiles(value: &Json) -> Result<Tiles, String> {
    let Json::Arr(rows) = value else {
        return Err("wall input must be a tile array".to_owned());
    };
    rows.iter().map(parse_tile).collect()
}
fn parse_tile(value: &Json) -> Result<Tile, String> {
    let Json::Arr(row) = value else {
        return Err("expected [x,y]".to_owned());
    };
    if row.len() != 2 {
        return Err("expected [x,y]".to_owned());
    }
    let coord = |v: &Json| match v {
        Json::Num(number)
            if number.is_finite() && number.fract() == 0.0 && (0.0..44.0).contains(number) =>
        {
            Ok(*number as i32)
        }
        _ => Err("tile must be an integer in 0..43".to_owned()),
    };
    Ok((coord(&row[0])?, coord(&row[1])?))
}
fn finite_pair(value: &Json) -> Result<(f64, f64), String> {
    let Json::Arr(row) = value else {
        return Err("expected numeric pair".to_owned());
    };
    if row.len() != 2 {
        return Err("expected numeric pair".to_owned());
    }
    let coord = |v: &Json| match v {
        Json::Num(number) if number.is_finite() => Ok(*number),
        _ => Err("expected finite numeric coordinate".to_owned()),
    };
    Ok((coord(&row[0])?, coord(&row[1])?))
}
fn list(value: &Json) -> Result<&[Json], String> {
    match value {
        Json::Arr(v) => Ok(v),
        _ => Err("expected JSON array".to_owned()),
    }
}
fn ensure_output(out: &Path, inputs: impl Iterator<Item = PathBuf>) -> Result<(), String> {
    if let Ok(out) = out.canonicalize() {
        for input in inputs {
            if input.canonicalize().is_ok_and(|input| input == out) {
                return Err("output must differ from every input".to_owned());
            }
        }
    }
    Ok(())
}
fn sibling_receipt(path: &Path) -> PathBuf {
    PathBuf::from(format!("{}.receipt.json", path.display()))
}
fn save_layout(
    out: &Path,
    layout: &Layout,
    receipt: &mut Receipt,
    context: &Context,
    full: bool,
    draft: bool,
) -> Result<(), String> {
    let admission = context.admission(layout, full);
    let accepted = admission.get("accepted") == Some(&Json::Bool(true));
    receipt.record(
        "validation",
        "clash-layout admission",
        Json::Null,
        admission,
    );
    write(&sibling_receipt(out), &receipt.to_json())?;
    if !accepted && !draft {
        return Err(format!(
            "layout rejected; review {} (use --draft yes to export measured partial/invalid data)",
            sibling_receipt(out).display()
        ));
    }
    write(out, &layout.to_json())
}

/// Entry point already wired by the integration-owned crate root.
pub fn cli(args: &[String]) -> Result<(), String> {
    let Some(command) = args.first().map(String::as_str) else {
        println!("{HELP}");
        return Ok(());
    };
    if matches!(command, "--help" | "help") {
        println!("{HELP}");
        return Ok(());
    }
    let options = Options::parse(&args[1..])?;
    options.validate(command)?;
    let root = options
        .get("root")
        .map(PathBuf::from)
        .unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."));
    let context = Context::load(&root)?;
    let out = options.path("out")?;
    ensure_output(
        out,
        options
            .values
            .iter()
            .filter(|(k, _)| !matches!(k.as_str(), "out" | "root"))
            .map(|(_, v)| PathBuf::from(v)),
    )?;
    ensure_output(
        &sibling_receipt(out),
        options.values.values().map(PathBuf::from),
    )?;
    if let Some(scores) = options.get("scores") {
        ensure_output(
            Path::new(scores),
            options
                .values
                .iter()
                .filter(|(key, _)| key.as_str() != "scores")
                .map(|(_, value)| PathBuf::from(value)),
        )?;
        if Path::new(scores) == out {
            return Err("scores and output must differ".to_owned());
        }
    }
    if matches!(command, "windows" | "replay") {
        if let Ok(directory) = out.canonicalize() {
            if options
                .values
                .iter()
                .filter(|(key, _)| key.as_str() != "out")
                .filter_map(|(_, value)| Path::new(value).canonicalize().ok())
                .any(|input| input.starts_with(&directory))
            {
                return Err("output directory must not contain an input".to_owned());
            }
        }
    }
    let mut receipt = Receipt::default();
    let input_keys = [
        "anchors",
        "grid",
        "points",
        "image",
        "buildings",
        "walls",
        "layout",
        "metadata",
        "levels",
        "hints",
        "pairs",
        "boxes",
        "add",
        "delete",
        "images",
        "raw",
        "windows",
        "before",
        "after",
        "account",
    ];
    for key in input_keys {
        if let Some(path) = options.get(key).map(Path::new).filter(|p| p.is_file()) {
            let bytes = fs::read(path).map_err(|e| format!("{}: {e}", path.display()))?;
            receipt.record(
                "source",
                &format!("explicit --{key} input"),
                Json::Null,
                obj([
                    ("path", string(path.display().to_string())),
                    ("identity", string(clash_layout::json::identity(&bytes))),
                ]),
            );
            let parent = sibling_receipt(path);
            if parent.is_file() {
                receipt.record(
                    "inherited provenance",
                    "parent digitization receipt",
                    Json::Null,
                    read(&parent)?,
                );
            }
        }
    }
    match command {
        "fit" => {
            let value = read(options.path("anchors")?)?;
            let anchors = list(&value)?
                .iter()
                .map(|v| {
                    let tile = finite_pair(v.get("tile").ok_or("anchor missing tile")?)?;
                    let screen = finite_pair(v.get("screen").ok_or("anchor missing screen")?)?;
                    Ok(fit::Anchor { tile, screen })
                })
                .collect::<Result<Vec<_>, String>>()?;
            let (grid, rms) = Grid::fit(&anchors)?;
            write(out, &grid.to_json())?;
            receipt.record(
                "measured",
                "least squares grid fit, RMS pixels",
                value,
                num(rms),
            );
        }
        "refine" => {
            let grid = Grid::from_json(&read(options.path("grid")?)?)?;
            let points = list(&read(options.path("points")?)?)?
                .iter()
                .map(finite_pair)
                .collect::<Result<Vec<_>, _>>()?;
            let (refined, residual) = grid.refine(&points, options.yes("center")?)?;
            write(out, &refined.to_json())?;
            receipt.record(
                "measured",
                "local lattice refinement; phase supplied by user",
                grid.to_json(),
                obj([
                    ("grid", refined.to_json()),
                    ("RMS_clipped_tiles", num(residual)),
                ]),
            );
        }
        "lattice" | "diagnostics" => {
            let image = Image::load(options.path("image")?)?;
            let grid = Grid::from_json(&read(options.path("grid")?)?)?;
            let mask = walls::Mask::parse(options.get("mask").unwrap_or("bright"))?;
            let points = lattice::mask_points(&image, mask);
            if command == "lattice" {
                let (fitted, strength) =
                    lattice::fit(&points, grid, options.number("lift", 12.0)?)?;
                write(out, &fitted.to_json())?;
                receipt.record(
                    "measured",
                    "mask-line harmonic lattice fit; origin phase from explicit initial grid",
                    grid.to_json(),
                    obj([("grid", fitted.to_json()), ("strength", num(strength))]),
                );
            } else {
                write(out, &lattice::diagnostics(&points, grid))?;
            }
        }
        "walls" => {
            let image = Image::load(options.path("image")?)?;
            let grid = Grid::from_json(&read(options.path("grid")?)?)?;
            let occupied = text_occupancy(&options, &context, &mut receipt)?;
            let lift: f64 = options.number("lift", 12.0)?;
            if !lift.is_finite() {
                return Err("lift must be finite".to_owned());
            }
            let mask = options.get("mask").unwrap_or("legacy");
            let tiles = if mask == "legacy" {
                walls::detect(&image, grid, lift, &occupied)
            } else {
                let scores = walls::scores(
                    &image,
                    grid,
                    lift,
                    walls::Mask::parse(mask)?,
                    options.number("bx", 0.3)?,
                    options.number("by", 0.7)?,
                );
                let threshold: f64 = options.number("threshold", 0.5)?;
                if !(0.0..=1.0).contains(&threshold) {
                    return Err("threshold must be in 0..1".to_owned());
                }
                if let Some(path) = options.get("scores") {
                    write(
                        Path::new(path),
                        &Json::Obj(
                            scores
                                .iter()
                                .map(|(&(x, y), &s)| (format!("{x},{y}"), num(s)))
                                .collect(),
                        ),
                    )?;
                }
                walls::threshold(
                    &scores,
                    &occupied,
                    threshold,
                    options.number("min-run", 2)?,
                    options.number("strong", 9.0)?,
                )
            };
            write(out, &buildings::tiles_json(&tiles))?;
            receipt.record(
                "measured",
                "automatic wall candidates; require visual review",
                grid.to_json(),
                buildings::tiles_json(&tiles),
            );
        }
        "pads" | "snap" => {
            let image = Image::load(options.path("image")?)?;
            let grid = Grid::from_json(&read(options.path("grid")?)?)?;
            let pads = pads::CyanPads::new(&image, grid);
            let result = if command == "pads" {
                pads.proposals(
                    &text_occupancy(&options, &context, &mut receipt)?,
                    options.number("threshold", 0.55)?,
                )
            } else {
                let layout = load_layout(options.path("layout")?)?;
                let mut result = Vec::new();
                for building in &layout.buildings {
                    let size = buildings::size(&context.catalog, &building.key)?;
                    let current = pads.score(building.position, size);
                    let (position, score) = pads.snap(building.position, size);
                    result.push(obj([
                        ("id", string(&building.id)),
                        ("current", buildings::tile_json(building.position)),
                        ("proposed", buildings::tile_json(position)),
                        ("current_score", num(current)),
                        ("score", num(score)),
                        (
                            "recommend",
                            Json::Bool(score > current + 0.25 && score > 0.6),
                        ),
                    ]));
                }
                arr(result)
            };
            write(out, &result)?;
            receipt.record(
                "proposal",
                "cyan footprint scores require manual identity/position review",
                Json::Null,
                result,
            );
        }
        "trace" => {
            let mut tiles = parse_tiles(&read(options.path("walls")?)?)?;
            let before = tiles.clone();
            let occupied = text_occupancy(&options, &context, &mut receipt)?;
            if let Some(path) = options.get("add") {
                tiles.extend(read_segments(Path::new(path))?);
            }
            if let Some(path) = options.get("delete") {
                for p in read_segments(Path::new(path))? {
                    tiles.remove(&p);
                }
            }
            if let Some(gap) = options.get("gap") {
                let gap = gap.parse::<i32>().map_err(|_| "invalid gap")?;
                let added = walls::fill_gaps(&mut tiles, &occupied, gap);
                receipt.record(
                    "imputed",
                    "straight wall gap fill",
                    Json::Null,
                    buildings::tiles_json(&added),
                );
            }
            if !tiles.is_disjoint(&occupied) {
                return Err("wall edits conflict with building footprints".to_owned());
            }
            receipt.record(
                "manually corrected",
                "wall segment edits",
                buildings::tiles_json(&before),
                buildings::tiles_json(&tiles),
            );
            write(out, &buildings::tiles_json(&tiles))?;
        }
        "build" => {
            let text = fs::read_to_string(options.path("buildings")?).map_err(|e| e.to_string())?;
            let walls = options
                .get("walls")
                .map(|v| read(Path::new(v)).and_then(|v| parse_tiles(&v)))
                .transpose()?
                .unwrap_or_default();
            let th = options.number("th", 16)?;
            let mut layout = buildings::build(
                &text,
                walls,
                options.get("name").unwrap_or("digitized"),
                th,
                &context.catalog,
                &mut receipt,
            )?;
            if let Some(path) = options.get("metadata") {
                let source = load_layout(Path::new(path))?;
                if source.town_hall != th {
                    return Err("metadata Town Hall differs from --th".to_owned());
                }
                layout.setup = source.setup;
                layout.notes = source.notes;
                receipt.record(
                    "measured",
                    "metadata from explicit reviewed source",
                    Json::Null,
                    string(path),
                );
            }
            save_layout(
                out,
                &layout,
                &mut receipt,
                &context,
                options.yes("full")?,
                options.yes("draft")?,
            )?;
            return Ok(());
        }
        "complete" | "finish" | "repair" | "impute" | "symmetry" | "seed" | "merge"
        | "inventory" => {
            let source_path = options.path("layout")?;
            let mut layout = load_layout(source_path)?;
            receipt.record(
                "measured",
                "source physical identity",
                Json::Null,
                string(clash_layout::json::identity(
                    &fs::read(source_path).map_err(|e| e.to_string())?,
                )),
            );
            match command {
                "impute" => impute_hints(
                    &mut layout,
                    &read(options.path("hints")?)?,
                    &context,
                    &mut receipt,
                )?,
                "symmetry" => apply_symmetry(
                    &mut layout,
                    &read(options.path("pairs")?)?,
                    &context,
                    &mut receipt,
                )?,
                "merge" => {
                    completion::merge(&mut layout, &context.catalog, &context.rules, &mut receipt)?
                }
                "inventory" => completion::inventory(
                    &mut layout,
                    &context.catalog,
                    &context.rules,
                    &mut receipt,
                )?,
                "seed" => {
                    let mut boxes = Vec::new();
                    if let Some(path) = options.get("boxes") {
                        for row in list(&read(Path::new(path))?)? {
                            let keys = list(row.get("keys").ok_or("box missing keys")?)?
                                .iter()
                                .map(|v| {
                                    v.opt_str()
                                        .map(str::to_owned)
                                        .ok_or("box key must be a string".to_owned())
                                })
                                .collect::<Result<_, _>>()?;
                            let lo = parse_tile(row.get("lo").ok_or("box missing lo")?)?;
                            let hi = parse_tile(row.get("hi").ok_or("box missing hi")?)?;
                            if lo.0 > hi.0 || lo.1 > hi.1 {
                                return Err("box lower bound exceeds upper bound".to_owned());
                            }
                            boxes.push(completion::TrapBox { keys, lo, hi });
                        }
                    }
                    completion::seed(
                        &mut layout,
                        &context.catalog,
                        &context.rules,
                        &boxes,
                        &mut receipt,
                    )?;
                }
                _ => {
                    if options.yes("replace-traps")? {
                        receipt.record(
                            "imputed",
                            "explicit replacement of source traps",
                            layout.to_json().at("traps").clone(),
                            arr([]),
                        );
                        layout.traps.clear();
                    }
                    if command == "complete" {
                        if let Some(radius) = options.get("tesla-radius") {
                            buildings::add_teslas_near_th(
                                &mut layout,
                                &context.catalog,
                                &context.rules,
                                &mut receipt,
                                radius.parse().map_err(|_| "invalid Tesla radius")?,
                            )?;
                        } else {
                            buildings::add_teslas(
                                &mut layout,
                                &context.catalog,
                                &context.rules,
                                &mut receipt,
                            )?;
                        }
                    }
                    buildings::repair(&mut layout, &context.catalog, &mut receipt)?;
                    if command != "repair" {
                        buildings::add_traps(
                            &mut layout,
                            &context.catalog,
                            &context.rules,
                            &mut receipt,
                        )?;
                        if options.yes("top-up")? {
                            buildings::top_up_walls(
                                &mut layout,
                                &context.catalog,
                                &context.rules,
                                &mut receipt,
                            )?;
                        }
                    }
                }
            }
            if let Some(account) = options.get("levels") {
                let th = options
                    .required("levels-th")?
                    .parse()
                    .map_err(|_| "invalid --levels-th")?;
                buildings::apply_levels(&mut layout, &read(Path::new(account))?, th, &mut receipt)?;
            }
            layout.notes.push_str(" Native digitizer completion/corrections are assumptions recorded in the accompanying receipt.");
            save_layout(
                out,
                &layout,
                &mut receipt,
                &context,
                options.yes("full")?,
                options.yes("draft")?,
            )?;
            return Ok(());
        }
        "overlay" | "guide" => {
            let layout = options
                .get("layout")
                .map(|p| load_layout(Path::new(p)))
                .transpose()?;
            let image = if command == "guide" {
                presentation::guide(
                    layout.as_ref().ok_or("guide requires --layout")?,
                    &context.catalog,
                )?
            } else {
                let image = Image::load(options.path("image")?)?;
                let grid = Grid::from_json(&read(options.path("grid")?)?)?;
                presentation::overlay(&image, grid, layout.as_ref(), &context.catalog)?
            };
            image.save(out)?;
        }
        "crop" | "dewm" => {
            let image = Image::load(options.path("image")?)?;
            let (x, y, zoom) = (
                options.number("x", 0)?,
                options.number("y", 0)?,
                options.number("zoom", 1)?,
            );
            let cropped = image.crop(
                x,
                y,
                options.number("width", image.width)?,
                options.number("height", image.height)?,
                1,
            )?;
            let transformed = if command == "dewm" {
                let alpha = options.number("alpha", 0.4)?;
                receipt.record(
                    "inspection transform",
                    "inverse white overlay, sigma=3, clamped image boundaries",
                    Json::Null,
                    num(alpha),
                );
                presentation::undo_white_overlay(&cropped, alpha)?
            } else {
                cropped
            };
            let mut scaled = transformed.crop(0, 0, transformed.width, transformed.height, zoom)?;
            if let Some(step) = options.get("ruler") {
                presentation::ruler(
                    &mut scaled,
                    (x, y),
                    zoom,
                    step.parse().map_err(|_| "invalid ruler step")?,
                )?;
            }
            scaled.save(out)?;
        }
        "windows" => {
            let image = Image::load(options.path("image")?)?;
            let width: usize = options.number("width", 600)?;
            let height: usize = options.number("height", 400)?;
            let zoom: usize = options.number("zoom", 2)?;
            let stride_x: usize = options.number("stride-x", width * 3 / 4)?;
            let stride_y: usize = options.number("stride-y", height * 3 / 4)?;
            if width == 0 || height == 0 || stride_x == 0 || stride_y == 0 {
                return Err("window dimensions and strides must be positive".to_owned());
            }
            fs::create_dir_all(out).map_err(|e| e.to_string())?;
            let mut windows = Vec::new();
            for y in (0..image.height).step_by(stride_y) {
                for x in (0..image.width).step_by(stride_x) {
                    let name = format!("w{}", windows.len());
                    image
                        .crop(
                            x,
                            y,
                            width.min(image.width - x),
                            height.min(image.height - y),
                            zoom,
                        )?
                        .save(&out.join(format!("{name}.png")))?;
                    windows.push((name, arr([num(x as i32), num(y as i32), num(zoom as i32)])));
                }
            }
            write(&out.join("windows.json"), &Json::Obj(windows))?;
        }
        "gallery" => {
            let paths = read(options.path("images")?)?;
            let paths = list(&paths)?
                .iter()
                .map(|value| match value {
                    Json::Str(path) => Ok(PathBuf::from(path)),
                    _ => Err("image path must be a string".to_owned()),
                })
                .collect::<Result<Vec<_>, _>>()?;
            ensure_output(out, paths.iter().cloned())?;
            ensure_output(&sibling_receipt(out), paths.iter().cloned())?;
            let images = paths
                .iter()
                .map(|path| Image::load(path))
                .collect::<Result<Vec<_>, _>>()?;
            presentation::gallery(
                &images,
                options.number("columns", 3)?,
                options.number("width", 480)?,
                options.number("height", 360)?,
            )?
            .save(out)?;
        }
        "convert" => convert(&options, &context, &mut receipt)?,
        "inspect" | "ascii" => {
            let layout = load_layout(options.path("layout")?)?;
            if command == "ascii" {
                fs::write(out, presentation::ascii(&layout, &context.catalog)?)
                    .map_err(|e| e.to_string())?;
            } else {
                write(
                    out,
                    &obj([
                        (
                            "admission",
                            context.admission(&layout, options.yes("full")?),
                        ),
                        ("missing", missing_inventory(&layout, &context)),
                        ("buildings", num(layout.buildings.len() as i32)),
                        ("walls", num(layout.walls.len() as i32)),
                        ("traps", num(layout.traps.len() as i32)),
                    ]),
                )?;
            }
        }
        "diff" => {
            let before = read(options.path("before")?)?;
            let after = read(options.path("after")?)?;
            let mut differences = Vec::new();
            replay::diff("$", &before, &after, &mut differences);
            write(out, &arr(differences))?;
        }
        "replay" => {
            return replay::run(
                options.path("inputs")?,
                options.path("references")?,
                options.path("account")?,
                options
                    .required("account-th")?
                    .parse()
                    .map_err(|_| "invalid --account-th")?,
                out,
                &context,
            )
        }
        _ => return Err(format!("unknown digitize command {command}; {HELP}")),
    }
    write(&sibling_receipt(out), &receipt.to_json())
}

fn text_occupancy(
    options: &Options,
    context: &Context,
    receipt: &mut Receipt,
) -> Result<Tiles, String> {
    if let Some(path) = options.get("buildings") {
        let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
        let layout = buildings::build(
            &text,
            Tiles::new(),
            "occupancy",
            16,
            &context.catalog,
            receipt,
        )?;
        buildings::occupied(&layout, &context.catalog, false)
    } else {
        Ok(Tiles::new())
    }
}
fn read_segments(path: &Path) -> Result<Tiles, String> {
    let value = read(path)?;
    let mut result = Tiles::new();
    for row in list(&value)? {
        let points = list(row)?;
        if points.len() != 2 {
            return Err("segments must be [[x0,y0],[x1,y1]]".to_owned());
        }
        result.extend(walls::segment(
            parse_tile(&points[0])?,
            parse_tile(&points[1])?,
        )?);
    }
    Ok(result)
}
fn missing_inventory(layout: &Layout, context: &Context) -> Json {
    let Some(rules) = context.rules.town_halls.get(&layout.town_hall) else {
        return Json::Null;
    };
    Json::Obj(
        rules
            .buildings
            .iter()
            .filter_map(|(key, &wanted)| {
                let have = layout.buildings.iter().filter(|b| &b.key == key).count();
                (have < wanted).then(|| (key.clone(), num((wanted - have) as i32)))
            })
            .collect(),
    )
}

fn impute_hints(
    layout: &mut Layout,
    hints: &Json,
    context: &Context,
    receipt: &mut Receipt,
) -> Result<(), String> {
    let mut occupied = buildings::occupied(layout, &context.catalog, true)?;
    for hint in list(hints)? {
        let key = hint
            .get("key")
            .and_then(Json::opt_str)
            .ok_or("hint needs key")?;
        let (hx, hy) = finite_pair(hint.get("center").ok_or("hint needs center")?)?;
        let size = buildings::size(&context.catalog, key)?;
        let mut best = None;
        let mut best_distance = f64::INFINITY;
        for x in 0..=44 - size {
            for y in 0..=44 - size {
                if !buildings::footprint((x, y), size).is_disjoint(&occupied) {
                    continue;
                }
                let distance = (f64::from(x) + f64::from(size) / 2.0 - hx)
                    .hypot(f64::from(y) + f64::from(size) / 2.0 - hy);
                if distance < best_distance {
                    best = Some((x, y));
                    best_distance = distance;
                }
            }
        }
        let position = best.ok_or("no free building imputation position")?;
        let mode = hint
            .get("mode")
            .and_then(Json::opt_str)
            .map(|v| clash_layout::model::Mode::parse(v).ok_or("unknown hint mode"))
            .transpose()?;
        let mut id = format!("imputed{}", layout.buildings.len());
        while layout.buildings.iter().any(|b| b.id == id) {
            id.push('_');
        }
        layout
            .buildings
            .push(clash_layout::model::BuildingPlacement {
                id,
                key: key.to_owned(),
                position,
                mode,
            });
        occupied.extend(buildings::footprint(position, size));
        receipt.record(
            "imputed",
            "nearest free footprint to explicit hint",
            hint.clone(),
            buildings::tile_json(position),
        );
    }
    Ok(())
}
fn apply_symmetry(
    layout: &mut Layout,
    pairs: &Json,
    context: &Context,
    receipt: &mut Receipt,
) -> Result<(), String> {
    for pair in list(pairs)? {
        let indices = list(pair)?;
        if indices.len() != 2 {
            return Err("symmetry pairs require two building indices".to_owned());
        }
        let index = |value: &Json| match value {
            Json::Num(number)
                if number.is_finite()
                    && number.fract() == 0.0
                    && *number >= 0.0
                    && *number < layout.buildings.len() as f64 =>
            {
                Ok(*number as usize)
            }
            _ => Err("invalid symmetry building index"),
        };
        let (a, b) = (index(&indices[0])?, index(&indices[1])?);
        if a == b || layout.buildings[a].key != layout.buildings[b].key {
            return Err("symmetry requires distinct same-key buildings".to_owned());
        }
        let (p, q) = (layout.buildings[a].position, layout.buildings[b].position);
        let x = (f64::from(p.0 + q.1) / 2.0).round_ties_even() as i32;
        let y = (f64::from(p.1 + q.0) / 2.0).round_ties_even() as i32;
        receipt.record(
            "imputed",
            "explicit x/y symmetry assumption",
            arr([buildings::tile_json(p), buildings::tile_json(q)]),
            arr([buildings::tile_json((x, y)), buildings::tile_json((y, x))]),
        );
        layout.buildings[a].position = (x, y);
        layout.buildings[b].position = (y, x);
    }
    // Admission below checks all bounds/overlaps; symmetry never silently nudges.
    buildings::occupied(layout, &context.catalog, true)?;
    Ok(())
}
fn convert(options: &Options, context: &Context, receipt: &mut Receipt) -> Result<(), String> {
    let grid = Grid::from_json(&read(options.path("grid")?)?)?;
    let windows = options
        .get("windows")
        .map(|p| read(Path::new(p)))
        .transpose()?
        .unwrap_or_else(|| obj(Vec::<(&str, Json)>::new()));
    let text = fs::read_to_string(options.path("raw")?).map_err(|e| e.to_string())?;
    let mut result = String::new();
    for (line_number, line) in text.lines().enumerate() {
        let (body, note) = line.split_once('#').unwrap_or((line, ""));
        let parts: Vec<_> = body.split_whitespace().collect();
        if parts.is_empty() {
            continue;
        }
        if !(4..=5).contains(&parts.len()) {
            return Err(format!(
                "raw line {}: expected window key x y [mode]",
                line_number + 1
            ));
        }
        let (window, key) = (parts[0], parts[1]);
        let size = buildings::size(&context.catalog, key)?;
        let px = parts[2].parse::<f64>().map_err(|_| "invalid raw x")?;
        let py = parts[3].parse::<f64>().map_err(|_| "invalid raw y")?;
        if !px.is_finite() || !py.is_finite() {
            return Err("nonfinite raw coordinate".to_owned());
        }
        let position = if window == "abs" {
            parse_tile(&arr([num(px), num(py)]))?
        } else {
            let (sx, sy) = if window == "orig" {
                (px, py)
            } else {
                let row = list(
                    windows
                        .get(window)
                        .ok_or_else(|| format!("unknown window {window}"))?,
                )?;
                if row.len() != 3 {
                    return Err("window must be [origin_x,origin_y,zoom]".to_owned());
                }
                let (ox, oy) = finite_pair(&arr([row[0].clone(), row[1].clone()]))?;
                let zoom = match row[2] {
                    Json::Num(number) if number.is_finite() && number > 0.0 => number,
                    _ => return Err("invalid window zoom".to_owned()),
                };
                (ox + px / zoom, oy + py / zoom)
            };
            let margin = options.number("margin", 0.45)? + if key == "camp" { 0.3 } else { 0.0 };
            grid.bottom_tip(sx, sy, size, margin)
        };
        let mode = parts.get(4).map(|m| format!(" {m}")).unwrap_or_default();
        result.push_str(&format!(
            "{key} {} {}{mode}  # {window} {}\n",
            position.0,
            position.1,
            note.trim()
        ));
        receipt.record(
            "measured",
            "window/bottom-tip conversion with explicit grid",
            string(line),
            buildings::tile_json(position),
        );
    }
    fs::write(options.path("out")?, result).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests;
