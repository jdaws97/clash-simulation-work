//! Complete source-recipe selection, motivated by the D4/D5 equipment audit.
//! This is a roster-only priority policy: it spends no extra scouting battles.

use super::*;

pub(super) struct RecipeSelection {
    pub steps: Vec<Json>,
    pub report: Json,
}

/// Optional actors may be absent, but consume ordinary stock when present.
/// This is distinct from optional spell opportunities and their shared budgets.
pub(super) fn optional_actor(step: &Json) -> bool {
    matches!(text(step, "action", ""), "deploy" | "ability") && flag(step, "optional")
}

impl Compiler<'_> {
    pub(super) fn select_recipe(
        &self,
        book: &Json,
        inventory: &Json,
        heroes: &[Json],
        spells: &Json,
        plan: &Json,
        overrides: &Json,
    ) -> Result<RecipeSelection, String> {
        // Preserve the complete default when it fits. Then use declared recipe
        // order, followed by standalone variants in stable support order. Aliases
        // of the same variant set do not get extra votes. Do not invent new
        // combinations of independently cited openings.
        let mut candidates = vec![("default".to_owned(), array([]))];
        for (name, names) in items(book, "recipes") {
            if !candidates.iter().any(|(_, previous)| previous == &names) {
                candidates.push((name, names));
            }
        }
        let mut variants = list(book, "variants").to_vec();
        variants.sort_by(|a, b| number(b, "support", 0.0).total_cmp(&number(a, "support", 0.0)));
        for variant in variants {
            let name = text(&variant, "name", "");
            let names = array([string(name)]);
            if !candidates.iter().any(|(_, previous)| previous == &names) {
                candidates.push((name.to_owned(), names));
            }
        }

        let mut results = Vec::new();
        let mut chosen = None;
        for (name, names) in candidates {
            let expanded =
                self.expand_variants(book, inventory, heroes, spells, plan, Some(&names));
            let (steps, problems) = match expanded {
                Ok(mut steps) => {
                    apply_overrides(&mut steps, overrides)?;
                    let problems = self.recipe_problems(&steps, inventory, heroes, spells, plan)?;
                    (Some(steps), problems)
                }
                Err(reason) => (None, vec![reason]),
            };
            let feasible = problems.is_empty();
            results.push(Json::Obj(vec![
                ("recipe".to_owned(), string(&name)),
                ("variants".to_owned(), names.clone()),
                ("feasible".to_owned(), Json::Bool(feasible)),
                (
                    "reasons".to_owned(),
                    array(problems.iter().map(|reason| string(reason))),
                ),
            ]));
            if feasible && chosen.is_none() {
                chosen = Some((name, names, steps.unwrap()));
            }
        }

        let (mode, name, names, steps) = if let Some((name, names, steps)) = chosen {
            ("feasible", name, names, steps)
        } else {
            let steps = self.expand_variants(book, inventory, heroes, spells, plan, None)?;
            let mut names = Vec::new();
            for step in &steps {
                if let Some(name) = step.get("variant") {
                    if !names.contains(name) {
                        names.push(name.clone());
                    }
                }
            }
            (
                "repaired_hybrid",
                "repaired hybrid".to_owned(),
                array(names),
                steps,
            )
        };
        Ok(RecipeSelection {
            steps,
            report: Json::Obj(vec![
                ("mode".to_owned(), string(mode)),
                ("recipe".to_owned(), string(&name)),
                ("variants".to_owned(), names),
                (
                    "policy".to_owned(),
                    string("default, declared recipes, stable support order"),
                ),
                ("extra_planning_battles".to_owned(), Json::Num(0.0)),
                ("candidates".to_owned(), array(results)),
            ]),
        })
    }

    fn recipe_problems(
        &self,
        steps: &[Json],
        inventory: &Json,
        heroes: &[Json],
        spells: &Json,
        plan: &Json,
    ) -> Result<Vec<String>, String> {
        let mut problems = Vec::new();
        for step in steps {
            // Incidental cleanup stock is not defining recipe equipment or a
            // main/charge actor. An authored optional deployment says the same
            // explicitly; neither waives stock accounting when it is present.
            if optional_spell(step)
                || optional_actor(step)
                    && !self.usable(step, inventory, heroes, spells, plan, steps)
                || text(step, "action", "") == "deploy" && text(step, "group", "") == "cleanup"
            {
                continue;
            }
            let id = text(step, "id", "");
            if !self.usable(step, inventory, heroes, spells, plan, steps) {
                problems.push(format!("{id}: unavailable actor or spell"));
            } else if text(step, "action", "") == "ability" && self.missing_equipment(step, plan) {
                problems.push(format!("{id}: unavailable defining equipment"));
            }
        }
        // Retain inherited ordinary count clipping (PB1a A3), but never admit
        // absent defining units, missing abilities, or oversubscribed spells.
        if !self.feasible(steps, &[], inventory, heroes, spells, plan, true)? {
            problems.push("insufficient mandatory stock".to_owned());
        }
        Ok(problems)
    }
}
