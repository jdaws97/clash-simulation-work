//! Provenance text shared by actors, pending hits and ordered damage counters.

use std::fmt;
use std::ops::Deref;
use std::rc::Rc;

#[derive(Clone)]
pub enum Source {
    Literal(&'static str),
    Shared(Rc<str>),
}

impl Source {
    #[inline]
    pub fn as_str(&self) -> &str {
        match self {
            Self::Literal(text) => text,
            Self::Shared(text) => text,
        }
    }
}

impl From<&str> for Source {
    fn from(text: &str) -> Self {
        match text {
            "spell" => Self::Literal("spell"),
            "trap" => Self::Literal("trap"),
            "poison" => Self::Literal("poison"),
            "eagle" => Self::Literal("eagle"),
            "mortar" => Self::Literal("mortar"),
            "bt" => Self::Literal("bt"),
            "wizard_tower" => Self::Literal("wizard_tower"),
            "th" => Self::Literal("th"),
            "spell_tower" => Self::Literal("spell_tower"),
            _ => Self::Shared(Rc::from(text)),
        }
    }
}

impl From<&String> for Source {
    fn from(text: &String) -> Self {
        Self::from(text.as_str())
    }
}

impl From<String> for Source {
    fn from(text: String) -> Self {
        Self::Shared(Rc::from(text))
    }
}

impl Deref for Source {
    type Target = str;

    fn deref(&self) -> &str {
        self.as_str()
    }
}

impl PartialEq for Source {
    fn eq(&self, other: &Self) -> bool {
        if let (Self::Shared(a), Self::Shared(b)) = (self, other) {
            if Rc::ptr_eq(a, b) {
                return true;
            }
        }
        self.as_str() == other.as_str()
    }
}

impl Eq for Source {}

impl PartialEq<&str> for Source {
    fn eq(&self, other: &&str) -> bool {
        self.as_str() == *other
    }
}

impl fmt::Display for Source {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        out.write_str(self.as_str())
    }
}

// Debug shows the text only: Literal and Shared are storage choices, and
// setup-check compares states through their Debug output.
impl fmt::Debug for Source {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        fmt::Debug::fmt(self.as_str(), f)
    }
}
