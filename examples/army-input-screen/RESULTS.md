# Conditional screen results

Five attempts total on unchanged fc9 code/data: the original three cases, one scoped B correction, and one B transfer. No automatic retry, broad sweep, new mechanic or shared combat edit. Nine distinct bundles passed full-battle admission (five v1, four review corrections).

| Input / fixture | Status | Stars | Destruction | Simulated seconds | End reason |
|---|---|---:|---:|---:|---|
| fourteen-dragons-twenty-minions / defense-0-hot-candle / west | completed | 2 | 89.36% | 180.00 | declared_time_limit |
| A-funnel-cleanup / defense-0-hot-candle / west | process_failure | — | — | — | unscored |
| B-funnel-balloon / defense-0-hot-candle / west | completed | 2 | 93.62% | 83.06 | attack_force_exhausted |
| B-funnel-balloon-v2 / defense-0-hot-candle / west | completed | 2 | 98.94% | 180.00 | declared_time_limit |
| B-funnel-balloon-v2 / defense-1-hero-hunter / east | completed | 0 | 47.87% | 68.62 | attack_force_exhausted |

Among the completed matching west cases, the conditional stars/destruction order is B v2, B v1, then C0. A has no score and cannot be placed in that order. The east result is a whole-plan transfer to another design/entry, not another cell in the west ranking or an independent real-game holdout.

B v1 cleared both west shoulders before commitment (camp 1.75s; gold storage 9.6322s), deployed all 320 troop housing and used all three active abilities. Its lead Dragon died at 42.3455s; the two later Rage casts remained blocked, along with later core Freezes. It spent 7/14 spell housing and ended with the attack force exhausted at 83.0603s. Hall death was 82.6399s.

The reviewed B v2 input removes that single-Dragon support gate and schedules Warden at 27s. On west it spent 13/14 spell housing, with every owned troop deployed; Hall death was 61.4368s. The conditional preparation Freeze remained unused after the shoulder cleared. One hidden Tesla remained. Its only surviving attacker was the Unicorn, so the 180-second end is not evidence of useful offensive survival or a simple cleanup opportunity. C0 also reached its time limit with only its Unicorn alive; elapsed time is not used as a score bonus.

A v1 hit the existing Duke isolation boundary guard versus the Slammer at 25.839675625595948 simulated seconds. The exact error is retained with no prefix score. A v2's support correction compiles but has not run. Resolving that guard belongs to the combat owner; this stream did not weaken it or move troops blindly to evade it.

The west and east B v2 inputs were frozen before their own outcomes. East completed with 0 stars and 47.8723% destruction. The force was exhausted at 68.6168 seconds; the Hall retained 5045.536 of 10800 HP. Both named shoulders died before 20 seconds (Air Defense 3 at 4.6431; Super Wizard Tower 0 at 7.9855), but the preparation Dragons died at 1.2191 and 4.8346 seconds. Initial targets match the declared shoulders; the upper Dragon recorded no projectile launch before death, so do not credit it with clearing the Air Defense. Champion, Duke and Queen died at 25.10, 25.8034 and 29.9160 seconds. All 320 troop housing deployed, all three active abilities were used, and 9 of 14 spell housing was spent. The army still failed. Successful shoulder-clear tells alone do not establish a viable entry, sufficient hero support or Hall access. No attempt is made to isolate the entry-angle effect from the changed defense design.

Practical disposition: B v2 is the strongest observed west package but its severe east failure prevents general TH18 promotion. Retain C0 as a reproducibility/control baseline and A unranked pending the owner fix. This batch does not establish a validated two-army shortlist. Confirm actual gear/pets/donations and translate ideal HP observations before any player-ready card. The fixed 20-second commitment still risks a failed funnel; the Hall-risk Freeze is only the disclosed imperfect proxy and does not solve bait/invisibility or provide dynamic rerouting. Further work should address these observed entry/support failures within a newly reviewed bounded plan, not expand a combinatorial search.

Full plans, exact budgets/equipment/pets and limitations are in README.md and review-corrections-v2/README.md. evaluation-status.json contains compact identities and outcomes. Full external evidence is in the task23 run directories and evidence ZIP. Existing v1 files and all failures are preserved; the unused v1 transfer manifest is superseded by the two-slot review-correction manifest. No additional runs remain authorized within this frozen batch.
