# When does the sim match the game?

Goal from the user (2026-10-18): keep going until the simulation matches the game, using any source (wiki, game data, video transcripts, guides, pictures, the user's real battles). "Be skeptical of everything. Don't trust, verify."

The sim counts as matching only when every check below passes. Each line is measured by a script, not judged by eye.

| # | Check | Target | How it is measured | Status (2026-10-19, round 7) |
|---|---|---|---|---|
| 1 | Unit, building, spell and equipment numbers | Agree with two independent sources | ClashKing game data vs engine, plus wiki for anything ClashKing lacks (`$TEMP/xcheck.py`, to move into `tools/baselab/xcheck_stats.py`) | 3,699 match, 0 open |
| 2 | Mechanics | Every mechanic used by meta armies passes a wiki-fact test | `tools/baselab/mechanic_tests.py`: small staged battles with a known wiki answer (time to kill, damage per hit, heal rate, trigger rules) | 7/7 pass (Inferno ramp, Healer on troops and heroes, Root Rider wall break, Freeze); 13 Codex category audits running |
| 3 | Attack plays | Every scripted step cites a real player's description | Playbooks in `output/sources/playbooks/`, every step quote-checked against its transcript | extraction running (211 transcripts) |
| 4 | Army strength without fudge | Every calibrated TH16 build within 0.85–1.15 | `tools/baselab/calibrate_meta.py --techniques` | Round 7: Throwers 1.01 pass / 1.17; Dragons 0.88 pass; Root Riders 1.17 / 1.17 (just outside) |
| 5 | Real defenses replayed | Brier clearly below the always-guess-the-average baseline, and destruction error under 4 points, with at least 40 real defenses | `tools/baselab/replay_log.py data/live/battles.jsonl` | Round 7, 12 defenses: Brier 0.192, below the 0.222 baseline for the first time; 6.5 points; sim P(3★) 58% vs real 67%. Still fails formally: needs 40 defenses |
| 6 | Real attack times | Sim time to finish within 15% of the user's real attack times for the same army | `replay_log.py`: sim time to 3-star vs real `battleTime` on real 3-star defenses | Round 7, 8 defenses: sim/real 0.84 (just under; round 6: 0.87). Fixed by player pacing and the waits measured from the source videos (4.5 s within a phase, 16.6 s between; `tools/baselab/step_gaps.py`); neither was tuned to this check (round 5: 0.64) |
| 7 | Real base ordering | The sim agrees with the user's live tests: the hole-free base is weaker than ranked-funnel1 for the user's armies (Throwers excepted) | `tools/baselab/adaptive_check.py` with playbook attackers | Round 7, 8 seeds, best side (as a scouting player attacks): **pass for the user's armies.** Root Riders 88% vs 62% 3★ on hole-free vs funnel1 (14.2 vs 10.8 units left); Druids 50% vs 12% (94.5% vs 78.4% destruction); Throwers do worse on hole-free, as the user found. Meta Dragons disagree (75% vs 100%). Averaged over all sides it is still a tie (14.1% vs 15.2%). The user's air army is left out (they rarely attack with air). Their real attacks came from the Eagle side; from there the sim shows the gap too |
| 8 | The user's own armies | Sim destruction with the user's armies within 10 points of their real attacks | The user's attacks in `data/live/battles.jsonl` (bases unknown, so only the level of strength is compared) | Air army: real ranked 76-89% vs TH17, sim 60-66% vs TH16 (fail, ~20 points weak). Druid/Ruin Witch: real 3★ x2 and 64%, sim 80-94% |

Notes:
- Ground truth is scarce. Checks 5 and 6 get stronger every day as `clash-battlelog-snapshot` adds battles to `data/live/battles.jsonl`. Record every base change in `data/live/base-history.json`, so replays use the right layout.
- A check is never passed by tuning against the test data itself. Calibration uses the reference bases; replays are held out.
- Anything taken from Codex or a transcript is verified before it changes the engine (quote check, wiki, or game data).
- Check 7 with a red-team attacker (docs/REDTEAM.md: the best cited attack per base, scored on fresh seeds; 2026-10-20). Root Riders: hole-free is weaker than funnel1 (39.4 vs 36.2 trophies). Druids: funnel1 looks weaker (29.1 vs 25.5) once it is attacked well. Neither army picks the Eagle side of hole-free.
