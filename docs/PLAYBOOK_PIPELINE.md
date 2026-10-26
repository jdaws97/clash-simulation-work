# Native playbook and research pipeline

`clash playbook` implements the deterministic playbook/research workflow in
`crates/clash-playbook-tools`. It uses the workspace JSON implementation and
standard library only. The simulation executor and its unsupported-content
checks are unchanged. No Python runtime, package install, provider credentials,
or network access is required for local import and verification.

The default root is the workspace containing the executable's source. Supply
`--root`, `--sources`, `--transcripts`, `--playbooks`, and output paths explicitly
when working with another corpus. Inputs in another checkout can remain
read-only. Acquisition caches, transcripts, prompts, provider replies, research
reports and job receipts belong in ignored local storage, never in Git.

## Commands and file contracts

```sh
# Import a discovery response (YouTube videoRenderer tree, yt-dlp entries,
# ordinary rows, a JSON array, or JSONL). Repeat for another family.
clash playbook harvest --family dragon --input search.json \
  --query 'th17 hydra attack strategy' --date 2026-10-25 \
  --out output/sources/videos.jsonl

# Import a stored transcript, yt-dlp json3 subtitles, or format-3 timedtext XML.
clash playbook transcript VIDEO --input captions.json3 \
  --transcripts output/sources/transcripts

# Check every committed playbook and write detailed per-citation diagnostics.
clash playbook verify --all --transcripts output/sources/transcripts \
  --report output/sources/citation-report.json

# Check a raw extraction offline; --dry suppresses its checked JSON write.
clash playbook verify --extracted VIDEO --sources output/sources

# Consolidate supplied model output into an executable source playbook.
clash playbook consolidate dragon --sources output/sources \
  --transcripts output/sources/transcripts --out data/playbooks/dragon.json

# Merge verified additions, or inspect without writing with --dry.
clash playbook complete dragon --input output/sources/completion/dragon.raw \
  --transcripts output/sources/transcripts --dry

# Recompute timing data, excluding test-* playbooks as the frozen tool did.
clash playbook gaps --transcripts output/sources/transcripts \
  --out output/sources/playbook-gaps.candidate.json
```

`videos.jsonl` retains one row per video with `id`, `title`, `channel`, `age`,
`length`, `families`, `query`, `age_days`, and `harvested`. Existing fields and
insertion order survive updates. Duplicate videos gain a family without
replacing their original query. The relative-age units and 183-day default
match `harvest_videos.py`; unknown ages and videos beyond the limit are skipped.
An `upload_date` from a provider is also accepted. Saved videoRenderer trees
use the original recursive discovery rules. Default queries cover all twelve
families in the frozen harvester.

Stored transcripts retain metadata and `lines: [[seconds, text], ...]`.
Existing normalized records retain their caption boundaries and metadata.
json3 and timedtext imports join segments, collapse whitespace, and round
milliseconds to one decimal second with ties to even. Format-3 timedtext uses
word spans in preference to direct paragraph text, as the original did.
Malformed input returns an error rather than supplying invented captions.

Normal consolidation requires supported actions, anchors, typed triggers,
unique IDs, valid declared dependencies, and a verified citation from the
family's declared source set. Invalid default steps/citations are removed with
reasons. Unsupported nested variant/support evidence prevents a strict write.
It never turns an uncited model reply into learned evidence. Existing trusted
playbooks can explicitly distinguish `uncited: true` or `provenance: learned`;
these items are counted separately and never counted as verified citations.

Default, variant, spell-support and aim citations are all inspected. Variant
references are checked in the context of their declared base and replacement
steps. The compiler remains responsible for inventory/loadout fitting, recipe
selection, removal/relinking and final executable-plan feasibility. The schema
contract test checks action, anchor and trigger vocabularies against the actual
Rust executor source, including newer objective/effect/cohort triggers and
`arrow`/`dash` aiming modes. No engine dependency or shared-crate edit was added.

Completion accepts only new IDs, dependencies on existing/previously accepted
steps, and verified family-source citations. It records `verified_t` and
`completion: true`. Placement retains original siblings' priority, follows the
referenced step, and puts time-only additions at the front, matching
`merge_completion.py`. Rejections remain explicit in the receipt.

## Citation compatibility and strict review

The port preserves `check_playbook.py` exactly for well-formed replies:

- Lowercase; replace every character outside ASCII `a-z`, `0-9` and spaces
  with a space; collapse whitespace; trim.
- Require at least six normalized characters and whole-word matches.
- Search at most four caption lines, including empty lines in that bound.
  Credit only the caption line where the quote begins.
- Select the nearest occurrence within 30 seconds inclusive; preserve the
  first occurrence on equal-distance ties. Without a stated time, use the
  first occurrence.
- Preserve the frozen brace-counting reply parser, including its treatment
  of braces inside strings. Compatibility never silently repairs model text.
- Filter the five extraction arrays and record kept/dropped and `verified_t`.

`verify --legacy` restricts citation review to the frozen consolidation
checker's default `steps` and `base_reading` scope. Current vocabulary and
source-level dependency validation still covers variants and support steps.
`consolidate --legacy` reproduces the old filtering and its limited
`dangling_after` diagnostic; use it for comparison, with `--dry`. Normal
consolidation enforces stronger checks and recognizes the current executor.

```sh
# Compare to saved Python outputs, without running Python or changing data.
clash playbook verify --all --legacy \
  --sources /path/to/read-only/output/sources \
  --transcripts /path/to/read-only/output/sources/transcripts \
  --check-recorded --report /tmp/playbook-equivalence.json
```

`--check-recorded` rechecks every `.raw` with a saved extraction `.json` and
compares all five filtered arrays, verification times and check verdicts. It
also rechecks each saved consolidation reply against the committed `check`
record. A missing transcript, mismatch or validation error fails the command
and remains in the report. The strict audit also fails unsupported evidence;
it does not call a wiki citation a verified video quote.

## Explicit external provider steps

Local input is always sufficient. These optional commands invoke an executable
already installed by the user; they never install it:

```sh
# Discovery only. A page is a bounded batch of 20 yt-dlp search results.
clash playbook harvest --family dragon --provider yt-dlp.exe --pages 2

# Subtitles and metadata only; no video or audio download.
clash playbook transcript VIDEO --fetch --provider yt-dlp.exe \
  --transcripts output/sources/transcripts

# Inspect extraction jobs first, then explicitly invoke a configured provider.
clash playbook extract --transcripts output/sources/transcripts
clash playbook extract --transcripts output/sources/transcripts \
  --run --provider /path/to/codex-ask --workers 3
```

In WSL, Windows `.exe` subtitle output paths are converted with the installed
`wslpath`. The subtitle provider receives `--ignore-config`, `--skip-download`,
English subtitle selection, json3 format and metadata output options. Fetches
stage in a unique local directory and publish normalized JSON only on success.
Human subtitles take precedence according to yt-dlp's subtitle selection;
its availability and YouTube access are explicit provider concerns. Search
results without usable age/date information remain excluded. Acquisition was
not exercised in this lane: tests use shell stubs for process handling and
never call a live acquisition or LLM provider.

Extraction reads `docs/playbook-extraction.md` or an explicit `--brief FILE`,
selects nonempty transcripts, saves raw replies and always regenerates checked
JSON. The provider receives its configured `--provider-arg` arguments followed
by one prompt argument. A wrapper around an installed `codex` executable can
adapt that contract; no particular home-directory wrapper is required. Model
extraction and consolidation remain external authoring steps, followed by
mandatory native evidence validation.

## Research and audit bookkeeping

```sh
clash playbook queue import --input subjects.tsv --out output/research/queue.tsv
clash playbook queue usage --queue output/research/queue.tsv
clash playbook queue usage --queue output/research/queue.tsv \
  --brief output/research/brief-entity.txt --run \
  --provider /path/to/codex-research --workers 4 --passes 2
clash playbook queue audit --input output/research/usage \
  --brief output/research/brief-gap.txt --out output/research/gaps \
  --skip output/research/gaps/skip-event.txt
```

Queue rows are `kind<TAB>name`. Slugs follow the shell scripts' ASCII lowercase
and punctuation-to-hyphen rules; collisions are rejected before workers start.
Usage results must exceed 1,500 bytes and audit results 800 bytes. Audit names
come from the usage report's first heading. Event skip lists remain supported.
Offline status never launches a provider. Add `--run --provider EXE` to execute
an audit, and `--report FILE` to save machine-readable status/results.

Workers are bounded (1–32), retries are bounded (1–10), and only successful,
nonempty/large-enough stdout is atomically published. Extraction also requires
a parseable object. Failed process output never replaces a completed result;
failures produce nonzero CLI status. Per-job `.jobs/<slug>.json` receipts save
prompt, input hash, provider configuration, minimum size, attempt/status and
output hash. Resume checks those identities and hashes. Pre-existing results
accepted under the old size-based rule are explicitly marked `imported_legacy`.
These receipts are local bookkeeping, not proof of factual research accuracy.

## Port receipt (2026-10-25)

All twelve committed `data/playbooks/*.json` files were read against the main
checkout's read-only `output/sources/transcripts` (346 stored transcripts).
No source data, golden, Python file, shared crate or Git metadata was edited.

- Frozen scope: **1,054/1,054 citations verified**, no validation errors.
- Saved checker equivalence: **260 extracted replies**, **6,201 kept / 3
  dropped items**, **11 consolidated replies**, **zero verdict differences**.
  The release CLI also passes that complete comparison with
  `PATH=/no-external-tools`, making Python and all provider executables
  unavailable during the check.
- Expanded scope: **1,844 verified video citations**, zero rejected video
  citations, and **one unsupported non-video citation**. The existing
  `electro-dragon.json` `support_edrag_invisibility` cites a wiki URL/title
  without video or time. The strict audit rejects it; the frozen checker did
  not inspect `spell_support`. The committed input is unchanged.
- All default, variant and support steps pass vocabulary/dependency checks.
- Strict consolidation also passes an offline dry run over all eleven stored
  raw consolidation replies; no candidate source files were written.
- Thirteen focused tests use declared synthetic inputs: exact normalization,
  quote boundaries/window/ties, frozen extraction and consolidation verdicts,
  current executor vocabulary, dependencies, source restrictions, completion
  order, transcript formats, discovery merging, timing quartiles, queue
  thresholds/skips, offline CLI flow, and provider failure/resume identities.
- The timing algorithm passes its synthetic known answers. On today's corpus
  it gives same-group median **4.5**, n **58**, quartiles **[2.5, 4.5, 14.5]**;
  group-change median **17.5**, n **17**, quartiles **[6.1, 17.5, 23.1]**.
  The pinned file has older n **50/16** and medians **4.5/16.6**. This is a
  recorded-input drift requiring review, not a claimed match or data rewrite.

Local evidence: `/tmp/clash-lE-citation-report.json` (expanded audit),
`/tmp/clash-lE-equivalence.json` (frozen scope and recorded-output comparison),
`/tmp/clash-lE-gap-report.json`, `/tmp/clash-lE-queue-status.json`,
`/tmp/clash-lE-tests.log`, and `/tmp/clash-lE-verify.log`.

After callers switch to these native commands, the deterministic behavior in
`harvest_videos.py`, `yt_transcript.py`, `check_playbook.py`,
`check_consolidated.py`, `merge_completion.py` and `step_gaps.py` is replaced.
`extract_playbooks.sh`, `research_usage.sh` and `audit_usage.sh` are replaced by
explicit native process jobs and offline checks. None was deleted in this
ownership-limited lane. Live provider acquisition remains untested; the wiki
support citation and stale timing data need source-owner review.
`verify_audit.py`'s separate wiki-finding ledger and `audit_fanout.sh` are outside
this requested command port and remain unported. These checks establish
pipeline regression behavior, not real-game calibration or research accuracy.

The WSL gate needs the worktree's Windows-style `.git` marker mapped to its
Linux path in this environment. The successful invocation uses these read-only
Git settings (no metadata/index writes and no source change):

```sh
. ~/.cargo/env
export GIT_DIR=/mnt/c/Users/jarod/Documents/clash-lab/.git/worktrees/clash-lab-lE
export GIT_WORK_TREE=/mnt/c/Users/jarod/Documents/clash-lab-lE
export GIT_OPTIONAL_LOCKS=0
CARGO_BUILD_JOBS=4 scripts/verify.sh /tmp/clash-target-lE
```

`git status` with that mapping confirms branch `port-lE` and changes only under
`crates/clash-playbook-tools/` plus this document. `git diff --check` passes.
The three golden SHA-256 values match the frozen values in RESTRUCTURE_LOG.md.
The offline bookkeeping review also read 44 usage queue subjects and 178 audit
subjects with the existing skip list; it invoked no provider and wrote reports
only under `/tmp`.

Final gate exit status: **0**, ending with:

```text
   Doc-tests clash_vidmine

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

ALL CHECKS PASSED
```

The gate includes formatting, offline workspace build/tests, battle goldens at
1/4 workers, 1,354 plan goldens, guardian fixtures, armysearch proofs, 100,000
layout mutations, base-search proofs and vidmine tests. Clippy is unavailable
in the installed toolchain; the gate reports it without installing anything.
Final golden hashes remain `cea706d8…172ab`, `40446127…f0ab4`, and
`3ea43b38…32681`, matching the full frozen hashes in RESTRUCTURE_LOG.md.
