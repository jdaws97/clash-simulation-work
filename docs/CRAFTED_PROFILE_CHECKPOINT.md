# Crafted role modifiers in paid battles

Base: 04a4ce002054a280b552964faca4813d64cce489. The attack-search stream found
that the generic Station actor's intentionally zero fallback damage received the
selected profile, while the actual crafted weapon model retained neutral damage.
Thus Cake-A-Pult previously hit for195 under both `none` and `legend_i`.

The profile transform now scales the actual primary and released Cake explosion
quantities once as defense weapon damage. Hero Hunter retains its separate2x hero
coefficient. Its poison DPS is a derived runtime quantity, scaled according to
the caller's existing explicit `impact_hazard_damage_policy`; `unchanged` remains
available. Source poison rows, module rows, selected levels, attack intervals,
projectile delays, radius, status magnitude/duration and Candle melt/capacity
statistics stay intact. Station HP receives only the defense HP profile, which
is1.0 for the published Legend I profile. Attacking heroes retain their separate
0.8 HP/damage role.

The transform validates the original crafted ownership contract first, then
synchronizes its model and actor projections after the recorded profile changes.
Raw entry still rejects changed weapon values or mismatched projections, and
applying the same scene profile twice remains an error. The application ledger
records primary/explosion/poison paths and exposes the capability
`crafted-role-profile-model-scaling-v1` when a selected Station was transformed.
Search integration may use the reviewed capability receipt to distinguish this
engine from the older defective baseline; it must not assume support from names.

Three bounded paid controls compare all three selected variants under neutral
and Legend I profiles; prove Cake195->234 and released bomb400->480 at unchanged
clocks; check Hunter hero targeting and both declared poison policies; preserve
source rows, Station HP and resource receipts; and reject pre/post-transform
owner tampering and double application. These are synthetic lifecycle and scaling
checks, not an optimal army or complete village performance claim.

The numeric role profile is the [official 27 April2026 table](https://supercell.com/en/games/clashofclans/blog/release-notes/the-sound-of-clash-update/),
verified2026-10-04. Secondary hazard scaling remains the caller's explicit
hypothesis. Crafted geometry/season selection retains its existing experimental
contract and pinned unverified catalog. October rotation and current client
session are not observed. Independent review is pending; complete held-out game
calibration remains zero.
