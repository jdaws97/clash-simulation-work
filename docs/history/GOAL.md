> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](../README.md) for native commands and remaining Python ports.

> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Goal (phase 2, set 2026-10-15 evening): the best base-design engine, the best bases and the best attacks

The user's words: "create the best simulation engine for creating defense bases for ranked and war, and the best simulated attack strategies. Iterate until you're satisfied. Try the ML stuff or anything else that adds to this. Clean up the workspace."

Satisfied means every box below is checked, with the evidence in this repo. A method is adopted only when it wins on equal compute and is judged on hold-out battles, never on its own search battles.

## A. Search engine for bases

- [x] Original layouts from scratch, with no template and no seed from existing bases (`archetypes.py`: organic and free plus four styles). All are legal, use at most 325 walls and have no drop holes.
- [x] A freeform wall move (`_rewire`): rooms split, merge and reshape during the search.
- [x] Attack-aware moves (`diagnose.py`, `guided_move`): traced battles show breaches, troop traffic and which defenses fall first, and changes are aimed there.
- [x] Population search with crossover and diversity (`evolve.py`, `tools/baselab/evolve_bases.py`).
- [x] A/B on equal compute, plain vs guided annealing (`tools/baselab/ab_guided.py`, 3 original starts, 60 steps each). Mean hold-out gain: guided **+1.10**, plain +0.16. Guided moves are now the default in `evolve_bases.py`: the top 4 parents each get a trace.
- [x] Noise sizing:
  - Attacker policy: about 300–700 paired battles to see a +0.05 change (`policy_screen.py`).
  - Base scores (`base_noise.py`): rank agreement between two independent battle sets is 0.79 at 68 battles and 0.84 at 136.
- [x] Learned attacker policy, screened before training. Single threshold changes are worth at most about ±0.05 (`local/evidence/policy-screen.out`). The combined positives won +0.061 ± 0.021 (+3.1% 3★) on 1,200 held-out battles and were adopted (`data/attacker-policy.json`). The planned long training run was dropped as noise-limited.
- [x] Real meta armies: 22 TrophyCoach builds, TH16/17/18 (`data/meta-armies-2026-10-15.json`, `meta_armies.py`), all camp-legal, weighted by real usage, used by every battle path (`meta_scenarios`).
  - TH16 builds are calibrated to real same-TH 3★ rates on the real bases (`calibrate_meta.py`): Throwers 1.04 / 1.43, Dragons 0.96, Root Riders 1.60 / 1.65. The engine's ground pushes are still weaker than real players'.
  - TH17/18 builds borrow their archetype's TH16 strength.
- [ ] A/B annealing vs evolution on equal compute.
- [ ] A learned score predictor (surrogate) trained on logged evaluations (`BASELAB_EVAL_LOG`). It pre-screens many candidate moves so only the promising ones are simulated. Success: rank correlation of at least 0.7 on held-out layouts, and more hold-out gain per CPU-hour than without it.
- [~] Adaptive attackers: attack plans (side, funnel, timing, spell targets) are searched against each candidate base, so a base must beat the strongest found attack, not only the scripted ones. Reported as worst-case alongside the average. (`tactics.py`, CEM over 11 knobs, co-evolution in `evolve_bases.py`.)
- [ ] Strategy breadth (raised by the user: "giant arrow, rocket backpack and earthquakes to take out compartments"):
  - Targeted actions the adaptive attacker chooses and aims:
    - a spell on a chosen target (core walls, key defense, CC, TH compartment);
    - a hero ability at a chosen time and target (Giant Arrow on a defense, Rocket Backpack into a compartment, Earthquake Boots on a wall line);
    - Freeze and Invisibility timed onto a named defense;
    - Overgrowth on a defense cluster.
  - More armies by meta share, each legal at TH16/17/18: blimp entries (Battle Blimp, Super Archer Blimp), Queen Charge hybrids, Lalo, Electro Titan smash, Super Witch/Yeti smash, Dragon and Rocket Balloon lines.
  - Today's state: 4 armies, one phased script, abilities on HP or time triggers, Earthquakes only for stuck-wall breaches or the AD zap.
  - Next armies by real meta share (RESEARCH-2026-10.md): Super Bowler Smash 6.4%, Mass Super Yeti 4.0%, Meteor Golem 2.3%.
- [ ] A learned attacker policy (the user asked for an attacker that "learns how to attack like a human": spells, equipment, aiming, troop drops, distractions):
  - Decision points with learnable triggers and targets, trained by evolution strategies across a library of many bases, so it learns general skill rather than one base's answer:
    - aimed abilities;
    - Freeze and Invisibility triggers;
    - Earthquake the core;
    - distraction drops and CC lures;
    - when to commit the push.
  - The per-base plan search (side, funnel, timing) sits on top, like a player scouting.
  - The attacker population's skill is calibrated to real outcomes: TrophyCoach per-army 3★ rates and the user's defense log. Human-level, not superhuman, so it cannot win by exploiting sim quirks.
  - Not chosen: imitation learning (no replay data with drop positions and times exists for this) and full deep RL (days to weeks of compute, needs PyTorch, and it exploits sim quirks). Deep RL can be layered on later, starting from the learned policy.

## B. Bases

- [ ] An original ranked base, designed from scratch, that beats the user's base and the remix on hold-out (TH17/18 meta, Electro) and stays ahead under Legend I.
- [ ] The same for war (TH16 attackers, lowest 3★ rate).
- [ ] Each final base is checked against adaptive attackers, with per-army breakdowns, weak sides and in-game build coordinates.

## C. Attacks

- [ ] Attack plans for the user's account (real levels, Portal Pendant level 1), optimized by the adaptive-attacker search against the best bases found: TH16–18, at Electro and Legend I.
- [ ] Concrete guides: camp 320 plus CC 50, spells, deploy order, side choice, and the fixes for the user's reported problems (Duke and RC dying early, Throwers spreading, Root Riders dying fast).

## D. Housekeeping

- [ ] `output/` stays under 200 MB. Image crops and debug overlays are deleted when done, evaluation logs are compressed, and no orphan processes are left behind.
- [ ] The report is rebuilt and republished at the same URL. The work is committed only with the user's OK.

---

# Phase 1: a simulator I trust, and the ranked and war answers it gives

Set 2026-10-15 at the user's request. The work is done when every item below is checked off, and every number in the final report can be traced to a run in this repo.

## 1. Finish and trust the simulator

- [x] Every entity in the game is modelled: all troops, super troops, sieges, summons, heroes, equipment, pets, spells, defenses, traps, crafted defenses and TH18 Guardians. `tools/baselab/engine_coverage.py` passes with zero errors.
- [x] Every defense's delivered DPS is within about 3% of its wiki table (`docs/history/ENGINE_V2.md`).
- [x] Ranked difficulty modifiers are modelled: Legend III, II and I (defense, defending hero and Guardian bonuses, attacking hero penalty, with the wiki's exclusions).
- [x] Equipment released after the ClashKing export, such as Portal Pendant (Oct 8, 2026), is pulled from the wiki.
- [x] The simulator reproduces real outcomes:
  - On human reference bases it matches TrophyCoach 3★ rates (calibration).
  - On **your own base** it matches your real defense log: about 5 trophies per defense, 10 of 13 three-starred.
- [~] The ground-army calibration gap shrinks through better attacker behaviour (wall breaching, funnelling, hero timing), not through stat boosts. Every remaining factor is stated plainly.
- [ ] Constants the wiki doesn't give are checked against your two screen recordings where possible.

## 2. Defense: bases that hold against the best TH16–18 attacks

- [x] **Ranked base (TH16).** Optimized against the live TH17/18 meta armies, weighted by how often you face them, at Electro (no modifier). Also reported under Legend modifiers in case you're promoted.
- [x] **War base (TH16).** Optimized against TH16 meta armies, minimizing 3★ rate.
- [x] Both are compared with your current base and the best human bases, on held-out scenarios, with per-army breakdowns and known weak spots.

## 3. Attack: strategies for your account

- [~] Targets: the best TH16–18 bases I can find — top human layouts digitized from screenshots, plus my optimized bases.
- [x] Armies run at your real levels (API), including Portal Pendant at level 1.
- [x] Tested at no modifier (Electro), Legend III and Legend I. Legend II sits between those two and was not run separately.
- [x] Results: 3★ rate, average stars and destruction for each army against TH16, TH17 and TH18 targets, plus the recommended army and loadout.

## 4. Deliver

- [x] A published report with base images and tile coordinates for building them in-game, attack recommendations, the evidence behind them, and limitations.
- [ ] The work committed to the repo once you approve.

## Status on 2026-10-15

- Report: https://claude.ai/artifact/SLevmdUcHE64TF4ztUsieH (generated by `tools/baselab/build_report.py`).
- `[~]` items are partly done:
  - The ground gap improved from 2.2–2.5× to 1.5–1.6×. The remainder is player skill, explained in `docs/history/ENGINE_V2.md`.
  - The TH17/18 attack targets are optimized and generated bases. No top online bases were digitized, pending the user's OK to download images.
- Still open: checking assumed constants against the two screen recordings, and committing the work (needs the user's approval).
