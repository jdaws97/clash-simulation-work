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
