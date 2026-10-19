"""Turn an attack plan into a readable army card and step-by-step guide.

The steps describe exactly what the simulated attacker does (plans.py), so
the guide and the simulated results match.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from baselab.engine import stats  # noqa: E402
from baselab.engine.plans import SPELL_NAMES, AttackPlan  # noqa: E402


def e(s):
    return html.escape(str(s))


def _housing(name):
    return int(stats.attrs(name).get("housing_ck") or stats.attrs(name).get("housing") or 0)


def _spell_space(key):
    return int(stats.attrs(SPELL_NAMES[key]).get("housing") or 1)


def _camp_rows(plan: AttackPlan):
    """(name, count, role) for every army-camp troop in deploy order."""
    rows = []
    for n, c, _lat in plan.flank:
        rows.append((n, c, "Funnel (first 10 s)"))
    for w in plan.main:
        for n, c in w.units:
            rows.append((n, c, "Main push"))
    for w in plan.support:
        for n, c in w.units:
            rows.append((n, c, "Behind the push (+2 s)"))
    for n, c in plan.breakers:
        rows.append((n, c, "Walls (when the push stalls on one)"))
    for n, c in plan.cleanup:
        rows.append((n, c, "Cleanup (+25 s, far side)"))
    merged = {}
    order = []
    for n, c, role in rows:
        if (n, role) not in merged:
            order.append((n, role))
            merged[(n, role)] = 0
        merged[(n, role)] += c
    return [(n, merged[(n, role)], role) for n, role in order]


def card(plan: AttackPlan, levels: dict) -> str:
    h = plan.housing()
    lv = levels or {}

    def lvl(n):
        v = lv.get(n)
        return f"L{v}" if v else ""

    camp = "".join(
        f"<tr><td>{e(n)}</td><td class=\"num\">{c}</td><td class=\"num\">{_housing(n)}</td><td class=\"num\">{c * _housing(n)}</td><td>{e(lvl(n))}</td><td>{e(role)}</td></tr>"
        for n, c, role in _camp_rows(plan)
    )
    cc_counts = {}
    for n in plan.cc_troops:
        cc_counts[n] = cc_counts.get(n, 0) + 1
    cc = "".join(f"<tr><td>{e(n)}</td><td class=\"num\">{c}</td><td class=\"num\">{_housing(n)}</td><td class=\"num\">{c * _housing(n)}</td></tr>" for n, c in cc_counts.items())
    spells = dict(plan._spells0)
    if plan._revives0:
        spells["revive"] = plan._revives0
    sp_rows = "".join(f"<tr><td>{e(SPELL_NAMES[k])}</td><td class=\"num\">{c}</td><td class=\"num\">{_spell_space(k) * c}</td><td>{e(lvl(SPELL_NAMES[k]))}</td></tr>" for k, c in spells.items())
    cc_sp = "".join(f"<tr><td>{e(SPELL_NAMES[k])}</td><td class=\"num\">{c}</td><td class=\"num\">{_spell_space(k) * c}</td></tr>" for k, c in plan._cc_spells0.items())
    heroes = "".join(
        f"<tr><td>{e(hn)} {e(lvl(hn))}</td><td>{e(' + '.join(f'{x} {lvl(x)}'.strip() for x in lo.equipment))}</td><td>{e((lo.pet or '') + (' ' + lvl(lo.pet) if lo.pet else ''))}</td></tr>"
        for hn, lo in plan.loadouts.items()
    )
    return f"""
<div class="army">
  <div class="army-block"><h4>Army camps · {h['camp']}/{h['camp_cap']}</h4>
    <div class="scroll"><table class="mini"><thead><tr><th>Troop</th><th>Count</th><th>Space each</th><th>Space</th><th>Your level</th><th>Job</th></tr></thead><tbody>{camp}</tbody></table></div></div>
  <div class="army-block"><h4>Clan Castle · {h['cc']}/{h['cc_cap']} troops + siege</h4>
    <p class="note">Siege machine: <b>{e(plan.siege or 'none')}</b>. The Clan Castle troops ride inside it and come out where it breaks.</p>
    <div class="scroll"><table class="mini"><thead><tr><th>Request</th><th>Count</th><th>Space each</th><th>Space</th></tr></thead><tbody>{cc}</tbody></table></div>
    <h4>Clan Castle spells · {h['cc_spells']}/{h['cc_spell_cap']}</h4>
    <div class="scroll"><table class="mini"><thead><tr><th>Spell</th><th>Count</th><th>Space</th></tr></thead><tbody>{cc_sp}</tbody></table></div></div>
  <div class="army-block"><h4>Your spells · {h['spells']}/{h['spell_cap']}</h4>
    <div class="scroll"><table class="mini"><thead><tr><th>Spell</th><th>Count</th><th>Space</th><th>Your level</th></tr></thead><tbody>{sp_rows}</tbody></table></div></div>
  <div class="army-block"><h4>Heroes</h4>
    <div class="scroll"><table class="mini"><thead><tr><th>Hero</th><th>Equipment</th><th>Pet</th></tr></thead><tbody>{heroes}</tbody></table></div></div>
</div>
{steps(plan)}"""


def steps(plan: AttackPlan) -> str:
    fun = [n for n, _lat in plan.funnel_heroes]
    flank = ", ".join(f"{c} {n}" for n, c, _ in plan.flank)
    main = ", ".join(f"{c} {n}" for w in plan.main for n, c in w.units)
    support = ", ".join(f"{c} {n}" for w in plan.support for n, c in w.units)
    spells = set(plan._spells0) | set(plan._cc_spells0)
    out = []
    out.append("<b>Pick your side.</b> Choose the side where the outer buildings are thinnest in front of the core. If the base has an open gap of 3×3 tiles or more inside its walls near the core, drop the whole push into that gap; the simulated attacker always does.")
    if fun:
        out.append(f"<b>0:00, funnel.</b> Drop the {e(fun[0])} about 6 tiles to the left of your entry point" + (f" and the {e(fun[1])} about 6 tiles to the right" if len(fun) > 1 else "") + (f", then {e(flank)} at the entry" if flank else "") + ". They clear the edge buildings that would otherwise pull your push sideways.")
    out.append(f"<b>Launch the push</b> once three edge buildings near your entry are down, at the latest {plan.main_max:.0f} s in" + (f" (no earlier than {plan.main_min:.0f} s)" if plan.main_min else "") + ". Deploy " + (f"the {e(plan.siege)} first, then " if plan.siege else "") + f"{e(main)} at the entry point in a tight group, about {plan.main[0].spread:.0f} tiles wide." + (f" Then the {e(' and '.join(plan.push_heroes))} right behind them." if plan.push_heroes else ""))
    if support:
        out.append(f"<b>+2 s:</b> {e(support)} right behind the push, so they follow and heal it.")
    if plan.siege and plan.cc_troops:
        out.append(f"<b>When the {e(plan.siege)} breaks,</b> your Clan Castle troops ({e(', '.join(plan.cc_troops))}) come out on that spot and join the push.")
    if plan.breakers:
        out.append(f"<b>Walls:</b> when two or more troops are stuck on the same wall, drop {e(', '.join(f'{c} {n}' for n, c in plan.breakers))} right next to them.")
    rules = []
    if "totem" in spells:
        rules.append("<b>Totem</b>: when three or more defenses are shooting the push, place it halfway between the push and those defenses. Wait about 5 s between Totems.")
    if "freeze" in spells:
        rules.append("<b>Freeze</b>: on an Inferno Tower, Scattershot, Eagle, X-Bow, Monolith or Town Hall that is shooting the push from within its range.")
    if "invis" in spells:
        rules.append("<b>Invisibility</b>: over the push whenever two or more heavy defenses are firing on it, or its health falls below about 60%. Chain them about 4.5 s apart.")
    if "poison" in spells:
        rules.append("<b>Poison</b>: on defending Clan Castle troops or heroes once three or more are near the push.")
    if "rage" in spells:
        rules.append("<b>Rage</b>: when at least half the push is fighting at once.")
    if "overgrowth" in spells:
        rules.append("<b>Overgrowth</b>: on the defense with the most dangerous defenses around it, ahead of the push.")
    if "clone" in spells:
        rules.append("<b>Clone</b>: over the big troops about a second after they're deployed.")
    if "haste" in spells:
        rules.append("<b>Haste</b>: over the push about 3 s after deploying, then every 8 s.")
    if "recall" in spells:
        rules.append("<b>Recall</b>: when the push stands in an empty area or is dying, recall it and redeploy where the most buildings remain.")
    if "eq" in spells:
        rules.append("<b>Earthquake</b>: save it to open walls, or use it with Lightning on an Air Defense.")
    if plan._revives0 or plan._cc_spells0.get("revive"):
        rules.append("<b>Revive</b>: on a hero that falls, right away.")
    out.append("<b>Spells, as the attack plays out:</b><ul>" + "".join(f"<li>{r}</li>" for r in rules) + "</ul>")
    hero_rules = []
    for hn, lo in plan.loadouts.items():
        if hn == "Grand Warden":
            hero_rules.append(f"<b>Grand Warden</b> ({e(' + '.join(lo.equipment))}): fire the ability when at least 5 troops are around him and a third of them are below about 55% health.")
        elif hn == "Dragon Duke":
            hero_rules.append(f"<b>Dragon Duke</b> ({e(' + '.join(lo.equipment))}): fire as soon as he targets a defense, or when he drops below 60% health.")
        elif hn == "Minion Prince" and "Portal Pendant" in lo.equipment:
            hero_rules.append("<b>Minion Prince</b> (Portal Pendant): when 6 or more troops near him have nothing left to hit or are below 45% health, pull them and redeploy them where the most buildings remain.")
        else:
            hero_rules.append(f"<b>{e(hn)}</b> ({e(' + '.join(lo.equipment))}): fire below 50% health, or 25 s after the hero starts fighting.")
    out.append("<b>Hero abilities:</b><ul>" + "".join(f"<li>{r}</li>" for r in hero_rules) + "</ul>")
    if plan.cleanup:
        out.append(f"<b>+25 s after the push, cleanup:</b> send {e(', '.join(f'{c} {n}' for n, c in plan.cleanup))} one at a time to the far-side buildings, each to a different one. Use the closest legal spot, including spots that open up as buildings fall.")
    return "<ol class=\"steps\">" + "".join(f"<li>{s}</li>" for s in out) + "</ol>"
