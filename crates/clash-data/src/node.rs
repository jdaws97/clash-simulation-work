//! Strict path-labelled JSON reader, independent of battle runtime.
use crate::json::Json;
use crate::stats::Level;

#[derive(Clone)]
pub struct Node<'a> {
    pub value: &'a Json,
    pub path: String,
}

impl<'a> Node<'a> {
    pub fn new(value: &'a Json, path: &str) -> Self {
        Self {
            value,
            path: path.to_owned(),
        }
    }

    pub fn fail(&self, message: &str) -> ! {
        panic!("{}: {message}", self.path)
    }

    pub fn field(&self, name: &str) -> Self {
        self.optional(name)
            .unwrap_or_else(|| panic!("{}.{}: missing field", self.path, name))
    }

    pub fn optional(&self, name: &str) -> Option<Self> {
        self.value.get(name).map(|value| Self {
            value,
            path: format!("{}.{}", self.path, name),
        })
    }

    pub fn object(&self) -> Vec<(String, Self)> {
        let Json::Obj(items) = self.value else {
            self.fail("expected object")
        };
        items
            .iter()
            .map(|(key, value)| {
                (
                    key.clone(),
                    Self {
                        value,
                        path: format!("{}.{}", self.path, key),
                    },
                )
            })
            .collect()
    }

    pub fn array(&self) -> Vec<Self> {
        let Json::Arr(items) = self.value else {
            self.fail("expected array")
        };
        items
            .iter()
            .enumerate()
            .map(|(index, value)| Self {
                value,
                path: format!("{}[{index}]", self.path),
            })
            .collect()
    }

    pub fn tuple(&self, length: usize) -> Vec<Self> {
        let items = self.array();
        if items.len() != length {
            self.fail(&format!("expected {length} items"));
        }
        items
    }

    pub fn keys(&self, allowed: &[&str]) {
        if let Some(tag) = self.optional("$type") {
            if !known_type(&tag.string()) {
                tag.fail("unknown $type");
            }
        }
        for (key, node) in self.object() {
            if key != "$type" && !allowed.contains(&key.as_str()) {
                node.fail("unknown field (no generic fallback)");
            }
        }
    }

    pub fn require_type(&self, expected: &str) {
        let actual = self.field("$type").string();
        if actual != expected {
            self.field("$type")
                .fail(&format!("expected {expected}, got {actual}"));
        }
    }

    pub fn require_fields(&self, fields: &[&str]) {
        for field in fields {
            self.field(field);
        }
    }

    pub fn string(&self) -> String {
        let Json::Str(value) = self.value else {
            self.fail("expected string")
        };
        value.clone()
    }

    pub fn number(&self) -> f64 {
        let Json::Num(value) = self.value else {
            self.fail("expected number")
        };
        *value
    }

    pub fn integer(&self) -> i64 {
        let value = self.number();
        if !value.is_finite()
            || value.fract() != 0.0
            || value < i64::MIN as f64
            || value >= 9_223_372_036_854_775_808.0
        {
            self.fail("expected integer in i64 range");
        }
        value as i64
    }

    pub fn usize(&self) -> usize {
        let value = self.integer();
        usize::try_from(value).unwrap_or_else(|_| self.fail("expected nonnegative index"))
    }

    pub fn i32(&self) -> i32 {
        i32::try_from(self.integer()).unwrap_or_else(|_| self.fail("integer outside i32 range"))
    }

    pub fn boolean(&self) -> bool {
        let Json::Bool(value) = self.value else {
            self.fail("expected boolean")
        };
        *value
    }

    pub fn optional_string(&self) -> Option<String> {
        if self.value.is_null() {
            None
        } else {
            Some(self.string())
        }
    }

    pub fn optional_bool(&self) -> Option<bool> {
        if self.value.is_null() {
            None
        } else {
            Some(self.boolean())
        }
    }

    pub fn optional_number(&self) -> Option<f64> {
        if self.value.is_null() {
            None
        } else {
            Some(self.number())
        }
    }

    pub fn optional_integer(&self) -> Option<i64> {
        if self.value.is_null() {
            None
        } else {
            Some(self.integer())
        }
    }

    pub fn level(&self) -> Level {
        match self.value {
            Json::Num(_) => Level::Int(self.integer()),
            Json::Str(value) => Level::Text(value.clone()),
            _ => self.fail("expected integer or string level"),
        }
    }

    pub fn optional_level(&self) -> Option<Level> {
        if self.value.is_null() {
            None
        } else {
            Some(self.level())
        }
    }

    pub fn pair(&self) -> (f64, f64) {
        let items = self.tuple(2);
        (items[0].number(), items[1].number())
    }

    pub fn optional_pair(&self) -> Option<(f64, f64)> {
        if self.value.is_null() {
            None
        } else {
            Some(self.pair())
        }
    }

    pub fn optional_source(&self) -> Option<(String, i64)> {
        if self.value.is_null() {
            return None;
        }
        let pair = self.tuple(2);
        Some((pair[0].string(), pair[1].integer()))
    }

    pub fn triple(&self) -> (f64, f64, f64) {
        let items = self.tuple(3);
        (items[0].number(), items[1].number(), items[2].number())
    }
}

pub fn known_type(name: &str) -> bool {
    matches!(
        name,
        "Building"
            | "Wall"
            | "Unit"
            | "UnitSpec"
            | "Weapon"
            | "Trap"
            | "Field"
            | "Pending"
            | "Builder"
            | "Deployment"
            | "Stage"
            | "BuildingType"
            | "HeroLoadout"
            | "Kit"
            | "AttackPlan"
            | "PlaybookPlan"
            | "SpellStock"
            | "Wave"
            | "DefenseSnipe"
    )
}
