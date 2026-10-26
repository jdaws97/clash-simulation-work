# vidmine M4

The video implementation is now the `clash-vidmine` workspace library. Run its
commands with `clash video ...` or the `vidmine` compatibility binary supplied by
`clash-cli`. Templates remain crate-local. The examples below retain the original
subcommand arguments.

A std-only Rust CLI for inspecting Clash of Clans video HUDs with the installed
`ffmpeg` and `ffprobe`. No Rust dependencies, Python, external OCR, model/tool
installation, or source-video downloads are needed. M1 templates and weak-HUD
rejection remain in place. This crate does not change or calibrate the v29 engine.

Build from the repository root in WSL:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/vidmine-target
cargo build -p clash-cli --bins --release --offline --manifest-path Cargo.toml
cargo test --offline --manifest-path crates/clash-vidmine/Cargo.toml
cargo fmt --check --manifest-path crates/clash-vidmine/Cargo.toml
VIDMINE=/tmp/vidmine-target/release/vidmine
```

## Video processing

```sh
"$VIDMINE" probe /path/to/video.mp4
"$VIDMINE" extract /path/to/video.mp4 --out local/web-videos/video-id
"$VIDMINE" positions /path/to/video.mp4 --out local/web-videos/video-id
"$VIDMINE" summary local/web-videos > local/evidence/web-videos/vidmine-summary.tsv
"$VIDMINE" verify local/web-videos
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
"$VIDMINE" resegment local/web-videos
"$VIDMINE" icons local/web-videos
"$VIDMINE" timing local/web-videos
"$VIDMINE" verify local/web-videos
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
"$VIDMINE" audit /path/to/video.mp4 --out local/web-videos/video-id
# View /tmp/vidmine-work/video-id-audit.png and fill *_truth in spot-check.tsv.
"$VIDMINE" score local/web-videos/video-id
"$VIDMINE" icon-audit local/web-videos
# View /tmp/vidmine-work/icon-audit.ppm; fill name_truth in icon-spot-check.tsv.
# Position sheets are under /tmp/vidmine-work/positions/video-id/page-*.ppm.
"$VIDMINE" score-positions local/web-videos/video-id
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
"$VIDMINE" icon-cluster local/web-videos
# View /tmp/vidmine-work/icons/page-*.ppm and label the generated clusters.
# icon-reviewed-groups.tsv: name<TAB>space-separated cluster IDs.
# icon-extra-labels.tsv: path<TAB>name for separately inspected crops.
"$VIDMINE" icon-learn local/web-videos
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
"$VIDMINE" identity local/web-videos
"$VIDMINE" identity-caps local/web-videos
# Sample six bar/league views in each existing attack interval.
"$VIDMINE" identity-video /path/to/video.mp4 --out local/web-videos/video-id
"$VIDMINE" summary local/web-videos > local/evidence/web-videos/vidmine-summary.tsv
"$VIDMINE" verify local/web-videos
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

The M3 pass leaves `defender_th` null with `defender_th_reason`. The optional M4
pass below can replace that abstention using a reviewed spatial reference and
the small scale-normalized sprite library. Run M4 after M3.

## M3 template development and review

```sh
"$VIDMINE" level-sheet local/web-videos/video-id
"$VIDMINE" army-sheet local/web-videos/video-id
"$VIDMINE" league-audit local/web-videos
"$VIDMINE" identity-learn local/evidence/web-videos/m3-template-labels.tsv
"$VIDMINE" card-learn local/evidence/web-videos/m3-icon-labels.tsv
"$VIDMINE" league-learn /tmp/vidmine-work/source.ppm Legend_I X Y W H
"$VIDMINE" identity-audit local/web-videos
# View /tmp/vidmine-work/m3/level-audit-*.ppm; explicitly write sample truths.
"$VIDMINE" identity-label-audit local/web-videos local/evidence/web-videos/m3-review-labels.tsv
"$VIDMINE" identity-freeze-audit local/web-videos
"$VIDMINE" identity-learn-audit local/web-videos
"$VIDMINE" identity-read-crops local/web-videos
"$VIDMINE" identity-score local/web-videos
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

## M4: camera, village grid, deployment candidates and defender sprites

Build with `CARGO_TARGET_DIR=/tmp/vidmine-target-m4`, offline. M4 reads existing
attack intervals; it does not download videos or change the v29 engine. Its
frames and review sheets stay under `/tmp/vidmine-work-m4`. No new full frames
are saved in the output directories. `spatial_keyframe` records the selected
preparation reference time, dimensions and RGB fingerprint. The original saved
`keyframe` and M3 evidence remain intact. Camera transforms and `grid_fit` refer
to **spatial_keyframe**, which may differ from that original JPEG.

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/vidmine-target-m4
cargo build -p clash-cli --bins --release --offline --manifest-path Cargo.toml
cargo test --offline --manifest-path crates/clash-vidmine/Cargo.toml
cargo fmt --check --manifest-path crates/clash-vidmine/Cargo.toml
VIDMINE=/tmp/vidmine-target-m4/release/vidmine

# OUT is the existing per-video output directory; VIDEO stays read-only.
"$VIDMINE" spatial-prepare "$VIDEO" --out "$OUT"
# Inspect the temporary key candidates and choose a preparation reference.
"$VIDMINE" spatial-spacing "$VIDEO" "$GRID_LABELS" > "$OUT/m4-spacing-review.tsv"
# Review the proposed wall spacing and fit the boundary origin before running.
"$VIDMINE" spatial "$VIDEO" --out "$OUT" --labels "$GRID_LABELS"
"$VIDMINE" spatial-verify "$OUT"
"$VIDMINE" spatial-summary "$OUTPUT_ROOT" > "$OUTPUT_ROOT/m4-summary.tsv"
"$VIDMINE" spatial-score "$OUTPUT_ROOT" "$DEPLOYMENT_TRUTH" "$OUTPUT_ROOT"
"$VIDMINE" spatial-score-th "$OUTPUT_ROOT" "$TH_TRUTH" "$OUTPUT_ROOT"
"$VIDMINE" cleanup-m4
```

Grid labels are tab-separated, with a header and one row per attack:
`attack video_t cx top a b wall_pairs`. The last field is optional. The projection
is `screen_x=cx+(x-y)*a`, `screen_y=top+(x+y)*b`, over 44×44 tiles, with x down-right
and y down-left. Tile positions are continuous and never clamped to the village;
units can appear outside its boundary. `spatial-spacing` finds compact yellow
wall-cap components and the dominant diagonal displacement between neighboring
caps. Its pair count is a diagnostic, not proof that every component is a wall.
It abstains with insufficient support. It preserves the initial projected map
center when proposing a new scale. Inspect the result before adopting it.

The origin is fitted manually from the visible boundary and scenery. Clipped
corners require extrapolation. This is a **provisional grid fit**, not an
independently verified absolute tile origin. The least-squares landmark fitter
and forward/inverse projection are available in `grid.rs`; parameter manifests
do not invent observed landmarks or a zero residual. Their landmark RMS is null.

The camera pass tracks textured patches inside the village, excludes the HUD
and preparation buttons, matches patches through an averaged image pyramid,
fits scale and translation with deterministic pair consensus, and refines the
inliers with least squares. One-second preparation samples bridge initial zooms;
battle samples occur every two seconds plus the event brackets. Adjacent fits
are composed back to the reference. A direct reference search attempts recovery
after tracking loss. Saved samples include actual correspondences, reference
times, inlier counts, photometric error and residuals. They have no interpolated
trajectory. A good residual does not independently certify camera accuracy;
composition can drift, repeated roofs can match incorrectly, and battle damage
can leave insufficient static evidence.

Each event is examined at -0.65 and +0.15 seconds. A separate local camera fit
registers the two frames, so a lost reference track need not erase screen
proposals. Color novelty in a small neighborhood suppresses ordinary sprite
motion and revealed ground. Changed components are ranked with color cues and,
for known troops, a village-edge prior. Up to five alternatives are retained.
Unknown identities receive no troop-only edge prior. This does not read a touch
coordinate or reliably distinguish a new unit from combat effects. Multiple
consumed units retain one group proposal and unassociated alternatives;
`individual_unit_positions_resolved` remains false. A failed local fit yields
no position; a failed reference fit yields screen-only proposals with null tiles.
All proposals remain `accepted: false`.

The sprite library contains ten manually reviewed 20×28 RGB features: two TH16,
two TH17 and six TH18 examples. See
[templates/townhalls/README.md](templates/townhalls/README.md). Features are sampled
in fitted tile units. A full reference-frame search combines color difference
and normalized correlation, refines spatially separated candidates at nearby
scales, and abstains on weak matches or a small inter-class margin. It supports
only TH16–18. Its scores are not probabilities. Lower THs, different skins,
obscured roofs and unfamiliar renderings can fail. No video title supplies a
prediction. Template membership is separate from validation membership.
The error cutoff 0.22 and margin cutoff 0.008 were selected during development
using the inspected references; non-template measurements are still not held out.

Deployment truth has columns `video attack event x_truth y_truth visible note`,
with explicit tab separators. `yes` requires an identifiable sprite/group/effect
center in the +0.15s frame, `ambiguous` excludes an unidentifiable appearance,
`no_event` records a separately reviewed upstream event problem, and blank or
`unlabeled` means no truth. Null predictions on visible labels count as errors.
Pixel and conditional tile thresholds use **all visible labels** as their
denominator. Means and medians describe only available predictions; missing
counts are reported alongside them. Tile error reprojects the manual pixel
center through the same fitted grid and camera. It measures conditional
localization error, **not independent absolute tile accuracy**. Sprite elevation,
movement since the touch, grouped units and the manual center uncertainty remain
unmodeled.

TH truth has columns `video attack th_truth training note`. `na` excludes a roof
that cannot be identified. Template-source keyframes are reported separately as
resubstitution. Other labeled keyframes are development measurements; template
and parameter selection were informed by this review. TH16 and TH17 library
examples do not establish held-out accuracy for those classes.

`spatial --preview` writes a temporary pending result beneath the fixed scratch
root while reading the existing output tree. `--attack N` limits a diagnostic
run. Review helpers include `spatial-keyframes VIDEO GRID_LABELS`,
`spatial-camera-check VIDEO KEY_TIME FRAME_TIME`, and `spatial-saved-review ROOT`.
After a reviewed spacing correction, `spatial-refresh VIDEO OUT GRID_LABELS`
updates grid/TH evidence without changing the reference time or trajectory;
then `spatial-reposition VIDEO OUT REGIONS_JSON` remaps event proposals. The
latter can also rerun local appearance detection without rebuilding every camera
sample. `spatial-verify ANALYSIS_ROOT ORIGINAL_ROOT` additionally checks that M4
preserved the original HUD, army, timing, keyframe and event fields.

M2 `positions` and M3 `identity` can replace spatial/defender fields. Re-run M4
when applying those older passes afterward. Synthetic tests cover projection,
wall pitch, image registration with fixed HUD content, transformed appearance
changes, scoring abstentions and malformed truth. They are not real-game
calibration. The output report records the separate hand-check measurements and
limitations; this milestone does not establish reliable automatic deployment
reconstruction.
