//! Admission errors for content the executor cannot represent (review R9).
//! Validate before setup/deployment, so searches receive a rejection without
//! unwinding a worker or emitting a panic log. Internal state invariants remain.

use std::fmt;

use crate::json::Json;

fn name(value: &Json) -> Option<&str> {
    match value {
        Json::Str(value) => Some(value),
        _ => None,
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ContentError {
    Unsupported { kind: &'static str, name: String },
    Invalid(String),
}

impl ContentError {
    pub fn unsupported(kind: &'static str, name: &str) -> Self {
        Self::Unsupported {
            kind,
            name: name.to_owned(),
        }
    }
}

impl fmt::Display for ContentError {
    fn fmt(&self, out: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Unsupported { kind, name } => write!(out, "unsupported {kind}: {name}"),
            Self::Invalid(message) => out.write_str(message),
        }
    }
}

impl std::error::Error for ContentError {}

pub fn equipment(name: &str) -> bool {
    matches!(
        name,
        "Vampstache"
            | "Electro Boots"
            | "Frozen Arrow"
            | "Stick Horse"
            | "Monolith Arrow"
            | "Rocket Spear"
            | "Revenge Deck"
            | "Fire Heart"
            | "Action Figure"
            | "Giant Arrow"
            | "Eternal Tome"
            | "Rage Gem"
            | "Fireball"
            | "Rocket Backpack"
            | "Spiky Ball"
            | "Earthquake Boots"
            | "Dark Orb"
            | "Meteor Staff"
            | "Barbarian Puppet"
            | "Archer Puppet"
            | "Hog Rider Puppet"
            | "Healer Puppet"
            | "Lavaloon Puppet"
            | "Seeking Shield"
            | "Haste Vial"
            | "Heroic Torch"
            | "Magic Mirror"
            | "Henchmen Puppet"
            | "Stun Blaster"
            | "Noble Iron"
            | "Rage Vial"
            | "Giant Gauntlet"
            | "Snake Bracelet"
            | "Invisibility Vial"
            | "Life Gem"
            | "Healing Tome"
            | "Royal Gem"
            | "Frost Flake"
            | "Dark Crown"
            | "Metal Pants"
            | "Portal Pendant"
            | "Flame Blower"
            | "Electro Fangs"
    )
}

pub fn pet(name: &str) -> bool {
    matches!(
        name,
        "Unicorn"
            | "Phoenix"
            | "Frosty"
            | "Poison Lizard"
            | "Spirit Fox"
            | "Electro Owl"
            | "Angry Jelly"
            | "L.A.S.S.I"
            | "Diggy"
            | "Mighty Yak"
            | "Sneezy"
            | "Greedy Raven"
    )
}

pub fn validate_plan(plan: &Json) -> Result<(), ContentError> {
    let kind = plan.get("$type").and_then(name).unwrap_or("");
    if !matches!(kind, "AttackPlan" | "PlaybookPlan" | "Stage") {
        return Err(ContentError::unsupported("plan", kind));
    }
    if kind == "PlaybookPlan" {
        let Some(Json::Arr(steps)) = plan.get("steps") else {
            return Err(ContentError::Invalid(
                "playbook needs a steps array".to_owned(),
            ));
        };
        for step in steps {
            validate_playbook_step_types(step)?;
        }
    }
    if let Some(Json::Obj(loadouts)) = plan.get("loadouts") {
        if loadouts
            .iter()
            .any(|(_, loadout)| !matches!(loadout, Json::Obj(_)))
        {
            return Err(ContentError::Invalid(
                "prepared loadouts must be objects".to_owned(),
            ));
        }
    }
    validate_loadouts(plan)?;
    for field in ["equipment_levels", "pet_levels"] {
        if let Some(Json::Obj(levels)) = plan.get(field) {
            for (name, value) in levels {
                if !matches!(value, Json::Num(level) if level.is_finite() && *level >= 1.0 && level.fract() == 0.0)
                {
                    return Err(ContentError::Invalid(format!(
                        "{name} requires a positive integer level"
                    )));
                }
            }
        }
    }
    Ok(())
}

/// Shared authoring/executor checks for fields read as strings or numbers by
/// Step::load. Null is allowed only where the executor treats it as absent.
pub fn validate_playbook_step_types(step: &Json) -> Result<(), ContentError> {
    if !matches!(step, Json::Obj(_)) {
        return Err(ContentError::Invalid("step must be an object".to_owned()));
    }
    for key in ["what", "origin", "at", "group", "aim"] {
        if let Some(value) = step.get(key).filter(|value| !value.is_null()) {
            if !matches!(value, Json::Str(_)) {
                return Err(ContentError::Invalid(format!("{key} needs a string")));
            }
        }
    }
    if let Some(value) = step.get("spread") {
        if !matches!(value, Json::Num(number) if number.is_finite()) {
            return Err(ContentError::Invalid(
                "spread needs a finite number".to_owned(),
            ));
        }
    }
    Ok(())
}

/// Build definitions use [equipment, equipment, pet]; prepared plans use named
/// loadout objects. Validate both before any compiler/executor stat lookups.
pub fn validate_loadouts(value: &Json) -> Result<(), ContentError> {
    if let Some(loadouts) = value.get("loadouts") {
        let Json::Obj(loadouts) = loadouts else {
            return Err(ContentError::Invalid(
                "loadouts must be an object".to_owned(),
            ));
        };
        for (_, loadout) in loadouts {
            if let Json::Arr(items) = loadout {
                for item in items.iter().take(2) {
                    let item = name(item).unwrap_or("");
                    if !equipment(item) {
                        return Err(ContentError::unsupported("hero equipment", item));
                    }
                }
                if let Some(item) = items.get(2).and_then(name).filter(|item| !item.is_empty()) {
                    if !pet(item) {
                        return Err(ContentError::unsupported("attacking pet", item));
                    }
                }
                continue;
            }
            if let Some(items) = loadout.get("equipment") {
                let Json::Arr(items) = items else {
                    return Err(ContentError::Invalid(
                        "equipment must be an array".to_owned(),
                    ));
                };
                for item in items {
                    let name = name(item).unwrap_or("");
                    if !equipment(name) {
                        return Err(ContentError::unsupported("hero equipment", name));
                    }
                }
            }
            if let Some(name) = loadout
                .get("pet")
                .and_then(name)
                .filter(|name| !name.is_empty())
            {
                if !pet(name) {
                    return Err(ContentError::unsupported("attacking pet", name));
                }
            }
        }
    }
    Ok(())
}

pub fn is_siege(name: &str) -> bool {
    matches!(
        name,
        "Log Launcher"
            | "Sky Wagon"
            | "Siege Barracks"
            | "Troop Launcher"
            | "Stone Slammer"
            | "Battle Blimp"
            | "Wall Wrecker"
            | "Battle Drill"
            | "Flame Flinger"
    )
}
