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

import json
import math
import os
from pathlib import Path
from dataclasses import dataclass, field

from ..mechanics import WORLD
from . import heroes
from .plans import SPELL_NAMES, THREAT, AttackPlan, edge_point

SPELL_KEYS = {v: k for k, v in SPELL_NAMES.items()}


# How fast a player can act. One action at a time: dragging n troops out of a
# slot costs PACE_TAP each plus PACE_SWITCH to pick the slot and the spot; a
# spell, recall or redeploy costs PACE_SWITCH; a hero ability PACE_ABILITY.
# These are assumptions (no source gives human input rates). BASELAB_PACE
# scales them (default 1.0); it is NOT tuned to the real battle times, which
# stay a held-out test (docs/SIM_ACCURACY.md check 6).
PACE_TAP, PACE_SWITCH, PACE_ABILITY = 0.15, 0.6, 0.3


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
    _hurt: dict = field(default_factory=dict)  # unit id -> [(t, hp)]
    _no_target: dict = field(default_factory=dict)  # step id -> time it was first ready with no target
    log_steps: list = field(default_factory=list)

    # the battle asks for initial deployments; everything here is dynamic
    def deployments(self, battle):
        return []

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
        return any(s["id"] not in self._done for s in self.steps if s["action"] in ("deploy", "redeploy"))

    def has_offensive_pending(self, battle):
        if (
            self._have("revive")
            and any(
                not hero.alive and hero.extra.get("revivable")
                for hero in battle.attackers
            )
            and any(
                step["id"] not in self._done
                and step["action"] == "spell"
                and step.get("what") == "Revive Spell"
                for step in self.steps
            )
        ):
            return True
        if any(unit.name != "Healer" for unit in battle.portal_stash):
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
        return edge_point(battle, self._edge_angle(which), 0.0)

    def _unit(self, battle, name):
        for u in battle.attackers:
            if u.alive and u.name == name:
                return u
        return None

    def _group(self, battle, g):
        return [u for u in battle.attackers if u.alive and u.group == g and u.name != "Totem" and u.kind != "pet"]

    def anchor(self, battle, at):
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
            tgt = u.target if u.target is not None and getattr(u.target, "alive", False) else None
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
            return (battle.th.x, battle.th.y) if battle.th is not None and battle.th.alive else None
        if kind == "threat":
            g = self._group(battle, arg) or self._group(battle, "main")
            if not g:
                return None
            cx, cy = self.centroid(g)
            firing = [(THREAT.get(b.key, 1), b) for b, d in self.threats_near(battle, cx, cy, 12)
                      if b.weapon is not None and (b.weapon.target is not None or getattr(b.weapon, "multi", None))]
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
            d = [u for u in battle.defenders if u.alive and u.target is not None and math.hypot(u.x - cx, u.y - cy) <= 8.0]
            return self.centroid(d) if d else None
        if kind == "building":
            g = self._group(battle, "main") or [u for u in battle.attackers if u.alive]
            cx, cy = self.centroid(g) if g else (battle.th.x, battle.th.y) if battle.th is not None else (WORLD / 2, WORLD / 2)
            pool = [b for b in battle.buildings if b.alive and b.key == arg]
            if not pool:
                return None
            b = min(pool, key=lambda b: math.hypot(b.x - cx, b.y - cy))
            return (b.x, b.y)
        raise ValueError(f"unknown anchor {at}")

    # ----------------------------------------------------------- triggers
    def _inside(self, battle, u):
        """Inside the base: at least 2 tiles past the deployable area (every
        tile within 2 is a no-drop tile), not just standing on the red line."""
        blocked = battle._live_no_deploy()
        x, y = int(u.x), int(u.y)
        return all((x + dx, y + dy) in blocked for dx in (-2, 0, 2) for dy in (-2, 0, 2))

    def _heavy_fire(self, battle, u, frac):
        hist = self._hurt.get(u.id, [])
        recent = [h for t, h in hist if battle.t - t <= 2.0]
        lost = (max(recent) - u.hp) if recent else 0.0
        locked = any(b.alive and b.weapon is not None and (b.weapon.target is u or u in (getattr(b.weapon, "multi", None) or []))
                     and THREAT.get(b.key, 0) >= 4 for b in battle.buildings)
        return lost >= frac * u.max_hp or locked

    def _down(self, battle, name):
        """A unit the steps deployed that has fallen: none of that name is
        alive, none waits in the portal stash and no more are in the camp."""
        return (
            name in self._deployed
            and self._unit(battle, name) is None
            and not any(u.name == name for u in battle.portal_stash)
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
        fallen = [u for u in battle.attackers if u.is_hero and not u.alive and u.extra.get("revivable")
                  and (not names or u.name in names)]
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
            engaged = sum(1 for u in g if u.target is not None and getattr(u.target, "alive", False)
                          and not isinstance(u.target, type(u)) and u.cooldown > 0)
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
            return not battle.th.alive or math.hypot(cx - battle.th.x, cy - battle.th.y) <= w.get("r", 8.0)
        if "heavy_fire" in w:
            # any unit of that name under heavy fire (several Throwers, etc.)
            return any(u.alive and u.name == w["heavy_fire"] and self._heavy_fire(battle, u, w.get("frac", 0.15))
                       for u in battle.attackers)
        if "hp_below" in w:
            u = self._unit(battle, w["hp_below"])
            return u is not None and u.hp < w.get("frac", 0.5) * u.max_hp
        if "spells_left" in w:
            return self.spells.get(SPELL_KEYS.get(w["spells_left"], w["spells_left"]), 0) <= w.get("n", 0)
        if "dead" in w:
            # knocked out, not recalled into the portal stash
            return (self._unit(battle, w["dead"]) is None and w["dead"] in self._deployed
                    and not any(u.name == w["dead"] for u in battle.portal_stash))
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
            self._drop(battle, what, pos[0], pos[1], s.get("group", "main"), jitter=0.3)
            self._deployed.add(what)
            return True
        left = self.inventory.get(what, 0)
        n = left if s.get("count") in (None, "all") else min(left, int(s["count"]))
        if n <= 0:
            return False
        at = str(s.get("at", ""))
        if at.startswith("edge:") and n >= 3 and "spread" not in s and what not in LINE_EXEMPT:
            # several troops at an edge are dragged in a line along the
            # deploy border (about a tile apart, at most 8 tiles wide), not
            # stacked on one tile
            ang = self._edge_angle(at.split(":", 1)[1])
            w = min(float(n - 1), 8.0)
            for i in range(n):
                x, y = edge_point(battle, ang, -w / 2 + w * i / (n - 1))
                self._drop(battle, what, x, y, s.get("group", "main"), jitter=0.3)
        else:
            for _ in range(n):
                self._drop(battle, what, pos[0], pos[1], s.get("group", "main"), jitter=s.get("spread", 1.0))
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

    def _ability(self, battle, s):
        u = self._unit(battle, s["what"])
        if u is None or u.kit is None or u.ability_used:
            return False
        if str(s.get("aim", "")).startswith("building:"):
            if self._aim_building(battle, u, s["aim"].split(":", 1)[1]):
                return True
            # not lined up yet: keep trying; after AIM_WAIT s fire it normally
            # rather than hold the ability all battle (an assumption)
            since = self._aim_since.setdefault(s["id"], battle.t)
            if battle.t - since >= AIM_WAIT:
                heroes.activate(battle, u)
                return True
            return False
        if s.get("aim"):
            if self._aim(battle, u, s["aim"]):
                self._fire_aimed(battle, u)
                return True
            return False
        heroes.activate(battle, u)
        return True

    @property
    def _aim_since(self):
        if not hasattr(self, "_aim_t"):
            self._aim_t = {}
        return self._aim_t

    def _aim_building(self, battle, u, key):
        """An ability aimed at a building (e.g. "arrow through the CC"). Giant
        Arrow: fired at the building once it is within the arrow's reach.
        Fireball: it always flies at the closest defense (wiki: Fireball), so
        the Warden fires it once that defense is within the blast radius of
        the building. The step waits until then; if the building is gone it
        fires normally."""
        tgt = min((b for b in battle.buildings if b.alive and b.key == key),
                  key=lambda b: math.hypot(b.x - u.x, b.y - u.y), default=None)
        if tgt is None:
            heroes.activate(battle, u)
            return True
        if u.kit.has("Giant Arrow"):
            # of the buildings of that key in reach, the one whose arrow line
            # (a straight shot through it) crosses the most of them: "line up
            # these two air defenses with the giant arrow" (s5btI1E0LdY 6:04)
            reach = self.P("arrow_reach")
            cands = [b for b in battle.buildings if b.alive and b.key == key
                     and math.hypot(b.x - u.x, b.y - u.y) <= reach]
            if not cands:
                return False

            def crossed(c):
                dx, dy = c.x - u.x, c.y - u.y
                n = math.hypot(dx, dy) or 1.0
                hits = 0
                for o in battle.buildings:
                    if o.alive and o.key == key:
                        along = ((o.x - u.x) * dx + (o.y - u.y) * dy) / n
                        off = abs((o.x - u.x) * dy - (o.y - u.y) * dx) / n
                        hits += along > 0 and off <= o.half_hit + 1.0
                return hits

            tgt = max(cands, key=lambda c: (crossed(c), -math.hypot(c.x - u.x, c.y - u.y)))
            u.extra["aim_at"] = tgt
            self._fire_aimed(battle, u)
            return True
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
            return what + " already deployed" if what in heroes.HEROES and what in self._deployed else None
        if self._impossible(battle, st.get("when")):
            return "waits on a unit that is down"
        if act in ("spell", "recall"):
            k = "recall" if act == "recall" else SPELL_KEYS.get(what)
            if k is not None and self.spells.get(k, 0) <= 0:
                return "no " + SPELL_NAMES[k] + " left"
            if at.startswith("building:") and not any(b.alive and b.key == at[9:] for b in battle.buildings):
                return at[9:] + " gone"
            if at == "th" and (battle.th is None or not battle.th.alive):
                return "Town Hall gone"
        elif act == "ability":
            u = self._unit(battle, what)
            if u is not None and (u.kit is None or u.ability_used):
                return "ability already used"
        elif act == "redeploy":
            if not battle.portal_stash and self.spells.get("recall", 0) <= 0 and battle.t - self._last("recall") > 5.0:
                return "nothing recalled"
        return None

    def on_tick(self, battle):
        if not hasattr(self, "_deployed"):
            self._deployed = set()
        t = battle.t
        if int(t * 10) % 5 == 0:
            for u in battle.attackers:
                if u.alive and (u.is_hero or u.housing >= 5):
                    h = self._hurt.setdefault(u.id, [])
                    h.append((t, u.hp))
                    if len(h) > 8:
                        del h[0]
        alive = any(u.alive and u.name != "Totem" and u.kind not in ("pet", "siege_idle") for u in battle.attackers)
        if alive:
            self._last_alive = t
        stalled = t - getattr(self, "_last_alive", 0.0) > 3.0
        # a step that can no longer happen is skipped so the steps chained
        # after it go ahead, as a player moves on when a charge dies
        for st in self.steps:
            if st["id"] not in self._done:
                why = self._cannot(battle, st)
                if why:
                    self._done[st["id"]] = t
                    self.log_steps.append((round(t, 1), st["id"] + " (skipped: " + why + ")"))
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
            if sid in self._done and not rep:
                continue
            act = s["action"]
            forced = False
            if rep and sid in self._done:
                if t < self._next.get(sid, 0.0) or (s.get("until") and self._ready(battle, s["until"])):
                    continue
            elif not self._ready(battle, s.get("when")):
                # troops still go in when the army is wiped out (stalled), when
                # the trigger waits on a unit that is down, and by LATE
                forced = act == "deploy" and (stalled or t >= LATE or (
                    self._impossible(battle, s.get("when")) and self._ready(battle, s.get("when"), relax=True)))
                if not forced:
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
                    pos = self.anchor(battle, s.get("at", "edge:main"))
                if pos is None and forced:
                    pos = self._edge(battle, "main")  # the anchor is gone: with the main push (as rest steps)
                if pos is None:
                    if act in ("spell", "recall") and s.get("what") != "Revive Spell" and sid not in self._done:
                        # ready but nothing to cast on (no defense firing, the
                        # group gone): after AIM_WAIT the player moves on
                        since = self._no_target.setdefault(sid, t)
                        if t - since >= AIM_WAIT:
                            self._done[sid] = t
                            self.log_steps.append((round(t, 1), sid + " (skipped: no target)"))
                    continue
                if act == "deploy":
                    ok = self._deploy(battle, s, pos)
                elif act in ("spell", "recall"):
                    # a recall step's "what" may name the unit recalled; the
                    # spell is always Recall
                    ok = self._spell(battle, {**s, "what": "Recall Spell" if act == "recall" else s.get("what")}, pos)
                elif act == "redeploy":
                    if battle.portal_stash and t >= battle.portal_ready_at:
                        heroes.portal_redeploy(battle, pos[0], pos[1])
                        ok = True
            if ok:
                n = max(1, before - self.inventory.get(s.get("what"), 0)) if act == "deploy" else 1
                self._busy_until = t + action_time(act, n)
            if ok or s.get("skip_if_impossible"):
                if sid not in self._done:
                    self._done[sid] = t
                    self.log_steps.append((round(t, 1), sid))
                if rep:
                    self._next[sid] = t + rep
        if t >= LATE and t >= getattr(self, "_busy_until", 0.0):
            # troops whose steps were skipped (their anchor unit fell) are
            # still in the camp: they go in with the main push (uncited, as
            # the rest steps of fit_steps)
            pending = {x.get("what") for x in self.steps if x["action"] == "deploy" and x["id"] not in self._done}
            left = next((n for n, c in self.inventory.items() if c > 0 and n not in pending), None)
            if left is not None:
                n = self.inventory[left]
                self._deploy(battle, {"id": "late-" + left, "what": left, "count": "all", "at": "edge:main"},
                             self._edge(battle, "main"))
                self._busy_until = t + action_time("deploy", n)
                self.log_steps.append((round(t, 1), "late-" + left))
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
            # Revive: the playbook decides when it names it; otherwise fallen
            # heroes are revived as the scripted plans do
            self.auto_revive = "revive" not in kinds
        return self._step_spells

    def _have(self, kind):
        if getattr(self, "_fallback", False) and kind in self._step_kinds():
            # the playbook keeps one copy for each of its own steps for this
            # spell that has not fired yet (all of them while it repeats one);
            # copies beyond that go to the fallback
            mine = [st for st in self.steps if (st["action"] == "recall" and kind == "recall")
                    or (st["action"] == "spell" and SPELL_KEYS.get(st.get("what")) == kind)]
            if any(st.get("every") for st in mine):
                return False
            return self.spells.get(kind, 0) > sum(1 for st in mine if st["id"] not in self._done)
        return super()._have(kind)

    def _fallback_spells(self, battle):
        """Spells the playbook never names are used by the general spell
        logic of the scripted plans (Freeze heavy defenses on the push, Rage
        when engaged, Heal under fire, Lightning on an Air Defense, Revive).
        This is NOT from a source: the playbooks only narrate some spells, and
        a real player does not finish an attack with half of them unused."""
        self._step_kinds()
        t = battle.t
        if t < getattr(self, "_next_fallback", 0.0) or t < getattr(self, "_busy_until", 0.0):
            return
        self._next_fallback = t + 0.5
        self.revive_knocked_out(battle)
        if battle.portal_stash and t >= battle.portal_ready_at and not any(
                st["action"] == "redeploy" and st["id"] not in self._done for st in self.steps):
            # units no redeploy step will bring back (a Portal Pendant or a
            # fallback Recall): redeployed where most buildings stand, as the
            # scripted plans do
            x, y = self.portal_point(battle)
            heroes.portal_redeploy(battle, x, y)
            self._busy_until = t + action_time("redeploy")
            return
        main = self.main_units(battle)
        if not main:
            return
        self._fallback = True
        left = sum(self.spells.values()) + sum(self.cc_spells.values())
        try:
            if not self._zap_done and self.zap_ad != (0, 0):
                self._zap(battle)
            self.generic_spells(battle, main)
        finally:
            self._fallback = False
        cast = left - sum(self.spells.values()) - sum(self.cc_spells.values())
        if cast > 0:
            self._busy_until = t + cast * action_time("spell", 1)
        # heroes whose ability the playbook never names use the scripted
        # plans' ability timing (uncited, like the spells above); the
        # playbook's own ability steps keep control of theirs
        mine = {st.get("what") for st in self.steps if st["action"] == "ability" and st["id"] not in self._done}
        held = [u for u in battle.attackers if u.alive and u.is_hero and u.name in mine and not u.ability_used]
        for u in held:
            u.ability_used = True
        try:
            self.hero_abilities(battle)
        finally:
            for u in held:
                u.ability_used = False



def _usable(st, have, heroes_in):
    w = st.get("what")
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


def pick_variants(pb: dict, inventory: dict, heroes_in: list, spells: dict) -> list:
    """The playbook's steps with its cited variants swapped in where the
    army needs them: a variant that replaces steps this army cannot play
    (e.g. a Flame Flinger it does not bring) with steps it can (its Log
    Launcher) takes their place. Best-supported variant first; additive
    variants (replacing nothing) are left out."""
    have = set(inventory) | set(heroes_in) | {SPELL_NAMES[k] for k, c in spells.items() if c}
    steps = [dict(x) for x in pb["steps"]]
    for v in sorted(pb.get("variants", []), key=lambda v: -v.get("support", 0)):
        repl = set(v.get("replaces") or [])
        cur = [x for x in steps if x["id"] in repl]
        if not repl or not cur or any(_usable(x, have, heroes_in) for x in cur):
            continue
        new = [dict(x, variant=v["name"]) for x in v.get("steps", [])]
        if not new or not all(_usable(x, have, heroes_in) for x in new):
            continue
        i = min(n for n, x in enumerate(steps) if x["id"] in repl)
        steps = [x for x in steps if x["id"] not in repl]
        steps[i:i] = new
    return steps


def fit_steps(steps: list, inventory: dict, heroes_in: list, spells: dict, cc=()) -> list:
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
    example army) and is marked "uncited". `cc`: the Clan Castle troops."""
    have = set(inventory) | set(heroes_in) | {SPELL_NAMES[k] for k, c in spells.items() if c}
    bring = set(inventory) | set(heroes_in) | {e if isinstance(e, str) else e.get("name") or e.get("type") for e in cc}
    # units the playbook itself deploys (summons such as Firemites or pets
    # are never "absent")
    army_units = {x.get("what") for x in steps if x["action"] == "deploy"} | set(heroes.HEROES)

    def absent(name):
        return name in army_units and name not in bring

    def absent_cond(w):
        return isinstance(w, dict) and any(k in w and absent(w[k]) for k in UNIT_TRIGGERS + ("dead",))

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
    casters = {("Recall Spell" if x["action"] == "recall" else x.get("what")) for x in steps
               if x["id"] not in dropped and x["action"] in ("spell", "recall")}

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
        if "spells_left" in w and name not in casters and spells.get(SPELL_KEYS.get(name), 0) > w.get("n", 0):
            # the army carries the spell but no kept step spends it (its
            # caster was dropped): wait for what that caster waited for
            caster = next((x for x in dropped.values() if x["action"] in ("spell", "recall")
                           and ("Recall Spell" if x["action"] == "recall" else x.get("what")) == name), None)
            return relink(dict(caster.get("when") or {"t": 0.0})) if caster is not None else {"t": 0.0}
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
    main_deploys = [x["id"] for x in kept if x["action"] == "deploy" and x.get("at", "edge:main") == "edge:main"
                    and x.get("what") not in heroes.HEROES]
    # the leftovers go with the main push: right after its first deploy
    anchor = {"after": main_deploys[0], "delay": 1.0} if main_deploys else {"t": 15.0}
    for x in orphans:  # nothing is left of its trigger: it goes with the main push
        x["when"] = dict(anchor) if x["id"] != anchor.get("after") else {"t": 15.0}
    for n in rest:
        kept.append({"id": f"rest-{n}", "action": "deploy", "what": n, "count": "all", "at": "edge:main",
                     "when": anchor, "uncited": True, "cite": []})
    # a hero the playbook never deploys (the army brings a different hero
    # than the playbook's example) goes in with the main push too
    for h in heroes_in:
        if h not in mentioned:
            kept.append({"id": f"rest-{h}", "action": "deploy", "what": h, "count": 1, "at": "edge:main",
                         "group": "main", "when": anchor, "uncited": True, "cite": []})
    # troops the steps name but only partly use (a step for 1 Super Minion
    # when the army has 5): the rest follow that unit's last step, and no
    # troop is still in the camp at 150 s (a player spends the army)
    for n, c in inventory.items():
        mine = [x for x in kept if x["action"] == "deploy" and x.get("what") == n and not x.get("uncited")]
        if not c or n in heroes.HEROES or not mine or any(x.get("count") in (None, "all") for x in mine):
            continue
        if sum(int(x["count"]) for x in mine) >= c:
            continue
        kept.append({"id": f"rest2-{n}", "action": "deploy", "what": n, "count": "all", "at": "edge:main",
                     "when": {"any": [{"after": mine[-1]["id"], "delay": 4.5}, {"t": 150.0}]},
                     "uncited": True, "cite": []})
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
    delays and the uncited fallbacks keep theirs."""
    g = _gaps()
    if g is None:
        return
    same, change = g
    group = {s["id"]: s.get("group", "main") for s in steps}
    act = {s["id"]: s["action"] for s in steps}

    def fix(w, mine):
        if not isinstance(w, dict):
            return w
        if "after" in w and not w.get("delay") and w["after"] in group:
            gap = same if group[w["after"]] == mine else change
            w = {**w, "delay": max(0.0, gap - action_time(act[w["after"]], 1))}
        for k in ("all", "any"):
            if k in w:
                w = {**w, k: [fix(x, mine) for x in w[k]]}
        return w

    for st in steps:
        if not st.get("uncited"):
            st["when"] = fix(st.get("when"), st.get("group", "main"))


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
                    st["when"] = {**w, "all": [{**x, "delay": float(v)} if isinstance(x, dict) and "after" in x else x
                                               for x in w["all"]]}
            elif k == "aim" and v is None:
                st.pop("aim", None)
            elif k in ("at", "aim", "every"):
                st[k] = v
            else:
                raise ValueError(f"unknown override field {k}")


def from_playbook(pb: dict, angle: float = 0.0, seed: int = 0, th: int = 16, own_levels: bool = False,
                  flank_offset: float = 0.9, charge_side: str = "left", build: dict | None = None,
                  overrides: dict | None = None) -> PlaybookPlan:
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
        build = {"archetype": ("user-" if own_levels else "pb-") + pb.get("family", "x"), "build": 1, "th": th, "share": 1.0,
                 "three_star": 0.0, "troops": dict(a["troops"]), "spells": dict(a["spells"]), "cc": dict(a.get("cc", {})),
                 "heroes": list(a["heroes"]), "loadouts": a.get("loadouts", {}), "own_levels": own_levels}
    base = compose(build, angle=angle, seed=seed)
    kw = {f.name: getattr(base, f.name) for f in fields(AttackPlan) if not f.name.startswith("_")}
    kw["spells"] = dict(base._spells0)
    kw["auto_revive"] = False
    kw["event_ruleset"] = dict(pb.get("event_ruleset", base.event_ruleset))
    plan = PlaybookPlan(**kw)
    plan.build_id = getattr(base, "build_id", None)
    plan.pol = base.pol
    inv = {n: c for n, c in build["troops"].items() if n != plan.siege}
    if plan.siege:
        inv[plan.siege] = 1
    plan.inventory = inv
    heroes_in = [h for h in build["heroes"] if h in heroes.HEROES]
    sp = dict(plan.spells)  # brewed + Clan Castle
    plan.steps = fit_steps(pick_variants(pb, inv, heroes_in, sp), inv, heroes_in, sp, cc=plan.cc_troops)
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
                st.setdefault("cite", []).append({"video": "L_LKqcL56NE", "t": 63.8, "quote": "invisibility spells every 4 seconds to"})
    apply_overrides(plan.steps, overrides)
    plan.flank_offset, plan.charge_side = flank_offset, charge_side
    return plan
