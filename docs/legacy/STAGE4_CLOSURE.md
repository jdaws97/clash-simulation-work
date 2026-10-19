# Bounded stage4 closure checklist

Base: frozen stage3 commit `7f150ed9afff1b8629f5fee751744d7a8681c45a`.
This worktree is separate; frozen review directories remain unchanged.

Each family needs compiler ownership, shared runtime behavior, finite resource
receipts, termination, two-step paid battle evidence, and independent recheck.
Component success alone does not close a row. No publication is planned while
the independent rechecks or material correctness issues remain open.

| Family | Required paid battle / shared contract | Current closure |
| --- | --- | --- |
| Bat | finite air releases, actual attacks, resource/Hall multiplier, trap and Castle trigger exclusions, continuation after paid cast | Implemented; paid two-step regressions; independent review pending |
| Skeleton | finite ground releases, actual attacks, per-hit armor with immunity/overflow, trap exclusions | Implemented; paid two-step regressions plus shared immunity control; independent review pending |
| Clone | freshly compiled source/reserves, finite housing, no paid duplication, source death/Recall, silent absolute expiry | Ordinary troop and Bat/Skeleton clones bound; source loss, Recall expiry, simultaneous production and finite-budget checks; review pending |
| Revive | same defeated hero, positive HP, spent ability retained, unfinished attack work, Phoenix entitlement, delayed continuation | Core hero loadouts bound; paid death/continuation/Ice/charge/pulse checks; secondary models reject; review pending |
| Ice Block | actual movement/attack pause, Freeze union, remaining work, incoming reduction, independent expiry | Ordinary troop path implemented; paid death-Freeze overlap at two steps; secondary lifecycles reject; independent review pending |
| Angry | real acquisition and movement, original priority restoration, Recall absolute expiry, field crossings | Ordinary/core-hero targeting bound; paid Recall return before/after expiry at two steps; review pending |
| Jump | real wall traversal with buildings still blocking, duration/boostTime, legal exit at expiry and replanning | Ordinary controls independently passed; Tornado expiry finding corrected with shared legal exit; two-step paid recheck pending |

The audit fixes at `59664f99b0ff1d902e990ae7bca97f34417d349e` and Flinger changes
at `da093e6eeacc677d056bbfce85642e92bbed8cf8` are present. Original reviewers have
cleared Earthquake sparse health, raw Inferno scope, Shield/Hall ordering and the
bounded Flinger shared path. Existing regressions remain required. These clears
do not cover other siege families or game calibration.

Three-spell policy limits: Bat Town Hall damage is a caller-supplied hypothesis
because the pinned source omits it. Skeleton armor unlock/overflow, spawn timing
and offsets are explicit hypotheses. Ground summons require clear declared
positions; no automatic relocation is invented. Garrison, Tornado and Giga Bomb
scenes retain their explicit per-actor response requirements, including reserves.
Forged effects, unowned reserves and user deployment of spell reserves reject.

Performance: preserve original exact recipe inputs and policies. TH16 Root Rider
still has no outcome; bound the next diagnosis and compare unchanged-prefix
semantics before an exact rerun. Do not rerun successful recipes without cause.
The [Healer contact checkpoint](HEALER_PURSUIT_CHECKPOINT.md) removes a measured
arrival cascade without widening steps/timeouts; it does not clear full-recipe
throughput. [Super Valkyrie death Rage](DEATH_RAGE_CHECKPOINT.md) is now bound with
paid death/Recall/expiry/continuation checks and independent review pending.
Selected current TH18 crafted defenses remain an explicit completion gap; the
uncrafted fixture must not be treated as representative crafted coverage.

Experimental original armies/layouts may be delivered after separate legality
and usability review; incomplete engine coverage does not block that trial
package. Performance rankings still require useful coverage, predeclared budgets,
distinct timeout/outcome handling, provenance, held-out matchups and resolution
checks. Creator presets are comparison baselines, and no simulation superiority
or game calibration is established here.
