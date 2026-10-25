# vidmine M3

A std-only Rust CLI for inspecting Clash of Clans video HUDs with the installed
`ffmpeg` and `ffprobe`. No Rust dependencies, Python, external OCR, model/tool
installation, or source-video downloads are needed. M1 templates and weak-HUD
rejection remain in place. This crate does not change or calibrate the v29 engine.

Build from the repository root in WSL:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/vidmine-target
cargo build --release --offline --manifest-path rust/vidmine/Cargo.toml
cargo test --offline --manifest-path rust/vidmine/Cargo.toml
cargo fmt --check --manifest-path rust/vidmine/Cargo.toml
VIDMINE=/tmp/vidmine-target/release/vidmine
```

## Video processing

```sh
"$VIDMINE" probe /path/to/video.mp4
"$VIDMINE" extract /path/to/video.mp4 --out output/web-videos/video-id
"$VIDMINE" positions /path/to/video.mp4 --out output/web-videos/video-id
"$VIDMINE" summary output/web-videos > output/web-videos/vidmine-summary.tsv
"$VIDMINE" verify output/web-videos
"$VIDMINE" cleanup
```

Probe independently searches clock and damage labels at 19 relative scales
(0.55–1.45, additionally scaled by source height) and several timestamps. A
shortlist of coarse matches is refined at individual pixels. Label variants
cover the tablet and newly inspected phone rasterizations. The minimum joint
label score stays 0.62: unsupported layouts still fail explicitly. Detection of
a label does not certify every card or an obscured field. The dev videos cover
two phone renderings and an edited moving replay crop; the other unavailable
failed M1 videos have not been validated.

`regions.json` records source dimensions, measured black-column bounds, layout,
matched template filenames, label confidence and HUD rectangles. Rectangle
format is `[x,y,width,height]` in source pixels. `phone_single_row` searches one
bar row; `tablet_two_rows` searches both. Count anchors are discovered in several
vertical windows, and missing portrait positions in phone card gaps are saved
as icon-only slots. A scrolled bar can produce a partial or mixed crop. Its
identity remains unknown when matching is weak or ambiguous.

Normal extraction streams packed RGB clock, damage and bar panels at 5 fps.
Clock OCR first uses the M1 threshold, then tries higher thresholds on an
abstention to reject bright background fragments. Glyph templates are normalized
16×24 binary masks. Count decreases still require a confirming sample and obey
initial inventory; increases, cuts and long unreadable count gaps break event
continuity. Raw OCR values, confidence and nulls remain available without
monotone interpolation. New extractions automatically add icon names and timing
annotations after writing their attack files. M3 then samples the army bar and
league region and adds Town Hall evidence.

A separate cropped-replay fallback searches the moving `Replay ends in:` label.
Its threshold is 0.72 during probe and 0.70 during tracking. It decodes full RGB
frames in memory at 1 fps, tracks local motion and scale, and reacquires in the
lower half of the frame when necessary. It never fabricates the absent troop
bar, counts, damage, stars or deployment events. Clock resets and long gaps
produce provisional replay intervals. Animated cropping can hide entire battle
boundaries, so these intervals explicitly remain unusable for timing.

One JPEG keyframe per attack, saved slot PPMs, and M3 sampled card PPMs persist in
the requested output directory. Development frames, sheets and crops go exclusively
under `/tmp/vidmine-work`; `cleanup` removes that fixed directory. Source videos
remain read-only. Keep this crate's build-time source directory and templates
available when running the compiled binary.

## Segmentation and timing

An attack tolerates HUD occlusion for up to 60 seconds. Stable preparation and
confirmed upward clock resets separate battles. The reset comparison uses a
recent median, preventing a brief wrong clock glyph from creating a new attack.
This addresses M1's two-second HUD-gap fragmentation. It cannot prove continuity
through a long scene with no HUD; review merged intervals when timing matters.

Eight-second windows estimate clock seconds per video second with the median
of separated clock-pair slopes. Windows require six readings across at least
three seconds and median residual at most 1.2 clock seconds. Rates above 1.25
are marked sped up, below 0.75 slowed, and below 0.25 paused. `playback_speed` is
the median of accepted window rates, so an overall value of 1 can coexist with
a short sped-up tail. `speed_segments` records the actual windows.

Clock discontinuities compare local speed-adjusted clock intercepts, rather
than assuming real-time playback. Completion clock resets near 100% are excluded
from cut detection. `edited` is true for a detected cut, a non-unit speed, or an
explicitly cropped replay. `usable_for_timing` additionally requires adequate
clock coverage and no readable-clock gap over three seconds. An occluded attack
can therefore be unedited but unusable for timing. Clock-preserving splices,
very short changes and some reset/overlay cases remain undetectable. Speed and
camera fit scores are measurements, not calibrated probabilities.

## Updates without source video

```sh
"$VIDMINE" resegment output/web-videos
"$VIDMINE" icons output/web-videos
"$VIDMINE" timing output/web-videos
"$VIDMINE" verify output/web-videos
```

`resegment` reads `readings.jsonl`, reconstructs intervals and count events,
renumbers attack JSON, records source fragment IDs, and updates `attacks.tsv`
and `run.json`. It reuses existing keyframe/icon paths without rewriting media.
It removes obsolete attack JSON after merging; old media may remain for
provenance. Cropped replay directories are skipped. This rebuild invalidates
previous per-event position annotations; run it before `positions` if video is
available. Original observation streams remain intact.

`icons` classifies each JSON-referenced saved crop against the small labeled RGB
portrait templates in [templates/icons](templates/icons/README.md). Slots gain
`name`, `name_confidence`, `name_method`, and the attack gains a library version.
Deployment events inherit their slot name. Null means unknown, including mixed,
shifted, occluded and missing portraits. Hero skins do not change the semantic
hero name. Slots with `count_box: null` have no count event stream.

`timing` updates flags and rates and writes `timing-summary.tsv` plus
`speed-segments.tsv`. `verify` parses every attack JSON, checks media references,
event intervals, deltas and initial inventories, and writes
`m2-validation.json` and `m2-artifact-summary.tsv`. These checks do not establish
semantic accuracy. `summary` retains the first 13 M1 columns and appends M3 fields.

## Deployment screen positions

`positions` seeks two native-resolution observations per count event, at -0.4
and +0.1 video seconds. It estimates a uniform camera scale and translation
using coarse-to-fine registration of stable image tiles, discarding high-error
tiles. It estimates both before-to-after and keyframe-to-after transforms. RGB
differencing in the aligned battlefield proposes up to three connected changed
regions. The fixed HUD and a conservative upper-right commentary mask are
excluded. Both appearances and departures can contribute; moving troops,
explosions and spell effects can dominate.

Each event gains `position.screen` in source pixels, ranked candidates, source
dimensions, burst timestamps, camera transforms, fit residuals, and
`accepted: false`. This is an **unverified appearance proposal**, not a touch or
certified unit location. The camera fit threshold only qualifies its image
registration residual; its real-video transform accuracy has not been measured.

The M1 keyframes have no reviewed grid origin or building-to-tile correspondences.
M2 records `grid_fit.status: unreliable` and `tile: null`, retaining screen
coordinates plus camera state rather than inventing absolute base tiles. Camera
zoom beyond the registration search range, large pans, scenery and combat can
invalidate a fit. Multiple units consumed in one count event have one proposal.
The M2 report quantifies the limited hand-checked screen accuracy; this output
is not suitable for automatic placement reconstruction yet.

## Reproducible reviews and template development

```sh
"$VIDMINE" audit /path/to/video.mp4 --out output/web-videos/video-id
# View /tmp/vidmine-work/video-id-audit.png and fill *_truth in spot-check.tsv.
"$VIDMINE" score output/web-videos/video-id
"$VIDMINE" icon-audit output/web-videos
# View /tmp/vidmine-work/icon-audit.ppm; fill name_truth in icon-spot-check.tsv.
# Position sheets are under /tmp/vidmine-work/positions/video-id/page-*.ppm.
"$VIDMINE" score-positions output/web-videos/video-id
```

HUD audit selects ten deterministic uniform times using FNV-1a(video ID) and an
LCG. It seeks those actual frames; cropped replays use integer times at their
1 fps cadence and recorded moving boxes. `na` truths exclude fields not visibly
displayed; null predictions on displayed fields count as errors. Invalid count
windows and hidden score HUDs must be reported separately from OCR accuracy.

The icon audit selects 40 deterministic saved crops, excluding original cluster
representative paths. Its seed is `0x7669646d696e6532`. This is a development
review, particularly when used to correct the catalog, not a held-out estimate.
Position accuracy uses Euclidean distance in source pixels, with a 48-pixel
threshold, and separately counts unidentifiable deployment appearances.
`position-check.tsv` includes blank manual truth fields. Re-running audit or
positions overwrites their blank tables; preserve completed labels first.

For this development pass, compact manual labels are retained in `m2-truth.tsv`,
`icon-truth.tsv` and `position-truth.tsv`. `label-hud DIR`, `label-icons DIR` and
`label-positions DIR` join those tables by their explicit keys and score them.
A blank truth is unlabeled; it never becomes a correct prediction by default.

```sh
"$VIDMINE" icon-cluster output/web-videos
# View /tmp/vidmine-work/icons/page-*.ppm and label the generated clusters.
# icon-reviewed-groups.tsv: name<TAB>space-separated cluster IDs.
# icon-extra-labels.tsv: path<TAB>name for separately inspected crops.
"$VIDMINE" icon-learn output/web-videos
"$VIDMINE" bootstrap-box /path/to/video.mp4 clock-phone 576 102 128 26 120 130
"$VIDMINE" label-crop /path/to/video.mp4 battle-phone-label 180 592 86 98 12
"$VIDMINE" sample /path/to/video.mp4 90 /tmp/vidmine-work/example.ppm
"$VIDMINE" cleanup
```

Re-clustering replaces the blank label manifest. Re-extracting a video can
replace numbered source crops and invalidate an old training manifest; view
new crops before learning them. The original M1 `bootstrap` and `learn-labels`
commands remain available. See [templates/README.md](templates/README.md) for
glyph provenance. Tests use declared synthetic data, not real-game calibration.

## M3: attacker levels, league labels and defender abstentions

```sh
# Reprocess all saved slots/cards and JPEG league regions without source video.
"$VIDMINE" identity output/web-videos
"$VIDMINE" identity-caps output/web-videos
# Sample six bar/league views in each existing attack interval.
"$VIDMINE" identity-video /path/to/video.mp4 --out output/web-videos/video-id
"$VIDMINE" summary output/web-videos > output/web-videos/vidmine-summary.tsv
"$VIDMINE" verify output/web-videos
```

Extraction invokes this pass automatically. The compiled crate needs its local
templates, `data/clashking-static-data.json` and `data/catalog.json`.
`m3-unit-caps.tsv` expands the static table
file into own-unit caps per TH, combining `required_townhall`, laboratory,
production-building, Hero Hall and Pet House requirements. Super units also
use the snapshot's `parentTroop`/`regularLevelRequired` availability metadata.
JSON records the
source fingerprint and catalog ceiling. This does not calibrate the v29 engine.

Every original slot gains `level: {value, confidence, raw, box, status, method}`.
The box is relative to its saved crop. The reader uses inspected 16×24 glyphs,
connected components, touching-digit splits and three brightness thresholds.
Complete runs take precedence over partial tokens. Narrow card borders and
ambiguous matches are rejected. Legacy windows can cut through the badge;
missing pixels are not reconstructed. `levels.tsv` records every saved-slot
attempt, including missing and ambiguous results.

Video runs also save `army_cards`: deduplicated observations with source boxes,
times, names, levels and donation-marker observations. These supplement the
original slots, whose deployment IDs stay intact. Six sampled views cannot
guarantee visibility of every scrolled card. Gray or weak portraits remain
unknown. No separate pet-card inventory is visibly present in these dev videos;
the data reader supports pet rules when identifiable pet slots exist.

A video-card level requires two independent sampled times before constraining
TH. Unconfirmed values remain in `observed_value`/`raw`. Conflicting values for
the same named unit and donation role are also withheld. Changed templates that
alter a saved reading require another video pass for confirmation. Legacy slots
have a single observation and weaker provenance.

`attacker_th` includes `min`, `max`, `best`, `consistent`, `status` and per-card
`evidence`. Its range intersects usable own-unit level/unlock constraints within
the local catalog's TH set. Known names without levels supply production
availability only. A level outside the table makes the result inconsistent; it
is never clamped. Shield-marked spells and potentially donated siege machines
do not impose the attacker's own upgrade/Workshop cap. Receiver Clan Castle
caps and special challenge rules are not modeled. Super availability is bounded
by the supplied parent-level metadata, whose snapshot is not live verification.

`best` is the smallest consistent TH with at least three distinct named level
constraints. It is a heuristic, not an exact identification or probability.
Underleveling permits higher THs: a maxed-looking TH16 army normally supports
`[16,18]` under this catalog. No reading is promoted to satisfy a video title.

`league: {label, confidence, status}` uses inspected whole-text masks under the
clock. Observed templates cover Legend I, II and III. Other text-like content
is unknown until labeled. Null plus `no_label_visible_*` means no displayed label
in the sampled region; the TSV renders it `none`. This does not distinguish war,
friendly, older ranked UI, or another mode. Similarity/absence scores are not
calibrated probabilities. `league_observations` preserves per-frame decisions.
Cropped replays explicitly leave the field unavailable.

`defender_th` remains null with `defender_th_reason`: the keyframes lack a
reviewed grid scale/origin and a labeled, scale-normalized TH sprite library.
No automatic sprite accuracy or TH18 confirmation is claimed.

## M3 template development and review

```sh
"$VIDMINE" level-sheet output/web-videos/video-id
"$VIDMINE" army-sheet output/web-videos/video-id
"$VIDMINE" league-audit output/web-videos
"$VIDMINE" identity-learn output/web-videos/m3-template-labels.tsv
"$VIDMINE" card-learn output/web-videos/m3-icon-labels.tsv
"$VIDMINE" league-learn /tmp/vidmine-work/source.ppm Legend_I X Y W H
"$VIDMINE" identity-audit output/web-videos
# View /tmp/vidmine-work/m3/level-audit-*.ppm; explicitly write sample truths.
"$VIDMINE" identity-label-audit output/web-videos output/web-videos/m3-review-labels.tsv
"$VIDMINE" identity-freeze-audit output/web-videos
"$VIDMINE" identity-learn-audit output/web-videos
"$VIDMINE" identity-read-crops output/web-videos
"$VIDMINE" identity-score output/web-videos
"$VIDMINE" cleanup
```

The deterministic development audit selects 12 army observations per video plus
12 accepted and 12 missing legacy reads. This stratification is not a random
coverage estimate. `na` excludes an unidentifiable field; blank means unlabeled;
a null prediction on a visible number is an error. Frozen small crops under
`m3-reviewed-crops/` retain inspected pixels when extraction renumbers cards.
`identity-read-crops` scores single-frame glyph/name predictions, before temporal
TH filtering. Do not join old keys to newly extracted numbered cards.
`identity-refresh-audit` is only for the unchanged source artifact generation.

The M3 truth and icon examples were used during development. The report separates
these measurements from held-out validation and per-attack TH certainty.
Recreating temporary source PPMs requires the caller's videos: use `sample VIDEO
30 /tmp/vidmine-work/m3/ID.ppm`, plus n5 at 48.2s. Manifests also reference preserved
M1 crops and frozen M3 review crops. Templates retain only small masks/RGB
features, never whole source frames.
