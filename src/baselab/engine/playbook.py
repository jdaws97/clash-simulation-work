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

import math
from dataclasses import dataclass, field

from . import heroes
from .plans import SPELL_NAMES, THREAT, AttackPlan, edge_point

SPELL_KEYS = {v: k for k, v in SPELL_NAMES.items()}


@dataclass
class PlaybookPlan(AttackPlan):
    steps: list = field(default_factory=list)
    inventory: dict = field(default_factory=dict)  # troop/siege name -> count left
    flank_offset: float = 0.9  # radians between the main side and each flank (knob)
    charge_side: str = "left"  # which flank the charge opens (knob)
    _done: dict = field(default_factory=dict)  # step id -> time it fired
    _next: dict = field(default_factory=dict)  # repeating step id -> next time
    _hurt: dict = field(default_factory=dict)  # unit id -> [(t, hp)]
    log_steps: list = field(default_factory=list)

    # the battle asks for initial deployments; everything here is dynamic
    def deployments(self, battle):
        return []

    def has_pending(self):
        """Pending while a deploy or redeploy step has not fired. The battle
        otherwise ends when every attacker is down (see on_tick: an army
        with nothing alive deploys its remaining steps, as players do)."""
        return any(s["id"] not in self._done for s in self.steps if s["action"] in ("deploy", "redeploy"))

    def has_offensive_pending(self, battle):
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
    def _edge(self, battle, which):
        off = {"main": 0.0, "left": -self.flank_offset, "right": self.flank_offset}
        if which == "charge":
            which = self.charge_side
        elif which == "funnel":
            which = "right" if self.charge_side == "left" else "left"
        return edge_point(battle, self.angle + off.get(which, 0.0), 0.0)

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
            g = self._group(battle, "main") or battle.attackers
            cx, cy = self.centroid(g) if g else (battle.th.x, battle.th.y)
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

    def _ready(self, battle, w):
        if not w:
            return True
        t = battle.t
        if "all" in w:
            return all(self._ready(battle, x) for x in w["all"])
        if "any" in w:
            return any(self._ready(battle, x) for x in w["any"])
        if "t" in w:
            return t >= w["t"]
        if "after" in w:
            ft = self._done.get(w["after"])
            return ft is not None and t >= ft + w.get("delay", 0.0)
        if "inside" in w:
            u = self._unit(battle, w["inside"])
            return u is not None and self._inside(battle, u)
        if "group_inside" in w:
            g = self._group(battle, w["group_inside"])
            return bool(g) and sum(self._inside(battle, u) for u in g) >= max(1, len(g) // 2)
        if "near_th" in w:
            g = self._group(battle, w["near_th"])
            if not g or battle.th is None:
                return False
            cx, cy = self.centroid(g)
            return not battle.th.alive or math.hypot(cx - battle.th.x, cy - battle.th.y) <= w.get("r", 8.0)
        if "heavy_fire" in w:
            u = self._unit(battle, w["heavy_fire"])
            return u is not None and self._heavy_fire(battle, u, w.get("frac", 0.15))
        if "hp_below" in w:
            u = self._unit(battle, w["hp_below"])
            return u is not None and u.hp < w.get("frac", 0.5) * u.max_hp
        if "spells_left" in w:
            return self.spells.get(SPELL_KEYS.get(w["spells_left"], w["spells_left"]), 0) <= w.get("n", 0)
        if "dead" in w:
            return self._unit(battle, w["dead"]) is None and w["dead"] in self._deployed
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
        for _ in range(n):
            self._drop(battle, what, pos[0], pos[1], s.get("group", "main"), jitter=s.get("spread", 1.0))
        self.inventory[what] = left - n
        self._deployed.add(what)
        return True

    def _spell(self, battle, s, pos):
        k = SPELL_KEYS.get(s["what"])
        if k is None or not self._have(k):
            return False
        self._use(battle, k, pos[0], pos[1])
        return True

    def _ability(self, battle, s):
        u = self._unit(battle, s["what"])
        if u is None or u.kit is None or u.ability_used:
            return False
        if s.get("aim"):
            if self._aim(battle, u, s["aim"]):
                self._fire_aimed(battle, u)
                return True
            return False
        heroes.activate(battle, u)
        return True

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
        for s in self.steps:
            sid = s["id"]
            rep = s.get("every")
            if sid in self._done and not rep:
                continue
            if rep and sid in self._done:
                if t < self._next.get(sid, 0.0) or (s.get("until") and self._ready(battle, s["until"])):
                    continue
            elif not self._ready(battle, s.get("when")) and not (stalled and s["action"] == "deploy"):
                continue
            ok = False
            act = s["action"]
            if act == "release_siege":
                ok = battle.release_siege(s.get("what"))
            elif act == "ability":
                ok = self._ability(battle, s)
            else:
                pos = self.anchor(battle, s.get("at", "edge:main"))
                if pos is None:
                    continue
                if act == "deploy":
                    ok = self._deploy(battle, s, pos)
                elif act in ("spell", "recall"):
                    ok = self._spell(battle, {**s, "what": s.get("what") or "Recall Spell"}, pos)
                elif act == "redeploy":
                    if battle.portal_stash and t >= battle.portal_ready_at:
                        heroes.portal_redeploy(battle, pos[0], pos[1])
                        ok = True
            if ok or s.get("skip_if_impossible"):
                if sid not in self._done:
                    self._done[sid] = t
                    self.log_steps.append((round(t, 1), sid))
                if rep:
                    self._next[sid] = t + rep


def from_playbook(pb: dict, angle: float = 0.0, seed: int = 0, th: int = 16, own_levels: bool = False,
                  flank_offset: float = 0.9, charge_side: str = "left") -> PlaybookPlan:
    """A PlaybookPlan for a playbook dict (data/playbooks/*.json): the army
    from pb["army"], the steps from pb["steps"]; levels, loadouts, spells and
    Clan Castle handling come from meta_armies.compose so every army path in
    the sim shares one setup."""
    from dataclasses import fields

    from ..meta_armies import compose

    a = pb["army"]
    build = {"archetype": ("user-" if own_levels else "pb-") + pb.get("family", "x"), "build": 1, "th": th, "share": 1.0,
             "three_star": 0.0, "troops": dict(a["troops"]), "spells": dict(a["spells"]), "cc": dict(a.get("cc", {})),
             "heroes": list(a["heroes"]), "loadouts": a.get("loadouts", {}), "own_levels": own_levels}
    base = compose(build, angle=angle, seed=seed)
    kw = {f.name: getattr(base, f.name) for f in fields(AttackPlan) if not f.name.startswith("_")}
    plan = PlaybookPlan(**kw)
    plan.build_id = getattr(base, "build_id", None)
    plan.pol = base.pol
    plan.steps = [dict(s) for s in pb["steps"]]
    inv = dict(a["troops"])
    if plan.siege:
        inv[plan.siege] = 1
    plan.inventory = inv
    plan.flank_offset, plan.charge_side = flank_offset, charge_side
    return plan
