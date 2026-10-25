//! Ports rust_export.py:40-41,225-256: exact tick records and Python event JSON.

pub use crate::float::py_float_repr;
use std::fmt::Write as FmtWrite;
use std::io::{self, Write};

use crate::state::{Battle, EntityRef, Value};

// json.rs intentionally reads every number as f64. Events need an explicit
// distinction: json.dumps([1, 1.0]) must remain "[1, 1.0]".
#[derive(Clone, Debug)]
pub enum LogValue {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    String(String),
    List(Vec<LogValue>),
    Map(Vec<(String, LogValue)>),
}

impl From<&str> for LogValue {
    fn from(value: &str) -> Self {
        Self::String(value.to_owned())
    }
}

impl From<String> for LogValue {
    fn from(value: String) -> Self {
        Self::String(value)
    }
}

impl From<f64> for LogValue {
    fn from(value: f64) -> Self {
        Self::Float(value)
    }
}

impl From<i64> for LogValue {
    fn from(value: i64) -> Self {
        Self::Int(value)
    }
}

// battle.py:514,886,955: fixed precision formats the exact binary value with
// half-even rounding, then one correctly rounded decimal-to-binary conversion.
pub fn round_decimal(value: f64, digits: usize) -> f64 {
    if !value.is_finite() {
        return value;
    }
    format!("{value:.digits$}")
        .parse()
        .expect("rounded decimal float")
}

fn string_json(value: &str, out: &mut String) {
    out.push('"');
    // json.dumps defaults: ensure_ascii=True; escapes use lowercase hex and
    // astral code points become UTF-16 surrogate pairs.
    for c in value.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            ' '..='~' => out.push(c),
            _ => {
                let mut buffer = [0_u16; 2];
                for code in c.encode_utf16(&mut buffer) {
                    write!(out, "\\u{code:04x}").expect("write to string");
                }
            }
        }
    }
    out.push('"');
}

fn value_json(value: &LogValue, out: &mut String) {
    match value {
        LogValue::Null => out.push_str("null"),
        LogValue::Bool(value) => out.push_str(if *value { "true" } else { "false" }),
        LogValue::Int(value) => write!(out, "{value}").expect("write to string"),
        LogValue::Float(value) => {
            if value.is_nan() {
                out.push_str("NaN");
            } else if value.is_infinite() {
                out.push_str(if value.is_sign_negative() {
                    "-Infinity"
                } else {
                    "Infinity"
                });
            } else {
                out.push_str(&py_float_repr(*value));
            }
        }
        LogValue::String(value) => string_json(value, out),
        LogValue::List(values) => list_json(values, out),
        LogValue::Map(values) => {
            out.push('{');
            for (index, (key, value)) in values.iter().enumerate() {
                if index != 0 {
                    out.push_str(", ");
                }
                string_json(key, out);
                out.push_str(": ");
                value_json(value, out);
            }
            out.push('}');
        }
    }
}

fn list_json(values: &[LogValue], out: &mut String) {
    out.push('[');
    for (index, value) in values.iter().enumerate() {
        if index != 0 {
            out.push_str(", ");
        }
        value_json(value, out);
    }
    out.push(']');
}

pub fn event_json(event: &[LogValue]) -> String {
    let mut out = String::new();
    list_json(event, &mut out);
    out
}

pub fn reference_value(battle: &Battle, reference: EntityRef) -> LogValue {
    let items = match reference {
        EntityRef::Building(id) => vec![("$building".to_owned(), LogValue::Int(id.0 as i64))],
        EntityRef::Wall(id) => {
            let wall = &battle.walls[id.0];
            vec![(
                "$wall".to_owned(),
                LogValue::List(vec![
                    LogValue::Int(i64::from(wall.tx)),
                    LogValue::Int(i64::from(wall.ty)),
                ]),
            )]
        }
        EntityRef::Unit(unit) => vec![
            ("$unit".to_owned(), LogValue::Int(unit.id.0 as i64)),
            ("team".to_owned(), LogValue::from(unit.team.as_str())),
        ],
        EntityRef::Trap(id) => vec![("$trap".to_owned(), LogValue::Int(id.0 as i64))],
    };
    LogValue::Map(items)
}

pub fn exported_value(battle: &Battle, value: &Value) -> LogValue {
    match value {
        Value::Null => LogValue::Null,
        Value::Bool(value) => LogValue::Bool(*value),
        Value::Number(value) => LogValue::Float(*value),
        Value::String(value) => LogValue::String(value.clone()),
        Value::List(values) => LogValue::List(
            values
                .iter()
                .map(|value| exported_value(battle, value))
                .collect(),
        ),
        Value::Map(values) => LogValue::Map(
            values
                .iter()
                .map(|(key, value)| (key.clone(), exported_value(battle, value)))
                .collect(),
        ),
        Value::Ref(reference) => reference_value(battle, *reference),
    }
}

impl Battle {
    // Pass precisely the tuple fields Python appends, including its explicit
    // round() calls. Later mechanics can build nested lists/maps without JSON.
    pub fn log_event(&mut self, fields: Vec<LogValue>) {
        if self.record {
            self.log.push(fields);
        }
    }
}

pub fn write_trace(battle: &mut Battle, out: &mut impl Write) -> io::Result<()> {
    battle.record = true;
    let mut last_buildings: Vec<f64> = battle.buildings.iter().map(|b| b.max_hp).collect();
    let mut last_walls: Vec<f64> = battle.walls.iter().map(|w| w.max_hp).collect();
    let mut nlog = 0;
    while !battle.ended && battle.t < battle.max_time {
        writeln!(out, "T {:016x}", battle.t.to_bits())?;
        battle.step();
        let pools: [(&str, Vec<_>); 2] = [
            ("atk", battle.attackers_pool().collect()),
            ("def", battle.defenders_pool().collect()),
        ];
        for (team, pool) in pools {
            for unit in pool.into_iter().filter(|unit| unit.alive) {
                writeln!(
                    out,
                    "U {team} {} {} {:016x} {:016x} {:016x}",
                    unit.id.0,
                    unit.name.replace(' ', "_"),
                    unit.x.to_bits(),
                    unit.y.to_bits(),
                    unit.hp.to_bits()
                )?;
            }
        }
        for (index, building) in battle.buildings.iter().enumerate() {
            if last_buildings[index] != building.hp {
                last_buildings[index] = building.hp;
                writeln!(out, "B {} {:016x}", building.id.0, building.hp.to_bits())?;
            }
        }
        for (index, wall) in battle.walls.iter().enumerate() {
            if last_walls[index] != wall.hp {
                last_walls[index] = wall.hp;
                writeln!(out, "W {} {} {:016x}", wall.tx, wall.ty, wall.hp.to_bits())?;
            }
        }
        for event in &battle.log[nlog..] {
            writeln!(out, "E {}", event_json(event))?;
        }
        nlog = battle.log.len();
        if battle.destroyed_counted >= battle.total_counted || battle.offense_finished() {
            break;
        }
    }
    let result = battle.result();
    writeln!(
        out,
        "R {} {} {:016x} {}",
        result.stars,
        result.destruction,
        result.time.to_bits(),
        result.units_left
    )
}
