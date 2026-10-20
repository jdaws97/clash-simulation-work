# Roadmap: from simulator to "this is the best base / army, go test it"

User goal (2026-10-20): everything in the game accounted for; the best base
and army design whatever it looks like; an easy way to update after patches.
The user tests whatever the simulation calls best.

## What "best" means
- Base: highest expected ranked defense trophies (war: lowest 3-star rate)
  against the armies TH17-18 attackers really bring, weighted by usage,
  each army playing the best cited attack for that base (red team,
  docs/REDTEAM.md), and still on top when each modelling assumption is
  pushed up and down (sensitivity).
- Army: highest expected trophies with armies the user can build (their
  levels, housing, a cited playbook), against the strongest bases found.

## Steps
| # | Step | State |
|---|---|---|
| 1 | Everything accounted for: `tools/baselab/engine_coverage.py` runs every entity in a battle; audit ledger open items triaged (fixed / irrelevant / needs data) | coverage tool's spell probe broken (tool bug); ledger triage to do |
| 2 | Attacks: cited playbook per meta army; red-team search per base | done (playbooks, red team merged) |
| 3 | Sensitivity: re-score finalists with pacing, waits, skill, strength, aim wait pushed both ways | to do |
| 4 | Base search: quality-diversity from scratch incl. unconventional designs (qd_search.py), red-team judged finalists, trap re-placement (trap_polish.py), CC composition | running |
| 5 | Army search: user-buildable armies x cited plans vs the strongest bases | to do |
| 6 | Patch update, one command: refresh game data + wiki, diff, flag stale hard-coded values and new content, rerun checks, re-score saved bests | to do |
| 7 | Real test loop: user puts the pick up, daily battle log vs prediction, trace and fix disagreements | ongoing (log collector runs daily) |

## Where the assumptions are
- Solid: unit/building/trap numbers and rules (game data v18.200.9, wiki;
  ~3,700 values cross-checked, 134 hard-coded values cite game data).
- Assumed: attacker behaviour details (timing, exact placement, armies that
  differ from the playbook's example), a few animation timings, TH17/18
  attacker calibration. Steps 2, 3 and 7 exist to bound these.
