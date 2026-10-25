# M2 icon library

Each `Name--variant.txt` contains 960 decimal RGB bytes: a 16×20 portrait
feature, sampled from x=10–90%, y=20–80% of its saved card crop. Counts, level
badges and most borders lie outside this region. Files are about 3–4 KiB each;
no full replay frames or source images are stored here. Several variants cover
skins, dimmed cards and scales. Matching uses mean absolute RGB distance per
channel, grouped by semantic name. Distance must be at most 0.13 and the next
name must be at least 0.012 worse. Confidence is a similarity score, not a
probability. Mixed, occluded, shifted and absent portraits can remain unknown.

`reviewed-clusters.tsv` records manually viewed original contact-sheet clusters;
`reviewed-extra.tsv` records separately viewed M2 phone crops. The full cluster
membership, representative manifest and development audit are in
`output/web-videos/icon-*.tsv`. Original wf fragment media was replaced during
its M2 extraction, so old wf cluster IDs 330–359 were excluded from training;
new phone crops were viewed separately. The classifier does not read metadata
titles at runtime. Titles helped cross-check semantic labels during development.

Important distinctions in this source batch include Super Bowler versus
Thrower, Apprentice Warden versus Electro Titan, Ruin Witch, Super Wall Breaker,
Super Barbarian, Minion Prince versus Dragon Duke, and Revive/Overgrowth spells.
The 40-icon audit is a development review used to correct labels, not a held-out
accuracy estimate. Five sampled crops cannot identify one complete portrait.
The remaining two abstentions are retained rather than guessed.

To rebuild with unchanged source crops, run `icon-learn output/web-videos`.
Re-clustering overwrites cluster IDs and the blank label manifest, so do it in a
separate output snapshot or preserve the reviewed manifest first. If videos are
re-extracted and overwrite numbered icon files, view and relabel those new
crops before relearning. `icons DIR` only classifies and does not retrain.

No web artwork was downloaded into this library. Semantic cross-checks used
Supercell's [Apprentice Warden announcement](https://supercell.com/en/games/clashofclans/blog/news/new-troop-1/),
[Super Bowler announcement](https://supercell.com/en/games/clashofclans/blog/news/superbowler-qols/),
and [June 2026 release notes](https://supercell.com/en/games/clashofclans/blog/release-notes/the-anime-fury-update-is-here/),
plus the supplied video pixels and queued-video titles.

## M3 additions

The active library has 341 feature files after M3. The added small RGB variants
come from manually inspected full-card geometry in the three M3 dev videos and
frozen review crops. `output/web-videos/m3-icon-labels.tsv` records native-source
rectangles; `m3-reviewed-icon-templates.tsv` records frozen source crops and
literal names. Native bootstrap frames are at 30s for each video and 48.2s for
n5-W8hHrRYs, stored temporarily under `/tmp/vidmine-work/m3` during learning.

Card matching also compares the old right-anchored geometry against complete
cards and abstains for gray portraits, weak similarity or conflicting alignment
results. The M3 name audit was used to add these variants, so its 55/55 named
identifiable crops is a development result, not held-out accuracy. Five sampled
portraits were left unidentifiable. The original M2 templates remain present.
