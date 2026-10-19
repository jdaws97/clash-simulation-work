# Consolidating playbooks into one executable playbook per army family

Input: every `output/sources/playbooks/<VIDEO_ID>.json` with `"relevant": true` and the given `army_family`. Each is a quote-checked extraction of one video (see docs/playbook-extraction.md). The matching transcripts are in `output/sources/transcripts/<VIDEO_ID>.json`.

Output: one JSON object, the playbook the simulator plays (`src/baselab/engine/playbook.py`). Write it in this exact shape:

```json
{
  "family": "root-rider",
  "name": "short name of the dominant plan",
  "sources": ["VIDEO_ID", "..."],
  "army": {"troops": {"Root Rider": 4}, "spells": {"Invisibility Spell": 5}, "cc": {"Siege Barracks": 1, "Rage Spell": 1},
           "heroes": ["Royal Champion", "Grand Warden", "Archer Queen", "Dragon Duke"],
           "loadouts": {"Royal Champion": ["Rocket Spear", "Electro Boots", "Spirit Fox"]}},
  "base_reading": [{"rule": "...", "support": 3, "cite": [{"video": "ID", "t": 49, "quote": "exact words"}]}],
  "steps": [
    {"id": "rc", "action": "deploy", "what": "Royal Champion", "count": 1, "at": "edge:charge", "group": "charge",
     "when": {"t": 0.5}, "support": 9, "cite": [{"video": "ID", "t": 49, "quote": "exact words"}]}
  ],
  "variants": [{"name": "...", "replaces": ["step ids"], "steps": [], "support": 2, "cite": []}],
  "notes": ["anything ambiguous or contested across videos"]
}
```

## Step vocabulary (the executor understands only these)

- `action`: `deploy` | `spell` | `ability` | `recall` | `redeploy` | `release_siege`
- `what`: an in-game name (unit, hero, siege machine or spell).
- `count`: a number, or `"all"`.
- `group`: `charge`, `funnel`, `main` or `duke` (any short label). Triggers and anchors refer to groups.
- `at` (where):
  - `edge:main`: the side the main army enters.
  - `edge:charge`: the flank the hero charge opens.
  - `edge:funnel`: the other flank.
  - `edge:left`, `edge:right`: flanks of the main side.
  - `unit:<Name>`: where that attacking unit is.
  - `unit_ahead:<Name>`: 2 tiles ahead of it toward its target (spells on a walking hero).
  - `group:<g>`: centre of a group.
  - `th`: the Town Hall.
  - `threat:<g>`: the most dangerous defense firing at group g.
  - `defenders:<g>`: enemy Clan Castle troops or heroes fighting group g.
  - `building:<key>`: nearest building of that key, e.g. `building:inferno`, `building:mono`, `building:eagle`, `building:scatter`, `building:xbow`, `building:ad`.
- `when` (trigger):
  - `{"t": seconds}`
  - `{"after": "step id", "delay": seconds}`
  - `{"inside": "<Name>"}`: that unit is well inside the base.
  - `{"group_inside": "<g>"}`
  - `{"near_th": "<g>", "r": tiles}`
  - `{"heavy_fire": "<Name>"}`: it is losing health fast or a heavy defense locks on.
  - `{"hp_below": "<Name>", "frac": 0.4}`
  - `{"spells_left": "<Spell Name>", "n": 0}`
  - `{"dead": "<Name>"}`
  - `{"defenders_near": "<g>"}`
  - `{"destruction": percent}`
  - `{"all": [...]}`, `{"any": [...]}`
- Repeats: `"every": seconds` plus `"until": trigger` (for example Invisibility every 4 seconds until none are left).

## Rules

1. Only use steps, rules and timings that the source playbooks contain. Every step and rule needs at least one `cite` copied from a source playbook (video id, its `verified_t` or `t`, and its exact `quote`). Do not paraphrase quotes.
2. `support` is the number of distinct videos that describe that step. Order steps the way most videos order them. Put minority plans in `variants`.
3. Translate the narration into the vocabulary as literally as possible. When the narration is vaguer than the vocabulary (for example "after the funnel is made"), pick the closest trigger and say so in `notes`. Never invent a number. If a delay is needed and none is stated, use `{"after": ..., "delay": 0}` and note it.
4. The army is the most common composition among the sources. If compositions differ a lot, choose the one used by most sources, and list the others in `notes`.
5. Reply with only the JSON object.
