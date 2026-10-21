# Video shot list: what only footage can settle

The game data tables fix almost every number. These are the timings and
shapes they leave ambiguous; each is currently an inferred value in the
engine. Record at 60 fps if possible (Google Play Games on PC + any screen
recorder), no commentary needed. Any replay or friendly challenge where the
moment happens works; slow-motion replay is fine. Only video files are
analysed: nothing touches the game client.

## A. Full defense replays (highest value)
5-10 of your Legend defense replays, start to finish. Each is a real
attacker's exact deploys and timings on a known base: the sim replays the
same army on the same layout and is compared second by second, not just on
final stars and %.

## B. Short clips (a few seconds each)
| # | Moment to capture | What gets measured | Engine now |
|---|---|---|---|
| 1 | A Bomb going off under a troop | trigger -> blast time (calibrates the frame rate for all traps) | 1.5 s (wiki) |
| 2 | A Giant Bomb going off | trigger -> blast | 1.59 s (inferred from frames) |
| 3 | An Air Bomb and a Seeking Air Mine firing | trigger -> hit | 0.3 s (inferred) |
| 4 | A Tornado Trap starting | trigger -> first pull | 0.34 s (inferred) |
| 5 | A Spring Trap with Hog Riders or Miners running over it | do fast troops pass untouched | trigger picks within 1 tile |
| 6 | A Scattershot's first shot at a fresh target | lock-on -> first shot, then shot interval | instant first shot, 3.2 s interval |
| 7 | An Air Sweeper puff hitting a Balloon line | how wide the puff is (angle) and push distance | +-5 degrees |
| 8 | A Freeze Spell on a group of troops/defenses | do edge units unfreeze earlier (outer ring) | uniform freeze |
| 9 | An Ice Golem dying among troops | same outer-ring question | uniform freeze |
| 10 | A P.E.K.K.A (or any melee troop) reaching a building | arrival -> first hit | first hit on arrival |
| 11 | Holding a troop slot to drag a line of troops | time between each troop appearing | 0.15 s per troop (assumed) |
| 12 | A Battle Blimp reaching the Town Hall | where exactly it breaks, death blast | over TH centre, no death blast |
| 13 | A Firespitter ball passing through troops | how far past its target it reaches | 2 tiles |
| 14 | Earthquake Boots activation | activation -> first hit | instant |
| 15 | A Druid healing a group | how many units each heal chain reaches | 4 |
| 16 | A Wall Breaker blowing a wall next to a building | does the building take damage too | no |

Clips can come from your own attacks, your defense replays, or friendly
challenges. Name each file with its number (e.g. `06-scattershot.mp4`).
