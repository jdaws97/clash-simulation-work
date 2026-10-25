# vidmine

A dependency-free Rust CLI for reading Clash of Clans video HUDs. It calls the
already installed `ffmpeg` and `ffprobe`; it does not download models, crates,
fonts, videos, or tools. It does not use Python or an external OCR program.

From the repository root in WSL:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/vidmine-target
cargo build --release --offline --manifest-path rust/vidmine/Cargo.toml
cargo test --offline --manifest-path rust/vidmine/Cargo.toml
cargo fmt --check --manifest-path rust/vidmine/Cargo.toml

VIDMINE=/tmp/vidmine-target/release/vidmine
"$VIDMINE" probe /path/to/video.mp4
"$VIDMINE" extract /path/to/video.mp4 --out output/web-videos/video-id/
"$VIDMINE" summary output/web-videos/
```

`probe` defaults to `output/web-videos/<video filename stem>/regions.json`.
An explicit `--out DIR` changes that destination. Rectangles use source pixels
and the order `[x, y, width, height]`. Content bounds come from black-column
detection, so pillarboxing is measured rather than assumed from the filename.
The compiled binary loads templates from this crate's build-time source path;
keep the crate and its templates available when using that binary.

## Processing and outputs

Probe searches upper-centre and right-side areas for thresholded label templates
at three scales. It samples 18 seconds and, if necessary, several fractions of
the duration. It refuses a weak label match instead of inventing regions.
The clock, percentage, stars, and bar boxes follow the matched HUD geometry.
This has been exercised on the five supplied 1280×720 videos. Other font scales,
languages, and phone layouts need further validation; region detection alone
does not establish that their troop-card layout is supported.

Extraction decodes once at 5 fps and packs RGB HUD crops into an image2pipe PPM
stream. RGB conversion precedes cropping to preserve odd pixel coordinates.
Neither full decoded frames nor time-series crops are written to the repository.
Only the requested keyframe JPEGs and one PPM icon per slot per attack persist.

White-pixel components are segmented into glyphs and normalized to 16×24 binary
masks. Classification uses labeled templates, shape distance, and the runner-up
margin. Clock grammar distinguishes `m` from a digit. Count reading tries
different thresholds and short vertical windows, accommodating dim printed
`x0`s and the movement of selected cards. Templates and the manual labeling
procedure are described in [templates/README.md](templates/README.md).

Each video directory contains:

| File | Meaning |
| --- | --- |
| `regions.json` | Measured source dimensions, content bounds, HUD boxes, label match |
| `readings.jsonl` | Every sampled frame, phase, raw OCR text/value/confidence, stars and counts |
| `readings.tsv` | Compact equivalent for inspection; count order is `slots.tsv` order |
| `slots.tsv` | Detected counted-card boxes and count windows |
| `attack-NN.json` | Attack interval, preparation start, clock/damage series, star/deployment events, cuts, slots, keyframe and result observations |
| `attack-NN-keyframe.jpg` | One early undamaged candidate, normally from preparation |
| `slots/attack-NN-slot-SS.ppm` | One icon per detected count slot, plus hero/siege portraits when the central layout is recognized |
| `attacks.tsv` | The per-attack summary consumed by `summary` |
| `run.json` | Frame count, attack count and elapsed extraction time |

Slot IDs are zero based, ordered by row then horizontal position. Hero/siege
portrait IDs follow counted slots and have `count_box: null`. They have icons
but no count/deployment stream. Unit names are deliberately unresolved.

Preparation uses the separate `Battle starts in:` label. Attacks require the
live HUD and a readable clock to begin, then persist through clock OCR gaps.
Results/preparation transitions and large resets to a new 3-minute battle split
attacks. A normal timer reset to zero on a completed triple is not an edit.
Cut detection compares robust `clock + video_time` estimates on both sides of a
candidate discontinuity. It needs about two seconds of readable clock on each
side. It cannot detect a splice that preserves the clock.

A deployment requires a decreasing count and agreement from a second sample.
A preparation/initial-sample mode supplies the initial count where available;
larger readings and later increases cannot become a deployment baseline.
Long unreadable gaps and detected cuts break event continuity. `delta`
is the positive number of units consumed, with both before/after counts kept.
Multiple units consumed between samples can form one event. An action at the
first observed attack sample, or a card never successfully detected, can be
missed. Event timestamps are observations at 0.2-second resolution, with video
sampling and integer clock rounding adding uncertainty. They are not touch
coordinates.

`initial_count` is stored with each counted slot. When an initial count is
available, accepted decreases cannot consume more than that inventory.
Legitimate recalls/refills and bar scrolling are not reconstructed by this
conservative rule; consult the raw stream for those cases. Selected-card border
strokes are filtered before digit parsing. These checks constrain implausible
events, but event precision and recall still need separately labeled action
intervals; ten random count readings per video do not measure event accuracy.

Clock and damage series preserve per-frame readings, including nulls and
occasional inconsistent values; they are not interpolated or silently forced
monotonic. Confidence measures template fit, not a calibrated probability.
Coverage and average confidence in the summaries are different from measured
spot-check accuracy.

The tool looks for result overlays in the five seconds after the live HUD ends.
`result_screen.settled` is false when the observed animation has not caught up
with the last live HUD. Final values use the larger of those observations, so
an animated `0%` does not overwrite a completed attack. A null result means no
accepted overlay observation, not that no result screen existed.

Hero ability use is unresolved: greying alone does not distinguish a used
ability from a dead hero. `hero_abilities` stays empty with an explicit reason.
Keyframe visibility needs human review; the batch report records that review
and any HUD occlusion. The extractor does not yet certify whole-base geometry.

## Reproducible spot checks

```sh
"$VIDMINE" audit /path/to/video.mp4 --out output/web-videos/video-id/
# Inspect /tmp/vidmine-work/video-id-audit.png.
# Fill the five *_truth columns in output/web-videos/video-id/spot-check.tsv.
# Use na for a field not displayed, e.g. damage during preparation.
"$VIDMINE" score output/web-videos/video-id/
"$VIDMINE" cleanup
```

Audit uses FNV-1a of the video ID as an LCG seed, chooses ten uniform timestamps,
sorts them, and displays full-frame thumbnails with enlarged clock/damage/star
and randomly chosen count-card crops. It reads the exact sought frames rather
than borrowing ground truth from the timeline. Re-running audit overwrites its
blank truth table, so preserve completed labels first. Score counts abstentions
as errors; `na` truths do not enter the denominator. The batch's labels and
scores are retained under `output/web-videos/`.

For template development only:

```sh
"$VIDMINE" bootstrap /path/to/mnJOtLowhqs.mp4 clock 12 13 14 15 16 17 18 19 20 21
"$VIDMINE" bootstrap /path/to/mnJOtLowhqs.mp4 damage 10 20 30 40 50 60 70 80 90 100 110 120 130 140 150
"$VIDMINE" sample /path/to/video.mp4 90 /tmp/vidmine-work/example.ppm
```

Bootstrap writes cluster masks and contact sheets only under
`/tmp/vidmine-work/bootstrap/`. Its development crop coordinates are for the
supplied 720p layout. Inspect the sheets, label clusters, and copy only small
glyph masks into `templates/`. `learn-labels` is the recorded coordinate manifest
for the manually inspected `mnJOtLowhqs` source, not automatic semantic labeling
of an arbitrary video. Delete development frames/crops after reviewing each
video, and finally remove `/tmp/vidmine-work`.

`cleanup` removes only the fixed `/tmp/vidmine-work` directory, including any
bootstrap and audit images. Extraction itself streams crops in memory.

The four Rust tests use explicitly synthetic sequences for segmentation,
clock-error rejection, deployment stability, cuts, and JSON escaping. They are
not real-game engine calibration. Keep real replay material and player data out
of Git; the batch did not stage or commit its output media.
