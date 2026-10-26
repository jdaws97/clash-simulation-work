# PB1a engine, fitter and executor fixes

Implemented D1, D2, A1–A4 and A11–A14 from
[`consolidated.md`](../local/reviews/playbooks/consolidated.md). A5–A10 and A15
remain for PB1b. All execution and verification used Rust in WSL, offline,
with `CARGO_TARGET_DIR=/tmp/clash-target-pb` and the repository catalog.
No Python files were edited or executed, and nothing was installed or downloaded.
The concurrent playbook/meta-data and `rust/vidmine` files were not edited.

## Behavior and interfaces

- **D1:** terminal combat deaths retire `Kit::doomed_at`; Revive also clears an
  expired deadline defensively. Spent Phoenix and used equipment stay spent.
- **D2:** an attached Angry Jelly participates on neither side of a separation
  pair. Detachment restores normal separation, including with its owner.
- **A1:** fitting removes statically unavailable equipment actions and rewires
  their dependents through their prerequisites. Explicit temporal delays survive
  relinking, including nested temporal conditions. Availability includes aim
  overrides. `unavailable_steps` reports the omitted action, hero and declared
  equipment; no successful ability event is invented. `required: true` makes
  an unavailable ability a compilation error. Equipment arrays retain their
  existing **any-of** activation meaning.
- **A2:** a spell/Recall step can declare `optional: true`, which makes it an
  opportunity without a minimum stock commitment. Alternatively,
  `spell_budget: "name"` declares a shared stock pool: feasibility reserves the
  largest single opportunity in that pool, plus all independent mandatory
  commitments. Different pools add; mixing spell types in a pool is an error.
  Runtime opportunities preserve stock reserved for unfinished mandatory casts,
  and every cast still checks and consumes real stock. A pressure predicate alone
  does not share a budget. `reviewed_spell_opportunities` supplies narrowly named
  compatibility declarations for the reviewed Druid Freezes, Bowler Poisons and
  charge Rage, and Thrower Totems. Explicit book annotations take precedence.
- **A3:** inherited ordinary troop allocations use execution's clipping/default
  `all` rules during feasibility. Fitting clips retained counts, removes zero
  allocations and rewires their dependents. Newly introduced mandatory packets,
  heroes and siege commitments remain strict. In particular, this cannot accept
  the old 42/38 Balloon package or duplicate Log Launcher commitments.
- **A4:** expansion rewires references to explicitly removed predecessors using
  their original prerequisites. Fitting does the same for unavailable/zero steps.
  Validation then checks unique IDs, unknown predecessors and cycles recursively
  in both `when` and `until`, before fitting and after roles/waits/overrides.
  `require_legal` also enforces the final graph, including for observed replays.
- **A11:** stall recovery follows transitive deployment prerequisites and respects
  scheduled spell preparation. A spell's optional `timeout` is an absolute battle
  time in seconds; the default bound is the existing late-deployment time.
  Terminal skips and impossible pressure-dependent openers permit recovery.
- **A12:** a missing Firemite remains possible while a live Furnace has spawns
  left, a Furnace/Firemite deployment is queued, or Furnace inventory remains.
  The existing target-wait bound remains in force. Exhausted/dead producers with
  no pending supply make absence terminal.
- **A13:** generic breach receives an inventory view with unfinished cited troop
  reservations subtracted. Only its actual consumption is applied to inventory.
  Completed/cancelled actions release reservations; uncited remainder actions do
  not reserve genuine surplus.
- **A14:** explicit `building:ad` aiming uses the inferred citation count, or an
  `aim_count` hint, with the existing aim deadline and bounded fallback.

## Before/after review witnesses

These are synthetic execution/regression probes using the reports' source armies
and existing layouts, not real-game calibration or reproductions of the videos.
The original binary and public playbooks were saved before editing. Source-link
armies were decoded in Rust; one siege was selected as in the reviews. Review
directories' original prepared jobs were not available, so source inventories
were reconstructed from the copied reports, source extractions and local links.
Where the report did not specify all counts, the reconstruction is stated below.

Times are battle seconds. Each row uses the same input before/after. Mechanic rows
use the original prepared plan to separate lifecycle/execution changes from fitter
changes. Fitter rows recompile the same inventory with the saved original book.

| Fix / witness | Base; seed; angle | Before | After |
| --- | --- | --- | --- |
| D1 Lavaloon L | r18d; 2; 0.21 | Duke deadline/death 49.4; Revive/redeath 63.1; 1★/66% | Revive 63.1, survives until 80.6; 1★/72%, 117.5s |
| D1 Meteor representative | r18a; 2; 0 | Duke death 27.6; Revive/redeath 39.7 | Revive 39.7, survives until 46.8; result remains 0★/46%, 180s |
| D1 Root Rider revival | r18a; 0; 0 | Duke death 54.6; Revive/redeath 70.7; 2★/67% | No immediate redeath; post-revive Block executes 74.7; 2★/87%, 150.4s |
| D2 Lavaloon R | r18d; 2; 0.21 | Attached pair drifts about 12.25 tiles during the frozen interval; 1★/53% | Owner and pet stay together at (32.636, 5.361) through samples 24–31; 2★/70%, 180s |
| A1 Dragon live line 38 | r18a; 2; 0 | Missing Backpack/Arrow at 0; Queen 47.3, Dragons 150 | Missing actions absent; Queen 22.5, Dragons 38.4; 0★/41%, 69.4s |
| A1 Electro Dragon observed 5 | r18b; 2; 0.21 | E-Drags 150, Warden 152.1 | E-Drags 24.3; 1★/56%, 64.8s |
| A1 Life Gem reconstruction | rb01; 2; 0 | Missing Fireball; Duke 150, Queen 150.8, Witches 152.4 | Duke 20.6, Queen 36.5, Witches 37.3; 3★/100%, 125.4s |
| A2 Life Gem/Druid/Titan/Super Witch source links | r18a; 2; 0 | All four explicit branches rejected as infeasible at Freeze budgets 1/1/2/1 | All four admitted with the same stock; graph repair also removes inherited dangling references |
| A2 Bowler RC source link | r18a; 2; 0 | Branch unavailable with its optional absent support | Branch admitted without adding Poison or Rage; 0★/37%, 86.2s |
| A2 Thrower full Zap source link | rb01; 2; 0 | Explicit branch infeasible with its one Totem | Admitted with one Totem; 3★/100%, 113.0s |
| A3 Root Rider joint source | r18a; 2; 0 | Explicit joint branch unavailable with one Balloon | Admitted with the same one Balloon and zero remainder; 0★/47%, 126.7s |
| A3 Root Rider TH16 meta 1 | r18a; 2; 0 | Nominal Balloon two blocks King-main repair | King-main repair admitted with the original one Balloon |
| A3 Yeti decoy | r18a; 2; 0 | Log Launcher is uncited remainder at 46.5 | Cited `siege_funnel` at 38.8 with the same single Baby Dragon |
| A4 Quick Fireball | r18a; 2; 0 | `warden_invisibility` waits on removed `ice_block`, skips at 83.0 | Reachable protection executes 5.7; also verified with PB2's corrected Quick Fireball book |
| A11 Electro Dragon Rocket | r18b; 2; 0.21 | Duke forced at 3.1 before spell preparation | Last secondary Quake 23.4 precedes Duke 24.0 |
| A11 Thrower Arrow source link | rb01; 2; 0 | Queen forced 3.1; Arrow skips 11.5 after emergency use | Quakes finish 7.8; Queen 11.7; Arrow executes 15.5 |
| A12 Thrower Firemite Clone reconstruction | rb01; 2; 0 | First-wave gap cancels Clone at 7.0 | Waits through the gap and clones a later wave at 10.5 |
| A13 Thrower V0+V8 source link | r18a; 2; 0 | Generic breach at 30.0 takes the reserved breaker; `hero_wall` skips 35.1 | No surplus breaker is exposed; `hero_wall` executes 35.1 |
| A14 Electro Dragon default | r18b; 2; 0.21 | Queen 6.7, one AD; 2★/65% | Queen 7.1, two ADs; 3★/100%, 146.9s |

The D2 review's diagnostic control reported 2★/85%; the implemented exclusion on
both sides produces the 2★/70% result above. The stationary attachment invariant,
rather than a destruction target, is the regression criterion. D1's three original
prepared-plan lifecycle controls match the reviews' isolated results exactly.
Recompiling the Root Rider revival also repairs inherited graph references and
therefore changes other deployment decisions; its combined fitted result is
2★/77%, 180s, distinct from the 2★/87% lifecycle-only control.

The Life Gem reconstruction assigns unspecified Wall Breakers zero and unspecified
hero equipment through normal defaults, with two Revives donated. Its 150-second
baseline differs from the review snapshot's Duke 145.5/Queen 150 while reproducing
the unavailable-Fireball dependency failure. The Clone reconstruction declares
10 Throwers, five Furnaces, five Healers, two Super Wall Breakers, Log Launcher,
four Clones and one Rage; these unspecified totals are synthetic, and its 7.0-second
failure matches the review. The Lavaloon L probe retains the review's stated TH16
level assumption and omission of unmapped equipment e61. The observed E-Drag input
uses the existing documented replay handling for its recorded capacity mismatch.

The Dragon timing differs from the review's 43.0 counterfactual because this fix
rewires source triggers before inferred pacing is applied. Configured delays are
preserved; population-inferred waits are recomputed for the surviving actions.

Detailed local logs and the Rust replay helper are under
[`local/reviews/playbooks/pb1a`](../local/reviews/playbooks/pb1a/). Private decoded
fixtures remain only in `/tmp/pb1a`, outside Git.

## Verification

- Rust unit tests cover both Phoenix death paths and defensive restoration,
  attachment pair order/detachment, unavailable equipment and required abilities,
  nested relinking and graph errors, optional/shared/mandatory spell stock,
  inherited clipping, strict added packets and duplicate siege rejection,
  transitive preparation/timeouts, renewable/permanent Firemite absence,
  reservation surplus/release, and count-aware aiming with deadline fallback.
- Battle regression: all 868 cases pass after accepting the 134 independently
  explained runtime changes listed in [`GOLDEN.md`](GOLDEN.md).
- The compiled-plan oracle contains 1,196 cases across both playbook modes,
  including the current library at four angles/two seeds, roster substitutions,
  explicit variants, overrides, tactics and illegal inputs. `compile-check`
  defaults to this Rust oracle and runs the existing account fixtures.
- `armysearch-proof`, `guardian-check`, the Rust test suite and `cargo fmt` pass.

Final counts: 45 Rust tests (17 library, eight fidelity, 20 mechanics), 868 battle
goldens, 608 playbook-enabled and 588 generic compiled-plan cases, and 50 guardian
fixtures. Battle expectations also pass with one worker. The plan checker rejects
an altered plan, an empty file and a malformed row in separate negative checks.

## PB1b handoff

| Deferred work | Interfaces to extend |
| --- | --- |
| A5 recipe selection/loadouts | `CompileOptions.overrides.__variants__`, `Compiler::pick_variants`, `feasible`, and `required` equipment actions. Add all-required variant loadouts separately from step equipment arrays' any-of semantics. Preserve the strict list of newly introduced allocation IDs. |
| A6 siege substitution | The siege-only repair filter still uses old step IDs. Add explicit replacement/role mapping there; `relink_removed` supplies only prerequisite repair for actually removed IDs. |
| A7 packet pacing | `add_waits`/`fix_wait` remain the pacing extension points. Preparation tracking preserves prerequisites but does not remove inferred inter-action waits. |
| A8 primary cohort/reserves | `main_started`, `Step.group`, `PlaybookPlan.steps`, `done`/`cancelled`, and `unreserved_inventory`. Add explicit primary deployment/cohort metadata and stable remainder ordering. |
| A9 role preservation | `apply_roles` and existing automatic role repair. General role changes still need explicit dependency normalization for requested as well as automatic variants. |
| A10 Recall lifecycle | `down`, `recoverable`, `charge_closed`, `initial_return`, and redeployment dispatch. Named return ownership and stored-hero charge closure remain unchanged. |
| A15 target semantics | `anchor`, `aim_building`, `aim_since`, AD reservations and `aim_count`. Retain the existing aim deadline while adding binding/value semantics; it must not reset on each target attempt. |
