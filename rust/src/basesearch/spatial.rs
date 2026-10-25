use crate::layout::model::{Layout, Tile};

use super::{Context, Rejection};

pub const WIDTH: i32 = 44;

pub fn size(context: &Context, key: &str, trap: bool) -> Result<i32, Rejection> {
    let value = if trap {
        context
            .catalog
            .trap_names
            .iter()
            .any(|(k, _)| k == key)
            .then(|| {
                context
                    .catalog
                    .trap_sizes
                    .iter()
                    .find(|(k, _)| k == key)
                    .map_or(1, |(_, s)| *s)
            })
    } else {
        context
            .catalog
            .building_types
            .iter()
            .find(|(k, _)| k == key)
            .map(|(_, b)| b.size)
    };
    value
        .map(|v| v as i32)
        .ok_or_else(|| Rejection::Conservation(format!("unknown key {key}")))
}

pub fn distance(a: Tile, b: Tile) -> i64 {
    let dx = a.0 as i64 - b.0 as i64;
    let dy = a.1 as i64 - b.1 as i64;
    dx.saturating_mul(dx).saturating_add(dy.saturating_mul(dy))
}

pub fn th(layout: &Layout) -> Tile {
    layout
        .buildings
        .iter()
        .find(|b| b.key == "th")
        .map_or((20, 20), |b| b.position)
}

/// Lower roles are packed deeper. Includes merged/new TH17/18 defenses.
pub fn role(key: &str) -> i32 {
    match key {
        "th" => -10,
        "mono" | "inferno" | "eagle" | "revenge" => 0,
        "st" | "cc" | "scatter" | "firespitter" => 10,
        "swt" | "mgt" | "mat" | "ric" | "crafting" | "banner" => 20,
        "xbow" | "ad" => 40,
        "wt" | "bt" | "sweeper" | "tesla" => 55,
        "mortar" | "at" | "cannon" => 80,
        _ => 120,
    }
}

#[derive(Clone)]
pub struct Board {
    occupied: [bool; 1936],
}

impl Board {
    pub fn new() -> Self {
        Self {
            occupied: [false; 1936],
        }
    }

    pub fn fits(&self, (x, y): Tile, size: i32) -> bool {
        if x < 0 || y < 0 || x as i64 + size as i64 > 44 || y as i64 + size as i64 > 44 {
            return false;
        }
        (y..y + size).all(|py| (x..x + size).all(|px| !self.occupied[(py * WIDTH + px) as usize]))
    }

    pub fn take(&mut self, position: Tile, size: i32) -> bool {
        if !self.fits(position, size) {
            return false;
        }
        for y in position.1..position.1 + size {
            for x in position.0..position.0 + size {
                self.occupied[(y * WIDTH + x) as usize] = true;
            }
        }
        true
    }

    pub fn near(&mut self, target: Tile, size: i32, budget: &mut usize) -> Result<Tile, Rejection> {
        let mut positions: Vec<_> = (0..=WIDTH - size)
            .flat_map(|y| (0..=WIDTH - size).map(move |x| (x, y)))
            .collect();
        positions.sort_by_key(|&p| (distance(p, target), p.1, p.0));
        for position in positions {
            if *budget == 0 {
                return Err(Rejection::RepairBudget);
            }
            *budget -= 1;
            if self.take(position, size) {
                return Ok(position);
            }
        }
        Err(Rejection::RepairBudget)
    }
}
