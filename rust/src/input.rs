use std::fs;
use std::path::Path;
use std::str::{FromStr, SplitWhitespace};

#[derive(Clone, Debug)]
pub struct Input {
    pub dt: f64,
    pub max_time: f64,
    pub world: usize,
    pub units: Vec<UnitSpec>,
    pub buildings: Vec<BuildingSpec>,
    pub walls: Vec<WallSpec>,
    pub scenarios: Vec<Scenario>,
}

#[derive(Clone, Debug)]
pub struct UnitSpec {
    pub name: String,
    pub hp: f64,
    pub damage: f64,
    pub interval: f64,
    pub range: f64,
    pub speed: f64,
    pub housing: usize,
    pub flying: bool,
    pub hits_air: bool,
    pub hits_ground: bool,
    pub splash: f64,
    pub windup_delay: f64,
}

#[derive(Clone, Debug)]
pub struct BuildingSpec {
    pub id: usize,
    pub key: String,
    pub cx: f64,
    pub cy: f64,
    pub half_hit: f64,
    pub hp: f64,
    pub size: i32,
    pub counted: bool,
    pub weapon: Option<WeaponSpec>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WeaponKind {
    Single,
    Splash,
    Mortar,
    Inferno,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Targets {
    Air,
    Ground,
    Both,
}

#[derive(Clone, Debug)]
pub struct WeaponSpec {
    pub kind: WeaponKind,
    pub targets: Targets,
    pub range: f64,
    pub min_range: f64,
    pub interval: f64,
    pub damage: f64,
    pub ammo: Option<usize>,
    pub proj_speed: f64,
    pub splash: f64,
    pub flight: f64,
    pub falloff: bool,
    pub same_type: bool,
    pub ramp: [(f64, f64); 3],
}

#[derive(Clone, Debug)]
pub struct WallSpec {
    pub tx: i32,
    pub ty: i32,
    pub hp: f64,
}

#[derive(Clone, Debug)]
pub struct Scenario {
    pub idx: usize,
    pub angle: f64,
    pub seed: u64,
    pub drops: Vec<Drop>,
}

#[derive(Clone, Debug)]
pub struct Drop {
    pub tick: usize,
    pub name: String,
    pub x: f64,
    pub y: f64,
}

pub fn load(path: &Path) -> Result<Input, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("cannot read {}: {error}", path.display()))?;
    parse(&text).map_err(|error| format!("{}: {error}", path.display()))
}

pub fn parse(text: &str) -> Result<Input, String> {
    let mut dt = None;
    let mut max_time = None;
    let mut world = None;
    let mut units = Vec::new();
    let mut buildings = Vec::new();
    let mut walls = Vec::new();
    let mut scenarios = Vec::new();
    let mut lines = text
        .lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty());

    while let Some((line_index, line)) = lines.next() {
        let mut record = Record::new(line_index + 1, line);
        match record.text("record type")? {
            "dt" => dt = Some(record.float("dt")?),
            "max_time" => max_time = Some(record.float("max_time")?),
            "world" => world = Some(record.integer("world")?),
            "unit" => units.push(UnitSpec {
                name: record.text("name")?.to_owned(),
                hp: record.float("hp")?,
                damage: record.float("damage")?,
                interval: record.float("interval")?,
                range: record.float("range")?,
                speed: record.float("speed")?,
                housing: record.integer("housing")?,
                flying: record.flag("flying")?,
                hits_air: record.flag("hits_air")?,
                hits_ground: record.flag("hits_ground")?,
                splash: record.float("splash")?,
                windup_delay: record.float("windup_delay")?,
            }),
            "building" => buildings.push(parse_building(&mut record)?),
            "wall" => walls.push(WallSpec {
                tx: record.integer("tx")?,
                ty: record.integer("ty")?,
                hp: record.float("hp")?,
            }),
            "scenario" => {
                let idx = record.integer("idx")?;
                let angle = record.float("angle")?;
                let seed = record.integer("seed")?;
                let count: usize = record.integer("ndrops")?;
                let mut drops = Vec::new();
                for _ in 0..count {
                    let (drop_index, drop_line) = lines.next().ok_or_else(|| {
                        record.error(&format!("expected {count} drops for scenario {idx}"))
                    })?;
                    let mut drop = Record::new(drop_index + 1, drop_line);
                    if drop.text("record type")? != "drop" {
                        return Err(drop.error("expected a drop record"));
                    }
                    drops.push(Drop {
                        tick: drop.integer("tick")?,
                        name: drop.text("name")?.to_owned(),
                        x: drop.float("x")?,
                        y: drop.float("y")?,
                    });
                    drop.finish()?;
                }
                // battle.py:902-904: retain file order for deployments on the same tick.
                drops.sort_by_key(|drop| drop.tick);
                scenarios.push(Scenario {
                    idx,
                    angle,
                    seed,
                    drops,
                });
            }
            kind => return Err(record.error(&format!("unknown record type {kind:?}"))),
        }
        record.finish()?;
    }

    // Building and wall vectors preserve Python list/dictionary iteration order.
    Ok(Input {
        dt: dt.ok_or("missing dt record")?,
        max_time: max_time.ok_or("missing max_time record")?,
        world: world.ok_or("missing world record")?,
        units,
        buildings,
        walls,
        scenarios,
    })
}

fn parse_building(record: &mut Record<'_>) -> Result<BuildingSpec, String> {
    let id = record.integer("id")?;
    let key = record.text("key")?.to_owned();
    let cx = record.float("cx")?;
    let cy = record.float("cy")?;
    let half_hit = record.float("half_hit")?;
    let hp = record.float("hp")?;
    let size = record.integer("size")?;
    let counted = record.flag("counted")?;
    let kind = match record.text("kind")? {
        "none" => None,
        "single" => Some(WeaponKind::Single),
        "splash" => Some(WeaponKind::Splash),
        "mortar" => Some(WeaponKind::Mortar),
        "inferno" => Some(WeaponKind::Inferno),
        other => return Err(record.error(&format!("unsupported weapon kind {other:?}"))),
    };
    let weapon = if let Some(kind) = kind {
        let targets = match record.text("targets")? {
            "air" => Targets::Air,
            "ground" => Targets::Ground,
            "both" => Targets::Both,
            other => return Err(record.error(&format!("unsupported targets {other:?}"))),
        };
        let range = record.float("range")?;
        let min_range = record.float("min_range")?;
        let interval = record.float("interval")?;
        let damage = record.float("damage")?;
        let raw_ammo: i64 = record.integer("ammo")?;
        let ammo = match raw_ammo {
            -1 => None,
            0.. => Some(raw_ammo as usize),
            _ => return Err(record.error("ammo must be -1 or nonnegative")),
        };
        Some(WeaponSpec {
            kind,
            targets,
            range,
            min_range,
            interval,
            damage,
            ammo,
            proj_speed: record.float("proj_speed")?,
            splash: record.float("splash")?,
            flight: record.float("flight")?,
            falloff: record.flag("falloff")?,
            same_type: record.flag("same_type")?,
            ramp: [
                (record.float("ramp_t0")?, record.float("ramp_v0")?),
                (record.float("ramp_t1")?, record.float("ramp_v1")?),
                (record.float("ramp_t2")?, record.float("ramp_v2")?),
            ],
        })
    } else {
        None
    };
    Ok(BuildingSpec {
        id,
        key,
        cx,
        cy,
        half_hit,
        hp,
        size,
        counted,
        weapon,
    })
}

struct Record<'a> {
    line: usize,
    fields: SplitWhitespace<'a>,
}

impl<'a> Record<'a> {
    fn new(line: usize, text: &'a str) -> Self {
        Self {
            line,
            fields: text.split_whitespace(),
        }
    }

    fn text(&mut self, name: &str) -> Result<&'a str, String> {
        self.fields
            .next()
            .ok_or_else(|| self.error(&format!("missing {name}")))
    }

    fn float(&mut self, name: &str) -> Result<f64, String> {
        let text = self.text(name)?;
        let value = text
            .parse::<f64>()
            .map_err(|_| self.error(&format!("invalid {name}: {text:?}")))?;
        if !value.is_finite() {
            return Err(self.error(&format!("{name} must be finite")));
        }
        Ok(value)
    }

    fn integer<T: FromStr>(&mut self, name: &str) -> Result<T, String> {
        let text = self.text(name)?;
        text.parse::<T>()
            .map_err(|_| self.error(&format!("invalid {name}: {text:?}")))
    }

    fn flag(&mut self, name: &str) -> Result<bool, String> {
        match self.text(name)? {
            "0" => Ok(false),
            "1" => Ok(true),
            other => Err(self.error(&format!("{name} must be 0 or 1, got {other:?}"))),
        }
    }

    fn finish(&mut self) -> Result<(), String> {
        if let Some(extra) = self.fields.next() {
            return Err(self.error(&format!("unexpected field {extra:?}")));
        }
        Ok(())
    }

    fn error(&self, message: &str) -> String {
        format!("line {}: {message}", self.line)
    }
}
