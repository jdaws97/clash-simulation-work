# When does the sim match the game?

Goal from the user (2026-10-18): keep going until the simulation matches the game, using any source (wiki, game data, video transcripts, guides, pictures, the user's real battles). "Be skeptical of everything. Don't trust, verify."

The sim counts as matching only when every check below passes. Each line is measured by a script, not judged by eye.

| # | Check | Target | How it is measured | Status (2026-10-18) |
|---|---|---|---|---|
| 1 | Unit, building, spell and equipment numbers | Agree with two independent sources | ClashKing game data vs engine, plus wiki for anything ClashKing lacks (`$TEMP/xcheck.py`, to move into `tools/baselab/xcheck_stats.py`) | 3,699 match, 0 open |
| 2 | Mechanics | Every mechanic used by meta armies passes a wiki-fact test | `tools/baselab/mechanic_tests.py`: small staged battles with a known wiki answer (time to kill, damage per hit, heal rate, trigger rules) | 7/7 pass (Inferno ramp, Healer on troops and heroes, Root Rider wall break, Freeze); 13 Codex category audits running |
| 3 | Attack plays | Every scripted step cites a real player's description | Playbooks in `output/sources/playbooks/`, every step quote-checked against its transcript | extraction running (211 transcripts) |
| 4 | Army strength without fudge | Every calibrated TH16 build within 0.85–1.15 | `tools/baselab/calibrate_meta.py --techniques` | Throwers 0.91/1.07 pass; Dragons 0.81 fail; Root Riders 1.28/1.31 fail |
| 5 | Real defenses replayed | Brier clearly below the always-guess-the-average baseline, and destruction error under 4 points, with at least 40 real defenses | `tools/baselab/replay_log.py data/live/battles.jsonl` | 12 defenses: 0.220 vs 0.222, 4.8 points (fail) |
| 6 | Real attack times | Sim time to finish within 15% of the user's real attack times for the same army | `replay_log.py`: sim time to 3-star vs real `battleTime` on real 3-star defenses | 8 defenses: sim/real 0.70 (fail: sim attacks finish 30% faster). Leads: deploy pacing (the playbooks fix it), unknown defensive CC and heroes, unit timing details (rules audit) |
| 7 | Real base ordering | The sim agrees with the user's live tests: the hole-free base is weaker than ranked-funnel1 for the user's armies (Throwers excepted) | `tools/baselab/adaptive_check.py` with playbook attackers | fail: 27% vs 31% (only Root Riders right) |

Notes:
- Ground truth is scarce. Checks 5 and 6 get stronger every day as `clash-battlelog-snapshot` adds battles to `data/live/battles.jsonl`. Record every base change in `data/live/base-history.json`, so replays use the right layout.
- A check is never passed by tuning against the test data itself. Calibration uses the reference bases; replays are held out.
- Anything taken from Codex or a transcript is verified before it changes the engine (quote check, wiki, or game data).
