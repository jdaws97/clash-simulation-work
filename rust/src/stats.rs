//! Ports stats.py:20-31,129-153,165-233 over rust_export.py's processed registry.

use std::cell::RefCell;
use std::collections::HashMap;
use std::fmt;
use std::fmt::Write;
use std::rc::Rc;

use crate::json::Json;

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub enum Level {
    Int(i64),
    Text(String),
}

impl Level {
    pub fn from_json(value: &Json) -> Self {
        match value {
            Json::Num(_) => Self::Int(value.i64()),
            Json::Str(text) => Self::Text(text.clone()),
            other => panic!("expected an integer or string level, got {other:?}"),
        }
    }
}

impl fmt::Display for Level {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Int(value) => write!(f, "{value}"),
            Self::Text(value) => f.write_str(value),
        }
    }
}

// stats.py:171-174,182: replacement retains the original dictionary position.
pub type Row = Vec<(String, Json)>;

fn set(row: &mut Row, key: String, value: Json) {
    if let Some((_, old)) = row.iter_mut().find(|(name, _)| *name == key) {
        *old = value;
    } else {
        row.push((key, value));
    }
}

fn lower(row: &Row) -> Row {
    let mut result = Vec::new();
    for (key, value) in row {
        set(&mut result, key.to_lowercase(), value.clone());
    }
    result
}

struct CachedRow {
    merged: Rc<Row>,
    text: Row,
    numeric: Row,
}

pub struct Stats {
    pub registry: Json,
    cache: RefCell<HashMap<(String, Level), CachedRow>>,
}

impl Stats {
    pub fn new(registry: Json) -> Self {
        // The current catalog has a dagger in "Laboratory Level Cap †".
        // Unicode lowercasing preserves it; do not assume ASCII column names.
        registry.obj();
        Self {
            registry,
            cache: RefCell::new(HashMap::new()),
        }
    }

    pub fn record(&self, name: &str) -> &Json {
        self.registry.get(name)
            .unwrap_or_else(|| panic!("catalog.registry[{name:?}]: missing record"))
    }

    pub fn attrs(&self, name: &str) -> &Json {
        self.record(name).get("attrs")
            .unwrap_or_else(|| panic!("catalog.registry[{name:?}].attrs: missing field"))
    }

    fn entry(&self, name: &str, level: &Level) -> &Json {
        self.record(name).at("levels").arr().iter().find(|entry| {
            entry.get("level").is_some_and(|value| match (level, value) {
                (Level::Int(a), Json::Num(b)) => *a as f64 == *b,
                (Level::Text(a), Json::Str(b)) => a == b,
                _ => false,
            })
        }).unwrap_or_else(|| panic!("catalog.registry[{name:?}].levels: no level {level}"))
    }

    fn ensure_row(&self, name: &str, level: &Level) {
        let key = (name.to_owned(), level.clone());
        if self.cache.borrow().contains_key(&key) {
            return;
        }
        let entry = self.entry(name, level);
        let mut merged: Row = entry.obj().iter()
            .filter(|(key, _)| key != "wiki").cloned().collect();
        let wiki = entry.get("wiki").map(Json::obj).unwrap_or(&[]);
        for (key, value) in wiki {
            set(&mut merged, key.clone(), value.clone());
        }
        let text = lower(&merged);
        let mut numeric = text.clone();
        // stats.py:192-210: only get(), never text() or row(), uses these aliases.
        for (alias, columns) in [
            ("hitpoints", &["hitpoints"][..]),
            ("dps", &["damage per second", "damage per second*", "base damage per second"][..]),
        ] {
            if let Some(game) = entry.get(alias).filter(|value| num(value, None).is_some()) {
                set(&mut numeric, alias.to_owned(), game.clone());
                continue;
            }
            let mut found = None;
            for column in columns {
                for (key, value) in wiki {
                    if key.to_lowercase() == *column && num(value, None).is_some() {
                        found = Some(value.clone());
                        break;
                    }
                }
                if found.is_some() {
                    break;
                }
            }
            if let Some(value) = found {
                set(&mut numeric, alias.to_owned(), value);
            }
        }
        self.cache.borrow_mut().insert(key, CachedRow {
            merged: Rc::new(merged),
            text,
            numeric,
        });
    }

    pub fn row(&self, name: &str, level: &Level) -> Rc<Row> {
        self.ensure_row(name, level);
        Rc::clone(&self.cache.borrow()[&(name.to_owned(), level.clone())].merged)
    }

    pub fn get(&self, name: &str, level: &Level, keys: &[&str], default: Option<f64>) -> Option<f64> {
        self.ensure_row(name, level);
        let cache = self.cache.borrow();
        let row = &cache[&(name.to_owned(), level.clone())].numeric;
        for key in keys {
            if let Some(fragment) = key.strip_prefix('~') {
                let fragment = fragment.to_lowercase();
                for (key, value) in row {
                    if key.contains(&fragment) {
                        if let Some(number) = num(value, None) {
                            return Some(number);
                        }
                    }
                }
            } else {
                let key = key.to_lowercase();
                if let Some((_, value)) = row.iter().find(|(name, _)| *name == key) {
                    if let Some(number) = num(value, None) {
                        return Some(number);
                    }
                }
            }
        }
        default
    }

    pub fn text(&self, name: &str, level: &Level, keys: &[&str], default: Option<Json>) -> Option<Json> {
        self.ensure_row(name, level);
        let cache = self.cache.borrow();
        let row = &cache[&(name.to_owned(), level.clone())].text;
        for key in keys {
            let key = key.to_lowercase();
            if let Some((_, value)) = row.iter().find(|(name, _)| *name == key) {
                return Some(value.clone());
            }
        }
        default
    }

    pub fn required_town_hall(&self, name: &str, level: &Level) -> f64 {
        self.get(name, level, &["Town Hall Level Required", "required_townhall"], Some(0.0))
            .expect("numeric default")
    }

    pub fn max_level(&self, name: &str, town_hall: i64) -> Option<i64> {
        let rec = self.record(name);
        if let Some(value) = rec.get("max_level").and_then(|map| map.get(&town_hall.to_string())) {
            return if value.is_null() {
                None
            } else {
                Some(value.i64())
            };
        }
        rec.at("levels").arr().iter().filter_map(|entry| {
            let Json::Num(level) = entry.get("level")? else {
                return None;
            };
            let level = *level as i64;
            (self.required_town_hall(name, &Level::Int(level)) <= town_hall as f64)
                .then_some(level)
        }).max()
    }
}

// Python's regex \d means Unicode decimal digits. Map Nd blocks to ASCII
// before float(), which accepts these digits too (stats.py:17,25-29).
fn decimal(c: char) -> Option<u32> {
    const ZEROES: &[u32] = &[
        0x30, 0x660, 0x6f0, 0x7c0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66,
        0xbe6, 0xc66, 0xce6, 0xd66, 0xde6, 0xe50, 0xed0, 0xf20, 0x1040,
        0x1090, 0x17e0, 0x1810, 0x1946, 0x19d0, 0x1a80, 0x1a90, 0x1b50,
        0x1bb0, 0x1c40, 0x1c50, 0xa620, 0xa8d0, 0xa900, 0xa9d0, 0xa9f0,
        0xaa50, 0xabf0, 0xff10, 0x104a0, 0x10d30, 0x11066, 0x110f0,
        0x11136, 0x111d0, 0x112f0, 0x11450, 0x114d0, 0x11650, 0x116c0,
        0x11730, 0x118e0, 0x11950, 0x11c50, 0x11d50, 0x11da0, 0x16a60,
        0x16ac0, 0x16b50, 0x1d7ce, 0x1d7d8, 0x1d7e2, 0x1d7ec, 0x1d7f6,
        0x1e140, 0x1e2f0, 0x1e950, 0x1fbf0,
    ];
    let code = c as u32;
    ZEROES.iter().find_map(|zero| {
        (code >= *zero && code < *zero + 10).then(|| code - *zero)
    })
}

pub fn num(value: &Json, default: Option<f64>) -> Option<f64> {
    match value {
        Json::Null => return default,
        Json::Num(value) => return Some(*value),
        Json::Bool(value) => return Some(f64::from(u8::from(*value))),
        _ => {}
    }
    // Python str() for containers includes their first nested numeric value;
    // repr formatting is supplied here rather than JSON's different bool/null.
    let text = match value {
        Json::Str(value) => value.clone(),
        other => python_text(other),
    };
    let chars: Vec<char> = text.replace('\u{2212}', "-").chars().collect();
    for start in 0..chars.len() {
        let mut end = start;
        let mut matched = String::new();
        if chars[end] == '-' {
            matched.push('-');
            end += 1;
        }
        if end == chars.len() || decimal(chars[end]).is_none() {
            continue;
        }
        while end < chars.len() {
            if let Some(digit) = decimal(chars[end]) {
                matched.push(char::from_digit(digit, 10).expect("decimal digit"));
            } else if chars[end] != ',' {
                break;
            }
            end += 1;
        }
        if chars.get(end) == Some(&'.') {
            matched.push('.');
            end += 1;
            while end < chars.len() {
                let Some(digit) = decimal(chars[end]) else {
                    break;
                };
                matched.push(char::from_digit(digit, 10).expect("decimal digit"));
                end += 1;
            }
        }
        return matched.parse().ok().or(default);
    }
    default
}

fn python_text(value: &Json) -> String {
    match value {
        Json::Null => "None".to_owned(),
        Json::Bool(value) => if *value { "True" } else { "False" }.to_owned(),
        Json::Num(value) => crate::trace::py_float_repr(*value),
        Json::Str(value) => python_string_repr(value),
        Json::Arr(items) => format!("[{}]", items.iter().map(python_text).collect::<Vec<_>>().join(", ")),
        Json::Obj(items) => format!("{{{}}}", items.iter().map(|(key, value)| {
            format!("{}: {}", python_string_repr(key), python_text(value))
        }).collect::<Vec<_>>().join(", ")),
    }
}

fn python_string_repr(value: &str) -> String {
    let quote = if value.contains('\'') && !value.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::new();
    out.push(quote);
    for c in value.chars() {
        if c == quote || c == '\\' {
            out.push('\\');
            out.push(c);
        } else {
            match c {
                '\t' => out.push_str("\\t"),
                '\n' => out.push_str("\\n"),
                '\r' => out.push_str("\\r"),
                _ => {
                    let escaped = c.escape_debug().to_string();
                    if c.is_control() || escaped.starts_with("\\u{") {
                        let code = c as u32;
                        if code <= 0xff {
                            write!(out, "\\x{code:02x}").expect("write to string");
                        } else if code <= 0xffff {
                            write!(out, "\\u{code:04x}").expect("write to string");
                        } else {
                            write!(out, "\\U{code:08x}").expect("write to string");
                        }
                    } else {
                        out.push(c);
                    }
                }
            }
        }
    }
    out.push(quote);
    out
}
