use crate::layout::model::{CcEntry, HeroBinding, Layout, Mode};
use crate::stats::Level;

use super::{inapplicable, Operator};
use crate::{Context, ProposalRng, Rejection};

pub fn edit(
    context: &Context,
    layout: &mut Layout,
    operator: Operator,
    rng: &mut ProposalRng,
) -> Result<(), Rejection> {
    use Mode::*;
    match operator {
        Operator::BuildingMode => {
            let choices: Vec<_> = layout
                .buildings
                .iter()
                .enumerate()
                .filter(|(_, b)| {
                    matches!(
                        b.key.as_str(),
                        "at" | "cannon"
                            | "mortar"
                            | "inferno"
                            | "xbow"
                            | "st"
                            | "sweeper"
                            | "firespitter"
                            | "mgt"
                            | "crafting"
                    )
                })
                .map(|(i, _)| i)
                .collect();
            if choices.is_empty() {
                return Err(inapplicable("no configurable building"));
            }
            let b = &mut layout.buildings[choices[rng.index(choices.len())]];
            let modes: &[Mode] = match b.key.as_str() {
                "at" | "cannon" | "mortar" => &[Normal, Geared],
                "inferno" => &[Single, Multi],
                "xbow" => &[Ground, Both],
                "st" => &[Rage, Poison, Invis, Earthquake],
                "sweeper" => &[N, NE, E, SE, S, SW, W, NW],
                "firespitter" => &[N, E, S, W],
                "mgt" => &[Long, Short],
                _ => &[None, Cake, Candle, Hunter],
            };
            b.mode = Some(modes[rng.index(modes.len())]);
        }
        Operator::SkeletonMode => {
            let choices: Vec<_> = layout
                .traps
                .iter()
                .enumerate()
                .filter(|(_, t)| t.key == "skeleton")
                .map(|(i, _)| i)
                .collect();
            if choices.is_empty() {
                return Err(inapplicable("no skeleton traps"));
            }
            let t = &mut layout.traps[choices[rng.index(choices.len())]];
            t.mode = Some(if t.mode == Some(Air) { Ground } else { Air });
        }
        Operator::HeroPermutation => {
            if layout.setup.heroes.len() < 2 {
                return Err(inapplicable("fewer than two heroes"));
            }
            let a = rng.index(layout.setup.heroes.len());
            let b = (a + 1 + rng.index(layout.setup.heroes.len() - 1)) % layout.setup.heroes.len();
            // Exchange heroes, retaining banner bindings in building order.
            let hero = layout.setup.heroes[a].hero.clone();
            layout.setup.heroes[a].hero = layout.setup.heroes[b].hero.clone();
            layout.setup.heroes[b].hero = hero;
        }
        Operator::HeroSelection => {
            let available: Vec<_> = layout
                .setup
                .hero_levels
                .keys()
                .filter(|name| !layout.setup.heroes.iter().any(|h| &h.hero == *name))
                .cloned()
                .collect();
            if available.is_empty() {
                return Err(inapplicable("no unused owned hero"));
            }
            let hero = available[rng.index(available.len())].clone();
            if layout.setup.heroes.is_empty() {
                let banner = layout
                    .buildings
                    .iter()
                    .find(|b| b.key == "banner")
                    .ok_or_else(|| inapplicable("no banner"))?;
                layout.setup.heroes.push(HeroBinding {
                    hero,
                    banner: Some(banner.id.clone()),
                });
            } else {
                let i = rng.index(layout.setup.heroes.len());
                layout.setup.heroes[i].hero = hero;
            }
        }
        Operator::CcPackage => {
            if !layout.buildings.iter().any(|b| b.key == "cc") {
                return Err(inapplicable("no Clan Castle"));
            }
            let level = layout
                .setup
                .levels
                .get("cc")
                .ok_or_else(|| inapplicable("missing fixed CC level"))?;
            let capacity = context
                .catalog
                .stats
                .get("Clan Castle", level, &["Troop Capacity"], Some(0.0))
                .unwrap_or(0.0) as u32;
            let packages: &[&[(&str, u32)]] = &[
                &[("Dragon", 1), ("Archer", 5)],
                &[("Ice Golem", 2), ("Archer", 5)],
                &[("Lava Hound", 1)],
                &[("Super Minion", 2), ("Headhunter", 2)],
                &[("Archer", 1)],
            ];
            let package = packages[rng.index(packages.len())];
            let entries: Vec<_> = package
                .iter()
                .map(|&(name, count)| {
                    let previous = layout.setup.cc_troops.iter().find(|e| e.name == name);
                    CcEntry {
                        name: name.to_owned(),
                        count,
                        source: previous.and_then(|e| e.source.clone()),
                        level: previous.and_then(|e| e.level.clone()),
                        object_form: true,
                    }
                })
                .collect();
            // Admission checks housing, donation eligibility and receiving caps.
            if capacity == 0 {
                return Err(inapplicable("zero CC capacity"));
            }
            layout.setup.cc_troops = entries;
        }
        Operator::Guardian => {
            if layout.town_hall != 18 {
                return Err(inapplicable("guardians require TH18"));
            }
            let current = layout
                .setup
                .levels
                .get("guardian")
                .cloned()
                .unwrap_or(Level::Int(1));
            let available: Vec<_> = context
                .catalog
                .stats
                .registry
                .obj()
                .iter()
                .filter(|(name, row)| {
                    context.catalog.units.contains_key(name)
                        && row.get("kind").is_some_and(|k| k.str() == "guardian")
                })
                .map(|(name, _)| name.clone())
                .collect();
            let available: Vec<_> = available
                .into_iter()
                .filter(|name| {
                    crate::layout::rules::valid_level(&context.catalog, name, &current, 18)
                })
                .collect();
            let mut available = available;
            available.sort();
            if available.is_empty() {
                return Err(inapplicable("no guardian at fixed level"));
            }
            let selected = available[rng.index(available.len())].clone();
            if layout.setup.guardian.as_ref() == Some(&selected)
                && !layout.setup.levels.contains_key("guardian")
            {
                layout.setup.guardian = Option::None;
            } else {
                layout.setup.guardian = Some(selected);
            }
        }
        _ => unreachable!(),
    }
    Ok(())
}
