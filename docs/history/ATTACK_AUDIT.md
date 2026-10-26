> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](../README.md) for native commands and remaining Python ports.

> Historical record, archived by G4 on 2026-10-25. Status claims, Python
> commands and removed source paths below describe their dated revision. Use
> [the current documentation](../README.md) for supported workflows. Local artifact paths
> were updated for retrieval; their contents and calibration claims are unchanged.

# Attack technique audit: written guides vs the simulator

Done 2026-10-15 at the user's request ("look up all written writings of the best attack strategy and determine if we accurately model it").

## Sources read
- **TrophyCoach:**
  - How to Three-Star in War (5-step system)
  - Queen Charge Guide
  - Best War Attack Strategies 2026
  - Army meta builds (`data/meta-armies-2026-10-15.json`)
- **1337wiki:** TH18 attack strategy. Step-by-step Duke Charge Hydra, Rocket Backpack Throwers, Duke Charge Super Bowlers and RC Walk Meteor Golems.
- **cocbasedrop:** TH18 attack strategy (Root Rider Yeti with RC charge, Lalo, funnelling checklist, base reading).
- **Boostroom:** funnelling masterclass.
- **blueprintcoc:** TH18 strategies. This one only names armies; its details are in paid videos.
- **Also:** equipment guides and the wiki's Giant Arrow page.

## Status legend
- **Yes:** modeled as the guides describe.
- **Partly:** a simpler version exists.
- **No:** missing.

Every Yes or Partly item points at the code. A play only becomes default behavior after a paired screen shows it helps (`policy_screen.py`, `charge_screen.py`). Otherwise it stays an option the tactic search can choose.

## Funnel and deployment

| Technique (source) | Status | In the engine |
|---|---|---|
| Two-sided funnel before the main army: hero or cheap troops on each flank (all guides) | Yes | `funnel_heroes` at ±6 tiles, `flank` troops; tactic knobs `funnel_scale` and `funnel_shift` |
| Wait 5–10 s for the corners to clear before committing (TrophyCoach, cocbasedrop "extra 3–4 s") | Yes | `main_min`/`main_max` plus `commit_progress` (buildings down near the entry); tactic knobs |
| Pick the weak side after scouting (TrophyCoach step 1) | Partly | The calibrated attacker scouts 2 random sides; the tactic search picks the side freely. It reads results, not the base. |
| Main army in a tight line, not scattered (TrophyCoach step 4, Boostroom) | Yes | `spread` knob; tight drops won in `attack_lab` |
| Tank first, damage dealers behind it a beat later (TrophyCoach step 4, 1337wiki) | **No** | The main wave lands all at once. Added below as `tank_lead`. |
| Heroes with the push, not ahead (TrophyCoach) | Yes | `push_heroes`; `heroes_push` knob |
| Siege lane: Log Launcher, Sky Wagon, Troop Launcher with Wall Breaker barrels | Yes | Sieges modeled as units; CC troops released where the siege breaks |
| Super Wall Breakers to open the first compartment (1337wiki) | Partly | `breakers` fire when 2+ push troops are stuck on a wall (`_breach`). Not pre-planned. |
| Jump or Earthquake to open compartments early (Boostroom) | Partly | Jump and 4× Earthquake in `_breach` when stuck; `eq_core_dist` policy play for core walls |
| Overgrowth to steer or narrow the path, or take a defense out (1337wiki) | Partly | Cast on the most dangerous defense cluster (`og_min_score`). Steering is not modeled. |
| Cleanup troops on far corners mid-fight (Boostroom 2:00–1:45 remaining) | Yes | Cleanup phase 25 s after the main drop, troops spread to far buildings |
| Clan Castle lure, drag to a corner, kill with Poison (TrophyCoach 3.5) | Partly | `lure_time` drops one troop by the CC; Poison targets CC troops near the army. The drag-and-kill is missing. |
| Two-flank air attack (Hydra) to split defensive fire (TrophyCoach, cocbasedrop) | Yes (new) | `split_main` knob |
| Lava Hound first, then the air pack (1337wiki, cocbasedrop) | **No** | Part of the tank-first item. |

## Hero charges and walks

| Technique | Status | In the engine |
|---|---|---|
| Queen Charge: Queen plus 4–6 Healers dropped together a beat after her (TrophyCoach) | Yes (new) | `setup_charge`; Healers drop 0.6 s after the hero, grouped |
| Royal Champion charge or walk with Invisibility; Recall once the funnel is done (1337wiki RC Walk, the user) | Yes (new) | `_charge_spells`: Invisibility when a heavy defense locks on or she is hurt; Recall after `charge_len` or below `charge_recall_hp`; she rejoins with the push |
| Invisibility cadence: about every 10 s while the Spirit Fox lives, every 4 s after (1337wiki) | Partly | Spirit Fox invisibility is modeled (`heroes.py`); our cast gap is fixed (`invis_gap` 4.5 s) and does not know about the Fox |
| Recall funnel: charge one flank, Recall, redeploy up the other (TrophyCoach) | Yes (new) | `recall_funnel` knob |
| Dragon Duke charge, Royal Rampage away from friendly flyers (1337wiki, TrophyCoach) | Yes | Duke charge (no Healers: they heal ground only); Rampage in the engine |
| Duke Rocket Backpack dash into a tight defense group, plus Earthquake and Lightning on that group (1337wiki Rocket Backpack Throwers) | Partly | Aimed dash (`dash_aim`); Lightning only zaps Air Defenses; no Earthquake + Lightning on the dash group |
| Revive the Duke once the main army reaches him, not early (1337wiki) | Partly | `revive_delay` after death, not tied to the army arriving |

## Spells

| Technique | Status | In the engine |
|---|---|---|
| Freeze the defense that is killing you, at that second (TrophyCoach step 5) | Yes | Freeze on the highest-threat defense in range that is firing; `freeze_reach`/`freeze_first` |
| Rage when the army enters the core (TrophyCoach); hold Rage so defenses commit first (cocbasedrop) | Yes | Rage when a share of the army is engaged (`rage_engaged`) |
| Heal when crossing a damage zone | Yes | Heal below `heal_hp` average health |
| Poison on CC troops and the defending hero cluster | Yes | Poison on 3+ defenders or any hero |
| Totems on the Guardian, defending heroes and big defenses (1337wiki) | Partly | Totems between the army and the hottest threats; not aimed at the Guardian or heroes specifically |
| Lightning to snipe an Air Defense before dragons (TrophyCoach, meta: 11 Lightning) | Yes | `zap_ad` |
| Angry Spell to turn troops chasing non-defenses back onto defenses (1337wiki Bowlers) | **No** | Real builds carry it; the brain never cast it. Added below. |
| Skeleton Spell as a distraction | **No** | Never cast. Added below. |
| Bat Spell | **No** | Never cast. Added below. |
| Ice Block, Haste, Clone, Recall | Yes | Triggers in `generic_spells` |

## Hero abilities and equipment

| Technique | Status | In the engine |
|---|---|---|
| Fire abilities at peak danger, not first danger (Boostroom, TrophyCoach) | Yes (tuned) | HP and time triggers; the learned policy fires sooner (`hero_hp` 0.7), +3.1% 3★ in testing |
| Eternal Tome the instant a big volley is coming | Partly | Warden fires on hurt nearby troops or low health, not on a predicted volley |
| Giant Arrow early, aimed at a key defense; double damage to Air Defenses | Yes | Aimed Arrow (`arrow_aim`, adopted); 2× vs AD in `heroes.activate` |
| Giant Arrow to trigger an Invisibility Spell Tower early | **No** | Low priority |
| Rocket Spear from range | Yes | Equipment effect; fired by the generic trigger |
| Warden Fireball on a cluster of key defenses at the start (TrophyCoach Super Yeti) | Partly | Fireball is implemented, but it fires with the Warden's ability, not aimed at a cluster at the start |
| All 43 hero equipment pieces | Yes | Every one is referenced in the engine |

## Army choice

| Technique | Status | In the engine |
|---|---|---|
| Real compositions per Town Hall | Yes | 22 TrophyCoach builds, weighted by real usage |
| War: pick the army that punishes the base's weakness (TrophyCoach step 2) | Partly | War scenarios use the TH16 meta mix. They do not pick the best army per base. In war, real attackers do. |

## Plan from this audit
1. **Now:**
   - cast Angry, Skeleton and Bat spells;
   - tank-first deployment (tanks lead, damage dealers a beat behind, Lava Hound first);
   - screen both against the current behavior.
2. **Next:**
   - Earthquake and Lightning on the dash group or a key defense cluster;
   - Totems aimed at the Guardian and defending heroes;
   - Revive tied to the army arriving;
   - an Invisibility cadence that knows about the Spirit Fox.
3. **Then:**
   - a war mode where the attacker brings the best of several armies for each base;
   - CC drag-and-kill.
