# New attack strategies (reasoned from mechanics, tested in the sim)

The user asked for strategies humans don't use yet, reasoned from the heroes, equipment, spells and troops. Every idea is a legal TH16 army for the user's account (camp 320, CC 50, spells 11, CC spells 3), defined in `data/custom-armies.json`. It is benchmarked by `tools/baselab/army_bench.py` against the user's own Root Rider army and the real TH16 meta builds:
- scripted with scouting on 6 strong bases;
- tuned tactics on the hardest ones.

**Honesty rule:** new strategies are where the simulator is least validated, because no real-world 3★ rate exists to calibrate against. Each result is marked with how well-tested its key mechanics are. The real test is a friendly challenge.

| Idea | Mechanical reasoning | Key mechanics and how well they're tested |
|---|---|---|
| **Portal relay Root Riders** | Minion Prince with Portal Pendant walks in the Root Rider push. When it stalls or is hurt, he portals it (up to the pendant's capacity) and redeploys it healed and hasted on a fresh side: two pushes from one army. Portal Pendant shipped Oct 8, 2026, so there's no human playbook yet. | Portal Pendant from the wiki (radius, capacity, heal, haste); the trigger is the brain's (stalled or hurt push). Untested against reality. |
| **Druid + Electro Titan Root Riders** | Healers fly, so Air Sweepers, Seeking Air Mines and air-targeting defenses kill them. Ground healing (Druids) behind an Electro Titan tank survives where Healers die. | Druid healing and Titan aura from wiki stats; Druid AI simplified. |
| **Puppet Queen Throwers** | The Queen with Healer Puppet and Magic Mirror brings her own Healers, so the 5 camp Healers (70 housing) become 4 more Throwers. | Puppet Healers from the wiki. The user's Throwers are level 2, the TH16 maximum (corrected by the user). |
| **Lavaloon Queen Dragons** | The Queen with Lavaloon Puppet funnels one flank and the King the other, so no camp space goes to funnel troops, behind the real TH16 meta (16 Dragons + 11 Lightning). | Puppet summons from the wiki. |
| **Decoy Super Yeti** | Bat and Skeleton Spells as decoys pull Scattershot, Monolith and single-target fire off a Super Yeti push; Druids heal from the ground. | Decoy targeting depends on defense target rules (modeled); the spell triggers are new (`skeleton_on`, `bat_on`). |
| **Flame Flinger Throwers** | Separation funnel: the Flinger burns a side from outside instead of a Log Launcher. Rare at TH16. | Flinger placement is simplified: the siege lands at the push entry, not on the opposite flank. Weak test. |

## Results (2026-10-15, `output/army-bench.out`, `output/army-bench-raw2.out`)

Scripted plan with scouting: 8 sides × 6 skill seeds per base, mean 3★ over your base, l1x, the remix, web A and the TH17 and TH18 targets. The user's levels throughout.

| Army | Family-calibrated | Raw (all 1.0) |
|---|---|---|
| **Puppet Queen Throwers (new)** | **48.4%** | **20.9%** |
| Druid + Titan Root Riders (new) | 37.3% | 0.7% |
| Real TH16 Throwers b2 | 31.9% | 4.0% |
| Portal relay Root Riders (new) | 29.6% | 0.7% |
| Real TH16 Root Riders b1 | 21.5% | 0.0% |
| Flame Flinger Throwers (new) | 21.0% | 7.2% |
| Real TH16 Throwers b1 | 20.6% | 12.1% |
| Decoy Super Yeti (new; no TH16 calibration) | 19.9% | 19.9% |
| User's Root Rider army | 10.3% | 2.7% |
| Real TH16 Dragons | 7.1% | 9.5% |
| Lavaloon Queen Dragons (new) | 3.3% | 6.8% |

Tuned tactics on the hardest bases (TH17 target / TH18 target / remix):

| Army | TH17 target | TH18 target | Remix |
|---|---|---|---|
| Puppet Queen Throwers | 83% | 29% | 96% |
| Real Throwers b2 | 33% | 8% | 83% |
| Druid-Titan Root Riders | 33% | 8% | 79% |
| Portal relay | 42% | 0% | 79% |

**Reading:**
- Puppet Queen Throwers wins under both calibration views and with tuning. It is pending a mechanics check of Healer Puppet: wiki vs engine.
- The Root Rider variants beat the real Root Rider build only with calibration. Raw, all Root Rider armies are near 0%, because of the known ground-push gap.
- Lavaloon Queen Dragons and Flame Flinger Throwers do not beat their baselines.
