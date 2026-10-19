# Attack playbook extraction (from video transcripts)

Rule from the user (2026-10-18): every attack the simulator plays must come from how real players describe attacking with that army. Nothing made up.

## Input

`output/sources/transcripts/<VIDEO_ID>.json` holds the title, channel, description and `lines`, a list of `[seconds, text]` caption lines. Most captions are auto-generated, so names get garbled ("valkyy's", "route riders"). Correct a name only when the intended name is certain.

## Output

Write exactly one JSON object, nothing else:

```json
{
  "video_id": "...",
  "relevant": true,
  "not_relevant_reason": null,
  "army_family": "root-rider | thrower | dragon | electro-dragon | super-bowler | yeti | lavaloon | meteor-golem | druid-ruin-witch | super-minion-air | other",
  "town_hall": 16,
  "army": {"troops": {}, "spells": {}, "cc": {}, "heroes": {"Royal Champion": ["Rocket Spear", "Electro Boots", "pet"]}, "stated": true},
  "base_reading": [{"rule": "how to choose the side or charge path", "quote": "...", "t": 45}],
  "steps": [
    {
      "n": 1,
      "phase": "charge | funnel | main | follow_up | cleanup",
      "action": "deploy | spell | ability | recall | wait",
      "what": "Royal Champion",
      "count": 1,
      "where": "corner of the charge side, where no long-range defense covers her",
      "side": "charge_side | opposite_flank | main_side | middle | any",
      "when": "start of the attack",
      "target": "corner defenses",
      "why": "removes the corner and starts the funnel",
      "quote": "short exact phrase from the transcript, 15 words or fewer",
      "t": 49
    }
  ],
  "rules": [{"if": "the Root Riders start to split", "then": "Overgrowth the buildings that pull them", "quote": "...", "t": 300}],
  "spell_policy": [{"spell": "Invisibility Spell", "how": "every 4 seconds on the charging Champion and Warden", "quote": "...", "t": 63}],
  "ability_policy": [{"hero": "Grand Warden", "how": "Eternal Tome when the push reaches the Town Hall", "quote": "...", "t": 120}],
  "uncertain": ["anything said ambiguously, or visible on screen but not spoken"]
}
```

## Rules

1. Only record what the transcript says, or what the description says for the army composition. Never add a step a typical player "would" do. If the speaker shows something without describing it, leave it out or put it under `uncertain`.
2. Every step, rule and policy needs a `quote` copied exactly from the transcript (15 words or fewer) and the caption time `t` in seconds.
3. Keep the speaker's order. When a video contains several attacks, record the shared plan once, and add the per-attack differences as `rules` (for example "on this base he charged the Queen instead").
4. If the video is not a how-to for one army (for example a base showcase or a news video), set `relevant` to false with a reason and leave the lists empty.
5. Use the in-game names: Root Rider, Valkyrie, Healer, Royal Champion, Grand Warden, Archer Queen, Barbarian King, Minion Prince, Dragon Duke, Siege Barracks, Invisibility Spell, Recall Spell, Overgrowth Spell, Totem Spell, and so on.
