# Video attack tempo benchmark

These commands reduce existing mined HUD observations and compare them with the
unchanged v29 simulator. They do not acquire videos, rerun OCR, fit a calibration,
or modify source records. Generated reports belong in ignored
`local/evidence/video/tempo/`.

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-vt
export CLASH_CATALOG="$PWD/data/generated/catalog.json"
cargo build --release --offline --locked
"$CARGO_TARGET_DIR/release/clash" video tempo \
  --in local/web-videos \
  --out local/evidence/video/tempo/video.json
"$CARGO_TARGET_DIR/release/clash" fidelity tempo \
  --video local/evidence/video/tempo/video.json \
  --out local/evidence/video/tempo/comparison.json \
  --angles 3 --replicates 2 --threads 4
```

The video input is a directory of video subdirectories, or one video directory.
Each attack-NN.json is read once. Sped-up records are excluded first; otherwise
usable_for_timing must be true. Exclusions retain the source path and timing
status. An additional clock consistency check can exclude an otherwise usable
record. Malformed JSON is an explicit error.

The battle clock counts down from 180 seconds. Elapsed time is
`video_t + 180 - median(video_t + clock_t)`, using clock readings with confidence
at least 0.6. At least six readings and 70% of these confident readings must lie
within two seconds of that unit-speed anchor. A sample must be within one second
before, or three seconds after, the clock inlier span. This short extrapolation
handles the HUD clock snapping to zero at completion: zero is not automatically
a timeout. The existing usability annotation has already screened cuts, missing
clock coverage and non-unit playback speed. Clock-preserving edits can escape
both checks. The constant-rate anchor retains countdown quantization and is not
a subsecond ground-truth clock.

Every row includes video identity, attack index, estimated attacker TH, observed
league, identified army cards, first/last observed deployment, destruction at
15/30/45/60/90/120/150 seconds, first observed star times, interpolated times to
50%/90%, observed final destruction/stars, end flags and battle end time.
Attacker TH evidence is preserved: the miner's "best" is the minimum compatible
TH, not an exact identification. Unknowns remain null. Army names require
confidence at least 0.8. Levels remain null when the miner abstained. Counts
require an initial count attached to that identified card; initial-slot indices
are not joined to the different army-card indices.
The miner's confidence scores are template/OCR screening scores, not calibrated
probabilities of correctness.

Damage readings require confidence at least 0.7, corroboration of the same value
within one second, and a nondecreasing retained sequence. Linear interpolation
requires observations on both sides and a gap of at most three seconds.
An exact threshold-valued reading retains its observed timestamp; when earlier
readings are missing, that timestamp can be an upper bound on the true crossing.
Crossings already reached when observation begins are left-censored and null.
Values after battle completion or after the last accepted damage observation
are null; a finished triple is not filled forward as 100% at later checkpoints.
Thus each later checkpoint describes attacks still observable at that time.
Its denominator can differ substantially from earlier checkpoints.

Star and deployment events require confidence at least 0.6. Deployments require
a positive count delta. These are observed card actions, including spells.
Offscreen cards, heroes, unreadable counts and missing detections make video
deployment timing partial: the first detected deployment need not be the first
real deployment, and "still deploying" shares describe detected late actions.
They are not estimates of complete troop deployment schedules. The simulator
uses explicit deploy/spell events and consequently has much better coverage.
Hero abilities are not added to either deployment schedule.
Simulator completeness refers to that native event stream: spawned units and
CC cargo are not deploy events, and it does not locate a separate CC-button tap.

A trustworthy final requires either sustained 100% for at least 0.4 seconds
plus an observed third star, a settled result screen with damage confidence at
least 0.7 and consistent damage/stars, or a clock-consistent timeout with a
near-terminal damage reading and observed non-three-star result. A sustained
100% endpoint supplies the third-star time and battle end; an uncorroborated
third-star time is null. An observed result screen can establish the result
without locating battle end precisely; its end time stays null. Otherwise the
row retains its last accepted damage and star observations, with an unobserved
end and untrusted final. Raw miner final values are retained separately.
"Trustworthy" means these reproducible screening rules passed, not that a human
has independently verified every frame.

Final-result aggregates and three-star shares use trustworthy finals only.
All fields report n, missing count, median, first and third quartiles, and an
estimate: the median for measurements or the mean for shares. Quantiles use
linear interpolation at `p * (n - 1)`. Coverage includes verified triple counts
and worst-case lower/upper bounds across all included rows, allowing every
unresolved final to be either a failure or a triple.

The simulator command uses the existing fidelity plan preparation, r8 strength
selection, Scorer visible scouting, and native Job runner. It records selected
battles through the runner's summary hook and checks stars, destruction and
exact end-time bits against the original scouting evaluation. No new battle
runner or mechanics are introduced. Destroyed-building events reconstruct a
5 Hz HUD destruction stream by holding each value until the next event.
Deploy/spell events and destruction/TH events supply deployment and star times.
The same std-only measurement, quantile, censoring and bootstrap source is
compiled into both command adapters; the crates' JSON implementations and
dependency manifests remain unchanged.

Default settings are three candidate sides, two seed replicates, all five skill
quantiles per replicate, and visible scouting over the existing three hidden
samples. Full scouting chooses among all candidate sides without inspecting
the actual hidden defense. Only the pinned meta library is used, at each build's
own attacker TH; missing cited playbooks and unsupported content remain errors.
Each attacker/defender TH cell uses max(number of armies, number of bases)
cyclic pairings. This covers every army and every reference base with a bounded
run, rather than a complete crossing. Selected attack rows have equal weight;
this is not an estimate of the videos' army prevalence.

The ten ranked-2026-10-24 layouts declare defender TH16; the four
ranked-th18-2026-10-25 layouts declare TH18. Saved layouts and levels are used
unchanged, including their transcription and hidden-content assumptions.
Defender TH below attacker TH is omitted. Consequently the benchmark has TH16
attackers against TH16 and TH18 defenses, TH17 attackers against TH18 defenses,
and TH18 attackers against TH18 defenses. There is no TH17 reference cohort.
Unknown attacker TH and estimates below TH16 remain in the video aggregate
without being silently promoted to a supported attacker TH. Use --town-hall to
select one supported attacker cohort. --seeds is an alias for the replicate
default; --replicates takes precedence. Runs above 6,000 total native battles,
including planning and diagnostic replays, are rejected.

Comparisons show the same aggregates for each simulator TH cell, all videos,
and videos with the same minimum-compatible attacker TH estimate. Differences
are simulator minus video. The 90% intervals are percentile bootstrap intervals
from 1,000 deterministic, unpaired cluster draws, resampling entire video IDs
and entire reference base IDs. All skill quantiles, armies and seeds on a base
remain together. Intervals describe variation within this selected corpus and
small reference set; they do not resolve unknown TH, selection bias, censoring,
OCR error or simulator uncertainty. Four TH18 bases give limited independent
defense evidence. Input fingerprints and the video report SHA-256 are saved;
a run errors if its fingerprinted inputs change.

CONFIRMED from the initial full-corpus reduction: 470 records were read; 324
passed timing checks. Exclusions were 74 sped-up, 53 insufficient continuous
clock, seven other non-unit playback, six clock discontinuity/merged fragments,
five moving edited crops, and one additional unit-speed anchor failure.
There are 173 unknown attacker TH rows; minimum-compatible estimates are TH13:
one, TH14: eight, TH16: 90, TH17: 13, and TH18: 39. Only 81 included rows have
an observed league label. Titles/channel descriptions were not substituted for
missing HUD identities.

There are 189 trustworthy finals: 181 sustained triples and eight consistent
timeouts. The other 135 ends are unobserved under these rules. The verified-final
three-star share is 181/189 = 95.8%; across all 324 included rows the unresolved
finals permit a share from 55.9% to 97.5%. This wide identification range matters
more than an apparently precise binomial interval.

The video median destruction curve is 8%, 17.5%, 29%, 42%, 69%, 86%, 93% at the
seven checkpoints, with n = 294, 280, 280, 267, 253, 204, 49 respectively.
Median time to 50% is 69.2 seconds (n=263), time to 90% is 119.1 seconds (n=250),
and observed battle end is 130.4 seconds (n=189; quartiles 116.8/140.2).
The last detected deployment median is 99.8 seconds; 89.1% have detected actions
after 60 seconds and 62.8% after 90 seconds (n=304).

CONFIRMED in the completed simulator benchmark: 3,520 native battles comprised
2,880 hidden-state planning battles, 320 evaluations and 320 recorded diagnostic
replays. All recorded results matched their original evaluations, including
exact end-time bits. The run covered five TH16, four TH17 and thirteen TH18 meta
builds, all fourteen reference layouts, two seed replicates and all five skill
quantiles (64 comparison rows per quantile). The r8 SHA-256 was
`821a486f0e481d58070b61099d0e102a410c3d4b02471efe5c6d71ebb0d565b8`.
There are 182 video rows without a supported estimated attacker TH comparator.

| Cohort | Rows | Destruction at 15 s | At 60 s | Median end, s | Verified-final 3-star share |
| --- | ---: | ---: | ---: | ---: | ---: |
| All included videos | 324 | 8% | 42% | 130.4 (n=189) | 95.8% (n=189) |
| Video attacker estimate TH16 | 90 | 8% | 41% | 129.9 (n=56) | 98.2% (n=56) |
| Sim TH16 → defender TH16 | 100 | 10% | 58% | 120.8 | 64.0% |
| Sim TH16 → defender TH18 | 50 | 9% | 53% | 96.5 | 2.0% |
| Video attacker estimate TH17 | 13 | 7% | 46% | 122.9 (n=10) | 100% (n=10) |
| Sim TH17 → defender TH18 | 40 | 18% | 55.5% | 99.5 | 0% |
| Video attacker estimate TH18 | 39 | 5% | 22% | 140.0 (n=24) | 87.5% (n=24) |
| Sim TH18 → defender TH18 | 130 | 13% | 55% | 112.7 | 26.9% |

These are observed-data comparisons, not matched defenses. Checkpoint medians
also have their own denominators; the JSON records every n and quartile.
The following primary TH16 differences compare the TH16-versus-TH16 simulator
cell with videos whose minimum-compatible attacker estimate is TH16. Positive
destruction differences mean the sim has destroyed more at that elapsed time;
negative time differences mean it reached that milestone earlier.

| Measurement | Sim minus video | Bootstrap 90% interval |
| --- | ---: | ---: |
| Destruction at 15 s | +2 percentage points | −3 to +4 |
| Destruction at 30 s | +4 percentage points | −3.0 to +14 |
| Destruction at 45 s | +12 percentage points | +2 to +22.0 |
| Destruction at 60 s | +17 percentage points | +6.5 to +28 |
| Time to 50% | −14.5 s | −31.0 to −4.2 |
| Time to 90% | −24.8 s | −35.8 to −18.7 |
| Battle end | −9.2 s | −23.6 to +2.5 |
| Last deployment | −42.1 s | −54.9 to −29.4 |
| Verified-final 3-star share | −34.2 percentage points | −43.3 to −24.3 |

The TH16 sim is faster through the middle of the attack. Its destruction lead
first excludes zero at 45 seconds; the 15/30-second differences remain uncertain.
Median last deployment is 56.7 seconds versus 98.8 seconds in the TH16-estimate
videos. Only 36%/9% of these sim attacks deploy after 60/90 seconds, versus
86.0%/64.0% with detected late actions in those videos. Median observed end is
earlier in the sim, but its TH16 interval crosses zero. Median time to 90%
conditions on reaching 90%: 78 sim rows and 79 video rows contribute.

The native TH18 sim already leads its TH18-estimate videos at 15 seconds by
eight percentage points (90% interval +3 to +11), and at 60 seconds by 33 points
(+17 to +39.5). It ends 27.4 seconds earlier (−38.2 to −9.1), while its verified
three-star share is 60.6 points lower (−74.5 to −45.9). Its last-deployment median
is 62.6 seconds versus 128.0 seconds. These TH18 video figures have 39 timing
rows and only 24 trustworthy finals.

Earlier simulation ends often reflect failure: across all simulator cells,
192/320 attacks end with exhausted offense, 28 run to the timer with fighting
units alive, and 100 destroy all buildings. The cross-TH18 defender comparisons
are especially severe (one triple in 50 TH16 attacks, none in 40 TH17 attacks).
They must not be pooled with equal-TH defenses to infer a TH16 fidelity error.

SUSPECTED: the compressed action schedule and early destruction lead followed
by offense exhaustion suggest overly aggressive commitment and/or insufficient
surviving combat strength during cleanup. These are hypotheses for matched
replay experiments. This benchmark does not identify a specific movement,
damage, targeting, spell or calibration defect. The zero TH17 triple observation
and its degenerate empirical bootstrap interval do not prove triples impossible.

SUSPECTED mechanisms must be distinguished from these corpus measurements.
Public attack videos preferentially show good attacks, selected creators and
successful army styles; edited or sped-up exclusions can introduce further
bias. Defender TH, defensive levels, heroes, equipment, traps and CC contents
are not reliably known in the video rows. Many attacker identities are only
lower bounds. The game patch and actual army mixture need not match the pinned
catalog or meta library. Video OCR and incomplete deployment visibility remain
measurement error. These observations can identify model symptoms and guide
later matched replay work; they cannot by themselves isolate a causal mechanics
error or establish population three-star accuracy.

Validation completed with the locked offline release build/tests and strict
workspace Clippy through `scripts/verify.sh`, ending in `ALL CHECKS PASSED`.
`cargo fmt --all -- --check` also passed. The three frozen golden JSONL files
retained their original SHA-256 hashes. Two tiny declared-synthetic known-answer
tests cover interpolation/censoring/statistics and terminal clock-zero handling.
The full gate log is in `local/evidence/video/tempo/verify.log`; the compact
numeric extract is `local/evidence/video/tempo/summary.txt`.
