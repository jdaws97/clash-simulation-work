# Completing a family playbook: the units it never deploys

The consolidated playbooks in `data/source/playbooks/<family>.json` mostly narrate
the clever parts of an attack (a hero charge, an ability, a recall). Many
army units have no step at all, so the simulator falls back to an uncited
dump. Your job: find, in the source transcripts, how players actually use
those units, and write steps for them in the executor vocabulary.

## Input

- The playbook: `data/source/playbooks/<FAMILY>.json` (its `steps`, `army`, `sources`).
- The units to cover (given in the prompt).
- Transcripts: `local/sources/transcripts/<VIDEO_ID>.json`, field `lines`
  is a list of `[seconds, text]`. Read the transcripts listed in the
  playbook's `sources` first; you may also read the per-video extractions
  `local/sources/playbooks/<VIDEO_ID>.json`.

## Output

Reply with only one JSON object:

```json
{
  "family": "super-minion-air",
  "add_steps": [
    {"id": "healers_warden", "action": "deploy", "what": "Healer", "count": 4,
     "at": "unit:Grand Warden", "group": "charge", "when": {"after": "warden", "delay": 2},
     "support": 3,
     "cite": [{"video": "ID", "t": 213.4, "quote": "exact words from one transcript line"}]}
  ],
  "uncovered": [{"what": "Goblin", "why": "no transcript says how it is used"}],
  "notes": ["anything contested between videos"]
}
```

- `id` must not clash with the playbook's existing step ids. `when` may
  refer to existing step ids.
- Use only the vocabulary in docs/playbook-consolidation.md ("Step
  vocabulary"). `at: "building:<key>"` targets the nearest live building of
  that key. Keys: `ad` Air Defense, `at` Archer Tower, `bt` Bomb Tower,
  `cannon`, `mortar`, `wt` Wizard Tower, `tesla` Hidden Tesla, `sweeper`
  Air Sweeper, `xbow`, `inferno`, `eagle`, `scatter`, `mat` Multi-Archer
  Tower, `ric` Ricochet Cannon, `mono` Monolith, `st` Spell Tower,
  `crafting` Crafted Defense, `cc` Clan Castle, `th` Town Hall.
- A step may set `"spread": tiles` (how widely the group is dropped around
  its anchor, default 1) when a transcript describes a line or a wide drop.
- `count` may be smaller than the army's total; several steps may deploy the
  same unit (e.g. "two rocket balloons on the mortar, two on the bomb
  tower" is two steps of 2).

## Rules

1. Every step needs at least one `cite` whose `quote` is copied exactly
   (a contiguous run of words) from one transcript line, with that line's
   time. The quote must describe this use of this unit. No paraphrase.
2. Do not invent. If no transcript says how a unit is used, list it under
   `uncovered` instead of guessing.
3. Prefer what most sources do (set `support` to the number of videos that
   describe it).
4. Do not change existing steps; only add.
