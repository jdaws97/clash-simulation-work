> Predecessor Python filenames and parity procedures in this document are
> historical provenance from `f04706c`. Deleted tools are not runnable; see
> [the current documentation](../../docs/README.md) for native commands and remaining Python ports.

# Lane lC: native observation ingestion and fidelity

Worktree: `clash-lab-lC`, branch `port-lC`. No commit or index write.
Only `crates/clash-dataimport/src/battlelog/**` and `crates/clash-fidelity/**`
were edited. No shared-root, manifest, dependency, engine, Python, source-data,
or golden changes were needed. The existing umbrella `dataimport` dispatcher
already exposes the new commands.

## Native capabilities

- `BattleLogSource` implementations for local JSON, JSONL, stdin, and explicitly
  configured keyless HTTPS. `HttpTransport` is injectable. The production HTTPS
  adapter uses installed curl for TLS, with no shell, curlrc, redirects,
  authentication option, API key, or credential prompt. No Rust dependencies,
  downloads, or installation were added.
- HTTP retries transient transport errors, 5xx, and 429 up to three attempts.
  Numeric `Retry-After` seconds are honored up to 60 seconds; a larger delay
  returns the error instead of retrying too soon. Other retry delays are 1/2
  seconds. 401/403 and 404/410 are explicit unsupported results. After-cursor
  pagination is opt-in, percent-encoded, bounded, and rejects loops; an
  unconfigured cursor fails rather than silently truncating results.
- Collection preserves the original `(battleTimestamp, opponentPlayerTag,
  attack)` dedupe tuple, including within one response. This deliberately differs
  from fidelity's `(timestamp, opponent TH, share code)` observation hash.
  Existing archive bytes are retained, malformed existing or incoming rows are
  rejected, and known player-tag mismatches fail. Older archives with no player
  tag remain importable; the caller must associate them with the correct player.
- `battles.jsonl` retains legacy `fetched`, `player_league`, and
  `player_trophies`, plus UTC `fetched_at`, provider, and player tag. Imported
  rows retain their existing context. New collection receipts always identify
  the importing provider/time. Exact source response bodies are retained under
  `raw/`, addressed by SHA-256, so runtime f64 normalization cannot destroy the
  original bytes. `collections/` binds those hashes to provider, UTC fetch time,
  and player. `player-latest.json` stays compatible with account readers;
  timestamped, hash-addressed player contexts also go under `players/`.
- Writers use a create-new advisory lock and same-directory temporary files,
  sync, and rename. Existing files remain intact on validation failure. Each
  file is atomic; the whole collection is not a filesystem transaction and can
  safely be retried after interruption. A crash can leave a `.lock` requiring
  explicit recovery after checking that the writer has stopped. New Unix data
  files have mode 0600; choose a private output directory on every platform.
- Snapshot `add`, `list`, `for-battle`, and `report` preserve explicit historical
  inputs, trap-level merge precedence, positive integer validation, per-wall
  validation, hero/banner order, field provenance and unknown-confidence marks
  for absent levels. They never import today's account into a frozen setup.
  Effective periods are UTC and half open. A new period closes an earlier open
  period; overlaps and changed archived snapshot bytes are rejected.
- Snapshot canonicalization uses the existing shared canonical/hash routines
  and retains original integer versus float tokens during field merging. The
  shared data snapshot reader and fidelity accept the resulting files directly.
- Import and fidelity both use `clash_data::battlelog::Decoder`; there is no
  second share-code parser. Unknown names and malformed hero suffixes retain
  their diagnostic forms, and fidelity retains unsupported-build rejection.
- Fidelity CV always fits native, stable-ID folds with training/evaluation
  separation and verified disjoint hash-bound ancestry. Implicit CV2 training,
  fit/report, and pooled metric paths have been removed. `--reference FILE`
  optionally compares supplied saved metrics, accepts either flat metrics or
  a native report's `pooled` object, and records its file hash. Missing metrics
  fail; null measurements produce null differences. Retired `--reference-cv2`,
  `--archive-cv2`, and `--python` flags return a migration error. Exported native
  plans retain Warden mode. The exposed-eagle board check now requires explicit
  `--base FILE`; report discovery no longer scans `output/overnight`.

## Commands

From the repository root, using an offline-built `clash` executable:

```sh
clash dataimport battlelog decode 'h2m1p2e4_34u1x0' --root "$PWD"
clash dataimport battlelog collect --provider local-json --tag '#P0' \
  --input /private/log.json --player /private/player.json --out /private/archive
clash dataimport battlelog collect --provider local-jsonl --tag '#P0' \
  --input /private/log.jsonl --out /private/archive
cat /private/log.jsonl | clash dataimport battlelog collect \
  --provider stdin --jsonl --tag '#P0' --out /private/archive
clash dataimport battlelog snapshot add /private/layout.json \
  --root "$PWD" --history /private/base-history.json \
  --levels /private/historical-levels.json --from 2026-10-21T05:00:00Z \
  --period league-day --source screenshot --confidence medium --notes 'Day 1'
clash dataimport battlelog snapshot list --history /private/base-history.json
clash dataimport battlelog snapshot for-battle 20261021T183738Z \
  --history /private/base-history.json --battles /private/archive/battles.jsonl
clash dataimport battlelog snapshot report --history /private/base-history.json \
  --battles /private/archive/battles.jsonl
```

`fetch` is an alias of the one-shot `collect`; neither polls indefinitely.
`--fetched-at` accepts an explicit timestamp for reproducible local imports;
otherwise the clock supplies UTC. No player, endpoint, or output defaults exist.
JSON input accepts an `items` envelope, array, or single battle object.

A configured provider can use the user-supplied ClashKing v2 history endpoint:

```sh
clash dataimport battlelog collect --provider http --provider-name clashking-v2 \
  --endpoint 'https://api.clashk.ing/v2/player/{tag}/battlelog/history' \
  --tag '#P0' --out /private/archive
```

This is a configuration example, not evidence that the endpoint is available.
Per the task's provider constraints, v2 history covers tracked players only;
empty stored history does not establish a complete observation window. There
is no default dependency on the old down proxy or a token-based replacement.
If a keyless provider supports profile capture, explicitly configure
`--player-endpoint 'https://host/players/{tag}'`. If it supports after-cursor
pagination, configure `--cursor-parameter after`. No live HTTP request was used
for development or tests. Local providers have no curl dependency.

## Equivalence evidence and deletion readiness

All added fixtures are explicitly synthetic. Expected decoder sections and the
frozen snapshot payload were authored independently from the inspected legacy
contract; no Python reference process was executed. The canonical known-answer
snapshot payload has SHA-256
`a3a67deb92486cb1ddaaf05356ce4cde9cf93d021a9aac73a1c817795ed8cfc8`.
Tests compare its complete bytes, exercise integer/float distinctions, and load
recorded snapshots through the existing shared reader with hash verification.

Focused tests cover known share codes and malformed content, distinct collector
and fidelity identities, repeat/no-op collection, player context, preservation
of existing bytes on errors, local parsing, 401/403/404/410/429/522 handling,
retry timing, cursor encoding/loops, UTC boundary closure, overlap rejection,
canonical snapshot hashes/tamper rejection, missing-level provenance, report
means/intervals/deduplication, saved metric comparisons, and retired modes.
These establish native synthetic regression behavior, not real-game calibration.

The following workflows are fully replaced and their Python implementations
can be removed by the integration lead once remaining Python callers are retired:

- `tools/baselab/snapshot_log.py`: keyless collection, append/dedupe, context capture.
- `tools/baselab/decode_battlelog.py`: shared decoder and native decode commands.
- `tools/baselab/snapshot.py`: recording, validation, history lookup and reports.

No predecessor was deleted in this lane because `src/` and `tools/` are frozen.
Remaining Python replay/calibration tools may still import these modules; source
removal must be coordinated across their callers. This lane does not claim the
aggregate-target `calibrate.py` or per-build `calibrate_meta.py` modes have been
ported. Existing native fidelity replay/observed/board/fit/CV remain available,
with their existing ancestry and unsupported-content checks.

Remaining integration work is optional umbrella spelling (`clash data snapshot`
versus the already-wired `clash dataimport battlelog snapshot`), live provider
contract/availability checks, and Windows acceptance. Archived comparison files
were retained untouched. Active fidelity source has no Python execution, Python
source imports, or implicit frozen-Python output paths. Explicit saved JSON
comparison data and supplied historical prepared jobs/outcomes remain usable.

## Verification receipt

The WSL invocation uses read-only Git environment overrides because this Windows
worktree's `.git` pointer contains a `C:/...` path. The initial unmodified
invocation reached layout corpus enumeration and failed to resolve that pointer;
no Git metadata or shared verification code was changed to address it.

```sh
. ~/.cargo/env
GIT_OPTIONAL_LOCKS=0 \
GIT_DIR=/mnt/c/Users/jarod/Documents/clash-lab/.git/worktrees/clash-lab-lC \
GIT_WORK_TREE=/mnt/c/Users/jarod/Documents/clash-lab-lC \
  scripts/verify.sh /tmp/clash-target-lC > /tmp/clash-lC-verify.log 2>&1
```

Native CLI smoke tests ran with `PATH=/nonexistent`, covering JSON collection
and dedupe, stdin JSONL import, byte-identical dataimport/fidelity decoding,
snapshot add/list/for-battle/report, and rejection of retired CV2 flags.
Receipts and exclusively synthetic input/output files are under
`/tmp/clash-lC-cli.fR8oLkYk`. A `cmp` verified that the saved raw log exactly
matches its input; archive and latest-player files were confirmed mode 0600.

Final gate exit status: **0**, ending in **ALL CHECKS PASSED**. The complete log
is `/tmp/clash-lC-verify.log`. This run rebuilt and checked the final Rust source.
No source changes followed it; only this Markdown receipt was completed.

| Check | Result |
| --- | --- |
| Workspace formatting | `cargo fmt --all -- --check` passed |
| Release workspace, all targets | `--locked --offline` build passed |
| Workspace release tests | 95 passed, 0 failed; 2 existing doc examples ignored |
| Focused port tests | 8 ingestion tests and 9 fidelity tests passed; 10 new tests total |
| Battle goldens | 868/868 at 1 worker; 868/868 at 4 workers |
| Plan goldens | 1354/1354 |
| Guardian check | 50 declared synthetic fixtures passed |
| Army-search proof | 4096 legality and 4096 program iterations; determinism/resume/ancestry checks passed |
| Layout proof | 100000 mutations; 2944 accepted builds, 97056 structured rejections; corpus 23 |
| Base-search M2 proof | Full configured operator/crossover/determinism proof passed |
| Final video tests | 24 passed, 0 failed |
| Golden bytes | All three SHA-256 values match the frozen restructure log |
| Diff whitespace | `git diff --check` passed |

Clippy is unavailable in the installed toolchain. The gate reported that
limitation; no component was downloaded and no Clippy audit is claimed.
After the final rebuild, collection/dedupe, raw log/profile byte equality,
decoder equality and snapshot reporting were rechecked with `PATH=/nonexistent`.
Those final synthetic receipts use `archive-final/` within the CLI directory above.

Final gate tail:

```text
test result: ok. 24 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.02s

   Doc-tests clash_vidmine

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

ALL CHECKS PASSED
```
