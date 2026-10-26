# H1 fixes — 2026-10-25

Baseline: branch `sim-accuracy`, HEAD `e05444d`. Findings are recorded in
`local/evidence/hunt-ported-2026-10-25.md`. All fixtures added here are declared
synthetic checks, not real-game calibration. No source values or battle
mechanics were changed. The work is intentionally uncommitted.

## 1. Cross population entries with execution skill

Before: army selection used `index % population.len()` while strength used the
group seed modulo five. A population of five armies therefore assigned each
army one permanent skill bin.

After: `clash-basesearch/src/cli.rs::manifests` advances the skill bin after
each complete pass over the population. Every army receives all five bins;
per-army bin counts differ by at most one. Budgets below five groups per
population entry now fail explicitly. The smoke configuration and documented
example use ten groups for their two-entry population.

Regression: `population_crosses_all_five_skill_bins` builds 50 groups for five
distinct genomes and requires exactly two observations of every bin for every
genome, identical skill on both side candidates, and rejection of insufficient
coverage.

## 2. Isolate manifest seed streams and reject collisions

Before: configurable screen and final seed offsets could coincide, repeating
compiled plans, hidden draws and execution randomness across the holdout.

After: a stable hash of manifest name/role and configured seed determines each
48-bit group stream. `Manifest::ensure_disjoint` checks group seeds, prepared
plan seeds and the actual scouting draw seeds exposed by
`clash-scoring::scouting::sample_seeds`. The CLI checks development, gate,
untouched final and every wave screen together before evaluating battles.
Collisions return an error naming both manifests and the shared seed.

Regression: `manifest_namespaces_prevent_reported_collision_and_check_detects_overlap`
uses the reported `battle_seed=3298534983151` and `final_seed=99823`, verifies
isolation, verifies different roles with the same configured seed are disjoint,
and deliberately clones samples under a different name to require an error.

## 3. Use fresh samples for adaptive racing

Before: later candidates descended from parents selected using the same screen
on which they subsequently raced. Fixed-candidate alpha spending did not cover
that adaptive reuse.

After: each wave receives a separately named, disjoint screen manifest, saved as
`screen-wave-N.json`. Candidates and incumbent identities are frozen before
observing that screen. Incumbents are evaluated again on the new screen, and
paired elimination uses those fresh rows. Those battles are charged to the
existing physical budget. Search rejects consumed screen seeds before changing
state, including after checkpoint resume. Checkpoint schema is now **4**;
schema 3 cannot establish the new sampling history and is rejected.

Regression: `adaptive_racing_reuse_has_false_eliminations_and_fresh_samples_do_not`
uses 32 deterministic trials, 4,096 groups per trial, and an adaptive subset
family over 1,048,576 possible observations. An incumbent memorizes its training
draws; its exact population utility remains below a fixed challenger. Reusing
the training samples falsely eliminates that better challenger in **32/32
trials (100%)**; independent fresh samples do so in **0/32 (0%)**. These are
synthetic counterexample rates, not an estimate of real-game error rates or a
general statistical guarantee. The check is also included in the native
`basesearch proof-completion` receipt under `adaptive_racing`.

`exact_checkpoint_waves_and_thread_counts` additionally checks fresh-screen
continuation, rejection of a reused screen without state mutation, deterministic
resume, and agreement at 1/4/16 workers.

## 4. Protect gallery source images

Before: output protection checked the `--images` manifest path but omitted the
image paths listed inside it.

After: gallery validates every listed path, canonicalizes those paths through
the existing output guard, and checks both the output and its receipt against
every image before loading or writing the gallery.

Regression: `gallery_refuses_canonical_source_image_aliases` supplies a disposable
synthetic image and an output alias containing `nested/..`. It requires an error,
byte-identical source contents and no output receipt.

## 5. Align authoring and executor field types

Before: verification accepted `what:{}`, `origin:{}` and `spread:null`; executor
loading then panicked when reading strings or a number.

After: shared `clash-data::content::validate_playbook_step_types` checks these
fields (and the other string anchor/group fields). It preserves null only where
the executor treats it as absent. Authoring validation calls this contract;
engine setup validates prepared playbook steps and returns
`ContentError::Invalid` before loading them.

Regressions: `malformed_executor_fields_fail_authoring_validation` requires a
field-specific validation failure for each reported case;
`malformed_playbook_fields_return_setup_errors` inserts the same cases into a
frozen synthetic prepared plan and requires engine setup errors without panic.

## 6. Reject empty and duplicate share-code sections

Before: codes without sections decoded to `{}`, and repeated section markers
silently overwrote earlier content.

After: decoding rejects empty codes, missing sections, unexpected text before
the first section, codes with no section content, and duplicate section markers.
Existing supported partial codes such as `u1x0` remain valid.

Regression: `share_codes_require_content_and_unique_sections` includes `""`,
`"garbage"`, `"u1x0u2x1"`, duplicates of other sections and content-free markers,
plus a valid partial code. Existing decoder known-answer checks are retained.

## 7. Propagate battle identity failures

Before: decode used `identity(battle).unwrap_or_default()` and emitted
`battle_id:""` for malformed records.

After: the CLI propagates identity failures. Shared identity validation returns
an error for missing, empty or wrongly typed timestamps instead of panicking on
a non-string timestamp.

Regression: `decode_cli_propagates_missing_or_invalid_battle_identity` invokes
the decode CLI with a local synthetic ranked battle for each timestamp case and
requires a timestamp error.

## 8. Scan reply JSON with string and escape awareness

Before: braces in quoted strings affected nesting and could cause extraction to
select a later nested object instead of its valid outer object.

After: the object scan tracks JSON string and escape state, tries outer objects
first, and retries later starts only when an earlier candidate is invalid.

Regression: `reply_scan_prefers_outer_object_and_respects_string_escapes` embeds
closing/opening braces, an escaped quote and an escaped backslash in strings,
with a conflicting nested steps object and surrounding prose/fences. The full
outer object must be returned. The former test freezing the broken quoted-brace
behavior now checks successful extraction.

## 9. Return errors for malformed digitizer numbers

Before: `Json::opt_f64` panicked on strings before finite-value filters ran.

After: grid fields, coordinate pairs, tiles, symmetry indices and window zoom
match numeric JSON variants explicitly and return errors for invalid types or
non-finite values.

Regression: `malformed_digitizer_numbers_return_errors_without_unwinding` checks
strings, null, booleans, objects, NaN and infinity in grid/coordinate/tile inputs.

## 10. Reject non-finite catalog environment options

Before: floating-point parsing accepted NaN/infinity, which could reach wire
serialization as unreadable JSON tokens.

After: catalog environment numeric parsing requires a finite number before it
can enter the catalog. The existing wire representation and pinned catalog are
unchanged.

Regression: `numeric_environment_options_reject_nonfinite_values` exercises NaN,
both infinity signs, `Infinity`, overflow, a valid finite value and the default,
using a dedicated test environment variable to avoid affecting other tests.

## 11. Invalidate research status when the prompt changes

Before: status compared input/output hashes but ignored the saved prompt,
although execution identity already recognized prompt changes.

After: status additionally compares the saved and current prompt hashes, emits
`prompt_hash`, and marks mismatched or missing saved prompt specifications
pending. Newly written job specifications also contain the prompt hash.

Regression: `research_status_invalidates_a_changed_prompt` creates a complete
synthetic job receipt, changes only the prompt, and requires pending status.

## Verification and frozen files

Verification uses the installed WSL Rust toolchain, `. ~/.cargo/env`, and
`CARGO_TARGET_DIR=/tmp/clash-target-h1`. All commands are offline; there are no
downloads or provider/data acquisition calls. The unrelated preexisting changes
to `.github/workflows/ci.yml`, `THIRD_PARTY.md` and untracked `target-ws/` are left
untouched.

Baseline SHA-256 values (the same values must be present after verification):

| File | SHA-256 |
| --- | --- |
| `fixtures/golden/cases.jsonl` | `cea706d86516a2100876f9aa4ec7cdd5de32f691202f9a6d049b64e690d172ab` |
| `fixtures/golden/expected.jsonl` | `40446127d538f7bab2a86ab9c7fcae8b3a725c4ceb462fd2d95236cb38af0ab4` |
| `fixtures/golden/plans.jsonl` | `3ea43b38a16c4608aa04ab308c2a0e1ba645ed2cd3b89ad386235d8c44d32681` |

Completed validation:

- `cargo fmt --all -- --check`: passed.
- `scripts/verify.sh`: exit 0, ending **ALL CHECKS PASSED**. This includes locked
  offline release build/tests, strict Clippy, 868 battle goldens at both one and
  four workers, 1,354 compiled-plan goldens, guardian fixtures and the complete
  army-search, layout, base-search and video gates.
- All three SHA-256 values above match the starting values; `git diff` reports
  no changes to any golden file.
- The updated two-wave `basesearch smoke --threads 4` completed using 2,392 of
  2,400 physical battles. Its fresh wave manifests, checkpoint, report and
  adaptive proof receipt are in ignored `local/evidence/h1-smoke.olkkOc5U/`, along
  with `verify.log` and `golden-sha256.txt`.
