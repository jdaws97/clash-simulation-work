//! Ports battle.py:1087-1130,1428-1669: navigation and separation.

use crate::battle::BUCKET;
use crate::geom::py_hypot;
use crate::grid::{Grid, TargetIdentity, GOAL_REACH_MIN, RES};
use crate::labels::{Name, Tag};
use crate::state::*;
use crate::{effects, geom, units};

#[cfg(test)]
mod attachment_tests {
    use super::*;
    use crate::battle::SpawnOptions;

    #[test]
    fn attached_jelly_is_excluded_on_both_sides_of_separation() {
        for pet_first in [false, true] {
            let mut battle = crate::test_support::battle();
            let first = if pet_first {
                "Angry Jelly"
            } else {
                "Dragon Duke"
            };
            let second = if pet_first {
                "Dragon Duke"
            } else {
                "Angry Jelly"
            };
            let a = battle.spawn(first, Team::Atk, 10.0, 10.0, SpawnOptions::default());
            let b = battle.spawn(second, Team::Atk, 10.0, 10.0, SpawnOptions::default());
            let (hero, pet) = if pet_first { (b, a) } else { (a, b) };
            battle.unit_mut(pet).owner = Some(hero);
            battle.unit_mut(pet).extra.brainwash_until = 100.0;
            battle.unit_mut(pet).flying = true;
            battle.unit_mut(hero).flying = true;
            battle.unit_mut(hero).frozen_until = 100.0;
            battle.rebuild_buckets();
            battle.separate();
            for unit in [hero, pet] {
                assert_eq!((battle.unit(unit).x, battle.unit(unit).y), (10.0, 10.0));
            }
            battle.unit_mut(pet).extra.brainwash_until = 0.0;
            battle.separate();
            assert_ne!((battle.unit(hero).x, battle.unit(hero).y), (10.0, 10.0));
        }
    }
}

impl Battle {
    // battle.py:_separate: neighboring buckets, pairs ordered by entity ID.
    pub fn separate(&mut self) {
        self.separate_team(Team::Atk);
        if self.params.defender_separation {
            self.separate_team(Team::Def);
        }
    }

    fn separate_team(&mut self, team: Team) {
        let mut attackers: Vec<_> = if team == Team::Atk {
            self.attackers_pool().map(Unit::reference).collect()
        } else {
            self.defenders_pool().map(Unit::reference).collect()
        };
        let air_radius = self.params.air_radius;
        let ground_radius = self.params.ground_radius;
        let housing_radius = self.params.ground_radius_per_housing;
        let housing_cap = self.params.separation_housing_cap;
        let push_fraction = self.params.separation_push;
        let coincident_angle = self.params.separation_angle;
        attackers.sort_by_key(|unit| unit.id.0);
        for a in attackers {
            let ua = self.unit(a);
            if !ua.alive || ua.speed <= 0.0 || ua.attached(self) {
                continue;
            }
            // battle.py:_separate radius(): flyers use the measured base radius
            // (output/dragon-spacing/measure.md); ground keeps the housing term.
            let radius = |u: &Unit| {
                if u.flying {
                    air_radius
                } else {
                    ground_radius + housing_radius * housing_cap.min(u.housing as f64)
                }
            };
            let ra = radius(ua);
            let max_radius = 0.8_f64
                .max(air_radius)
                .max(ground_radius + housing_radius * housing_cap);
            let mut neighbors = if team == Team::Atk {
                self.attackers_near(ua.x, ua.y, ra + max_radius)
            } else {
                self.defenders_near(ua.x, ua.y, ra + max_radius)
            };
            neighbors.sort_by_key(|unit| unit.id.0);
            for b in neighbors {
                let ua = self.unit(a);
                let ub = self.unit(b);
                if b.id.0 <= a.id.0
                    || ub.flying != ua.flying
                    || ub.speed <= 0.0
                    || ub.attached(self)
                {
                    continue;
                }
                let rb = radius(ub);
                let (mut dx, mut dy) = (ub.x - ua.x, ub.y - ua.y);
                let d2 = dx * dx + dy * dy;
                let limit = ra + rb;
                if d2 >= limit * limit {
                    continue;
                }
                let mut d = d2.sqrt();
                let push = if d < 1e-6 {
                    let angle =
                        (ua.id.0 as f64 * coincident_angle).rem_euclid(2.0 * std::f64::consts::PI);
                    dx = geom::py_cos(angle);
                    dy = geom::py_sin(angle);
                    d = 1.0;
                    limit * push_fraction
                } else {
                    (limit - d) * push_fraction
                };
                let (ux, uy) = (dx / d * push, dy / d * push);
                // battle.py:1381-1382: separation does not restart attack charges.
                self.nudge_with_pushback(a, -ux, -uy, false);
                self.nudge_with_pushback(b, ux, uy, false);
            }
        }
    }

    // battle.py:1384-1400: forced movement defaults to a fresh charge out of range.
    pub fn nudge(&mut self, reference: UnitRef, dx: f64, dy: f64) {
        self.nudge_with_pushback(reference, dx, dy, true);
    }

    fn nudge_with_pushback(&mut self, reference: UnitRef, dx: f64, dy: f64, pushback: bool) {
        let u = self.unit(reference);
        if self.t < u.extra.tornado_wall_until {
            return;
        }
        let (nx, ny, flying) = (u.x + dx, u.y + dy, u.flying);
        if !flying {
            let (i, j) = self.grid.cell(nx, ny);
            let mode = self.wall_mode(reference);
            let grid = self.navigation_grid(reference);
            let index = grid.index(i, j);
            if grid.blocked[index] || grid.wall[index] && mode == Tag::Normal {
                return;
            }
        }
        let high = self.catalog.world as f64 - 0.1;
        let u = self.unit_mut(reference);
        let old_position = (u.x, u.y);
        let previous = ((u.x / BUCKET) as i32, (u.y / BUCKET) as i32);
        u.x = high.min(0.1_f64.max(nx));
        u.y = high.min(0.1_f64.max(ny));
        self.update_bucket(reference, previous);
        let u = self.unit(reference);
        if pushback && (u.x, u.y) != old_position {
            units::pushback_windup(self, reference);
            self.force_retarget(reference, crate::targeting::ForcedRetarget::Default);
        }
    }

    // battle.py:1509-1529: path cost, then edge distance, then list order.
    pub fn path_target(&mut self, reference: UnitRef, pool: &[BuildingId]) -> BuildingId {
        let mut geometry = std::mem::take(&mut self.building_geometry_scratch);
        geometry.clear();
        geometry.extend(pool.iter().map(|id| {
            let building = self.building(*id);
            (building.x, building.y, building.half_hit)
        }));
        let u = self.unit(reference);
        let (x, y) = (u.x, u.y);
        let reach = units::effective_range(self, u).max(GOAL_REACH_MIN);
        let wall_extra = self.normal_wall_extra();
        let costs = self
            .navigation_grid(reference)
            .building_costs(x, y, wall_extra, &geometry, reach);
        let mut k = 0;
        for i in 1..costs.len() {
            let (cx, cy, half) = geometry[i];
            let (best_x, best_y, best_half) = geometry[k];
            if costs[i] < costs[k]
                || costs[i] == costs[k]
                    && geom::edge_distance(x, y, cx, cy, half)
                        < geom::edge_distance(x, y, best_x, best_y, best_half)
            {
                k = i;
            }
        }
        let unreachable = costs[k] >= 1e8;
        self.building_geometry_scratch = geometry;
        if unreachable {
            let mut best = pool[0];
            let mut distance = self.building(best).edge_distance(x, y);
            for &id in &pool[1..] {
                let d = self.building(id).edge_distance(x, y);
                if d < distance {
                    distance = d;
                    best = id;
                }
            }
            return best;
        }
        pool[k]
    }

    // battle.py:1460-1476.
    pub fn wall_mode(&self, reference: UnitRef) -> Tag {
        let u = self.unit(reference);
        if u.team == Team::Def {
            return Tag::Ignore;
        }
        if !matches!(u.kind, Tag::Siege | Tag::SiegeIdle) && self.t < u.extra.jump_until {
            return Tag::Ignore;
        }
        if self.t < u.extra.horse_until || effects::torch_stats(u, self.t).1 != 0.0 {
            return Tag::Ignore;
        }
        if !u.extra.torches.is_empty() && !u.flying {
            let (i, j) = self.grid.cell(u.x, u.y);
            if self.grid.wall[self.grid.index(i, j)] {
                return Tag::Ignore;
            }
        }
        u.spec.walls.clone()
    }

    // battle.py:1478-1503: independent wall topology for active Jump fields.
    pub fn navigation_grid(&mut self, reference: UnitRef) -> &mut Grid {
        if matches!(self.unit(reference).kind, Tag::Siege | Tag::SiegeIdle) {
            return &mut self.grid;
        }
        let active = || {
            self.fields
                .iter()
                .filter(|f| f.kind == Tag::Jump && f.started <= self.t && self.t < f.until)
                .map(|f| {
                    (
                        f.identity,
                        f.x.to_bits(),
                        f.y.to_bits(),
                        f.radius.to_bits(),
                        f.started.to_bits(),
                    )
                })
        };
        if active().next().is_none() {
            return &mut self.grid;
        }
        let unchanged = self
            .jump_grid_key
            .as_ref()
            .is_some_and(|(version, fields)| {
                *version == self.grid.version && fields.iter().copied().eq(active())
            });
        if !unchanged {
            let key = (self.grid.version, active().collect());
            let mut grid = Grid::new(self.catalog.world);
            grid.blocked.clone_from(&self.grid.blocked);
            grid.wall.clone_from(&self.grid.wall);
            for wall in &self.walls {
                if wall.alive && crate::spells::wall_jumped(self, wall.id) {
                    grid.set_wall(wall.tx, wall.ty, false);
                }
            }
            self.jump_grid_key = Some(key);
            self.jump_grid = Some(grid);
        }
        self.jump_grid.as_mut().expect("Jump topology")
    }

    // battle.py:1505-1520: add strongest speed bonus, then multiply slow.
    pub fn speed_of(&self, reference: UnitRef) -> f64 {
        let u = self.unit(reference);
        let mut speed = u.speed;
        let (_, rage_speed) = units::rage_boost(u, self.t);
        let horse_speed = if self.t < u.extra.horse_until {
            u.extra.horse_speed
        } else {
            0.0
        };
        speed += rage_speed
            .max(units::haste_speed(u, self.t))
            .max(horse_speed)
            .max(effects::torch_stats(u, self.t).0);
        speed *= effects::slow_mult(u, self.t, true);
        speed
    }

    // battle.py:1591-1653: field handles outlive waypoint lookups until prune.
    pub fn move_towards(
        &mut self,
        reference: UnitRef,
        target: EntityRef,
        position: Option<(f64, f64)>,
    ) {
        let step = self.speed_of(reference) * self.dt;
        if step <= 0.0 {
            return;
        }
        let (tx, ty) = position.unwrap_or_else(|| self.entity_position(target));
        let mut mode = self.wall_mode(reference);
        let u = self.unit(reference);
        if u.name_id == Name::RuinWitch && u.team == Team::Atk {
            mode = Tag::Normal;
        }
        if mode == Tag::Smash {
            mode = Tag::Ignore;
        }
        if u.flying || mode == Tag::Fly || u.underground || u.spec.prefer == Tag::Th {
            self.move_straight(reference, tx, ty, step);
            return;
        }
        let reach = if position.is_none() {
            units::effective_range(self, u)
        } else {
            1.0 / RES as f64
        };
        let reach = reach.max(GOAL_REACH_MIN);
        let half = if position.is_none() {
            match target {
                EntityRef::Building(id) => self.building(id).half_hit,
                EntityRef::Wall(id) => self.walls[id.0].half_hit,
                _ => 0.0,
            }
        } else {
            0.0
        };
        let identity = match target {
            EntityRef::Building(id) => TargetIdentity::Building(id.0),
            EntityRef::Wall(id) => TargetIdentity::Wall(self.walls[id.0].tx, self.walls[id.0].ty),
            EntityRef::Unit(id) => TargetIdentity::Unit(id.id.0),
            EntityRef::Trap(_) => panic!("navigation target is a trap"),
        };
        let wall_extra = match mode {
            Tag::Normal => self.normal_wall_extra(),
            Tag::Ignore | Tag::Fly => 0.0,
            _ => panic!("unknown wall mode {mode}"),
        };
        let (x, y) = (u.x, u.y);
        let grid = self.navigation_grid(reference);
        let field = grid.field(identity, tx, ty, half, reach, wall_extra);
        let mut next = grid.next_step(field, x, y);
        if next.at_goal {
            let (i, j) = grid.cell(x, y);
            let cell = grid.index(i, j);
            if grid.distance(field, cell) == 0.0 || grid.blocked[cell] {
                self.move_straight(reference, tx, ty, step);
            }
            return;
        }
        if next.is_wall && mode == Tag::Ignore {
            next.is_wall = false;
        }
        if next.is_wall {
            if let Some(&wall) = self.wall_indices.get(&(next.x as i32, next.y as i32)) {
                if self.walls[wall.0].alive {
                    if self.unit(reference).name_id == Name::RuinWitch
                        && reference.team == Team::Atk
                    {
                        self.unit_mut(reference).target = None;
                        return;
                    }
                    self.unit_mut(reference).wall_target = Some(wall);
                    if self.params.target_list {
                        let until = self.t + self.params.selected_wall_time / 1000.0;
                        let memory = self.target_memory.entry(reference).or_default();
                        memory.selected_wall = Some(wall);
                        memory.wall_until = until;
                    }
                    return;
                }
            }
        }
        if next.x == x && next.y == y {
            let timeout = if self.params.target_list {
                self.params.forget_target_time / 1000.0
            } else {
                self.params.stuck_timeout
            };
            let dt = self.dt;
            let u = self.unit_mut(reference);
            u.stuck += dt;
            if u.stuck > timeout {
                u.target = None;
                u.stuck = 0.0;
            }
            return;
        }
        self.unit_mut(reference).stuck = 0.0;
        let mut left = step - py_hypot(next.x - x, next.y - y);
        self.move_straight(reference, next.x, next.y, step);
        for _ in 0..4 {
            let u = self.unit(reference);
            if left <= 1e-9 || u.x != next.x || u.y != next.y {
                break;
            }
            let (x, y) = (u.x, u.y);
            next = self.navigation_grid(reference).next_step(field, x, y);
            if next.at_goal || next.is_wall && mode != Tag::Ignore || next.x == x && next.y == y {
                break;
            }
            let d = py_hypot(next.x - x, next.y - y);
            self.move_straight(reference, next.x, next.y, left);
            left -= d;
        }
    }

    // battle.py:1655-1669: preserve dx / d * step evaluation order.
    pub fn move_straight(&mut self, reference: UnitRef, tx: f64, ty: f64, step: f64) {
        let t = self.t;
        let u = self.unit_mut(reference);
        if t < u.extra.tornado_wall_until {
            return;
        }
        let (dx, dy) = (tx - u.x, ty - u.y);
        if dx != 0.0 || dy != 0.0 {
            u.extra.facing = (dx, dy);
        }
        let d = py_hypot(dx, dy);
        if d != 0.0 && u.name_id == Name::SuperHogRider {
            u.extra.heading = Some((dx / d, dy / d));
        }
        let previous = ((u.x / BUCKET) as i32, (u.y / BUCKET) as i32);
        if d <= step || d == 0.0 {
            u.x = tx;
            u.y = ty;
        } else {
            u.x += dx / d * step;
            u.y += dy / d * step;
        }
        self.update_bucket(reference, previous);
    }
}
