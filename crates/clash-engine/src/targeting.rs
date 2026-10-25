//! Experimental AI hypotheses derived from local v18.200.9 CSV names.
//! All behavior in this module is opt-in; see docs/PROBE_CARDS.md.

use crate::geom;
use crate::grid::{GOAL_REACH_MIN, RES};
use crate::labels::{Name, Tag};
use crate::state::*;
use crate::units;

#[derive(Clone, Copy, Debug)]
pub enum ForcedRetarget {
    Default,
    Jump,
    Tesla,
}

#[derive(Clone, Debug, Default)]
pub struct TargetMemory {
    pub original: Option<BuildingId>,
    pub forgotten: Option<BuildingId>,
    pub forced: Option<ForcedRetarget>,
    pub last_progress: f64,
    pub distance: Option<f64>,
    pub obstacle_hp: Option<f64>,
    pub selected_wall: Option<WallId>,
    pub wall_until: f64,
    pub ignores_walls: bool,
}

impl Battle {
    pub fn attacker_knows_building(&self, building: &Building) -> bool {
        !self.params.hidden_information || !building.hidden_tesla || building.revealed
    }

    pub fn visible_buildings(&self) -> impl Iterator<Item = &Building> {
        self.buildings
            .iter()
            .filter(|building| self.attacker_knows_building(building))
    }

    pub fn attacker_knows_trap(&self, trap: &Trap) -> bool {
        !self.params.hidden_information || trap.fuse_at >= 0.0 || !trap.armed
    }

    pub fn normal_wall_extra(&self) -> f64 {
        let cost = if self.params.target_list {
            self.params.wall_cost_base / self.params.internal_units_per_tile
        } else {
            self.params.wall_cost
        };
        cost / RES as f64
    }

    pub fn force_retarget(&mut self, reference: UnitRef, cause: ForcedRetarget) {
        if !self.params.target_list {
            return;
        }
        let original = match self.unit(reference).target {
            Some(EntityRef::Building(id)) => Some(id),
            _ => None,
        };
        let memory = self.target_memory.entry(reference).or_default();
        if memory.original.is_none() {
            memory.original = original;
        }
        memory.forced = Some(cause);
        self.unit_mut(reference).target = None;
    }

    /// No progress means neither closer to the destination nor damaging an obstacle.
    /// Euclidean progress, the timer reset rule, and expiry are hypotheses.
    pub fn target_memory_tick(&mut self, reference: UnitRef) {
        if !self.params.target_list {
            return;
        }
        let u = self.unit(reference);
        let current = u.target;
        let wall = u.wall_target;
        let distance = current.map(|target| self.entity_edge_distance(target, u.x, u.y));
        let obstacle_hp = wall
            .map(|id| self.walls[id.0].hp)
            .or_else(|| match current {
                Some(EntityRef::Building(id)) => Some(self.building(id).hp),
                _ => None,
            });
        let ignores_walls = self.wall_mode(reference) == Tag::Ignore;
        let t = self.t;
        let forget_after = self.params.forget_target_time / 1000.0;
        let wall_dead = wall.is_some_and(|id| !self.walls[id.0].alive);
        let memory = self.target_memory.entry(reference).or_default();
        let jump_changed = memory.ignores_walls != ignores_walls;
        memory.ignores_walls = ignores_walls;
        let progressed = match (distance, memory.distance) {
            (Some(now), Some(before)) => now < before - 1e-6,
            (Some(_), None) => true,
            _ => false,
        } || obstacle_hp != memory.obstacle_hp;
        if progressed {
            memory.last_progress = t;
        }
        memory.distance = distance;
        memory.obstacle_hp = obstacle_hp;
        let expired = matches!(current, Some(EntityRef::Building(_)))
            && t - memory.last_progress >= forget_after;
        if expired {
            if let Some(EntityRef::Building(id)) = current {
                memory.forgotten = Some(id);
            }
            memory.original = None;
            memory.distance = None;
            memory.last_progress = t;
        }
        if wall_dead || t >= memory.wall_until {
            memory.selected_wall = None;
        }
        if expired || wall_dead && self.params.retarget_after_destroying_wall {
            self.force_retarget(reference, ForcedRetarget::Default);
            if wall_dead && self.params.retarget_after_destroying_wall {
                self.target_memory.entry(reference).or_default().original = None;
            }
        } else if jump_changed {
            self.force_retarget(reference, ForcedRetarget::Jump);
        }
    }

    pub fn target_list_target(&mut self, reference: UnitRef, pool: &[BuildingId]) -> BuildingId {
        let memory = self
            .target_memory
            .get(&reference)
            .cloned()
            .unwrap_or_default();
        let keep_original = if memory.forced.is_some() {
            self.params.stick_to_targeted_building_when_forcing_retarget
        } else {
            self.params.remember_original_target
        };
        if let Some(original) = memory
            .original
            .filter(|id| keep_original && pool.contains(id) && Some(*id) != memory.forgotten)
        {
            self.target_memory.entry(reference).or_default().forced = None;
            return original;
        }
        let u = self.unit(reference);
        let (x, y) = (u.x, u.y);
        let use_paths = !u.flying && !u.underground && self.wall_mode(reference) == Tag::Normal;
        let reach = units::effective_range(self, u).max(GOAL_REACH_MIN);
        let mut candidates: Vec<_> = pool
            .iter()
            .copied()
            .filter(|id| Some(*id) != memory.forgotten || pool.len() == 1)
            .collect();
        candidates.sort_by(|a, b| {
            self.building(*a)
                .edge_distance(x, y)
                .total_cmp(&self.building(*b).edge_distance(x, y))
        });
        candidates.truncate(self.params.max_target_list_size as usize);
        let geometry: Vec<_> = candidates
            .iter()
            .map(|id| {
                let b = self.building(*id);
                (b.x, b.y, b.half_hit)
            })
            .collect();
        let wall_extra = self.normal_wall_extra();
        let costs: Vec<f64> = if use_paths {
            self.navigation_grid(reference)
                .exact_building_costs(x, y, wall_extra, &geometry, reach)
        } else {
            geometry
                .iter()
                .map(|&(cx, cy, half)| geom::edge_distance(x, y, cx, cy, half))
                .collect()
        };
        let primary = candidates.len().min(self.params.target_list_size as usize);
        let expand = memory.forced.is_some() || costs[..primary].iter().all(|cost| *cost >= 1e8);
        let count = if expand { candidates.len() } else { primary };
        let noise = memory.forced.map_or(0.0, |cause| match cause {
            ForcedRetarget::Default => self.params.force_new_target_default_max_noise,
            ForcedRetarget::Jump => self.params.force_new_target_jump_max_noise,
            ForcedRetarget::Tesla => self.params.force_new_target_tesla_max_noise,
        }) / self.params.internal_units_per_tile;
        let mut best = 0;
        let mut best_score = f64::INFINITY;
        for (rank, &cost) in costs.iter().take(count).enumerate() {
            let extra_rank = (rank + 1).saturating_sub(primary) as f64;
            let random = if noise > 0.0 {
                self.rng_mut().uniform(0.0, noise)
            } else {
                0.0
            };
            let score = cost + extra_rank * self.params.extra_target_path_cost_penalty + random;
            if score < best_score {
                best = rank;
                best_score = score;
            }
        }
        let chosen = candidates[best];
        let memory = self.target_memory.entry(reference).or_default();
        if !memory.original.is_some_and(|id| pool.contains(&id))
            || !self.params.remember_original_target
            || memory.original == memory.forgotten
        {
            memory.original = Some(chosen);
        }
        memory.forced = None;
        memory.distance = None;
        memory.last_progress = self.t;
        chosen
    }

    /// Seed-centred neighborhoods, not connected components: a long chain must
    /// not combine two distant armies. Membership and tie rules are hypotheses.
    pub fn spatial_follow_target(&self, reference: UnitRef) -> (Option<EntityRef>, bool) {
        let u = self.unit(reference);
        let range = if u.name_id == Name::ApprenticeWarden {
            self.params.apprentice_radius
        } else {
            self.params.warden_radius
        };
        let radius = self.params.target_groups_radius / self.params.internal_units_per_tile;
        let threshold = if u.name_id == Name::ApprenticeWarden {
            self.params.apprentice_target_groups_min_weight
        } else {
            self.params.target_groups_min_weight
        } / self.params.group_weight_units_per_weight;
        let ww = &self.catalog.warden_weights;
        let mut allies: Vec<_> = self
            .attackers_near_iter(u.x, u.y, range)
            .filter(|ally| *ally != reference && self.unit(*ally).name_id != Name::Totem)
            .collect();
        allies.sort_by_key(|ally| ally.id.0);
        let weight = |ally: UnitRef| {
            let a = self.unit(ally);
            if a.is_hero {
                ww.at("heroes").f64()
            } else if a.kind == Tag::Pet {
                ww.at("pets").f64()
            } else {
                ww.at("weights").get(&a.name).map_or(0.0, |v| v.f64())
            }
        };
        let mut best: Option<(f64, f64, Vec<UnitRef>)> = None;
        for &seed in &allies {
            let s = self.unit(seed);
            let group: Vec<_> = allies
                .iter()
                .copied()
                .filter(|ally| {
                    let a = self.unit(*ally);
                    geom::dist(s.x, s.y, a.x, a.y) <= radius
                })
                .collect();
            let total = group.iter().copied().map(weight).sum::<f64>();
            let distance = geom::dist(u.x, u.y, s.x, s.y);
            if total >= threshold
                && best.as_ref().map_or(true, |(previous, d, _)| {
                    total > *previous || total == *previous && distance < *d
                })
            {
                best = Some((total, distance, group));
            }
        }
        let Some((_, _, group)) = best else {
            return (None, false);
        };
        let mut votes: Vec<(EntityRef, f64)> = Vec::new();
        for ally in group {
            let a = self.unit(ally);
            let target = a
                .wall_target
                .filter(|id| self.walls[id.0].alive)
                .map(EntityRef::Wall)
                .or(a.target);
            let Some(target) = target.filter(|target| match target {
                EntityRef::Building(id) => self.building_targetable(*id),
                EntityRef::Wall(id) => self.walls[id.0].alive,
                _ => false,
            }) else {
                continue;
            };
            if let Some((_, score)) = votes.iter_mut().find(|(id, _)| *id == target) {
                *score += weight(ally);
            } else {
                votes.push((target, weight(ally)));
            }
        }
        // First ID-ordered ally wins ties; changing this is a probe hypothesis.
        let mut chosen = None;
        let mut score = -1.0;
        for (target, vote) in votes {
            if vote > score {
                chosen = Some(target);
                score = vote;
            }
        }
        (
            chosen,
            chosen.is_none() && self.params.warden_waits_for_group_retargeting,
        )
    }
}
