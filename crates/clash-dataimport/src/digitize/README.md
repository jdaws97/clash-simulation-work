G4 cleanup follow-up (2026-10-25): replaced Python entry points and the
digitizer scratch toolkit were removed after reference closure. Required
unported Python workflows and their imports remain. The lane receipt below
preserves its original scope; see [CLEANUP_G4.md](../../../../docs/CLEANUP_G4.md)
for the current file inventory, local paths and pending Rust handoff.

# Native screenshot digitizer (lane lD)

The public entry point is `clash_dataimport::digitize::cli`; the already wired
command is `clash dataimport digitize`. All implementation uses Rust's standard
library plus the existing `clash-data` and `clash-layout` crates. No Python,
image subprocess, network access, downloads or additional Cargo dependencies
are required at runtime or in the portable tests.

The only change outside `crates/clash-dataimport/src/digitize/` is the new
`crates/clash-layout/src/render.rs` and its `pub mod render;` declaration.
The renderer is public so other presentation lanes can reuse it. No shared
catalog, engine, rules, fixture or dispatcher changes were needed.

## Commands and data contracts

Every command uses `--key value` options. Boolean values are `yes` or `no`.
`--root` explicitly selects the workspace containing the pinned catalog and
base rules; otherwise the build-time workspace root is used. `--out` is
required. Unknown options are rejected. Layout inputs and their receipts are
never rewritten. Layout output includes the existing layout schema and stable
instance IDs. A `NAME.receipt.json` sibling records sources, changes and
admission, including rejected drafts. `--draft yes` permits exporting a layout
that admission rejects, with the rejection explicitly retained in the receipt.
`--full yes` requests full building/trap inventory; the default permits partial
transcriptions while still checking content, levels, bounds and overlaps.

| Command | Inputs / behavior |
| --- | --- |
| `fit` | `--anchors` JSON array of `{ "tile": [x,y], "screen": [sx,sy] }`; independent least-squares horizontal/vertical fits, RMS pixel residual. |
| `refine` | `--grid`, `--points` array of screen pairs, `--center yes` for cap centers; deterministic local refinement of clipped tile residuals. |
| `lattice` | `--image`, `--grid`, optional `--mask bright`, `--lift 12`; fit line harmonics near the declared grid, resolve periodic origin ambiguity using that grid. |
| `diagnostics` | Same image/grid/mask inputs; fractional-tile histograms and harmonic strength. |
| `walls` | `--image`, `--grid`, optional `--buildings`, `--lift 12`, `--mask legacy` (the original RGB-mean detector) or `pale`, `bright`, `gold`, `dark`, `cyan`; mask modes accept `--threshold`, `--min-run`, `--strong`, `--bx`, `--by`, optional `--scores` JSON output. |
| `trace` | `--walls`, optional `--add`/`--delete` files of `[[[x0,y0],[x1,y1]], ...]` inclusive straight segments; optional `--gap` closes unoccupied straight gaps, recorded separately as imputation. `--buildings` excludes footprints. |
| `build` | `--buildings` text `key x y [mode] # comment`, `T:key` for observed traps; `--walls`, `--th`, `--name`, optional explicit `--metadata` reviewed layout. Drops footprint-conflicting walls with a receipt; preserves explicit modes. Unknown troops/heroes/guardian are empty without metadata. |
| `convert` | `--raw` text `orig key sx sy [mode]`, `abs key x y [mode]`, or `window_name key zx zy [mode]`; `--grid`, optional `--windows` map `{ "name": [origin_x,origin_y,zoom] }`, `--margin 0.45` (+0.3 for camps). Bottom-tip conversion, ties-to-even rounding, bounds clamping. |
| `pads` | `--image`, `--grid`, optional `--buildings` and `--threshold 0.55`; scored cyan lower-V footprint proposals, cross-dilation radius 2, greedy non-overlapping selection. Identities remain unknown. |
| `snap` | `--image`, `--grid`, `--layout`; scores offsets -2..2 and records review recommendations, without silently applying them. |
| `complete` | `--layout`; add missing hidden Teslas inside walls, repair overlaps, add missing traps. Optional explicit `--tesla-radius 12` instead of enclosure; `--replace-traps yes` explicitly discards the input traps. |
| `finish` | `--layout`; repair overlaps and fill missing trap inventory, preserving recorded traps by default. |
| `repair` | `--layout`; nearest free position for conflicts/bounds, utility buildings restricted to outside walls. No building is silently deleted if there is no space. |
| `impute` | `--layout`, `--hints` JSON array `{ "key": "tesla", "center": [hx,hy], "mode": ... }`; nearest free footprint for each explicit hint. |
| `symmetry` | `--layout`, `--pairs` JSON array of building index pairs; explicitly average same-key mirrored positions and record the symmetry assumption. Admission checks the result. |
| `merge` | `--layout`; merge closest Cannon/Archer Tower pairs into Ricochet/Multi-Archer towers toward TH-specific merged inventory, then repair. |
| `inventory` | `--layout`; explicitly impute remaining buildings using TH rules, role proximity and seed 16, rather than global catalog counts. No memory acquisition/import path is included. |
| `seed` | `--layout`; top up walls, then spread missing traps in the enclosed area or convex hull. Optional `--boxes` JSON array `{ "keys": ["giant"], "lo": [x0,y0], "hi": [x1,y1] }`; empty keys means all. Candidate order is sorted and seed 16 is explicit. |
| `overlay` | `--image`, `--grid`, optional `--layout`; village grid, labels, cyan footprints, magenta walls, orange traps. |
| `guide` | `--layout`; labeled isometric build guide on a blank village. |
| `crop` | `--image`, `--x`, `--y`, `--width`, `--height`, integer `--zoom`; optional `--ruler` original-pixel spacing. |
| `dewm` | Crop options plus explicit `--alpha`; inverse white-overlay inspection transform, sigma-3 Gaussian and clamped image boundaries. Source image remains unchanged and the transform is receipted. |
| `windows` | `--image`, `--width`, `--height`, `--zoom`, optional `--stride-x`/`--stride-y`; PNG windows plus an origin/zoom `windows.json` usable by `convert`. |
| `gallery` | `--images` JSON array of PNG/PPM paths; `--columns`, `--width`, `--height` contact-sheet cells. Crop/window commands compose tile-centered galleries. |
| `inspect` | `--layout`, optional `--full yes`; admission and missing TH inventory report. |
| `ascii` | `--layout`; 44x44 occupancy map (`!` marks a conflict). |
| `diff` | `--before`/`--after` JSON; all structural differences, ignoring object order, preserving array order and absent-versus-null distinctions. |
| `replay` | Explicit private input root, reference root and account; see acceptance evidence below. |

`complete` and `finish` accept `--top-up yes`. Any layout-changing command
accepts `--levels FILE --levels-th N`. The declared TH must equal the layout TH,
the account's `town_hall` if present, and `levels.th` if present. In particular,
relabeling the supplied TH16 account as TH18 does not bypass the guard. No
account path is discovered implicitly. Accounts and their receipts remain
private outputs, not fixtures.

Receipts distinguish measured transcription, explicit manual wall edits,
algorithmic imputation, unresolved positions, source identities, inherited
receipts and admission. Completion adds a new output. Hidden structures,
repaired positions, filled wall gaps, assumed symmetry and account overlays are
not presented as measured placements. Missing interior Tesla space is recorded
as unresolved, rather than inventing a position without explicit permission
via a radius/hint operation.

`clash-layout::render::Image` reads binary 8-bit PPM and non-interlaced 8-bit PNG
(grayscale, RGB, indexed, gray-alpha and RGBA; alpha is ignored when producing
RGB, like the old RGB conversion). PNG inflation supports stored, fixed and
dynamic DEFLATE blocks and all five scanline filters, with CRC/Adler checks and
bounded allocation. Output is PPM or PNG with stored DEFLATE blocks. JPEG,
interlaced PNG and low/16-bit PNG are explicitly unsupported. Rendering uses a
portable bitmap font and nearest-neighbor crops/zoom, so image bytes are not
asserted equal to Pillow/font/Lanczos exports.

## Port mapping / deletion eligibility

The retained capabilities of `digitize.py`, `grid_overlay.py`,
`finish_digitized.py` and `complete_digitized.py` are replaced by the commands
above. Their intentional changes are explicit input accounts, TH guards,
receipt-preserving completion, preservation of observed traps, current
8-neighbor exterior geometry, and failing instead of silently dropping a
building when repair has no room. `trace_walls.py` is absent in the frozen tree;
there is no such file to delete. Native `trace` provides that capability.

The toolkit is consolidated by capability, as requested in restructure plan
section 3; it does not retain hardcoded paths, shell subprocess wrappers,
Python expression evaluation or a SciPy runtime:

| Frozen toolkit files (relative to `tools/baselab/digitize_kit/`) | Native replacement |
| --- | --- |
| `cfit.py`, `chk2.py`, `chk3.py`, `chkmap.py`, `fh.py`, `fitoff.py`, `fitoff2.py`, `hfit.py`, `vfit.py`, `wfit.py`; `batch_b/lat.py`, `batch_b/proj.py` | `fit`, `refine`, `lattice`, `diagnostics`, `overlay`. Anchor/harmonic/local fitting replaces the separate scratch optimizers; old checker-score tables and SciPy optimization trajectories are not numerically reproduced. |
| `palewalls.py`, `walls2.py`, `walls3.py`, `wd.py`; `batch_b/walls4.py`, `batch_b/gapfill.py`, `batch_b/wclean.py` | `walls`, `trace`, scored wall JSON. Native fixed masks replace arbitrary evaluated mask expressions. Component/window variants are configurable. |
| `pads.py`, `pads2.py`, `probe.py`, `snap.py` | `pads`, `snap` scores and overlay inspection. A common lower-V score replaces separate proposal variants. |
| `conv.py`, `build.py`, `finalize.py`, `resolve.py`, `seed.py`, `merge_impute.py`, `inv.py`; `batch_b/build.py`, `batch_b/conv.py`, `batch_b/seed.py`, `batch_b/symfix.py` | `convert`, `build`, `repair`, `complete`, `merge`, `inventory`, `impute`, `seed`, `symmetry`, `inspect`. Metadata is an explicit reviewed input. Seed candidates are sorted; seed placement does not claim Python hash-set order parity. |
| `gal.py`, `gal2.py`, `gl.py`, `ov.py`, `ovl.py`, `ovt.py`, `ovw.py`, `sheet.py`, `wins.py`, `zoom.py`, `zt.py`, `ztw.py`, `zw.py`; `batch_b/full.py`, `batch_b/gal2.py`, `batch_b/rul.py`, `batch_b/win.py`, `batch_b/dewm.py` | `overlay`, `crop`, `windows`, `gallery`, `guide`, `dewm`, portable raster primitives. Compose operations for full/grid-only/window/contact-sheet views. |
| `ascii.py`, `dots.py`, `diff.py` | `ascii`, `overlay`, `diff`, `diagnostics`. |
| `blobs.py`, `cands.py`, `ccparse.py`, `rt.sh`, `win.sh` | Excluded hardcoded acquisition/scratch wrappers under the plan; no port. The two `*_buildings.txt` files are reviewed input data, not programs. |

The four main Python tools can be deleted after integration accepts the gates
below. The toolkit's supported workflows have native substitutes, but any
consumer requiring the exact old checker metrics, every SciPy fit trajectory,
weighted parity-snap experiment, expression masks, or Pillow/JPEG pixels still
needs migration; exact parity for those scratch variants is not claimed.
No Python file was edited or deleted in this lane.

## Acceptance evidence

Build and verification use WSL, `. ~/.cargo/env`, the offline workspace, and
`CARGO_TARGET_DIR=/tmp/clash-target-lD`.

Portable tests cover known-answer projection/anchor fitting and conversion,
synthetic RGB wall runs versus grass, explicit wall traces/gap exclusions,
synthetic Tesla selection, trap inventory/idempotence, cross-TH overlay
rejection (including misleading declarations), seed inventory/admission,
source-preserving CLI behavior, unknown-option rejection, structural JSON
comparison, PNG stored/fixed/dynamic compression and raster corruption.
The two small PNG inputs under `testdata/` are declared synthetic red-to-blue
gradients generated with ImageMagick during development; tests require only
the frozen bytes and assert dimensions/colors. They contain no screenshot or
account information. The physical fixture constructed by tests is synthetic,
not a real-game calibration fixture.

The native PNG decoder also decoded the private `t18a-alexpate99.png` screenshot.
Its PPM export compared byte-for-byte equal to ImageMagick's independent PPM
export. The native grid/footprint/wall/trap overlay was visually inspected. All
private image exports and comparison outputs are under `/tmp`, not in Git.
ImageMagick was only an existing local development oracle and is not called
by Rust, tests or verification.

Private replay command (the account is explicit, read only):

```sh
. ~/.cargo/env
CARGO_TARGET_DIR=/tmp/clash-target-lD cargo run --release --offline --locked \
  -p clash-cli --bin clash -- dataimport digitize replay \
  --inputs /mnt/c/Users/jarod/Documents/clash-lab/local/digitize \
  --references data/source/reference-bases \
  --account private/your-levels.json \
  --account-th 16 --out /tmp/clash-lD-replay
```

For each of 14 bases, replay reconstructs the layout from `buildings.txt`,
`grid.json` and the reviewed walls before reading the reference for comparison.
The October 24 folders lack standalone `walls.json`; their saved
`layout.json.walls` supplies that reviewed intermediate. Saved `layout.json`
also supplies measured metadata and observed traps; committed reference
coordinates are never copied into the rebuilt layout.

Replay writes default-policy, four-neighbor diagnostic and explicitly declared
historical-assumption variants, with receipts, all current-policy field
comparisons, and a `summary.json`. It fails if any historical physical layout
differs or fails partial admission. Object order, whitespace and additive
schema/instance IDs are normalized for comparison; building/trap array order,
modes, every coordinate and sorted wall arrays are compared exactly.

| Bases | Default-policy physical differences | Historical replay |
| --- | --- | --- |
| `rb01`, `rb04`–`rb07`, `rb09`, `rb10` | 0 | Exact buildings/walls/traps |
| `rb02` | 15 scalar field differences | Exact with four-neighbor exterior flood |
| `rb03` | 28 scalar field differences | Exact with four-neighbor exterior flood |
| `rb08` | 16 scalar field differences | Exact with four-neighbor exterior flood |
| `r18a`, `r18c` | 0 | Exact buildings/walls/traps |
| `r18b` | 5 missing Tesla objects | Exact with the reference's documented later radius-12 Tesla fallback, after trap placement |
| `r18d` | 97 trap-array scalar differences | Exact with legacy trap replacement; the source's observed Giga Bomb at (21,20) is deliberately retained by the native default |

The four-neighbor replay establishes the historical geometry explanation for
`rb02`, `rb03` and `rb08`; the current eight-neighbor geometry is unchanged.
Changing Tesla footprints also changes available trap tiles. `r18b`'s measured
274-wall transcription has no enclosed free 2x2 footprints. The historical
fallback reproduces its later five assumed positions without copying their
coordinates from the reference. The trap-array count for `r18d` includes index
shifts caused by preserving its measured trap before imputed traps.

All 14 historical physical layouts match, all 14 historical variants pass
partial admission, and all 14 default-policy variants pass partial admission.
Default-policy metadata differences are exhaustive in `<id>.diff.json`:

- All 14 keep their measured narrative instead of appending the legacy
  completion/account/reference prose; assumptions are in the receipts.
- All four TH18 layouts retain unobservable/empty source CC troops, whereas
  the references assumed the legacy default seven troops.
- All four TH18 layouts retain observed defending hero levels; the committed
  references cleared these maps to use TH18 maxima. TH16 levels are never
  overlaid onto these bases. `r18a`, `r18b`, `r18d` have four observed hero-level
  entries; `r18c` has three.
- The 10 TH16 account setups match their committed reference setups exactly.

There is no claim of byte-identical legacy layout JSON or pixel-identical
rendering. Every material default-policy difference is recorded with its JSON
path, old/new value and explanation. These are screenshot regression checks,
not real-game calibration or verification of uncertain hidden placements.

Final full-gate result and frozen hashes are recorded below after verification.

Account compatibility detail: legacy level files without `town_hall` or
`levels.th` are accepted only as TH16, matching the supplied legacy input.
Other Town Halls require an embedded numeric Town Hall matching both the layout
and `--levels-th`. A real-file rejection check confirmed that declaring the
untyped TH16 account as TH18 fails before producing a layout.

The worktree's `.git` file contains a Windows path, which ordinary WSL Git
cannot resolve. The first gate passed compilation, tests, battle/plan goldens,
guardian and armysearch proofs, then stopped at layout proof's `git ls-files`.
The final gate uses read-only Git path overrides, without editing Git metadata:

```sh
. ~/.cargo/env
GIT_DIR=/mnt/c/Users/jarod/Documents/clash-lab/.git/worktrees/clash-lab-lD \
GIT_WORK_TREE=/mnt/c/Users/jarod/Documents/clash-lab-lD \
GIT_OPTIONAL_LOCKS=0 \
  scripts/verify.sh /tmp/clash-target-lD > /tmp/clash-lD-verify-final.log 2>&1
```

Additional recorded-output equivalence: native `walls --mask legacy` on the
private TH18-a screenshot and saved grid produced exactly the same sorted 807
candidate coordinates as its saved `walls-detected.json`. This tests the actual
RGB sampling, projection, color thresholds and component filtering against an
existing detector output, independently of layout reconstruction from reviewed
walls.

Integration follow-up: this lane leaves all Python deletions and the commit to
the integration lead. The planned `clash data digitize` spelling/help update is
also integration-owned; the existing `clash dataimport digitize` dispatch works.
Exact legacy scratch numeric/pixel variants listed above remain outside the
claimed equivalence. The reusable renderer and all supported command code are
contained in the assigned paths; there is no requested shared-kernel change.

## Final verification receipt

The finished-source invocation above exited **0** and ended with
`ALL CHECKS PASSED`. Full log: `/tmp/clash-lD-verify-final.log`.

- `cargo fmt --all -- --check`: passed.
- Locked offline release build, workspace and all targets: passed.
- Workspace release tests: 93 passed, 0 failed; 2 pre-existing documentation
  examples ignored. Eight focused tests belong to this port (seven dataimport,
  one layout renderer). The final video test invocation also passed 24/24.
- Battle goldens: 868/868 at one worker and 868/868 at four workers.
- Plan goldens: 1354/1354. Guardian fixtures: 50/50.
- Armysearch: 4096 legality cases and 4096 program cases, worker determinism,
  resume/cache/budget/holdout proofs passed.
- Layout: importer/inventories, boundary/geometry and 100000 mutations passed;
  2944 accepted and built, 97056 structured rejections, 23 committed corpus
  layouts checked.
- Basesearch M2: 93000 operator attempts, 81864 accepted engine builds,
  3000 accepted crossovers, workers 1/4/16/1 passed.
- Finished release digitizer: 14/14 historical physical layouts equal and
  admitted; current-policy/metadata differences recorded. The wall detector
  again reproduced all 807 saved candidates, with an empty structural diff.
- Independent PNG-to-PPM comparison, real-account TH mismatch rejection and
  read-only Git diff whitespace checks passed.
- Clippy is absent from the installed toolchain. The gate reports this;
  no component was downloaded and no Clippy audit is claimed.

Frozen golden SHA-256 values, checked again after verification:

```text
cea706d86516a2100876f9aa4ec7cdd5de32f691202f9a6d049b64e690d172ab  cases.jsonl
40446127d538f7bab2a86ab9c7fcae8b3a725c4ceb462fd2d95236cb38af0ab4  expected.jsonl
3ea43b38a16c4608aa04ab308c2a0e1ba645ed2cd3b89ad386235d8c44d32681  plans.jsonl
```

Final gate tail:

```text
   Doc-tests clash_vidmine

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

ALL CHECKS PASSED
```

All changes are inside the assigned paths on `port-lD`. No Git index/commit,
Python source, golden bytes, main-checkout data/output files or protected
checkout was written. Private replay layouts, accounts in receipts and image
exports remain in `/tmp` only. The integration lead can stage these assigned
Rust modules, this report and the two declared synthetic PNG fixtures after
reviewing the gate.
