# When does the sim match the game?

Goal from the user (2026-10-18): keep going until the simulation matches the game, using any source (wiki, game data, video transcripts, guides, pictures, the user's real battles). "Be skeptical of everything. Don't trust, verify."

The sim counts as matching only when every check below passes. Each line is measured by a script, not judged by eye.

| # | Check | Target | How it is measured | Status (2026-10-19, round 6) |
|---|---|---|---|---|
| 1 | Unit, building, spell and equipment numbers | Agree with two independent sources | ClashKing game data vs engine, plus wiki for anything ClashKing lacks (`$TEMP/xcheck.py`, to move into `tools/baselab/xcheck_stats.py`) | 3,699 match, 0 open |
| 2 | Mechanics | Every mechanic used by meta armies passes a wiki-fact test | `tools/baselab/mechanic_tests.py`: small staged battles with a known wiki answer (time to kill, damage per hit, heal rate, trigger rules) | 7/7 pass (Inferno ramp, Healer on troops and heroes, Root Rider wall break, Freeze); 13 Codex category audits running |
| 3 | Attack plays | Every scripted step cites a real player's description | Playbooks in `output/sources/playbooks/`, every step quote-checked against its transcript | extraction running (211 transcripts) |
| 4 | Army strength without fudge | Every calibrated TH16 build within 0.85–1.15 | `tools/baselab/calibrate_meta.py --techniques` | Round 6: Throwers 1.01 pass / 1.24 fail; Dragons 0.88 pass; Root Riders 1.21/1.24 fail (round 5, before the waits: 1.04/1.14) |
| 5 | Real defenses replayed | Brier clearly below the always-guess-the-average baseline, and destruction error under 4 points, with at least 40 real defenses | `tools/baselab/replay_log.py data/live/battles.jsonl` | Round 6, 12 defenses: Brier 0.241 vs 0.222, 7.6 points, star bias -0.11, sim P(3★) 56% vs real 67% (fail; round 5 was 0.230 / 6.4; 12 defenses is too few to separate these) |
| 6 | Real attack times | Sim time to finish within 15% of the user's real attack times for the same army | `replay_log.py`: sim time to 3-star vs real `battleTime` on real 3-star defenses | Round 6, 8 defenses: sim/real 0.87 (pass). Fixed by player pacing and the waits measured from the source videos (4.5 s within a phase, 16.6 s between; `tools/baselab/step_gaps.py`); neither was tuned to this check (round 5: 0.64) |
| 7 | Real base ordering | The sim agrees with the user's live tests: the hole-free base is weaker than ranked-funnel1 for the user's armies (Throwers excepted) | `tools/baselab/adaptive_check.py` with playbook attackers | Round 6, 8 seeds: fail, funnel1 14.3% vs hole-free 14.6% (a tie; reality: hole-free much weaker). Root Riders keep more units on hole-free (13.1 vs 9.1), as the user saw, but the gap is small. The round-5 destruction pattern did not hold at 8 seeds. 8 angles x 2 flanks already cover the TH corner |
| 8 | The user's own armies | Sim destruction with the user's armies within 10 points of their real attacks | The user's attacks in `data/live/battles.jsonl` (bases unknown, so only the level of strength is compared) | Air army: real ranked 76-89% vs TH17, sim 60-66% vs TH16 (fail, ~20 points weak). Druid/Ruin Witch: real 3★ x2 and 64%, sim 80-94% |

Notes:
- Ground truth is scarce. Checks 5 and 6 get stronger every day as `clash-battlelog-snapshot` adds battles to `data/live/battles.jsonl`. Record every base change in `data/live/base-history.json`, so replays use the right layout.
- A check is never passed by tuning against the test data itself. Calibration uses the reference bases; replays are held out.
- Anything taken from Codex or a transcript is verified before it changes the engine (quote check, wiki, or game data).
