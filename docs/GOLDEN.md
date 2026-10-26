> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](README.md) for native commands and remaining Python ports.

# Rust golden regression suite

## HA2 — feasible army openings (2026-10-26)

This task intentionally changes automatic recipe selection, starting from
`7a67925`. The compiler tries complete default/declared/standalone source
recipes against actual actors, spell stock and equipped abilities before using
the historical repair path. `recipe_selection` records candidate verdicts,
the deterministic priority, the chosen recipe or `repaired_hybrid`, and zero
additional scouting battles. See the ignored [HA2 report](../local/ha2/report.md)
for evidence and paired results.

The plan oracle was intentionally regenerated with `clash golden plans record`
in public mode. Comparing every old row by its complete case and playbook mode:

- **855 unchanged old rows**.
- **499 selection-report-only changes**: removing `recipe_selection` makes each
  complete row identical to its old value. There are **zero executable-plan or
  rejection changes among the 1,354 existing rows**. These armies still need
  repair because the current authored recipes do not fully fit their stock.
- **Four new controls**: `dragon:variant:Rapid main-first Dragons` and
  `dragon:recipe:Rapid main-first Dragons`, each with playbooks off/on at the
  existing variant-control angle/seed. Generic controls compile unchanged;
  playbook controls reject the inherited test army because it carries Sky Wagon,
  whereas the cited new recipe requires Log Launcher. These rejection controls
  do not claim to execute the recorded attack. A separate declared synthetic
  compiler test exercises the admitted Dragon/Launcher/hero/reserved-Wizard path.

The new plan total is **1,358**. No battle fixture or expected battle trace was
changed: `cases.jsonl` remains SHA-256
`cea706d86516a2100876f9aa4ec7cdd5de32f691202f9a6d049b64e690d172ab`,
and `expected.jsonl` remains
`40446127d538f7bab2a86ab9c7fcae8b3a725c4ceb462fd2d95236cb38af0ab4`.
The old plan SHA-256 was
`60dbb24903bb2c0443abf4624e0231e5f33e083492fac571b187a830dcc47958`.
The new plan SHA-256 is
`169d8eee9b9c3a580ac69bbf9531365e1dc0a8a8b495673807bfc1b433703eed`.
Per-row comparison artifacts are in ignored `local/ha2/golden-differences.*`.

The original G1 oracle was the engine at `python-frozen`, commit
`d774e17498a2f753aa05a094db67e5d2d1cb89ac`. Python/Rust setup and trace parity
stages 1–9 passed 868/868 at that commit. G2 replaces platform C-runtime maths
with fixed musl algorithms in `crates/clash-engine/src/detmath.rs` and re-records the Rust
oracle in WSL. **Windows must now reproduce these expectations bit-exactly.**
Python is frozen and is no longer a parity target. This suite runs Rust alone;
it does not import Python, regenerate Python expectations, install crates, or
require the old parity checkout. There are no game-mechanics changes in G2.

PB1a subsequently accepts the intended mechanics/executor corrections documented
at the end of this file. The current expectations include those corrections.

These are **synthetic simulation regression scenarios**, including scenarios
using existing village geometry and army configurations. They are not real-game
calibration or recorded attacks. Personal layout names and descriptive notes
were removed; no profiles, replay media, memory captures, or credentials are
included.

## Run

The G1/G2 workspace relocation preserves all three golden files byte-for-byte.
Frozen SHA-256 values and before/after checks are recorded in
[RESTRUCTURE_LOG.md](RESTRUCTURE_LOG.md). Runtime catalog and rules paths remain
under `data/generated/`; pinned source inputs now live under `data/source/`.
The legacy `rust/` directory is removed. This relocation does
not authorize recording new expectations.

From the repository root in WSL:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-ws
export CLASH_CATALOG="$PWD/data/generated/catalog.json"
cargo build --workspace --all-targets --release --locked --offline --manifest-path Cargo.toml
/tmp/clash-target-ws/release/clash golden check fixtures/golden/cases.jsonl fixtures/golden/expected.jsonl --threads 16
/tmp/clash-target-ws/release/clash golden plans check fixtures/golden/plans.jsonl --root "$PWD"
scripts/verify.sh /tmp/clash-target-ws
```

Outside the checkout, use absolute fixture paths and pass an absolute `--root`
for plan checks. `CLASH_CATALOG` selects the catalog explicitly and takes
precedence over the supported legacy `BASELAB_CATALOG` name. The gate runs
both one-worker and four-worker battle checks against the same expected bytes,
then plan, guardian, armysearch, layout, M2 and video checks. The
`baselab-engine` compatibility binary accepts the same golden arguments.

On Windows, use the same arguments with `target/release/clash.exe`
after `cargo build --workspace --all-targets --release --locked --offline --manifest-path Cargo.toml`. Set
`CLASH_CATALOG` to the absolute path of `data/generated/catalog.json` if the binary
or target directory has moved. The engine remains std-only. The current G2
expectations were recorded and checked in WSL. Windows verification is pending
with the caller; a Windows mismatch must be investigated, not accepted as a
separate platform baseline. The G1 platform differences below are historical.

`--threads N` must be positive; its default is the available parallelism. Each
worker builds its own battle, RNG, and mutable plan through `setup::build`, the
same setup path used by `Runner::build`. Only the read-only catalog is shared.
Cases and reports always retain fixture order. Check returns exit status 0 on
success and nonzero on any mismatch, malformed input, or failed battle. Empty
files, duplicate IDs, and a changed expected ID list/order fail the check.

## What is frozen

`fixtures/golden/cases.jsonl` contains one self-contained object per line:

```json
{"id":"my-synthetic-case","synthetic":true,"layout":{},"plan":{},"options":{"seed":123,"town_hall":18}}
```

The empty objects above are placeholders for a valid prepared layout and plan.
`options` uses the existing job options accepted by `setup::build`. All data
needed apart from the tracked catalog is inline; there are no runtime paths to
the old exports, account files, army libraries, or other layouts.

The initial cases came from the last parity run's `jobs-S-K.json` files in
`clash-lab-parity/output/parity`. In numeric stage/case order, the selected
layout and plan were copied inline, job `layout`/`plan` indices were removed
from options, and layout `name`/`notes` were removed. Runtime fields, array and
object order, and numeric values were preserved. Stage sizes are:

| Stage | Cases |
| --- | ---: |
| 1 | 72 |
| 2 | 96 |
| 3 | 64 |
| 4 | 64 |
| 5 | 68 |
| 6 | 40 |
| 7 | 184 |
| 8 | 160 |
| 9 | 120 |
| Total | 868 |

Each corresponding `expected.jsonl` row has schema version 1 and records:

- Case ID and a fingerprint of the canonical fixture JSON, so fixture edits
  require explicit acceptance even if the result happens to stay the same.
- Stars; reported destruction as exact f64 bits; raw destruction as exact f64
  bits; result time as exact f64 bits; and the reason execution stopped.
- A 128-bit FNV-1a hash of every byte emitted by `trace::write_trace`, including
  LF line endings. This includes all tick markers, live unit position/HP bits,
  building/wall damage, logged events, and the final result line.
- A compact diagnostic stream: one 64-bit FNV-1a fingerprint per complete tick
  (`T` through its `U/B/W/E` lines), followed by one for the final `R` record.
  The u64 values are little endian, encoded as unpadded base64url.

FNV has fixed constants and wrapping arithmetic; it does not use Rust's
randomized hashers or platform byte order. Hashes are regression fingerprints,
not cryptographic signatures. The engine reports destruction as an integer
ceiling; `destruction_bits` stores that percentage converted to f64, while
`raw_destruction_bits` also preserves the unrounded ratio. Result time is the
engine's value rounded to 0.1 seconds, matching the parity `R` line, not the
unrounded tick clock.

End reasons reflect the existing trace loop: `plan_ended` for an explicit
ending, then `all_destroyed`, then `offense_finished`, otherwise `time_limit`.
This classification adds no stopping rule to the engine.

Failures list each changed scalar/hash field. For a changed trace, check
reruns that case with tracing, verifies that the rerun is deterministic, and
prints the first differing **per-tick trace event**, its expected/actual
fingerprints, and that tick's actual `T/U/B/W/E` lines (or the final `R`).
Compact expectations retain tick fingerprints, not old individual trace lines:
the report locates the first changed tick, not the first changed line within
that tick. Use the prior engine checkout with `trace-job` if old line text is
needed. No full trace files or diagnostic sidecars need to be committed.

## Accept an intended change

1. Run `golden check` against the existing expectations. Review the changed
   cases, fields, and first changed ticks. Fix unexpected changes first.
2. Record to a temporary file with the intended engine:

   ```sh
   /tmp/clash-target-ws/release/clash golden record fixtures/golden/cases.jsonl /tmp/expected-next.jsonl --threads 16
   /tmp/clash-target-ws/release/clash golden check fixtures/golden/cases.jsonl /tmp/expected-next.jsonl --threads 1
   /tmp/clash-target-ws/release/clash golden check fixtures/golden/cases.jsonl /tmp/expected-next.jsonl --threads 16
   cp /tmp/expected-next.jsonl fixtures/golden/expected.jsonl
   cargo fmt --manifest-path Cargo.toml --all -- --check
   ```

3. Commit the engine/fixture change together with the new expectations. Include
   a commit note listing **every changed case ID and why its change is intended**,
   along with the source/evidence for mechanics changes. A list of changed
   IDs alone is insufficient. Do not silently bless an unexplained new hash.

`golden record fixtures/golden/cases.jsonl fixtures/golden/expected.jsonl` also works
directly. Recording leaves an existing expected file alone if any battle fails;
it refuses to overwrite the case file itself.

## Add a Rust-only case

Create a declared synthetic layout and compile a plan entirely in Rust, for
example:

```sh
/tmp/clash-target-ws/release/clash compile meta:mass-dragons-18-1 0.0 123 /tmp/plan.json --root "$PWD"
```

Choose a build ID from the tracked army library (or pass a synthetic
build JSON file in place of the example ID). The compile command's output
is the prepared `plan` object, not a golden case or a raw army definition.
The golden case stores the completed output so later compiler/library changes
do not silently alter an existing battle fixture.

In PowerShell, combine an existing synthetic prepared layout, the compiled
plan, and explicit battle options into a new JSONL row without Python:

```powershell
.\rust\target\release\baselab-engine.exe compile meta:mass-dragons-18-1 0.0 123 plan.json --root $PWD.Path
$row = [ordered]@{
    id = 'rust-only-example-001'
    synthetic = $true
    layout = Get-Content -Raw synthetic-layout.json | ConvertFrom-Json
    plan = Get-Content -Raw plan.json | ConvertFrom-Json
    options = [ordered]@{ seed = 123; town_hall = 18 }
}
$line = $row | ConvertTo-Json -Depth 100 -Compress
$path = Join-Path $PWD 'fixtures/golden/cases.jsonl'
[System.IO.File]::AppendAllText($path, $line + "`n", [System.Text.UTF8Encoding]::new($false))
```

Use a unique descriptive ID, finite numbers, a legal prepared plan, and explicit
options for behavior the case needs to freeze. Keep new cases independent of
private account data and external files. Append cases in a documented stable
order, then review and accept the expected changes using the procedure above.
The existing unsupported-content checks remain active; do not bypass them to
make a fixture run.

## Initial validation

Recorded with the unchanged d774e17 simulation code, Rust 1.99.1,
`x86_64-unknown-linux-gnu` in WSL. The added harness changes only CLI wiring and
adds `golden.rs`; Python, mechanics, catalog, and existing trace code are unchanged.

| Operation | Cases | Threads | Engine wall seconds | Process wall seconds |
| --- | ---: | ---: | ---: | ---: |
| Record | 868 | 16 | 6.062 | 6.85 |
| Check, first run | 868 | 16 | 5.643 | 6.88 |
| Check, second run, same binary | 868 | 16 | 5.068 | 5.96 |
| Check | 868 | 1 | 44.833 | 47.00 |
| Re-record to temporary file | 868 | 1 | 44.347 | 47.39 |
| Check after reverting mutation, launched from `/tmp` | 868 | 16 | 5.116 | 6.01 |

Every check above passed 868/868. The 1-thread re-record was byte-for-byte
identical to the committed 16-thread recording. Initial fixture sizes are
11,447,681 bytes for cases and 8,769,350 bytes for expectations (20,217,031
bytes / 19.28 MiB combined). No split or external sidecar is needed.

The saved Python parity `R` lines were read directly with a temporary Rust
verification helper; no Python code was run or changed. Case 0 from every stage
matches stars, reported destruction, and exact result-time bits:

| Case | Stars | Destruction | Time bits |
| --- | ---: | ---: | --- |
| stage-1-case-0 | 0 | 43 | `404aa66666666666` |
| stage-2-case-0 | 0 | 40 | `404ed9999999999a` |
| stage-3-case-0 | 1 | 78 | `405b39999999999a` |
| stage-4-case-0 | 2 | 75 | `406269999999999a` |
| stage-5-case-0 | 1 | 62 | `4066800000000000` |
| stage-6-case-0 | 0 | 43 | `4053c66666666666` |
| stage-7-case-0 | 0 | 26 | `4050accccccccccd` |
| stage-8-case-0 | 2 | 83 | `4066800000000000` |
| stage-9-case-0 | 0 | 44 | `4066800000000000` |

A stronger comparison of **all** saved Python results and complete traces
found existing differences between this WSL engine and the saved Windows
Python/Rust traces. After CRLF-to-LF normalization, 385/868 trace hashes differ
(by stage: 20, 22, 53, 57, 39, 16, 22, 108, 48). Final stars/destruction/time
match in 866/868 cases. The two differing final results are:

| Case | Saved Windows Python/Rust | Current WSL Rust |
| --- | --- | --- |
| stage-4-case-8 | 2 stars, 78%, time bits `40608ccccccccccd` | 2 stars, 77%, time bits `4060666666666666` |
| stage-4-case-12 | 3 stars, 100%, time bits `4063c66666666666` | 3 stars, 100%, time bits `4062266666666666` |

Direct `trace-job` runs on the **original** exported jobs reproduce these
differences, independent of fixture packing or the golden runner. For example,
`jobs-1-6.json` first differs from its saved Rust/Python trace at trace line
7419, where Skeleton 55's x bits are `402d54666a95ce97` in WSL versus
`402d54666a95ce98` in the saved trace. This establishes a pre-existing
platform/build difference, not its exact mathematical cause. No tolerance,
rounding, physics change, or skipped case was introduced to conceal it.
This was the G1 limitation. G2 below removes the platform-specific mathematical
implementations; Windows is now required to pass the current WSL oracle.

Additional CLI checks rejected zero workers, empty fixtures, duplicate IDs,
unknown job options, and attempts to record over the fixture file. A failed
record left an existing expected file unchanged. The documented Rust `compile`
example also ran successfully. Its compiled plan was combined with an existing
fixture layout into a temporary Rust-only case: record at 1 thread and check at
16 threads both passed. `cargo fmt --check` passed.

For the negative control, `setup::build` temporarily added `0.000001` to `dt`
only when the job seed was 200. Checking all 868 cases then exited with status
1: 867 passed and `stage-1-case-0` failed. It reported changed destruction,
raw destruction, time, trace hash, and event count, then reran the case and
printed the first changed tick:

```text
stage-1-case-0 DIFFERS:
  destruction_bits: "4045800000000000" -> "4041800000000000"
  time_bits: "404aa66666666666" -> "4045000000000000"
  trace_hash: "5a635578d5a1519c9c11c16d245ff268" -> "de6e64582aede3444613f28b275c62b6"
  trace_events: 534 -> 421 events (fingerprints differ)
  first differing trace event 1 (one tick, or final R):
    expected fingerprint=19cb5e54ba4de700
    actual   fingerprint=8c6b9cff77abfba2
    actual: T 0000000000000000
    actual: U atk 1 P.E.K.K.A 40482de5dbd1007c 4039a434485dff08 40be140000000000
    actual: E [0.0, "deploy", "P.E.K.K.A", 48.5, 25.5]
golden check: cases=868 passed=867 failed=1 threads=16 wall_seconds=5.118823
```

Process wall time was 6.03 seconds. The temporary change was reverted exactly
(`setup.rs` SHA-256 before/after:
`2e47c936010459784e0775d135fdba09cb0e98d342b4e9efbda49f3758f2cb5e`).
Expectations were not changed during the negative control.
The rebuilt binary was byte-for-byte identical to the binary before the tweak
(SHA-256 `32a3190e193a9d72d76575b1584868f38031a031ab7bf2fb24d1eb73b3e7286d`),
and the final full check passed from `/tmp` with an absolute catalog path.

Original G1 baseline SHA-256 values (before G2):

- `cases.jsonl`: `cea706d86516a2100876f9aa4ec7cdd5de32f691202f9a6d049b64e690d172ab`
- `expected.jsonl`: `4edfee14d4975d9f283dcd3cb56afebc6c96322af2915c42a5a16f84a6ecffb7`
- `data/generated/catalog.json`: `91f122ee1649c50fca3cda9bb4d36b837dd2714e071e025b010613a5424979cc`

## G2: platform-identical maths

G1 used `ucrtbase.dll` for `sin`, `cos`, `atan2`, `pow` and scoring's `exp` on
Windows, and Rust's platform f64 functions on Linux. The G1 investigation
found 385/868 Windows-versus-WSL trace differences and two final-result
differences. G2 deliberately moves from that `python-frozen` baseline to one
platform-identical numerical implementation. No tolerances, output rounding,
fixture changes or physics changes accompany this replacement.

`detmath.rs` ports the musl/FreeBSD msun/fdlibm routines, preserving polynomial
coefficients, expression grouping and binary64 intermediate rounding. It uses
ordinary Rust operations and bit conversions on every platform. There is no
unsafe code, FFI, dependency, platform switch, library transcendental call or
`mul_add`. The library now forbids unsafe code at compile time. Both DLL loaders
(including the separate one in `scoring.rs`) have been removed.

Source details, consulted 2026-10-25:

- Trigonometric entry points and kernels: musl
  [`sin.c`](https://github.com/ifduyue/musl/blob/master/src/math/sin.c),
  [`cos.c`](https://github.com/ifduyue/musl/blob/master/src/math/cos.c),
  [`__sin.c`](https://github.com/ifduyue/musl/blob/master/src/math/__sin.c),
  [`__cos.c`](https://github.com/ifduyue/musl/blob/master/src/math/__cos.c),
  [`__rem_pio2.c`](https://github.com/ifduyue/musl/blob/master/src/math/__rem_pio2.c),
  [`__rem_pio2_large.c`](https://github.com/ifduyue/musl/blob/master/src/math/__rem_pio2_large.c),
  [`atan.c`](https://github.com/ifduyue/musl/blob/master/src/math/atan.c), and
  [`atan2.c`](https://github.com/rofl0r/musl/blob/master/src/math/atan2.c).
- Legacy `pow.c`: musl's fdlibm import at
  [`b69f695acedd4ce2798ef9ea28d834ceccc789bd`](https://git.musl-libc.org/cgit/musl/diff/src/math/pow.c?h=v1.1.21&id=b69f695acedd4ce2798ef9ea28d834ceccc789bd).
- Legacy `exp.c`: the musl source preserved in Zircon at
  [`13ee3dc5e4c46bf127977ad28645c47442ec517d`](https://fuchsia.googlesource.com/zircon/+/13ee3dc5e4c46bf127977ad28645c47442ec517d/third_party/ulib/musl/third_party/math/exp.c).
  These are the fdlibm algorithms before musl's 2018 Arm replacements;
  `pow` is not implemented as `exp(y * ln(x))`.
- Exact power-of-two scaling: musl
  [`scalbn.c`](https://github.com/ifduyue/musl/blob/master/src/math/scalbn.c).
  The [musl MIT licence](https://github.com/ifduyue/musl/blob/master/COPYRIGHT)
  and original Sun notices are retained at the top of `detmath.rs`.

The large-angle reducer retains all 66 binary64 2/pi limbs and recomputation,
specialized to musl's `prec=1` output. Extended/quad precision modes are unused.
The port omits `FORCE_EVAL` expressions whose only purpose is to raise C
floating-point exception flags, and returns a canonical NaN for domain errors
and NaN inputs. The engine contract uses round-to-nearest-even binary64 under
the normal Rust compilation model, without fast-math, changed rounding modes,
or flush-to-zero. Signed zero, subnormal, infinity and finite results retain
the musl algorithms. This is not a general C floating-point-environment API.

### Accuracy and reproducibility proof

A temporary standalone Rust helper under `/tmp/clash-g2` compared the port to
the host's f64 platform functions. It is a proof run, not a committed test
suite. Rust 1.99.1, `x86_64-unknown-linux-gnu`, WSL, release optimization,
overflow checks enabled; SplitMix64 seed `0x47325f6d61746873`, top 53 bits
converted to uniform doubles. Each iteration draws angle, x, y, exp argument,
base, and (every third iteration) a random power, in that order.

Each function receives 1,000,000 random engine-range inputs, followed by edge
inputs. Angles are uniform in [-16*pi, 16*pi], `atan2` coordinates in
[-128, 128], `exp` arguments in [-0.25, 0.25] (covering scoring's five
arguments), and `pow` bases in [0.000001, 16384], with powers cycling through
0.5, 2 and uniform [-4, 4]. The actual engine uses powers 0.5 and 2; the
additional powers exercise the general fdlibm path. Edges include adjacent
f64 values around multiples of pi/2, scoring inputs, range-reduction and
overflow/underflow boundaries, signed axes, subnormals, infinities and NaNs.

| Function | Comparisons including edges | Differing results | Max ULP distance from host |
| --- | ---: | ---: | ---: |
| sin | 1,006,168 | 31,019 | 1 |
| cos | 1,006,168 | 30,997 | 1 |
| atan2 | 1,000,441 | 177,674 | 1 |
| exp | 1,000,051 | 70,454 | 1 |
| pow | 1,000,441 | 33,276 | 1 |

A further 1,000,000 random raw-bit inputs per function, continuing the same
RNG stream, exercise the full exponent range and large-angle reducer:

| Function | Comparisons | Differing results | Max ULP distance from host |
| --- | ---: | ---: | ---: |
| sin | 1,000,000 | 15,647 | 1 |
| cos | 1,000,000 | 15,843 | 1 |
| atan2 | 1,000,000 | 9,903 | 1 |
| exp | 1,000,000 | 705 | 1 |
| pow | 1,000,000 | 358 | 1 |

Every comparison agrees on finite/infinite/NaN classification and infinity
sign. Difference counts compare result bits, except that all NaNs are treated
as equivalent; ULP distance is the distance between ordered finite f64 values.
These are empirical distances to host libm, not a mathematical worst-case
error bound relative to exact real arithmetic. Musl's nearly-rounded results
are expected to differ from the host's last bit on some inputs.

The helper hashes every result in order. Debug, optimized, and optimized
`-C target-feature=+fma` builds produced identical fingerprints for all ten
rows. Thus neither optimization nor enabling FMA instructions changed the
operation results in this proof. Windows still needs the caller's full golden
check; no Windows execution is claimed here.

### Golden re-recording

The unchanged G1 binary first passed 868/868 against the saved G1 recording.
The new engine recorded all 868 cases in WSL, then `golden check` against G1
reported exactly 416 changed cases. Every changed case has a changed trace
hash and tick-fingerprint stream; 452 cases are byte-identical. Fixtures,
schema, case fingerprints, stars and stopping reasons are unchanged.

The replacement of host maths with fixed musl maths is the intended reason for
every changed case. The first changed G1 diagnostic is `stage-1-case-6`, trace
event 229. The complete changed-case index list is retained below: an index K
in row S denotes `stage-S-case-K`, and inclusive ranges expand to every K.

| Stage | Changed cases | Changed case indices |
| --- | ---: | --- |
| 1 | 22 | 6, 12, 14, 19, 22, 27, 29, 34, 36, 39–40, 42, 44, 47, 57, 59, 66–71 |
| 2 | 24 | 4, 16, 20–22, 24, 29, 31, 40, 44, 48–49, 52–53, 55, 65, 68, 72–73, 76–77, 84, 87–88 |
| 3 | 54 | 2–15, 18–20, 22–23, 25–42, 44–47, 50–62 |
| 4 | 57 | 2–5, 8–23, 25–47, 49–56, 58–63 |
| 5 | 44 | 3, 8, 12–15, 17–19, 21–25, 27, 31–35, 37–39, 46–66 |
| 6 | 18 | 3, 10, 12–13, 16, 20, 22, 24–25, 27–29, 31–32, 35, 37–39 |
| 7 | 23 | 46, 49, 56, 128, 148, 158, 162, 167–179, 181–183 |
| 8 | 114 | 1–4, 8–15, 19–21, 24–25, 27–32, 35–37, 39–40, 42–43, 45, 47–48, 50–54, 56–57, 59–61, 64–65, 67–72, 76–80, 83–92, 94–95, 99–104, 106–116, 118–119, 122–124, 126, 128–131, 134, 138, 141–144, 146–154, 156–159 |
| 9 | 60 | 1–5, 7–8, 10, 19–22, 24, 26, 30–31, 33–35, 46, 50–51, 54, 56–59, 63–65, 77, 79–81, 84–92, 94, 96, 105–119 |

Only two cases change final result fields:

| Case | G1 WSL result | G2 platform-identical result |
| --- | --- | --- |
| stage-4-case-8 | 2 stars, 77%, time bits `4060666666666666` | 2 stars, 78%, time bits `40608ccccccccccd` |
| stage-4-case-12 | 3 stars, 100%, time bits `4062266666666666` | 3 stars, 100%, time bits `4063c66666666666` |

Case 8 also changes raw-destruction bits from `405335e50d79435e` to
`405379435e50d794`. Both G2 final results happen to match the saved
Windows results from the G1 investigation. This observation does not
establish that the new complete traces match the old Windows traces.

| G2 operation | Cases passing | Threads | Engine wall seconds |
| --- | ---: | ---: | ---: |
| Record to temporary file | 868/868 | 16 | 5.302 |
| Check temporary recording | 868/868 | 1 | 48.473 |
| Check temporary recording | 868/868 | 16 | 5.363 |
| Rebuilt binary, installed recording | 868/868 | 16 | 5.261 |

After these checks, the temporary recording replaces
`fixtures/golden/expected.jsonl`. The fixture file and catalog keep their G1
SHA-256 values. Current expectation SHA-256:

`7bcf0c5f160aa1e98cbc7a76f9947fae9eb089cce1020cd7553f392565e1bbd5`.

`cargo build --release --offline` and `cargo fmt --check` pass.
The repository-root `python3 -B verify.py` command cannot run because
`verify.py` is absent in this checkout. No Python engine code or tests
were changed; Python parity is intentionally retired for G2.

### Complete Rust maths call-site audit

The audit covered all `rust/src/**/*.rs`, including Rust-only search,
scoring, CLI and existing proof modules, and the `attacker.rs` path module.
`rust/vidmine` is outside this task and was not edited. Locations below
refer to the G2 source; line numbers are source lines, and `(x2)` means
two calls on the same line.

Before G2, the platform calls were `geom.rs:211` (`cos`), `:219` (`sin`),
`:227` (`atan2`), `:236` (`powf`), and `scoring.rs:124` (`exp`), together
with their Windows FFI alternatives. Current dispatch is
`geom.rs:155,160,165,170` and `scoring.rs:102`, all calling `detmath`.

No platform calls remain to `sin`, `cos`, `tan`, `asin`, `acos`, `atan`,
`atan2`, `sinh`, `cosh`, `tanh`, `asinh`, `acosh`, `atanh`, `exp`, `exp2`,
`exp_m1`, `ln`, `log`, `log2`, `log10`, `ln_1p`, `powf`, `powi`, `cbrt`,
`hypot`, `sin_cos`, gamma or error functions. Only the five ported public
functions are in use. `atan` is a private ported dependency of `atan2`.

Every caller of the maths wrappers is listed here; helper definitions
are omitted. Paths in these tables are relative to `rust/src`:

| File | py_cos | py_sin | py_atan2 | py_pow | py_hypot |
| --- | --- | --- | --- | --- | --- |
| ai.rs | — | — | — | — | 552 |
| attacker.rs | 320 (x2) | — | 311; 319; 344 | — | 1256; 1428; 1507; 1773; 1850 |
| battle.rs | — | — | — | 191 (x2); 508 (x2) | — |
| combat.rs | 504 | 505 | 496 | — | 564; 568; 619; 624; 652 |
| defense.rs | — | — | 1385; 1402; 1520; 1548; 1905 | — | 1400 |
| geom.rs | — | — | — | — | 3; 9 |
| heroes.rs | 1815; 2316; 3287 | 1816; 2317; 3288 | 1742; 1756; 1796 | — | 135; 159; 162; 1421; 1444; 2245; 2399; 2402; 2915 |
| movement.rs | 48 | 49 | — | — | 316; 328; 345 |
| pets.rs | — | — | — | 727 | — |
| plans.rs | 2284 | 2284 | 1133; 1143; 1150 | — | 1155; 1166; 1180; 1429 (x2); 1719; 1725; 1750; 2268; 2270 |
| playbook.rs | — | — | — | 2063; 2064 | 622; 738; 744; 776; 873; 882; 1123 |
| spells.rs | 1225 | 1226 | — | 1483 | 502; 795; 828; 830; 1541; 1949 |
| state.rs | — | — | — | — | 1103; 1121; 1132; 1590 |
| traps.rs | 454; 588 | 455; 588 | — | — | — |
| units.rs | 876; 1503; 1546; 1603; 1669 | 877; 1504; 1547; 1604; 1670 | — | — | 1100; 2323; 2572; 2594; 2687 |

`py_hypot` at `geom.rs:94` already implements CPython vector_norm using
explicit scaling, compensated products/sums and a Newton correction.
It calls only exact `sqrt`, so changing it to a musl hypot would add an
unnecessary numerical change. It remains platform-independent.

All direct uses of the requested deterministic functions and other
rounding/sign/remainder functions follow. The inventory conservatively
includes integer calls with matching names. Integer-only sites include
`armies.rs:287` and `trace.rs:90` (`abs`), `units.rs:2789` (`abs`),
`compile.rs:286` and `scoring.rs:102,106` (`rem_euclid`), and both
`div_euclid` sites. They require no maths replacement.

| Function | All direct call sites |
| --- | --- |
| sqrt | `armysearch/score.rs:481,580,686`; `detmath.rs:705`; `geom.rs:109,130`; `grid.rs:870,1238`; `movement.rs:45` |
| floor | `armysearch/program_mutate.rs:303`; `detmath.rs:339`; `scoring.rs:70`; `units.rs:643,644` |
| ceil | `armysearch/score.rs:324`; `attacker.rs:1470`; `defense.rs:511`; `traps.rs:614` |
| round | `armysearch/proof.rs:60`; `armysearch/search.rs:102,103` |
| round_ties_even | `geom.rs:48` |
| abs | `armies.rs:287`; `armysearch/account.rs:321`; `armysearch/fix_proof.rs:680,681`; `attacker.rs:106`; `combat.rs:498`; `defense.rs:1402,1522,1549,1906,1958`; `detmath.rs:483,566,683,708`; `geom.rs:7,8,54,58,95 (x2)`; `grid.rs:1384,1385,1402,1405`; `heroes.rs:1760,2032,2927,2943`; `pets.rs:725,726`; `plans.rs:1085 (x2),1086,1134,1151,1308,1786 (x2)`; `spells.rs:456 (x4)`; `trace.rs:65,90`; `units.rs:62 (x4),2605,2688,2689,2789 (x2),2792 (x2),3042` |
| mul_add | None |
| trunc | None |
| fract | `armies.rs:87,513`; `armysearch/account.rs:199`; `armysearch/genome.rs:73`; `armysearch/program_validate.rs:111,252`; `compile.rs:1557,2024`; `json.rs:69`; `load.rs:139`; `scoring.rs:457`; `setup.rs:373,382,1465` |
| copysign | `geom.rs:87`; `traps.rs:647` |
| rem_euclid | `armysearch/eval.rs:119,199,284`; `armysearch/operators.rs:357`; `combat.rs:498`; `compile.rs:286`; `defense.rs:1402,1522,1549,1906`; `heroes.rs:1758`; `movement.rs:47`; `plans.rs:1134,1150`; `scoring.rs:102,106` |
| div_euclid | `effects.rs:148`; `heroes.rs:189` |

Also inspected: `nextafter` in `traps.rs:639` is already implemented with
bits and `copysign`; `round6` in `geom.rs:51` and `round_decimal` in
`trace.rs:111` and `scoring.rs:1198` use fixed Rust integer/decimal conversion;
degree/radian conversion (for example `setup.rs:1421`) is explicit multiplication.
`%`, floating `rem_euclid`, comparisons, `min`/`max`/`clamp`, classification,
sign tests, `total_cmp`, bit conversions, basic arithmetic and f32/f64
conversions have no approximated transcendental implementation to replace.
No `recip`, `signum`, `to_radians`, `to_degrees`, `next_up`, `next_down` or
`round_ties_away` library calls were found. Rust constant values and Rust
decimal parsing/formatting do not select the host C maths library.

## PB1a: compiled plans and intended runtime changes

PB1a intentionally changes Rust fitting and therefore diverges from the frozen
Python compiler. No Python was executed. The saved `/tmp/m2-plan-reference-0.json`
and `-1.json` already failed baseline coverage because the current library includes
`custom:user-rr-oct25`, which those references omit.

`compile-check` now defaults to the Rust compiled-plan oracle in
`fixtures/golden/plans.jsonl`. Explicit `--reference FILE` comparisons remain available
for historical saved references; only an explicit `--python` requests the legacy
Python exporter. Normal checking never starts Python.

The plan oracle records complete current Rust inputs, output plans, legality
diagnostics and expected errors for **1,196 declared synthetic cases** in both
playbook modes. It covers the library at four angles/two seeds, roster changes,
explicit variants, overrides, supported/unsupported tactics and invalid inputs.
Checking regenerates the case list, so additions, removals, changed inputs,
ordering and changed compilation outcomes fail. `compile-check` also retains the
account admission fixtures.

From the repository root, using the PB1a WSL binary and absolute catalog path:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-pb
export CLASH_CATALOG="$PWD/data/generated/catalog.json"
cargo build --workspace --all-targets --release --locked --offline --manifest-path Cargo.toml
/tmp/clash-target-pb/release/clash golden plans check fixtures/golden/plans.jsonl
cd rust
/tmp/clash-target-pb/release/clash compile-check --playbooks 1
/tmp/clash-target-pb/release/clash compile-check --playbooks 0
```

After reviewing an intentional compiler or library change, record with
`clash golden plans record fixtures/golden/plans.jsonl` from the repository
root, then check both modes. Plan recording writes through a temporary file.
The plan snapshot includes the concurrently corrected PB2 library; PB1a does not
edit those source data files.

The original battle fixtures remain unchanged. The untouched binary first passed
868/868 old expectations. The intended engine then changed **134/868** cases.
Independent Rust control recordings enabled each runtime correction separately;
disabling all runtime corrections reproduced **868/868** old expectations exactly.
Every changed case below differs under at least one identified individual fix:

- **D1 — consumed Phoenix deadline:** terminal death/Revive clears the consumed
  deadline. A revived hero survives instead of being killed again by the expired
  Phoenix timer. This individually affects 41 cases.
- **D2 — attached Angry Jelly separation:** attached Jelly is excluded from both
  sides of collision pairing. Its owner no longer receives artificial repeated
  displacement; detached units retain normal separation. This individually
  affects 94 cases.
- **A14 — Air Defense aim count:** explicit AD aiming honors the requested/inferred
  count, changing the ability time/line instead of firing through only one AD.
  This individually affects 11 cases.

Overlaps are intentional: 36 D1-only, 84 D2-only, two A14-only, three D1+D2,
two D1+A14 and seven D2+A14 cases, totaling 134. Other PB1a changes do not alter
the old prepared battle traces; fitter regressions are covered by the new plan
oracle, and A11–A13 have focused Rust tests and seeded witness replays.
See [`PB1A.md`](PB1A.md) for before/after witnesses, source boundaries and the
deferred PB1b interfaces. These are simulation regression results, not calibration.

Every accepted changed case and its independently verified reason follows.

| Case | Reason(s) defined above |
| --- | --- |
| stage-4-case-29 | D1 |
| stage-4-case-31 | D1 |
| stage-4-case-33 | D1 |
| stage-4-case-39 | D1 |
| stage-4-case-47 | D1 |
| stage-4-case-49 | D1 |
| stage-4-case-57 | D1 |
| stage-4-case-63 | D1 |
| stage-5-case-1 | D2 |
| stage-5-case-2 | D2 |
| stage-5-case-6 | D2 |
| stage-5-case-8 | D2 + A14 |
| stage-5-case-9 | D2 |
| stage-5-case-10 | D2 |
| stage-5-case-11 | A14 |
| stage-5-case-12 | D1 + A14 |
| stage-5-case-13 | D2 + A14 |
| stage-5-case-16 | D1 |
| stage-5-case-17 | D1 |
| stage-5-case-18 | D1 |
| stage-5-case-19 | D2 |
| stage-5-case-22 | D1 |
| stage-5-case-33 | D2 |
| stage-5-case-34 | D2 + A14 |
| stage-5-case-38 | D1 + D2 |
| stage-5-case-40 | D2 |
| stage-5-case-41 | D2 + A14 |
| stage-5-case-42 | D2 + A14 |
| stage-5-case-43 | A14 |
| stage-5-case-44 | D1 + A14 |
| stage-5-case-45 | D2 + A14 |
| stage-5-case-48 | D1 |
| stage-5-case-51 | D2 |
| stage-5-case-62 | D1 |
| stage-5-case-65 | D2 |
| stage-5-case-66 | D2 + A14 |
| stage-7-case-10 | D2 |
| stage-7-case-20 | D2 |
| stage-7-case-33 | D2 |
| stage-7-case-43 | D2 |
| stage-7-case-56 | D2 |
| stage-7-case-66 | D2 |
| stage-7-case-79 | D2 |
| stage-7-case-89 | D2 |
| stage-7-case-102 | D2 |
| stage-7-case-112 | D2 |
| stage-7-case-125 | D2 |
| stage-7-case-135 | D2 |
| stage-7-case-148 | D2 |
| stage-7-case-158 | D2 |
| stage-7-case-171 | D2 |
| stage-7-case-181 | D2 |
| stage-8-case-0 | D1 |
| stage-8-case-6 | D2 |
| stage-8-case-7 | D2 |
| stage-8-case-8 | D2 |
| stage-8-case-15 | D2 |
| stage-8-case-16 | D2 |
| stage-8-case-17 | D2 |
| stage-8-case-21 | D2 |
| stage-8-case-22 | D2 |
| stage-8-case-29 | D2 |
| stage-8-case-30 | D2 |
| stage-8-case-31 | D2 |
| stage-8-case-32 | D2 |
| stage-8-case-33 | D2 |
| stage-8-case-44 | D2 |
| stage-8-case-45 | D2 |
| stage-8-case-46 | D1 + D2 |
| stage-8-case-65 | D2 |
| stage-8-case-66 | D2 |
| stage-8-case-70 | D1 |
| stage-8-case-71 | D1 |
| stage-8-case-72 | D1 |
| stage-8-case-76 | D2 |
| stage-8-case-77 | D2 |
| stage-8-case-85 | D1 |
| stage-8-case-90 | D1 |
| stage-8-case-91 | D1 |
| stage-8-case-92 | D1 |
| stage-8-case-93 | D1 |
| stage-8-case-95 | D1 |
| stage-8-case-102 | D1 |
| stage-8-case-105 | D2 |
| stage-8-case-106 | D2 |
| stage-8-case-107 | D2 |
| stage-8-case-114 | D2 |
| stage-8-case-115 | D2 |
| stage-8-case-116 | D2 |
| stage-8-case-120 | D2 |
| stage-8-case-121 | D2 |
| stage-8-case-128 | D2 |
| stage-8-case-129 | D2 |
| stage-8-case-130 | D2 |
| stage-8-case-131 | D2 |
| stage-8-case-132 | D2 |
| stage-8-case-143 | D1 + D2 |
| stage-8-case-144 | D2 |
| stage-8-case-145 | D2 |
| stage-9-case-6 | D2 |
| stage-9-case-7 | D2 |
| stage-9-case-8 | D2 |
| stage-9-case-21 | D2 |
| stage-9-case-22 | D2 |
| stage-9-case-23 | D2 |
| stage-9-case-36 | D2 |
| stage-9-case-37 | D2 |
| stage-9-case-38 | D2 |
| stage-9-case-45 | D1 |
| stage-9-case-46 | D1 |
| stage-9-case-47 | D1 |
| stage-9-case-48 | D1 |
| stage-9-case-50 | D1 |
| stage-9-case-51 | D2 |
| stage-9-case-52 | D2 |
| stage-9-case-53 | D2 |
| stage-9-case-61 | D1 |
| stage-9-case-66 | D2 |
| stage-9-case-67 | D2 |
| stage-9-case-68 | D2 |
| stage-9-case-75 | D1 |
| stage-9-case-76 | D1 |
| stage-9-case-77 | D1 |
| stage-9-case-79 | D1 |
| stage-9-case-81 | D2 |
| stage-9-case-82 | D2 |
| stage-9-case-83 | D2 |
| stage-9-case-96 | D2 |
| stage-9-case-97 | D2 |
| stage-9-case-98 | D2 |
| stage-9-case-106 | D1 |
| stage-9-case-111 | D2 |
| stage-9-case-112 | D2 |
| stage-9-case-113 | D2 |

## PB1b: intentional recipe/controller and plan-oracle changes

PB1b preserves the battle fixture inputs and the v29 combat rules. It adds
explicit recipe selection, all-required variant loadouts, siege-role repair,
connected-packet pacing, primary deployment/cohort and reserve roles, cited-role
normalization, named Recall lifecycle handling, and the narrowly cited objective
and effect dependencies. See [PB1B.md](PB1B.md) for source citations, paired replay
witnesses, section C holds and TH18 measurements. No Python was run or edited.

The unchanged binary first passed **868/868 battle cases** and **1,196/1,196 plan
cases** against the saved PB1a recordings. The intended runtime changes alter
**two battle cases**, leaving **866 byte-identical**. These original prepared
plans do not carry PB1b packet/cohort/objective annotations; their changes come
from A10's stored-hero charge closure and bound named-return lifecycle. No army,
spell stock, level, combat constant or fixture result was adjusted to target a
score. Both accepted cases and the intended reason are listed here:

| Case | Intended reason |
| --- | --- |
| stage-5-case-27 | A10: Recall storage closes charge support; named returns bind to their opening task and hero |
| stage-5-case-56 | A10: Recall storage closes charge support; named returns bind to their opening task and hero |

The compiled-plan oracle contains **1,354 declared synthetic cases**: 667 with
playbooks disabled and 687 with playbooks enabled. It retains every old case and
adds 158 explicit-recipe cases, including generic-mode compatibility controls.
Of the old cases, **522 change and 674 remain identical**. Each changed or added
case is enumerated below, grouped only when its case ID, mode and change reasons
match. Angle/seed pairs uniquely identify each fixture within that group.

Reason keys describe the changed executable fields:

- **C5:** explicit recipe dispatch, composition/resource or all-required-loadout
  validation (A5). New fixtures exercise that public input path.
- **C6:** replacement siege ID/role and preserved cited prerequisites (A6).
- **P:** connected packets and wait fitting (A7).
- **M:** explicit primary/cohort allocations, sorted inventory/remainders and
  reserve/scout/breach roles (A8).
- **D:** cited role preservation and inherited dependency normalization (A9).
- **R:** charge package/closure, named Recall return and post-Recall metadata (A10).
- **O:** bound objective, prior-success, named threat, effect/renewal, wave and
  recipient prerequisites (A15).
- **B:** dependent cited playbook corrections, including added/removed source
  steps and quantities. Their per-book citations and limitations are in PB1B.

Slash-separated keys identify fields shared by those semantics; keys are not
mutually exclusive. Error-outcome changes marked C5/O are intentional recipe or
final-graph compatibility checks. An unchanged generic plan with a new recipe
input is a new C5 fixture, not an altered generic battle.

Angle labels `0.000000`, `1.570796`, `3.141593` and `4.712389` stand for the
fixture generator's exact `0`, `pi/2`, `pi` and `3*pi/2` values; `0.370000` is its
literal 0.37 variant/override probe. No fixture angle was rounded for execution.

| Status; mode; case ID | Exact fixture angle label/seed pairs | Intended reason keys |
| --- | --- | --- |
| changed; playbook; custom-armies.json:custom:decoy-super-yeti | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; custom-armies.json:custom:druid-titan-rr | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:flinger-throwers | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; custom-armies.json:custom:lavaloon-queen-dragons | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; custom-armies.json:custom:portal-relay-rr | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:puppet-queen-throwers | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; custom-armies.json:custom:user-air | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | B, C5/C6, C6, D/M, M, O, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-druid-ruin | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, O, P, P/D/O |
| changed; playbook; custom-armies.json:custom:user-fireball-warden | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-AQ-GW-MP-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; custom-armies.json:custom:user-rr-h-AQ-GW-RC-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-AQ-GW-RC-MP | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-AQ-RC-MP-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-AQ-GW-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-AQ-GW-MP | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | C5/C6, D/M, M, P, P/D/O |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-AQ-GW-RC | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | C5/C6, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-AQ-MP-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-AQ-RC-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-AQ-RC-MP | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | B, D/M, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-GW-MP-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-GW-RC-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-GW-RC-MP | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | C5/C6, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-BK-RC-MP-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-h-GW-RC-MP-DD | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M, P, P/D/O, R |
| changed; playbook; custom-armies.json:custom:user-rr-oct25 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O, R |
| changed; playbook; donation-level-cap | 0.000000/0 | M, P, P/D/O |
| changed; playbook; dragon:variant:Flame Blower Duke opening | 0.370000/1 | C5/O |
| changed; playbook; dragon:variant:Mass Dragons | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; equipment-owner-duplicate-pet | 0.000000/0 | M, P, P/D/O |
| changed; playbook; fireball-warden:variant:Early Spiky Ball to establish the hero funnel | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; fireball-warden:variant:Giant Arrow through the opened core | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; fireball-warden:variant:Quick Fireball before Healers and Furnaces | 0.370000/1 | D/M, M, O, P, P/D/O, R |
| changed; playbook; fireball-warden:variant:Three-Invisibility Fireball redirect | 0.370000/1 | D/M, M, O, P, P/D/O, R |
| changed; playbook; fireball-warden:variant:Wall Breaker entry with Headhunters and Druid | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; five-hero-slots | 0.000000/0 | M, P, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:e-drag-spam-18-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; meta-armies-2026-10-15.json:e-drag-spam-18-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; meta-armies-2026-10-15.json:mass-dragons-16-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M, P, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:mass-dragons-17-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M, P, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:mass-dragons-17-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; meta-armies-2026-10-15.json:mass-dragons-18-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M, P, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:mass-dragons-18-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M |
| changed; playbook; meta-armies-2026-10-15.json:mass-meteor-golem-18-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:mass-super-yeti-18-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:mass-super-yeti-18-4 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:mass-thrower-16-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; meta-armies-2026-10-15.json:mass-thrower-16-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; meta-armies-2026-10-15.json:mass-thrower-17-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M |
| changed; playbook; meta-armies-2026-10-15.json:mass-thrower-17-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M |
| changed; playbook; meta-armies-2026-10-15.json:mass-thrower-18-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:mass-thrower-18-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | M |
| changed; playbook; meta-armies-2026-10-15.json:root-rider-16-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | C5/C6, D/M, M, P, P/D/O, R |
| changed; playbook; meta-armies-2026-10-15.json:root-rider-16-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | C5/C6, D/M, M, P, P/D/O, R |
| changed; playbook; meta-armies-2026-10-15.json:root-rider-18-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, R |
| changed; playbook; meta-armies-2026-10-15.json:root-rider-18-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | C5/C6, D/M, M, P, P/D/O, R |
| changed; playbook; meta-armies-2026-10-15.json:super-bowler-smash-18-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; meta-armies-2026-10-15.json:super-bowler-smash-18-3 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O, R |
| changed; playbook; observed-armies.json:e-drag-spam-17-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; observed-armies.json:e-drag-spam-17-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; observed-armies.json:e-drag-spam-17-3 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; observed-armies.json:e-drag-spam-17-4 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; observed-armies.json:e-drag-spam-17-5 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; observed-armies.json:e-drag-spam-17-6 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; observed-armies.json:e-drag-spam-17-7 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M |
| changed; playbook; observed-armies.json:root-rider-17-1 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | C5/C6, D/M, M, P, P/D/O, R |
| changed; playbook; observed-armies.json:root-rider-17-2 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | D/M, M, P, P/D/O |
| changed; playbook; observed-armies.json:root-rider-17-3 | 0.000000/0, 0.000000/1, 1.570796/0, 1.570796/1, 3.141593/0, 3.141593/1, 4.712389/0, 4.712389/1 | C5/C6, D/M, M, P, P/D/O, R |
| changed; playbook; overrides-dragon | 0.370000/1 | M, P, P/D/O |
| changed; playbook; overrides-druid-ruin-witch | 0.370000/1 | D/M, M, O, P, P/D/O |
| changed; playbook; overrides-electro-dragon | 0.370000/1 | D/M, M |
| changed; playbook; overrides-fireball-warden | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; overrides-meteor-golem | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; overrides-root-rider | 0.370000/1 | D/M, M, P, R |
| changed; playbook; overrides-super-bowler | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; overrides-super-minion-air | 0.370000/1 | B, C5/C6, C6, D/M, M, O, P, P/D/O, R |
| changed; playbook; overrides-thrower | 0.370000/1 | D/M, M, P/D/O |
| changed; playbook; overrides-yeti | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; root-rider:variant:Barbarian King with the main army | 0.370000/1 | C5/C6, D/M, M, P, P/D/O, R |
| changed; playbook; root-rider:variant:Dragon Duke opening with Flame Blower, Earthquake and Angry Spell | 0.370000/1 | C5/O |
| changed; playbook; root-rider:variant:Root Rider and Thrower main army | 0.370000/1 | D/M, M, P, R |
| changed; playbook; roster-dragon | 0.370000/1 | M, P, P/D/O |
| changed; playbook; roster-druid-ruin-witch | 0.370000/1 | D/M, M, O, P, P/D/O |
| changed; playbook; roster-electro-dragon | 0.370000/1 | D/M, M |
| changed; playbook; roster-fireball-warden | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; roster-meteor-golem | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; roster-root-rider | 0.370000/1 | D/M, M, P, R |
| changed; playbook; roster-super-bowler | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; roster-super-minion-air | 0.370000/1 | B, C5/C6, C6, D/M, M, O, P, P/D/O, R |
| changed; playbook; roster-thrower | 0.370000/1 | D/M, M, P/D/O |
| changed; playbook; roster-yeti | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; super-bowler:variant:Dragon Duke charge with King and Queen support | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; super-bowler:variant:Protect the Queen with Totem and reserve Rage for Bowlers | 0.370000/1 | D/M, M, P, P/D/O, R |
| changed; playbook; super-bowler:variant:Rocket Backpack and Flame Blower funnel | 0.370000/1 | C5/O |
| changed; playbook; super-minion-air:variant:Continue the Warden walk until dangerous defensive fire | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; super-minion-air:variant:Early Spiky Ball through a Rage compartment | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; super-minion-air:variant:Finish Giant Arrow before redeploying the Warden | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; super-minion-air:variant:Ice Block-assisted Fireball | 0.370000/1 | B, C5/C6, D/M, M, O, P, P/D/O, R |
| changed; playbook; super-minion-air:variant:Log Launcher hero dive | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; super-minion-air:variant:One Super Minion to accelerate a lengthy Warden charge | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; super-minion-air:variant:Three Earthquakes before Rocket Backpack | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; super-minion-air:variant:Two Super Minions to snipe a remaining Super Wizard Tower | 0.370000/1 | C5/O |
| changed; playbook; super-minion-air:variant:Two simultaneous split Earthquakes on the Revenge Tower and Monolith | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; tactics-dragon | 0.370000/1 | M, P, P/D/O |
| changed; playbook; tactics-druid-ruin-witch | 0.370000/1 | D/M, M, O, P, P/D/O |
| changed; playbook; tactics-electro-dragon | 0.370000/1 | D/M, M |
| changed; playbook; tactics-fireball-warden | 0.370000/1 | B, D/M, M, O, P, P/D/O, R |
| changed; playbook; tactics-meteor-golem | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; tactics-root-rider | 0.370000/1 | D/M, M, P, R |
| changed; playbook; tactics-super-bowler | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; tactics-super-minion-air | 0.370000/1 | B, C5/C6, C6, D/M, M, O, P, P/D/O, R |
| changed; playbook; tactics-thrower | 0.370000/1 | D/M, M, P/D/O |
| changed; playbook; tactics-yeti | 0.370000/1 | D/M, M, P, P/D/O |
| changed; playbook; three-super-boosts | 0.000000/0 | D/M, M, P, P/D/O |
| changed; playbook; thrower:variant:Queen counterfunnel with King saved for the back end | 0.370000/1 | D/M, M, P/D/O |
| changed; playbook; unknown-spell-event | 0.000000/0 | M, P, P/D/O |
| new; generic; dragon:recipe:Dragon Riders with Inferno Dragons | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Flame Blower Duke opening | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Flame Flinger opening with a sixty-second lead | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Giant Arrow and Rocket Backpack followed by zapquake | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Ice Hound leads the Dragons and Dragon Riders | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Mass Dragons | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Repeat Overgrowth on the Monolith compartment | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Revenge Deck Duke charge with Ice Block | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Rocket Spear Royal Champion charge before the Duke funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Siege Barracks with the Queen on the opposite flank | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Spirit Fox Duke Invisibility charge and Royal Champion funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Super Dragons after a Revenge Deck Duke funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; dragon:recipe:Three-Earthquake opening and opposite Sky Wagon funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; druid-ruin-witch:recipe:Electro Titans ahead of four Ruin Witches | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; druid-ruin-witch:recipe:Four Ruin Witches with staggered Druids | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; druid-ruin-witch:recipe:Life Gem Warden walk | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; druid-ruin-witch:recipe:Super Witch hybrid with Royal Champion funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; electro-dragon:recipe:Four Electro Dragons funnel a Ruin Witch and hero push | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; electro-dragon:recipe:Rage-assisted flank and Skeleton distraction | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; electro-dragon:recipe:Revenge Tower compartment Zapquake with Siege Barracks | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; electro-dragon:recipe:Rocket Backpack Zapquake with a secondary Spell Tower | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; fireball-warden:recipe:Early Spiky Ball to establish the hero funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; fireball-warden:recipe:Giant Arrow through the opened core | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; fireball-warden:recipe:Quick Fireball before Healers and Furnaces | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; fireball-warden:recipe:Three-Invisibility Fireball redirect | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; fireball-warden:recipe:Wall Breaker entry with Headhunters and Druid | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; meteor-golem:recipe:Fireball opening instead of the Dragon Duke and two-Golem funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; meteor-golem:recipe:Natural funnel: send all Meteor Golems together | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; meteor-golem:recipe:Queen opposite the Meteor Golem push; delay her ability | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; meteor-golem:recipe:Six Meteor Golems with seven Super Archers | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; meteor-golem:recipe:Warden walk opening with test Balloons and five Healers | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Barbarian King with the main army | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Dragon Duke charge with Ice Block and delayed revival | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Dragon Duke opening with Flame Blower, Earthquake and Angry Spell | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Isolate the Town Hall with Overgrowth and save Rocket Spear for it | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Recall early rather than risk the Royal Champion or Spirit Fox | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Rocket Backpack and Giant Arrow setup before the main army | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Root Rider and Thrower main army | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Royal Champion and Grand Warden charge with four-second Invisibility and a Siege Barracks funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; root-rider:recipe:Super Archers protected by an entry Totem | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-bowler:recipe:Dragon Duke charge with King and Queen support | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-bowler:recipe:Log Launcher entry for Invisibility Towers or failed wall access | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-bowler:recipe:Protect the Queen with Totem and reserve Rage for Bowlers | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-bowler:recipe:Rocket Backpack and Flame Blower funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-bowler:recipe:Royal Champion charge with Queen and Duke counter funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-bowler:recipe:Troop Launcher for gradual wall access | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Battle Drill siege choice | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Continue the Warden walk until dangerous defensive fire | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Early Spiky Ball through a Rage compartment | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Finish Giant Arrow before redeploying the Warden | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Ice Block-assisted Fireball | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Log Launcher hero dive | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:One Super Minion to accelerate a lengthy Warden charge | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Open the Flame Flinger to tank for the Queen | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Ricochet Fireball with complementary hero objectives | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Royal Champion follow-up with raged Rocket Spear | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Scatter Fireball with Clan Castle and Super Wizard Tower shots | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Three Earthquakes before Rocket Backpack | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Troop Launcher from the Town Hall side | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Two Super Minions to snipe a remaining Super Wizard Tower | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Two simultaneous split Earthquakes on the Revenge Tower and Monolith | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:recipe:Warden and Flame Flinger on the same side | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:variant:Ricochet Fireball with complementary hero objectives | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; super-minion-air:variant:Scatter Fireball with Clan Castle and Super Wizard Tower shots | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Earthquakes with Giant Arrow and Rocket Backpack | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Firemite Clone opening; only the first Clone cast is specified | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Queen counterfunnel with King saved for the back end | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Rocket Backpack with a two-Earthquake three-Lightning finish | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Skeleton distractions instead of the Totem package | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Spirit Fox and Invisibility Duke charge with an early Warden ability | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Troop Launcher for an open or short Town Hall route | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Two Earthquakes and six Lightnings before the Duke funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Warden walk before the Thrower push | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; thrower:recipe:Yeti frontline for the Town Hall and defending heroes | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; yeti:recipe:Log Launcher through the main entry | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; yeti:recipe:One Super Yeti on each flank before the rest | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; yeti:recipe:Protect the charging Dragon Duke with Invisibility | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; yeti:recipe:Siege Barracks counter-funnel with a later Queen ability | 0.370000/1 | C5 (new recipe fixture) |
| new; generic; yeti:recipe:Wait for the last friendly Ice Golem before Torch and Rage | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Dragon Riders with Inferno Dragons | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Flame Blower Duke opening | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Flame Flinger opening with a sixty-second lead | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Giant Arrow and Rocket Backpack followed by zapquake | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Ice Hound leads the Dragons and Dragon Riders | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Mass Dragons | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Repeat Overgrowth on the Monolith compartment | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Revenge Deck Duke charge with Ice Block | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Rocket Spear Royal Champion charge before the Duke funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Siege Barracks with the Queen on the opposite flank | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Spirit Fox Duke Invisibility charge and Royal Champion funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Super Dragons after a Revenge Deck Duke funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; dragon:recipe:Three-Earthquake opening and opposite Sky Wagon funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; druid-ruin-witch:recipe:Electro Titans ahead of four Ruin Witches | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; druid-ruin-witch:recipe:Four Ruin Witches with staggered Druids | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; druid-ruin-witch:recipe:Life Gem Warden walk | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; druid-ruin-witch:recipe:Super Witch hybrid with Royal Champion funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; electro-dragon:recipe:Four Electro Dragons funnel a Ruin Witch and hero push | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; electro-dragon:recipe:Rage-assisted flank and Skeleton distraction | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; electro-dragon:recipe:Revenge Tower compartment Zapquake with Siege Barracks | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; electro-dragon:recipe:Rocket Backpack Zapquake with a secondary Spell Tower | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; fireball-warden:recipe:Early Spiky Ball to establish the hero funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; fireball-warden:recipe:Giant Arrow through the opened core | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; fireball-warden:recipe:Quick Fireball before Healers and Furnaces | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; fireball-warden:recipe:Three-Invisibility Fireball redirect | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; fireball-warden:recipe:Wall Breaker entry with Headhunters and Druid | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; meteor-golem:recipe:Fireball opening instead of the Dragon Duke and two-Golem funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; meteor-golem:recipe:Natural funnel: send all Meteor Golems together | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; meteor-golem:recipe:Queen opposite the Meteor Golem push; delay her ability | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; meteor-golem:recipe:Six Meteor Golems with seven Super Archers | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; meteor-golem:recipe:Warden walk opening with test Balloons and five Healers | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Barbarian King with the main army | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Dragon Duke charge with Ice Block and delayed revival | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Dragon Duke opening with Flame Blower, Earthquake and Angry Spell | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Isolate the Town Hall with Overgrowth and save Rocket Spear for it | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Recall early rather than risk the Royal Champion or Spirit Fox | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Rocket Backpack and Giant Arrow setup before the main army | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Root Rider and Thrower main army | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Royal Champion and Grand Warden charge with four-second Invisibility and a Siege Barracks funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; root-rider:recipe:Super Archers protected by an entry Totem | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-bowler:recipe:Dragon Duke charge with King and Queen support | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-bowler:recipe:Log Launcher entry for Invisibility Towers or failed wall access | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-bowler:recipe:Protect the Queen with Totem and reserve Rage for Bowlers | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-bowler:recipe:Rocket Backpack and Flame Blower funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-bowler:recipe:Royal Champion charge with Queen and Duke counter funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-bowler:recipe:Troop Launcher for gradual wall access | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Battle Drill siege choice | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Continue the Warden walk until dangerous defensive fire | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Early Spiky Ball through a Rage compartment | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Finish Giant Arrow before redeploying the Warden | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Ice Block-assisted Fireball | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Log Launcher hero dive | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:One Super Minion to accelerate a lengthy Warden charge | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Open the Flame Flinger to tank for the Queen | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Ricochet Fireball with complementary hero objectives | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Royal Champion follow-up with raged Rocket Spear | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Scatter Fireball with Clan Castle and Super Wizard Tower shots | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Three Earthquakes before Rocket Backpack | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Troop Launcher from the Town Hall side | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Two Super Minions to snipe a remaining Super Wizard Tower | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Two simultaneous split Earthquakes on the Revenge Tower and Monolith | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:recipe:Warden and Flame Flinger on the same side | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:variant:Ricochet Fireball with complementary hero objectives | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; super-minion-air:variant:Scatter Fireball with Clan Castle and Super Wizard Tower shots | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Earthquakes with Giant Arrow and Rocket Backpack | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Firemite Clone opening; only the first Clone cast is specified | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Queen counterfunnel with King saved for the back end | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Rocket Backpack with a two-Earthquake three-Lightning finish | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Skeleton distractions instead of the Totem package | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Spirit Fox and Invisibility Duke charge with an early Warden ability | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Troop Launcher for an open or short Town Hall route | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Two Earthquakes and six Lightnings before the Duke funnel | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Warden walk before the Thrower push | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; thrower:recipe:Yeti frontline for the Town Hall and defending heroes | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; yeti:recipe:Log Launcher through the main entry | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; yeti:recipe:One Super Yeti on each flank before the rest | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; yeti:recipe:Protect the charging Dragon Duke with Invisibility | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; yeti:recipe:Siege Barracks counter-funnel with a later Queen ability | 0.370000/1 | C5 (new recipe fixture) |
| new; playbook; yeti:recipe:Wait for the last friendly Ice Golem before Torch and Rage | 0.370000/1 | C5 (new recipe fixture) |

## P1: plan goldens pinned to the public account (2026-10-25)

Player data moved out of Git into `private/` (see `crates/clash-data/src/private.rs`).
`golden plans record|check` now replaces the compiler's account with the synthetic
`data/source/accounts/public-th16.json` (every non-seasonal item at its TH16 cap,
from `clash dataimport account caps --th 16`), so the check gives the same answer
with or without local private data. 416 of 1,354 plan cases were re-recorded; every
difference is an account level (troop, spell, hero, equipment or pet level, and the
stocks and plan numbers derived from them). Battle goldens (`cases.jsonl`,
`expected.jsonl`) embed their plans and did not change.

The account Town Hall in `Compiler::account_legal` and armysearch's
`AccountRules::load` now comes from `levels.th` (default 16; the live player
snapshot's `townHallLevel` sets it). The port had read `levels.gm`, the Gold Mine
level, which matched only by coincidence for the old account. The armysearch
fingerprint now also covers `data/source/accounts/`.
