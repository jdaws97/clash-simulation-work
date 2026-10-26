> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Conditional recipe equipment

Action Figure, Giant Arrow, Fireball and Earthquake Boots now have explicit
compiler and runtime contracts in the v27-or-later hero scope. They consume the
existing hero's **one shared manual ability charge**, executing all selected
active equipment at that activation. There is no independent Fireball/Tome
charge and no automatic hero activation. These handlers enable conditional
comparisons, not a claim of game calibration.

## Evidence and unresolved identity

Equipment statistics remain the rows in `data/catalog.json`, pinned to
[chiefpansancolt c6967314](https://github.com/chiefpansancolt/clash-of-clans-data/tree/c6967314d7281bb87c362993e2635e58cd77b351/data/home/hero-equipment).
This includes equipment additions, Action Figure's invisibility duration,
summon level and Queen regeneration; Arrow's damage/radius; Fireball's
damage/radius; and Boots' ground radius/building and troop damage percentages.
No source statistic rows were edited.

**Action Figure summon statistics are not resolved by that catalog.** The
separate [ClashKing b8f42a70 extraction](https://raw.githubusercontent.com/ClashKingInc/ClashKingAssets/b8f42a707fe92d5293d46088bf536450ae422e7b/assets/static_data.json)
contains seasonal Giant Giant ID 4000156, TID `CHARACTER_APRIL25GTG`, while Action
Figure exposes a troop level without an entity ID. The matching name does not
prove that the seasonal and equipment summons share statistics. The example
policy uses seasonal level 10 (18,500 HP, 700 DPS, 2-second attacks) only with the
mandatory status `explicit_uncalibrated_hypothesis` and identity label
`caller_declared_equipment_summon_not_verified_seasonal_identity`. Its raw speed
and range conversions, splash radius and rage multipliers are also conditional.
Do not call a run using this mapping a verified Action Figure recommendation.

The sample policy is specifically for level 27 equipment, whose pinned summon
level is 10. Other equipment levels require matching explicitly supplied summon
statistics; a mismatched level fails compilation. Missing fields or unsupported
policies also fail explicitly. A verified equipment-summon identity plus its HP,
damage, speed, range, splash and rage values would close the remaining stat gap.

## Conditional contracts

`data/battle-policies/recipe-equipment.json` supplies example `parameters` for
each item. Every behavioral field receives explicit hypothesis provenance in
the compiled model. Callers must include the selected item level and these
parameters in `hero_parameters.equipment`; there is no implicit default.

| Item | Conditional behavior |
| --- | --- |
| Action Figure | One controlled Giant Giant reserve at the Queen's declared offset. Queen invisibility and self-heal use pinned equipment values. Self-heal starts from actual deployment, continues during Freeze, and stops while inactive. The summon survives Queen death and has no timed expiry. It targets ground defenses then buildings, clears walls, and uses source-centered splash with one shared wall/primary clock. Rage latches once after a nonlethal health batch at or below half maximum HP; healing never toggles it off. Damage/movement/attack-rate multipliers are explicit hypotheses. |
| Giant Arrow | Facing uses the current live target center, or a required fallback unit vector. A moving disk contacts live enemy footprints once each, including walls and either unit layer. Release delay, speed and total travel distance are explicit. Scheduler contact events account for target movement instead of polling at the maximum solver step. |
| Fireball | Chooses nearest visible defense footprint, ties within existing epsilon by ID. Hidden Tesla and invisible defenses cannot be acquired. No eligible defense consumes the shared activation with an explicit no-target event. Travel captures target center and damage at activation; impact samples live nearby actors even if the original target or Warden dies. |
| Earthquake Boots | One activation-centered ground pulse. Buildings and units take their declared fractions of maximum HP; walls receive maximum-HP damage. The policy permits lethal damage and does not scale percentages with hero damage. Invulnerability and incoming damage factors still use shared receipts. |

Arrow and Fireball effects are captured **at activation**, survive their declared
release delay and source death, and do not scale with later Rage spells. Their
area collateral ignores Invisibility but excludes hidden Tesla and respects the
scene's defending-unit collateral policy. This is a complete declared geometry
and timing model; it is not inferred from the equipment tooltip.

The example delays (0.1 s), Arrow speed (12 tiles/s), Fireball speed (8 tiles/s),
Arrow travel (80 tiles), Giant splash (1.5 tiles) and rage factors (1.5) are
engineering hypotheses. Vary them in sensitivity comparisons. Equipment levels,
statistics and timing require independent calibration before predictive use.

## Runtime integration and accounting

`compile_recipe_equipment(instance, hero, catalog)` returns `(model, row)`.
`compile_mirror_clones(actor)` retains its existing entrypoint but additionally
returns the Action Figure reserve through `compile_action_figure_summons`.
The reserve has `summon_model.equipment = "action-figure"` and its Queen parent,
with no independent catalog/army identity. It is never purchased from army
housing. Its declared housing weight is for Spring Trap behavior only.

Action Figure is a troop for buffs, healing, hazards and Spring Traps. Explicit
generated-summon battle-modifier policy determines profile inheritance. Mirror
and Action Figure summons are matched separately during activation, so each is
deployed once and only Mirror receives clone expiry. All released damage uses
shared damage receipts. Queued projectiles and arrows appear in termination
continuation facts; they cannot be silently discarded when their hero dies.

`HeroRosterCombat.wall_impacts` dispatches Giant Giant splash and existing King
splash through the same wall hit. The spatial kernel must use that dispatcher.
Hero health settlement invokes the summon rage latch, preserving residual
attack work under Freeze and rate changes.

## Validation

Four focused tests cover Arrow's full solver contacts at maximum steps 0.017 and
0.8 seconds, once-only shared activation and post-death travel; Fireball/Tome
shared charge and dead-primary impact; Action Figure generation, separation from
Mirror, classes, regeneration, persistent/latching rage and level rejection;
and Boots' wall, air, maximum-HP and immunity distinctions. They use synthetic
fixtures. Resource-ledger and full-village comparisons are integration checks,
not implied by these lifecycle checks.
