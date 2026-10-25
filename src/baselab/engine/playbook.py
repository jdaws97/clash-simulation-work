"""Playbook attacks: the attacker plays only steps that real players describe.

A playbook (data/playbooks/<family>.json) is a list of steps compiled from
quote-checked video transcripts and guides (output/sources/playbooks). Each
step cites its sources. The executor below runs the steps in the battle:
every step has an action, a place (anchor) and a trigger, all from a small
vocabulary that mirrors how players narrate attacks ("release the Royal
Champion in the corner", "Invisibility every 4 seconds", "only release the
Dragon Duke after the Root Riders enter the base", "Rage when the troops
reach the core").

Choices a player makes per base (which side, which corner to charge, how far
apart the flanks are) are knobs, set by scouting or the tactic search; the
structure itself is never invented.

Step fields:
  id        unique name, other steps refer to it in triggers
  action    deploy | spell | ability | recall | redeploy | release_siege
  what      unit, hero, siege or spell name; for deploy also "rest:<Troop>"
  count     number, or "all" (every remaining one)
  at        anchor (see Anchor below)
  when      trigger dict (see _ready)
  every     seconds between repeats (spells only), with optional "until" trigger
  cite      [{"video": id, "t": seconds, "quote": "..."}]

Anchors:
  edge:main | edge:left | edge:right | edge:charge | edge:funnel   points on the deploy edge
  unit:<Name>          the named attacking unit (first alive), e.g. unit:Royal Champion
  unit_ahead:<Name>    2 tiles ahead of that unit toward its target (spells on a moving hero)
  group:<g>            centroid of an attacking group (charge, funnel, main)
  th                   the Town Hall
  threat:<g>           the most dangerous defense firing at group g
  building:<key>       the alive building of that key nearest the main group
"""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
from dataclasses import dataclass, field

from ..mechanics import WORLD
from . import heroes, spells, stats, units
from .plans import SPELL_NAMES, THREAT, AttackPlan, _band_hit, edge_point

SPELL_KEYS = {v: k for k, v in SPELL_NAMES.items()}


# How fast a player can act. One action at a time: dragging n troops out of a
# slot costs PACE_TAP each plus PACE_SWITCH to pick the slot and the spot; a
# spell, recall or redeploy costs PACE_SWITCH; a hero ability PACE_ABILITY.
# These are assumptions (no source gives human input rates). BASELAB_PACE
# scales them (default 1.0); it is NOT tuned to the real battle times, which
# stay a held-out test (docs/SIM_ACCURACY.md check 6).
# PACE_TAP is measured: 0.133 s between troops when a slot is held (60 fps
# video, 20 intervals, two players; docs/VIDEO_MEASUREMENTS.md). The switch
# and ability times remain assumptions.
PACE_TAP, PACE_SWITCH, PACE_ABILITY = 0.133, 0.6, 0.3


def action_time(act: str, n: int = 1) -> float:
    scale = float(os.environ.get("BASELAB_PACE", "1.0"))
    if act == "deploy":
        return scale * (PACE_SWITCH + PACE_TAP * n)
    if act == "ability":
        return scale * PACE_ABILITY
    return scale * PACE_SWITCH


# seconds a building-aimed ability waits to line up before firing anyway
# (an assumption, not from a source); also how long a ready spell step waits
# for its target (a defense firing, a group to cast on) before the player
# moves on to the steps chained after it
AIM_WAIT = 10.0

# no troop is still in the camp at this time (a player spends the army; the
# uncited rule fit_steps' rest2 steps already use)
LATE = 150.0

UNIT_TRIGGERS = ("inside", "hp_below", "heavy_fire")

# troops that go in as one stack even when several are dropped: Healers
# follow whoever they are healing, Wall Breakers open one wall section
LINE_EXEMPT = {"Healer", "Wall Breaker"}


@dataclass
class PlaybookPlan(AttackPlan):
    auto_revive: bool = False
    steps: list = field(default_factory=list)
    inventory: dict = field(default_factory=dict)  # troop/siege name -> count left
    flank_offset: float = 0.9  # radians between the main side and each flank (knob)
    charge_side: str = "left"  # which flank the charge opens (knob)
    _done: dict = field(default_factory=dict)  # step id -> time it fired
    _next: dict = field(default_factory=dict)  # repeating step id -> next time
    _cancelled: set = field(default_factory=set)  # skipped or stopped step ids
    _hurt: dict = field(default_factory=dict)  # unit id -> [(t, hp)]
    _no_target: dict = field(
        default_factory=dict
    )  # step id -> time it was first ready with no target
    log_steps: list = field(default_factory=list)

    # the battle asks for initial deployments; everything here is dynamic
    def deployments(self, battle):
        # Wiki: Rocket Spear/Flame Flinger, spare snipers can open before the push.
        out = self.opening_deployments(battle)
        self._deployed = set(self._snipe_deployed)
        # A hero that opened on an exposed defense has made its cited entry:
        # steps chained "after" that entry go on from the opening's time.
        opened = {d.name: d.time for d in out if d.name in self._snipe_deployed}
        for step in self.steps:
            if step["action"] == "deploy" and step.get("what") in opened:
                self._done.setdefault(step["id"], opened[step["what"]])
                self.log_steps.append(
                    (
                        round(opened[step["what"]], 1),
                        step["id"] + " (opened on a snipe)",
                    )
                )
        for deployment in out:
            if deployment.name not in heroes.HEROES:
                self.inventory[deployment.name] -= 1
        return out

    def _snipe_available(self, name):
        # User (TH16 ranked, 2026-10-24): players fit a cited plan to the base,
        # e.g. Spear or Backpack an exposed Eagle. Steps that only place and
        # time a hero leave that choice open (its role cost is priced in
        # _snipe_cost). A cited ability, or steps that follow the hero (its
        # Healers, Invisibility, Ice Block), keep it in its walk or charge:
        # data/playbooks/fireball-warden.json otherwise threw the Warden's
        # Fireball from outside before his cited walk.
        if name in getattr(self, "_snipe_deployed", set()):
            return False
        for step in self.steps:
            if step["id"] in self._cancelled or (
                step["id"] in self._done and not step.get("every")
            ):
                continue
            if step.get("completion") or step.get("uncited"):
                continue
            # output/research/usage/grand-warden.md: equipment supplies abilities.
            # https://clashofclans.fandom.com/wiki/Grand_Warden
            if step["action"] == "ability" and self._missing_equipment(step):
                continue
            if (
                name == "Flame Flinger"
                and step["action"] == "release_siege"
                and step.get("what") in (None, name)
            ):
                return False
            if step["action"] == "ability" and step.get("what") == name:
                return False
            anchors = (step.get("at", ""), step.get("aim", ""))
            if any(str(anchor).endswith(":" + name) for anchor in anchors):
                return False
        if name == "Flame Flinger":
            return self.siege == name and self.inventory.get(name, 0) > 0
        return name in self.push_heroes or any(
            hero == name for hero, _ in self.funnel_heroes
        )

    def _snipe_role(self, name):
        # Wiki: Hero Equipment, preserve the value of a hero's planned support role.
        # Completion steps also assign the spare hero to a main push or funnel.
        for step in self.steps:
            if step["action"] == "deploy" and step.get("what") == name:
                return step.get("group", "main")
        return super()._snipe_role(name)

    def _snipe_lightning_count(self):
        # Wiki: Giant Arrow, retain the cited Air Defense targets and their area.
        # The existing _zap reservation helper can still spend safe copies elsewhere.
        if any(
            self._ad_target_count(step)
            and step["id"] not in self._done
            and step["id"] not in self._cancelled
            and not self._missing_equipment(step)
            for step in self.steps
        ):
            return 0
        return super()._snipe_lightning_count()

    def setup_charge(self, hero, healers, lateral=0.0, at=0.0):
        """Not applied: a playbook plays only its own cited charges (its
        steps). The scripted brain's charge (AttackPlan.setup_charge) moved
        heroes and Healers between lists this plan never reads, so a charge
        scenario silently replayed the plain playbook."""
        return False

    def has_pending(self):
        """Pending while a deploy or redeploy step has not fired. The battle
        otherwise ends when every attacker is down (see on_tick: an army
        with nothing alive deploys its remaining steps, as players do)."""
        # Wiki: Healer, undeployed reserves keep the battle running.
        return (
            (bool(self.cc_troops) and not self.siege and not self._cc_released)
            or any(self.inventory.values())
            or any(
                s["id"] not in self._done
                for s in self.steps
                if s["action"] in ("deploy", "redeploy")
            )
        )

    def has_offensive_pending(self, battle):
        self._step_kinds()
        if self._has_deployable_cc(battle):
            return True
        # Wiki: Revive Spell, eligible fallen heroes can return through fallback too.
        if (
            self._have("revive")
            and any(
                not hero.alive and hero.extra.get("revivable")
                for hero in battle.attackers
            )
            and (
                self.auto_revive
                or any(
                    (step["id"] not in self._done or step.get("every"))
                    and step["id"] not in self._cancelled
                    and step["action"] == "spell"
                    and step.get("what") == "Revive Spell"
                    for step in self.steps
                )
            )
        ):
            return True
        if any(unit.name != "Healer" for unit in battle.portal_stash):
            return True
        # Wiki: Healer, non-healing troops still in camp prevent battle end.
        if any(
            name != "Healer" and count > 0 for name, count in self.inventory.items()
        ):
            return True
        return any(
            step["id"] not in self._done
            and step["action"] == "deploy"
            and step.get("what") != "Healer"
            and (
                step.get("what") in heroes.HEROES
                or self.inventory.get(step.get("what"), 0) > 0
            )
            for step in self.steps
        )

    # ------------------------------------------------------------ anchors
    def _edge_angle(self, which):
        off = {"main": 0.0, "left": -self.flank_offset, "right": self.flank_offset}
        if which == "charge":
            which = self.charge_side
        elif which == "funnel":
            which = "right" if self.charge_side == "left" else "left"
        return self.angle + off.get(which, 0.0)

    def _edge(self, battle, which):
        # Wiki: Archer Queen, cluster placement belongs to an actual hero charge.
        charge = which == "charge" and any(
            step["action"] == "deploy"
            and step.get("what") in heroes.HEROES
            and step.get("group", "main") == "charge"
            for step in self.steps
        )
        if charge:
            # User (TH16 ranked, 2026-10-23): charge toward reachable defense clusters.
            if not hasattr(self, "_charge_edge"):
                self._charge_edge = self.charge_point(battle, self._edge_angle(which))
            return self._charge_edge
        return edge_point(battle, self._edge_angle(which), 0.0)

    def _unit(self, battle, name):
        for u in battle.attackers:
            # Wiki: Magic Mirror, clones keep fighting after the real Queen falls.
            if u.alive and u.name == name and u.kind != "hero_clone":
                return u
        return None

    def _group(self, battle, g):
        return [
            u
            for u in battle.attackers
            if u.alive and u.group == g and u.name != "Totem" and u.kind != "pet"
        ]

    def anchor(self, battle, at, *, unclaimed=False):
        # Wiki: Rocket Spear, spell targets exclude a defense with lethal damage claimed.
        claimed = getattr(self, "_snipe_claimed", ()) if unclaimed else ()
        kind, _, arg = at.partition(":")
        if kind == "edge":
            return self._edge(battle, arg)
        if kind == "unit":
            u = self._unit(battle, arg)
            return (u.x, u.y) if u else None
        if kind == "unit_ahead":
            # a spell "on" a moving unit lands a little ahead of it, toward its
            # target: Invisibility lasts only while the unit stays inside the
            # 4-tile radius (wiki: Invisibility Spell), so dropping it where she
            # stands lets a walking hero leave it within a couple of seconds
            u = self._unit(battle, arg)
            if u is None:
                return None
            tgt = (
                u.target
                if u.target is not None and getattr(u.target, "alive", False)
                else None
            )
            if tgt is None:
                return (u.x, u.y)
            dx, dy = tgt.x - u.x, tgt.y - u.y
            d = math.hypot(dx, dy)
            lead = min(2.0, d)
            return (u.x + dx / d * lead, u.y + dy / d * lead) if d > 0 else (u.x, u.y)
        if kind == "group":
            g = self._group(battle, arg)
            return self.centroid(g) if g else None
        if kind == "th":
            return (
                (battle.th.x, battle.th.y)
                if battle.th is not None and battle.th.alive
                else None
            )
        if kind == "threat":
            g = self._group(battle, arg) or self._group(battle, "main")
            if not g:
                return None
            cx, cy = self.centroid(g)
            # Wiki: Fireball, hide frontline defenses to filter its available targets.
            firing = [
                (THREAT.get(b.key, 1), b)
                for b, d in self.threats_near(battle, cx, cy, 12)
                if battle.building_targetable(b)
                and b.id not in claimed
                and b.weapon is not None
                and (b.weapon.target is not None or getattr(b.weapon, "multi", None))
            ]
            if not firing:
                return None
            b = max(firing, key=lambda tb: tb[0])[1]
            return (b.x, b.y)
        if kind == "defenders":
            # defending Clan Castle troops / heroes fighting near group arg
            # defending Clan Castle troops or heroes that are fighting the group
            g = self._group(battle, arg or "main")
            if not g:
                return None
            cx, cy = self.centroid(g)
            d = [
                u
                for u in battle.defenders
                if u.alive
                and u.target is not None
                and math.hypot(u.x - cx, u.y - cy) <= 8.0
            ]
            return self.centroid(d) if d else None
        if kind == "building":
            g = self._group(battle, "main") or [u for u in battle.attackers if u.alive]
            cx, cy = (
                self.centroid(g)
                if g
                else (
                    (battle.th.x, battle.th.y)
                    if battle.th is not None
                    else (WORLD / 2, WORLD / 2)
                )
            )
            pool = [
                b
                for b in battle.buildings
                if b.alive and b.key == arg and b.id not in claimed
            ]
            if not pool:
                return None
            b = min(pool, key=lambda b: math.hypot(b.x - cx, b.y - cy))
            return (b.x, b.y)
        raise ValueError(f"unknown anchor {at}")

    def _totem_anchor(self, battle, at, pos):
        # User (TH16 ranked, 2026-10-23): spread Totems; keep the cited anchor family.
        # game data v18.200.9: Totem.Radius=500 -> shared 5-tile spacing check.
        if not self._totem_covered(battle, pos[0], pos[1]):
            return pos
        kind, _, arg = at.partition(":")
        if kind == "defenders":
            group = self._group(battle, arg or "main")
            if not group:
                return None
            cx, cy = self.centroid(group)
            foes = [
                u
                for u in battle.defenders
                if u.alive
                and u.target is not None
                and math.hypot(u.x - cx, u.y - cy) <= 8.0
                and not self._totem_covered(battle, u.x, u.y)
            ]
            if not foes:
                return None
            target = min(foes, key=lambda u: math.hypot(u.x - pos[0], u.y - pos[1]))
            return (target.x, target.y)
        if kind in ("threat", "group"):
            group = self._group(battle, arg)
            if kind == "threat":
                group = group or self._group(battle, "main")
            if not group:
                return None
            cx, cy = self.centroid(group)
            threats = self.threats_near(battle, cx, cy, 12)
            if kind == "threat":
                threats = [
                    (b, d)
                    for b, d in threats
                    if b.weapon.target is not None or getattr(b.weapon, "multi", None)
                ]
        else:
            # Fixed, edge and unit anchors keep the original point in the spell area.
            level = spells._lvl(battle, "Totem Spell", None)
            radius = spells._radius("Totem Spell", level, 5.0)
            threats = self.threats_near(battle, pos[0], pos[1], radius)
        targets = self._totem_targets(battle, threats)
        if not targets:
            return None
        target, _, _ = min(
            targets,
            key=lambda item: (
                math.hypot(item[0].x - pos[0], item[0].y - pos[1]),
                -item[2],
            ),
        )
        return (target.x, target.y)

    # ----------------------------------------------------------- triggers
    def _inside(self, battle, u):
        """Inside the base: at least 2 tiles past the deployable area (every
        tile within 2 is a no-drop tile), not just standing on the red line."""
        blocked = battle._live_no_deploy()
        x, y = int(u.x), int(u.y)
        return all(
            (x + dx, y + dy) in blocked for dx in (-2, 0, 2) for dy in (-2, 0, 2)
        )

    def _heavy_fire(self, battle, u, frac):
        hist = self._hurt.get(u.id, [])
        recent = [h for t, h in hist if battle.t - t <= 2.0]
        lost = (max(recent) - u.hp) if recent else 0.0
        locked = any(
            b.alive
            and b.weapon is not None
            and (b.weapon.target is u or u in (getattr(b.weapon, "multi", None) or []))
            and THREAT.get(b.key, 0) >= 4
            for b in battle.buildings
        )
        return lost >= frac * u.max_hp or locked

    def _down(self, battle, name):
        """A unit the steps deployed that has fallen: none of that name is
        alive, none waits in the portal stash and no more are in the camp."""
        return (
            name in self._deployed
            and self._unit(battle, name) is None
            # Wiki: Magic Mirror, a recalled clone is not the real Hero either.
            and not any(
                u.name == name and u.kind != "hero_clone" for u in battle.portal_stash
            )
            # Video: docs/VIDEO_MEASUREMENTS.md:30, later taps may still be queued.
            and not any(
                d.name == name for d in battle.deployments[battle._next_deploy :]
            )
            and (name in heroes.HEROES or self.inventory.get(name, 0) <= 0)
        )

    def _impossible(self, battle, w):
        """The trigger can no longer come true: it waits on a unit that is down
        (an `all` with such a part, an `any` with only such parts)."""
        if not isinstance(w, dict) or not w:
            return False
        if "all" in w:
            return any(self._impossible(battle, x) for x in w["all"])
        if "any" in w:
            return all(self._impossible(battle, x) for x in w["any"])
        return any(k in w and self._down(battle, w[k]) for k in UNIT_TRIGGERS)

    def _fallen(self, battle, names=()):
        """The most recently knocked-out hero a Revive Spell can bring back
        (one of `names` when given)."""
        fallen = [
            u
            for u in battle.attackers
            if u.is_hero
            and not u.alive
            and u.extra.get("revivable")
            and (not names or u.name in names)
        ]
        return max(fallen, key=lambda u: u.extra.get("ko_at", 0.0), default=None)

    def _revive_names(self, s):
        names = []
        at = str(s.get("at", ""))
        if at.startswith(("unit:", "unit_ahead:")):
            names.append(at.split(":", 1)[1])

        def walk(w):
            if isinstance(w, dict):
                if "dead" in w:
                    names.append(w["dead"])
                for k in ("all", "any"):
                    for x in w.get(k, []):
                        walk(x)

        walk(s.get("when"))
        return names

    def _ready(self, battle, w, relax=False):
        """Is trigger w true now? relax: conditions on a unit that is down
        count as met (a deploy step then goes ahead without them)."""
        if not w:
            return True
        t = battle.t
        if "all" in w:
            return all(self._ready(battle, x, relax) for x in w["all"])
        if "any" in w:
            parts = [x for x in w["any"] if not (relax and self._impossible(battle, x))]
            return any(self._ready(battle, x, relax) for x in parts) if parts else True
        if relax and any(k in w and self._down(battle, w[k]) for k in UNIT_TRIGGERS):
            return True
        if "t" in w:
            return t >= w["t"]
        if "after" in w:
            ft = self._done.get(w["after"])
            return ft is not None and t >= ft + w.get("delay", 0.0)
        if "inside" in w:
            u = self._unit(battle, w["inside"])
            return u is not None and self._inside(battle, u)
        if "group_inside" in w:
            # "once the army enters the base": most of the group is deep
            # inside, or (ranged armies such as Throwers fight from outside)
            # most of it has been attacking buildings for 3 s
            g = self._group(battle, w["group_inside"])
            if not g:
                return False
            if sum(self._inside(battle, u) for u in g) >= max(1, len(g) // 2):
                return True
            engaged = sum(
                1
                for u in g
                if u.target is not None
                and getattr(u.target, "alive", False)
                and not isinstance(u.target, type(u))
                and u.cooldown > 0
            )
            key = "engaged_since:" + w["group_inside"]
            if engaged >= max(1, len(g) // 2):
                since = self._hurt.setdefault(key, battle.t)
                return battle.t - since >= 3.0
            self._hurt.pop(key, None)
            return False
        if "near_th" in w:
            g = self._group(battle, w["near_th"])
            if not g or battle.th is None:
                return False
            cx, cy = self.centroid(g)
            return not battle.th.alive or math.hypot(
                cx - battle.th.x, cy - battle.th.y
            ) <= w.get("r", 8.0)
        if "heavy_fire" in w:
            # any unit of that name under heavy fire (several Throwers, etc.)
            # Wiki: Magic Mirror, a clone is separate from the real Hero.
            return any(
                u.alive
                and u.name == w["heavy_fire"]
                and u.kind != "hero_clone"
                and self._heavy_fire(battle, u, w.get("frac", 0.15))
                for u in battle.attackers
            )
        if "hp_below" in w:
            u = self._unit(battle, w["hp_below"])
            return u is not None and u.hp < w.get("frac", 0.5) * u.max_hp
        if "spells_left" in w:
            return self.spells.get(
                SPELL_KEYS.get(w["spells_left"], w["spells_left"]), 0
            ) <= w.get("n", 0)
        if "dead" in w:
            # knocked out, not recalled into the portal stash
            # Wiki: Magic Mirror, only the real Queen satisfies named-Hero checks.
            return (
                self._unit(battle, w["dead"]) is None
                and w["dead"] in self._deployed
                and not any(
                    u.name == w["dead"] and u.kind != "hero_clone"
                    for u in battle.portal_stash
                )
            )
        if "defenders_near" in w:
            return self.anchor(battle, "defenders:" + w["defenders_near"]) is not None
        if "destruction" in w:
            return battle.destruction() >= w["destruction"]
        raise ValueError(f"unknown trigger {w}")

    # ------------------------------------------------------------ actions
    def _deploy(self, battle, s, pos):
        what = s["what"]
        if what in heroes.HEROES:
            if what in self._deployed:
                return False
            backpack = (
                what == "Dragon Duke"
                and self._has_backpack()
                and s.get("at", "edge:charge") in ("edge:charge", "edge:funnel")
                and not s.get("at_cite")
            )
            if backpack:
                # User (TH16 ranked, 2026-10-23): scout Backpack's centre-facing band.
                # A concrete building/unit/point anchor retains the cited deployment.
                side = s.get("at", "edge:charge").split(":", 1)[1]
                pos = self.backpack_point(battle, self._edge_angle(side))
            self._drop(
                battle,
                what,
                pos[0],
                pos[1],
                s.get("group", "main"),
                jitter=0.3,
                fixed_point=backpack,
            )
            self._deployed.add(what)
            return True
        left = self.inventory.get(what, 0)
        n = left if s.get("count") in (None, "all") else min(left, int(s["count"]))
        if n <= 0:
            return False
        at = str(s.get("at", ""))
        # Video: docs/VIDEO_MEASUREMENTS.md:30 -> 0.133 s between held troops.
        tap = PACE_TAP * float(os.environ.get("BASELAB_PACE", "1.0"))
        spread = s.get("spread", 1.0)
        if at.startswith("edge:") and n >= 3 and what not in LINE_EXEMPT:
            # Several edge troops are dragged along the deploy border; the
            # neutral line is about a tile apart, at most 8 tiles wide.
            # output/research/usage/archer.md: spread deployments avoid splash.
            # A spread multiplier scales this formation, never selects a stack.
            # https://clashofclans.fandom.com/wiki/Archer
            ang = self._edge_angle(at.split(":", 1)[1])
            w = min(float(n - 1), 8.0) * spread
            for i in range(n):
                x, y = edge_point(battle, ang, -w / 2 + w * i / (n - 1))
                self._drop(
                    battle,
                    what,
                    x,
                    y,
                    s.get("group", "main"),
                    jitter=0.3 * spread,
                    at=battle.t + i * tap,
                )
        else:
            for i in range(n):
                self._drop(
                    battle,
                    what,
                    pos[0],
                    pos[1],
                    s.get("group", "main"),
                    jitter=spread,
                    at=battle.t + i * tap,
                )
        self.inventory[what] = left - n
        self._deployed.add(what)
        return True

    def _spell(self, battle, s, pos):
        k = SPELL_KEYS.get(s["what"])
        if k is None or not self._have(k):
            return False
        self.cast_spell(
            battle,
            SPELL_NAMES[k],
            pos[0],
            pos[1],
            level=s.get("level"),
            origin=s.get("origin"),
        )
        return True

    def _missing_equipment(self, st, u=None):
        # Wiki: Hero Equipment, an ability requires its equipment to be equipped.
        # Only the action names its required item; citations can discuss other kits.
        if not hasattr(self, "_equipment_steps"):
            self._equipment_steps = {}
        if st["id"] not in self._equipment_steps:
            text = str(st.get("ability") or st["id"]).replace("_", " ").lower()
            required = st.get("equipment") or next(
                (
                    name
                    for name, record in stats.registry().items()
                    if record["kind"] == "equipment"
                    and record.get("attrs", {}).get("raw", {}).get("User") == st["what"]
                    and name.lower() in text
                ),
                None,
            )
            aliases = {
                "Archer Queen": (
                    ("arrow", "Giant Arrow"),
                    ("queen shot", "Giant Arrow"),
                    ("healers out", "Healer Puppet"),
                ),
                "Grand Warden": (("tome", "Eternal Tome"), ("torch", "Heroic Torch")),
                "Royal Champion": (("spear", "Rocket Spear"),),
                "Dragon Duke": (
                    ("backpack", "Rocket Backpack"),
                    ("jetpack", "Rocket Backpack"),
                    ("blaster", "Stun Blaster"),
                    ("stun", "Stun Blaster"),
                ),
            }
            for word, equipment in aliases.get(st["what"], ()):
                if word in text and not required:
                    required = equipment
            aim = st.get("aim", "")
            if not st.get("equipment"):
                if aim == "arrow" or (
                    aim.startswith("building:") and st["what"] == "Archer Queen"
                ):
                    required = "Giant Arrow"
                elif aim == "dash":
                    required = "Rocket Backpack"
                elif aim.startswith("building:") and st["what"] == "Grand Warden":
                    required = "Fireball"
            self._equipment_steps[st["id"]] = [required] if required else []
        loadout = self.loadouts.get(st["what"]) or heroes.DEFAULT_LOADOUTS.get(
            st["what"]
        )
        equipped = (
            u.kit.equip
            if u is not None and u.kit is not None
            else (loadout.equipment if loadout is not None else ())
        )
        return next(
            (
                name
                for name in self._equipment_steps[st["id"]]
                if name not in equipped
                or (self.account_equipment and name not in self.equipment_levels)
            ),
            None,
        )

    def _ad_target_count(self, st):
        # Wiki: Giant Arrow, multiple Air Defenses can share a shot; the step's
        # citations specify how many targets the later hero ability intends.
        if st["action"] != "ability":
            return 0
        aim = st.get("aim", "")
        # Wiki: Giant Arrow/Fireball, aimed damaging abilities can remove defenses.
        # Protective abilities mentioning Air Defenses do not reserve targets.
        equipment = {
            "Archer Queen": "Giant Arrow",
            "Grand Warden": "Fireball",
        }.get(st["what"])
        if (
            equipment is None
            or aim not in ("arrow", "building:ad")
            or (aim == "arrow" and st["what"] != "Archer Queen")
            or st.get("equipment", equipment) != equipment
        ):
            return 0
        quotes = " ".join(
            c.get("quote", "") for c in st.get("aim_cite", []) + st.get("cite", [])
        ).lower()
        if aim != "building:ad" and "air defense" not in quotes:
            return 0
        count = 1
        for word, number in (
            ("two", 2),
            ("three", 3),
            ("four", 4),
            ("both", 2),
            ("both those", 2),
            ("couple of", 2),
        ):
            if word + " air defenses" in quotes:
                count = max(count, number)
        return count

    def _ability(self, battle, s):
        u = self._unit(battle, s["what"])
        if (
            u is None
            or u.kit is None
            or u.ability_used
            or self._missing_equipment(s, u)
        ):
            return False
        # Policy: the line hold and any paired cast share this step's AIM_WAIT window.
        since = self._aim_since.setdefault(s["id"], battle.t)
        deadline = since + AIM_WAIT
        # Wiki: Fireball/Rocket Spear, automatic aim cannot extend the policy hold.
        if battle.t >= deadline:
            return self._fire_aimed(battle, u, deadline=deadline)
        # Wiki: Giant Arrow needs its cited target; Fireball can hit another cluster.
        if (
            self._ad_target_count(s)
            and not u.kit.has("Fireball")
            and not any(b.alive and b.key == "ad" for b in battle.buildings)
        ):
            return False
        if str(s.get("aim", "")).startswith("building:"):
            if self._aim_building(
                battle, u, s["aim"].split(":", 1)[1], deadline=deadline
            ):
                return True
            # not lined up yet: keep trying; after AIM_WAIT s fire it normally
            # rather than hold the ability all battle (an assumption)
            if battle.t - since >= AIM_WAIT:
                return self._fire_aimed(battle, u, deadline=deadline)
            return False
        if s.get("aim") == "arrow" and self._ad_target_count(s):
            # Wiki: Giant Arrow, keep the cited Air Defense line and target count.
            if self._aim_building(
                battle, u, "ad", deadline=deadline, count=self._ad_target_count(s)
            ):
                return True
            if battle.t >= deadline:
                return self._fire_aimed(battle, u, deadline=deadline)
            return False
        if u.kit.has("Giant Arrow") or u.kit.has("Rocket Backpack"):
            # Wiki: Giant Arrow/Rocket Backpack, timing does not redirect the ability.
            return self._line_ability(battle, u, deadline=deadline)
        if s.get("aim"):
            if self._aim(battle, u, s["aim"]):
                return self._fire_aimed(battle, u, deadline=deadline)
            return False
        if u.kit.has("Fireball") or (
            u.name == "Royal Champion"
            and (u.kit.has("Rocket Spear") or u.kit.has("Seeking Shield"))
        ):
            # Wiki: Fireball/Rocket Spear/Seeking Shield, time automatic aim for value.
            return self._cluster_ability(battle, u)
        heroes.activate(battle, u)
        return True

    @property
    def _aim_since(self):
        if not hasattr(self, "_aim_t"):
            self._aim_t = {}
        return self._aim_t

    def _aim_building(self, battle, u, key, *, deadline=None, count=1):
        """An ability aimed at a building (e.g. "arrow through the CC"). Giant
        Arrow: wait until the Queen's current firing line crosses the building.
        Fireball: it always flies at the closest defense (wiki: Fireball), so
        the Warden fires it once that defense is within the blast radius of
        the building. The step waits until then; if the building is gone it
        fires normally."""
        tgt = min(
            (b for b in battle.buildings if b.alive and b.key == key),
            key=lambda b: math.hypot(b.x - u.x, b.y - u.y),
            default=None,
        )
        if tgt is None:
            if u.kit.has("Fireball") or (
                u.name == "Royal Champion"
                and (u.kit.has("Rocket Spear") or u.kit.has("Seeking Shield"))
            ):
                # User (TH16 ranked, 2026-10-23): scout a cluster if the anchor is gone.
                return self._cluster_ability(battle, u)
            # Wiki: Giant Arrow, do not replace the cited Air Defense shot.
            if key == "ad":
                return False
            if u.kit.has("Giant Arrow"):
                # User (TH16 ranked, 2026-10-23): score the live line if its anchor fell.
                return self._line_ability(battle, u, deadline=deadline)
            heroes.activate(battle, u)
            return True
        if u.kit.has("Giant Arrow"):
            # Wiki: Giant Arrow, fires toward the Queen's current target and
            # travels through the entire village; building distance is no limit.
            band, effect = self._ability_band(battle, u)
            if band is None:
                return False
            hits = sum(
                1
                for b in battle.buildings
                if b.key == key
                and battle.building_targetable(b)
                and _band_hit(b, band, effect[0], effect[1])
            )
            if hits >= count:
                return self._fire_aimed(battle, u, deadline=deadline)
            return False
        if u.kit.has("Fireball"):
            defs = heroes._targets(battle, defenses=True)
            if not defs:
                return False
            near = min(defs, key=lambda b: heroes._distance(b, u.x, u.y))
            radius = heroes._col("Fireball", u.kit.lv("Fireball"), "damage radius")
            if tgt.edge_distance(near.x, near.y) > radius:
                return False
            heroes.activate(battle, u)
            return True
        heroes.activate(battle, u)
        return True

    def _pendant_possible(self, battle):
        # output/research/usage/minion-prince.md: Pendant recalls the Prince
        # and nearby allies for a later redeployment.
        # https://clashofclans.fandom.com/wiki/Portal_Pendant
        name = "Minion Prince"
        unit = self._unit(battle, name)
        if unit is not None:
            return (
                not unit.ability_used
                and unit.kit is not None
                and unit.kit.has("Portal Pendant")
            )
        pending = any(
            step["action"] == "deploy"
            and step.get("what") == name
            and step["id"] not in self._done
            and step["id"] not in self._cancelled
            for step in self.steps
        ) or any(d.name == name for d in battle.deployments[battle._next_deploy :])
        if not pending or self._down(battle, name):
            return False
        loadout = self.loadouts.get(name) or heroes.DEFAULT_LOADOUTS[name]
        return "Portal Pendant" in loadout.equipment and (
            not self.account_equipment or "Portal Pendant" in self.equipment_levels
        )

    def _cannot(self, battle, st):
        """Why step st can no longer happen (None while it still can)."""
        act, what = st["action"], st.get("what")
        at = str(st.get("at", ""))
        target = None
        if at.startswith(("unit:", "unit_ahead:")) and what != "Revive Spell":
            target = at.split(":", 1)[1]  # a Revive is for a fallen hero
        elif act == "ability":
            target = what
        if target and self._down(battle, target):
            return target + " down"  # Recall a dead Champion, Invisibility on her
        if act == "deploy":
            if what in heroes.HEROES:
                return what + " already deployed" if what in self._deployed else None
            return None
        # Wiki: Hero Equipment, an ability already being held keeps its own deadline.
        holding = act == "ability" and st["id"] in self._aim_since
        if not holding and self._impossible(battle, st.get("when")):
            return "waits on a unit that is down"
        if act in ("spell", "recall"):
            k = "recall" if act == "recall" else SPELL_KEYS.get(what)
            if k is not None and self.spells.get(k, 0) <= 0:
                return "no " + SPELL_NAMES[k] + " left"
            if at.startswith("building:") and not any(
                b.alive and b.key == at[9:] for b in battle.buildings
            ):
                return at[9:] + " gone"
            if at == "th" and (battle.th is None or not battle.th.alive):
                return "Town Hall gone"
        elif act == "ability":
            u = self._unit(battle, what)
            missing = self._missing_equipment(st, u)
            if missing:
                return "missing " + missing
            if u is not None and (u.kit is None or u.ability_used):
                return "ability already used"
            # Wiki: Giant Arrow, skip an Air Defense shot when its targets are gone.
            # Wiki: Fireball, a lost anchor can be replaced by another defense cluster.
            if (
                self._ad_target_count(st)
                and what != "Grand Warden"
                and not any(b.alive and b.key == "ad" for b in battle.buildings)
            ):
                return "ad gone"
        elif act == "redeploy":
            if (
                not battle.portal_stash
                and self.spells.get("recall", 0) <= 0
                and battle.t - self._last("recall") > 5.0
                and not self._pendant_possible(battle)
            ):
                return "nothing recalled"
        elif act == "release_siege":
            # Wiki: Siege Barracks, destruction already releases the Clan Castle troops.
            name = what or self.siege
            if (
                self.inventory.get(name, 0) <= 0
                and not any(
                    u.alive and u.kind == "siege" and (what is None or u.name == what)
                    for u in battle.attackers
                )
                and not any(
                    d.name == name for d in battle.deployments[battle._next_deploy :]
                )
            ):
                return "no siege left"
        return None

    def on_tick(self, battle):
        if not hasattr(self, "_deployed"):
            self._deployed = set()
        # output/hunt/r9/s2.out #4: pets, summons and cargo also arrive in battle.
        # output/research/usage/archer-queen.md: Mirror clones are separate heroes.
        # https://clashofclans.fandom.com/wiki/Magic_Mirror
        self._deployed.update(
            unit.name for unit in battle.attackers if unit.kind != "hero_clone"
        )
        t = battle.t
        self.opening_actions(battle)
        if int(t * 10) % 5 == 0:
            for u in battle.attackers:
                if u.alive and (u.is_hero or u.housing >= 5):
                    h = self._hurt.setdefault(u.id, [])
                    h.append((t, u.hp))
                    if len(h) > 8:
                        del h[0]
        alive = any(
            u.alive and u.name != "Totem" and u.kind not in ("pet", "siege_idle")
            for u in battle.attackers
        )
        if alive:
            self._last_alive = t
        stalled = t - getattr(self, "_last_alive", 0.0) > 3.0
        # a step that can no longer happen is skipped so the steps chained
        # after it go ahead, as a player moves on when a charge dies
        for st in self.steps:
            if st["id"] in self._cancelled:
                continue
            if st["id"] not in self._done or st.get("every"):
                why = self._cannot(battle, st)
                if (
                    not why
                    and st.get("every")
                    and st.get("until")
                    and self._ready(battle, st["until"])
                ):
                    why = "until reached"
                if why:
                    # Wiki: Invisibility Spell, remaining copies can support other units.
                    self._done.setdefault(st["id"], t)
                    self._cancelled.add(st["id"])
                    self.log_steps.append(
                        (round(t, 1), st["id"] + " (skipped: " + why + ")")
                    )
        # Wiki: Lightning Spell, remove defenses to pave the way for troops.
        if not self._zap_done and self.zap_ad != (0, 0):
            self._fallback_spells(battle, opening=True)
        # the consolidated playbook's own steps first; steps added later for
        # units it never deployed (completion) and uncited fallbacks fill in
        # when none of those is ready
        order = [x for x in self.steps if not (x.get("completion") or x.get("uncited"))]
        order += [x for x in self.steps if x.get("completion") or x.get("uncited")]
        for s in order:
            if t < getattr(self, "_busy_until", 0.0):
                break  # the player's hands are still on the last action
            sid = s["id"]
            rep = s.get("every")
            if sid in self._cancelled or (sid in self._done and not rep):
                continue
            act = s["action"]
            forced = False
            if rep and sid in self._done:
                if t < self._next.get(sid, 0.0) or (
                    s.get("until") and self._ready(battle, s["until"])
                ):
                    continue
            # Wiki: Hero Equipment, the original trigger only starts the bounded hold.
            elif not (act == "ability" and sid in self._aim_since) and not self._ready(
                battle, s.get("when")
            ):
                # troops still go in when the army is wiped out (stalled), when
                # the trigger waits on a unit that is down, and by LATE
                forced = act == "deploy" and (
                    stalled
                    or t >= LATE
                    or (
                        self._impossible(battle, s.get("when"))
                        and self._ready(battle, s.get("when"), relax=True)
                    )
                )
                if not forced:
                    continue
            # Playbook: root-rider.json, exhausted main_ice still waits for its trigger.
            if (
                act == "deploy"
                and s.get("what") not in heroes.HEROES
                and self.inventory.get(s.get("what"), 0) <= 0
            ):
                why = "no " + s["what"] + " left"
                self._done.setdefault(sid, t)
                self._cancelled.add(sid)
                self.log_steps.append((round(t, 1), sid + " (skipped: " + why + ")"))
                continue
            ok = False
            before = self.inventory.get(s.get("what"), 0)
            if act == "release_siege":
                ok = battle.release_siege(s.get("what"))
            elif act == "ability":
                ok = self._ability(battle, s)
            else:
                if s.get("what") == "Revive Spell":
                    # a Revive goes on the fallen hero it is for (radius 8,
                    # wiki: Revive Spell), wherever the step's anchor points
                    hero = self._fallen(battle, self._revive_names(s))
                    pos = (hero.x, hero.y) if hero is not None else None
                else:
                    pos = self.anchor(
                        battle, s.get("at", "edge:main"), unclaimed=act == "spell"
                    )
                if pos is None and forced:
                    pos = self._edge(
                        battle, "main"
                    )  # the anchor is gone: with the main push (as rest steps)
                # User (TH16 ranked, 2026-10-23): wait rather than stack Totems.
                totem_covered = False
                if (
                    act == "spell"
                    and s.get("what") == "Totem Spell"
                    and pos is not None
                ):
                    pos = self._totem_anchor(battle, s.get("at", "edge:main"), pos)
                    totem_covered = pos is None
                if pos is None:
                    if act in ("spell", "recall") and s.get("what") != "Revive Spell":
                        # ready but nothing to cast on (no defense firing, the
                        # group gone): after AIM_WAIT the player moves on
                        since = self._no_target.setdefault(sid, t)
                        if totem_covered and t == since:
                            self.log_steps.append(
                                (round(t, 1), sid + " (waiting: Totem area covered)")
                            )
                        if t - since >= AIM_WAIT:
                            self._done.setdefault(sid, t)
                            self._cancelled.add(sid)
                            why = "Totem area covered" if totem_covered else "no target"
                            self.log_steps.append(
                                (round(t, 1), sid + " (skipped: " + why + ")")
                            )
                    continue
                self._no_target.pop(sid, None)
                if act == "deploy":
                    ok = self._deploy(battle, s, pos)
                elif act in ("spell", "recall"):
                    # a recall step's "what" may name the unit recalled; the
                    # spell is always Recall
                    ok = self._spell(
                        battle,
                        {
                            **s,
                            "what": (
                                "Recall Spell" if act == "recall" else s.get("what")
                            ),
                        },
                        pos,
                    )
                elif act == "redeploy":
                    if battle.portal_stash and t >= battle.portal_ready_at:
                        # Playbook: gWXxU_sp7Kg 43.5, Queen returns with Bowlers and Warden.
                        for u in battle.portal_stash:
                            u.group = s.get("group", "main")
                        heroes.portal_redeploy(battle, pos[0], pos[1])
                        ok = True
            if ok:
                n = (
                    max(1, before - self.inventory.get(s.get("what"), 0))
                    if act == "deploy"
                    else 1
                )
                self._busy_until = t + action_time(act, n)
            if ok or s.get("skip_if_impossible"):
                if sid not in self._done:
                    self._done[sid] = t
                    self.log_steps.append((round(t, 1), sid))
                if rep:
                    self._next[sid] = t + rep
        if t >= getattr(self, "_busy_until", 0.0):
            # troops whose steps were skipped (their anchor unit fell) are
            # still in the camp: they go in with the main push (uncited, as
            # the rest steps of fit_steps)
            # Wiki: Healer, undeployed non-healing reserves must still be used.
            pending = {
                x.get("what")
                for x in self.steps
                if x["action"] == "deploy" and x["id"] not in self._done
            }
            left = next(
                (n for n, c in self.inventory.items() if c > 0 and n not in pending),
                None,
            )
            if left is not None:
                n = self.inventory[left]
                self._deploy(
                    battle,
                    {
                        "id": "late-" + left,
                        "what": left,
                        "count": "all",
                        "at": "edge:main",
                    },
                    self._edge(battle, "main"),
                )
                self._busy_until = t + action_time("deploy", n)
                self.log_steps.append((round(t, 1), "late-" + left))
        if (
            t >= getattr(self, "_busy_until", 0.0)
            and not self.siege
            and self.cc_troops
            and not self._cc_released
            and (
                stalled
                or t >= LATE
                or any(
                    step["action"] == "deploy"
                    and step.get("group", "main") == "main"
                    and step["id"] in self._done
                    and step["id"] not in self._cancelled
                    for step in self.steps
                )
            )
        ):
            # output/research/usage/cleanup-troops-and-end-of-attack-play.md:
            # commit unused support with the push, or rescue a stalled attack.
            # https://www.youtube.com/watch?v=ahiJ-bgdmSE&t=2125
            x, y = self._edge(battle, "main")
            units.release_cc_at(battle, x, y, "main")
            self._busy_until = t + action_time("deploy")
            self.log_steps.append((round(t, 1), "clan-castle"))
        self._fallback_spells(battle)

    # ------------------------------------------------- uncited spell fallback
    def _step_kinds(self):
        if not hasattr(self, "_step_spells"):
            kinds = set()
            for st in self.steps:
                if st["action"] == "recall":
                    kinds.add("recall")
                elif st["action"] == "spell" and st.get("what") in SPELL_KEYS:
                    kinds.add(SPELL_KEYS[st["what"]])
            self._step_spells = kinds
        # Wiki: Revive Spell, heroes can be revived repeatedly while spells remain.
        self.auto_revive = not any(
            st["action"] == "spell"
            and st.get("what") == "Revive Spell"
            and st["id"] not in self._cancelled
            and (st["id"] not in self._done or st.get("every"))
            for st in self.steps
        )
        return self._step_spells

    def _have(self, kind):
        if getattr(self, "_fallback", False) and kind in self._step_kinds():
            # the playbook keeps one copy for each of its own steps for this
            # spell that has not fired yet (all of them while it repeats one);
            # copies beyond that go to the fallback
            # Wiki: Invisibility Spell, copies are not tied to the original hero.
            mine = [
                st
                for st in self.steps
                if st["id"] not in self._cancelled
                and (
                    (st["action"] == "recall" and kind == "recall")
                    or (
                        st["action"] == "spell"
                        and SPELL_KEYS.get(st.get("what")) == kind
                    )
                )
            ]
            if any(st.get("every") for st in mine):
                return False
            return self.spells.get(kind, 0) > sum(
                1 for st in mine if st["id"] not in self._done
            )
        return super()._have(kind)

    def _zap(self, battle, *, single_cast=False):
        # Wiki: Giant Arrow, line up Air Defenses and save Lightning for others.
        if not hasattr(self, "_ad_reservations"):
            self._ad_reservations = {}
        reserved = set()
        for st in self.steps:
            count = self._ad_target_count(st)
            if not count or st["id"] in self._done or st["id"] in self._cancelled:
                continue
            # Wiki: Hero Equipment, only an unused equipped ability can fire.
            u = self._unit(battle, st["what"])
            if self._missing_equipment(st, u) or (
                u is not None and (u.kit is None or u.ability_used)
            ):
                continue
            if u is None and not (
                any(
                    s["action"] == "deploy"
                    and s.get("what") == st["what"]
                    and s["id"] not in self._done
                    and s["id"] not in self._cancelled
                    for s in self.steps
                )
                or any(
                    d.name == st["what"]
                    for d in battle.deployments[battle._next_deploy :]
                )
            ):
                continue
            if st["id"] not in self._ad_reservations:
                deploy = next(
                    (
                        s
                        for s in self.steps
                        if s["action"] == "deploy" and s.get("what") == st["what"]
                    ),
                    {},
                )
                pos = self.anchor(battle, deploy.get("at", "edge:main")) or self._edge(
                    battle, "main"
                )
                ads = sorted(
                    (
                        b
                        for b in battle.buildings
                        if b.alive and b.key == "ad" and b.id not in reserved
                    ),
                    key=lambda b: math.hypot(b.x - pos[0], b.y - pos[1]),
                )
                self._ad_reservations[st["id"]] = [b.id for b in ads[:count]]
            reserved.update(self._ad_reservations[st["id"]])
        super()._zap(battle, single_cast=single_cast, reserved=reserved)

    def _fallback_spells(self, battle, *, opening=False):
        """Spells the playbook never names are used by the general spell
        logic of the scripted plans (Freeze heavy defenses on the push, Rage
        when engaged, Heal under fire, Lightning on an Air Defense, Revive).
        This is NOT from a source: the playbooks only narrate some spells, and
        a real player does not finish an attack with half of them unused."""
        self._step_kinds()
        t = battle.t
        if t < getattr(self, "_next_fallback", 0.0) or t < getattr(
            self, "_busy_until", 0.0
        ):
            return
        self._next_fallback = t + 0.5
        if not opening:
            # Wiki: Hero abilities, save endangered heroes before another spare
            # spell. A pending cited trigger holds normal timing, never low-HP
            # emergency use. This policy does not wait for automatic KO use.
            for u in battle.attackers:
                if not u.alive or not u.is_hero or u.kit is None or u.ability_used:
                    continue
                threshold = self.P(
                    "warden_hp"
                    if u.name == "Grand Warden"
                    else "duke_hp" if u.name == "Dragon Duke" else "hero_hp"
                )
                if u.hp / max(1.0, u.max_hp) < threshold:
                    heroes.activate(battle, u)
                    if u.ability_used:
                        self._busy_until = t + action_time("ability")
                        return
        # Wiki: Lightning Spell, opening defense removal precedes the troop push.
        if not self._zap_done and self.zap_ad != (0, 0):
            self._fallback = True
            left = sum(self.spells.values())
            try:
                self._zap(battle, single_cast=True)
            finally:
                self._fallback = False
            if sum(self.spells.values()) < left:
                self._busy_until = t + action_time("spell")
                return
        if opening:
            return
        # Wiki: Electro Dragon, spare Lightning can remove an Air Sweeper.
        self._fallback = True
        try:
            cast = self._spare_lightning(battle)
            if not cast:
                # Wiki: Earthquake Spell, spare casts weaken clustered defenses.
                cast = self._spare_quake(battle)
        finally:
            self._fallback = False
        if cast:
            self._busy_until = t + action_time("spell")
            return
        # Video: docs/VIDEO_MEASUREMENTS.md:31, spell drops are separate actions.
        left = sum(self.spells.values())
        self.revive_knocked_out(battle, single_cast=True)
        if sum(self.spells.values()) < left:
            self._busy_until = t + action_time("spell")
            return
        if (
            battle.portal_stash
            and t >= battle.portal_ready_at
            and not any(
                st["action"] == "redeploy" and st["id"] not in self._done
                for st in self.steps
            )
        ):
            # units no redeploy step will bring back (a Portal Pendant or a
            # fallback Recall): redeployed where most buildings stand, as the
            # scripted plans do
            x, y = self.portal_point(battle)
            heroes.portal_redeploy(battle, x, y)
            self._busy_until = t + action_time("redeploy")
            return
        main = self.main_units(battle)
        if not main:
            # Wiki: Battle Blimp, cargo support continues without a surviving push.
            main = self._cargo_support(battle) or []
            if not main:
                # Wiki: Heroes, independent charges and funnel flanks still
                # receive spare support after the main push has fallen.
                main = [
                    u
                    for u in battle.attackers
                    if u.alive and u.name != "Totem" and u.kind != "pet"
                ]
        self._fallback = True
        left = sum(self.spells.values())
        try:
            if getattr(self, "_fallback_quakes", None):
                x, y = self._fallback_quakes.pop(0)
                if self._have("eq"):
                    self._use(battle, "eq", x, y)
            if sum(self.spells.values()) == left:
                self.generic_spells(battle, main, single_cast=True)
        finally:
            self._fallback = False
        if sum(self.spells.values()) < left:
            self._busy_until = t + action_time("spell")
            return
        # heroes whose ability the playbook never names use the scripted
        # plans' ability timing (uncited, like the spells above); the
        # playbook's own ability steps keep control of theirs
        mine = {
            st.get("what")
            for st in self.steps
            if st["action"] == "ability" and st["id"] not in self._done
        }
        held = [
            u
            for u in battle.attackers
            if u.alive and u.is_hero and u.name in mine and not u.ability_used
        ]
        for u in held:
            u.ability_used = True
        try:
            self.hero_abilities(battle)
        finally:
            for u in held:
                u.ability_used = False


def _usable(st, have, heroes_in, pets, steps):
    w = st.get("what")
    at = str(st.get("at", ""))
    if at.startswith(("unit:", "unit_ahead:")):
        name = at.split(":", 1)[1]
        if name in stats.registry() and stats.record(name)["kind"] == "pet":
            # Wiki: Spirit Fox, invisibility belongs to its assigned Hero.
            named = []

            def find_heroes(trigger):
                if not isinstance(trigger, dict):
                    return
                for key in UNIT_TRIGGERS + ("dead",):
                    if trigger.get(key) in heroes.HEROES:
                        named.append(trigger[key])
                for key in ("all", "any"):
                    for part in trigger.get(key, []):
                        find_heroes(part)

            find_heroes(st.get("when"))
            if not named:
                named = [
                    step["what"]
                    for step in steps
                    if step["action"] == "deploy"
                    and step.get("what") in heroes.HEROES
                    and step.get("group", "main") == st.get("group", "main")
                ]
            if not any(pets.get(hero) == name for hero in named or heroes_in):
                return False
    if st["action"] in ("deploy", "release_siege"):
        return w in have
    if st["action"] == "recall":
        return "Recall Spell" in have
    if st["action"] == "spell":
        return w in have
    if st["action"] == "ability":
        return w in heroes_in
    if st["action"] == "redeploy":
        return w is None or w in heroes_in
    return True


def pick_variants(
    pb: dict,
    inventory: dict,
    heroes_in: list,
    spells: dict,
    loadouts=None,
    selected=None,
    equipment_levels=None,
    account_equipment=False,
) -> list:
    """The playbook's steps with its cited variants swapped in where the
    army needs them: a variant that replaces steps this army cannot play
    (e.g. a Flame Flinger it does not bring) with steps it can (its Log
    Launcher) takes their place. Best-supported repairs come first. Explicit
    selections also allow feasible alternatives and additive variants; their
    complete sequence must fit the stock and required equipment."""
    have = (
        set(inventory)
        | set(heroes_in)
        | {SPELL_NAMES[k] for k, c in spells.items() if c}
    )
    # Wiki: Spirit Fox, the pet supports its assigned Hero, not another hero.
    pets = {}
    for hero in heroes_in:
        loadout = (loadouts or {}).get(hero) or heroes.DEFAULT_LOADOUTS.get(hero)
        pets[hero] = loadout.pet if loadout is not None else None
    # deep copies: plan construction edits steps (e.g. appends a cite in
    # from_playbook), which used to mutate the cached playbook itself, so
    # every later plan of the family accumulated another citation
    steps = copy.deepcopy(pb["steps"])
    checker = PlaybookPlan(
        loadouts=loadouts or {},
        equipment_levels=equipment_levels or {},
        account_equipment=account_equipment,
    )

    def feasible(candidate, added):
        stock = {**inventory, **{hero: 1 for hero in heroes_in}}
        stock.update({SPELL_NAMES[k]: count for k, count in spells.items()})
        for st in candidate:
            usable = _usable(st, have, heroes_in, pets, candidate)
            if st["action"] == "ability":
                checker._equipment_steps = {}
                usable = usable and not checker._missing_equipment(st)
            if not usable:
                if st["id"] in added:
                    return False
                continue
            if st["action"] not in ("deploy", "spell", "recall"):
                continue
            name = "Recall Spell" if st["action"] == "recall" else st.get("what")
            left = stock.get(name, 0)
            amount = st.get("count", 1)
            amount = left if amount in (None, "all") else int(amount)
            if amount <= 0 or amount > left:
                return False
            stock[name] = left - amount
        return True

    used = set()
    for v in sorted(pb.get("variants", []), key=lambda v: -v.get("support", 0)):
        repl = set(v.get("replaces") or [])
        cur = [x for x in steps if x["id"] in repl]
        # Playbook: Yeti, KDalGKrAyL0 50.2 -> Barracks and Queen share the variant.
        requested = selected is not None and v["name"] in selected
        if selected is not None and not requested:
            continue
        if repl & used or (repl and not cur):
            continue
        new = [dict(copy.deepcopy(x), variant=v["name"]) for x in v.get("steps", [])]
        if not new or not all(_usable(x, have, heroes_in, pets, new) for x in new):
            continue
        i = min((n for n, x in enumerate(steps) if x["id"] in repl), default=len(steps))
        candidate = [x for x in steps if x["id"] not in repl]
        candidate[i:i] = new
        if not feasible(candidate, {x["id"] for x in new}):
            if requested:
                raise ValueError(f"Infeasible playbook variant: {v['name']}")
            continue
        # Policy: automatic substitution repairs unusable defaults. Explicit
        # selection also exposes feasible alternatives and additive variants.
        if not requested and (
            not repl
            or all(_usable(x, have, heroes_in, pets, steps) for x in cur)
            and feasible(steps, {x["id"] for x in cur})
        ):
            continue
        steps = candidate
        used.update(repl)
    if selected is not None:
        applied = {st.get("variant") for st in steps}
        missing = set(selected) - applied
        if missing:
            raise ValueError(
                "Unavailable playbook variants: " + ", ".join(sorted(missing))
            )
    return steps


def fit_steps(
    steps: list, inventory: dict, heroes_in: list, spells: dict, cc=()
) -> list:
    """The playbook's steps for a particular army: steps for troops, heroes
    or spells the army does not carry are dropped, and any step triggered
    "after" a dropped step inherits the dropped step's own trigger (delays
    add), so the sequence still flows. So are spells and abilities cast on,
    or only triggered by, a unit the playbook deploys but this army does not
    bring (Invisibility on a Royal Champion it leaves at home); a condition
    on such a unit inside an `all` / `any` is left out, and a deploy step
    whose whole trigger is one goes in with the main push. A redeploy step
    needs a Recall Spell to have something to redeploy. Troops the steps
    never mention join the main push right after its first deploy: that
    last rule is NOT from a source (real armies differ from the playbook's
    example army) and is marked "uncited". Unmentioned heroes inherit the
    place/group/trigger of a comparable cited hero, preferring an absent
    assault or ranged-support hero. `cc`: the Clan Castle troops."""
    # Policy (uncited): roster substitutions inherit a comparable cited hero's
    # place, group and trigger, preferably replacing an absent hero. King/RC/
    # Duke are assault heroes; Queen/Prince/Warden are ranged support. This
    # retains a funnel or a delayed push instead of treating a siege as a tank.
    templates = [
        st
        for st in steps
        if st["action"] == "deploy" and st.get("what") in heroes.HEROES
    ]
    mentioned_heroes = {st["what"] for st in templates}
    assault = {"Barbarian King", "Royal Champion", "Dragon Duke"}
    replacements = set()
    steps = copy.deepcopy(steps)
    for hero in heroes_in:
        if hero in mentioned_heroes:
            continue
        comparable = [
            st for st in templates if (st["what"] in assault) == (hero in assault)
        ]
        choices = comparable or templates
        if not choices:
            continue
        template = min(
            choices,
            key=lambda st: (
                st["what"] in heroes_in,
                st["what"] in replacements,
                st.get("group", "main") == "charge",
                st["what"] == "Grand Warden",
            ),
        )
        replacements.add(template["what"])

        def substitute(value):
            if isinstance(value, dict):
                return {k: substitute(v) for k, v in value.items()}
            if isinstance(value, list):
                return [substitute(v) for v in value]
            return hero if value == template["what"] else value

        place = template.get("at", "edge:main")
        if place in ("unit:" + template["what"], "unit_ahead:" + template["what"]):
            place = "edge:main"
        steps.append(
            {
                "id": f"rest-{hero}",
                "action": "deploy",
                "what": hero,
                "count": 1,
                "at": place,
                "group": template.get("group", "main"),
                "when": substitute(copy.deepcopy(template.get("when"))),
                "uncited": True,
                "cite": [],
            }
        )
    have = (
        set(inventory)
        | set(heroes_in)
        | {SPELL_NAMES[k] for k, c in spells.items() if c}
    )
    bring = (
        set(inventory)
        | set(heroes_in)
        | {e if isinstance(e, str) else e.get("name") or e.get("type") for e in cc}
    )
    # units the playbook itself deploys (summons such as Firemites or pets
    # are never "absent")
    army_units = {x.get("what") for x in steps if x["action"] == "deploy"} | set(
        heroes.HEROES
    )

    def absent(name):
        return name in army_units and name not in bring

    def absent_cond(w):
        return isinstance(w, dict) and any(
            k in w and absent(w[k]) for k in UNIT_TRIGGERS + ("dead",)
        )

    def usable(st):
        w = st.get("what")
        at = str(st.get("at", ""))
        if at.startswith(("unit:", "unit_ahead:")) and absent(at.split(":", 1)[1]):
            return False
        if st["action"] != "deploy" and absent_cond(st.get("when")):
            return False
        if st["action"] in ("deploy",):
            return w in have
        if st["action"] == "recall":
            return "Recall Spell" in have
        if st["action"] == "spell":
            return w in have
        if st["action"] == "ability":
            return w in heroes_in
        if st["action"] == "redeploy":
            return (w is None or w in heroes_in) and "Recall Spell" in have
        return True

    steps = [dict(x) for x in steps]
    dropped = {x["id"]: x for x in steps if not usable(x)}
    casters = {
        ("Recall Spell" if x["action"] == "recall" else x.get("what"))
        for x in steps
        if x["id"] not in dropped and x["action"] in ("spell", "recall")
    }

    def relink(w):
        """w with dropped steps and absent units taken out; None when nothing
        is left of it."""
        if not isinstance(w, dict):
            return w
        if absent_cond(w):
            return None
        if "after" in w and w["after"] in dropped:
            up = relink(dict(dropped[w["after"]].get("when") or {"t": 0.0}))
            if up is None:
                return None
            if "after" in up:
                up["delay"] = up.get("delay", 0.0) + w.get("delay", 0.0)
            elif "t" in up:
                up["t"] = up["t"] + w.get("delay", 0.0)
            return up
        name = SPELL_NAMES.get(w.get("spells_left"), w.get("spells_left"))
        if (
            "spells_left" in w
            and name not in casters
            and spells.get(SPELL_KEYS.get(name), 0) > w.get("n", 0)
        ):
            # the army carries the spell but no kept step spends it (its
            # caster was dropped): wait for what that caster waited for
            caster = next(
                (
                    x
                    for x in dropped.values()
                    if x["action"] in ("spell", "recall")
                    and ("Recall Spell" if x["action"] == "recall" else x.get("what"))
                    == name
                ),
                None,
            )
            return (
                relink(dict(caster.get("when") or {"t": 0.0}))
                if caster is not None
                else {"t": 0.0}
            )
        for k in ("all", "any"):
            if k in w:
                parts = [p for p in (relink(x) for x in w[k]) if p is not None]
                if not parts:
                    return None
                w = {**w, k: parts}
        return w

    kept, orphans = [], []
    for x in steps:
        if x["id"] in dropped:
            continue
        w = relink(x.get("when"))
        if x.get("when") and w is None:
            orphans.append(x)  # its whole trigger was a unit this army does not bring
        x["when"] = w
        if x.get("until"):
            x["until"] = relink(x["until"])
        kept.append(x)
    mentioned = {x.get("what") for x in kept if x["action"] == "deploy"}
    rest = [n for n, c in inventory.items() if c and n not in mentioned]
    main_deploys = [
        x["id"]
        for x in kept
        if x["action"] == "deploy"
        and x.get("at", "edge:main") == "edge:main"
        and x.get("what") not in heroes.HEROES
    ]
    # the leftovers go with the main push: right after its first deploy
    anchor = {"after": main_deploys[0], "delay": 1.0} if main_deploys else {"t": 15.0}
    for x in orphans:  # nothing is left of its trigger: it goes with the main push
        x["when"] = dict(anchor) if x["id"] != anchor.get("after") else {"t": 15.0}
    for n in rest:
        kept.append(
            {
                "id": f"rest-{n}",
                "action": "deploy",
                "what": n,
                "count": "all",
                "at": "edge:main",
                "when": anchor,
                "uncited": True,
                "cite": [],
            }
        )
    # a hero the playbook never deploys (the army brings a different hero
    # than the playbook's example) goes in with the main push too
    for h in heroes_in:
        if h not in mentioned:
            kept.append(
                {
                    "id": f"rest-{h}",
                    "action": "deploy",
                    "what": h,
                    "count": 1,
                    "at": "edge:main",
                    "group": "main",
                    "when": anchor,
                    "uncited": True,
                    "cite": [],
                }
            )
    # troops the steps name but only partly use (a step for 1 Super Minion
    # when the army has 5): the rest follow that unit's last step, and no
    # troop is still in the camp at 150 s (a player spends the army)
    for n, c in inventory.items():
        mine = [
            x
            for x in kept
            if x["action"] == "deploy" and x.get("what") == n and not x.get("uncited")
        ]
        if (
            not c
            or n in heroes.HEROES
            or not mine
            or any(x.get("count") in (None, "all") for x in mine)
        ):
            continue
        if sum(int(x["count"]) for x in mine) >= c:
            continue
        kept.append(
            {
                "id": f"rest2-{n}",
                "action": "deploy",
                "what": n,
                "count": "all",
                "at": "edge:main",
                "when": {
                    "any": [{"after": mine[-1]["id"], "delay": 4.5}, {"t": 150.0}]
                },
                "uncited": True,
                "cite": [],
            }
        )
    return kept


def _gaps():
    p = Path(__file__).resolve().parents[3] / "data" / "playbook-gaps.json"
    if os.environ.get("BASELAB_GAPS", "1") == "0" or not p.exists():
        return None
    g = json.loads(p.read_text(encoding="utf-8"))
    return g["same_group"]["median"], g["group_change"]["median"]


def add_waits(steps: list) -> None:
    """The playbooks write "after X" with delay 0 when the source names the
    order but not the wait. Real players wait: the median gap between such
    steps in the source videos is 4.5 s within a group and 16.6 s when the
    attack moves to a new group (tools/baselab/step_gaps.py ->
    data/playbook-gaps.json). Those medians replace the unstated zeros,
    less the time the action itself takes (action_time). Explicit non-zero
    delays and the uncited fallbacks keep theirs. Zero-delay chains whose
    citations explicitly say immediate (including the cited Invis/Invis/Fireball
    sequence) keep zero delay; action_time still paces the player's inputs."""
    g = _gaps()
    if g is None:
        return
    same, change = g
    group = {s["id"]: s.get("group", "main") for s in steps}
    act = {s["id"]: s["action"] for s in steps}
    by_id = {s["id"]: s for s in steps}
    # Playbook: fireball-warden, 12Z_sTAEOHw 95/104.4 and 7rzBODLfnug
    # 288.1/292.4 describe Ice Block -> Fireball; Healers complete the walk.
    # Policy: do not add population-median idle time to that exposed walk's
    # preparation chain. Keep its order, explicit waits and paced input costs.
    walk_support = set()
    for step in steps:
        if step["action"] != "deploy" or step.get("what") != "Healer":
            continue
        chain = []
        current = step
        while current["id"] not in chain:
            chain.append(current["id"])
            previous = (current.get("when") or {}).get("after")
            if previous not in by_id:
                break
            current = by_id[previous]
            if current["action"] == "deploy" and current.get("what") == "Grand Warden":
                if current.get("group", "main") == "charge":
                    walk_support.update(chain)
                break

    def immediate(st, previous):
        quotes = " ".join(c.get("quote", "") for c in st.get("cite", [])).lower()
        if any(
            word in quotes
            for word in (
                "immediately",
                "right away",
                "straight away",
                "instantly",
                "quick succession",
            )
        ):
            return True
        # Wiki: Fireball, multiple Invisibilities in quick succession then
        # immediate Fireball. iBpk-396MQs 78.3/82.1 cites "Invis Invis" / "Fireball".
        if previous.get("what") != "Invisibility Spell":
            return False
        if st.get("what") == "Invisibility Spell" and "invis invis" in quotes:
            return True
        before = " ".join(c.get("quote", "") for c in previous.get("cite", [])).lower()
        return (
            st["action"] == "ability"
            and st.get("what") == "Grand Warden"
            and "fireball" in quotes
            and ("invis invis" in before or "quick succession" in before)
        )

    def fix(w, mine, st):
        if not isinstance(w, dict):
            return w
        if "after" in w and not w.get("delay") and w["after"] in group:
            if st["id"] not in walk_support and not immediate(st, by_id[w["after"]]):
                gap = same if group[w["after"]] == mine else change
                w = {**w, "delay": max(0.0, gap - action_time(act[w["after"]], 1))}
        for k in ("all", "any"):
            if k in w:
                w = {**w, k: [fix(x, mine, st) for x in w[k]]}
        return w

    for st in steps:
        if not st.get("uncited") or (
            st["action"] == "deploy" and st.get("what") in heroes.HEROES
        ):
            st["when"] = fix(st.get("when"), st.get("group", "main"), st)


def apply_overrides(steps: list, overrides: dict | None) -> None:
    """Per-base choices a player makes inside the playbook's own steps
    (redteam.py searches them): {step id: {field: value}} with fields
      at     the step's anchor (e.g. which defense a Rocket Balloon snipe or
             an Earthquake targets)
      aim    an ability's target, "building:<key>"; None fires it normally
      every  repeat interval of a repeating spell
      delay  the wait of the step's "after" trigger (top level or inside "all")
    Unknown step ids are ignored (the army may not play that step)."""
    if not overrides:
        return
    for st in steps:
        o = overrides.get(st["id"])
        if not o:
            continue
        for k, v in o.items():
            if k == "delay":
                w = st.get("when")
                if isinstance(w, dict) and "after" in w:
                    st["when"] = {**w, "delay": float(v)}
                elif isinstance(w, dict) and "all" in w:
                    st["when"] = {
                        **w,
                        "all": [
                            (
                                {**x, "delay": float(v)}
                                if isinstance(x, dict) and "after" in x
                                else x
                            )
                            for x in w["all"]
                        ],
                    }
            elif k == "aim" and v is None:
                st.pop("aim", None)
            elif k in ("at", "aim", "every"):
                st[k] = v
            else:
                raise ValueError(f"unknown override field {k}")


def warden_walk(steps, has_healers):
    # output/research/usage/grand-warden-walk.md: Healers require ground mode.
    # https://clashofclans.fandom.com/wiki/Grand_Warden
    by_id = {step["id"]: step for step in steps}

    def follows(trigger, previous, seen=()):
        if not isinstance(trigger, dict):
            return False
        if "t" in trigger:
            start = by_id[previous].get("when") or {}
            return "t" in start and trigger["t"] >= start["t"]
        if "after" in trigger:
            reference = trigger["after"]
            if reference == previous:
                return True
            if reference in seen or reference not in by_id:
                return False
            return follows(by_id[reference].get("when"), previous, (*seen, reference))
        if "all" in trigger:
            return any(follows(part, previous, seen) for part in trigger["all"])
        if "any" in trigger:
            return bool(trigger["any"]) and all(
                follows(part, previous, seen) for part in trigger["any"]
            )
        return False

    return has_healers and any(
        step["action"] == "deploy"
        and step.get("what") == "Healer"
        and step.get("count", "all") != 0
        and (
            step.get("at") in ("unit:Grand Warden", "unit_ahead:Grand Warden")
            or any(
                warden["action"] == "deploy"
                and warden.get("what") == "Grand Warden"
                and warden.get("group", "main") == step.get("group", "main")
                and warden.get("at") == step.get("at")
                and warden.get("at", "").startswith("edge:")
                and follows(step.get("when"), warden["id"])
                for warden in steps
            )
        )
        for step in steps
    )


def from_playbook(
    pb: dict,
    angle: float = 0.0,
    seed: int = 0,
    th: int = 16,
    own_levels: bool = False,
    flank_offset: float = 0.9,
    charge_side: str = "left",
    build: dict | None = None,
    overrides: dict | None = None,
) -> PlaybookPlan:
    """A PlaybookPlan for a playbook dict (data/playbooks/*.json). With
    `build` (a meta or custom army), that army is played through the
    playbook's steps (fit_steps); otherwise the playbook's example army.
    Levels, loadouts, spells and Clan Castle handling come from
    meta_armies.compose so every army path in the sim shares one setup.
    `overrides` sets per-step choices (apply_overrides)."""
    from dataclasses import fields

    from ..meta_armies import compose

    if build is None:
        a = pb["army"]
        build = {
            "archetype": ("user-" if own_levels else "pb-") + pb.get("family", "x"),
            "build": 1,
            "th": th,
            "share": 1.0,
            "three_star": 0.0,
            "troops": dict(a["troops"]),
            "spells": dict(a["spells"]),
            "cc": dict(a.get("cc", {})),
            "heroes": list(a["heroes"]),
            "loadouts": a.get("loadouts", {}),
            "own_levels": own_levels,
        }
    base = compose(build, angle=angle, seed=seed)
    kw = {
        f.name: getattr(base, f.name)
        for f in fields(AttackPlan)
        if not f.name.startswith("_")
    }
    kw["spells"] = dict(base._spells0)
    kw["auto_revive"] = False
    # data/your-levels.json: own-level builds use a complete equipment inventory.
    kw["account_equipment"] = bool(
        build.get("own_levels") or build["archetype"].startswith("user-")
    )
    kw["event_ruleset"] = dict(pb.get("event_ruleset", base.event_ruleset))
    # Wiki: Eagle Artillery, attack exposed key defenses before mass deployment.
    # Red-team compares off/value/aggressive with the same army and playbook.
    opening = (overrides or {}).get("__opening__", {})
    kw["snipe_mode"] = opening.get("snipe_mode", base.snipe_mode)
    plan = PlaybookPlan(**kw)
    plan.snipe_exposed = bool(opening.get("snipe_exposed", plan.snipe_exposed))
    plan.build_id = getattr(base, "build_id", None)
    # data/observed-armies.json: direct and wrapper construction share the
    # same validated replay exceptions; observed alone never bypasses legality.
    plan.observed = getattr(base, "observed", False)
    plan.pol = base.pol
    inv = {n: c for n, c in build["troops"].items() if n != plan.siege}
    if plan.siege:
        inv[plan.siege] = 1
    plan.inventory = inv
    heroes_in = [h for h in build["heroes"] if h in heroes.HEROES]
    sp = dict(plan.spells)  # brewed + Clan Castle
    plan.steps = fit_steps(
        pick_variants(
            pb,
            inv,
            heroes_in,
            sp,
            plan.loadouts,
            selected=(overrides or {}).get("__variants__", {}).get("names"),
            equipment_levels=plan.equipment_levels,
            account_equipment=plan.account_equipment,
        ),
        inv,
        heroes_in,
        sp,
        cc=plan.cc_troops,
    )
    # data/custom-armies.json: explicit roles apply only to unreferenced groups.
    # Playbook group anchors and group conditions retain their original heroes.
    # Wiki: Healer Puppet, send the Queen alongside the main army in smash attacks.
    referenced_groups = set()
    conditions = []
    for st in plan.steps:
        choices = (overrides or {}).get(st["id"], {})
        for key in ("at", "aim"):
            anchor = choices.get(key, st.get(key, ""))
            kind, _, group = str(anchor).partition(":")
            if kind in ("group", "threat", "defenders"):
                referenced_groups.add(group or "main")
        conditions.extend((st.get("when"), st.get("until")))
    while conditions:
        condition = conditions.pop()
        if not isinstance(condition, dict):
            continue
        for key in ("group_inside", "near_th", "defenders_near"):
            if key in condition:
                referenced_groups.add(condition[key])
        conditions.extend(condition.get("all", []))
        conditions.extend(condition.get("any", []))
    for st in plan.steps:
        if st["action"] != "deploy" or st.get("what") not in heroes_in:
            continue
        if st.get("group", "main") in referenced_groups:
            continue
        if st["what"] in build.get("funnel", []):
            st["at"], st["group"] = "edge:funnel", "funnel"
        elif st["what"] in build.get("push", []):
            st["at"], st["group"] = "edge:main", "main"
    add_waits(plan.steps)
    # Invisibility cadence on a charging hero depends on her pet: the merged
    # playbooks' 10-second cycle relies on Spirit Fox covering the gaps; without
    # a Fox players chain one every 4 seconds ("invisibility spells every 4
    # seconds", The Stealth, L_LKqcL56NE at 1:03)
    for st in plan.steps:
        at = str(st.get("at", ""))
        if st.get("what") == "Invisibility Spell" and st.get("every") and ":" in at:
            hero = at.split(":", 1)[1]
            lo = plan.loadouts.get(hero)
            if hero in heroes.HEROES and (lo is None or lo.pet != "Spirit Fox"):
                st["every"] = 4.0
                st.setdefault("cite", []).append(
                    {
                        "video": "L_LKqcL56NE",
                        "t": 63.8,
                        "quote": "invisibility spells every 4 seconds to",
                    }
                )
    apply_overrides(plan.steps, overrides)
    if warden_walk(plan.steps, plan.inventory.get("Healer", 0) > 0):
        plan.ground = True
    plan.flank_offset, plan.charge_side = flank_offset, charge_side
    return plan
