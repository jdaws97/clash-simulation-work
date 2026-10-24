//! Strict search boundary for playbook.py:505-675,677-739,964-1153.
//! The executor accepts trusted plans; search proposals must return errors.

use std::collections::{BTreeMap, BTreeSet};

use crate::json::Json;

use super::{deploy_stock, spell_stock, unit_names, AttackProgram};
use crate::armysearch::genome::ArmyGenome;
use crate::armysearch::util::text;

pub const MAX_STEPS: usize = 256;

// mechanics.py:67-138, mirrored by the frozen native catalog. An
// absent building on a particular target is allowed; unknown keys are not.
const BUILDING_KEYS: &[&str] = &[
    "th", "cc", "ad", "sweeper", "at", "mat", "cannon", "ric", "bt", "bh",
    "eagle", "tesla", "inferno", "mono", "mortar", "scatter", "st", "wt", "xbow",
    "gm", "ec", "dd", "gs", "es", "ds", "camp", "barracks", "dbarracks", "sf",
    "dsf", "lab", "workshop", "pethouse", "smith", "herohall", "helper", "bob",
    "banner", "mgt", "firespitter", "swt", "revenge", "crafting",
];

pub fn finite(value: &Json, depth: usize) -> Result<(), String> {
    if depth > 24 {
        return Err("program nesting exceeds 24".to_owned());
    }
    match value {
        Json::Num(value) if !value.is_finite() => Err("nonfinite program number".to_owned()),
        Json::Obj(fields) => {
            let mut keys = BTreeSet::new();
            for (key, value) in fields {
                if !keys.insert(key) {
                    return Err(format!("duplicate program key: {key}"));
                }
                finite(value, depth + 1)?;
            }
            Ok(())
        }
        Json::Arr(values) => {
            for value in values {
                finite(value, depth + 1)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

fn name<'a>(value: &'a Json, field: &str) -> Result<&'a str, String> {
    match value.get(field) {
        Some(Json::Str(value)) if !value.is_empty() => Ok(value),
        _ => Err(format!("{field} must be a nonempty string")),
    }
}

pub fn scalar(value: &Json, low: f64, high: f64) -> Result<f64, String> {
    match value {
        Json::Num(value) if value.is_finite() && (low..=high).contains(value) => Ok(*value),
        _ => Err(format!("expected finite number in [{low}, {high}]")),
    }
}

pub fn amount(step: &Json, left: usize, default: usize) -> Result<usize, String> {
    let count = match step.get("count") {
        None | Some(Json::Null) => default,
        Some(Json::Str(value)) if value == "all" => left,
        Some(Json::Str(value)) => value.parse::<usize>().map_err(|_| "invalid integer count")?,
        Some(value) => {
            let value = scalar(value, 1.0, 10000.0)?;
            if value.fract() != 0.0 {
                return Err("count must be integral".to_owned());
            }
            value as usize
        }
    };
    if count == 0 || count > left {
        return Err(format!("inventory exceeded: requested {count}, remaining {left}"));
    }
    Ok(count)
}

struct References {
    units: BTreeSet<String>,
    groups: BTreeSet<String>,
    ids: BTreeSet<String>,
    spells: BTreeMap<String, usize>,
}

fn contains(names: &BTreeSet<String>, name: &str, kind: &str) -> Result<(), String> {
    if names.contains(name) {
        Ok(())
    } else {
        Err(format!("unknown {kind} reference: {name}"))
    }
}

fn anchor(value: &str, refs: &References, aim: bool) -> Result<(), String> {
    if value == "th" || aim && matches!(value, "arrow" | "dash") {
        return Ok(());
    }
    let Some((kind, arg)) = value.split_once(':') else {
        return Err(format!("unknown anchor: {value}"));
    };
    match kind {
        "edge" if matches!(arg, "main" | "charge" | "funnel" | "left" | "right") => Ok(()),
        "unit" | "unit_ahead" => contains(&refs.units, arg, "unit"),
        "group" | "threat" | "defenders" => contains(&refs.groups, arg, "group"),
        "building" if BUILDING_KEYS.contains(&arg) => Ok(()),
        _ => Err(format!("unknown anchor: {value}")),
    }
}

fn trigger(value: &Json, refs: &References, edges: &mut Vec<String>) -> Result<(), String> {
    if matches!(value, Json::Null) {
        return Ok(());
    }
    let Json::Obj(fields) = value else {
        return Err("trigger must be an object or null".to_owned());
    };
    if fields.is_empty() {
        return Ok(());
    }
    let operations = ["t", "after", "inside", "group_inside", "near_th", "heavy_fire",
        "hp_below", "spells_left", "dead", "defenders_near", "destruction", "all", "any"];
    let selected: Vec<_> = operations.iter().copied().filter(|key| value.get(key).is_some()).collect();
    if selected.len() != 1 {
        return Err("trigger requires exactly one operation (combine with all/any)".to_owned());
    }
    let key = selected[0];
    let parameter = match key {
        "after" => "delay",
        "near_th" => "r",
        "heavy_fire" | "hp_below" => "frac",
        "spells_left" => "n",
        _ => "",
    };
    if fields.iter().any(|(field, _)| field != key && field != parameter) {
        return Err(format!("unsupported parameter for {key}"));
    }
    match key {
        "all" | "any" => {
            let Some(Json::Arr(parts)) = value.get(key) else {
                return Err(format!("{key} requires an array"));
            };
            if parts.is_empty() || parts.len() > 16 {
                return Err("all/any requires 1..16 children".to_owned());
            }
            for part in parts {
                trigger(part, refs, edges)?;
            }
        }
        "t" => {
            scalar(value.at(key), 0.0, 180.0)?;
        }
        "destruction" => {
            scalar(value.at(key), 0.0, 100.0)?;
        }
        "after" => {
            let id = name(value, key)?;
            contains(&refs.ids, id, "step")?;
            edges.push(id.to_owned());
        }
        "inside" | "heavy_fire" | "hp_below" | "dead" => {
            contains(&refs.units, name(value, key)?, "unit")?;
        }
        "group_inside" | "near_th" | "defenders_near" => {
            contains(&refs.groups, name(value, key)?, "group")?;
        }
        "spells_left" => {
            let spell = name(value, key)?;
            let spell = crate::plans::spell_key(spell).map(crate::plans::spell_name).unwrap_or(spell);
            if !refs.spells.contains_key(spell) {
                return Err(format!("spell condition absent from army: {spell}"));
            }
        }
        _ => unreachable!(),
    }
    if let Some(value) = value.get(parameter) {
        let (low, high) = match parameter {
            "delay" => (0.0, 180.0),
            "r" => (0.0, 100.0),
            "frac" => (0.0, 1.0),
            "n" => (0.0, 10000.0),
            _ => unreachable!(),
        };
        let number = scalar(value, low, high)?;
        if parameter == "n" && number.fract() != 0.0 {
            return Err("spells_left n must be integral".to_owned());
        }
    }
    Ok(())
}

fn acyclic(
    id: &str,
    graph: &BTreeMap<String, Vec<String>>,
    active: &mut BTreeSet<String>,
    done: &mut BTreeSet<String>,
) -> Result<(), String> {
    if done.contains(id) {
        return Ok(());
    }
    if !active.insert(id.to_owned()) {
        return Err(format!("cyclic after dependency: {id}"));
    }
    for next in &graph[id] {
        acyclic(next, graph, active, done)?;
    }
    active.remove(id);
    done.insert(id.to_owned());
    Ok(())
}

pub fn equipment(step: &Json, genome: &ArmyGenome) -> Result<(), String> {
    let hero = name(step, "what")?;
    let choice = genome.heroes.iter().find(|choice| choice.hero == hero)
        .ok_or_else(|| format!("ability requires selected hero: {hero}"))?;
    let description = text(step, "ability", text(step, "id", "")).replace('_', " ").to_lowercase();
    let aim = text(step, "aim", "");
    let inferred = if aim == "arrow" || hero == "Archer Queen" && aim.starts_with("building:") {
        Some("Giant Arrow")
    } else if aim == "dash" {
        Some("Rocket Backpack")
    } else if hero == "Grand Warden" && aim.starts_with("building:") {
        Some("Fireball")
    } else {
        None
    };
    let explicit = step.get("equipment").and_then(|value| match value {
        Json::Str(value) => Some(value.as_str()),
        _ => None,
    });
    // Preserve registry order in playbook.py:683-694's full-name inference.
    let names: &[&str] = match hero {
        "Archer Queen" => &[
            "Archer Puppet", "Invisibility Vial", "Frozen Arrow", "Monolith Arrow",
            "Giant Arrow", "Healer Puppet", "Magic Mirror", "Action Figure",
        ],
        "Barbarian King" => &[
            "Barbarian Puppet", "Rage Vial", "Earthquake Boots", "Giant Gauntlet",
            "Vampstache", "Spiky Ball", "Snake Bracelet", "Stick Horse",
        ],
        "Grand Warden" => &[
            "Eternal Tome", "Life Gem", "Heroic Torch", "Fireball", "Rage Gem",
            "Healing Tome", "Lavaloon Puppet",
        ],
        "Royal Champion" => &[
            "Seeking Shield", "Royal Gem", "Hog Rider Puppet", "Haste Vial",
            "Rocket Spear", "Electro Boots", "Frost Flake",
        ],
        "Minion Prince" => &[
            "Dark Crown", "Henchmen Puppet", "Dark Orb", "Metal Pants", "Noble Iron",
            "Meteor Staff", "Portal Pendant",
        ],
        "Dragon Duke" => &[
            "Fire Heart", "Rocket Backpack", "Stun Blaster", "Flame Blower",
            "Electro Fangs", "Revenge Deck",
        ],
        _ => &[],
    };
    let full_name = names.iter().copied().find(|item| description.contains(item.to_lowercase().as_str()));
    let mut required = explicit.or(full_name);
    // playbook.py:677-739 also infers equipment from the ability/id text.
    let aliases: &[(&str, &str)] = match hero {
        "Archer Queen" => &[
            ("arrow", "Giant Arrow"),
            ("queen shot", "Giant Arrow"),
            ("healers out", "Healer Puppet"),
        ],
        "Grand Warden" => &[("tome", "Eternal Tome"), ("torch", "Heroic Torch")],
        "Royal Champion" => &[("spear", "Rocket Spear")],
        "Dragon Duke" => &[
            ("backpack", "Rocket Backpack"),
            ("jetpack", "Rocket Backpack"),
            ("blaster", "Stun Blaster"),
            ("stun", "Stun Blaster"),
        ],
        _ => &[],
    };
    for &(word, item) in aliases {
        if required.is_none() && description.contains(word) {
            required = Some(item);
        }
    }
    if explicit.is_none() && inferred.is_some() {
        required = inferred;
    }
    if let Some(item) = required {
        if !choice.equipment.iter().any(|equipment| equipment == item) {
            return Err(format!("{hero} does not carry {item}"));
        }
    }
    Ok(())
}

pub fn validate(program: &AttackProgram, genome: &ArmyGenome) -> Result<(), String> {
    if program.steps.is_empty() || program.steps.len() > MAX_STEPS {
        return Err("program requires 1..256 steps".to_owned());
    }
    let mut refs = References {
        units: unit_names(genome),
        groups: BTreeSet::new(),
        ids: BTreeSet::new(),
        spells: spell_stock(genome),
    };
    for step in &program.steps {
        finite(step, 0)?;
        if !matches!(step, Json::Obj(_)) {
            return Err("program step must be an object".to_owned());
        }
        for key in ["id", "action", "what", "group", "at", "aim", "origin", "equipment", "ability"] {
            if step.get(key).is_some_and(|value| !matches!(value, Json::Str(_))) {
                return Err(format!("step {key} must be a string"));
            }
        }
        if !refs.ids.insert(name(step, "id")?.to_owned()) {
            return Err("duplicate program step id".to_owned());
        }
        if matches!(text(step, "action", ""), "deploy" | "redeploy") {
            refs.groups.insert(text(step, "group", "main").to_owned());
        }
    }
    let mut stock = deploy_stock(genome);
    let mut brewed = BTreeMap::<String, usize>::new();
    let mut donated = BTreeMap::<String, usize>::new();
    for unit in &genome.spells {
        *brewed.entry(unit.name.clone()).or_default() += unit.count;
    }
    for unit in &genome.cc_spells {
        *donated.entry(unit.name.clone()).or_default() += unit.count;
    }
    // plans.py:955-976 selects the first matching live stock at cast time.
    // Totals must be independent of the order of pending step definitions.
    let mut spell_demand = BTreeMap::<String, [usize; 3]>::new();
    let mut abilities = BTreeSet::new();
    let mut graph = BTreeMap::new();
    let mut releases = 0;
    let mut redeploys = 0;
    let recalls = refs.spells.get("Recall Spell").copied().unwrap_or(0)
        + genome.heroes.iter().filter(|hero| hero.equipment.iter().any(|item| item == "Portal Pendant")).count();
    for (index, step) in program.steps.iter().enumerate() {
        let check = || -> Result<Vec<String>, String> {
            let allowed = ["id", "action", "what", "count", "group", "at", "when", "every", "until",
                "aim", "spread", "level", "origin", "completion", "uncited", "learned", "skip_if_impossible",
                "ability", "equipment", "cite", "aim_cite", "at_cite", "support", "variant", "note", "notes"];
            if step.obj().iter().any(|(key, _)| !allowed.contains(&key.as_str())) {
                return Err("unknown step field".to_owned());
            }
            for key in ["id", "action", "what", "group", "at", "aim", "origin", "equipment", "ability"] {
                if let Some(value) = step.get(key) {
                    if !matches!(value, Json::Str(_)) && !(key == "what" && matches!(value, Json::Null)) {
                        return Err(format!("{key} must be a string"));
                    }
                }
            }
            let group = text(step, "group", "main");
            if group.is_empty() || group.len() > 64 {
                return Err("invalid group label".to_owned());
            }
            for key in ["completion", "uncited", "learned", "skip_if_impossible"] {
                if step.get(key).is_some_and(|value| !matches!(value, Json::Bool(_))) {
                    return Err(format!("{key} must be boolean"));
                }
            }
            if step.get("origin").is_some_and(|value| !matches!(value.str(), "brewed" | "donated")) {
                return Err("unknown spell origin".to_owned());
            }
            for key in ["cite", "aim_cite", "at_cite"] {
                if let Some(value) = step.get(key) {
                    if !matches!(value, Json::Arr(_)) {
                        return Err(format!("{key} must be an array"));
                    }
                    for citation in value.arr() {
                        let invalid_quote = citation.get("quote")
                            .is_some_and(|value| !matches!(value, Json::Str(_)));
                        if !matches!(citation, Json::Obj(_)) || invalid_quote {
                            return Err("invalid citation record".to_owned());
                        }
                    }
                }
            }
            anchor(text(step, "at", "edge:main"), &refs, false)?;
            if let Some(aim) = step.get("aim") {
                anchor(aim.str(), &refs, true)?;
            }
            if let Some(spread) = step.get("spread") {
                scalar(spread, 0.0, 100.0)?;
            }
            if let Some(level) = step.get("level") {
                scalar(level, 1.0, 100.0)?;
                return Err("program levels are fixed account inputs".to_owned());
            }
            let mut edges = Vec::new();
            for key in ["when", "until"] {
                if let Some(value) = step.get(key) {
                    trigger(value, &refs, &mut edges)?;
                }
            }
            Ok(edges)
        };
        let edges = check().map_err(|reason| format!("step {index}: {reason}"))?;
        graph.insert(name(step, "id")?.to_owned(), edges);
        let action = name(step, "action")?;
        let what = text(step, "what", "");
        let repeated = step.get("every").is_some();
        if let Some(every) = step.get("every") {
            scalar(every, 0.1, 180.0).map_err(|reason| format!("step {index}: {reason}"))?;
            if !matches!(action, "spell" | "recall") {
                return Err(format!("step {index}: repetition only supports casts"));
            }
        }
        let mut spend = || -> Result<(), String> {
            match action {
                "deploy" => {
                    let left = stock.get(what).copied().unwrap_or(0);
                    let count = amount(step, left, left)?;
                    stock.insert(what.to_owned(), left - count);
                }
                "spell" | "recall" => {
                    if action == "recall" && !what.is_empty() && what != "Recall Spell" && !refs.units.contains(what) {
                        return Err("recall what must name Recall Spell or an army unit".to_owned());
                    }
                    let spell = if action == "recall" {
                        "Recall Spell"
                    } else {
                        what
                    };
                    let left = refs.spells.get(spell).copied().unwrap_or(0);
                    // playbook.py:663-675 casts exactly one per execution.
                    // A repeat conservatively reserves its entire stock.
                    let count = amount(step, left, 1)?;
                    if count != 1 {
                        return Err("a cast step consumes one spell; split steps or use every".to_owned());
                    }
                    let origin = step.get("origin").map(Json::str);
                    let home = brewed.get(spell).copied().unwrap_or(0);
                    let cc = donated.get(spell).copied().unwrap_or(0);
                    let available = match origin {
                        Some("brewed") => home,
                        Some("donated") => cc,
                        _ => home + cc,
                    };
                    if available == 0 {
                        return Err("spell origin inventory exceeded".to_owned());
                    }
                    // playbook.py:964-1007 only checks total remaining stock.
                    // A restricted repeat cannot stop at its origin boundary.
                    if repeated && origin.is_some() && available != left {
                        return Err("origin-restricted repeat requires a single-origin stock".to_owned());
                    }
                    let compartment = match origin {
                        Some("brewed") => 0,
                        Some("donated") => 1,
                        _ => 2,
                    };
                    spell_demand.entry(spell.to_owned()).or_default()[compartment]
                        += if repeated { available } else { 1 };
                }
                "ability" => {
                    equipment(step, genome)?;
                    if !abilities.insert(what.to_owned()) {
                        return Err("hero ability used twice".to_owned());
                    }
                    amount(step, 1, 1)?;
                }
                "release_siege" => {
                    amount(step, 1, 1)?;
                    if genome.siege.is_none() || !what.is_empty() && genome.siege.as_deref() != Some(what) {
                        return Err("release requires selected siege".to_owned());
                    }
                    releases += 1;
                    if releases > 1 {
                        return Err("siege released twice".to_owned());
                    }
                }
                "redeploy" => {
                    amount(step, 1, 1)?;
                    redeploys += 1;
                    if recalls == 0 || redeploys > recalls || !what.is_empty() && !refs.units.contains(what) {
                        return Err("redeploy requires Recall or Portal Pendant inventory".to_owned());
                    }
                }
                _ => return Err(format!("unknown action: {action}")),
            }
            Ok(())
        };
        spend().map_err(|reason| format!("step {index}: {reason}"))?;
    }
    for (spell, [home_demand, cc_demand, unrestricted]) in spell_demand {
        let home = brewed.get(&spell).copied().unwrap_or(0);
        let cc = donated.get(&spell).copied().unwrap_or(0);
        if home_demand > home
            || cc_demand > cc
            || home_demand + cc_demand + unrestricted > home + cc
        {
            return Err(format!("spell origin inventory exceeded: {spell}"));
        }
        // playbook.py:1155-1241 reserves spell kinds, not origins. Unrestricted
        // casts (including fallback after a skipped step) consume brewed first.
        // A later brewed-only cast is unsafe while any donated stock exists.
        // Donated-only finite casts are safe: the kind reservation and brewed
        // first selection leave their required donated copies until they fire.
        if home_demand > 0 && cc > 0 {
            return Err(format!("brewed-only cast can be starved by unrestricted casts: {spell}"));
        }
    }
    for hero in &genome.heroes {
        if stock.get(&hero.hero).copied().unwrap_or(0) != 0 {
            return Err(format!("selected hero has no deployment: {}", hero.hero));
        }
    }
    let mut done = BTreeSet::new();
    for id in graph.keys() {
        acyclic(id, &graph, &mut BTreeSet::new(), &mut done)?;
    }
    Ok(())
}
