//! Playbook construction and legality; playbook.py:1387-2100, plans.py:523-945.
//! No battle is constructed and no Python process is needed by this module.

use std::path::Path;

use crate::armies::{
    self, array, field, items, list, object, put, python_value, remove, string, ArmyLibrary,
};
use crate::json::Json;
use crate::plans::{flag, is_hero, number, spell_key, spell_name, text, truth};
use crate::stats::{self, Level, Stats};

#[derive(Clone, Debug)]
pub struct CompileOptions {
    pub playbooks: bool,
    pub flank_offset: f64,
    pub charge_side: Option<String>,
    pub overrides: Json,
    pub tactics: Option<Vec<f64>>,
    /// Enforce the live account's inventory and production/capacity rules.
    pub account: bool,
}

impl Default for CompileOptions {
    fn default() -> Self {
        Self {
            playbooks: true,
            flank_offset: 0.9,
            charge_side: None,
            overrides: object(),
            tactics: None,
            account: false,
        }
    }
}

pub struct Compiler<'a> {
    pub library: ArmyLibrary,
    pub stats: &'a Stats,
    pub playbooks: Vec<(String, Json)>,
    pub gaps: Option<(f64, f64)>,
    pub pace: f64,
    siege_caps: Json,
}

impl<'a> Compiler<'a> {
    pub fn load(root: &Path, stats: &'a Stats) -> Result<Self, String> {
        let library = ArmyLibrary::load(root, stats)?;
        let mut paths = std::fs::read_dir(root.join("data/playbooks"))
            .map_err(|error| error.to_string())?
            .map(|entry| {
                entry
                    .map(|value| value.path())
                    .map_err(|error| error.to_string())
            })
            .collect::<Result<Vec<_>, _>>()?;
        paths.sort();
        let mut playbooks = Vec::new();
        for path in paths {
            if path.extension().and_then(|ext| ext.to_str()) == Some("json") {
                let name = path
                    .file_stem()
                    .and_then(|name| name.to_str())
                    .ok_or("Invalid playbook filename")?;
                let book = armies::read_json(&path)?;
                if book.get("steps").is_some() {
                    playbooks.push((name.to_owned(), book));
                }
            }
        }
        let gap_path = root.join("data/playbook-gaps.json");
        let gaps = if std::env::var("BASELAB_GAPS").as_deref() != Ok("0") && gap_path.exists() {
            let value = armies::read_json(&gap_path)?;
            Some((
                value.at("same_group").at("median").f64(),
                value.at("group_change").at("median").f64(),
            ))
        } else {
            None
        };
        let pace = std::env::var("BASELAB_PACE")
            .unwrap_or_else(|_| "1.0".to_owned())
            .parse::<f64>()
            .map_err(|_| "Invalid BASELAB_PACE")?;
        if !pace.is_finite() {
            return Err("BASELAB_PACE must be finite".to_owned());
        }
        let siege_caps = armies::read_json(&root.join("rust/data/clan_castle.json"))?;
        Ok(Self {
            library,
            stats,
            playbooks,
            gaps,
            pace,
            siege_caps,
        })
    }

    pub fn plan_for_build(
        &self,
        build: &Json,
        angle: f64,
        seed: i64,
        options: &CompileOptions,
    ) -> Result<Json, String> {
        crate::content::validate_loadouts(build).map_err(|error| error.to_string())?;
        let mut build = build.clone();
        if options.account {
            put(&mut build, "own_levels", Json::Bool(true));
        }
        let base = armies::compose(&self.library, self.stats, &build, angle, seed)?;
        let book = if options.playbooks {
            // output/research/usage/super-dragon.md: use dragon.json's variant;
            // ordinary Yeti has no cited book and keeps the generic plan.
            // https://clashofclans.fandom.com/wiki/Super_Dragon
            armies::family_of(&build)
                .map(|family| {
                    if family == "super-dragon" {
                        "dragon"
                    } else {
                        family
                    }
                })
                .and_then(|family| self.playbooks.iter().find(|(name, _)| name == family))
        } else {
            None
        };
        let mut plan = if let Some((_, book)) = book {
            self.from_playbook(book, &build, base, seed, options)?
        } else {
            base
        };
        if let Some(tactics) = &options.tactics {
            apply_tactics(&mut plan, tactics)?;
        }
        Ok(plan)
    }

    pub fn compile(
        &self,
        build: &Json,
        angle: f64,
        seed: i64,
        options: &CompileOptions,
    ) -> Result<Json, String> {
        let mut plan = self.plan_for_build(build, angle, seed, options)?;
        self.require_legal(&mut plan)?;
        if options.account {
            let problems = self.account_legal(build, &plan);
            if !problems.is_empty() {
                return Err(format!("Illegal account army: {}", problems.join("; ")));
            }
        }
        Ok(plan)
    }

    // playbook.py:1957-2100: only public dataclass fields are copied; implicit
    // InitVars and runtime state are freshly constructed, never copied.
    fn from_playbook(
        &self,
        pb: &Json,
        build: &Json,
        mut plan: Json,
        seed: i64,
        options: &CompileOptions,
    ) -> Result<Json, String> {
        put(&mut plan, "$type", string("PlaybookPlan"));
        put(&mut plan, "auto_revive", Json::Bool(false));
        let event_ruleset = pb
            .get("event_ruleset")
            .cloned()
            .unwrap_or_else(|| field(&plan, "event_ruleset"));
        put(&mut plan, "event_ruleset", event_ruleset);
        let opening = options
            .overrides
            .get("__opening__")
            .cloned()
            .unwrap_or_else(object);
        if let Some(mode) = opening.get("snipe_mode") {
            if !matches!(mode, Json::Str(value) if matches!(value.as_str(), "off" | "value" | "aggressive"))
            {
                return Err(format!(
                    "Unknown snipe mode {}",
                    text(&opening, "snipe_mode", "")
                ));
            }
            if mode.str() != "value" {
                put(&mut plan, "snipe_mode", mode.clone());
            }
        }
        if opening
            .get("snipe_exposed")
            .is_some_and(|value| !truth(value))
        {
            put(&mut plan, "snipe_exposed", Json::Bool(false));
        }
        let mut inventory = Json::Obj(items(build, "troops"));
        if let Some(siege) = plan.at("siege").opt_str() {
            remove(&mut inventory, siege);
            put(&mut inventory, siege, Json::Num(1.0));
        }
        let heroes = list(build, "heroes");
        let selected = options
            .overrides
            .get("__variants__")
            .and_then(|value| value.get("names"))
            .filter(|value| !value.is_null());
        let variants =
            self.pick_variants(pb, &inventory, heroes, plan.at("spells"), &plan, selected)?;
        let mut steps = fit_steps(
            &variants,
            &inventory,
            heroes,
            plan.at("spells"),
            list(&plan, "cc_troops"),
        )?;
        add_spell_support(pb, &mut steps, plan.at("spells"));
        // output/research/usage/invisibility-spell.md: cover the first hero
        // independently of the second hero's gate.
        // https://clashofclans.fandom.com/wiki/Invisibility_Spell
        let charge: Vec<String> = steps
            .iter()
            .filter(|step| {
                text(step, "action", "") == "deploy"
                    && text(step, "group", "") == "charge"
                    && is_hero(text(step, "what", ""))
            })
            .map(|step| text(step, "id", "").to_owned())
            .collect();
        if let Some(first) = charge.first() {
            for step in &mut steps {
                let when = field(step, "when");
                if text(step, "what", "") == "Invisibility Spell"
                    && text(step, "at", "") == "group:charge"
                    && charge
                        .iter()
                        .skip(1)
                        .any(|id| id == text(&when, "after", ""))
                    && !flag(&when, "delay")
                {
                    put(step, "when", after(first, 0.0));
                }
            }
        }
        apply_roles(&mut steps, build, &options.overrides);
        if let Some(gaps) = self.gaps {
            add_waits(&mut steps, gaps, self.pace);
        }
        // playbook.py:2035-2052: cadence uses the assigned pet, before overrides.
        for step in &mut steps {
            if text(step, "what", "") != "Invisibility Spell" || !flag(step, "every") {
                continue;
            }
            let at = text(step, "at", "");
            if let Some((_, hero)) = at.split_once(':') {
                let fox = plan
                    .at("loadouts")
                    .get(hero)
                    .is_some_and(|loadout| text(loadout, "pet", "") == "Spirit Fox");
                if is_hero(hero) && !fox {
                    put(step, "every", Json::Num(4.0));
                    let mut citations = list(step, "cite").to_vec();
                    citations.push(Json::Obj(vec![
                        ("video".to_owned(), string("L_LKqcL56NE")),
                        ("t".to_owned(), Json::Num(63.8)),
                        (
                            "quote".to_owned(),
                            string("invisibility spells every 4 seconds to"),
                        ),
                    ]));
                    put(step, "cite", Json::Arr(citations));
                }
            }
        }
        apply_overrides(&mut steps, &options.overrides)?;
        if build.get("warden_mode").is_none()
            && warden_walk(&steps, number(&inventory, "Healer", 0.0) > 0.0)
        {
            put(&mut plan, "warden_mode", string("ground"));
        }
        put(&mut plan, "inventory", inventory);
        put(&mut plan, "steps", Json::Arr(steps));
        put(&mut plan, "flank_offset", Json::Num(options.flank_offset));
        let side = options
            .charge_side
            .as_deref()
            .unwrap_or(if seed.rem_euclid(2) == 0 {
                "left"
            } else {
                "right"
            });
        if !matches!(side, "left" | "right") {
            return Err("charge side must be left or right".to_owned());
        }
        put(&mut plan, "charge_side", string(side));
        for key in ["_done", "_next", "_hurt", "_no_target"] {
            put(&mut plan, key, object());
        }
        put(&mut plan, "_cancelled", array([]));
        put(&mut plan, "_entered", array([]));
        put(&mut plan, "_charge_closed", Json::Bool(false));
        put(&mut plan, "log_steps", array([]));
        Ok(plan)
    }

    // playbook.py:677-739: required equipment comes from the action, never from
    // citations. Registry order decides ambiguous full-name matches.
    fn missing_equipment(&self, step: &Json, plan: &Json) -> bool {
        let hero = text(step, "what", "");
        let description = step
            .get("ability")
            .filter(|value| truth(value))
            .unwrap_or(step.at("id"));
        let description = description.str().replace('_', " ").to_lowercase();
        // A list of items is read below; only a single name seeds `required`.
        let mut required = match step.get("equipment") {
            Some(Json::Str(name)) if !name.is_empty() => Some(name.clone()),
            _ => None,
        };
        if required.is_none() {
            required = self
                .stats
                .registry
                .obj()
                .iter()
                .find(|(name, record)| {
                    text(record, "kind", "") == "equipment"
                        && record
                            .get("attrs")
                            .and_then(|attrs| attrs.get("raw"))
                            .is_some_and(|raw| text(raw, "User", "") == hero)
                        && description.contains(name.to_lowercase().as_str())
                })
                .map(|(name, _)| name.clone());
        }
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
        for (word, equipment) in aliases {
            if required.is_none() && description.contains(*word) {
                required = Some((*equipment).to_owned());
            }
        }
        if !flag(step, "equipment") {
            let aim = text(step, "aim", "");
            if aim == "arrow" || (aim.starts_with("building:") && hero == "Archer Queen") {
                required = Some("Giant Arrow".to_owned());
            } else if aim == "dash" {
                required = Some("Rocket Backpack".to_owned());
            } else if aim.starts_with("building:") && hero == "Grand Warden" {
                required = Some("Fireball".to_owned());
            }
        }
        let fallback = armies::default_loadout(hero).unwrap_or_else(object);
        let loadout = plan.at("loadouts").get(hero).unwrap_or(&fallback);
        let required: Vec<String> = match step.get("equipment") {
            Some(Json::Arr(names)) if !names.is_empty() => {
                names.iter().map(|name| name.str().to_owned()).collect()
            }
            _ => required.into_iter().collect(),
        };
        // playbook.py _missing_equipment: any-of; one press fires whichever
        // listed item is equipped.
        !required.is_empty()
            && required.iter().all(|item| {
                !list(loadout, "equipment").contains(&string(item))
                    || flag(plan, "account_equipment")
                        && plan.at("equipment_levels").get(item).is_none()
            })
    }

    fn usable(
        &self,
        step: &Json,
        inventory: &Json,
        heroes: &[Json],
        spells: &Json,
        plan: &Json,
        steps: &[Json],
    ) -> bool {
        let at = text(step, "at", "");
        if let Some((kind, name)) = at.split_once(':') {
            if matches!(kind, "unit" | "unit_ahead")
                && self
                    .stats
                    .registry
                    .get(name)
                    .is_some_and(|record| text(record, "kind", "") == "pet")
            {
                let mut named = Vec::new();
                named_heroes(&field(step, "when"), &mut named);
                if named.is_empty() {
                    named.extend(
                        steps
                            .iter()
                            .filter(|other| {
                                text(other, "action", "") == "deploy"
                                    && is_hero(text(other, "what", ""))
                                    && text(other, "group", "main") == text(step, "group", "main")
                            })
                            .map(|other| field(other, "what")),
                    );
                }
                let named = if named.is_empty() { heroes } else { &named };
                if !named.iter().any(|hero| {
                    let fallback = armies::default_loadout(hero.str()).unwrap_or_else(object);
                    text(
                        plan.at("loadouts").get(hero.str()).unwrap_or(&fallback),
                        "pet",
                        "",
                    ) == name
                }) {
                    return false;
                }
            }
        }
        basic_usable(step, inventory, heroes, spells, false)
    }

    fn feasible(
        &self,
        candidate: &[Json],
        added: &[String],
        inventory: &Json,
        heroes: &[Json],
        spells: &Json,
        plan: &Json,
        check_equipment: bool,
    ) -> Result<bool, String> {
        let mut stock = inventory.clone();
        for hero in heroes {
            put(&mut stock, hero.str(), Json::Num(1.0));
        }
        for (key, count) in spells.obj() {
            put(&mut stock, spell_name(key), count.clone());
        }
        for step in candidate {
            let usable = self.usable(step, inventory, heroes, spells, plan, candidate)
                && (!check_equipment
                    || text(step, "action", "") != "ability"
                    || !self.missing_equipment(step, plan));
            if !usable {
                if added.iter().any(|id| id == text(step, "id", "")) {
                    return Ok(false);
                }
                continue;
            }
            if !matches!(text(step, "action", ""), "deploy" | "spell" | "recall") {
                continue;
            }
            let name = caster_name(step);
            let left = number(&stock, name, 0.0) as i64;
            let amount = step_amount(step, left, 1)?;
            if amount <= 0 || amount > left {
                return Ok(false);
            }
            put(&mut stock, name, Json::Num((left - amount) as f64));
        }
        Ok(true)
    }

    // playbook.py:1430-1526: sort is stable for equal support.
    pub fn pick_variants(
        &self,
        pb: &Json,
        inventory: &Json,
        heroes: &[Json],
        spells: &Json,
        plan: &Json,
        selected: Option<&Json>,
    ) -> Result<Vec<Json>, String> {
        let mut steps = list(pb, "steps").to_vec();
        let mut variants = list(pb, "variants").to_vec();
        variants.sort_by(|a, b| number(b, "support", 0.0).total_cmp(&number(a, "support", 0.0)));
        let mut used = Vec::new();
        for variant in variants {
            let mut replaces = variant
                .get("replaces")
                .filter(|value| truth(value))
                .map_or(&[][..], Json::arr)
                .to_vec();
            let mut current: Vec<Json> = steps
                .iter()
                .filter(|step| replaces.contains(step.at("id")))
                .cloned()
                .collect();
            let requested = selected.is_some_and(|names| names.arr().contains(variant.at("name")));
            if selected.is_some() && !requested {
                continue;
            }
            if replaces.iter().any(|id| used.contains(id))
                || !replaces.is_empty() && current.is_empty()
            {
                continue;
            }
            let mut new = list(&variant, "steps").to_vec();
            for step in &mut new {
                put(step, "variant", field(&variant, "name"));
            }
            // output/research/usage/root-rider.md: siege alternatives retain
            // the charge strategy. https://www.youtube.com/watch?v=C0lnvxJraoM&t=246
            let broken: Vec<Json> = current
                .iter()
                .filter(|step| !self.usable(step, inventory, heroes, spells, plan, &steps))
                .cloned()
                .collect();
            if !requested
                && !broken.is_empty()
                && broken.iter().all(|step| {
                    text(step, "action", "") == "deploy" && armies::is_siege(text(step, "what", ""))
                })
            {
                replaces = broken.iter().map(|step| field(step, "id")).collect();
                current = broken;
                new.retain(|step| {
                    replaces.contains(step.at("id"))
                        && text(step, "action", "") == "deploy"
                        && armies::is_siege(text(step, "what", ""))
                });
            }
            if new.is_empty()
                || !new
                    .iter()
                    .all(|step| self.usable(step, inventory, heroes, spells, plan, &new))
            {
                continue;
            }
            let index = steps
                .iter()
                .position(|step| replaces.contains(step.at("id")))
                .unwrap_or(steps.len());
            // output/research/usage/root-rider.md: preserve the chosen funnel/main roles.
            // https://www.youtube.com/watch?v=C0lnvxJraoM&t=246
            // Clone before rewiring so a rejected variant cannot change retained steps.
            let mut candidate: Vec<Json> = steps
                .iter()
                .filter(|step| !replaces.contains(step.at("id")))
                .cloned()
                .collect();
            candidate.splice(index..index, new.iter().cloned());
            if !requested {
                for old in &current {
                    let replacement = new.iter().find(|step| step.get("id") == old.get("id"));
                    if text(old, "group", "main") != "main"
                        || replacement.is_none_or(|step| text(step, "group", "main") == "main")
                    {
                        continue;
                    }
                    for step in &mut candidate {
                        let when = field(step, "when");
                        if matches!(text(step, "action", ""), "deploy" | "redeploy")
                            && text(step, "group", "main") == "main"
                            && when.get("after") == old.get("id")
                        {
                            let mut parent = field(old, "when");
                            if parent.get("after").is_some() {
                                let delay =
                                    number(&parent, "delay", 0.0) + number(&when, "delay", 0.0);
                                put(&mut parent, "delay", Json::Num(delay));
                                put(step, "when", parent);
                            } else if let Some(t) = parent.get("t") {
                                put(step, "when", time(t.f64() + number(&when, "delay", 0.0)));
                            }
                        }
                    }
                }
            }
            let ids: Vec<String> = new
                .iter()
                .map(|step| text(step, "id", "").to_owned())
                .collect();
            if !self.feasible(&candidate, &ids, inventory, heroes, spells, plan, true)? {
                if requested {
                    return Err(format!(
                        "Infeasible playbook variant: {}",
                        variant.at("name").str()
                    ));
                }
                continue;
            }
            let current_ids: Vec<String> = current
                .iter()
                .map(|step| text(step, "id", "").to_owned())
                .collect();
            if !requested
                && (replaces.is_empty()
                    || current
                        .iter()
                        .all(|step| self.usable(step, inventory, heroes, spells, plan, &steps))
                        // Missing equipment skips its step, rather than silently
                        // substituting an ability with no named requirement.
                        && self.feasible(
                            &steps,
                            &current_ids,
                            inventory,
                            heroes,
                            spells,
                            plan,
                            false,
                        )?)
            {
                continue;
            }
            steps = candidate;
            used.extend_from_slice(&replaces);
        }
        if let Some(names) = selected {
            let mut missing: Vec<&str> = names
                .arr()
                .iter()
                .map(Json::str)
                .filter(|name| !steps.iter().any(|step| text(step, "variant", "") == *name))
                .collect();
            missing.sort_unstable();
            missing.dedup();
            if !missing.is_empty() {
                return Err(format!(
                    "Unavailable playbook variants: {}",
                    missing.join(", ")
                ));
            }
        }
        Ok(steps)
    }
}

fn step_amount(step: &Json, left: i64, default: i64) -> Result<i64, String> {
    match step.get("count") {
        None => Ok(default),
        Some(Json::Null) => Ok(left),
        Some(Json::Str(value)) if value == "all" => Ok(left),
        Some(Json::Str(value)) => value
            .parse::<i64>()
            .map_err(|_| format!("Invalid step count {value}")),
        Some(Json::Num(value)) if value.is_finite() => Ok(*value as i64),
        _ => Err("Invalid step count".to_owned()),
    }
}

fn caster_name(step: &Json) -> &str {
    if text(step, "action", "") == "recall" {
        "Recall Spell"
    } else {
        text(step, "what", "")
    }
}

fn have(name: &str, inventory: &Json, heroes: &[Json], spells: &Json) -> bool {
    inventory.get(name).is_some()
        || heroes.contains(&string(name))
        || spell_key(name).is_some_and(|key| number(spells, key, 0.0) != 0.0)
}

fn basic_usable(step: &Json, inventory: &Json, heroes: &[Json], spells: &Json, fit: bool) -> bool {
    let what = text(step, "what", "");
    match text(step, "action", "") {
        "deploy" | "spell" => have(what, inventory, heroes, spells),
        "release_siege" if !fit => have(what, inventory, heroes, spells),
        "recall" => have("Recall Spell", inventory, heroes, spells),
        "ability" => heroes.contains(&string(what)),
        "redeploy" => {
            (what.is_empty() || heroes.contains(&string(what)))
                && (!fit || have("Recall Spell", inventory, heroes, spells))
        }
        _ => true,
    }
}

fn named_heroes(trigger: &Json, out: &mut Vec<Json>) {
    if !matches!(trigger, Json::Obj(_)) {
        return;
    }
    for key in ["inside", "hp_below", "heavy_fire", "dead"] {
        if let Some(value @ Json::Str(name)) = trigger.get(key) {
            if is_hero(name) {
                out.push(value.clone());
            }
        }
    }
    for key in ["all", "any"] {
        for part in list(trigger, key) {
            named_heroes(part, out);
        }
    }
}

fn assault(hero: &str) -> bool {
    matches!(hero, "Barbarian King" | "Royal Champion" | "Dragon Duke")
}

fn substitute(value: &Json, old: &Json, replacement: &Json) -> Json {
    match value {
        Json::Obj(entries) => Json::Obj(
            entries
                .iter()
                .map(|(key, value)| (key.clone(), substitute(value, old, replacement)))
                .collect(),
        ),
        Json::Arr(entries) => array(
            entries
                .iter()
                .map(|value| substitute(value, old, replacement)),
        ),
        _ if value == old => replacement.clone(),
        _ => value.clone(),
    }
}

struct Relinker<'a> {
    army_units: Vec<Json>,
    bring: Vec<Json>,
    dropped: Vec<Json>,
    casters: Vec<String>,
    spells: &'a Json,
}

impl Relinker<'_> {
    fn absent(&self, name: &Json) -> bool {
        self.army_units.contains(name) && !self.bring.contains(name)
    }

    fn absent_cond(&self, trigger: &Json) -> bool {
        ["inside", "hp_below", "heavy_fire", "dead"]
            .iter()
            .any(|key| trigger.get(key).is_some_and(|value| self.absent(value)))
    }

    // playbook.py:1653-1698. A cycle is malformed input, never an infinite walk.
    fn relink(&self, trigger: &Json, seen: &[String]) -> Result<Json, String> {
        if !matches!(trigger, Json::Obj(_)) {
            return Ok(trigger.clone());
        }
        if self.absent_cond(trigger) {
            return Ok(Json::Null);
        }
        if let Some(after) = trigger.get("after") {
            if let Some(dropped) = self
                .dropped
                .iter()
                .find(|step| step.get("id") == Some(after))
            {
                let id = after.str();
                if seen.iter().any(|value| value == id) {
                    return Err(format!("Cyclic dropped trigger: {id}"));
                }
                let mut seen = seen.to_vec();
                seen.push(id.to_owned());
                let parent = dropped
                    .get("when")
                    .filter(|value| truth(value))
                    .cloned()
                    .unwrap_or_else(|| time(0.0));
                let mut up = self.relink(&parent, &seen)?;
                if up.is_null() {
                    return Ok(up);
                }
                if up.get("after").is_some() {
                    let delay = number(&up, "delay", 0.0) + number(trigger, "delay", 0.0);
                    put(&mut up, "delay", Json::Num(delay));
                } else if let Some(t) = up.get("t") {
                    let t = t.f64() + number(trigger, "delay", 0.0);
                    put(&mut up, "t", Json::Num(t));
                }
                return Ok(up);
            }
        }
        if let Some(name) = trigger.get("spells_left") {
            let name = name.str();
            let name = if crate::plans::SPELL_NAMES
                .iter()
                .any(|(key, _)| *key == name)
            {
                spell_name(name)
            } else {
                name
            };
            if !self.casters.iter().any(|caster| caster == name)
                && spell_key(name)
                    .is_some_and(|key| number(self.spells, key, 0.0) > number(trigger, "n", 0.0))
            {
                if seen.iter().any(|value| value == name) {
                    return Err(format!("Cyclic spell trigger: {name}"));
                }
                let mut seen = seen.to_vec();
                seen.push(name.to_owned());
                let parent = self
                    .dropped
                    .iter()
                    .find(|step| {
                        matches!(text(step, "action", ""), "spell" | "recall")
                            && caster_name(step) == name
                    })
                    .and_then(|step| step.get("when"))
                    .filter(|value| truth(value))
                    .cloned()
                    .unwrap_or_else(|| time(0.0));
                return self.relink(&parent, &seen);
            }
        }
        let mut out = trigger.clone();
        for key in ["all", "any"] {
            if let Some(parts) = trigger.get(key) {
                let parts = parts
                    .arr()
                    .iter()
                    .map(|part| self.relink(part, seen))
                    .collect::<Result<Vec<_>, _>>()?;
                let parts: Vec<Json> = parts.into_iter().filter(|part| !part.is_null()).collect();
                if parts.is_empty() {
                    return Ok(Json::Null);
                }
                put(&mut out, key, Json::Arr(parts));
            }
        }
        Ok(out)
    }
}

fn time(t: f64) -> Json {
    Json::Obj(vec![("t".to_owned(), Json::Num(t))])
}
fn after(id: &str, delay: f64) -> Json {
    Json::Obj(vec![
        ("after".to_owned(), string(id)),
        ("delay".to_owned(), Json::Num(delay)),
    ])
}

fn rest_step(
    id: &str,
    what: &Json,
    count: Json,
    at: &str,
    group: Option<&str>,
    when: Json,
) -> Json {
    let mut out = Json::Obj(vec![
        ("id".to_owned(), string(id)),
        ("action".to_owned(), string("deploy")),
        ("what".to_owned(), what.clone()),
        ("count".to_owned(), count),
        ("at".to_owned(), string(at)),
        ("when".to_owned(), when),
        ("uncited".to_owned(), Json::Bool(true)),
        ("cite".to_owned(), array([])),
    ]);
    if let Some(group) = group {
        put(&mut out, "group", string(group));
    }
    out
}

// playbook.py:1529-1786, including the comparable uncited-hero role rule.
pub fn fit_steps(
    source: &[Json],
    inventory: &Json,
    heroes: &[Json],
    spells: &Json,
    cc: &[Json],
) -> Result<Vec<Json>, String> {
    let templates: Vec<&Json> = source
        .iter()
        .filter(|step| text(step, "action", "") == "deploy" && is_hero(text(step, "what", "")))
        .collect();
    let mut replacements = Vec::new();
    let mut steps = source.to_vec();
    for hero in heroes {
        if templates.iter().any(|step| step.get("what") == Some(hero)) {
            continue;
        }
        let comparable: Vec<&Json> = templates
            .iter()
            .copied()
            .filter(|step| assault(text(step, "what", "")) == assault(hero.str()))
            .collect();
        let choices = if comparable.is_empty() {
            &templates
        } else {
            &comparable
        };
        let template = choices.iter().min_by_key(|step| {
            (
                heroes.contains(step.at("what")),
                replacements.contains(step.at("what")),
                text(step, "group", "main") == "charge",
                text(step, "what", "") == "Grand Warden",
            )
        });
        let Some(template) = template else {
            continue;
        };
        replacements.push(field(template, "what"));
        let mut at = text(template, "at", "edge:main");
        let old = template.at("what");
        if at == format!("unit:{}", old.str()) || at == format!("unit_ahead:{}", old.str()) {
            at = "edge:main";
        }
        steps.push(rest_step(
            &format!("rest-{}", hero.str()),
            hero,
            Json::Num(1.0),
            at,
            Some(text(template, "group", "main")),
            substitute(&field(template, "when"), old, hero),
        ));
    }
    let mut bring: Vec<Json> = inventory
        .obj()
        .iter()
        .map(|(name, _)| string(name))
        .chain(heroes.iter().cloned())
        .collect();
    bring.extend(cc.iter().map(|entry| {
        if matches!(entry, Json::Str(_)) {
            entry.clone()
        } else {
            entry
                .get("name")
                .filter(|value| truth(value))
                .cloned()
                .unwrap_or_else(|| field(entry, "type"))
        }
    }));
    let mut army_units: Vec<Json> = steps
        .iter()
        .filter(|step| text(step, "action", "") == "deploy")
        .map(|step| field(step, "what"))
        .collect();
    army_units.extend(
        [
            "Barbarian King",
            "Archer Queen",
            "Grand Warden",
            "Royal Champion",
            "Minion Prince",
            "Dragon Duke",
        ]
        .into_iter()
        .map(string),
    );
    let mut relinker = Relinker {
        army_units,
        bring,
        dropped: Vec::new(),
        casters: Vec::new(),
        spells,
    };
    for step in &steps {
        let missing_at = text(step, "at", "")
            .split_once(':')
            .is_some_and(|(kind, name)| {
                matches!(kind, "unit" | "unit_ahead") && relinker.absent(&string(name))
            });
        if missing_at
            || (text(step, "action", "") != "deploy" && relinker.absent_cond(&field(step, "when")))
            || !basic_usable(step, inventory, heroes, spells, true)
        {
            relinker.dropped.push(step.clone());
        }
    }
    relinker.casters = steps
        .iter()
        .filter(|step| {
            !relinker
                .dropped
                .iter()
                .any(|dropped| dropped.get("id") == step.get("id"))
                && matches!(text(step, "action", ""), "spell" | "recall")
        })
        .map(|step| caster_name(step).to_owned())
        .collect();
    let mut kept = Vec::new();
    let mut orphans = Vec::new();
    for mut step in steps {
        if relinker
            .dropped
            .iter()
            .any(|dropped| dropped.get("id") == step.get("id"))
        {
            continue;
        }
        let when = relinker.relink(&field(&step, "when"), &[])?;
        if flag(&step, "when") && when.is_null() {
            orphans.push(field(&step, "id"));
        }
        put(&mut step, "when", when);
        if flag(&step, "until") {
            let until = relinker.relink(step.at("until"), &[])?;
            put(&mut step, "until", until);
        }
        kept.push(step);
    }
    let mentioned: Vec<Json> = kept
        .iter()
        .filter(|step| text(step, "action", "") == "deploy")
        .map(|step| field(step, "what"))
        .collect();
    // output/research/usage/dragon.md: Dragons precede supporting Riders.
    // https://www.youtube.com/watch?v=55I-qks9qdI
    // Policy: leftovers follow the variant's main troop, never its lead siege.
    let anchor = kept
        .iter()
        .find(|step| {
            text(step, "action", "") == "deploy"
                && text(step, "at", "edge:main") == "edge:main"
                && text(step, "group", "main") == "main"
                && !is_hero(text(step, "what", ""))
                && !armies::is_siege(text(step, "what", ""))
        })
        .map_or_else(|| time(15.0), |step| after(text(step, "id", ""), 1.0));
    for step in &mut kept {
        if orphans.contains(step.at("id")) {
            let when = if step.get("id") == anchor.get("after") {
                time(15.0)
            } else {
                anchor.clone()
            };
            put(step, "when", when);
        }
    }
    for (name, count) in inventory.obj() {
        if truth(count) && !mentioned.contains(&string(name)) {
            // output/research/usage/super-wall-breaker.md: breach with the push.
            // https://blueprintcoc.com/blogs/town-hall-16/top-3-th16-army-links
            let breach = matches!(name.as_str(), "Wall Breaker" | "Super Wall Breaker")
                && anchor.get("after").is_some();
            let when = if breach {
                after(text(&anchor, "after", ""), 0.0)
            } else {
                anchor.clone()
            };
            kept.push(rest_step(
                &format!("rest-{name}"),
                &string(name),
                string("all"),
                "edge:main",
                None,
                when,
            ));
            if breach {
                let id = format!("rest-{name}");
                for step in &mut kept {
                    let mut when = field(step, "when");
                    if text(step, "id", "") != id
                        && text(step, "action", "") == "deploy"
                        && when.get("after") == anchor.get("after")
                    {
                        put(&mut when, "after", string(&id));
                        put(step, "when", when);
                    }
                }
            }
        }
    }
    for hero in heroes {
        if !mentioned.contains(hero) {
            kept.push(rest_step(
                &format!("rest-{}", hero.str()),
                hero,
                Json::Num(1.0),
                "edge:main",
                Some("main"),
                anchor.clone(),
            ));
        }
    }
    for (name, count) in inventory.obj() {
        let mine: Vec<&Json> = kept
            .iter()
            .filter(|step| {
                text(step, "action", "") == "deploy"
                    && text(step, "what", "") == name
                    && !flag(step, "uncited")
            })
            .collect();
        if !truth(count)
            || is_hero(name)
            || mine.is_empty()
            || mine.iter().any(|step| {
                step.get("count")
                    .is_none_or(|count| count.is_null() || count == &string("all"))
            })
        {
            continue;
        }
        let used = mine
            .iter()
            .map(|step| step_amount(step, 0, 0))
            .collect::<Result<Vec<_>, _>>()?
            .iter()
            .sum::<i64>();
        if used >= count.i64() {
            continue;
        }
        let when = Json::Obj(vec![(
            "any".to_owned(),
            array([
                after(text(mine[mine.len() - 1], "id", ""), 4.5),
                time(150.0),
            ]),
        )]);
        kept.push(rest_step(
            &format!("rest2-{name}"),
            &string(name),
            string("all"),
            "edge:main",
            None,
            when,
        ));
    }
    Ok(kept)
}

fn collect_groups(condition: &Json, groups: &mut Vec<String>) {
    for key in ["group_inside", "near_th", "defenders_near"] {
        if let Some(value) = condition.get(key) {
            groups.push(value.str().to_owned());
        }
    }
    for key in ["all", "any"] {
        for part in list(condition, key) {
            collect_groups(part, groups);
        }
    }
}

fn add_spell_support(pb: &Json, steps: &mut Vec<Json>, spells: &Json) {
    // output/research/usage/invisibility-spell.md: protect the cited recipient.
    // https://clashofclans.fandom.com/wiki/Invisibility_Spell
    // Only fill an unnamed spell whose recipient still has a deployment.
    for step in list(pb, "spell_support") {
        let name = text(step, "what", "");
        let target = text(step, "at", "")
            .split_once(':')
            .expect("support recipient")
            .1;
        if spell_key(name).is_none_or(|kind| number(spells, kind, 0.0) <= 0.0)
            || steps.iter().any(|other| {
                text(other, "action", "") == "spell" && text(other, "what", "") == name
            })
        {
            continue;
        }
        if steps
            .iter()
            .any(|other| text(other, "action", "") == "deploy" && text(other, "what", "") == target)
        {
            steps.push(step.clone());
        }
    }
}

fn apply_roles(steps: &mut [Json], build: &Json, overrides: &Json) {
    let mut referenced = Vec::new();
    for step in steps.iter() {
        let choices = overrides.get(text(step, "id", ""));
        for key in ["at", "aim"] {
            let anchor = choices
                .and_then(|choices| choices.get(key))
                .or_else(|| step.get(key));
            if let Some(Json::Str(anchor)) = anchor {
                if let Some((kind, group)) = anchor.split_once(':') {
                    if matches!(kind, "group" | "threat" | "defenders") {
                        referenced.push(if group.is_empty() { "main" } else { group }.to_owned());
                    }
                }
            }
        }
        collect_groups(&field(step, "when"), &mut referenced);
        collect_groups(&field(step, "until"), &mut referenced);
    }
    for step in steps {
        if text(step, "action", "") != "deploy"
            || !list(build, "heroes").contains(&field(step, "what"))
            || referenced
                .iter()
                .any(|group| group == text(step, "group", "main"))
        {
            continue;
        }
        let role = if list(build, "funnel").contains(&field(step, "what")) {
            Some(("edge:funnel", "funnel"))
        } else if list(build, "push").contains(&field(step, "what")) {
            Some(("edge:main", "main"))
        } else {
            None
        };
        if let Some((at, group)) = role {
            put(step, "at", string(at));
            put(step, "group", string(group));
        }
    }
}

fn quotes(step: &Json) -> String {
    list(step, "cite")
        .iter()
        .map(|cite| text(cite, "quote", ""))
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn immediate(step: &Json, previous: &Json) -> bool {
    let words = quotes(step);
    if [
        "immediately",
        "right away",
        "straight away",
        "instantly",
        "quick succession",
    ]
    .iter()
    .any(|word| words.contains(*word))
    {
        return true;
    }
    if text(previous, "what", "") != "Invisibility Spell" {
        return false;
    }
    if text(step, "what", "") == "Invisibility Spell" && words.contains("invis invis") {
        return true;
    }
    let before = quotes(previous);
    text(step, "action", "") == "ability"
        && text(step, "what", "") == "Grand Warden"
        && words.contains("fireball")
        && (before.contains("invis invis") || before.contains("quick succession"))
}

fn fix_wait(
    trigger: &Json,
    step: &Json,
    source: &[Json],
    walk: &[String],
    gaps: (f64, f64),
    pace: f64,
) -> Json {
    if !matches!(trigger, Json::Obj(_)) {
        return trigger.clone();
    }
    let mut out = trigger.clone();
    if let Some(previous) = trigger
        .get("after")
        .and_then(|id| source.iter().find(|step| step.get("id") == Some(id)))
    {
        // output/research/usage/root-rider.md: one paced smash deployment chain.
        // https://www.youtube.com/watch?v=g9UjZ9xFQOU&t=169
        let smash = matches!(text(step, "action", ""), "deploy" | "redeploy")
            && text(step, "group", "main") == "main"
            && text(previous, "group", "main") == "main"
            && matches!(text(previous, "action", ""), "deploy" | "redeploy");
        let protection = text(step, "what", "") == "Invisibility Spell"
            && text(step, "group", "main") == "charge"
            && text(previous, "action", "") == "deploy"
            && text(previous, "group", "") == "charge"
            && is_hero(text(previous, "what", ""));
        if !flag(trigger, "delay")
            && !smash
            && !protection
            && !walk.iter().any(|id| id == text(step, "id", ""))
            && !immediate(step, previous)
        {
            let gap = if text(previous, "group", "main") == text(step, "group", "main") {
                gaps.0
            } else {
                gaps.1
            };
            let action_time = match text(previous, "action", "") {
                "deploy" => pace * (0.6 + 0.133 * 1.0),
                "ability" => pace * 0.3,
                _ => pace * 0.6,
            };
            put(&mut out, "delay", Json::Num((gap - action_time).max(0.0)));
        }
    }
    for key in ["all", "any"] {
        if let Some(parts) = trigger.get(key) {
            put(
                &mut out,
                key,
                array(
                    parts
                        .arr()
                        .iter()
                        .map(|part| fix_wait(part, step, source, walk, gaps, pace)),
                ),
            );
        }
    }
    out
}

// playbook.py:1797-1878: walk preparation chains and explicit immediate cites
// retain their zero delays; inherited hero roles receive measured waits.
pub fn add_waits(steps: &mut [Json], gaps: (f64, f64), pace: f64) {
    let source = steps.to_vec();
    let mut walk = Vec::new();
    for step in &source {
        if text(step, "action", "") != "deploy" || text(step, "what", "") != "Healer" {
            continue;
        }
        let mut chain = Vec::new();
        let mut current = step;
        while !chain.contains(&text(current, "id", "").to_owned()) {
            chain.push(text(current, "id", "").to_owned());
            let Some(previous) = current.get("when").and_then(|when| when.get("after")) else {
                break;
            };
            let Some(parent) = source.iter().find(|step| step.get("id") == Some(previous)) else {
                break;
            };
            current = parent;
            if text(current, "action", "") == "deploy"
                && text(current, "what", "") == "Grand Warden"
            {
                if text(current, "group", "main") == "charge" {
                    walk.extend(chain);
                }
                break;
            }
        }
    }
    for step in steps {
        if !flag(step, "uncited")
            || text(step, "action", "") == "deploy" && is_hero(text(step, "what", ""))
        {
            let when = fix_wait(&field(step, "when"), step, &source, &walk, gaps, pace);
            put(step, "when", when);
        }
    }
}

// playbook.py:1881-1918: only direct/`all` after conditions accept delay overrides.
pub fn apply_overrides(steps: &mut [Json], overrides: &Json) -> Result<(), String> {
    for step in steps {
        let Some(choices) = overrides.get(text(step, "id", "")) else {
            continue;
        };
        for (key, value) in choices.obj() {
            match key.as_str() {
                "delay" => {
                    let delay = match value {
                        Json::Str(value) => {
                            value.parse::<f64>().map_err(|_| "Invalid delay override")?
                        }
                        _ => value.f64(),
                    };
                    let mut when = field(step, "when");
                    if when.get("after").is_some() {
                        put(&mut when, "delay", Json::Num(delay));
                    } else if let Some(parts) = when.get("all") {
                        let mut parts = parts.arr().to_vec();
                        for part in &mut parts {
                            if part.get("after").is_some() {
                                put(part, "delay", Json::Num(delay));
                            }
                        }
                        put(&mut when, "all", Json::Arr(parts));
                    }
                    if !when.is_null() {
                        put(step, "when", when);
                    }
                }
                "aim" if value.is_null() => remove(step, "aim"),
                "at" | "aim" | "every" => put(step, key, value.clone()),
                _ => return Err(format!("unknown override field {key}")),
            }
        }
    }
    Ok(())
}

// playbook.py:warden_walk: compilation and learned installation share this rule.
// output/research/usage/grand-warden-walk.md: Healers require ground mode.
// https://clashofclans.fandom.com/wiki/Grand_Warden
pub fn warden_walk(steps: &[Json], has_healers: bool) -> bool {
    has_healers
        && steps.iter().any(|healer| {
            text(healer, "action", "") == "deploy"
                && text(healer, "what", "") == "Healer"
                && healer.get("count") != Some(&Json::Num(0.0))
                && (matches!(
                    text(healer, "at", ""),
                    "unit:Grand Warden" | "unit_ahead:Grand Warden"
                ) || steps.iter().any(|warden| {
                    text(warden, "action", "") == "deploy"
                        && text(warden, "what", "") == "Grand Warden"
                        && text(warden, "group", "main") == text(healer, "group", "main")
                        && warden.get("at") == healer.get("at")
                        && text(warden, "at", "").starts_with("edge:")
                        && follows(&field(healer, "when"), text(warden, "id", ""), steps, &[])
                }))
        })
}

fn follows(trigger: &Json, previous: &str, steps: &[Json], seen: &[String]) -> bool {
    if let Some(t) = trigger.get("t") {
        return steps
            .iter()
            .find(|step| text(step, "id", "") == previous)
            .and_then(|step| step.get("when"))
            .and_then(|when| when.get("t"))
            .is_some_and(|start| t.f64() >= start.f64());
    }
    if let Some(reference) = trigger.get("after") {
        if reference.str() == previous {
            return true;
        }
        if seen.iter().any(|id| id == reference.str()) {
            return false;
        }
        let Some(step) = steps.iter().find(|step| step.get("id") == Some(reference)) else {
            return false;
        };
        let mut seen = seen.to_vec();
        seen.push(reference.str().to_owned());
        return follows(&field(step, "when"), previous, steps, &seen);
    }
    if let Some(parts) = trigger.get("all") {
        return parts
            .arr()
            .iter()
            .any(|part| follows(part, previous, steps, seen));
    }
    if let Some(parts) = trigger.get("any") {
        return !parts.arr().is_empty()
            && parts
                .arr()
                .iter()
                .all(|part| follows(part, previous, steps, seen));
    }
    false
}

pub const TACTIC_DEFAULTS: [f64; 19] = [
    0.0, 1.0, 0.0, 0.0, 1.0, 1.0, 8.0, 10.0, 0.0, 0.0, 1.5, 0.0, 0.0, 0.0, 0.0, 0.35, 25.0, 0.0,
    0.0,
];
pub const TACTIC_NAMES: [&str; 19] = [
    "angle",
    "funnel_scale",
    "funnel_shift",
    "flank_lat",
    "spread",
    "support_spread",
    "main_min",
    "main_gap",
    "heroes_push",
    "freeze_pick",
    "revive_delay",
    "charge_pick",
    "charge_healers",
    "charge_lat",
    "charge_at",
    "charge_recall_hp",
    "charge_len",
    "recall_funnel",
    "split_main",
];

// tactics.py:135-164: generic knobs are explicitly rejected for playbooks.
pub fn apply_tactics(plan: &mut Json, values: &[f64]) -> Result<(), String> {
    if values.len() < 11 || values.len() > 19 || values.iter().any(|value| !value.is_finite()) {
        return Err("Tactics require 11 to 19 finite values".to_owned());
    }
    if text(plan, "$type", "") != "PlaybookPlan" {
        return Err("Native tactic compilation currently requires a PlaybookPlan".to_owned());
    }
    let supported = [0, 1, 4, 5, 9, 10];
    let unsupported: Vec<&str> = values
        .iter()
        .enumerate()
        .filter(|(index, value)| !supported.contains(index) && **value != TACTIC_DEFAULTS[*index])
        .map(|(index, _)| TACTIC_NAMES[index])
        .collect();
    if !unsupported.is_empty() {
        return Err(format!(
            "Playbook does not execute generic tactic knobs: {}",
            unsupported.join(", ")
        ));
    }
    let tau = 2.0 * std::f64::consts::PI;
    // CPython float modulo first uses fmod, then adjusts the sign, preserving
    // +0.0 and rounding at the upper endpoint (tactics.py:140).
    let mut angle = values[0] % tau;
    if angle < 0.0 {
        angle += tau;
    }
    if angle == 0.0 {
        angle = 0.0;
    }
    put(plan, "angle", Json::Num(angle));
    let offset = plan.at("flank_offset").f64() * values[1];
    put(plan, "flank_offset", Json::Num(offset));
    let freeze_options: &[&[&str]] = &[
        &[],
        &["inferno"],
        &["mono"],
        &["scatter"],
        &["eagle"],
        &["xbow"],
        &["inferno", "mono"],
        &["scatter", "inferno"],
    ];
    let pick = values[9] as i64;
    let pick = if pick < 0 {
        freeze_options.len() as i64 + pick
    } else {
        pick
    };
    let choice = freeze_options
        .get(pick as usize)
        .ok_or("freeze_pick is out of range")?;
    put(
        plan,
        "freeze_first",
        array(choice.iter().map(|name| string(name))),
    );
    put(plan, "revive_delay", Json::Num(values[10]));
    let mut steps = list(plan, "steps").to_vec();
    for step in &mut steps {
        if text(step, "action", "") != "deploy"
            || plan.at("loadouts").get(text(step, "what", "")).is_some()
        {
            continue;
        }
        let scale = if text(step, "what", "") == "Healer" {
            values[5]
        } else {
            values[4]
        };
        if scale != 1.0 {
            let spread = (number(step, "spread", 1.0) * scale).max(0.1);
            put(step, "spread", Json::Num(spread));
        }
    }
    put(plan, "steps", Json::Arr(steps));
    Ok(())
}

fn integer(value: &Json, name: &str, minimum: i64) -> Result<i64, String> {
    if let Json::Num(number) = value {
        if number.is_finite()
            && number.fract() == 0.0
            && *number >= minimum as f64
            && *number <= i32::MAX as f64
        {
            return Ok(*number as i64);
        }
    }
    Err(format!("Invalid {name} level {}", python_value(value)))
}

fn quantities(plan: &Json) -> Vec<(String, Json)> {
    let mut out: Vec<(String, Json)> = list(plan, "flank")
        .iter()
        .map(|entry| (entry.arr()[0].str().to_owned(), entry.arr()[1].clone()))
        .collect();
    for wave in list(plan, "main").iter().chain(list(plan, "support")) {
        out.extend(
            list(wave, "units")
                .iter()
                .map(|entry| (entry.arr()[0].str().to_owned(), entry.arr()[1].clone())),
        );
    }
    for key in ["cleanup", "breakers"] {
        out.extend(
            list(plan, key)
                .iter()
                .map(|entry| (entry.arr()[0].str().to_owned(), entry.arr()[1].clone())),
        );
    }
    out
}

fn roster(plan: &Json) -> Vec<String> {
    let mut out: Vec<String> = list(plan, "funnel_heroes")
        .iter()
        .map(|entry| entry.arr()[0].str().to_owned())
        .chain(
            list(plan, "push_heroes")
                .iter()
                .map(|hero| hero.str().to_owned()),
        )
        .collect();
    if let Some(hero) = plan.get("charge_hero").filter(|value| truth(value)) {
        out.push(hero.str().to_owned());
    }
    for (name, count) in quantities(plan) {
        if is_hero(&name) {
            out.extend((0..count.i64()).map(|_| name.clone()));
        }
    }
    out
}

impl Compiler<'_> {
    fn record(&self, name: &str) -> Result<&Json, String> {
        self.stats
            .registry
            .get(name)
            .ok_or_else(|| format!("'{name}'"))
    }

    fn row_exists(&self, name: &str, level: i64) -> Result<(), String> {
        if !list(self.record(name)?, "levels")
            .iter()
            .any(|row| row.get("level") == Some(&Json::Num(level as f64)))
        {
            return Err(format!("'{name} has no level {level}'"));
        }
        Ok(())
    }

    fn validate_level(&self, name: &str, level: i64, th: i64) -> Result<(), String> {
        self.record(name)?;
        if self.stats.max_level(name, th).is_none() {
            return Err(format!("{name} is unavailable at Town Hall {th}"));
        }
        self.row_exists(name, level)?;
        if self.stats.required_town_hall(name, &Level::Int(level)) > th as f64 {
            return Err(format!("Illegal {name} level {level} at Town Hall {th}"));
        }
        Ok(())
    }

    fn get(&self, name: &str, level: i64, key: &str) -> f64 {
        self.stats
            .get(name, &Level::Int(level), &[key], Some(0.0))
            .unwrap_or(0.0)
    }

    fn building_level(&self, plan: &Json, name: &str, key: &str) -> i64 {
        let production = match name {
            "Barracks" => Some("barracks"),
            "Dark Barracks" => Some("dbarracks"),
            "Workshop" => Some("workshop"),
            _ => None,
        };
        if let Some(account_key) = production {
            if flag(plan, "account_equipment") {
                return number(self.library.user.at("levels"), account_key, 0.0) as i64;
            }
            return self
                .stats
                .max_level(name, plan.at("town_hall").i64())
                .unwrap_or(0);
        }
        plan.get(key).filter(|value| !value.is_null()).map_or_else(
            || {
                self.stats
                    .max_level(name, plan.at("town_hall").i64())
                    .unwrap_or(0)
            },
            Json::i64,
        )
    }

    fn siege_cap(&self, plan: &Json) -> Result<i64, String> {
        let siege = text(plan, "siege", "");
        let castle = self
            .building_level(plan, "Clan Castle", "clan_castle_level")
            .min(13);
        if castle < 6 {
            return Ok(0);
        }
        let table = list(&self.siege_caps, "tables")
            .iter()
            .find(|table| text(table, "heading", "") == "Siege Machine Level Cap");
        // Derived wiki table: rust/data/clan_castle.json, Siege Machine Level Cap.
        // https://clashofclans.fandom.com/wiki/Clan_Castle
        let value = table
            .and_then(|table| {
                list(table, "rows")
                    .iter()
                    .find(|row| row.arr().first().is_some_and(|name| name == &string(siege)))
            })
            .and_then(|row| row.arr().get((castle - 5) as usize))
            .ok_or_else(|| format!("missing siege donation cap: {siege}, Clan Castle {castle}"))?;
        if value == &string("-") {
            return Ok(0);
        }
        stats::num(value, None)
            .filter(|cap| cap.is_finite() && *cap > 0.0 && cap.fract() == 0.0)
            .map(|cap| cap as i64)
            .ok_or_else(|| format!("invalid siege donation cap: {siege}, Clan Castle {castle}"))
    }

    // plans.py:574-612: donated research uses the Castle's Laboratory cap;
    // brewed research uses the actual Laboratory, with identical row filters.
    pub fn spell_level(&self, plan: &Json, stock: &Json) -> Result<Option<i64>, String> {
        if let Some(value) = stock.get("level").filter(|value| !value.is_null()) {
            return integer(value, text(stock, "name", ""), 1).map(Some);
        }
        let name = stock.at("name").str();
        let donated = text(stock, "origin", "") == "donated";
        let levels = plan.at(if donated {
            "cc_spell_levels"
        } else {
            "spell_levels"
        });
        if let Some(level) = levels.get(name) {
            return integer(level, name, 1).map(Some);
        }
        let lab = if donated {
            let castle = self.building_level(plan, "Clan Castle", "clan_castle_level");
            if castle > 0 {
                self.get("Clan Castle", castle, "~laboratory level cap") as i64
            } else {
                0
            }
        } else {
            self.building_level(plan, "Laboratory", "laboratory_level")
        };
        let th = if donated {
            self.row_exists("Laboratory", lab)?;
            self.stats
                .required_town_hall("Laboratory", &Level::Int(lab))
        } else {
            plan.at("town_hall").f64()
        };
        Ok(list(self.record(name)?, "levels")
            .iter()
            .filter_map(|row| {
                let Json::Num(level) = row.get("level")? else {
                    return None;
                };
                let level = *level as i64;
                (self.get(name, level, "Laboratory Level Required") <= lab as f64
                    && self.stats.required_town_hall(name, &Level::Int(level)) <= th)
                    .then_some(level)
            })
            .max())
    }

    // spells.py:60-108, including the event-only spell declarations.
    fn validate_spell(
        &self,
        plan: &Json,
        name: &str,
        level: Option<i64>,
        donated: bool,
    ) -> Result<(), String> {
        let level = level.ok_or_else(|| format!("Invalid {name} level None"))?;
        if level <= 0 {
            return Err(format!("Invalid {name} level {level}"));
        }
        self.row_exists(name, level)?;
        let event = plan.at("event_ruleset");
        if matches!(
            name,
            "Santa's Surprise" | "Bag of Frostmites" | "Birthday Boom" | "Yellow Card"
        ) {
            if !flag(event, "version") || !list(event, "spells").contains(&string(name)) {
                return Err(format!("{name} requires an explicit event version"));
            }
            if donated && matches!(name, "Santa's Surprise" | "Birthday Boom") {
                return Err(format!("{name} cannot be donated"));
            }
            if name == "Bag of Frostmites" && number(event, "sweet_elixir", 0.0) < 5500.0 {
                return Err("Bag of Frostmites requires 5,500 Sweet Elixir".to_owned());
            }
            if name == "Yellow Card" && number(event, "event_currency", 0.0) < 3000.0 {
                return Err("Yellow Card requires 3,000 event currency".to_owned());
            }
            if name == "Birthday Boom" && text(event, "birthday_damage", "") != "table" {
                return Err("Select Birthday Boom's table interpretation explicitly".to_owned());
            }
        }
        let (th, lab) = if donated {
            let castle = self.building_level(plan, "Clan Castle", "clan_castle_level");
            let lab = if castle > 0 {
                self.get("Clan Castle", castle, "~laboratory level cap") as i64
            } else {
                0
            };
            if lab == 0 {
                return Err("Donated spells require a Clan Castle".to_owned());
            }
            (
                self.stats
                    .required_town_hall("Laboratory", &Level::Int(lab)) as i64,
                lab,
            )
        } else {
            let raw = self.stats.attrs(name).get("raw");
            for (factory, supplied) in [
                ("Spell Factory", "spell_factory_level"),
                ("Dark Spell Factory", "dark_spell_factory_level"),
            ] {
                if let Some(required) = raw
                    .and_then(|raw| raw.get(&format!("{factory} Level Required")))
                    .and_then(|value| stats::num(value, None))
                {
                    if (self.building_level(plan, factory, supplied) as f64) < required {
                        return Err(format!("{name} requires {factory} level {required}"));
                    }
                }
            }
            (
                plan.at("town_hall").i64(),
                self.building_level(plan, "Laboratory", "laboratory_level"),
            )
        };
        self.validate_level(name, level, th)?;
        if self.get(name, level, "Laboratory Level Required") > lab as f64 {
            return Err(format!(
                "{name} level {level} exceeds Laboratory level {lab}"
            ));
        }
        Ok(())
    }

    pub fn housing(&self, plan: &Json) -> Result<Json, String> {
        let h = |name: &str| -> Result<i64, String> {
            if is_hero(name) {
                return Ok(0);
            }
            let attrs = self.record(name)?.at("attrs");
            Ok(attrs
                .get("housing_ck")
                .filter(|value| truth(value))
                .or_else(|| attrs.get("housing"))
                .map_or(0, |value| value.f64() as i64))
        };
        let mut camp = 0;
        for (name, count) in quantities(plan) {
            camp += h(&name)? * count.i64();
        }
        camp += h("Healer")? * number(plan, "_charge_n", 0.0) as i64;
        let mut cc = 0;
        for entry in list(plan, "cc_troops") {
            let (name, count) = match entry {
                Json::Str(name) => (name.as_str(), 1),
                _ => (
                    text(entry, "name", text(entry, "type", "")),
                    number(entry, "count", 1.0) as i64,
                ),
            };
            cc += h(name)? * count;
        }
        let spell_space = |key: &str| -> Result<i64, String> {
            let mut total = 0;
            for (key, count) in items(plan, key) {
                total += self
                    .record(spell_name(&key))?
                    .at("attrs")
                    .at("housing")
                    .i64()
                    * count.i64();
            }
            Ok(total)
        };
        let factory = self.building_level(plan, "Spell Factory", "spell_factory_level");
        let dark = self.building_level(plan, "Dark Spell Factory", "dark_spell_factory_level");
        let castle = self.building_level(plan, "Clan Castle", "clan_castle_level");
        let capacity = (if factory > 0 {
            self.get("Spell Factory", factory, "Spell Storage Capacity")
        } else {
            0.0
        }) + if dark > 0 {
            self.get("Dark Spell Factory", dark, "Spell Storage Capacity")
        } else {
            0.0
        };
        let cc_capacity = if plan.at("clan_castle_level").is_null() {
            55
        } else if castle > 0 {
            self.get("Clan Castle", castle, "Troop Capacity") as i64
        } else {
            0
        };
        let camp_cap = if plan.at("town_hall").i64() == 16 {
            340
        } else {
            352
        };
        Ok(Json::Obj(vec![
            ("camp".to_owned(), Json::Num(camp as f64)),
            ("camp_cap".to_owned(), Json::Num(camp_cap as f64)),
            ("cc".to_owned(), Json::Num(cc as f64)),
            ("cc_cap".to_owned(), Json::Num(cc_capacity as f64)),
            (
                "spells".to_owned(),
                Json::Num(spell_space("_spells0")? as f64),
            ),
            ("spell_cap".to_owned(), Json::Num(capacity)),
            (
                "cc_spells".to_owned(),
                Json::Num(spell_space("_cc_spells0")? as f64),
            ),
            (
                "cc_spell_cap".to_owned(),
                Json::Num(if castle > 0 {
                    self.get("Clan Castle", castle, "Spell Capacity")
                } else {
                    0.0
                }),
            ),
            ("siege".to_owned(), field(plan, "siege")),
        ]))
    }

    // plans.py:legal: inspect camp kinds first, then retain validation order,
    // including errors accumulated before an invalid level/count ends the try block.
    pub fn legal(&self, plan: &Json) -> Vec<String> {
        let mut problems = Vec::new();
        // output/research/usage/lavaloon.md: summons cannot occupy camps.
        // https://clashofclans.fandom.com/wiki/Lavaloon_Puppet
        // Inspect every kind independently of waivable level/count errors.
        for (name, count) in quantities(plan) {
            if let Ok(record) = self.record(&name) {
                if truth(&count)
                    && !matches!(text(record, "kind", ""), "troop" | "super_troop" | "hero")
                {
                    problems.push(format!("{name} is not a camp troop"));
                }
            }
        }
        if let Err(error) = self.legal_inner(plan, &mut problems) {
            problems.push(error);
        }
        problems
    }

    fn legal_inner(&self, plan: &Json, problems: &mut Vec<String>) -> Result<(), String> {
        let th = plan.at("town_hall").i64();
        let quantities = quantities(plan);
        let roster = roster(plan);
        let hall = self.stats.max_level("Hero Hall", th).unwrap_or(0);
        let slots = self.get("Hero Hall", hall, "Hero Slots") as usize;
        if roster.len() > slots {
            problems.push(format!("heroes {} > {slots} slots", roster.len()));
        }
        let mut seen = Vec::new();
        let mut pets = Vec::new();
        for hero in roster {
            if seen.contains(&hero) {
                problems.push(format!("Duplicate hero: {hero}"));
                continue;
            }
            seen.push(hero.clone());
            if !is_hero(&hero) {
                problems.push(format!("Unknown hero: {hero}"));
                continue;
            }
            if self.stats.max_level(&hero, th).is_none() {
                problems.push(format!("{hero} is unavailable at Town Hall {th}"));
            }
            let fallback = armies::default_loadout(&hero).expect("known hero");
            let loadout = plan
                .at("loadouts")
                .get(&hero)
                .filter(|value| truth(value))
                .unwrap_or(&fallback);
            if text(loadout, "hero", "") != hero {
                problems.push(format!(
                    "Loadout for {} cannot be applied to {hero}",
                    text(loadout, "hero", "")
                ));
            }
            let equipment = list(loadout, "equipment");
            if equipment.len() > 2 {
                problems.push(format!("{hero} can equip at most 2 equipment items"));
            }
            if equipment
                .iter()
                .enumerate()
                .any(|(index, item)| equipment[..index].contains(item))
            {
                problems.push(format!("Duplicate equipment for {hero}"));
            }
            for item in equipment {
                let item = item.str();
                if text(self.record(item)?, "kind", "") != "equipment" {
                    problems.push(format!("{item} is not hero equipment"));
                    continue;
                }
                let owner = self
                    .stats
                    .attrs(item)
                    .get("raw")
                    .map_or("None", |raw| text(raw, "User", "None"));
                if owner != hero {
                    problems.push(format!("{item} belongs to {owner}, not {hero}"));
                }
                if self.stats.max_level(item, th).is_none() {
                    problems.push(format!("{item} is unavailable at Town Hall {th}"));
                } else if let Some(level) = plan.at("equipment_levels").get(item) {
                    self.validate_level(item, integer(level, item, 1)?, th)?;
                }
            }
            if let Some(pet) = loadout.get("pet").filter(|value| truth(value)) {
                let pet = pet.str();
                if pets.contains(&pet.to_owned()) {
                    problems.push(format!("Duplicate pet: {pet}"));
                }
                pets.push(pet.to_owned());
                if text(self.record(pet)?, "kind", "") != "pet" {
                    problems.push(format!("{pet} is not a pet"));
                } else if self.stats.max_level(pet, th).is_none() {
                    problems.push(format!("{pet} is unavailable at Town Hall {th}"));
                } else if let Some(level) = plan.at("pet_levels").get(pet) {
                    self.validate_level(pet, integer(level, pet, 1)?, th)?;
                }
            }
        }
        let mut boosted = Vec::new();
        for (name, count) in &quantities {
            if count.f64() > 0.0 && flag(self.record(name)?, "super") && !boosted.contains(name) {
                boosted.push(name.clone());
            }
        }
        if boosted.len() > 2 {
            problems.push(format!("boosted super troop types {} > 2", boosted.len()));
        }
        for (name, count) in &quantities {
            if !matches!(count, Json::Num(value) if value.is_finite() && *value >= 0.0 && value
                .fract() == 0.0)
            {
                return Err(format!(
                    "Invalid troop count for {name}: {}",
                    python_value(count)
                ));
            }
        }
        for (name, key) in [
            ("Spell Factory", "spell_factory_level"),
            ("Dark Spell Factory", "dark_spell_factory_level"),
            ("Laboratory", "laboratory_level"),
            ("Clan Castle", "clan_castle_level"),
        ] {
            if let Some(value) = plan.get(key).filter(|value| !value.is_null()) {
                let level = integer(value, name, 0)?;
                if level > 0 {
                    self.validate_level(name, level, th)?;
                }
            }
        }
        // game data v18.200.9 / registry raw: Meteor Golem requires
        // Barracks 19; Sky Wagon requires Workshop 9 (TH16 maxima 18/8).
        // output/research/usage/meteor-golem.md and sky-wagon.md.
        let mut trained = quantities.clone();
        if flag(plan, "siege") && !flag(plan, "siege_donated") {
            trained.push((plan.at("siege").str().to_owned(), Json::Num(1.0)));
        }
        for (name, count) in &trained {
            if count.f64() <= 0.0 {
                continue;
            }
            self.record(name)?;
            let raw = self
                .stats
                .attrs(name)
                .get("raw")
                .cloned()
                .unwrap_or_else(object);
            for (building, key) in [
                ("Barracks", "barracks_level"),
                ("Dark Barracks", "dark_barracks_level"),
                ("Workshop", "workshop_level"),
            ] {
                let required = raw
                    .get(&format!("{building} Level Required"))
                    .and_then(|value| stats::num(value, Some(0.0)))
                    .unwrap_or(0.0);
                let available = self.building_level(plan, building, key);
                if (available as f64) < required {
                    return Err(format!(
                        "{name} requires {building} level {required} (available {available})"
                    ));
                }
            }
        }
        let lab = self.building_level(plan, "Laboratory", "laboratory_level");
        let mut troop_levels = plan.at("troop_levels").clone();
        if flag(plan, "siege_donated") && flag(plan, "siege") {
            let siege = plan.at("siege").str();
            if troop_levels.get(siege).is_none() {
                put(
                    &mut troop_levels,
                    siege,
                    Json::Num(self.siege_cap(plan)? as f64),
                );
            }
        }
        for levels in [&troop_levels, plan.at("hero_levels")] {
            for (name, value) in levels.obj() {
                let level = integer(value, name, 1)?;
                if plan.get("siege") == Some(&string(name)) && flag(plan, "siege_donated") {
                    self.row_exists(name, level)?;
                    let cap = self.siege_cap(plan)?;
                    if level > cap {
                        return Err(format!(
                            "{name} level {level} exceeds Clan Castle donation cap {cap}"
                        ));
                    }
                    continue;
                }
                self.validate_level(name, level, th)?;
                let mut research = name.as_str();
                if flag(self.record(name)?, "super") {
                    for (column, _) in items(self.stats.attrs(name), "raw") {
                        if let Some(base) = column.strip_suffix(" Level Required") {
                            if self
                                .stats
                                .registry
                                .get(base)
                                .is_some_and(|record| text(record, "kind", "") == "troop")
                            {
                                // Keep the base string alive outside this temporary column.
                                research = self
                                    .stats
                                    .registry
                                    .obj()
                                    .iter()
                                    .find(|(key, _)| key == base)
                                    .expect("known base")
                                    .0
                                    .as_str();
                                break;
                            }
                        }
                    }
                }
                if self.get(research, level, "Laboratory Level Required") > lab as f64 {
                    return Err(format!(
                        "{name} level {level} exceeds Laboratory level {lab}"
                    ));
                }
            }
        }
        for (key, donated) in [("spell_levels", false), ("cc_spell_levels", true)] {
            for (name, value) in items(plan, key) {
                self.validate_spell(plan, &name, Some(integer(&value, &name, 1)?), donated)?;
            }
        }
        for stock in list(plan, "_spell_stock") {
            if !flag(stock, "remaining") && stock.at("level").is_null() {
                continue;
            }
            self.validate_spell(
                plan,
                stock.at("name").str(),
                self.spell_level(plan, stock)?,
                text(stock, "origin", "") == "donated",
            )?;
        }
        let housing = self.housing(plan)?;
        for (key, cap) in [
            ("camp", "camp_cap"),
            ("cc", "cc_cap"),
            ("spells", "spell_cap"),
            ("cc_spells", "cc_spell_cap"),
        ] {
            if housing.at(key).f64() > housing.at(cap).f64() {
                let capacity = if matches!(key, "spells" | "cc_spells") {
                    crate::trace::py_float_repr(housing.at(cap).f64())
                } else {
                    python_value(housing.at(cap))
                };
                problems.push(format!(
                    "{key} {} > {capacity}",
                    python_value(housing.at(key))
                ));
            }
        }
        Ok(())
    }

    // plans.py:841-928: an observed flag cannot grant a replay exception. Require
    // the logged recipe and its loadouts/stock to match the constructed plan.
    fn logged_exception(&self, plan: &Json, problem: &str) -> bool {
        if !matches!(
            problem,
            "cc_spells 4 > 3.0" | "Greedy Raven is unavailable at Town Hall 17"
        ) || !flag(plan, "observed")
        {
            return false;
        }
        for build in &self.library.builds {
            let source = &build.value;
            if build.library != "observed-armies.json"
                || !flag(source, "observed")
                || !flag(source, "source_battle_timestamps")
                || text(plan, "build_id", "") != armies::build_id(source)
                || plan.get("town_hall") != source.get("th")
            {
                continue;
            }
            let expected = match armies::compose(&self.library, self.stats, source, 0.0, 0) {
                Ok(expected) => expected,
                Err(_) => return false,
            };
            let mut actual_roster = roster(plan);
            let mut expected_roster = roster(&expected);
            actual_roster.sort_unstable();
            expected_roster.sort_unstable();
            if actual_roster != expected_roster
                || !same_mapping(plan.at("loadouts"), expected.at("loadouts"))
                || plan.get("siege") != expected.get("siege")
            {
                return false;
            }
            if !same_positive_counts(plan.at("_spells0"), expected.at("_spells0"))
                || !same_positive_counts(plan.at("_cc_spells0"), expected.at("_cc_spells0"))
            {
                return false;
            }
            if !same_positive_counts(
                &cargo_counts(list(plan, "cc_troops")),
                &cargo_counts(list(&expected, "cc_troops")),
            ) {
                return false;
            }
            let mut fixed = object();
            let mut reserves = object();
            for entry in list(plan, "flank") {
                add_count(&mut fixed, entry.arr()[0].str(), entry.arr()[1].f64());
            }
            for wave in list(plan, "main").iter().chain(list(plan, "support")) {
                for entry in list(wave, "units") {
                    add_count(&mut fixed, entry.arr()[0].str(), entry.arr()[1].f64());
                }
            }
            add_count(&mut fixed, "Healer", number(plan, "_charge_n", 0.0));
            for key in ["cleanup", "breakers"] {
                for entry in list(plan, key) {
                    add_count(&mut reserves, entry.arr()[0].str(), entry.arr()[1].f64());
                }
            }
            let mut names: Vec<String> = items(source, "troops")
                .into_iter()
                .filter(|(name, _)| !armies::is_siege(name))
                .map(|(name, _)| name)
                .collect();
            names.extend(
                fixed
                    .obj()
                    .iter()
                    .chain(reserves.obj())
                    .map(|(name, _)| name.clone()),
            );
            let matches = names.iter().all(|name| {
                let actual = number(&fixed, name, 0.0) + number(&reserves, name, 0.0);
                let expected = number(source.at("troops"), name, 0.0);
                let reserve = reserves.get(name).is_some()
                    || text(plan, "_phase", "") == "done"
                        && matches!(
                            name.as_str(),
                            "Archer"
                                | "Minion"
                                | "Barbarian"
                                | "Goblin"
                                | "Wall Breaker"
                                | "Super Wall Breaker"
                        );
                if reserve {
                    actual <= expected
                } else {
                    actual == expected
                }
            });
            return matches;
        }
        false
    }

    pub fn require_legal(&self, plan: &mut Json) -> Result<(), String> {
        crate::content::validate_plan(plan).map_err(|error| error.to_string())?;
        // plans.py:require_legal / tools/baselab/replay_log.py: decoded armies
        // and real_battle replays retain their documented inventories.
        let battle_log = flag(plan, "observed")
            && (text(plan, "build_id", "").starts_with("log-") || flag(plan, "real_battle"));
        let mut problems = Vec::new();
        for problem in self.legal(plan) {
            if !problem.ends_with(" is not a camp troop")
                && (battle_log || self.logged_exception(plan, &problem))
            {
                eprintln!(
                    "Logged army {}: {problem}; using documented replay handling",
                    text(plan, "build_id", "(replay)")
                );
            } else {
                problems.push(problem);
            }
        }
        if !problems.is_empty() {
            return Err(format!("Illegal attack plan: {}", problems.join("; ")));
        }
        let mut stocks = list(plan, "_spell_stock").to_vec();
        for stock in &mut stocks {
            if flag(stock, "remaining") {
                let level = self
                    .spell_level(plan, stock)?
                    .map_or(Json::Null, |level| Json::Num(level as f64));
                put(stock, "level", level);
            }
        }
        put(plan, "_spell_stock", Json::Arr(stocks));
        Ok(())
    }

    /// Search admission rules use the actual account, never replay exceptions.
    /// plans.py:674-839 supplies roster/boost/level rules; production unlocks
    /// additionally use registry.attrs.raw and data/your-levels.json.
    pub fn account_legal(&self, build: &Json, plan: &Json) -> Vec<String> {
        let mut out = self.legal(plan);
        if let Ok(housing) = self.housing(plan) {
            let levels = self.library.user.at("levels");
            let capacity = |name: &str, key: &str, column: &str| {
                let level = number(levels, key, 0.0) as i64;
                if level > 0 {
                    self.get(name, level, column)
                } else {
                    0.0
                }
            };
            for (key, cap) in [
                (
                    "camp",
                    4.0 * capacity("Army Camp", "camp", "Troop Capacity"),
                ),
                (
                    "spells",
                    self.get(
                        "Spell Factory",
                        self.building_level(plan, "Spell Factory", "spell_factory_level"),
                        "Spell Storage Capacity",
                    ) + capacity("Dark Spell Factory", "dsf", "Spell Storage Capacity"),
                ),
                ("cc", capacity("Clan Castle", "cc", "Troop Capacity")),
                ("cc_spells", capacity("Clan Castle", "cc", "Spell Capacity")),
            ] {
                if housing.at(key).f64() > cap {
                    out.push(format!(
                        "account {key} {} > {cap}",
                        python_value(housing.at(key))
                    ));
                }
            }
        }
        if plan.at("town_hall").i64() != number(self.library.user.at("levels"), "gm", 16.0) as i64 {
            out.push("Army Town Hall differs from account Town Hall".to_owned());
        }
        let levels = self.library.user.at("levels");
        for (name, count) in items(build, "troops")
            .into_iter()
            .chain(items(build, "spells"))
        {
            if !truth(&count) {
                continue;
            }
            let Some(record) = self.stats.registry.get(&name) else {
                out.push(format!("Unknown troop: {name}"));
                continue;
            };
            let raw = record
                .at("attrs")
                .get("raw")
                .cloned()
                .unwrap_or_else(object);
            for (building, key) in [
                ("Barracks", "barracks"),
                ("Dark Barracks", "dbarracks"),
                ("Workshop", "workshop"),
                ("Spell Factory", "sf"),
                ("Dark Spell Factory", "dsf"),
            ] {
                if let Some(required) = raw
                    .get(&format!("{building} Level Required"))
                    .and_then(|value| stats::num(value, None))
                {
                    let available = levels
                        .get(key)
                        .and_then(|value| stats::num(value, None))
                        .unwrap_or_else(|| {
                            if key == "sf" {
                                self.building_level(plan, "Spell Factory", "spell_factory_level")
                                    as f64
                            } else {
                                0.0
                            }
                        });
                    if available < required {
                        out.push(format!(
                            "{name} requires {building} level {required} (account {available})"
                        ));
                    }
                }
            }
            if flag(record, "super") {
                for (column, required) in raw.obj() {
                    let Some(base) = column.strip_suffix(" Level Required") else {
                        continue;
                    };
                    if self
                        .stats
                        .registry
                        .get(base)
                        .is_some_and(|record| text(record, "kind", "") == "troop")
                    {
                        let owned = self
                            .library
                            .user
                            .at("attack_levels")
                            .get(base)
                            .and_then(|value| stats::num(value, None))
                            .unwrap_or(0.0);
                        if owned < stats::num(required, Some(0.0)).unwrap_or(0.0) {
                            out.push(format!(
                                "{name} requires owned {base} level {}",
                                python_value(required)
                            ));
                        }
                    }
                }
            } else if self.library.user.at("attack_levels").get(&name).is_none() {
                out.push(format!("Account has no researched {name}"));
            }
        }
        let mut sieges = 0.0;
        for (name, count) in items(build, "troops").into_iter().chain(items(build, "cc")) {
            if armies::is_siege(&name) {
                sieges += count.f64();
            }
        }
        if sieges > 1.0 {
            out.push(format!("account siege {sieges} > 1"));
        }
        for hero in roster(plan) {
            if self.library.user.at("hero_levels").get(&hero).is_none() {
                out.push(format!("Account does not own {hero}"));
            }
            let fallback = armies::default_loadout(&hero).unwrap_or_else(object);
            let loadout = plan.at("loadouts").get(&hero).unwrap_or(&fallback);
            for item in list(loadout, "equipment") {
                if !self
                    .library
                    .user
                    .at("equipment_levels")
                    .get(item.str())
                    .is_some_and(truth)
                {
                    out.push(format!("Account does not own {}", item.str()));
                }
            }
            if let Some(pet) = loadout.get("pet").filter(|value| truth(value)) {
                if !self
                    .library
                    .user
                    .at("pet_levels")
                    .get(pet.str())
                    .is_some_and(truth)
                {
                    out.push(format!("Account does not own {}", pet.str()));
                }
            }
        }
        out
    }
}

fn add_count(stock: &mut Json, name: &str, amount: f64) {
    let total = number(stock, name, 0.0) + amount;
    put(stock, name, Json::Num(total));
}

fn cargo_counts(entries: &[Json]) -> Json {
    let mut out = object();
    for entry in entries {
        match entry {
            Json::Str(name) => add_count(&mut out, name, 1.0),
            _ => add_count(
                &mut out,
                text(entry, "name", text(entry, "type", "")),
                number(entry, "count", 1.0),
            ),
        }
    }
    out
}

fn same_positive_counts(left: &Json, right: &Json) -> bool {
    left.obj()
        .iter()
        .chain(right.obj())
        .all(|(key, _)| number(left, key, 0.0) == number(right, key, 0.0))
}

fn same_mapping(left: &Json, right: &Json) -> bool {
    match (left, right) {
        (Json::Obj(left), Json::Obj(right)) => {
            left.len() == right.len()
                && left.iter().all(|(key, value)| {
                    right
                        .iter()
                        .find(|(name, _)| name == key)
                        .is_some_and(|(_, other)| same_mapping(value, other))
                })
        }
        (Json::Arr(left), Json::Arr(right)) => {
            left.len() == right.len()
                && left
                    .iter()
                    .zip(right)
                    .all(|(left, right)| same_mapping(left, right))
        }
        _ => left == right,
    }
}
