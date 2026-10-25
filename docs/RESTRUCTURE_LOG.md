# G1/G2 restructure log

Base: `24d25e7997f3e90a238340fc7dbcfbb953d5c9ff` on `sim-accuracy`.
Files were renamed in the filesystem (Git rename semantics); no commit or index write was attempted.

## Moved files

| Previous path | Current path |
| --- | --- |
| `rust/Cargo.lock` | `Cargo.lock` |
| `rust/Cargo.toml` | `Cargo.toml` |
| `rust/examples/mechanics_proof.rs` | `crates/clash-engine/examples/mechanics_proof.rs` |
| `rust/fixtures/layout/admission.json` | `fixtures/layout/admission.json` |
| `rust/fixtures/layout/geometry.json` | `fixtures/layout/geometry.json` |
| `rust/fixtures/layout/inventory.json` | `fixtures/layout/inventory.json` |
| `rust/fixtures/mechanics/demos.json` | `fixtures/mechanics/demos.json` |
| `rust/fixtures/mechanics/evidence.json` | `fixtures/mechanics/evidence.json` |
| `rust/golden/cases.jsonl` | `fixtures/golden/cases.jsonl` |
| `rust/golden/expected.jsonl` | `fixtures/golden/expected.jsonl` |
| `rust/golden/plans.jsonl` | `fixtures/golden/plans.jsonl` |
| `rust/src/ai.rs` | `crates/clash-engine/src/ai.rs` |
| `rust/src/armies.rs` | `crates/clash-plans/src/armies.rs` |
| `rust/src/armysearch.rs` | `crates/clash-armysearch/src/lib.rs` |
| `rust/src/armysearch/account.rs` | `crates/clash-armysearch/src/account.rs` |
| `rust/src/armysearch/eval.rs` | `crates/clash-armysearch/src/eval.rs` |
| `rust/src/armysearch/fix_proof.rs` | `crates/clash-armysearch/src/fix_proof.rs` |
| `rust/src/armysearch/genome.rs` | `crates/clash-armysearch/src/genome.rs` |
| `rust/src/armysearch/novelty.rs` | `crates/clash-armysearch/src/novelty.rs` |
| `rust/src/armysearch/operators.rs` | `crates/clash-armysearch/src/operators.rs` |
| `rust/src/armysearch/program.rs` | `crates/clash-armysearch/src/program.rs` |
| `rust/src/armysearch/program_mutate.rs` | `crates/clash-armysearch/src/program_mutate.rs` |
| `rust/src/armysearch/program_proof.rs` | `crates/clash-armysearch/src/program_proof.rs` |
| `rust/src/armysearch/program_validate.rs` | `crates/clash-armysearch/src/program_validate.rs` |
| `rust/src/armysearch/proof.rs` | `crates/clash-armysearch/src/proof.rs` |
| `rust/src/armysearch/report.rs` | `crates/clash-armysearch/src/report.rs` |
| `rust/src/armysearch/score.rs` | `crates/clash-armysearch/src/score.rs` |
| `rust/src/armysearch/search.rs` | `crates/clash-armysearch/src/search.rs` |
| `rust/src/armysearch/themed.rs` | `crates/clash-armysearch/src/themed.rs` |
| `rust/src/armysearch/util.rs` | `crates/clash-armysearch/src/util.rs` |
| `rust/src/attacker.rs` | `crates/clash-engine/src/plans/attacker.rs` |
| `rust/src/basesearch/anneal.rs` | `crates/clash-basesearch/src/anneal.rs` |
| `rust/src/basesearch/crossover.rs` | `crates/clash-basesearch/src/crossover.rs` |
| `rust/src/basesearch/generate.rs` | `crates/clash-basesearch/src/generate.rs` |
| `rust/src/basesearch/mod.rs` | `crates/clash-basesearch/src/lib.rs` |
| `rust/src/basesearch/operators/guided.rs` | `crates/clash-basesearch/src/operators/guided.rs` |
| `rust/src/basesearch/operators/macro_ops.rs` | `crates/clash-basesearch/src/operators/macro_ops.rs` |
| `rust/src/basesearch/operators/mod.rs` | `crates/clash-basesearch/src/operators/mod.rs` |
| `rust/src/basesearch/operators/setup.rs` | `crates/clash-basesearch/src/operators/setup.rs` |
| `rust/src/basesearch/operators/walls.rs` | `crates/clash-basesearch/src/operators/walls.rs` |
| `rust/src/basesearch/proof.rs` | `crates/clash-basesearch/src/proof.rs` |
| `rust/src/basesearch/repair.rs` | `crates/clash-basesearch/src/repair.rs` |
| `rust/src/basesearch/spatial.rs` | `crates/clash-basesearch/src/spatial.rs` |
| `rust/src/battle.rs` | `crates/clash-engine/src/battle.rs` |
| `rust/src/battlelog.rs` | `crates/clash-data/src/battlelog.rs` |
| `rust/src/catalog.rs` | `crates/clash-data/src/catalog.rs` |
| `rust/src/combat.rs` | `crates/clash-engine/src/combat.rs` |
| `rust/src/compile.rs` | `crates/clash-plans/src/compile.rs` |
| `rust/src/compile_cli.rs` | `crates/clash-cli/src/compile_cli.rs` |
| `rust/src/compile_tests.rs` | `crates/clash-plans/src/compile_tests.rs` |
| `rust/src/content.rs` | `crates/clash-data/src/content.rs` |
| `rust/src/defense.rs` | `crates/clash-engine/src/defense.rs` |
| `rust/src/detmath.rs` | `crates/clash-engine/src/detmath.rs` |
| `rust/src/effects.rs` | `crates/clash-engine/src/effects.rs` |
| `rust/src/fast_hash.rs` | `crates/clash-data/src/fast_hash.rs` |
| `rust/src/fidelity/board.rs` | `crates/clash-fidelity/src/board.rs` |
| `rust/src/fidelity/decode.rs` | `crates/clash-fidelity/src/decode.rs` |
| `rust/src/fidelity/fit.rs` | `crates/clash-fidelity/src/fit.rs` |
| `rust/src/fidelity/history.rs` | `crates/clash-fidelity/src/history.rs` |
| `rust/src/fidelity/io.rs` | `crates/clash-fidelity/src/io.rs` |
| `rust/src/fidelity/main.rs` | `crates/clash-fidelity/src/lib.rs` |
| `rust/src/fidelity/metrics.rs` | `crates/clash-fidelity/src/metrics.rs` |
| `rust/src/fidelity/observed.rs` | `crates/clash-fidelity/src/observed.rs` |
| `rust/src/fidelity/provenance.rs` | `crates/clash-fidelity/src/provenance.rs` |
| `rust/src/fidelity/replay.rs` | `crates/clash-fidelity/src/replay.rs` |
| `rust/src/fidelity/th18.rs` | `crates/clash-fidelity/src/th18.rs` |
| `rust/src/field_profile.rs` | `crates/clash-engine/src/field_profile.rs` |
| `rust/src/float.rs` | `crates/clash-data/src/float.rs` |
| `rust/src/geom.rs` | `crates/clash-engine/src/geom.rs` |
| `rust/src/golden.rs` | `crates/clash-cli/src/golden.rs` |
| `rust/src/grid.rs` | `crates/clash-engine/src/grid.rs` |
| `rust/src/heroes.rs` | `crates/clash-engine/src/heroes.rs` |
| `rust/src/jobs.rs` | `crates/clash-cli/src/jobs.rs` |
| `rust/src/json.rs` | `crates/clash-data/src/json.rs` |
| `rust/src/labels.rs` | `crates/clash-data/src/labels.rs` |
| `rust/src/layout/admit.rs` | `crates/clash-layout/src/admit.rs` |
| `rust/src/layout/cli.rs` | `crates/clash-cli/src/layout_cli.rs` |
| `rust/src/layout/geometry.rs` | `crates/clash-layout/src/geometry.rs` |
| `rust/src/layout/import.rs` | `crates/clash-cli/src/layout_rules.rs` |
| `rust/src/layout/json.rs` | `crates/clash-layout/src/json.rs` |
| `rust/src/layout/mod.rs` | `crates/clash-layout/src/lib.rs` |
| `rust/src/layout/model.rs` | `crates/clash-layout/src/model.rs` |
| `rust/src/layout/proof.rs` | `crates/clash-cli/src/layout_proof.rs` |
| `rust/src/layout/rules.rs` | `crates/clash-layout/src/rules.rs` |
| `rust/src/lib.rs` | `crates/clash-engine/src/lib.rs` |
| `rust/src/load.rs` | `crates/clash-engine/src/load.rs` |
| `rust/src/main.rs` | `crates/clash-cli/src/legacy.rs` |
| `rust/src/movement.rs` | `crates/clash-engine/src/movement.rs` |
| `rust/src/node.rs` | `crates/clash-data/src/node.rs` |
| `rust/src/params.rs` | `crates/clash-engine/src/params.rs` |
| `rust/src/pets.rs` | `crates/clash-engine/src/pets.rs` |
| `rust/src/plan_golden.rs` | `crates/clash-cli/src/plan_golden.rs` |
| `rust/src/plan_wire.rs` | `crates/clash-data/src/plan_wire.rs` |
| `rust/src/plans.rs` | `crates/clash-engine/src/plans.rs` |
| `rust/src/playbook.rs` | `crates/clash-engine/src/playbook.rs` |
| `rust/src/playbook_tests.rs` | `crates/clash-engine/src/playbook_tests.rs` |
| `rust/src/pyrandom.rs` | `crates/clash-engine/src/pyrandom.rs` |
| `rust/src/runner.rs` | `crates/clash-engine/src/runner.rs` |
| `rust/src/scoring.rs` | `crates/clash-scoring/src/scoring.rs` |
| `rust/src/scoring_cli.rs` | `crates/clash-cli/src/scoring_cli.rs` |
| `rust/src/scouting.rs` | `crates/clash-scoring/src/scouting.rs` |
| `rust/src/setup.rs` | `crates/clash-engine/src/setup.rs` |
| `rust/src/shared.rs` | `crates/clash-engine/src/shared.rs` |
| `rust/src/snapshots.rs` | `crates/clash-data/src/snapshots.rs` |
| `rust/src/source.rs` | `crates/clash-engine/src/source.rs` |
| `rust/src/spells.rs` | `crates/clash-engine/src/spells.rs` |
| `rust/src/state.rs` | `crates/clash-engine/src/state.rs` |
| `rust/src/stats.rs` | `crates/clash-data/src/stats.rs` |
| `rust/src/targeting.rs` | `crates/clash-engine/src/targeting.rs` |
| `rust/src/test_support.rs` | `crates/clash-engine/src/test_support.rs` |
| `rust/src/trace.rs` | `crates/clash-engine/src/trace.rs` |
| `rust/src/traps.rs` | `crates/clash-engine/src/traps.rs` |
| `rust/src/units.rs` | `crates/clash-engine/src/units.rs` |
| `rust/src/wire.rs` | `crates/clash-data/src/wire.rs` |
| `rust/tests/mechanics.rs` | `crates/clash-engine/tests/mechanics.rs` |
| `rust/tests/support/mechanics.rs` | `crates/clash-engine/tests/support/mechanics.rs` |
| `rust/vidmine/.gitignore` | `crates/clash-vidmine/.gitignore` |
| `rust/vidmine/Cargo.toml` | `crates/clash-vidmine/Cargo.toml` |
| `rust/vidmine/README.md` | `crates/clash-vidmine/README.md` |
| `rust/vidmine/src/appearance.rs` | `crates/clash-vidmine/src/appearance.rs` |
| `rust/vidmine/src/audit.rs` | `crates/clash-vidmine/src/audit.rs` |
| `rust/vidmine/src/camera.rs` | `crates/clash-vidmine/src/camera.rs` |
| `rust/vidmine/src/extract.rs` | `crates/clash-vidmine/src/extract.rs` |
| `rust/vidmine/src/grid.rs` | `crates/clash-vidmine/src/grid.rs` |
| `rust/vidmine/src/icons.rs` | `crates/clash-vidmine/src/icons.rs` |
| `rust/vidmine/src/identity.rs` | `crates/clash-vidmine/src/identity.rs` |
| `rust/vidmine/src/identity_review.rs` | `crates/clash-vidmine/src/identity_review.rs` |
| `rust/vidmine/src/image.rs` | `crates/clash-vidmine/src/image.rs` |
| `rust/vidmine/src/json.rs` | `crates/clash-vidmine/src/json.rs` |
| `rust/vidmine/src/league.rs` | `crates/clash-vidmine/src/league.rs` |
| `rust/vidmine/src/main.rs` | `crates/clash-vidmine/src/lib.rs` |
| `rust/vidmine/src/ocr.rs` | `crates/clash-vidmine/src/ocr.rs` |
| `rust/vidmine/src/positions.rs` | `crates/clash-vidmine/src/positions.rs` |
| `rust/vidmine/src/probe.rs` | `crates/clash-vidmine/src/probe.rs` |
| `rust/vidmine/src/replay.rs` | `crates/clash-vidmine/src/replay.rs` |
| `rust/vidmine/src/review.rs` | `crates/clash-vidmine/src/review.rs` |
| `rust/vidmine/src/spatial.rs` | `crates/clash-vidmine/src/spatial.rs` |
| `rust/vidmine/src/spatial_review.rs` | `crates/clash-vidmine/src/spatial_review.rs` |
| `rust/vidmine/src/timing.rs` | `crates/clash-vidmine/src/timing.rs` |
| `rust/vidmine/src/townhall.rs` | `crates/clash-vidmine/src/townhall.rs` |
| `rust/vidmine/src/video.rs` | `crates/clash-vidmine/src/video.rs` |
| `rust/vidmine/templates/README.md` | `crates/clash-vidmine/templates/README.md` |
| `rust/vidmine/templates/battle-label.txt` | `crates/clash-vidmine/templates/battle-label.txt` |
| `rust/vidmine/templates/battle-phone-label.txt` | `crates/clash-vidmine/templates/battle-phone-label.txt` |
| `rust/vidmine/templates/battle-q-label.txt` | `crates/clash-vidmine/templates/battle-q-label.txt` |
| `rust/vidmine/templates/clock-0-a.txt` | `crates/clash-vidmine/templates/clock-0-a.txt` |
| `rust/vidmine/templates/clock-0-modern-3.txt` | `crates/clash-vidmine/templates/clock-0-modern-3.txt` |
| `rust/vidmine/templates/clock-0-phone-5.txt` | `crates/clash-vidmine/templates/clock-0-phone-5.txt` |
| `rust/vidmine/templates/clock-1-a.txt` | `crates/clash-vidmine/templates/clock-1-a.txt` |
| `rust/vidmine/templates/clock-1-modern-0.txt` | `crates/clash-vidmine/templates/clock-1-modern-0.txt` |
| `rust/vidmine/templates/clock-1-modern-5.txt` | `crates/clash-vidmine/templates/clock-1-modern-5.txt` |
| `rust/vidmine/templates/clock-1-phone-2.txt` | `crates/clash-vidmine/templates/clock-1-phone-2.txt` |
| `rust/vidmine/templates/clock-1-phone-9.txt` | `crates/clash-vidmine/templates/clock-1-phone-9.txt` |
| `rust/vidmine/templates/clock-1-phone-extra-12.txt` | `crates/clash-vidmine/templates/clock-1-phone-extra-12.txt` |
| `rust/vidmine/templates/clock-1-q-m3.txt` | `crates/clash-vidmine/templates/clock-1-q-m3.txt` |
| `rust/vidmine/templates/clock-2-a.txt` | `crates/clash-vidmine/templates/clock-2-a.txt` |
| `rust/vidmine/templates/clock-2-modern-8.txt` | `crates/clash-vidmine/templates/clock-2-modern-8.txt` |
| `rust/vidmine/templates/clock-2-phone-3.txt` | `crates/clash-vidmine/templates/clock-2-phone-3.txt` |
| `rust/vidmine/templates/clock-2-q-m3.txt` | `crates/clash-vidmine/templates/clock-2-q-m3.txt` |
| `rust/vidmine/templates/clock-3-a.txt` | `crates/clash-vidmine/templates/clock-3-a.txt` |
| `rust/vidmine/templates/clock-3-modern-12.txt` | `crates/clash-vidmine/templates/clock-3-modern-12.txt` |
| `rust/vidmine/templates/clock-3-phone-8.txt` | `crates/clash-vidmine/templates/clock-3-phone-8.txt` |
| `rust/vidmine/templates/clock-3-phone-extra-10.txt` | `crates/clash-vidmine/templates/clock-3-phone-extra-10.txt` |
| `rust/vidmine/templates/clock-3-q-m3.txt` | `crates/clash-vidmine/templates/clock-3-q-m3.txt` |
| `rust/vidmine/templates/clock-4-a.txt` | `crates/clash-vidmine/templates/clock-4-a.txt` |
| `rust/vidmine/templates/clock-4-b.txt` | `crates/clash-vidmine/templates/clock-4-b.txt` |
| `rust/vidmine/templates/clock-4-modern-19.txt` | `crates/clash-vidmine/templates/clock-4-modern-19.txt` |
| `rust/vidmine/templates/clock-4-modern-20.txt` | `crates/clash-vidmine/templates/clock-4-modern-20.txt` |
| `rust/vidmine/templates/clock-4-modern-6.txt` | `crates/clash-vidmine/templates/clock-4-modern-6.txt` |
| `rust/vidmine/templates/clock-4-phone-11.txt` | `crates/clash-vidmine/templates/clock-4-phone-11.txt` |
| `rust/vidmine/templates/clock-4-phone-7.txt` | `crates/clash-vidmine/templates/clock-4-phone-7.txt` |
| `rust/vidmine/templates/clock-4-q-m3.txt` | `crates/clash-vidmine/templates/clock-4-q-m3.txt` |
| `rust/vidmine/templates/clock-5-a.txt` | `crates/clash-vidmine/templates/clock-5-a.txt` |
| `rust/vidmine/templates/clock-5-modern-2.txt` | `crates/clash-vidmine/templates/clock-5-modern-2.txt` |
| `rust/vidmine/templates/clock-5-phone-10.txt` | `crates/clash-vidmine/templates/clock-5-phone-10.txt` |
| `rust/vidmine/templates/clock-5-phone-extra-9.txt` | `crates/clash-vidmine/templates/clock-5-phone-extra-9.txt` |
| `rust/vidmine/templates/clock-5-q-m3.txt` | `crates/clash-vidmine/templates/clock-5-q-m3.txt` |
| `rust/vidmine/templates/clock-6-a.txt` | `crates/clash-vidmine/templates/clock-6-a.txt` |
| `rust/vidmine/templates/clock-6-modern-7.txt` | `crates/clash-vidmine/templates/clock-6-modern-7.txt` |
| `rust/vidmine/templates/clock-6-phone-0.txt` | `crates/clash-vidmine/templates/clock-6-phone-0.txt` |
| `rust/vidmine/templates/clock-6-phone-extra-8.txt` | `crates/clash-vidmine/templates/clock-6-phone-extra-8.txt` |
| `rust/vidmine/templates/clock-7-a.txt` | `crates/clash-vidmine/templates/clock-7-a.txt` |
| `rust/vidmine/templates/clock-7-modern-18.txt` | `crates/clash-vidmine/templates/clock-7-modern-18.txt` |
| `rust/vidmine/templates/clock-7-phone-extra-6.txt` | `crates/clash-vidmine/templates/clock-7-phone-extra-6.txt` |
| `rust/vidmine/templates/clock-8-a.txt` | `crates/clash-vidmine/templates/clock-8-a.txt` |
| `rust/vidmine/templates/clock-8-modern-15.txt` | `crates/clash-vidmine/templates/clock-8-modern-15.txt` |
| `rust/vidmine/templates/clock-8-phone-extra-5.txt` | `crates/clash-vidmine/templates/clock-8-phone-extra-5.txt` |
| `rust/vidmine/templates/clock-8-q-m3.txt` | `crates/clash-vidmine/templates/clock-8-q-m3.txt` |
| `rust/vidmine/templates/clock-9-a.txt` | `crates/clash-vidmine/templates/clock-9-a.txt` |
| `rust/vidmine/templates/clock-9-modern-13.txt` | `crates/clash-vidmine/templates/clock-9-modern-13.txt` |
| `rust/vidmine/templates/clock-9-phone-extra-3.txt` | `crates/clash-vidmine/templates/clock-9-phone-extra-3.txt` |
| `rust/vidmine/templates/clock-m-q-m3.txt` | `crates/clash-vidmine/templates/clock-m-q-m3.txt` |
| `rust/vidmine/templates/count-0-95.txt` | `crates/clash-vidmine/templates/count-0-95.txt` |
| `rust/vidmine/templates/count-1-145.txt` | `crates/clash-vidmine/templates/count-1-145.txt` |
| `rust/vidmine/templates/count-1-175.txt` | `crates/clash-vidmine/templates/count-1-175.txt` |
| `rust/vidmine/templates/count-1-a.txt` | `crates/clash-vidmine/templates/count-1-a.txt` |
| `rust/vidmine/templates/count-2-145.txt` | `crates/clash-vidmine/templates/count-2-145.txt` |
| `rust/vidmine/templates/count-2-175.txt` | `crates/clash-vidmine/templates/count-2-175.txt` |
| `rust/vidmine/templates/count-2-95.txt` | `crates/clash-vidmine/templates/count-2-95.txt` |
| `rust/vidmine/templates/count-2-a.txt` | `crates/clash-vidmine/templates/count-2-a.txt` |
| `rust/vidmine/templates/count-3-145.txt` | `crates/clash-vidmine/templates/count-3-145.txt` |
| `rust/vidmine/templates/count-3-175.txt` | `crates/clash-vidmine/templates/count-3-175.txt` |
| `rust/vidmine/templates/count-3-95.txt` | `crates/clash-vidmine/templates/count-3-95.txt` |
| `rust/vidmine/templates/count-3-a.txt` | `crates/clash-vidmine/templates/count-3-a.txt` |
| `rust/vidmine/templates/count-4-145.txt` | `crates/clash-vidmine/templates/count-4-145.txt` |
| `rust/vidmine/templates/count-4-175.txt` | `crates/clash-vidmine/templates/count-4-175.txt` |
| `rust/vidmine/templates/count-5-a.txt` | `crates/clash-vidmine/templates/count-5-a.txt` |
| `rust/vidmine/templates/count-x-199-534-145.txt` | `crates/clash-vidmine/templates/count-x-199-534-145.txt` |
| `rust/vidmine/templates/count-x-199-534-175.txt` | `crates/clash-vidmine/templates/count-x-199-534-175.txt` |
| `rust/vidmine/templates/count-x-199-534-95.txt` | `crates/clash-vidmine/templates/count-x-199-534-95.txt` |
| `rust/vidmine/templates/count-x-264-534-145.txt` | `crates/clash-vidmine/templates/count-x-264-534-145.txt` |
| `rust/vidmine/templates/count-x-264-534-175.txt` | `crates/clash-vidmine/templates/count-x-264-534-175.txt` |
| `rust/vidmine/templates/count-x-330-534-145.txt` | `crates/clash-vidmine/templates/count-x-330-534-145.txt` |
| `rust/vidmine/templates/count-x-330-534-175.txt` | `crates/clash-vidmine/templates/count-x-330-534-175.txt` |
| `rust/vidmine/templates/count-x-330-534-95.txt` | `crates/clash-vidmine/templates/count-x-330-534-95.txt` |
| `rust/vidmine/templates/count-x-395-534-95.txt` | `crates/clash-vidmine/templates/count-x-395-534-95.txt` |
| `rust/vidmine/templates/count-x-395-630-145.txt` | `crates/clash-vidmine/templates/count-x-395-630-145.txt` |
| `rust/vidmine/templates/count-x-395-630-175.txt` | `crates/clash-vidmine/templates/count-x-395-630-175.txt` |
| `rust/vidmine/templates/count-x-a.txt` | `crates/clash-vidmine/templates/count-x-a.txt` |
| `rust/vidmine/templates/damage-0-a.txt` | `crates/clash-vidmine/templates/damage-0-a.txt` |
| `rust/vidmine/templates/damage-0-modern-10.txt` | `crates/clash-vidmine/templates/damage-0-modern-10.txt` |
| `rust/vidmine/templates/damage-0-phone-7.txt` | `crates/clash-vidmine/templates/damage-0-phone-7.txt` |
| `rust/vidmine/templates/damage-1-a.txt` | `crates/clash-vidmine/templates/damage-1-a.txt` |
| `rust/vidmine/templates/damage-1-b.txt` | `crates/clash-vidmine/templates/damage-1-b.txt` |
| `rust/vidmine/templates/damage-1-modern-12.txt` | `crates/clash-vidmine/templates/damage-1-modern-12.txt` |
| `rust/vidmine/templates/damage-1-modern-9.txt` | `crates/clash-vidmine/templates/damage-1-modern-9.txt` |
| `rust/vidmine/templates/damage-1-phone-2.txt` | `crates/clash-vidmine/templates/damage-1-phone-2.txt` |
| `rust/vidmine/templates/damage-2-a.txt` | `crates/clash-vidmine/templates/damage-2-a.txt` |
| `rust/vidmine/templates/damage-2-modern-2.txt` | `crates/clash-vidmine/templates/damage-2-modern-2.txt` |
| `rust/vidmine/templates/damage-2-phone-4.txt` | `crates/clash-vidmine/templates/damage-2-phone-4.txt` |
| `rust/vidmine/templates/damage-3-a.txt` | `crates/clash-vidmine/templates/damage-3-a.txt` |
| `rust/vidmine/templates/damage-3-modern-8.txt` | `crates/clash-vidmine/templates/damage-3-modern-8.txt` |
| `rust/vidmine/templates/damage-3-phone-3.txt` | `crates/clash-vidmine/templates/damage-3-phone-3.txt` |
| `rust/vidmine/templates/damage-4-a.txt` | `crates/clash-vidmine/templates/damage-4-a.txt` |
| `rust/vidmine/templates/damage-4-modern-4.txt` | `crates/clash-vidmine/templates/damage-4-modern-4.txt` |
| `rust/vidmine/templates/damage-4-phone-6.txt` | `crates/clash-vidmine/templates/damage-4-phone-6.txt` |
| `rust/vidmine/templates/damage-5-a.txt` | `crates/clash-vidmine/templates/damage-5-a.txt` |
| `rust/vidmine/templates/damage-5-modern-11.txt` | `crates/clash-vidmine/templates/damage-5-modern-11.txt` |
| `rust/vidmine/templates/damage-5-phone-9.txt` | `crates/clash-vidmine/templates/damage-5-phone-9.txt` |
| `rust/vidmine/templates/damage-6-a.txt` | `crates/clash-vidmine/templates/damage-6-a.txt` |
| `rust/vidmine/templates/damage-6-modern-3.txt` | `crates/clash-vidmine/templates/damage-6-modern-3.txt` |
| `rust/vidmine/templates/damage-6-modern-6.txt` | `crates/clash-vidmine/templates/damage-6-modern-6.txt` |
| `rust/vidmine/templates/damage-6-phone-0.txt` | `crates/clash-vidmine/templates/damage-6-phone-0.txt` |
| `rust/vidmine/templates/damage-7-a.txt` | `crates/clash-vidmine/templates/damage-7-a.txt` |
| `rust/vidmine/templates/damage-7-modern-14.txt` | `crates/clash-vidmine/templates/damage-7-modern-14.txt` |
| `rust/vidmine/templates/damage-7-phone-5.txt` | `crates/clash-vidmine/templates/damage-7-phone-5.txt` |
| `rust/vidmine/templates/damage-8-a.txt` | `crates/clash-vidmine/templates/damage-8-a.txt` |
| `rust/vidmine/templates/damage-8-modern-7.txt` | `crates/clash-vidmine/templates/damage-8-modern-7.txt` |
| `rust/vidmine/templates/damage-8-phone-8.txt` | `crates/clash-vidmine/templates/damage-8-phone-8.txt` |
| `rust/vidmine/templates/damage-9-a.txt` | `crates/clash-vidmine/templates/damage-9-a.txt` |
| `rust/vidmine/templates/damage-9-modern-0.txt` | `crates/clash-vidmine/templates/damage-9-modern-0.txt` |
| `rust/vidmine/templates/damage-9-modern-13.txt` | `crates/clash-vidmine/templates/damage-9-modern-13.txt` |
| `rust/vidmine/templates/damage-9-phone-10.txt` | `crates/clash-vidmine/templates/damage-9-phone-10.txt` |
| `rust/vidmine/templates/damage-label.txt` | `crates/clash-vidmine/templates/damage-label.txt` |
| `rust/vidmine/templates/damage-modern-label.txt` | `crates/clash-vidmine/templates/damage-modern-label.txt` |
| `rust/vidmine/templates/damage-phone-label.txt` | `crates/clash-vidmine/templates/damage-phone-label.txt` |
| `rust/vidmine/templates/icons/Apprentice_Warden--42.txt` | `crates/clash-vidmine/templates/icons/Apprentice_Warden--42.txt` |
| `rust/vidmine/templates/icons/Apprentice_Warden--5.txt` | `crates/clash-vidmine/templates/icons/Apprentice_Warden--5.txt` |
| `rust/vidmine/templates/icons/Apprentice_Warden--88.txt` | `crates/clash-vidmine/templates/icons/Apprentice_Warden--88.txt` |
| `rust/vidmine/templates/icons/Apprentice_Warden--m3-reviewed-42.txt` | `crates/clash-vidmine/templates/icons/Apprentice_Warden--m3-reviewed-42.txt` |
| `rust/vidmine/templates/icons/Apprentice_Warden--m3-reviewed-46.txt` | `crates/clash-vidmine/templates/icons/Apprentice_Warden--m3-reviewed-46.txt` |
| `rust/vidmine/templates/icons/Archer--105.txt` | `crates/clash-vidmine/templates/icons/Archer--105.txt` |
| `rust/vidmine/templates/icons/Archer--116.txt` | `crates/clash-vidmine/templates/icons/Archer--116.txt` |
| `rust/vidmine/templates/icons/Archer--14.txt` | `crates/clash-vidmine/templates/icons/Archer--14.txt` |
| `rust/vidmine/templates/icons/Archer--174.txt` | `crates/clash-vidmine/templates/icons/Archer--174.txt` |
| `rust/vidmine/templates/icons/Archer--187.txt` | `crates/clash-vidmine/templates/icons/Archer--187.txt` |
| `rust/vidmine/templates/icons/Archer--214.txt` | `crates/clash-vidmine/templates/icons/Archer--214.txt` |
| `rust/vidmine/templates/icons/Archer--231.txt` | `crates/clash-vidmine/templates/icons/Archer--231.txt` |
| `rust/vidmine/templates/icons/Archer--28.txt` | `crates/clash-vidmine/templates/icons/Archer--28.txt` |
| `rust/vidmine/templates/icons/Archer--60.txt` | `crates/clash-vidmine/templates/icons/Archer--60.txt` |
| `rust/vidmine/templates/icons/Archer--9.txt` | `crates/clash-vidmine/templates/icons/Archer--9.txt` |
| `rust/vidmine/templates/icons/Archer--extra-22.txt` | `crates/clash-vidmine/templates/icons/Archer--extra-22.txt` |
| `rust/vidmine/templates/icons/Archer--extra-5.txt` | `crates/clash-vidmine/templates/icons/Archer--extra-5.txt` |
| `rust/vidmine/templates/icons/Archer--m3-reviewed-0.txt` | `crates/clash-vidmine/templates/icons/Archer--m3-reviewed-0.txt` |
| `rust/vidmine/templates/icons/Archer--m3-reviewed-1.txt` | `crates/clash-vidmine/templates/icons/Archer--m3-reviewed-1.txt` |
| `rust/vidmine/templates/icons/Archer--m3-reviewed-15.txt` | `crates/clash-vidmine/templates/icons/Archer--m3-reviewed-15.txt` |
| `rust/vidmine/templates/icons/Archer--m3-reviewed-20.txt` | `crates/clash-vidmine/templates/icons/Archer--m3-reviewed-20.txt` |
| `rust/vidmine/templates/icons/Archer--m3-reviewed-25.txt` | `crates/clash-vidmine/templates/icons/Archer--m3-reviewed-25.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--109.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--109.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--12.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--12.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--120.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--120.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--130.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--130.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--136.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--136.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--162.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--162.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--166.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--166.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--177.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--177.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--202.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--202.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--208.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--208.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--218.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--218.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--237.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--237.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--49.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--49.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--57.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--57.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--72.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--72.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--79.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--79.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--95.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--95.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--extra-14.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--extra-14.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--m3-15.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--m3-15.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--m3-6.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--m3-6.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--m3-reviewed-15.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--m3-reviewed-15.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--m3-reviewed-19.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--m3-reviewed-19.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--m3-reviewed-22.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--m3-reviewed-22.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--m3-reviewed-27.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--m3-reviewed-27.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--m3-reviewed-36.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--m3-reviewed-36.txt` |
| `rust/vidmine/templates/icons/Archer_Queen--m3-reviewed-6.txt` | `crates/clash-vidmine/templates/icons/Archer_Queen--m3-reviewed-6.txt` |
| `rust/vidmine/templates/icons/Baby_Dragon--197.txt` | `crates/clash-vidmine/templates/icons/Baby_Dragon--197.txt` |
| `rust/vidmine/templates/icons/Baby_Dragon--29.txt` | `crates/clash-vidmine/templates/icons/Baby_Dragon--29.txt` |
| `rust/vidmine/templates/icons/Baby_Dragon--8.txt` | `crates/clash-vidmine/templates/icons/Baby_Dragon--8.txt` |
| `rust/vidmine/templates/icons/Baby_Dragon--m3-3.txt` | `crates/clash-vidmine/templates/icons/Baby_Dragon--m3-3.txt` |
| `rust/vidmine/templates/icons/Baby_Dragon--m3-reviewed-21.txt` | `crates/clash-vidmine/templates/icons/Baby_Dragon--m3-reviewed-21.txt` |
| `rust/vidmine/templates/icons/Baby_Dragon--m3-reviewed-3.txt` | `crates/clash-vidmine/templates/icons/Baby_Dragon--m3-reviewed-3.txt` |
| `rust/vidmine/templates/icons/Baby_Dragon--m3-reviewed-7.txt` | `crates/clash-vidmine/templates/icons/Baby_Dragon--m3-reviewed-7.txt` |
| `rust/vidmine/templates/icons/Balloon--100.txt` | `crates/clash-vidmine/templates/icons/Balloon--100.txt` |
| `rust/vidmine/templates/icons/Balloon--191.txt` | `crates/clash-vidmine/templates/icons/Balloon--191.txt` |
| `rust/vidmine/templates/icons/Balloon--206.txt` | `crates/clash-vidmine/templates/icons/Balloon--206.txt` |
| `rust/vidmine/templates/icons/Balloon--4.txt` | `crates/clash-vidmine/templates/icons/Balloon--4.txt` |
| `rust/vidmine/templates/icons/Balloon--40.txt` | `crates/clash-vidmine/templates/icons/Balloon--40.txt` |
| `rust/vidmine/templates/icons/Balloon--74.txt` | `crates/clash-vidmine/templates/icons/Balloon--74.txt` |
| `rust/vidmine/templates/icons/Balloon--extra-18.txt` | `crates/clash-vidmine/templates/icons/Balloon--extra-18.txt` |
| `rust/vidmine/templates/icons/Balloon--extra-3.txt` | `crates/clash-vidmine/templates/icons/Balloon--extra-3.txt` |
| `rust/vidmine/templates/icons/Balloon--m3-2.txt` | `crates/clash-vidmine/templates/icons/Balloon--m3-2.txt` |
| `rust/vidmine/templates/icons/Balloon--m3-reviewed-13.txt` | `crates/clash-vidmine/templates/icons/Balloon--m3-reviewed-13.txt` |
| `rust/vidmine/templates/icons/Balloon--m3-reviewed-16.txt` | `crates/clash-vidmine/templates/icons/Balloon--m3-reviewed-16.txt` |
| `rust/vidmine/templates/icons/Balloon--m3-reviewed-2.txt` | `crates/clash-vidmine/templates/icons/Balloon--m3-reviewed-2.txt` |
| `rust/vidmine/templates/icons/Balloon--m3-reviewed-21.txt` | `crates/clash-vidmine/templates/icons/Balloon--m3-reviewed-21.txt` |
| `rust/vidmine/templates/icons/Balloon--m3-reviewed-26.txt` | `crates/clash-vidmine/templates/icons/Balloon--m3-reviewed-26.txt` |
| `rust/vidmine/templates/icons/Balloon--m3-reviewed-39.txt` | `crates/clash-vidmine/templates/icons/Balloon--m3-reviewed-39.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--108.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--108.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--11.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--11.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--119.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--119.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--135.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--135.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--168.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--168.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--176.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--176.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--189.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--189.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--209.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--209.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--219.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--219.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--236.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--236.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--47.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--47.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--66.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--66.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--76.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--76.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--86.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--86.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--extra-15.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--extra-15.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--m3-14.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--m3-14.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--m3-5.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--m3-5.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--m3-reviewed-14.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--m3-reviewed-14.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--m3-reviewed-17.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--m3-reviewed-17.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--m3-reviewed-38.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--m3-reviewed-38.txt` |
| `rust/vidmine/templates/icons/Barbarian_King--m3-reviewed-5.txt` | `crates/clash-vidmine/templates/icons/Barbarian_King--m3-reviewed-5.txt` |
| `rust/vidmine/templates/icons/Bat_Spell--89.txt` | `crates/clash-vidmine/templates/icons/Bat_Spell--89.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--107.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--107.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--118.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--118.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--139.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--139.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--167.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--167.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--175.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--175.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--188.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--188.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--215.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--215.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--233.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--233.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--234.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--234.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--46.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--46.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--extra-28.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--extra-28.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--m3-reviewed-2.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--m3-reviewed-2.txt` |
| `rust/vidmine/templates/icons/Battle_Blimp--m3-reviewed-8.txt` | `crates/clash-vidmine/templates/icons/Battle_Blimp--m3-reviewed-8.txt` |
| `rust/vidmine/templates/icons/Clone_Spell--123.txt` | `crates/clash-vidmine/templates/icons/Clone_Spell--123.txt` |
| `rust/vidmine/templates/icons/Clone_Spell--181.txt` | `crates/clash-vidmine/templates/icons/Clone_Spell--181.txt` |
| `rust/vidmine/templates/icons/Clone_Spell--220.txt` | `crates/clash-vidmine/templates/icons/Clone_Spell--220.txt` |
| `rust/vidmine/templates/icons/Clone_Spell--67.txt` | `crates/clash-vidmine/templates/icons/Clone_Spell--67.txt` |
| `rust/vidmine/templates/icons/Clone_Spell--extra-11.txt` | `crates/clash-vidmine/templates/icons/Clone_Spell--extra-11.txt` |
| `rust/vidmine/templates/icons/Clone_Spell--m3-reviewed-48.txt` | `crates/clash-vidmine/templates/icons/Clone_Spell--m3-reviewed-48.txt` |
| `rust/vidmine/templates/icons/Dragon--16.txt` | `crates/clash-vidmine/templates/icons/Dragon--16.txt` |
| `rust/vidmine/templates/icons/Dragon--192.txt` | `crates/clash-vidmine/templates/icons/Dragon--192.txt` |
| `rust/vidmine/templates/icons/Dragon--51.txt` | `crates/clash-vidmine/templates/icons/Dragon--51.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--111.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--111.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--122.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--122.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--132.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--132.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--138.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--138.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--165.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--165.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--201.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--201.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--205.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--205.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--22.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--22.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--222.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--222.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--226.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--226.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--228.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--228.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--239.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--239.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--50.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--50.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--59.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--59.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--70.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--70.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--77.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--77.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--84.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--84.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--93.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--93.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--extra-24.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--extra-24.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--m3-13.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--m3-13.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--m3-7.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--m3-7.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--m3-reviewed-12.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--m3-reviewed-12.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--m3-reviewed-13.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--m3-reviewed-13.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--m3-reviewed-44.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--m3-reviewed-44.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--m3-reviewed-54.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--m3-reviewed-54.txt` |
| `rust/vidmine/templates/icons/Dragon_Duke--m3-reviewed-7.txt` | `crates/clash-vidmine/templates/icons/Dragon_Duke--m3-reviewed-7.txt` |
| `rust/vidmine/templates/icons/Dragon_Rider--194.txt` | `crates/clash-vidmine/templates/icons/Dragon_Rider--194.txt` |
| `rust/vidmine/templates/icons/Dragon_Rider--53.txt` | `crates/clash-vidmine/templates/icons/Dragon_Rider--53.txt` |
| `rust/vidmine/templates/icons/Electro_Dragon--m3-0.txt` | `crates/clash-vidmine/templates/icons/Electro_Dragon--m3-0.txt` |
| `rust/vidmine/templates/icons/Electro_Dragon--m3-reviewed-0.txt` | `crates/clash-vidmine/templates/icons/Electro_Dragon--m3-reviewed-0.txt` |
| `rust/vidmine/templates/icons/Electro_Dragon--m3-reviewed-16.txt` | `crates/clash-vidmine/templates/icons/Electro_Dragon--m3-reviewed-16.txt` |
| `rust/vidmine/templates/icons/Electro_Dragon--m3-reviewed-18.txt` | `crates/clash-vidmine/templates/icons/Electro_Dragon--m3-reviewed-18.txt` |
| `rust/vidmine/templates/icons/Electro_Titan--3.txt` | `crates/clash-vidmine/templates/icons/Electro_Titan--3.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--161.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--161.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--180.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--180.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--243.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--243.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--35.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--35.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--extra-27.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--extra-27.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--extra-7.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--extra-7.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-11.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-11.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-reviewed-11.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-reviewed-11.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-reviewed-24.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-reviewed-24.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-reviewed-25.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-reviewed-25.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-reviewed-28.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-reviewed-28.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-reviewed-37.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-reviewed-37.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-reviewed-41.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-reviewed-41.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-reviewed-47.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-reviewed-47.txt` |
| `rust/vidmine/templates/icons/Freeze_Spell--m3-reviewed-9.txt` | `crates/clash-vidmine/templates/icons/Freeze_Spell--m3-reviewed-9.txt` |
| `rust/vidmine/templates/icons/Giant--90.txt` | `crates/clash-vidmine/templates/icons/Giant--90.txt` |
| `rust/vidmine/templates/icons/Goblin--198.txt` | `crates/clash-vidmine/templates/icons/Goblin--198.txt` |
| `rust/vidmine/templates/icons/Golem--extra-23.txt` | `crates/clash-vidmine/templates/icons/Golem--extra-23.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--110.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--110.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--121.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--121.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--126.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--126.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--13.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--13.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--131.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--131.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--137.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--137.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--160.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--160.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--178.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--178.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--182.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--182.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--203.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--203.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--207.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--207.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--221.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--221.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--225.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--225.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--23.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--23.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--238.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--238.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--48.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--48.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--58.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--58.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--71.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--71.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--78.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--78.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--85.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--85.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--94.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--94.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--extra-16.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--extra-16.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--m3-12.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--m3-12.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--m3-reviewed-12.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--m3-reviewed-12.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--m3-reviewed-22.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--m3-reviewed-22.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--m3-reviewed-3.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--m3-reviewed-3.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--m3-reviewed-4.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--m3-reviewed-4.txt` |
| `rust/vidmine/templates/icons/Grand_Warden--m3-reviewed-6.txt` | `crates/clash-vidmine/templates/icons/Grand_Warden--m3-reviewed-6.txt` |
| `rust/vidmine/templates/icons/Headhunter--103.txt` | `crates/clash-vidmine/templates/icons/Headhunter--103.txt` |
| `rust/vidmine/templates/icons/Headhunter--114.txt` | `crates/clash-vidmine/templates/icons/Headhunter--114.txt` |
| `rust/vidmine/templates/icons/Headhunter--172.txt` | `crates/clash-vidmine/templates/icons/Headhunter--172.txt` |
| `rust/vidmine/templates/icons/Headhunter--185.txt` | `crates/clash-vidmine/templates/icons/Headhunter--185.txt` |
| `rust/vidmine/templates/icons/Headhunter--213.txt` | `crates/clash-vidmine/templates/icons/Headhunter--213.txt` |
| `rust/vidmine/templates/icons/Headhunter--232.txt` | `crates/clash-vidmine/templates/icons/Headhunter--232.txt` |
| `rust/vidmine/templates/icons/Headhunter--32.txt` | `crates/clash-vidmine/templates/icons/Headhunter--32.txt` |
| `rust/vidmine/templates/icons/Headhunter--65.txt` | `crates/clash-vidmine/templates/icons/Headhunter--65.txt` |
| `rust/vidmine/templates/icons/Headhunter--7.txt` | `crates/clash-vidmine/templates/icons/Headhunter--7.txt` |
| `rust/vidmine/templates/icons/Headhunter--73.txt` | `crates/clash-vidmine/templates/icons/Headhunter--73.txt` |
| `rust/vidmine/templates/icons/Headhunter--80.txt` | `crates/clash-vidmine/templates/icons/Headhunter--80.txt` |
| `rust/vidmine/templates/icons/Healer--101.txt` | `crates/clash-vidmine/templates/icons/Healer--101.txt` |
| `rust/vidmine/templates/icons/Healer--169.txt` | `crates/clash-vidmine/templates/icons/Healer--169.txt` |
| `rust/vidmine/templates/icons/Healer--171.txt` | `crates/clash-vidmine/templates/icons/Healer--171.txt` |
| `rust/vidmine/templates/icons/Healer--184.txt` | `crates/clash-vidmine/templates/icons/Healer--184.txt` |
| `rust/vidmine/templates/icons/Healer--31.txt` | `crates/clash-vidmine/templates/icons/Healer--31.txt` |
| `rust/vidmine/templates/icons/Healer--62.txt` | `crates/clash-vidmine/templates/icons/Healer--62.txt` |
| `rust/vidmine/templates/icons/Healer--extra-17.txt` | `crates/clash-vidmine/templates/icons/Healer--extra-17.txt` |
| `rust/vidmine/templates/icons/Healer--extra-2.txt` | `crates/clash-vidmine/templates/icons/Healer--extra-2.txt` |
| `rust/vidmine/templates/icons/Healer--m3-reviewed-52.txt` | `crates/clash-vidmine/templates/icons/Healer--m3-reviewed-52.txt` |
| `rust/vidmine/templates/icons/Hog_Rider--m3-reviewed-17.txt` | `crates/clash-vidmine/templates/icons/Hog_Rider--m3-reviewed-17.txt` |
| `rust/vidmine/templates/icons/Hog_Rider--m3-reviewed-32.txt` | `crates/clash-vidmine/templates/icons/Hog_Rider--m3-reviewed-32.txt` |
| `rust/vidmine/templates/icons/Ice_Golem--1.txt` | `crates/clash-vidmine/templates/icons/Ice_Golem--1.txt` |
| `rust/vidmine/templates/icons/Ice_Golem--33.txt` | `crates/clash-vidmine/templates/icons/Ice_Golem--33.txt` |
| `rust/vidmine/templates/icons/Ice_Golem--75.txt` | `crates/clash-vidmine/templates/icons/Ice_Golem--75.txt` |
| `rust/vidmine/templates/icons/Ice_Golem--extra-1.txt` | `crates/clash-vidmine/templates/icons/Ice_Golem--extra-1.txt` |
| `rust/vidmine/templates/icons/Ice_Golem--extra-20.txt` | `crates/clash-vidmine/templates/icons/Ice_Golem--extra-20.txt` |
| `rust/vidmine/templates/icons/Ice_Hound--63.txt` | `crates/clash-vidmine/templates/icons/Ice_Hound--63.txt` |
| `rust/vidmine/templates/icons/Ice_Hound--82.txt` | `crates/clash-vidmine/templates/icons/Ice_Hound--82.txt` |
| `rust/vidmine/templates/icons/Invisibility_Spell--125.txt` | `crates/clash-vidmine/templates/icons/Invisibility_Spell--125.txt` |
| `rust/vidmine/templates/icons/Invisibility_Spell--18.txt` | `crates/clash-vidmine/templates/icons/Invisibility_Spell--18.txt` |
| `rust/vidmine/templates/icons/Invisibility_Spell--216.txt` | `crates/clash-vidmine/templates/icons/Invisibility_Spell--216.txt` |
| `rust/vidmine/templates/icons/Invisibility_Spell--242.txt` | `crates/clash-vidmine/templates/icons/Invisibility_Spell--242.txt` |
| `rust/vidmine/templates/icons/Invisibility_Spell--45.txt` | `crates/clash-vidmine/templates/icons/Invisibility_Spell--45.txt` |
| `rust/vidmine/templates/icons/Invisibility_Spell--extra-25.txt` | `crates/clash-vidmine/templates/icons/Invisibility_Spell--extra-25.txt` |
| `rust/vidmine/templates/icons/Invisibility_Spell--m3-reviewed-11.txt` | `crates/clash-vidmine/templates/icons/Invisibility_Spell--m3-reviewed-11.txt` |
| `rust/vidmine/templates/icons/Jump_Spell--m3-reviewed-23.txt` | `crates/clash-vidmine/templates/icons/Jump_Spell--m3-reviewed-23.txt` |
| `rust/vidmine/templates/icons/Jump_Spell--m3-reviewed-29.txt` | `crates/clash-vidmine/templates/icons/Jump_Spell--m3-reviewed-29.txt` |
| `rust/vidmine/templates/icons/Lava_Hound--17.txt` | `crates/clash-vidmine/templates/icons/Lava_Hound--17.txt` |
| `rust/vidmine/templates/icons/Lava_Hound--195.txt` | `crates/clash-vidmine/templates/icons/Lava_Hound--195.txt` |
| `rust/vidmine/templates/icons/Minion--54.txt` | `crates/clash-vidmine/templates/icons/Minion--54.txt` |
| `rust/vidmine/templates/icons/Minion--extra-6.txt` | `crates/clash-vidmine/templates/icons/Minion--extra-6.txt` |
| `rust/vidmine/templates/icons/Minion--m3-reviewed-40.txt` | `crates/clash-vidmine/templates/icons/Minion--m3-reviewed-40.txt` |
| `rust/vidmine/templates/icons/Minion_Prince--204.txt` | `crates/clash-vidmine/templates/icons/Minion_Prince--204.txt` |
| `rust/vidmine/templates/icons/Minion_Prince--25.txt` | `crates/clash-vidmine/templates/icons/Minion_Prince--25.txt` |
| `rust/vidmine/templates/icons/Overgrowth_Spell--124.txt` | `crates/clash-vidmine/templates/icons/Overgrowth_Spell--124.txt` |
| `rust/vidmine/templates/icons/Overgrowth_Spell--163.txt` | `crates/clash-vidmine/templates/icons/Overgrowth_Spell--163.txt` |
| `rust/vidmine/templates/icons/Overgrowth_Spell--190.txt` | `crates/clash-vidmine/templates/icons/Overgrowth_Spell--190.txt` |
| `rust/vidmine/templates/icons/Overgrowth_Spell--241.txt` | `crates/clash-vidmine/templates/icons/Overgrowth_Spell--241.txt` |
| `rust/vidmine/templates/icons/Overgrowth_Spell--56.txt` | `crates/clash-vidmine/templates/icons/Overgrowth_Spell--56.txt` |
| `rust/vidmine/templates/icons/Overgrowth_Spell--69.txt` | `crates/clash-vidmine/templates/icons/Overgrowth_Spell--69.txt` |
| `rust/vidmine/templates/icons/Overgrowth_Spell--extra-9.txt` | `crates/clash-vidmine/templates/icons/Overgrowth_Spell--extra-9.txt` |
| `rust/vidmine/templates/icons/Poison_Spell--19.txt` | `crates/clash-vidmine/templates/icons/Poison_Spell--19.txt` |
| `rust/vidmine/templates/icons/Poison_Spell--240.txt` | `crates/clash-vidmine/templates/icons/Poison_Spell--240.txt` |
| `rust/vidmine/templates/icons/Poison_Spell--37.txt` | `crates/clash-vidmine/templates/icons/Poison_Spell--37.txt` |
| `rust/vidmine/templates/icons/Poison_Spell--68.txt` | `crates/clash-vidmine/templates/icons/Poison_Spell--68.txt` |
| `rust/vidmine/templates/icons/Poison_Spell--extra-10.txt` | `crates/clash-vidmine/templates/icons/Poison_Spell--extra-10.txt` |
| `rust/vidmine/templates/icons/Poison_Spell--m3-9.txt` | `crates/clash-vidmine/templates/icons/Poison_Spell--m3-9.txt` |
| `rust/vidmine/templates/icons/Poison_Spell--m3-reviewed-9.txt` | `crates/clash-vidmine/templates/icons/Poison_Spell--m3-reviewed-9.txt` |
| `rust/vidmine/templates/icons/README.md` | `crates/clash-vidmine/templates/icons/README.md` |
| `rust/vidmine/templates/icons/Rage_Spell--34.txt` | `crates/clash-vidmine/templates/icons/Rage_Spell--34.txt` |
| `rust/vidmine/templates/icons/Rage_Spell--83.txt` | `crates/clash-vidmine/templates/icons/Rage_Spell--83.txt` |
| `rust/vidmine/templates/icons/Rage_Spell--m3-reviewed-24.txt` | `crates/clash-vidmine/templates/icons/Rage_Spell--m3-reviewed-24.txt` |
| `rust/vidmine/templates/icons/Rage_Spell--m3-reviewed-27.txt` | `crates/clash-vidmine/templates/icons/Rage_Spell--m3-reviewed-27.txt` |
| `rust/vidmine/templates/icons/Rage_Spell--m3-reviewed-49.txt` | `crates/clash-vidmine/templates/icons/Rage_Spell--m3-reviewed-49.txt` |
| `rust/vidmine/templates/icons/Recall_Spell--36.txt` | `crates/clash-vidmine/templates/icons/Recall_Spell--36.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--112.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--112.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--140.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--140.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--179.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--179.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--196.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--196.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--20.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--20.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--217.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--217.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--245.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--245.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--246.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--246.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--247.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--247.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--55.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--55.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--extra-26.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--extra-26.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--extra-8.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--extra-8.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--m3-8.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--m3-8.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--m3-reviewed-35.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--m3-reviewed-35.txt` |
| `rust/vidmine/templates/icons/Revive_Spell--m3-reviewed-8.txt` | `crates/clash-vidmine/templates/icons/Revive_Spell--m3-reviewed-8.txt` |
| `rust/vidmine/templates/icons/Royal_Champion--223.txt` | `crates/clash-vidmine/templates/icons/Royal_Champion--223.txt` |
| `rust/vidmine/templates/icons/Royal_Champion--227.txt` | `crates/clash-vidmine/templates/icons/Royal_Champion--227.txt` |
| `rust/vidmine/templates/icons/Royal_Champion--24.txt` | `crates/clash-vidmine/templates/icons/Royal_Champion--24.txt` |
| `rust/vidmine/templates/icons/Royal_Champion--27.txt` | `crates/clash-vidmine/templates/icons/Royal_Champion--27.txt` |
| `rust/vidmine/templates/icons/Royal_Champion--m3-reviewed-31.txt` | `crates/clash-vidmine/templates/icons/Royal_Champion--m3-reviewed-31.txt` |
| `rust/vidmine/templates/icons/Ruin_Witch--106.txt` | `crates/clash-vidmine/templates/icons/Ruin_Witch--106.txt` |
| `rust/vidmine/templates/icons/Ruin_Witch--117.txt` | `crates/clash-vidmine/templates/icons/Ruin_Witch--117.txt` |
| `rust/vidmine/templates/icons/Ruin_Witch--129.txt` | `crates/clash-vidmine/templates/icons/Ruin_Witch--129.txt` |
| `rust/vidmine/templates/icons/Ruin_Witch--210.txt` | `crates/clash-vidmine/templates/icons/Ruin_Witch--210.txt` |
| `rust/vidmine/templates/icons/Ruin_Witch--43.txt` | `crates/clash-vidmine/templates/icons/Ruin_Witch--43.txt` |
| `rust/vidmine/templates/icons/Ruin_Witch--extra-0.txt` | `crates/clash-vidmine/templates/icons/Ruin_Witch--extra-0.txt` |
| `rust/vidmine/templates/icons/Ruin_Witch--m3-reviewed-10.txt` | `crates/clash-vidmine/templates/icons/Ruin_Witch--m3-reviewed-10.txt` |
| `rust/vidmine/templates/icons/Ruin_Witch--m3-reviewed-51.txt` | `crates/clash-vidmine/templates/icons/Ruin_Witch--m3-reviewed-51.txt` |
| `rust/vidmine/templates/icons/Siege_Barracks--10.txt` | `crates/clash-vidmine/templates/icons/Siege_Barracks--10.txt` |
| `rust/vidmine/templates/icons/Siege_Barracks--extra-13.txt` | `crates/clash-vidmine/templates/icons/Siege_Barracks--extra-13.txt` |
| `rust/vidmine/templates/icons/Siege_Barracks--m3-4.txt` | `crates/clash-vidmine/templates/icons/Siege_Barracks--m3-4.txt` |
| `rust/vidmine/templates/icons/Siege_Barracks--m3-reviewed-4.txt` | `crates/clash-vidmine/templates/icons/Siege_Barracks--m3-reviewed-4.txt` |
| `rust/vidmine/templates/icons/Skeleton_Spell--m3-10.txt` | `crates/clash-vidmine/templates/icons/Skeleton_Spell--m3-10.txt` |
| `rust/vidmine/templates/icons/Skeleton_Spell--m3-reviewed-10.txt` | `crates/clash-vidmine/templates/icons/Skeleton_Spell--m3-reviewed-10.txt` |
| `rust/vidmine/templates/icons/Skeleton_Spell--m3-reviewed-30.txt` | `crates/clash-vidmine/templates/icons/Skeleton_Spell--m3-reviewed-30.txt` |
| `rust/vidmine/templates/icons/Super_Archer--211.txt` | `crates/clash-vidmine/templates/icons/Super_Archer--211.txt` |
| `rust/vidmine/templates/icons/Super_Archer--61.txt` | `crates/clash-vidmine/templates/icons/Super_Archer--61.txt` |
| `rust/vidmine/templates/icons/Super_Archer--extra-21.txt` | `crates/clash-vidmine/templates/icons/Super_Archer--extra-21.txt` |
| `rust/vidmine/templates/icons/Super_Archer--m3-reviewed-53.txt` | `crates/clash-vidmine/templates/icons/Super_Archer--m3-reviewed-53.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--104.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--104.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--115.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--115.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--134.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--134.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--164.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--164.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--173.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--173.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--186.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--186.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--230.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--230.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--m3-reviewed-18.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--m3-reviewed-18.txt` |
| `rust/vidmine/templates/icons/Super_Barbarian--m3-reviewed-34.txt` | `crates/clash-vidmine/templates/icons/Super_Barbarian--m3-reviewed-34.txt` |
| `rust/vidmine/templates/icons/Super_Bowler--2.txt` | `crates/clash-vidmine/templates/icons/Super_Bowler--2.txt` |
| `rust/vidmine/templates/icons/Super_Bowler--224.txt` | `crates/clash-vidmine/templates/icons/Super_Bowler--224.txt` |
| `rust/vidmine/templates/icons/Super_Bowler--41.txt` | `crates/clash-vidmine/templates/icons/Super_Bowler--41.txt` |
| `rust/vidmine/templates/icons/Super_Bowler--87.txt` | `crates/clash-vidmine/templates/icons/Super_Bowler--87.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--102.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--102.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--128.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--128.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--170.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--170.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--183.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--183.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--212.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--212.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--30.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--30.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--6.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--6.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--64.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--64.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--extra-12.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--extra-12.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--extra-19.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--extra-19.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--m3-1.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--m3-1.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--m3-reviewed-1.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--m3-reviewed-1.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--m3-reviewed-20.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--m3-reviewed-20.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--m3-reviewed-23.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--m3-reviewed-23.txt` |
| `rust/vidmine/templates/icons/Super_Wall_Breaker--m3-reviewed-5.txt` | `crates/clash-vidmine/templates/icons/Super_Wall_Breaker--m3-reviewed-5.txt` |
| `rust/vidmine/templates/icons/Thrower--99.txt` | `crates/clash-vidmine/templates/icons/Thrower--99.txt` |
| `rust/vidmine/templates/icons/Thrower--extra-4.txt` | `crates/clash-vidmine/templates/icons/Thrower--extra-4.txt` |
| `rust/vidmine/templates/icons/Thrower--m3-reviewed-14.txt` | `crates/clash-vidmine/templates/icons/Thrower--m3-reviewed-14.txt` |
| `rust/vidmine/templates/icons/Totem_Spell--199.txt` | `crates/clash-vidmine/templates/icons/Totem_Spell--199.txt` |
| `rust/vidmine/templates/icons/Valkyrie--39.txt` | `crates/clash-vidmine/templates/icons/Valkyrie--39.txt` |
| `rust/vidmine/templates/icons/Wall_Breaker--193.txt` | `crates/clash-vidmine/templates/icons/Wall_Breaker--193.txt` |
| `rust/vidmine/templates/icons/Wall_Breaker--52.txt` | `crates/clash-vidmine/templates/icons/Wall_Breaker--52.txt` |
| `rust/vidmine/templates/icons/Wall_Breaker--81.txt` | `crates/clash-vidmine/templates/icons/Wall_Breaker--81.txt` |
| `rust/vidmine/templates/icons/Wall_Breaker--m3-reviewed-19.txt` | `crates/clash-vidmine/templates/icons/Wall_Breaker--m3-reviewed-19.txt` |
| `rust/vidmine/templates/icons/Wall_Breaker--m3-reviewed-26.txt` | `crates/clash-vidmine/templates/icons/Wall_Breaker--m3-reviewed-26.txt` |
| `rust/vidmine/templates/icons/Wall_Breaker--m3-reviewed-33.txt` | `crates/clash-vidmine/templates/icons/Wall_Breaker--m3-reviewed-33.txt` |
| `rust/vidmine/templates/icons/Wall_Breaker--m3-reviewed-50.txt` | `crates/clash-vidmine/templates/icons/Wall_Breaker--m3-reviewed-50.txt` |
| `rust/vidmine/templates/icons/Wizard--38.txt` | `crates/clash-vidmine/templates/icons/Wizard--38.txt` |
| `rust/vidmine/templates/icons/Wizard--m3-reviewed-43.txt` | `crates/clash-vidmine/templates/icons/Wizard--m3-reviewed-43.txt` |
| `rust/vidmine/templates/icons/Wizard--m3-reviewed-45.txt` | `crates/clash-vidmine/templates/icons/Wizard--m3-reviewed-45.txt` |
| `rust/vidmine/templates/icons/Yeti--15.txt` | `crates/clash-vidmine/templates/icons/Yeti--15.txt` |
| `rust/vidmine/templates/icons/reviewed-clusters.tsv` | `crates/clash-vidmine/templates/icons/reviewed-clusters.tsv` |
| `rust/vidmine/templates/icons/reviewed-extra.tsv` | `crates/clash-vidmine/templates/icons/reviewed-extra.tsv` |
| `rust/vidmine/templates/league/Legend_I--gold.txt` | `crates/clash-vidmine/templates/league/Legend_I--gold.txt` |
| `rust/vidmine/templates/league/Legend_II--gold.txt` | `crates/clash-vidmine/templates/league/Legend_II--gold.txt` |
| `rust/vidmine/templates/league/Legend_III--gold.txt` | `crates/clash-vidmine/templates/league/Legend_III--gold.txt` |
| `rust/vidmine/templates/level-0-m3-20-1-210.txt` | `crates/clash-vidmine/templates/level-0-m3-20-1-210.txt` |
| `rust/vidmine/templates/level-0-m3-22-1-150.txt` | `crates/clash-vidmine/templates/level-0-m3-22-1-150.txt` |
| `rust/vidmine/templates/level-0-m3-22-1-180.txt` | `crates/clash-vidmine/templates/level-0-m3-22-1-180.txt` |
| `rust/vidmine/templates/level-0-m3-22-1-210.txt` | `crates/clash-vidmine/templates/level-0-m3-22-1-210.txt` |
| `rust/vidmine/templates/level-0-m3-23-1-150.txt` | `crates/clash-vidmine/templates/level-0-m3-23-1-150.txt` |
| `rust/vidmine/templates/level-0-m3-23-1-180.txt` | `crates/clash-vidmine/templates/level-0-m3-23-1-180.txt` |
| `rust/vidmine/templates/level-0-m3-23-1-210.txt` | `crates/clash-vidmine/templates/level-0-m3-23-1-210.txt` |
| `rust/vidmine/templates/level-0-m3-30-1-150.txt` | `crates/clash-vidmine/templates/level-0-m3-30-1-150.txt` |
| `rust/vidmine/templates/level-0-m3-30-1-180.txt` | `crates/clash-vidmine/templates/level-0-m3-30-1-180.txt` |
| `rust/vidmine/templates/level-0-m3-31-1-150.txt` | `crates/clash-vidmine/templates/level-0-m3-31-1-150.txt` |
| `rust/vidmine/templates/level-0-m3-31-1-180.txt` | `crates/clash-vidmine/templates/level-0-m3-31-1-180.txt` |
| `rust/vidmine/templates/level-0-m3-4-1-150.txt` | `crates/clash-vidmine/templates/level-0-m3-4-1-150.txt` |
| `rust/vidmine/templates/level-0-m3-4-1-180.txt` | `crates/clash-vidmine/templates/level-0-m3-4-1-180.txt` |
| `rust/vidmine/templates/level-0-m3-4-1-210.txt` | `crates/clash-vidmine/templates/level-0-m3-4-1-210.txt` |
| `rust/vidmine/templates/level-1-m3-1-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-1-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-1-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-1-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-1-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-1-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-1-1-150.txt` | `crates/clash-vidmine/templates/level-1-m3-1-1-150.txt` |
| `rust/vidmine/templates/level-1-m3-1-1-180.txt` | `crates/clash-vidmine/templates/level-1-m3-1-1-180.txt` |
| `rust/vidmine/templates/level-1-m3-1-1-210.txt` | `crates/clash-vidmine/templates/level-1-m3-1-1-210.txt` |
| `rust/vidmine/templates/level-1-m3-11-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-11-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-11-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-11-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-11-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-11-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-12-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-12-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-12-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-12-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-13-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-13-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-13-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-13-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-13-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-13-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-14-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-14-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-14-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-14-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-14-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-14-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-14-1-150.txt` | `crates/clash-vidmine/templates/level-1-m3-14-1-150.txt` |
| `rust/vidmine/templates/level-1-m3-14-1-180.txt` | `crates/clash-vidmine/templates/level-1-m3-14-1-180.txt` |
| `rust/vidmine/templates/level-1-m3-14-1-210.txt` | `crates/clash-vidmine/templates/level-1-m3-14-1-210.txt` |
| `rust/vidmine/templates/level-1-m3-19-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-19-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-19-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-19-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-19-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-19-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-20-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-20-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-21-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-21-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-21-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-21-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-24-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-24-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-24-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-24-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-24-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-24-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-25-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-25-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-25-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-25-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-25-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-25-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-25-1-150.txt` | `crates/clash-vidmine/templates/level-1-m3-25-1-150.txt` |
| `rust/vidmine/templates/level-1-m3-25-1-180.txt` | `crates/clash-vidmine/templates/level-1-m3-25-1-180.txt` |
| `rust/vidmine/templates/level-1-m3-25-1-210.txt` | `crates/clash-vidmine/templates/level-1-m3-25-1-210.txt` |
| `rust/vidmine/templates/level-1-m3-26-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-26-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-26-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-26-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-26-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-26-0-210.txt` |
| `rust/vidmine/templates/level-1-m3-26-1-150.txt` | `crates/clash-vidmine/templates/level-1-m3-26-1-150.txt` |
| `rust/vidmine/templates/level-1-m3-26-1-180.txt` | `crates/clash-vidmine/templates/level-1-m3-26-1-180.txt` |
| `rust/vidmine/templates/level-1-m3-26-1-210.txt` | `crates/clash-vidmine/templates/level-1-m3-26-1-210.txt` |
| `rust/vidmine/templates/level-1-m3-27-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-27-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-27-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-27-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-28-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-28-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-28-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-28-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-29-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-29-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-29-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-29-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-30-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-30-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-30-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-30-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-6-0-150.txt` | `crates/clash-vidmine/templates/level-1-m3-6-0-150.txt` |
| `rust/vidmine/templates/level-1-m3-6-0-180.txt` | `crates/clash-vidmine/templates/level-1-m3-6-0-180.txt` |
| `rust/vidmine/templates/level-1-m3-6-0-210.txt` | `crates/clash-vidmine/templates/level-1-m3-6-0-210.txt` |
| `rust/vidmine/templates/level-2-m3-12-1-150.txt` | `crates/clash-vidmine/templates/level-2-m3-12-1-150.txt` |
| `rust/vidmine/templates/level-2-m3-12-1-180.txt` | `crates/clash-vidmine/templates/level-2-m3-12-1-180.txt` |
| `rust/vidmine/templates/level-2-m3-21-1-150.txt` | `crates/clash-vidmine/templates/level-2-m3-21-1-150.txt` |
| `rust/vidmine/templates/level-2-m3-21-1-180.txt` | `crates/clash-vidmine/templates/level-2-m3-21-1-180.txt` |
| `rust/vidmine/templates/level-2-m3-27-1-150.txt` | `crates/clash-vidmine/templates/level-2-m3-27-1-150.txt` |
| `rust/vidmine/templates/level-2-m3-27-1-180.txt` | `crates/clash-vidmine/templates/level-2-m3-27-1-180.txt` |
| `rust/vidmine/templates/level-2-m3-28-1-150.txt` | `crates/clash-vidmine/templates/level-2-m3-28-1-150.txt` |
| `rust/vidmine/templates/level-2-m3-28-1-180.txt` | `crates/clash-vidmine/templates/level-2-m3-28-1-180.txt` |
| `rust/vidmine/templates/level-2-m3-29-1-150.txt` | `crates/clash-vidmine/templates/level-2-m3-29-1-150.txt` |
| `rust/vidmine/templates/level-2-m3-29-1-180.txt` | `crates/clash-vidmine/templates/level-2-m3-29-1-180.txt` |
| `rust/vidmine/templates/level-2-m3-7-0-150.txt` | `crates/clash-vidmine/templates/level-2-m3-7-0-150.txt` |
| `rust/vidmine/templates/level-2-m3-7-0-180.txt` | `crates/clash-vidmine/templates/level-2-m3-7-0-180.txt` |
| `rust/vidmine/templates/level-2-m3-7-0-210.txt` | `crates/clash-vidmine/templates/level-2-m3-7-0-210.txt` |
| `rust/vidmine/templates/level-3-m3-10-1-210.txt` | `crates/clash-vidmine/templates/level-3-m3-10-1-210.txt` |
| `rust/vidmine/templates/level-3-m3-19-1-150.txt` | `crates/clash-vidmine/templates/level-3-m3-19-1-150.txt` |
| `rust/vidmine/templates/level-3-m3-19-1-180.txt` | `crates/clash-vidmine/templates/level-3-m3-19-1-180.txt` |
| `rust/vidmine/templates/level-3-m3-19-1-210.txt` | `crates/clash-vidmine/templates/level-3-m3-19-1-210.txt` |
| `rust/vidmine/templates/level-3-m3-38-0-150.txt` | `crates/clash-vidmine/templates/level-3-m3-38-0-150.txt` |
| `rust/vidmine/templates/level-3-m3-38-0-180.txt` | `crates/clash-vidmine/templates/level-3-m3-38-0-180.txt` |
| `rust/vidmine/templates/level-3-m3-38-0-210.txt` | `crates/clash-vidmine/templates/level-3-m3-38-0-210.txt` |
| `rust/vidmine/templates/level-4-m3-11-1-150.txt` | `crates/clash-vidmine/templates/level-4-m3-11-1-150.txt` |
| `rust/vidmine/templates/level-4-m3-11-1-180.txt` | `crates/clash-vidmine/templates/level-4-m3-11-1-180.txt` |
| `rust/vidmine/templates/level-4-m3-11-1-210.txt` | `crates/clash-vidmine/templates/level-4-m3-11-1-210.txt` |
| `rust/vidmine/templates/level-4-m3-13-1-150.txt` | `crates/clash-vidmine/templates/level-4-m3-13-1-150.txt` |
| `rust/vidmine/templates/level-4-m3-13-1-180.txt` | `crates/clash-vidmine/templates/level-4-m3-13-1-180.txt` |
| `rust/vidmine/templates/level-4-m3-13-1-210.txt` | `crates/clash-vidmine/templates/level-4-m3-13-1-210.txt` |
| `rust/vidmine/templates/level-4-m3-15-0-150.txt` | `crates/clash-vidmine/templates/level-4-m3-15-0-150.txt` |
| `rust/vidmine/templates/level-4-m3-15-0-180.txt` | `crates/clash-vidmine/templates/level-4-m3-15-0-180.txt` |
| `rust/vidmine/templates/level-4-m3-3-0-150.txt` | `crates/clash-vidmine/templates/level-4-m3-3-0-150.txt` |
| `rust/vidmine/templates/level-4-m3-3-0-180.txt` | `crates/clash-vidmine/templates/level-4-m3-3-0-180.txt` |
| `rust/vidmine/templates/level-4-m3-3-0-210.txt` | `crates/clash-vidmine/templates/level-4-m3-3-0-210.txt` |
| `rust/vidmine/templates/level-5-m3-24-1-150.txt` | `crates/clash-vidmine/templates/level-5-m3-24-1-150.txt` |
| `rust/vidmine/templates/level-5-m3-24-1-180.txt` | `crates/clash-vidmine/templates/level-5-m3-24-1-180.txt` |
| `rust/vidmine/templates/level-5-m3-24-1-210.txt` | `crates/clash-vidmine/templates/level-5-m3-24-1-210.txt` |
| `rust/vidmine/templates/level-5-m3-33-0-150.txt` | `crates/clash-vidmine/templates/level-5-m3-33-0-150.txt` |
| `rust/vidmine/templates/level-5-m3-33-0-180.txt` | `crates/clash-vidmine/templates/level-5-m3-33-0-180.txt` |
| `rust/vidmine/templates/level-5-m3-5-1-150.txt` | `crates/clash-vidmine/templates/level-5-m3-5-1-150.txt` |
| `rust/vidmine/templates/level-5-m3-5-1-180.txt` | `crates/clash-vidmine/templates/level-5-m3-5-1-180.txt` |
| `rust/vidmine/templates/level-5-m3-5-1-210.txt` | `crates/clash-vidmine/templates/level-5-m3-5-1-210.txt` |
| `rust/vidmine/templates/level-5-m3-6-1-150.txt` | `crates/clash-vidmine/templates/level-5-m3-6-1-150.txt` |
| `rust/vidmine/templates/level-5-m3-6-1-180.txt` | `crates/clash-vidmine/templates/level-5-m3-6-1-180.txt` |
| `rust/vidmine/templates/level-5-m3-6-1-210.txt` | `crates/clash-vidmine/templates/level-5-m3-6-1-210.txt` |
| `rust/vidmine/templates/level-6-m3-0-0-150.txt` | `crates/clash-vidmine/templates/level-6-m3-0-0-150.txt` |
| `rust/vidmine/templates/level-6-m3-0-0-180.txt` | `crates/clash-vidmine/templates/level-6-m3-0-0-180.txt` |
| `rust/vidmine/templates/level-6-m3-37-0-150.txt` | `crates/clash-vidmine/templates/level-6-m3-37-0-150.txt` |
| `rust/vidmine/templates/level-6-m3-37-0-180.txt` | `crates/clash-vidmine/templates/level-6-m3-37-0-180.txt` |
| `rust/vidmine/templates/level-7-m3-17-0-150.txt` | `crates/clash-vidmine/templates/level-7-m3-17-0-150.txt` |
| `rust/vidmine/templates/level-7-m3-17-0-180.txt` | `crates/clash-vidmine/templates/level-7-m3-17-0-180.txt` |
| `rust/vidmine/templates/level-7-m3-22-0-150.txt` | `crates/clash-vidmine/templates/level-7-m3-22-0-150.txt` |
| `rust/vidmine/templates/level-7-m3-22-0-180.txt` | `crates/clash-vidmine/templates/level-7-m3-22-0-180.txt` |
| `rust/vidmine/templates/level-7-m3-22-0-210.txt` | `crates/clash-vidmine/templates/level-7-m3-22-0-210.txt` |
| `rust/vidmine/templates/level-7-m3-31-0-150.txt` | `crates/clash-vidmine/templates/level-7-m3-31-0-150.txt` |
| `rust/vidmine/templates/level-7-m3-31-0-180.txt` | `crates/clash-vidmine/templates/level-7-m3-31-0-180.txt` |
| `rust/vidmine/templates/level-7-m3-32-0-150.txt` | `crates/clash-vidmine/templates/level-7-m3-32-0-150.txt` |
| `rust/vidmine/templates/level-7-m3-32-0-180.txt` | `crates/clash-vidmine/templates/level-7-m3-32-0-180.txt` |
| `rust/vidmine/templates/level-7-m3-32-0-210.txt` | `crates/clash-vidmine/templates/level-7-m3-32-0-210.txt` |
| `rust/vidmine/templates/level-7-m3-4-0-150.txt` | `crates/clash-vidmine/templates/level-7-m3-4-0-150.txt` |
| `rust/vidmine/templates/level-7-m3-4-0-180.txt` | `crates/clash-vidmine/templates/level-7-m3-4-0-180.txt` |
| `rust/vidmine/templates/level-7-m3-4-0-210.txt` | `crates/clash-vidmine/templates/level-7-m3-4-0-210.txt` |
| `rust/vidmine/templates/level-7-m3-8-0-150.txt` | `crates/clash-vidmine/templates/level-7-m3-8-0-150.txt` |
| `rust/vidmine/templates/level-7-m3-8-0-180.txt` | `crates/clash-vidmine/templates/level-7-m3-8-0-180.txt` |
| `rust/vidmine/templates/level-7-m3-8-0-210.txt` | `crates/clash-vidmine/templates/level-7-m3-8-0-210.txt` |
| `rust/vidmine/templates/level-8-m3-18-0-150.txt` | `crates/clash-vidmine/templates/level-8-m3-18-0-150.txt` |
| `rust/vidmine/templates/level-8-m3-18-0-180.txt` | `crates/clash-vidmine/templates/level-8-m3-18-0-180.txt` |
| `rust/vidmine/templates/level-8-m3-9-0-150.txt` | `crates/clash-vidmine/templates/level-8-m3-9-0-150.txt` |
| `rust/vidmine/templates/level-8-m3-9-0-180.txt` | `crates/clash-vidmine/templates/level-8-m3-9-0-180.txt` |
| `rust/vidmine/templates/level-8-m3-9-0-210.txt` | `crates/clash-vidmine/templates/level-8-m3-9-0-210.txt` |
| `rust/vidmine/templates/level-9-m3-10-0-210.txt` | `crates/clash-vidmine/templates/level-9-m3-10-0-210.txt` |
| `rust/vidmine/templates/level-9-m3-16-0-150.txt` | `crates/clash-vidmine/templates/level-9-m3-16-0-150.txt` |
| `rust/vidmine/templates/level-9-m3-16-0-180.txt` | `crates/clash-vidmine/templates/level-9-m3-16-0-180.txt` |
| `rust/vidmine/templates/level-9-m3-16-0-210.txt` | `crates/clash-vidmine/templates/level-9-m3-16-0-210.txt` |
| `rust/vidmine/templates/level-9-m3-2-0-150.txt` | `crates/clash-vidmine/templates/level-9-m3-2-0-150.txt` |
| `rust/vidmine/templates/level-9-m3-2-0-180.txt` | `crates/clash-vidmine/templates/level-9-m3-2-0-180.txt` |
| `rust/vidmine/templates/level-9-m3-2-0-210.txt` | `crates/clash-vidmine/templates/level-9-m3-2-0-210.txt` |
| `rust/vidmine/templates/level-9-m3-23-0-150.txt` | `crates/clash-vidmine/templates/level-9-m3-23-0-150.txt` |
| `rust/vidmine/templates/level-9-m3-23-0-180.txt` | `crates/clash-vidmine/templates/level-9-m3-23-0-180.txt` |
| `rust/vidmine/templates/level-9-m3-23-0-210.txt` | `crates/clash-vidmine/templates/level-9-m3-23-0-210.txt` |
| `rust/vidmine/templates/level-9-m3-35-0-150.txt` | `crates/clash-vidmine/templates/level-9-m3-35-0-150.txt` |
| `rust/vidmine/templates/level-9-m3-35-0-180.txt` | `crates/clash-vidmine/templates/level-9-m3-35-0-180.txt` |
| `rust/vidmine/templates/level-9-m3-35-0-210.txt` | `crates/clash-vidmine/templates/level-9-m3-35-0-210.txt` |
| `rust/vidmine/templates/level-9-m3-36-0-150.txt` | `crates/clash-vidmine/templates/level-9-m3-36-0-150.txt` |
| `rust/vidmine/templates/level-9-m3-36-0-180.txt` | `crates/clash-vidmine/templates/level-9-m3-36-0-180.txt` |
| `rust/vidmine/templates/level-9-m3-36-0-210.txt` | `crates/clash-vidmine/templates/level-9-m3-36-0-210.txt` |
| `rust/vidmine/templates/level-9-m3-5-0-150.txt` | `crates/clash-vidmine/templates/level-9-m3-5-0-150.txt` |
| `rust/vidmine/templates/level-9-m3-5-0-180.txt` | `crates/clash-vidmine/templates/level-9-m3-5-0-180.txt` |
| `rust/vidmine/templates/level-9-m3-5-0-210.txt` | `crates/clash-vidmine/templates/level-9-m3-5-0-210.txt` |
| `rust/vidmine/templates/prep-label.txt` | `crates/clash-vidmine/templates/prep-label.txt` |
| `rust/vidmine/templates/prep-phone-label.txt` | `crates/clash-vidmine/templates/prep-phone-label.txt` |
| `rust/vidmine/templates/prep-q-label.txt` | `crates/clash-vidmine/templates/prep-q-label.txt` |
| `rust/vidmine/templates/replay-label.txt` | `crates/clash-vidmine/templates/replay-label.txt` |
| `rust/vidmine/templates/result-label.txt` | `crates/clash-vidmine/templates/result-label.txt` |
| `rust/vidmine/templates/townhalls/README.md` | `crates/clash-vidmine/templates/townhalls/README.md` |
| `rust/vidmine/templates/townhalls/provenance.tsv` | `crates/clash-vidmine/templates/townhalls/provenance.tsv` |
| `rust/vidmine/templates/townhalls/th16-local-web-base-a.rgb` | `crates/clash-vidmine/templates/townhalls/th16-local-web-base-a.rgb` |
| `rust/vidmine/templates/townhalls/th16-local-web-base-b.rgb` | `crates/clash-vidmine/templates/townhalls/th16-local-web-base-b.rgb` |
| `rust/vidmine/templates/townhalls/th17-MtZsw40-Sr0-a01.rgb` | `crates/clash-vidmine/templates/townhalls/th17-MtZsw40-Sr0-a01.rgb` |
| `rust/vidmine/templates/townhalls/th17-S50ZlHsVhfQ-a01.rgb` | `crates/clash-vidmine/templates/townhalls/th17-S50ZlHsVhfQ-a01.rgb` |
| `rust/vidmine/templates/townhalls/th18-55LNGorvOqw-a01-prep.rgb` | `crates/clash-vidmine/templates/townhalls/th18-55LNGorvOqw-a01-prep.rgb` |
| `rust/vidmine/templates/townhalls/th18-WRFPgMQfRmI-a01-prep.rgb` | `crates/clash-vidmine/templates/townhalls/th18-WRFPgMQfRmI-a01-prep.rgb` |
| `rust/vidmine/templates/townhalls/th18-WRFPgMQfRmI-a02-prep.rgb` | `crates/clash-vidmine/templates/townhalls/th18-WRFPgMQfRmI-a02-prep.rgb` |
| `rust/vidmine/templates/townhalls/th18-WRFPgMQfRmI-a03-prep.rgb` | `crates/clash-vidmine/templates/townhalls/th18-WRFPgMQfRmI-a03-prep.rgb` |
| `rust/vidmine/templates/townhalls/th18-WRFPgMQfRmI-a06-prep.rgb` | `crates/clash-vidmine/templates/townhalls/th18-WRFPgMQfRmI-a06-prep.rgb` |
| `rust/vidmine/templates/townhalls/th18-WRFPgMQfRmI-a10-prep.rgb` | `crates/clash-vidmine/templates/townhalls/th18-WRFPgMQfRmI-a10-prep.rgb` |

## Boundary changes and dispositions

- Extracted `load::Node` to data; `load` re-exports it and implements the
  runtime-local team parsing extension. The accepted type list and errors are
  unchanged. Catalog no longer imports battle loading.
- Extracted the exact float formatter to data and re-exported it from engine
  trace. Extracted the exact CLI JSON serializer and fidelity wire/hash helpers
  to data. Kept plan-wire helpers separate from fidelity helpers because their
  existing missing/null handling differs. These are relocations of the original
  implementations, with no parser or number-policy replacement.
- Moved the pure siege predicate to data/content. The executor now imports
  data's plan-wire helpers rather than armies/compiler code.
- Kept attacker execution in engine under `plans/attacker.rs`. Compiler and
  playbook fitting live in plans; scoring/scouting live in scoring.
- Captured 11 distinct prepared synthetic executor inputs before removing the
  compiler dependency from engine tests. `fixtures/playbooks/executor.jsonl`
  records the requests, synthetic builds/playbooks and prepared plans. The
  compiler checks every frozen preparation in its owning crate, while engine
  keeps its original private runtime assertions. Engine has no tool dev-deps.
- Split raw share-code decoding/name resolution and observation identity into
  data/battlelog. Kept observed-build conversion and scoring seed composition
  in fidelity. Shared snapshot readers moved to data/snapshots; observation
  assembly remains in fidelity. No share-code/hash semantics were duplicated.
- Layout production code contains model, admission, geometry and rule loading.
  Local rule derivation and layout proof/dispatch moved to CLI. The future
  dataimport crate will take the importer in G3; no port was added in G2.
- Fidelity and video expose argument-injectable library command entry points.
  The CLI dispatches every previous engine command plus fidelity/video and the
  planned simulation/plan/proof aliases. Three compatibility binaries forward
  through the same dispatch. Video's independent JSON implementation remains.
- Compiler/scoring defaults and existing data files are unchanged. Armysearch
  verification explicitly selects `data/your-levels.json` after compiler load,
  so the proof's account does not silently acquire the optional live overlay.
  Plan goldens retain their accepted compiler input/default contract; personal
  data cleanup and account-default changes belong to later steps.
- Source fingerprints now enumerate `crates/` rather than `rust/src/`. Fidelity
  fingerprints use root `Cargo.toml`; executable hashes naturally change after
  rebuilding. Existing fits/checkpoints with old source identities are not
  relabeled as new calibration evidence.
- `rust/src/fidelity/archive_export.rs` was unregistered historical code and
  is removed from active source. Historical reproduction instructions in
  `docs/FIDELITY_RUST.md` still obtain its original version via Git archive.
- The former engine manifest/lockfile become the root workspace manifest and
  shared lockfile. Vidmine's nested workspace/profile and duplicate
  `rust/vidmine/Cargo.lock` are removed. `rust/verify.sh` remains a thin wrapper.
- Python `src/`, `tools/`, protected checkouts, real profiles, replay media,
  raw captures, transcripts, credentials and all existing `data/` inputs were
  not edited. The six pre-existing untracked data files were left untouched.
  No Python was executed, no dependencies/components downloaded, and no Git
  index or commit was written.

New extracted files in the move inventory (`node.rs`, `float.rs`, `wire.rs`,
`plan_wire.rs`, `battlelog.rs`, `snapshots.rs`, and `layout/import.rs`) were first
created alongside the old modules and checked before relocation. Their sources
are respectively load, trace, compile_cli plus fidelity/io, armies,
fidelity/decode, fidelity/history, and layout/rules. Compiler test support is
split from the original test_support into `crates/clash-plans/src/test_support.rs`.
Crate roots, the umbrella dispatcher and thin binary entry points are new or
replaced integration wiring.

## Frozen bytes

SHA-256 was recorded before changes in `/tmp/clash-g1-hashes-before.txt` and
checked again after relocation. Both expectation files and the battle inputs
are byte-identical; no golden record command was run.

| Before → after path | SHA-256 before and after |
| --- | --- |
| `rust/golden/cases.jsonl` → `fixtures/golden/cases.jsonl` | `cea706d86516a2100876f9aa4ec7cdd5de32f691202f9a6d049b64e690d172ab` |
| `rust/golden/expected.jsonl` → `fixtures/golden/expected.jsonl` | `40446127d538f7bab2a86ab9c7fcae8b3a725c4ceb462fd2d95236cb38af0ab4` |
| `rust/golden/plans.jsonl` → `fixtures/golden/plans.jsonl` | `3ea43b38a16c4608aa04ab308c2a0e1ba645ed2cd3b89ad386235d8c44d32681` |
| `rust/data/catalog.json` (unchanged path) | `91f122ee1649c50fca3cda9bb4d36b837dd2714e071e025b010613a5424979cc` |
| `rust/data/base_rules.json` (unchanged path) | `9b2e389104a7319eb3e0607e25326c585799362cdb250f9b3532fd43602bd58b` |
| `rust/data/clan_castle.json` (unchanged path) | `a7ffb1d265d51ddfa7fc853ee42bc6fcb9b23d59b3e88d08d73f3a280fd207c3` |
| `rust/data/target17.json` (unchanged path) | `5eaebfc7b5912fa6b55783cd742f3eb106979d9b204d2ae61e8783e41a690ff6` |
| `rust/data/target18.json` (unchanged path) | `47e88a7f1caa79f6110e2a09260dad57a10eb03c16c3b802a865012a4a0a9a03` |

## Dependency evidence

`cargo tree -p clash-engine --offline` in WSL:

```text
clash-engine v0.1.0
├── clash-data v0.1.0
└── clash-layout v0.1.0
    └── clash-data v0.1.0
```

The closure has no compiler, scoring, search, fidelity, video or CLI crate,
including in development/test dependencies. Every workspace dependency is a
local path; there are no external Rust dependencies.

## Acceptance evidence (WSL, 2026-10-25)

Final gate invocation, with the caller's working directory set to `/tmp`:

```sh
. ~/.cargo/env
CARGO_BUILD_JOBS=4 CARGO_TARGET_DIR=/tmp/clash-target-ws \
  /mnt/c/Users/jarod/Documents/clash-lab/scripts/verify.sh \
  > /tmp/clash-g2-verify.log 2>&1
```

Exit status **0**, ending with `ALL CHECKS PASSED`. The build uses the installed
stable `rustc 1.99.1 (58cf8f9c3 2026-10-13)` and Cargo 1.99.1. No network
provisioning is part of the gate. Reports use a unique temporary directory,
which the EXIT trap removes on both success and failure; the full console log
above remains available locally.

| Check | Result |
| --- | --- |
| `cargo fmt --all -- --check` | Passed |
| Workspace, all targets, release build with `--locked --offline` | Passed |
| Workspace release tests with `--locked --offline` | 85 passed, 0 failed; 2 pre-existing documentation examples ignored |
| Battle golden check, 1 worker | 868/868, 0 failures |
| Battle golden check, 4 workers | 868/868, 0 failures; same full-trace/outcome expectations |
| Plan golden check | 1354/1354, 0 failures |
| Guardian check | 50/50 declared synthetic fixtures |
| Armysearch proof | Passed 4096 legality cases and 4096 program cases; native/program determinism at 1/4/16 workers, resume/cache/budget/holdout checks retained |
| Layout proof | Importer, TH16/17/18 inventories, admission/geometry and all 100000 mutations passed; 2944 accepted, 97056 rejected |
| Basesearch M2 proof | Passed 93000 operator attempts (1000 per TH/operator), 81864 accepted engine builds, 3000 accepted crossovers, workers 1/4/16/1 |
| Final vidmine tests | 24/24 passed (also included in the 85 workspace tests) |
| Frozen golden/catalog/rules/castle/target SHA-256 checks | All eight files match their pre-restructure bytes |
| Engine dependency closure | Data and layout only, including test/development closure |
| Rename inventory audit | All 765 removed tracked paths have existing logged destinations; two additional removals explicitly accounted for above |
| Python and data diff audit | No changes under `src/`, `tools/`, `data/`, or `rust/data/` |
| Shell syntax and `git diff --check` | Passed |

Clippy is **unavailable** in the installed toolchain (`cargo-clippy` is not
installed); no component was fetched and no Clippy warning audit is claimed.
The gate reports this limitation. Where Clippy is installed, it first tries
`-D warnings`; if existing warnings prevent that, it prints the complete strict
report and runs ordinary Clippy, whose actual errors still fail verification.
No warning suppression or mechanics cleanup was added for this migration.

Before relocation, helper extraction also passed 868 battle goldens and 1354
plan goldens, the frozen executor-input compiler test and fidelity tests. The
boundary M2 receipt passed 744 attempts / 24 crossovers at 1/4/16/1 workers.
An earlier baseline M2 receipt was discarded because a concurrent rebuild
replaced its executable before its final hash read; the final full workspace
run above kept binaries fixed throughout and supersedes that interrupted run.

Additional commands executed from `/tmp` compared umbrella and compatibility
outputs byte-for-byte: help for `clash`/`baselab-engine`, share-code decoding for
`clash fidelity`/`fidelity`, video help for `clash video`/`vidmine`, and native plan
compilation for `clash plan compile`/`baselab-engine compile`. A missing golden
expectation file returned a failing status. No additional mechanics fixtures
were needed. Historical protected checkouts remain untouched and HEAD is still
`24d25e7997f3e90a238340fc7dbcfbb953d5c9ff`.

These checks establish synthetic regression preservation and deterministic
workspace behavior. They do not establish real-game calibration. Windows,
Python ports/deletion, data reorganization and future tool-crate ports remain
outside G1/G2.
