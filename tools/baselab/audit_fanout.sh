#!/bin/bash
# Fan out deep mechanic audits to Codex, one session per game category.
# Each writes output/checks/audit-<category>.md. Findings are leads: every
# mismatch is verified against the wiki/game data before the engine changes.
# Usage: tools/baselab/audit_fanout.sh [PARALLEL] [category ...]
cd "$(dirname "$0")/../.."
PAR=${1:-7}
shift
declare -A SCOPE=(
 [troops-elixir]="every Elixir troop usable at TH16-18 (Barbarian, Archer, Giant, Goblin, Wall Breaker, Balloon, Wizard, Healer, Dragon, P.E.K.K.A, Baby Dragon, Miner, Electro Dragon, Yeti, Dragon Rider, Electro Titan, Root Rider, Thrower, plus any newer Elixir troop in the data)"
 [troops-dark]="every Dark Elixir troop (Minion, Hog Rider, Valkyrie, Golem, Witch, Lava Hound, Bowler, Ice Golem, Headhunter, Apprentice Warden, Druid, Furnace, Ruin Witch, plus newer) and their sub-units (Golemites, Lava Pups, Skeletons, Bear form, Firemites, Ruin Knights)"
 [troops-super]="every Super troop (Super Barbarian, Super Archer, Super Giant, Sneaky Goblin, Super Wall Breaker, Rocket Balloon, Super Wizard, Super Dragon, Inferno Dragon, Super Minion, Super Valkyrie, Super Witch, Ice Hound, Super Bowler, Super Miner, Super Hog Rider, Super Yeti) and seasonal troops in current rotation"
 [siege]="every Siege Machine (Wall Wrecker, Battle Blimp, Stone Slammer, Siege Barracks, Log Launcher, Flame Flinger, Battle Drill, Troop Launcher, Sky Wagon, plus newer), including Clan Castle troop release rules"
 [spells]="every attacking spell, Elixir and Dark (Lightning, Healing, Rage, Jump, Freeze, Clone, Invisibility, Recall, Revive, Totem, Overgrowth, Poison, Earthquake, Haste, Skeleton, Bat, Ice Block, plus newer), including stacking rules, housing, radius, duration, Clan Castle spells"
 [heroes]="the six heroes (Barbarian King, Archer Queen, Grand Warden incl. air/ground mode, Royal Champion, Minion Prince, Dragon Duke): base stats, targeting, abilities on attack, regeneration, behaviour on defense from the Hero Banner (territory, retreat), league modifiers, automatic ability on KO"
 [equipment-1]="every Hero Equipment for the Barbarian King and Archer Queen: active abilities and passive boosts, numbers per level"
 [equipment-2]="every Hero Equipment for the Grand Warden, Royal Champion, Minion Prince and Dragon Duke (incl. Portal Pendant and any newer): active abilities and passive boosts, numbers per level"
 [pets]="every Hero Pet (L.A.S.S.I, Electro Owl, Mighty Yak, Unicorn, Frosty, Diggy, Poison Lizard, Phoenix, Spirit Fox, Angry Jelly, Sneezy, Greedy Raven, plus newer): stats, targeting, abilities, summons"
 [defenses-1]="Cannon, Archer Tower, Mortar, Air Defense, Wizard Tower, Air Sweeper, Hidden Tesla, Bomb Tower, X-Bow, Builder's Hut (battle builders: repair and attack), Clan Castle (defending troop release radius)"
 [defenses-2]="Inferno Tower (single/multi), Eagle Artillery, Scattershot, Spell Tower (each spell mode), Monolith, Multi-Archer Tower, Ricochet Cannon, Multi-Gear Tower, Firespitter, Revenge Tower, Crafting Station modes, Town Hall weapons TH13-18 incl. Inferno Artillery and Guardians, and any newer defense"
 [traps]="every trap (Bomb, Spring Trap, Giant Bomb, Air Bomb, Seeking Air Mine, Skeleton Trap ground/air, Tornado Trap, Giga Bomb, plus newer): trigger radius, delay, damage, targets, interactions with heroes/sieges"
 [rules]="general battle rules: troop movement speed units, pathing around buildings and walls, wall-breaking choices, target selection and retargeting, deploy zones (red line, one tile around buildings and walls), destruction percentage and which buildings count, stars, the 3-minute timer and 30 s scouting, troops that ignore walls, flying units, Clan Castle defending troops (trigger, targeting), splash/friendly damage, attack speed vs damage per hit"
)
cats=("$@")
[ ${#cats[@]} -eq 0 ] && cats=("${!SCOPE[@]}")
mkdir -p output/checks
for c in "${cats[@]}"; do
  [ -s "output/checks/audit-$c.md" ] && continue
  cat > "output/checks/audit-$c.prompt" <<EOF
You are auditing a Clash of Clans battle simulator for accuracy. Repository: this one. Engine: src/baselab/engine/*.py, src/baselab/mechanics.py, src/baselab/loadouts.py; stat lookups go through src/baselab/engine/stats.py (data/registry.json). Ground truth, in order: the local Clash of Clans fandom wiki copy data/wiki/pages/<Page_Name>.json (field "wikitext", fetched 2026-10-15), then data/clashking-static-data.json (extracted game data; ranges/speeds in hundredths of tiles). You may also browse clashofclans.fandom.com for pages missing locally.

Scope: $( printf '%s' "${SCOPE[$c]}" ).

For EVERY entity in scope, list each mechanic the wiki states (behaviour, targeting, numbers per level, special abilities, timings, radii, interactions) and compare with what the engine actually does. Read the code; do not assume.

Output markdown:
1. A table per entity: mechanic | wiki says (exact quote, 25 words or fewer, + page) | engine does (file:line + short code excerpt) | verdict MATCH / MISMATCH / MISSING / UNSURE.
2. Then "## Fixes": for each MISMATCH or MISSING, a precise proposed change (file, function, what to change, the wiki numbers to use). Never invent a number; if the wiki gives none, say NUMBER NOT STATED.
3. Then "## Impact": rank the fixes by how much they would change TH16-18 ranked/war battle outcomes, citing how common the entity is.
Be exhaustive and precise. Mark anything you could not verify as UNSURE.
EOF
done
printf '%s\n' "${cats[@]}" | xargs -P "$PAR" -I{} bash -c '[ -s output/checks/audit-{}.md ] || { ~/bin/codex-ask "$(cat output/checks/audit-{}.prompt)" > output/checks/audit-{}.md.tmp 2>&1 && mv output/checks/audit-{}.md.tmp output/checks/audit-{}.md; echo "done {} $(wc -l < output/checks/audit-{}.md) lines"; }'
