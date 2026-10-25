# Template provenance and labels

These are binary glyph masks derived from the supplied `mnJOtLowhqs.mp4`.
They are video observations, not synthetic fixtures or game-engine calibration.
No whole video frame, name, loot/profile readout, or replay file is stored here.
All temporary source crops and contact sheets were kept under
`/tmp/vidmine-work/` and removed after review.

Format: decimal `width height`, then one line per row, `#` for foreground and
`.` for background. Numeric templates are normalized to 16×24. Labels retain
their native 720p dimensions. A filename such as `clock-4-b.txt` means family,
human-assigned character, and variant. The reader ignores this README.

The `bootstrap` command segmented white glyphs with vertical projections,
normalized them, and clustered masks whose differing-pixel fraction was below
0.115. The cluster sheets and source crops were viewed and labeled manually.

| Family | Source times / inspection | Cluster labels |
| --- | --- | --- |
| Clock | 12–21s, 90s, 136–146s, 149s | Clusters 0..11: `2`, `m`, `5`, `8`, `7`, `6`, `4`, `3`, `1`, `0`, `9`, alternate `4` |
| Damage | 10,20,…,150s, plus 152,155,160s | Clusters 0..13: `0`,`%`,`3`,`%`,`6`,`%`,`1`,`1`,`2`,`4`,`8`,`5`,`7`,`9` |
| Counts | Inspected bar at 10/18s, then dim cards and selected cards | Dedicated `0`–`5` and `x` variants; larger damage-font masks supply fallback `6`–`9` |

The clock clusterer sometimes grouped small `s` with `5`; numeric templates were
copied from actual digit examples. The reader removes the unit glyph according
to clock grammar and checks the wide `m` shape before parsing minutes.
Percentage punctuation is removed from a HUD-gated glyph run. It is not a digit.

The `learn-labels` manifest records the manually checked coordinates:

| Label | Source time | Source box |
| --- | --- | --- |
| `battle-label.txt` | 90s | `[590,15,102,12]` |
| `damage-label.txt` | 90s | `[998,460,130,12]` |
| `prep-label.txt` | 5s | `[582,15,118,12]` |
| `result-label.txt` | 154s | `[592,79,98,14]` |

At 18s the first-row cards visibly print `x2,x1,x3,x0,x1,x2`; the lower row
includes `x4`. These provided count variants at thresholds 95, 145 and 175.
The initial `x5` example came from the first-row healer card at 10s.
`count-x-<x>-<y>-<threshold>.txt` records the coordinates and threshold of an
inspected count-prefix variant, including a selected-card/background variant.

These masks fit the supplied game/font/video compression. Similar-looking
layouts at other scales, bright scenery, fades and card-selection animation can
still produce abstentions or incorrect readings. The retained batch spot checks
are the empirical quality evidence; similarity scores alone are not accuracy.

## M2 phone and moving replay observations

All new glyph masks were clustered from native source crops with
`bootstrap-box`, visually labeled in contact sheets under `/tmp/vidmine-work`,
and normalized with the same 16×24 method as M1. Non-digit clusters (M/s/% and
background fragments) were excluded. The timestamp-to-cluster logs are retained
in `output/web-videos/*-bootstrap.log`. These are inspected development examples,
not independent validation or engine calibration.

- HHRxAQs1egY clock: `[576,102,128,26]`, times 105–190 in ten-second steps
  (including 105 and 110), and 121–129. Phone digit templates contain all 0–9.
- HHRxAQs1egY damage: `[1155,516,81,22]`, times 120–190 in ten-second steps,
  213.4, 345.2, 569.6, 767.4, 804.4 and 960.8. All 0–9 are represented.
- wf5vDOJCnWM damage: `[1154,503,81,22]`, times 40,60,80,100,120,140,160,
  246.2,347.4,363.6,623.2,681.4,716.4,786.6,1057.8. The subscription graphic
  at 100s was excluded. Modern damage digits contain all 0–9.
- wf5vDOJCnWM clock: `[578,103,128,25]`, the ten audit times above (with 97.4
  and 321.8) and 37–46. All 0–9 are represented; extra scenery fragments and
  contaminated M glyphs were excluded. The actual 246.2s crop reads **1m46s**.
- `battle-phone-label`: HHR 180s `[592,86,98,12]`.
- `prep-phone-label`: HHR 90s `[584,86,114,12]`.
- `damage-phone-label`: HHR 180s `[1090,496,121,12]`.
- `damage-modern-label`: wf 90s `[1089,483,121,12]`.
- `replay-label`: 5InNp3cBzCA 360s `[577,646,130,17]`.

Label masks use threshold 145; bootstrap glyph sheets use 180. Clock reading
uses 175, with 195 and 215 as abstention fallbacks. The source videos are read
only. No replay frames or unnormalized card crops are embedded in the crate.
The separately labeled small RGB portrait features are documented in
[icons/README.md](icons/README.md).

## M3 level badges and QLeqlJlkJw8 clock

M3 adds 152 normalized level glyph variants, explicitly labeled from visible
card digits. Coordinates and literal strings are in
`output/web-videos/m3-template-labels.tsv`. Sources include the three supplied
M3 videos at 30s, preserved mnJOtLowhqs first-attack crops, and frozen reviewed
badge crops. A row with unsuitable segmentation at a particular threshold is
skipped; no generated font or inferred level cap supplies a glyph label.
Thresholds are 150, 180 and 210. Only tiny normalized masks enter this directory.
Full bootstrap frames and enlarged training sheets remain temporary.

For QLeqlJlkJw8 the native clock bootstrap box was `[574,96,139,27]`, viewed at
30, 100, 180, 330 and 500s. The reviewed clusters were `0=2, 1=M, 2=5, 3=8,
5=1, 6=4, 7=3`; unit S clusters were excluded. These become `clock-*-q-m3.txt`.
The uppercase M variant is recognized by template shape as well as the existing
wide-m grammar. `battle-q-label.txt` is 30s `[600,78,104,12]`;
`prep-q-label.txt` is 15s `[593,76,122,13]`.

Whole league-label masks are in `league/`. The inspected native sources are:

| Label | Existing output keyframe | Source rectangle |
| --- | --- | --- |
| Legend I | mnJOtLowhqs/attack-01-keyframe.jpg | `[603,71,73,19]` |
| Legend II | A6iUvh2FMGY/attack-01-keyframe.jpg | `[602,134,76,17]` |
| Legend III | aaZbYKIG0jQ/attack-01-keyframe.jpg | `[600,142,80,17]` |

Gold text uses a color mask; white text is supported as another template style.
These labels and glyphs are development observations, not synthetic fixtures,
held-out validation, or real-game engine calibration. The M3 report includes
visible-field errors and abstentions, including a missed soft Legend II label.
