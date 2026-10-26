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

# G5a — data layout and Rust workspace documentation (2026-10-25)

Workspace: `/mnt/c/Users/jarod/Documents/clash-lab`, branch `sim-accuracy`.
One writer; no commit or index update, downloads, Python execution, baseline
edits or sibling-checkout edits. The pre-existing `.github/workflows/ci.yml`
change, `hunt-ported.out` and `target-ws/` are outside this task and left alone.
Builds/runs source `~/.cargo/env` and use `CARGO_TARGET_DIR=/tmp/clash-target-g5`.

## Layout and byte-preservation decisions

- `data/source/` owns the existing pinned external/model inputs, including
  ClashKing snapshots, CSVs, balance overrides, mechanics claims/evidence,
  armies, playbooks, calibration priors, layouts, reference bases and the
  explicitly requested legacy live log/account/replay inputs. Existing source
  basenames are retained directly under this directory to keep directory-based
  readers straightforward. New personal and derived work belongs in `local/`.
- The upstream video catalog moves from `data/catalog.json` to
  `data/source/catalog.json`. It remains distinct from the runtime catalog;
  their schemas and bytes are not merged or rewritten.
- All five `rust/data/*` files move to `data/generated/`, alongside the existing
  registry and manifest. These seven pinned outputs are byte-identical. The
  Castle table and declared synthetic TH17/18 targets retain their contracts.
- Three licenses move to `data/licenses/`. Existing ignored backups/logs and
  the already-present 1,561-file ignored wiki mirror move under `data/source/`;
  nothing is downloaded. Ignore patterns follow those moves. The inventory
  below records every file, including ignored files; it does not version their
  contents. The eight other ignored files retain their prior ignored status.
- `rust/.gitignore` and `rust/verify.sh` are removed, then the entire empty
  `rust/` directory is removed, including its empty metadata directory shells.
  `scripts/verify.sh` is the only verification entry point.
- `data/source/live/base-history.json` and the three source replay JSON files
  update operational layout paths (and the history's snapshot/wiki path text).
  No observed values, timestamps or confidence statements change.
- All other moved file payloads are preserved by filesystem rename. In
  particular, calibration/report ancestry, source hashes, historical manifest
  keys and provenance identifiers are not rebound to the new inputs. Original
  CRLF bytes in some source inputs remain intact.
- Plan goldens contain the old `data/playbooks/fireball-warden.json` spelling
  only in historical army `idea` prose. No reader opens that string; the text
  and all golden bytes remain untouched. The same prose in the source army
  library remains untouched so compiler preparation stays identical.
- The rules importer loads the new ClashKing path but emits the same frozen
  provenance strings as before. Its first relocated gate detected changed
  provenance output; those strings were restored before acceptance. The
  importer still compares its entire derived document with pinned rules.
  This preserves rule identities without regenerating data or weakening checks.

Runtime catalog precedence is explicit CLI/configuration path, `CLASH_CATALOG`,
legacy `BASELAB_CATALOG`, then `ROOT/data/generated/catalog.json`. The legacy
name remains supported. Other `BASELAB_*` behavior/settings are unchanged.
Explicit fidelity catalog paths keep their original root-relative resolution.
The verification script explicitly selects the pinned catalog and army-proof
account, rather than inheriting a caller's catalog override.

## Reader and fixture changes

Every changed reader/helper is listed below. Directory scans, fingerprints and
compile-time includes are part of this inventory, not just string defaults.

| File | Change |
| --- | --- |
| `crates/clash-data/src/catalog.rs` | Central catalog override/default resolution and relocated weights documentation. |
| `crates/clash-data/src/battlelog.rs` | Decoder reads ClashKing names from `data/source/`. |
| `crates/clash-data/src/snapshots.rs` | Default history layouts and account inventory use `data/source/`. |
| `crates/clash-cli/src/legacy.rs` | Simulation, traces, jobs, guardian/golden/layout checks use shared catalog resolution. |
| `crates/clash-cli/src/compile_cli.rs` | Repository discovery uses source army library; compilation honors new/legacy catalog variables. |
| `crates/clash-cli/src/scoring_cli.rs` | Catalog environment selection and default generated catalog path. |
| `crates/clash-cli/src/layout_rules.rs` | Actual ClashKing reader moves; frozen provenance identifiers stay unchanged. |
| `crates/clash-cli/src/layout_proof.rs` | Generated rules/targets and relocated source corpus; sorted filesystem inventory covers unstaged moves and rejects an empty corpus. |
| `crates/clash-cli/src/lib.rs` | Umbrella help lists dataimport and playbook namespaces. |
| `crates/clash-plans/src/armies.rs` | Army, policy, account and live-overlay readers scan `data/source/`; logical library IDs stay unchanged. |
| `crates/clash-plans/src/compile.rs` | Source playbook/gap readers and generated Castle table; account/table comments follow paths. |
| `crates/clash-plans/src/test_support.rs` | Pinned test catalog uses `data/generated/`. |
| `crates/clash-scoring/src/scoring.rs` | Calibration priors, armies, playbooks, battle observations and ClashKing directory scans use `data/source/`. |
| `crates/clash-armysearch/src/lib.rs` | Root discovery and shared catalog default/override selection. |
| `crates/clash-armysearch/src/operators.rs` | Additional meta-army discovery scans `data/source/`. |
| `crates/clash-armysearch/src/report.rs` | Input fingerprints and fingerprint proof enumerate source/generated/compiler inputs and source playbooks. |
| `crates/clash-armysearch/src/score.rs` | Default reference layouts move to source; TH17/18 targets move to generated. |
| `crates/clash-basesearch/src/cli.rs` | Shared catalog selection, generated rules and Castle fingerprint input. |
| `crates/clash-basesearch/src/completion_tests.rs` | Generated catalog/rule test context. |
| `crates/clash-basesearch/src/proof.rs` | Generated rules/catalog for production and synthetic proof contexts. |
| `crates/clash-fidelity/src/lib.rs` | Shared catalog override/default, root-relative explicit catalog, source priors/log/history. |
| `crates/clash-fidelity/src/board.rs` | Source CV prior, history, log and own-layout defaults; prior hash guard unchanged. |
| `crates/clash-fidelity/src/observed.rs` | Source account inventory and replay corpus. |
| `crates/clash-fidelity/src/provenance.rs` | Prior/report discovery and source/generated fingerprint paths; original ancestry hashes unchanged. |
| `crates/clash-fidelity/src/replay.rs` | Source calibration and army inputs. |
| `crates/clash-fidelity/src/th18.rs` | Source TH18 reference layout paths. |
| `crates/clash-dataimport/src/catalog/build.rs` | Source ClashKing, overrides and warden weights, including override hashing. |
| `crates/clash-dataimport/src/catalog/csv.rs` | Source gamecsv directory. |
| `crates/clash-dataimport/src/catalog/mod.rs` | Source ClashKing reader and ignored source wiki default. |
| `crates/clash-dataimport/src/catalog/tests.rs` | Source/generated acceptance paths and isolated source-only perturbation root; no generated inputs introduced. |
| `crates/clash-dataimport/src/digitize/mod.rs` | Shared catalog selection and generated rules. |
| `crates/clash-playbook-tools/src/lib.rs` | Source playbook directory and reviewed gap-output default; corpus remains ignored `local/sources/`. |
| `crates/clash-playbook-tools/tests/pipeline.rs` | Relocated committed playbook corpus. |
| `crates/clash-vidmine/src/identity.rs` | Both independent video identity catalog paths and source receipts use `data/source/`. |
| `crates/clash-engine/src/test_support.rs` | Pinned generated catalog for executor unit tests. |
| `crates/clash-engine/tests/support/mechanics.rs` | Shared current/legacy catalog variable selection and generated default. |
| `crates/clash-engine/tests/mechanics.rs` | `include_str!` reads source CSV `globals.csv`; data values unchanged. |
| `crates/clash-engine/src/battle.rs` | Wiki citation comment follows the ignored source mirror. |
| `crates/clash-engine/src/plans/attacker.rs` | Same wiki citation-comment relocation; executor logic unchanged. |
| `fixtures/layout/geometry.json` | Target17/18 lookup keys point at `data/generated/`; expected geometry numbers unchanged. |
| `scripts/verify.sh` | Absolute generated catalog via `CLASH_CATALOG`; explicit relocated proof account. |
| `data/source/live/base-history.json` | Operational reference-layout and documented snapshot/wiki paths. |
| `data/source/replays/2026-10-03-afghanistan-dragons.json` | Source-layout path spelling. |
| `data/source/replays/2026-10-03-paw-paw-rootriders.json` | Source-layout path spelling. |
| `data/source/replays/2026-10-21-maroon-machine.json` | Operational source-layout path. |
| `.gitignore` | Source wiki mirror and dated backup paths; remove obsolete rust target rule. |

No `include_bytes!` refers to moved data; synthetic digitizer images and video
resources stay crate-local. Low-level catalog/rules loaders still accept explicit
paths. Source hash manifests relative to the wiki mirror remain unchanged.

## Documentation changes

`README.md` is rewritten for the Rust workspace, with all twelve crate purposes,
engine/tool boundaries, build/command examples, data/local ownership and the
verification/golden contract. `docs/ARCHITECTURE.md` adds the actual manifest
dependency graph and source → dataimport → generated → engine / plans → engine
→ scoring → tools flows. `AGENTS.md` records Rust-only work, the commit gate,
frozen goldens, local/private data, external video paths and no Supercell API key.

The following documents update current data paths, examples, source links,
catalog-variable spelling, layout status or navigation. Dated historical
receipts remain provenance; G4/the original restructure plan gain explicit
current-status notes rather than rewriting their old inventories.

| File | Update |
| --- | --- |
| `THIRD_PARTY.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `crates/clash-basesearch/README.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `crates/clash-dataimport/src/digitize/README.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `crates/clash-vidmine/README.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/BASE_DESIGN_PRINCIPLES.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/BASE_SEARCH_CONTRACTS.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/BASE_SEARCH_RUST_DESIGN.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/BUILDER_SCREENSHOTS.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/CLEANUP_G4.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/DATA_PIPELINE.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/ENGINE_STATUS.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/GOLDEN.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/MOVE_LIBRARY_DESIGN.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/PARAMS.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/PB1B.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/PLAYBOOK_PIPELINE.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/PROBE_CARDS.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/README.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/RESTRUCTURE_PLAN.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/RM1_EVIDENCE.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/ROADMAP.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/RUST_PORT.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/SCOUTING.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/SIMULATION_METHODS_RESEARCH.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/VIDEO_MEASUREMENTS.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/playbook-completion.md` | Current source/generated paths, commands or status; historical evidence remains labeled. |
| `docs/ARCHITECTURE.md` | New crate graph, data flow and ownership/runtime contracts. |

## Every moved tracked file

There are 125 tracked file moves, plus the two removed Rust-directory support
files listed above. This list is independent of Git rename similarity heuristics.

| Before | After |
| --- | --- |
| `data/CLASHKING-LICENSE.txt` | `data/licenses/CLASHKING-LICENSE.txt` |
| `data/DATA-LICENSE.txt` | `data/licenses/DATA-LICENSE.txt` |
| `data/SECONDARY-LICENSE.txt` | `data/licenses/SECONDARY-LICENSE.txt` |
| `data/attacker-policy.json` | `data/source/attacker-policy.json` |
| `data/balance-claims.json` | `data/source/balance-claims.json` |
| `data/balance-overrides.json` | `data/source/balance-overrides.json` |
| `data/baselab-calibration-v1.json` | `data/source/baselab-calibration-v1.json` |
| `data/baselab-calibration.json` | `data/source/baselab-calibration.json` |
| `data/battle-policies/development-full-army.json` | `data/source/battle-policies/development-full-army.json` |
| `data/battle-policies/development-th16.json` | `data/source/battle-policies/development-th16.json` |
| `data/battle-policies/experimental-duke-isolation.json` | `data/source/battle-policies/experimental-duke-isolation.json` |
| `data/battle-policies/experimental-higher-th.json` | `data/source/battle-policies/experimental-higher-th.json` |
| `data/battle-policies/layout-search-crafted-experimental.json` | `data/source/battle-policies/layout-search-crafted-experimental.json` |
| `data/battle-policies/recipe-equipment.json` | `data/source/battle-policies/recipe-equipment.json` |
| `data/battle-policies/recipe-frosty.json` | `data/source/battle-policies/recipe-frosty.json` |
| `data/battle-policies/recipe-log-launcher.json` | `data/source/battle-policies/recipe-log-launcher.json` |
| `data/battle-policies/recipe-spells.json` | `data/source/battle-policies/recipe-spells.json` |
| `data/battle-policies/recipe-troops.json` | `data/source/battle-policies/recipe-troops.json` |
| `data/builder-bases/blueprint-ranked-2026-06-seed.json` | `data/source/builder-bases/blueprint-ranked-2026-06-seed.json` |
| `data/builder-bases/blueprint-ranked-2026-06.jpg` | `data/source/builder-bases/blueprint-ranked-2026-06.jpg` |
| `data/builder-bases/blueprint-ranked-2026-06.json` | `data/source/builder-bases/blueprint-ranked-2026-06.json` |
| `data/builder-bases/candidates.json` | `data/source/builder-bases/candidates.json` |
| `data/builder-bases/loay-samy-cc92583-seed.json` | `data/source/builder-bases/loay-samy-cc92583-seed.json` |
| `data/builder-bases/loay-samy-cc92583.jpg` | `data/source/builder-bases/loay-samy-cc92583.jpg` |
| `data/builder-bases/loay-samy-cc92583.json` | `data/source/builder-bases/loay-samy-cc92583.json` |
| `data/builder-bases/reyferro-cc101332-seed.json` | `data/source/builder-bases/reyferro-cc101332-seed.json` |
| `data/builder-bases/reyferro-cc101332.jpg` | `data/source/builder-bases/reyferro-cc101332.jpg` |
| `data/builder-bases/reyferro-cc101332.json` | `data/source/builder-bases/reyferro-cc101332.json` |
| `data/builder-bases/reyferro-cc96154-seed.json` | `data/source/builder-bases/reyferro-cc96154-seed.json` |
| `data/builder-bases/reyferro-cc96154.jpg` | `data/source/builder-bases/reyferro-cc96154.jpg` |
| `data/builder-bases/reyferro-cc96154.json` | `data/source/builder-bases/reyferro-cc96154.json` |
| `data/builder-bases/thakur-trophy-2026-10-draft.jpg` | `data/source/builder-bases/thakur-trophy-2026-10-draft.jpg` |
| `data/builder-bases/thakur-trophy-2026-10-draft.json` | `data/source/builder-bases/thakur-trophy-2026-10-draft.json` |
| `data/catalog.json` | `data/source/catalog.json` |
| `data/clashking-static-data.json` | `data/source/clashking-static-data.json` |
| `data/clashking-static-source.json` | `data/source/clashking-static-source.json` |
| `data/custom-armies.json` | `data/source/custom-armies.json` |
| `data/equipment-pet-gap-evidence.json` | `data/source/equipment-pet-gap-evidence.json` |
| `data/extracted-stat-selection.json` | `data/source/extracted-stat-selection.json` |
| `data/gamecsv/v18.200.9/buildings.csv` | `data/source/gamecsv/v18.200.9/buildings.csv` |
| `data/gamecsv/v18.200.9/characters.csv` | `data/source/gamecsv/v18.200.9/characters.csv` |
| `data/gamecsv/v18.200.9/globals.csv` | `data/source/gamecsv/v18.200.9/globals.csv` |
| `data/gamecsv/v18.200.9/heroes.csv` | `data/source/gamecsv/v18.200.9/heroes.csv` |
| `data/gamecsv/v18.200.9/mini_levels.csv` | `data/source/gamecsv/v18.200.9/mini_levels.csv` |
| `data/gamecsv/v18.200.9/pets.csv` | `data/source/gamecsv/v18.200.9/pets.csv` |
| `data/gamecsv/v18.200.9/projectiles.csv` | `data/source/gamecsv/v18.200.9/projectiles.csv` |
| `data/gamecsv/v18.200.9/special_abilities.csv` | `data/source/gamecsv/v18.200.9/special_abilities.csv` |
| `data/gamecsv/v18.200.9/spells.csv` | `data/source/gamecsv/v18.200.9/spells.csv` |
| `data/gamecsv/v18.200.9/traps.csv` | `data/source/gamecsv/v18.200.9/traps.csv` |
| `data/live/base-history.json` | `data/source/live/base-history.json` |
| `data/live/battles.jsonl` | `data/source/live/battles.jsonl` |
| `data/live/player-latest.json` | `data/source/live/player-latest.json` |
| `data/manifest.json` | `data/generated/manifest.json` |
| `data/mechanics-claims.json` | `data/source/mechanics-claims.json` |
| `data/meta-armies-2026-10-15.json` | `data/source/meta-armies-2026-10-15.json` |
| `data/meta-calibration-defenses.json` | `data/source/meta-calibration-defenses.json` |
| `data/meta-calibration-defenses.report.json` | `data/source/meta-calibration-defenses.report.json` |
| `data/meta-calibration-playbooks.json` | `data/source/meta-calibration-playbooks.json` |
| `data/meta-calibration-r5.json` | `data/source/meta-calibration-r5.json` |
| `data/meta-calibration-r6.json` | `data/source/meta-calibration-r6.json` |
| `data/meta-calibration-r7.json` | `data/source/meta-calibration-r7.json` |
| `data/meta-calibration-r8.json` | `data/source/meta-calibration-r8.json` |
| `data/meta-calibration-techniques.json` | `data/source/meta-calibration-techniques.json` |
| `data/meta-calibration.json` | `data/source/meta-calibration.json` |
| `data/mode-rules.json` | `data/source/mode-rules.json` |
| `data/observed-armies.json` | `data/source/observed-armies.json` |
| `data/playbook-gaps.json` | `data/source/playbook-gaps.json` |
| `data/playbooks/dragon.json` | `data/source/playbooks/dragon.json` |
| `data/playbooks/druid-ruin-witch.json` | `data/source/playbooks/druid-ruin-witch.json` |
| `data/playbooks/electro-dragon.json` | `data/source/playbooks/electro-dragon.json` |
| `data/playbooks/fireball-warden.json` | `data/source/playbooks/fireball-warden.json` |
| `data/playbooks/lavaloon.json` | `data/source/playbooks/lavaloon.json` |
| `data/playbooks/meteor-golem.json` | `data/source/playbooks/meteor-golem.json` |
| `data/playbooks/root-rider.json` | `data/source/playbooks/root-rider.json` |
| `data/playbooks/super-bowler.json` | `data/source/playbooks/super-bowler.json` |
| `data/playbooks/super-minion-air.json` | `data/source/playbooks/super-minion-air.json` |
| `data/playbooks/test-stealth-rr.json` | `data/source/playbooks/test-stealth-rr.json` |
| `data/playbooks/thrower.json` | `data/source/playbooks/thrower.json` |
| `data/playbooks/yeti.json` | `data/source/playbooks/yeti.json` |
| `data/primary-stat-claims.json` | `data/source/primary-stat-claims.json` |
| `data/reference-bases/ranked-2026-10-24/rb01.json` | `data/source/reference-bases/ranked-2026-10-24/rb01.json` |
| `data/reference-bases/ranked-2026-10-24/rb02.json` | `data/source/reference-bases/ranked-2026-10-24/rb02.json` |
| `data/reference-bases/ranked-2026-10-24/rb03.json` | `data/source/reference-bases/ranked-2026-10-24/rb03.json` |
| `data/reference-bases/ranked-2026-10-24/rb04.json` | `data/source/reference-bases/ranked-2026-10-24/rb04.json` |
| `data/reference-bases/ranked-2026-10-24/rb05.json` | `data/source/reference-bases/ranked-2026-10-24/rb05.json` |
| `data/reference-bases/ranked-2026-10-24/rb06.json` | `data/source/reference-bases/ranked-2026-10-24/rb06.json` |
| `data/reference-bases/ranked-2026-10-24/rb07.json` | `data/source/reference-bases/ranked-2026-10-24/rb07.json` |
| `data/reference-bases/ranked-2026-10-24/rb08.json` | `data/source/reference-bases/ranked-2026-10-24/rb08.json` |
| `data/reference-bases/ranked-2026-10-24/rb09.json` | `data/source/reference-bases/ranked-2026-10-24/rb09.json` |
| `data/reference-bases/ranked-2026-10-24/rb10.json` | `data/source/reference-bases/ranked-2026-10-24/rb10.json` |
| `data/reference-bases/ranked-th18-2026-10-25/r18a.json` | `data/source/reference-bases/ranked-th18-2026-10-25/r18a.json` |
| `data/reference-bases/ranked-th18-2026-10-25/r18b.json` | `data/source/reference-bases/ranked-th18-2026-10-25/r18b.json` |
| `data/reference-bases/ranked-th18-2026-10-25/r18c.json` | `data/source/reference-bases/ranked-th18-2026-10-25/r18c.json` |
| `data/reference-bases/ranked-th18-2026-10-25/r18d.json` | `data/source/reference-bases/ranked-th18-2026-10-25/r18d.json` |
| `data/reference-bases/real-l1x.json` | `data/source/reference-bases/real-l1x.json` |
| `data/reference-bases/real-l1x.png` | `data/source/reference-bases/real-l1x.png` |
| `data/reference-bases/real-l3x.json` | `data/source/reference-bases/real-l3x.json` |
| `data/reference-bases/real-l3x.png` | `data/source/reference-bases/real-l3x.png` |
| `data/reference-bases/real-l4x.json` | `data/source/reference-bases/real-l4x.json` |
| `data/reference-bases/real-l4x.png` | `data/source/reference-bases/real-l4x.png` |
| `data/reference-bases/real-l5x.json` | `data/source/reference-bases/real-l5x.json` |
| `data/reference-bases/real-l5x.png` | `data/source/reference-bases/real-l5x.png` |
| `data/reference-bases/real-l6x.json` | `data/source/reference-bases/real-l6x.json` |
| `data/reference-bases/real-l6x.png` | `data/source/reference-bases/real-l6x.png` |
| `data/reference-bases/your-base-2026-10-21.json` | `data/source/reference-bases/your-base-2026-10-21.json` |
| `data/reference-bases/your-base.json` | `data/source/reference-bases/your-base.json` |
| `data/reference-bases/your-base.png` | `data/source/reference-bases/your-base.png` |
| `data/registry.json` | `data/generated/registry.json` |
| `data/remaining-troop-source-audit.json` | `data/source/remaining-troop-source-audit.json` |
| `data/replays/2026-10-03-afghanistan-dragons.json` | `data/source/replays/2026-10-03-afghanistan-dragons.json` |
| `data/replays/2026-10-03-paw-paw-rootriders.json` | `data/source/replays/2026-10-03-paw-paw-rootriders.json` |
| `data/replays/2026-10-21-maroon-machine.json` | `data/source/replays/2026-10-21-maroon-machine.json` |
| `data/secondary-raw.json` | `data/source/secondary-raw.json` |
| `data/siege-lifecycle-evidence.json` | `data/source/siege-lifecycle-evidence.json` |
| `data/troop-lifecycle-source-audit.json` | `data/source/troop-lifecycle-source-audit.json` |
| `data/unresolved-content.json` | `data/source/unresolved-content.json` |
| `data/video-measurements-traps.json` | `data/source/video-measurements-traps.json` |
| `data/video-measurements-troops.json` | `data/source/video-measurements-troops.json` |
| `data/warden-weights.json` | `data/source/warden-weights.json` |
| `data/your-levels.json` | `data/source/your-levels.json` |
| `rust/data/base_rules.json` | `data/generated/base_rules.json` |
| `rust/data/catalog.json` | `data/generated/catalog.json` |
| `rust/data/clan_castle.json` | `data/generated/clan_castle.json` |
| `rust/data/target17.json` | `data/generated/target17.json` |
| `rust/data/target18.json` | `data/generated/target18.json` |

## Every moved ignored file

The 1,569 ignored files comprise the existing 1,561-file wiki acquisition
cache and eight existing backups/logs. Only their paths are recorded here;
the payloads remain ignored and were not acquired or added to Git.

| Before | After |
| --- | --- |
| `data/attacker-policy-pre-deepdrop.json` | `data/source/attacker-policy-pre-deepdrop.json` |
| `data/custom-armies-pre-userarmies.json` | `data/source/custom-armies-pre-userarmies.json` |
| `data/meta-calibration-defenses-v7.json.log` | `data/source/meta-calibration-defenses-v7.json.log` |
| `data/meta-calibration-defenses-v8.json.log` | `data/source/meta-calibration-defenses-v8.json.log` |
| `data/meta-calibration-pre-deepdrop.json` | `data/source/meta-calibration-pre-deepdrop.json` |
| `data/meta-calibration-pre-healfix.json` | `data/source/meta-calibration-pre-healfix.json` |
| `data/meta-calibration-pre-techniques.json` | `data/source/meta-calibration-pre-techniques.json` |
| `data/wiki/catalog.json` | `data/source/wiki/catalog.json` |
| `data/wiki/index.json` | `data/source/wiki/index.json` |
| `data/wiki/last_edited.json` | `data/source/wiki/last_edited.json` |
| `data/wiki/pages/Action_Figure.json` | `data/source/wiki/pages/Action_Figure.json` |
| `data/wiki/pages/Air_Bomb.json` | `data/source/wiki/pages/Air_Bomb.json` |
| `data/wiki/pages/Air_Bombs.json` | `data/source/wiki/pages/Air_Bombs.json` |
| `data/wiki/pages/Air_Bombs_Home_Village.json` | `data/source/wiki/pages/Air_Bombs_Home_Village.json` |
| `data/wiki/pages/Air_Defense.json` | `data/source/wiki/pages/Air_Defense.json` |
| `data/wiki/pages/Air_Defense_Home_Village.json` | `data/source/wiki/pages/Air_Defense_Home_Village.json` |
| `data/wiki/pages/Air_Sweeper.json` | `data/source/wiki/pages/Air_Sweeper.json` |
| `data/wiki/pages/Airship.json` | `data/source/wiki/pages/Airship.json` |
| `data/wiki/pages/Alchemist.json` | `data/source/wiki/pages/Alchemist.json` |
| `data/wiki/pages/Angry_Jelly.json` | `data/source/wiki/pages/Angry_Jelly.json` |
| `data/wiki/pages/Angry_Spell.json` | `data/source/wiki/pages/Angry_Spell.json` |
| `data/wiki/pages/Anime_Clash.json` | `data/source/wiki/pages/Anime_Clash.json` |
| `data/wiki/pages/Anime_Fury_Medal_Event.json` | `data/source/wiki/pages/Anime_Fury_Medal_Event.json` |
| `data/wiki/pages/Apprentice_Warden.json` | `data/source/wiki/pages/Apprentice_Warden.json` |
| `data/wiki/pages/Archer.json` | `data/source/wiki/pages/Archer.json` |
| `data/wiki/pages/Archer_Puppet.json` | `data/source/wiki/pages/Archer_Puppet.json` |
| `data/wiki/pages/Archer_Queen.json` | `data/source/wiki/pages/Archer_Queen.json` |
| `data/wiki/pages/Archer_Queen_Altar.json` | `data/source/wiki/pages/Archer_Queen_Altar.json` |
| `data/wiki/pages/Archer_Queen_Skin_Features.json` | `data/source/wiki/pages/Archer_Queen_Skin_Features.json` |
| `data/wiki/pages/Archer_Tower.json` | `data/source/wiki/pages/Archer_Tower.json` |
| `data/wiki/pages/Archer_Tower_Home_Village.json` | `data/source/wiki/pages/Archer_Tower_Home_Village.json` |
| `data/wiki/pages/Army.json` | `data/source/wiki/pages/Army.json` |
| `data/wiki/pages/Army_Buildings_Home_Village.json` | `data/source/wiki/pages/Army_Buildings_Home_Village.json` |
| `data/wiki/pages/Army_Camp_Home_Village.json` | `data/source/wiki/pages/Army_Camp_Home_Village.json` |
| `data/wiki/pages/Attack_Challenges.json` | `data/source/wiki/pages/Attack_Challenges.json` |
| `data/wiki/pages/Attack_Challenges_Archive.json` | `data/source/wiki/pages/Attack_Challenges_Archive.json` |
| `data/wiki/pages/Attack_Challenges_Archive_2022.json` | `data/source/wiki/pages/Attack_Challenges_Archive_2022.json` |
| `data/wiki/pages/Attack_Challenges_Archive_2023.json` | `data/source/wiki/pages/Attack_Challenges_Archive_2023.json` |
| `data/wiki/pages/Attack_Challenges_Archive_Pre-2022.json` | `data/source/wiki/pages/Attack_Challenges_Archive_Pre-2022.json` |
| `data/wiki/pages/Attack_Challenges_Controllable_Heroes_Cookie_Chaos.json` | `data/source/wiki/pages/Attack_Challenges_Controllable_Heroes_Cookie_Chaos.json` |
| `data/wiki/pages/Attack_Challenges_Hero_Campaign_Dragon_Escape.json` | `data/source/wiki/pages/Attack_Challenges_Hero_Campaign_Dragon_Escape.json` |
| `data/wiki/pages/Awesome_Medal_Event.json` | `data/source/wiki/pages/Awesome_Medal_Event.json` |
| `data/wiki/pages/Azure_Dragon.json` | `data/source/wiki/pages/Azure_Dragon.json` |
| `data/wiki/pages/B.O.B_s_Hut.json` | `data/source/wiki/pages/B.O.B_s_Hut.json` |
| `data/wiki/pages/Baby_Dragon.json` | `data/source/wiki/pages/Baby_Dragon.json` |
| `data/wiki/pages/Baby_Dragon_Home_Village.json` | `data/source/wiki/pages/Baby_Dragon_Home_Village.json` |
| `data/wiki/pages/Bag_of_Frostmites.json` | `data/source/wiki/pages/Bag_of_Frostmites.json` |
| `data/wiki/pages/Balloon.json` | `data/source/wiki/pages/Balloon.json` |
| `data/wiki/pages/Barbarian.json` | `data/source/wiki/pages/Barbarian.json` |
| `data/wiki/pages/Barbarian_Home_Village.json` | `data/source/wiki/pages/Barbarian_Home_Village.json` |
| `data/wiki/pages/Barbarian_Kicker.json` | `data/source/wiki/pages/Barbarian_Kicker.json` |
| `data/wiki/pages/Barbarian_King.json` | `data/source/wiki/pages/Barbarian_King.json` |
| `data/wiki/pages/Barbarian_King_Altar.json` | `data/source/wiki/pages/Barbarian_King_Altar.json` |
| `data/wiki/pages/Barbarian_King_Skin_Features.json` | `data/source/wiki/pages/Barbarian_King_Skin_Features.json` |
| `data/wiki/pages/Barbarian_Puppet.json` | `data/source/wiki/pages/Barbarian_Puppet.json` |
| `data/wiki/pages/Barcher.json` | `data/source/wiki/pages/Barcher.json` |
| `data/wiki/pages/Barracks.json` | `data/source/wiki/pages/Barracks.json` |
| `data/wiki/pages/Bat.json` | `data/source/wiki/pages/Bat.json` |
| `data/wiki/pages/Bat_Spell.json` | `data/source/wiki/pages/Bat_Spell.json` |
| `data/wiki/pages/Bat_Spell_Bat.json` | `data/source/wiki/pages/Bat_Spell_Bat.json` |
| `data/wiki/pages/Battle.json` | `data/source/wiki/pages/Battle.json` |
| `data/wiki/pages/Battle_Blimp.json` | `data/source/wiki/pages/Battle_Blimp.json` |
| `data/wiki/pages/Battle_Copter.json` | `data/source/wiki/pages/Battle_Copter.json` |
| `data/wiki/pages/Battle_Copter_Altar.json` | `data/source/wiki/pages/Battle_Copter_Altar.json` |
| `data/wiki/pages/Battle_Drill.json` | `data/source/wiki/pages/Battle_Drill.json` |
| `data/wiki/pages/Battle_Machine.json` | `data/source/wiki/pages/Battle_Machine.json` |
| `data/wiki/pages/Battle_Machine_Altar.json` | `data/source/wiki/pages/Battle_Machine_Altar.json` |
| `data/wiki/pages/Battle_Modifiers.json` | `data/source/wiki/pages/Battle_Modifiers.json` |
| `data/wiki/pages/Battle_Ram.json` | `data/source/wiki/pages/Battle_Ram.json` |
| `data/wiki/pages/Battle_Ram_Home_Village.json` | `data/source/wiki/pages/Battle_Ram_Home_Village.json` |
| `data/wiki/pages/Beta_Minion.json` | `data/source/wiki/pages/Beta_Minion.json` |
| `data/wiki/pages/Birthday_Boom.json` | `data/source/wiki/pages/Birthday_Boom.json` |
| `data/wiki/pages/Blacksmith.json` | `data/source/wiki/pages/Blacksmith.json` |
| `data/wiki/pages/Blast_Bow.json` | `data/source/wiki/pages/Blast_Bow.json` |
| `data/wiki/pages/Boat.json` | `data/source/wiki/pages/Boat.json` |
| `data/wiki/pages/Bomb.json` | `data/source/wiki/pages/Bomb.json` |
| `data/wiki/pages/Bomb_Hive.json` | `data/source/wiki/pages/Bomb_Hive.json` |
| `data/wiki/pages/Bomb_Tower.json` | `data/source/wiki/pages/Bomb_Tower.json` |
| `data/wiki/pages/Bomb_Tower_Home_Village.json` | `data/source/wiki/pages/Bomb_Tower_Home_Village.json` |
| `data/wiki/pages/Bomber.json` | `data/source/wiki/pages/Bomber.json` |
| `data/wiki/pages/Bowler.json` | `data/source/wiki/pages/Bowler.json` |
| `data/wiki/pages/Boxer_Giant.json` | `data/source/wiki/pages/Boxer_Giant.json` |
| `data/wiki/pages/Broom_Witch.json` | `data/source/wiki/pages/Broom_Witch.json` |
| `data/wiki/pages/Broom_Witch_Witch_Spirit.json` | `data/source/wiki/pages/Broom_Witch_Witch_Spirit.json` |
| `data/wiki/pages/Builder.json` | `data/source/wiki/pages/Builder.json` |
| `data/wiki/pages/Builder_Battles.json` | `data/source/wiki/pages/Builder_Battles.json` |
| `data/wiki/pages/Builder_s_Apprentice.json` | `data/source/wiki/pages/Builder_s_Apprentice.json` |
| `data/wiki/pages/Builder_s_Hut.json` | `data/source/wiki/pages/Builder_s_Hut.json` |
| `data/wiki/pages/Builder_s_Hut_Home_Village.json` | `data/source/wiki/pages/Builder_s_Hut_Home_Village.json` |
| `data/wiki/pages/Building_Merging.json` | `data/source/wiki/pages/Building_Merging.json` |
| `data/wiki/pages/C.O.O.K.I.E.json` | `data/source/wiki/pages/C.O.O.K.I.E.json` |
| `data/wiki/pages/Cake-A-Pult.json` | `data/source/wiki/pages/Cake-A-Pult.json` |
| `data/wiki/pages/Cannon.json` | `data/source/wiki/pages/Cannon.json` |
| `data/wiki/pages/Cannon_Cart.json` | `data/source/wiki/pages/Cannon_Cart.json` |
| `data/wiki/pages/Cannon_Home_Village.json` | `data/source/wiki/pages/Cannon_Home_Village.json` |
| `data/wiki/pages/Chief_s_Journey.json` | `data/source/wiki/pages/Chief_s_Journey.json` |
| `data/wiki/pages/Clan_Badge.json` | `data/source/wiki/pages/Clan_Badge.json` |
| `data/wiki/pages/Clan_Castle.json` | `data/source/wiki/pages/Clan_Castle.json` |
| `data/wiki/pages/Clan_Castle_Home_Village.json` | `data/source/wiki/pages/Clan_Castle_Home_Village.json` |
| `data/wiki/pages/Clan_Games.json` | `data/source/wiki/pages/Clan_Games.json` |
| `data/wiki/pages/Clan_Games_Archive.json` | `data/source/wiki/pages/Clan_Games_Archive.json` |
| `data/wiki/pages/Clan_Games_Challenges.json` | `data/source/wiki/pages/Clan_Games_Challenges.json` |
| `data/wiki/pages/Clan_Perks.json` | `data/source/wiki/pages/Clan_Perks.json` |
| `data/wiki/pages/Clan_Rush.json` | `data/source/wiki/pages/Clan_Rush.json` |
| `data/wiki/pages/Clan_War_Leagues.json` | `data/source/wiki/pages/Clan_War_Leagues.json` |
| `data/wiki/pages/Clan_Wars.json` | `data/source/wiki/pages/Clan_Wars.json` |
| `data/wiki/pages/Clans.json` | `data/source/wiki/pages/Clans.json` |
| `data/wiki/pages/Clash_of_Cards.json` | `data/source/wiki/pages/Clash_of_Cards.json` |
| `data/wiki/pages/Clash_of_Clans_Skin_Sets.json` | `data/source/wiki/pages/Clash_of_Clans_Skin_Sets.json` |
| `data/wiki/pages/Clash_with_Haaland.json` | `data/source/wiki/pages/Clash_with_Haaland.json` |
| `data/wiki/pages/Clone_Spell.json` | `data/source/wiki/pages/Clone_Spell.json` |
| `data/wiki/pages/Cookie_Rumble.json` | `data/source/wiki/pages/Cookie_Rumble.json` |
| `data/wiki/pages/Cosmic_Rock.json` | `data/source/wiki/pages/Cosmic_Rock.json` |
| `data/wiki/pages/Crafting_Station.json` | `data/source/wiki/pages/Crafting_Station.json` |
| `data/wiki/pages/Crusher.json` | `data/source/wiki/pages/Crusher.json` |
| `data/wiki/pages/Crusher_Mortar.json` | `data/source/wiki/pages/Crusher_Mortar.json` |
| `data/wiki/pages/Cumulative_Costs.json` | `data/source/wiki/pages/Cumulative_Costs.json` |
| `data/wiki/pages/Cumulative_Costs_Home_Village.json` | `data/source/wiki/pages/Cumulative_Costs_Home_Village.json` |
| `data/wiki/pages/Dark_Barracks.json` | `data/source/wiki/pages/Dark_Barracks.json` |
| `data/wiki/pages/Dark_Crown.json` | `data/source/wiki/pages/Dark_Crown.json` |
| `data/wiki/pages/Dark_Deal.json` | `data/source/wiki/pages/Dark_Deal.json` |
| `data/wiki/pages/Dark_Elixir_Drill.json` | `data/source/wiki/pages/Dark_Elixir_Drill.json` |
| `data/wiki/pages/Dark_Elixir_Storage.json` | `data/source/wiki/pages/Dark_Elixir_Storage.json` |
| `data/wiki/pages/Dark_Elixir_Troops.json` | `data/source/wiki/pages/Dark_Elixir_Troops.json` |
| `data/wiki/pages/Dark_Orb.json` | `data/source/wiki/pages/Dark_Orb.json` |
| `data/wiki/pages/Dark_Spell_Factory.json` | `data/source/wiki/pages/Dark_Spell_Factory.json` |
| `data/wiki/pages/Dark_Spells.json` | `data/source/wiki/pages/Dark_Spells.json` |
| `data/wiki/pages/Debt_Collector.json` | `data/source/wiki/pages/Debt_Collector.json` |
| `data/wiki/pages/Defensive_Buildings_Home_Village.json` | `data/source/wiki/pages/Defensive_Buildings_Home_Village.json` |
| `data/wiki/pages/Destruction.json` | `data/source/wiki/pages/Destruction.json` |
| `data/wiki/pages/Diggy.json` | `data/source/wiki/pages/Diggy.json` |
| `data/wiki/pages/Double_Cannon.json` | `data/source/wiki/pages/Double_Cannon.json` |
| `data/wiki/pages/Dragon.json` | `data/source/wiki/pages/Dragon.json` |
| `data/wiki/pages/Dragon_Dash.json` | `data/source/wiki/pages/Dragon_Dash.json` |
| `data/wiki/pages/Dragon_Duke.json` | `data/source/wiki/pages/Dragon_Duke.json` |
| `data/wiki/pages/Dragon_Festival.json` | `data/source/wiki/pages/Dragon_Festival.json` |
| `data/wiki/pages/Dragon_Pinata.json` | `data/source/wiki/pages/Dragon_Pinata.json` |
| `data/wiki/pages/Dragon_Rider.json` | `data/source/wiki/pages/Dragon_Rider.json` |
| `data/wiki/pages/Drop_Ship.json` | `data/source/wiki/pages/Drop_Ship.json` |
| `data/wiki/pages/Drop_Ship_Skeleton.json` | `data/source/wiki/pages/Drop_Ship_Skeleton.json` |
| `data/wiki/pages/Druid.json` | `data/source/wiki/pages/Druid.json` |
| `data/wiki/pages/Druid_Bear.json` | `data/source/wiki/pages/Druid_Bear.json` |
| `data/wiki/pages/Eagle_Artillery.json` | `data/source/wiki/pages/Eagle_Artillery.json` |
| `data/wiki/pages/Earthquake_Boots.json` | `data/source/wiki/pages/Earthquake_Boots.json` |
| `data/wiki/pages/Earthquake_Spell.json` | `data/source/wiki/pages/Earthquake_Spell.json` |
| `data/wiki/pages/El_Primo.json` | `data/source/wiki/pages/El_Primo.json` |
| `data/wiki/pages/Electro_Boots.json` | `data/source/wiki/pages/Electro_Boots.json` |
| `data/wiki/pages/Electro_Dragon.json` | `data/source/wiki/pages/Electro_Dragon.json` |
| `data/wiki/pages/Electro_Fangs.json` | `data/source/wiki/pages/Electro_Fangs.json` |
| `data/wiki/pages/Electro_Owl.json` | `data/source/wiki/pages/Electro_Owl.json` |
| `data/wiki/pages/Electro_Titan.json` | `data/source/wiki/pages/Electro_Titan.json` |
| `data/wiki/pages/Electrofire_Wizard.json` | `data/source/wiki/pages/Electrofire_Wizard.json` |
| `data/wiki/pages/Elephant_Rider.json` | `data/source/wiki/pages/Elephant_Rider.json` |
| `data/wiki/pages/Elephant_Rider_Elephant.json` | `data/source/wiki/pages/Elephant_Rider_Elephant.json` |
| `data/wiki/pages/Elephant_Rider_Rider.json` | `data/source/wiki/pages/Elephant_Rider_Rider.json` |
| `data/wiki/pages/Elixir_Collector_Home_Village.json` | `data/source/wiki/pages/Elixir_Collector_Home_Village.json` |
| `data/wiki/pages/Elixir_Spells.json` | `data/source/wiki/pages/Elixir_Spells.json` |
| `data/wiki/pages/Elixir_Storage.json` | `data/source/wiki/pages/Elixir_Storage.json` |
| `data/wiki/pages/Elixir_Storage_Home_Village.json` | `data/source/wiki/pages/Elixir_Storage_Home_Village.json` |
| `data/wiki/pages/Elixir_Troops.json` | `data/source/wiki/pages/Elixir_Troops.json` |
| `data/wiki/pages/Endless_Haste_Spell.json` | `data/source/wiki/pages/Endless_Haste_Spell.json` |
| `data/wiki/pages/Equipment_Blast.json` | `data/source/wiki/pages/Equipment_Blast.json` |
| `data/wiki/pages/Eternal_Tome.json` | `data/source/wiki/pages/Eternal_Tome.json` |
| `data/wiki/pages/Events.json` | `data/source/wiki/pages/Events.json` |
| `data/wiki/pages/Experience.json` | `data/source/wiki/pages/Experience.json` |
| `data/wiki/pages/Fancy_Shop.json` | `data/source/wiki/pages/Fancy_Shop.json` |
| `data/wiki/pages/Fire_Heart.json` | `data/source/wiki/pages/Fire_Heart.json` |
| `data/wiki/pages/Fireball.json` | `data/source/wiki/pages/Fireball.json` |
| `data/wiki/pages/Firecracker.json` | `data/source/wiki/pages/Firecracker.json` |
| `data/wiki/pages/Firecrackers.json` | `data/source/wiki/pages/Firecrackers.json` |
| `data/wiki/pages/Firespitter.json` | `data/source/wiki/pages/Firespitter.json` |
| `data/wiki/pages/Flame_Blower.json` | `data/source/wiki/pages/Flame_Blower.json` |
| `data/wiki/pages/Flame_Flinger.json` | `data/source/wiki/pages/Flame_Flinger.json` |
| `data/wiki/pages/Flame_Spinner.json` | `data/source/wiki/pages/Flame_Spinner.json` |
| `data/wiki/pages/Flying_Fortress.json` | `data/source/wiki/pages/Flying_Fortress.json` |
| `data/wiki/pages/Flying_Fortress_Skeleton_Glider.json` | `data/source/wiki/pages/Flying_Fortress_Skeleton_Glider.json` |
| `data/wiki/pages/Football_Camp.json` | `data/source/wiki/pages/Football_Camp.json` |
| `data/wiki/pages/Forge.json` | `data/source/wiki/pages/Forge.json` |
| `data/wiki/pages/Freeze_Spell.json` | `data/source/wiki/pages/Freeze_Spell.json` |
| `data/wiki/pages/Freeze_Trap.json` | `data/source/wiki/pages/Freeze_Trap.json` |
| `data/wiki/pages/Friend_or_Foe.json` | `data/source/wiki/pages/Friend_or_Foe.json` |
| `data/wiki/pages/Frost_Flake.json` | `data/source/wiki/pages/Frost_Flake.json` |
| `data/wiki/pages/Frost_Spell.json` | `data/source/wiki/pages/Frost_Spell.json` |
| `data/wiki/pages/Frosty.json` | `data/source/wiki/pages/Frosty.json` |
| `data/wiki/pages/Frosty_Frostmite.json` | `data/source/wiki/pages/Frosty_Frostmite.json` |
| `data/wiki/pages/Frozen_Arrow.json` | `data/source/wiki/pages/Frozen_Arrow.json` |
| `data/wiki/pages/Furnace.json` | `data/source/wiki/pages/Furnace.json` |
| `data/wiki/pages/Furnace_Firemite.json` | `data/source/wiki/pages/Furnace_Firemite.json` |
| `data/wiki/pages/Game_Tips.json` | `data/source/wiki/pages/Game_Tips.json` |
| `data/wiki/pages/Gems.json` | `data/source/wiki/pages/Gems.json` |
| `data/wiki/pages/Giant.json` | `data/source/wiki/pages/Giant.json` |
| `data/wiki/pages/Giant_Arrow.json` | `data/source/wiki/pages/Giant_Arrow.json` |
| `data/wiki/pages/Giant_Bomb.json` | `data/source/wiki/pages/Giant_Bomb.json` |
| `data/wiki/pages/Giant_Cannon.json` | `data/source/wiki/pages/Giant_Cannon.json` |
| `data/wiki/pages/Giant_Gauntlet.json` | `data/source/wiki/pages/Giant_Gauntlet.json` |
| `data/wiki/pages/Giant_Giant.json` | `data/source/wiki/pages/Giant_Giant.json` |
| `data/wiki/pages/Giant_Skeleton.json` | `data/source/wiki/pages/Giant_Skeleton.json` |
| `data/wiki/pages/Giant_Thrower.json` | `data/source/wiki/pages/Giant_Thrower.json` |
| `data/wiki/pages/Giga_Bomb.json` | `data/source/wiki/pages/Giga_Bomb.json` |
| `data/wiki/pages/Gingerbread_Bakery.json` | `data/source/wiki/pages/Gingerbread_Bakery.json` |
| `data/wiki/pages/Glossary.json` | `data/source/wiki/pages/Glossary.json` |
| `data/wiki/pages/Goblin.json` | `data/source/wiki/pages/Goblin.json` |
| `data/wiki/pages/Goblin_Thrower.json` | `data/source/wiki/pages/Goblin_Thrower.json` |
| `data/wiki/pages/Goblin_Workers.json` | `data/source/wiki/pages/Goblin_Workers.json` |
| `data/wiki/pages/Gold_Mine_Home_Village.json` | `data/source/wiki/pages/Gold_Mine_Home_Village.json` |
| `data/wiki/pages/Gold_Rush.json` | `data/source/wiki/pages/Gold_Rush.json` |
| `data/wiki/pages/Gold_Storage.json` | `data/source/wiki/pages/Gold_Storage.json` |
| `data/wiki/pages/Gold_Storage_Home_Village.json` | `data/source/wiki/pages/Gold_Storage_Home_Village.json` |
| `data/wiki/pages/Golden_Dragon.json` | `data/source/wiki/pages/Golden_Dragon.json` |
| `data/wiki/pages/Golem.json` | `data/source/wiki/pages/Golem.json` |
| `data/wiki/pages/Golem_Golemite.json` | `data/source/wiki/pages/Golem_Golemite.json` |
| `data/wiki/pages/Grand_Warden.json` | `data/source/wiki/pages/Grand_Warden.json` |
| `data/wiki/pages/Grand_Warden_Altar.json` | `data/source/wiki/pages/Grand_Warden_Altar.json` |
| `data/wiki/pages/Grand_Warden_Skin_Features.json` | `data/source/wiki/pages/Grand_Warden_Skin_Features.json` |
| `data/wiki/pages/Graveyard_Spell.json` | `data/source/wiki/pages/Graveyard_Spell.json` |
| `data/wiki/pages/Greedy_Raven.json` | `data/source/wiki/pages/Greedy_Raven.json` |
| `data/wiki/pages/Guard.json` | `data/source/wiki/pages/Guard.json` |
| `data/wiki/pages/Guard_Post.json` | `data/source/wiki/pages/Guard_Post.json` |
| `data/wiki/pages/Hall_of_Fame.json` | `data/source/wiki/pages/Hall_of_Fame.json` |
| `data/wiki/pages/Haste_Spell.json` | `data/source/wiki/pages/Haste_Spell.json` |
| `data/wiki/pages/Haste_Vial.json` | `data/source/wiki/pages/Haste_Vial.json` |
| `data/wiki/pages/Headhunter.json` | `data/source/wiki/pages/Headhunter.json` |
| `data/wiki/pages/Healer.json` | `data/source/wiki/pages/Healer.json` |
| `data/wiki/pages/Healer_Puppet.json` | `data/source/wiki/pages/Healer_Puppet.json` |
| `data/wiki/pages/Healing_Spell.json` | `data/source/wiki/pages/Healing_Spell.json` |
| `data/wiki/pages/Healing_Spell_Home_Village.json` | `data/source/wiki/pages/Healing_Spell_Home_Village.json` |
| `data/wiki/pages/Healing_Tome.json` | `data/source/wiki/pages/Healing_Tome.json` |
| `data/wiki/pages/Helper_Hut.json` | `data/source/wiki/pages/Helper_Hut.json` |
| `data/wiki/pages/Henchmen_Puppet.json` | `data/source/wiki/pages/Henchmen_Puppet.json` |
| `data/wiki/pages/Henchmen_Puppet_Henchmen.json` | `data/source/wiki/pages/Henchmen_Puppet_Henchmen.json` |
| `data/wiki/pages/Hero_Banner.json` | `data/source/wiki/pages/Hero_Banner.json` |
| `data/wiki/pages/Hero_Bell.json` | `data/source/wiki/pages/Hero_Bell.json` |
| `data/wiki/pages/Hero_Equipment.json` | `data/source/wiki/pages/Hero_Equipment.json` |
| `data/wiki/pages/Hero_Hall.json` | `data/source/wiki/pages/Hero_Hall.json` |
| `data/wiki/pages/Hero_Hunter.json` | `data/source/wiki/pages/Hero_Hunter.json` |
| `data/wiki/pages/Hero_Rush.json` | `data/source/wiki/pages/Hero_Rush.json` |
| `data/wiki/pages/Hero_s_Journey.json` | `data/source/wiki/pages/Hero_s_Journey.json` |
| `data/wiki/pages/Heroes.json` | `data/source/wiki/pages/Heroes.json` |
| `data/wiki/pages/Heroic_Torch.json` | `data/source/wiki/pages/Heroic_Torch.json` |
| `data/wiki/pages/Hidden_Mega_Tesla.json` | `data/source/wiki/pages/Hidden_Mega_Tesla.json` |
| `data/wiki/pages/Hidden_Tesla_Home_Village.json` | `data/source/wiki/pages/Hidden_Tesla_Home_Village.json` |
| `data/wiki/pages/Hog_Glider.json` | `data/source/wiki/pages/Hog_Glider.json` |
| `data/wiki/pages/Hog_Raiders.json` | `data/source/wiki/pages/Hog_Raiders.json` |
| `data/wiki/pages/Hog_Rider.json` | `data/source/wiki/pages/Hog_Rider.json` |
| `data/wiki/pages/Hog_Rider_Puppet.json` | `data/source/wiki/pages/Hog_Rider_Puppet.json` |
| `data/wiki/pages/Hog_Wizard.json` | `data/source/wiki/pages/Hog_Wizard.json` |
| `data/wiki/pages/Hook_Tower.json` | `data/source/wiki/pages/Hook_Tower.json` |
| `data/wiki/pages/Hot_Candle.json` | `data/source/wiki/pages/Hot_Candle.json` |
| `data/wiki/pages/Hydra_Headstone.json` | `data/source/wiki/pages/Hydra_Headstone.json` |
| `data/wiki/pages/Ice_Block_Spell.json` | `data/source/wiki/pages/Ice_Block_Spell.json` |
| `data/wiki/pages/Ice_Golem.json` | `data/source/wiki/pages/Ice_Golem.json` |
| `data/wiki/pages/Ice_Hound.json` | `data/source/wiki/pages/Ice_Hound.json` |
| `data/wiki/pages/Ice_Hound_Ice_Pup.json` | `data/source/wiki/pages/Ice_Hound_Ice_Pup.json` |
| `data/wiki/pages/Ice_Minion.json` | `data/source/wiki/pages/Ice_Minion.json` |
| `data/wiki/pages/Ice_Wizard.json` | `data/source/wiki/pages/Ice_Wizard.json` |
| `data/wiki/pages/In-App_Purchases.json` | `data/source/wiki/pages/In-App_Purchases.json` |
| `data/wiki/pages/Individual_Costs.json` | `data/source/wiki/pages/Individual_Costs.json` |
| `data/wiki/pages/Individual_Costs_Home_Village.json` | `data/source/wiki/pages/Individual_Costs_Home_Village.json` |
| `data/wiki/pages/Inferno_Dragon.json` | `data/source/wiki/pages/Inferno_Dragon.json` |
| `data/wiki/pages/Inferno_Dragon_Home_Village.json` | `data/source/wiki/pages/Inferno_Dragon_Home_Village.json` |
| `data/wiki/pages/Inferno_Tower.json` | `data/source/wiki/pages/Inferno_Tower.json` |
| `data/wiki/pages/Inferno_Tower_Home_Village.json` | `data/source/wiki/pages/Inferno_Tower_Home_Village.json` |
| `data/wiki/pages/Invisibility_Spell.json` | `data/source/wiki/pages/Invisibility_Spell.json` |
| `data/wiki/pages/Invisibility_Vial.json` | `data/source/wiki/pages/Invisibility_Vial.json` |
| `data/wiki/pages/Jump_Spell.json` | `data/source/wiki/pages/Jump_Spell.json` |
| `data/wiki/pages/Jump_Spell_Home_Village.json` | `data/source/wiki/pages/Jump_Spell_Home_Village.json` |
| `data/wiki/pages/K.A.N.E.json` | `data/source/wiki/pages/K.A.N.E.json` |
| `data/wiki/pages/L.A.S.S.I.json` | `data/source/wiki/pages/L.A.S.S.I.json` |
| `data/wiki/pages/Lab_Assistant.json` | `data/source/wiki/pages/Lab_Assistant.json` |
| `data/wiki/pages/Laboratory.json` | `data/source/wiki/pages/Laboratory.json` |
| `data/wiki/pages/Lava_Hound.json` | `data/source/wiki/pages/Lava_Hound.json` |
| `data/wiki/pages/Lava_Hound_Lava_Pup.json` | `data/source/wiki/pages/Lava_Hound_Lava_Pup.json` |
| `data/wiki/pages/Lava_Launcher.json` | `data/source/wiki/pages/Lava_Launcher.json` |
| `data/wiki/pages/Lava_Launcher_Home_Village.json` | `data/source/wiki/pages/Lava_Launcher_Home_Village.json` |
| `data/wiki/pages/Lavaloon.json` | `data/source/wiki/pages/Lavaloon.json` |
| `data/wiki/pages/Lavaloon_Lavaloon_Pup.json` | `data/source/wiki/pages/Lavaloon_Lavaloon_Pup.json` |
| `data/wiki/pages/Lavaloon_Puppet.json` | `data/source/wiki/pages/Lavaloon_Puppet.json` |
| `data/wiki/pages/Lavaloon_Puppet_Lavaloon.json` | `data/source/wiki/pages/Lavaloon_Puppet_Lavaloon.json` |
| `data/wiki/pages/Layouts_Home_Village.json` | `data/source/wiki/pages/Layouts_Home_Village.json` |
| `data/wiki/pages/Life_Gem.json` | `data/source/wiki/pages/Life_Gem.json` |
| `data/wiki/pages/Light_Beam.json` | `data/source/wiki/pages/Light_Beam.json` |
| `data/wiki/pages/Lightning_Spell.json` | `data/source/wiki/pages/Lightning_Spell.json` |
| `data/wiki/pages/Lightning_Spell_Home_Village.json` | `data/source/wiki/pages/Lightning_Spell_Home_Village.json` |
| `data/wiki/pages/Loading_Screen_Hints.json` | `data/source/wiki/pages/Loading_Screen_Hints.json` |
| `data/wiki/pages/Loading_Screens.json` | `data/source/wiki/pages/Loading_Screens.json` |
| `data/wiki/pages/Log_Launcher.json` | `data/source/wiki/pages/Log_Launcher.json` |
| `data/wiki/pages/Log_Trap.json` | `data/source/wiki/pages/Log_Trap.json` |
| `data/wiki/pages/Logger.json` | `data/source/wiki/pages/Logger.json` |
| `data/wiki/pages/Longshot.json` | `data/source/wiki/pages/Longshot.json` |
| `data/wiki/pages/Loot_Cart.json` | `data/source/wiki/pages/Loot_Cart.json` |
| `data/wiki/pages/M.E.C.H.A.json` | `data/source/wiki/pages/M.E.C.H.A.json` |
| `data/wiki/pages/Magic_Items.json` | `data/source/wiki/pages/Magic_Items.json` |
| `data/wiki/pages/Magic_Items_List.json` | `data/source/wiki/pages/Magic_Items_List.json` |
| `data/wiki/pages/Magic_Mirror.json` | `data/source/wiki/pages/Magic_Mirror.json` |
| `data/wiki/pages/Magic_Snacks.json` | `data/source/wiki/pages/Magic_Snacks.json` |
| `data/wiki/pages/Mashup_Madness.json` | `data/source/wiki/pages/Mashup_Madness.json` |
| `data/wiki/pages/Mashup_Mania.json` | `data/source/wiki/pages/Mashup_Mania.json` |
| `data/wiki/pages/Master_Builder_s_Boat.json` | `data/source/wiki/pages/Master_Builder_s_Boat.json` |
| `data/wiki/pages/Master_Builder_s_Hut.json` | `data/source/wiki/pages/Master_Builder_s_Hut.json` |
| `data/wiki/pages/Mega_Mine.json` | `data/source/wiki/pages/Mega_Mine.json` |
| `data/wiki/pages/Mega_Sparky.json` | `data/source/wiki/pages/Mega_Sparky.json` |
| `data/wiki/pages/Mega_Tesla.json` | `data/source/wiki/pages/Mega_Tesla.json` |
| `data/wiki/pages/Meltdown_Mayhem.json` | `data/source/wiki/pages/Meltdown_Mayhem.json` |
| `data/wiki/pages/Metal_Pants.json` | `data/source/wiki/pages/Metal_Pants.json` |
| `data/wiki/pages/Meteor_Golem.json` | `data/source/wiki/pages/Meteor_Golem.json` |
| `data/wiki/pages/Meteor_Golem_Meteormite.json` | `data/source/wiki/pages/Meteor_Golem_Meteormite.json` |
| `data/wiki/pages/Meteor_Staff.json` | `data/source/wiki/pages/Meteor_Staff.json` |
| `data/wiki/pages/Mighty_Yak.json` | `data/source/wiki/pages/Mighty_Yak.json` |
| `data/wiki/pages/Mine.json` | `data/source/wiki/pages/Mine.json` |
| `data/wiki/pages/Miner.json` | `data/source/wiki/pages/Miner.json` |
| `data/wiki/pages/Mini-Minion_Hive.json` | `data/source/wiki/pages/Mini-Minion_Hive.json` |
| `data/wiki/pages/Minion.json` | `data/source/wiki/pages/Minion.json` |
| `data/wiki/pages/Minion_Horde.json` | `data/source/wiki/pages/Minion_Horde.json` |
| `data/wiki/pages/Minion_Prince.json` | `data/source/wiki/pages/Minion_Prince.json` |
| `data/wiki/pages/Money_in_the_Bank_Rush.json` | `data/source/wiki/pages/Money_in_the_Bank_Rush.json` |
| `data/wiki/pages/Monolith.json` | `data/source/wiki/pages/Monolith.json` |
| `data/wiki/pages/Monolith_Arrow.json` | `data/source/wiki/pages/Monolith_Arrow.json` |
| `data/wiki/pages/Mortar.json` | `data/source/wiki/pages/Mortar.json` |
| `data/wiki/pages/Mountain_Golem.json` | `data/source/wiki/pages/Mountain_Golem.json` |
| `data/wiki/pages/Multi-Archer_Tower.json` | `data/source/wiki/pages/Multi-Archer_Tower.json` |
| `data/wiki/pages/Multi-Gear_Tower.json` | `data/source/wiki/pages/Multi-Gear_Tower.json` |
| `data/wiki/pages/Multi_Cannon.json` | `data/source/wiki/pages/Multi_Cannon.json` |
| `data/wiki/pages/Multi_Mortar.json` | `data/source/wiki/pages/Multi_Mortar.json` |
| `data/wiki/pages/Multiplayer_Battles.json` | `data/source/wiki/pages/Multiplayer_Battles.json` |
| `data/wiki/pages/Night_Witch.json` | `data/source/wiki/pages/Night_Witch.json` |
| `data/wiki/pages/Night_Witch_Bat.json` | `data/source/wiki/pages/Night_Witch_Bat.json` |
| `data/wiki/pages/Noble_Iron.json` | `data/source/wiki/pages/Noble_Iron.json` |
| `data/wiki/pages/O.T.T.O_s_Outpost.json` | `data/source/wiki/pages/O.T.T.O_s_Outpost.json` |
| `data/wiki/pages/Ores.json` | `data/source/wiki/pages/Ores.json` |
| `data/wiki/pages/Other_Buildings_Home_Village.json` | `data/source/wiki/pages/Other_Buildings_Home_Village.json` |
| `data/wiki/pages/Overgrowth_Spell.json` | `data/source/wiki/pages/Overgrowth_Spell.json` |
| `data/wiki/pages/P.E.K.K.A.json` | `data/source/wiki/pages/P.E.K.K.A.json` |
| `data/wiki/pages/Party_Wizard.json` | `data/source/wiki/pages/Party_Wizard.json` |
| `data/wiki/pages/Pathfinding.json` | `data/source/wiki/pages/Pathfinding.json` |
| `data/wiki/pages/Pet_House.json` | `data/source/wiki/pages/Pet_House.json` |
| `data/wiki/pages/Pets.json` | `data/source/wiki/pages/Pets.json` |
| `data/wiki/pages/Phoenix.json` | `data/source/wiki/pages/Phoenix.json` |
| `data/wiki/pages/Player_Profile.json` | `data/source/wiki/pages/Player_Profile.json` |
| `data/wiki/pages/Poison_Lizard.json` | `data/source/wiki/pages/Poison_Lizard.json` |
| `data/wiki/pages/Poison_Spell.json` | `data/source/wiki/pages/Poison_Spell.json` |
| `data/wiki/pages/Portal_Panic.json` | `data/source/wiki/pages/Portal_Panic.json` |
| `data/wiki/pages/Portal_Pendant.json` | `data/source/wiki/pages/Portal_Pendant.json` |
| `data/wiki/pages/Power_P.E.K.K.A.json` | `data/source/wiki/pages/Power_P.E.K.K.A.json` |
| `data/wiki/pages/Practice_Mode.json` | `data/source/wiki/pages/Practice_Mode.json` |
| `data/wiki/pages/Prospector.json` | `data/source/wiki/pages/Prospector.json` |
| `data/wiki/pages/Pumpkin_Barbarian.json` | `data/source/wiki/pages/Pumpkin_Barbarian.json` |
| `data/wiki/pages/Pumpkin_Bomb.json` | `data/source/wiki/pages/Pumpkin_Bomb.json` |
| `data/wiki/pages/Push_Trap.json` | `data/source/wiki/pages/Push_Trap.json` |
| `data/wiki/pages/Rage_Gem.json` | `data/source/wiki/pages/Rage_Gem.json` |
| `data/wiki/pages/Rage_Spell.json` | `data/source/wiki/pages/Rage_Spell.json` |
| `data/wiki/pages/Rage_Spell_Home_Village.json` | `data/source/wiki/pages/Rage_Spell_Home_Village.json` |
| `data/wiki/pages/Rage_Vial.json` | `data/source/wiki/pages/Rage_Vial.json` |
| `data/wiki/pages/Raged_Barbarian.json` | `data/source/wiki/pages/Raged_Barbarian.json` |
| `data/wiki/pages/Raid_Cart.json` | `data/source/wiki/pages/Raid_Cart.json` |
| `data/wiki/pages/Raid_Cart_Post.json` | `data/source/wiki/pages/Raid_Cart_Post.json` |
| `data/wiki/pages/Raid_Weekends.json` | `data/source/wiki/pages/Raid_Weekends.json` |
| `data/wiki/pages/Ram_Rider.json` | `data/source/wiki/pages/Ram_Rider.json` |
| `data/wiki/pages/Ranked_Battles.json` | `data/source/wiki/pages/Ranked_Battles.json` |
| `data/wiki/pages/Rapid_Rockets.json` | `data/source/wiki/pages/Rapid_Rockets.json` |
| `data/wiki/pages/Recall_Spell.json` | `data/source/wiki/pages/Recall_Spell.json` |
| `data/wiki/pages/Reflector.json` | `data/source/wiki/pages/Reflector.json` |
| `data/wiki/pages/Removed_features.json` | `data/source/wiki/pages/Removed_features.json` |
| `data/wiki/pages/Resource_Buildings_Home_Village.json` | `data/source/wiki/pages/Resource_Buildings_Home_Village.json` |
| `data/wiki/pages/Revenge_Deck.json` | `data/source/wiki/pages/Revenge_Deck.json` |
| `data/wiki/pages/Revenge_Tower.json` | `data/source/wiki/pages/Revenge_Tower.json` |
| `data/wiki/pages/Revive_Spell.json` | `data/source/wiki/pages/Revive_Spell.json` |
| `data/wiki/pages/Ricochet_Cannon.json` | `data/source/wiki/pages/Ricochet_Cannon.json` |
| `data/wiki/pages/Roaster.json` | `data/source/wiki/pages/Roaster.json` |
| `data/wiki/pages/Roaster_Home_Village.json` | `data/source/wiki/pages/Roaster_Home_Village.json` |
| `data/wiki/pages/Rocket_Artillery.json` | `data/source/wiki/pages/Rocket_Artillery.json` |
| `data/wiki/pages/Rocket_Backpack.json` | `data/source/wiki/pages/Rocket_Backpack.json` |
| `data/wiki/pages/Rocket_Balloon.json` | `data/source/wiki/pages/Rocket_Balloon.json` |
| `data/wiki/pages/Rocket_Balloon_Home_Village.json` | `data/source/wiki/pages/Rocket_Balloon_Home_Village.json` |
| `data/wiki/pages/Rocket_Spear.json` | `data/source/wiki/pages/Rocket_Spear.json` |
| `data/wiki/pages/Rocking_Reindeer.json` | `data/source/wiki/pages/Rocking_Reindeer.json` |
| `data/wiki/pages/Root_Rider.json` | `data/source/wiki/pages/Root_Rider.json` |
| `data/wiki/pages/Royal_Champion.json` | `data/source/wiki/pages/Royal_Champion.json` |
| `data/wiki/pages/Royal_Champion_Altar.json` | `data/source/wiki/pages/Royal_Champion_Altar.json` |
| `data/wiki/pages/Royal_Champion_Skin_Features.json` | `data/source/wiki/pages/Royal_Champion_Skin_Features.json` |
| `data/wiki/pages/Royal_Gem.json` | `data/source/wiki/pages/Royal_Gem.json` |
| `data/wiki/pages/Royal_Ghost.json` | `data/source/wiki/pages/Royal_Ghost.json` |
| `data/wiki/pages/Ruin_Witch.json` | `data/source/wiki/pages/Ruin_Witch.json` |
| `data/wiki/pages/Ruin_Witch_Ruin_Knight.json` | `data/source/wiki/pages/Ruin_Witch_Ruin_Knight.json` |
| `data/wiki/pages/Rumbling_Goblins.json` | `data/source/wiki/pages/Rumbling_Goblins.json` |
| `data/wiki/pages/Santa_Strike.json` | `data/source/wiki/pages/Santa_Strike.json` |
| `data/wiki/pages/Santa_s_Surprise.json` | `data/source/wiki/pages/Santa_s_Surprise.json` |
| `data/wiki/pages/Scattershot.json` | `data/source/wiki/pages/Scattershot.json` |
| `data/wiki/pages/Season_Challenges.json` | `data/source/wiki/pages/Season_Challenges.json` |
| `data/wiki/pages/Season_Challenges_Archive.json` | `data/source/wiki/pages/Season_Challenges_Archive.json` |
| `data/wiki/pages/Season_Challenges_Archive_2019.json` | `data/source/wiki/pages/Season_Challenges_Archive_2019.json` |
| `data/wiki/pages/Season_Challenges_Archive_2020.json` | `data/source/wiki/pages/Season_Challenges_Archive_2020.json` |
| `data/wiki/pages/Season_Challenges_Archive_2021.json` | `data/source/wiki/pages/Season_Challenges_Archive_2021.json` |
| `data/wiki/pages/Season_Challenges_Archive_2022.json` | `data/source/wiki/pages/Season_Challenges_Archive_2022.json` |
| `data/wiki/pages/Season_Challenges_Archive_2023.json` | `data/source/wiki/pages/Season_Challenges_Archive_2023.json` |
| `data/wiki/pages/Season_Challenges_List.json` | `data/source/wiki/pages/Season_Challenges_List.json` |
| `data/wiki/pages/Seeking_Air_Mine.json` | `data/source/wiki/pages/Seeking_Air_Mine.json` |
| `data/wiki/pages/Seeking_Shield.json` | `data/source/wiki/pages/Seeking_Shield.json` |
| `data/wiki/pages/Shield.json` | `data/source/wiki/pages/Shield.json` |
| `data/wiki/pages/Shrink_Trap.json` | `data/source/wiki/pages/Shrink_Trap.json` |
| `data/wiki/pages/Siege_Barracks.json` | `data/source/wiki/pages/Siege_Barracks.json` |
| `data/wiki/pages/Siege_Machines.json` | `data/source/wiki/pages/Siege_Machines.json` |
| `data/wiki/pages/Single_Player_Campaign.json` | `data/source/wiki/pages/Single_Player_Campaign.json` |
| `data/wiki/pages/Skeleton.json` | `data/source/wiki/pages/Skeleton.json` |
| `data/wiki/pages/Skeleton_Barrel.json` | `data/source/wiki/pages/Skeleton_Barrel.json` |
| `data/wiki/pages/Skeleton_Barrel_Home_Village.json` | `data/source/wiki/pages/Skeleton_Barrel_Home_Village.json` |
| `data/wiki/pages/Skeleton_Spell.json` | `data/source/wiki/pages/Skeleton_Spell.json` |
| `data/wiki/pages/Skeleton_Spell_Skeleton.json` | `data/source/wiki/pages/Skeleton_Spell_Skeleton.json` |
| `data/wiki/pages/Skeleton_Trap.json` | `data/source/wiki/pages/Skeleton_Trap.json` |
| `data/wiki/pages/Sky_Wagon.json` | `data/source/wiki/pages/Sky_Wagon.json` |
| `data/wiki/pages/Smasher.json` | `data/source/wiki/pages/Smasher.json` |
| `data/wiki/pages/Snake.json` | `data/source/wiki/pages/Snake.json` |
| `data/wiki/pages/Snake_Barrel.json` | `data/source/wiki/pages/Snake_Barrel.json` |
| `data/wiki/pages/Snake_Barrel_Snake.json` | `data/source/wiki/pages/Snake_Barrel_Snake.json` |
| `data/wiki/pages/Snake_Bracelet.json` | `data/source/wiki/pages/Snake_Bracelet.json` |
| `data/wiki/pages/Snake_Bracelet_Snake.json` | `data/source/wiki/pages/Snake_Bracelet_Snake.json` |
| `data/wiki/pages/Snake_Festival.json` | `data/source/wiki/pages/Snake_Festival.json` |
| `data/wiki/pages/Snake_Shrine.json` | `data/source/wiki/pages/Snake_Shrine.json` |
| `data/wiki/pages/Sneak_Peeks.json` | `data/source/wiki/pages/Sneak_Peeks.json` |
| `data/wiki/pages/Sneaky_Archer.json` | `data/source/wiki/pages/Sneaky_Archer.json` |
| `data/wiki/pages/Sneaky_Goblin.json` | `data/source/wiki/pages/Sneaky_Goblin.json` |
| `data/wiki/pages/Sneezy.json` | `data/source/wiki/pages/Sneezy.json` |
| `data/wiki/pages/Sneezy_Booger.json` | `data/source/wiki/pages/Sneezy_Booger.json` |
| `data/wiki/pages/Sound_of_Clash.json` | `data/source/wiki/pages/Sound_of_Clash.json` |
| `data/wiki/pages/Soundtrack.json` | `data/source/wiki/pages/Soundtrack.json` |
| `data/wiki/pages/Sour_Elixir_Cauldron.json` | `data/source/wiki/pages/Sour_Elixir_Cauldron.json` |
| `data/wiki/pages/Spear_Thrower.json` | `data/source/wiki/pages/Spear_Thrower.json` |
| `data/wiki/pages/Spear_Trap.json` | `data/source/wiki/pages/Spear_Trap.json` |
| `data/wiki/pages/Spell_Factory.json` | `data/source/wiki/pages/Spell_Factory.json` |
| `data/wiki/pages/Spell_Tower.json` | `data/source/wiki/pages/Spell_Tower.json` |
| `data/wiki/pages/Spells.json` | `data/source/wiki/pages/Spells.json` |
| `data/wiki/pages/Spiky_Ball.json` | `data/source/wiki/pages/Spiky_Ball.json` |
| `data/wiki/pages/Spirit_Fox.json` | `data/source/wiki/pages/Spirit_Fox.json` |
| `data/wiki/pages/Spring_Trap_Home_Village.json` | `data/source/wiki/pages/Spring_Trap_Home_Village.json` |
| `data/wiki/pages/Star_Bonus.json` | `data/source/wiki/pages/Star_Bonus.json` |
| `data/wiki/pages/Stars.json` | `data/source/wiki/pages/Stars.json` |
| `data/wiki/pages/Starter_Challenges.json` | `data/source/wiki/pages/Starter_Challenges.json` |
| `data/wiki/pages/Stick_Horse.json` | `data/source/wiki/pages/Stick_Horse.json` |
| `data/wiki/pages/Stone_Slammer.json` | `data/source/wiki/pages/Stone_Slammer.json` |
| `data/wiki/pages/Streak_Event.json` | `data/source/wiki/pages/Streak_Event.json` |
| `data/wiki/pages/Strongman_s_Caravan.json` | `data/source/wiki/pages/Strongman_s_Caravan.json` |
| `data/wiki/pages/Stun_Blaster.json` | `data/source/wiki/pages/Stun_Blaster.json` |
| `data/wiki/pages/Suggested_Updates.json` | `data/source/wiki/pages/Suggested_Updates.json` |
| `data/wiki/pages/Super_Archer.json` | `data/source/wiki/pages/Super_Archer.json` |
| `data/wiki/pages/Super_Barbarian.json` | `data/source/wiki/pages/Super_Barbarian.json` |
| `data/wiki/pages/Super_Barbarian_Home_Village.json` | `data/source/wiki/pages/Super_Barbarian_Home_Village.json` |
| `data/wiki/pages/Super_Bowler.json` | `data/source/wiki/pages/Super_Bowler.json` |
| `data/wiki/pages/Super_Dragon.json` | `data/source/wiki/pages/Super_Dragon.json` |
| `data/wiki/pages/Super_Dragon_Home_Village.json` | `data/source/wiki/pages/Super_Dragon_Home_Village.json` |
| `data/wiki/pages/Super_Dragon_Post.json` | `data/source/wiki/pages/Super_Dragon_Post.json` |
| `data/wiki/pages/Super_Giant.json` | `data/source/wiki/pages/Super_Giant.json` |
| `data/wiki/pages/Super_Giant_Home_Village.json` | `data/source/wiki/pages/Super_Giant_Home_Village.json` |
| `data/wiki/pages/Super_Giant_Post.json` | `data/source/wiki/pages/Super_Giant_Post.json` |
| `data/wiki/pages/Super_Hog_Rider.json` | `data/source/wiki/pages/Super_Hog_Rider.json` |
| `data/wiki/pages/Super_Hog_Rider_Super_Hog.json` | `data/source/wiki/pages/Super_Hog_Rider_Super_Hog.json` |
| `data/wiki/pages/Super_Hog_Rider_Super_Rider.json` | `data/source/wiki/pages/Super_Hog_Rider_Super_Rider.json` |
| `data/wiki/pages/Super_Ice_Bath.json` | `data/source/wiki/pages/Super_Ice_Bath.json` |
| `data/wiki/pages/Super_Miner.json` | `data/source/wiki/pages/Super_Miner.json` |
| `data/wiki/pages/Super_Miner_Home_Village.json` | `data/source/wiki/pages/Super_Miner_Home_Village.json` |
| `data/wiki/pages/Super_Minion.json` | `data/source/wiki/pages/Super_Minion.json` |
| `data/wiki/pages/Super_Troop_Spotlight.json` | `data/source/wiki/pages/Super_Troop_Spotlight.json` |
| `data/wiki/pages/Super_Troops.json` | `data/source/wiki/pages/Super_Troops.json` |
| `data/wiki/pages/Super_Valkyrie.json` | `data/source/wiki/pages/Super_Valkyrie.json` |
| `data/wiki/pages/Super_Wall_Breaker.json` | `data/source/wiki/pages/Super_Wall_Breaker.json` |
| `data/wiki/pages/Super_Witch.json` | `data/source/wiki/pages/Super_Witch.json` |
| `data/wiki/pages/Super_Witch_Big_Boy.json` | `data/source/wiki/pages/Super_Witch_Big_Boy.json` |
| `data/wiki/pages/Super_Wizard.json` | `data/source/wiki/pages/Super_Wizard.json` |
| `data/wiki/pages/Super_Wizard_Home_Village.json` | `data/source/wiki/pages/Super_Wizard_Home_Village.json` |
| `data/wiki/pages/Super_Wizard_Tower.json` | `data/source/wiki/pages/Super_Wizard_Tower.json` |
| `data/wiki/pages/Super_Wizard_Tower_Home_Village.json` | `data/source/wiki/pages/Super_Wizard_Tower_Home_Village.json` |
| `data/wiki/pages/Super_Yeti.json` | `data/source/wiki/pages/Super_Yeti.json` |
| `data/wiki/pages/Super_Yeti_Electromite.json` | `data/source/wiki/pages/Super_Yeti_Electromite.json` |
| `data/wiki/pages/Supercharge.json` | `data/source/wiki/pages/Supercharge.json` |
| `data/wiki/pages/Temporary_Troops.json` | `data/source/wiki/pages/Temporary_Troops.json` |
| `data/wiki/pages/The_Disarmer.json` | `data/source/wiki/pages/The_Disarmer.json` |
| `data/wiki/pages/Thrower.json` | `data/source/wiki/pages/Thrower.json` |
| `data/wiki/pages/Tornado_Trap.json` | `data/source/wiki/pages/Tornado_Trap.json` |
| `data/wiki/pages/Totem_Spell.json` | `data/source/wiki/pages/Totem_Spell.json` |
| `data/wiki/pages/Totem_Thrower.json` | `data/source/wiki/pages/Totem_Thrower.json` |
| `data/wiki/pages/Town_Hall.json` | `data/source/wiki/pages/Town_Hall.json` |
| `data/wiki/pages/Town_Hall_Giga_Inferno.json` | `data/source/wiki/pages/Town_Hall_Giga_Inferno.json` |
| `data/wiki/pages/Town_Hall_Giga_Inferno_TH13.json` | `data/source/wiki/pages/Town_Hall_Giga_Inferno_TH13.json` |
| `data/wiki/pages/Town_Hall_Giga_Inferno_TH14.json` | `data/source/wiki/pages/Town_Hall_Giga_Inferno_TH14.json` |
| `data/wiki/pages/Town_Hall_Giga_Inferno_TH15.json` | `data/source/wiki/pages/Town_Hall_Giga_Inferno_TH15.json` |
| `data/wiki/pages/Town_Hall_Giga_Inferno_TH16.json` | `data/source/wiki/pages/Town_Hall_Giga_Inferno_TH16.json` |
| `data/wiki/pages/Town_Hall_Giga_Tesla.json` | `data/source/wiki/pages/Town_Hall_Giga_Tesla.json` |
| `data/wiki/pages/Town_Hall_Giga_Weapons.json` | `data/source/wiki/pages/Town_Hall_Giga_Weapons.json` |
| `data/wiki/pages/Town_Hall_Guardians.json` | `data/source/wiki/pages/Town_Hall_Guardians.json` |
| `data/wiki/pages/Town_Hall_Home_Village.json` | `data/source/wiki/pages/Town_Hall_Home_Village.json` |
| `data/wiki/pages/Town_Hall_Inferno_Artillery.json` | `data/source/wiki/pages/Town_Hall_Inferno_Artillery.json` |
| `data/wiki/pages/Town_Hall_Trivia.json` | `data/source/wiki/pages/Town_Hall_Trivia.json` |
| `data/wiki/pages/Town_Hall_Unlocks.json` | `data/source/wiki/pages/Town_Hall_Unlocks.json` |
| `data/wiki/pages/Town_Hall_Upgrade_Differences.json` | `data/source/wiki/pages/Town_Hall_Upgrade_Differences.json` |
| `data/wiki/pages/Toyshop_Throwdown.json` | `data/source/wiki/pages/Toyshop_Throwdown.json` |
| `data/wiki/pages/Traps.json` | `data/source/wiki/pages/Traps.json` |
| `data/wiki/pages/Traps_Home_Village.json` | `data/source/wiki/pages/Traps_Home_Village.json` |
| `data/wiki/pages/Treasure.json` | `data/source/wiki/pages/Treasure.json` |
| `data/wiki/pages/Treasure_Chests.json` | `data/source/wiki/pages/Treasure_Chests.json` |
| `data/wiki/pages/Treasure_Hunt.json` | `data/source/wiki/pages/Treasure_Hunt.json` |
| `data/wiki/pages/Treasury.json` | `data/source/wiki/pages/Treasury.json` |
| `data/wiki/pages/Troop_Launcher.json` | `data/source/wiki/pages/Troop_Launcher.json` |
| `data/wiki/pages/Troop_Movement_Speed.json` | `data/source/wiki/pages/Troop_Movement_Speed.json` |
| `data/wiki/pages/Troop_Targeting.json` | `data/source/wiki/pages/Troop_Targeting.json` |
| `data/wiki/pages/Troops.json` | `data/source/wiki/pages/Troops.json` |
| `data/wiki/pages/Trophies.json` | `data/source/wiki/pages/Trophies.json` |
| `data/wiki/pages/Trophy_Leagues.json` | `data/source/wiki/pages/Trophy_Leagues.json` |
| `data/wiki/pages/Unicorn.json` | `data/source/wiki/pages/Unicorn.json` |
| `data/wiki/pages/Valkyrie.json` | `data/source/wiki/pages/Valkyrie.json` |
| `data/wiki/pages/Vampstache.json` | `data/source/wiki/pages/Vampstache.json` |
| `data/wiki/pages/Versus_Battles.json` | `data/source/wiki/pages/Versus_Battles.json` |
| `data/wiki/pages/Village_Edit_Mode.json` | `data/source/wiki/pages/Village_Edit_Mode.json` |
| `data/wiki/pages/Wall.json` | `data/source/wiki/pages/Wall.json` |
| `data/wiki/pages/Wall_Breaker.json` | `data/source/wiki/pages/Wall_Breaker.json` |
| `data/wiki/pages/Wall_Home_Village.json` | `data/source/wiki/pages/Wall_Home_Village.json` |
| `data/wiki/pages/Wall_Wrecker.json` | `data/source/wiki/pages/Wall_Wrecker.json` |
| `data/wiki/pages/Walls_Home_Village.json` | `data/source/wiki/pages/Walls_Home_Village.json` |
| `data/wiki/pages/War_Alliances.json` | `data/source/wiki/pages/War_Alliances.json` |
| `data/wiki/pages/Wise_Warriors.json` | `data/source/wiki/pages/Wise_Warriors.json` |
| `data/wiki/pages/Witch.json` | `data/source/wiki/pages/Witch.json` |
| `data/wiki/pages/Witch_Golem.json` | `data/source/wiki/pages/Witch_Golem.json` |
| `data/wiki/pages/Witch_Golem_Big_Boy.json` | `data/source/wiki/pages/Witch_Golem_Big_Boy.json` |
| `data/wiki/pages/Witch_Golem_Skeleton.json` | `data/source/wiki/pages/Witch_Golem_Skeleton.json` |
| `data/wiki/pages/Witch_Skeleton.json` | `data/source/wiki/pages/Witch_Skeleton.json` |
| `data/wiki/pages/Wizard.json` | `data/source/wiki/pages/Wizard.json` |
| `data/wiki/pages/Wizard_Tower.json` | `data/source/wiki/pages/Wizard_Tower.json` |
| `data/wiki/pages/Wizard_Vendor.json` | `data/source/wiki/pages/Wizard_Vendor.json` |
| `data/wiki/pages/Workshop.json` | `data/source/wiki/pages/Workshop.json` |
| `data/wiki/pages/X-Bow.json` | `data/source/wiki/pages/X-Bow.json` |
| `data/wiki/pages/X-Bow_Home_Village.json` | `data/source/wiki/pages/X-Bow_Home_Village.json` |
| `data/wiki/pages/YEETer.json` | `data/source/wiki/pages/YEETer.json` |
| `data/wiki/pages/YEETer_Tribal_Tag_Team.json` | `data/source/wiki/pages/YEETer_Tribal_Tag_Team.json` |
| `data/wiki/pages/Yellow_Card.json` | `data/source/wiki/pages/Yellow_Card.json` |
| `data/wiki/pages/Yeti.json` | `data/source/wiki/pages/Yeti.json` |
| `data/wiki/pages/Yeti_Undertaker.json` | `data/source/wiki/pages/Yeti_Undertaker.json` |
| `data/wiki/pages/Yeti_Undertaker_Skeletons_of_Darkness.json` | `data/source/wiki/pages/Yeti_Undertaker_Skeletons_of_Darkness.json` |
| `data/wiki/pages/Yeti_Yetimite.json` | `data/source/wiki/pages/Yeti_Yetimite.json` |
| `data/wiki/pages/Zap_Trap.json` | `data/source/wiki/pages/Zap_Trap.json` |
| `data/wiki/tables/Action_Figure.json` | `data/source/wiki/tables/Action_Figure.json` |
| `data/wiki/tables/Air_Bomb.json` | `data/source/wiki/tables/Air_Bomb.json` |
| `data/wiki/tables/Air_Bombs.json` | `data/source/wiki/tables/Air_Bombs.json` |
| `data/wiki/tables/Air_Bombs_Home_Village.json` | `data/source/wiki/tables/Air_Bombs_Home_Village.json` |
| `data/wiki/tables/Air_Defense.json` | `data/source/wiki/tables/Air_Defense.json` |
| `data/wiki/tables/Air_Defense_Home_Village.json` | `data/source/wiki/tables/Air_Defense_Home_Village.json` |
| `data/wiki/tables/Air_Sweeper.json` | `data/source/wiki/tables/Air_Sweeper.json` |
| `data/wiki/tables/Airship.json` | `data/source/wiki/tables/Airship.json` |
| `data/wiki/tables/Alchemist.json` | `data/source/wiki/tables/Alchemist.json` |
| `data/wiki/tables/Angry_Jelly.json` | `data/source/wiki/tables/Angry_Jelly.json` |
| `data/wiki/tables/Angry_Spell.json` | `data/source/wiki/tables/Angry_Spell.json` |
| `data/wiki/tables/Anime_Clash.json` | `data/source/wiki/tables/Anime_Clash.json` |
| `data/wiki/tables/Anime_Fury_Medal_Event.json` | `data/source/wiki/tables/Anime_Fury_Medal_Event.json` |
| `data/wiki/tables/Apprentice_Warden.json` | `data/source/wiki/tables/Apprentice_Warden.json` |
| `data/wiki/tables/Archer.json` | `data/source/wiki/tables/Archer.json` |
| `data/wiki/tables/Archer_Puppet.json` | `data/source/wiki/tables/Archer_Puppet.json` |
| `data/wiki/tables/Archer_Queen.json` | `data/source/wiki/tables/Archer_Queen.json` |
| `data/wiki/tables/Archer_Queen_Altar.json` | `data/source/wiki/tables/Archer_Queen_Altar.json` |
| `data/wiki/tables/Archer_Queen_Skin_Features.json` | `data/source/wiki/tables/Archer_Queen_Skin_Features.json` |
| `data/wiki/tables/Archer_Tower.json` | `data/source/wiki/tables/Archer_Tower.json` |
| `data/wiki/tables/Archer_Tower_Home_Village.json` | `data/source/wiki/tables/Archer_Tower_Home_Village.json` |
| `data/wiki/tables/Army.json` | `data/source/wiki/tables/Army.json` |
| `data/wiki/tables/Army_Buildings_Home_Village.json` | `data/source/wiki/tables/Army_Buildings_Home_Village.json` |
| `data/wiki/tables/Army_Camp_Home_Village.json` | `data/source/wiki/tables/Army_Camp_Home_Village.json` |
| `data/wiki/tables/Attack_Challenges.json` | `data/source/wiki/tables/Attack_Challenges.json` |
| `data/wiki/tables/Attack_Challenges_Archive.json` | `data/source/wiki/tables/Attack_Challenges_Archive.json` |
| `data/wiki/tables/Attack_Challenges_Archive_2022.json` | `data/source/wiki/tables/Attack_Challenges_Archive_2022.json` |
| `data/wiki/tables/Attack_Challenges_Archive_2023.json` | `data/source/wiki/tables/Attack_Challenges_Archive_2023.json` |
| `data/wiki/tables/Attack_Challenges_Archive_Pre-2022.json` | `data/source/wiki/tables/Attack_Challenges_Archive_Pre-2022.json` |
| `data/wiki/tables/Attack_Challenges_Controllable_Heroes_Cookie_Chaos.json` | `data/source/wiki/tables/Attack_Challenges_Controllable_Heroes_Cookie_Chaos.json` |
| `data/wiki/tables/Attack_Challenges_Hero_Campaign_Dragon_Escape.json` | `data/source/wiki/tables/Attack_Challenges_Hero_Campaign_Dragon_Escape.json` |
| `data/wiki/tables/Awesome_Medal_Event.json` | `data/source/wiki/tables/Awesome_Medal_Event.json` |
| `data/wiki/tables/Azure_Dragon.json` | `data/source/wiki/tables/Azure_Dragon.json` |
| `data/wiki/tables/B.O.B_s_Hut.json` | `data/source/wiki/tables/B.O.B_s_Hut.json` |
| `data/wiki/tables/Baby_Dragon.json` | `data/source/wiki/tables/Baby_Dragon.json` |
| `data/wiki/tables/Baby_Dragon_Home_Village.json` | `data/source/wiki/tables/Baby_Dragon_Home_Village.json` |
| `data/wiki/tables/Bag_of_Frostmites.json` | `data/source/wiki/tables/Bag_of_Frostmites.json` |
| `data/wiki/tables/Balloon.json` | `data/source/wiki/tables/Balloon.json` |
| `data/wiki/tables/Barbarian.json` | `data/source/wiki/tables/Barbarian.json` |
| `data/wiki/tables/Barbarian_Home_Village.json` | `data/source/wiki/tables/Barbarian_Home_Village.json` |
| `data/wiki/tables/Barbarian_Kicker.json` | `data/source/wiki/tables/Barbarian_Kicker.json` |
| `data/wiki/tables/Barbarian_King.json` | `data/source/wiki/tables/Barbarian_King.json` |
| `data/wiki/tables/Barbarian_King_Altar.json` | `data/source/wiki/tables/Barbarian_King_Altar.json` |
| `data/wiki/tables/Barbarian_King_Skin_Features.json` | `data/source/wiki/tables/Barbarian_King_Skin_Features.json` |
| `data/wiki/tables/Barbarian_Puppet.json` | `data/source/wiki/tables/Barbarian_Puppet.json` |
| `data/wiki/tables/Barcher.json` | `data/source/wiki/tables/Barcher.json` |
| `data/wiki/tables/Barracks.json` | `data/source/wiki/tables/Barracks.json` |
| `data/wiki/tables/Bat.json` | `data/source/wiki/tables/Bat.json` |
| `data/wiki/tables/Bat_Spell.json` | `data/source/wiki/tables/Bat_Spell.json` |
| `data/wiki/tables/Bat_Spell_Bat.json` | `data/source/wiki/tables/Bat_Spell_Bat.json` |
| `data/wiki/tables/Battle_Blimp.json` | `data/source/wiki/tables/Battle_Blimp.json` |
| `data/wiki/tables/Battle_Copter.json` | `data/source/wiki/tables/Battle_Copter.json` |
| `data/wiki/tables/Battle_Copter_Altar.json` | `data/source/wiki/tables/Battle_Copter_Altar.json` |
| `data/wiki/tables/Battle_Drill.json` | `data/source/wiki/tables/Battle_Drill.json` |
| `data/wiki/tables/Battle_Machine.json` | `data/source/wiki/tables/Battle_Machine.json` |
| `data/wiki/tables/Battle_Machine_Altar.json` | `data/source/wiki/tables/Battle_Machine_Altar.json` |
| `data/wiki/tables/Battle_Ram.json` | `data/source/wiki/tables/Battle_Ram.json` |
| `data/wiki/tables/Battle_Ram_Home_Village.json` | `data/source/wiki/tables/Battle_Ram_Home_Village.json` |
| `data/wiki/tables/Beta_Minion.json` | `data/source/wiki/tables/Beta_Minion.json` |
| `data/wiki/tables/Birthday_Boom.json` | `data/source/wiki/tables/Birthday_Boom.json` |
| `data/wiki/tables/Blacksmith.json` | `data/source/wiki/tables/Blacksmith.json` |
| `data/wiki/tables/Blast_Bow.json` | `data/source/wiki/tables/Blast_Bow.json` |
| `data/wiki/tables/Boat.json` | `data/source/wiki/tables/Boat.json` |
| `data/wiki/tables/Bomb.json` | `data/source/wiki/tables/Bomb.json` |
| `data/wiki/tables/Bomb_Hive.json` | `data/source/wiki/tables/Bomb_Hive.json` |
| `data/wiki/tables/Bomb_Tower.json` | `data/source/wiki/tables/Bomb_Tower.json` |
| `data/wiki/tables/Bomb_Tower_Home_Village.json` | `data/source/wiki/tables/Bomb_Tower_Home_Village.json` |
| `data/wiki/tables/Bomber.json` | `data/source/wiki/tables/Bomber.json` |
| `data/wiki/tables/Bowler.json` | `data/source/wiki/tables/Bowler.json` |
| `data/wiki/tables/Boxer_Giant.json` | `data/source/wiki/tables/Boxer_Giant.json` |
| `data/wiki/tables/Broom_Witch.json` | `data/source/wiki/tables/Broom_Witch.json` |
| `data/wiki/tables/Broom_Witch_Witch_Spirit.json` | `data/source/wiki/tables/Broom_Witch_Witch_Spirit.json` |
| `data/wiki/tables/Builder.json` | `data/source/wiki/tables/Builder.json` |
| `data/wiki/tables/Builder_Battles.json` | `data/source/wiki/tables/Builder_Battles.json` |
| `data/wiki/tables/Builder_s_Apprentice.json` | `data/source/wiki/tables/Builder_s_Apprentice.json` |
| `data/wiki/tables/Builder_s_Hut.json` | `data/source/wiki/tables/Builder_s_Hut.json` |
| `data/wiki/tables/C.O.O.K.I.E.json` | `data/source/wiki/tables/C.O.O.K.I.E.json` |
| `data/wiki/tables/Cake-A-Pult.json` | `data/source/wiki/tables/Cake-A-Pult.json` |
| `data/wiki/tables/Cannon.json` | `data/source/wiki/tables/Cannon.json` |
| `data/wiki/tables/Cannon_Cart.json` | `data/source/wiki/tables/Cannon_Cart.json` |
| `data/wiki/tables/Cannon_Home_Village.json` | `data/source/wiki/tables/Cannon_Home_Village.json` |
| `data/wiki/tables/Chief_s_Journey.json` | `data/source/wiki/tables/Chief_s_Journey.json` |
| `data/wiki/tables/Clan_Badge.json` | `data/source/wiki/tables/Clan_Badge.json` |
| `data/wiki/tables/Clan_Castle.json` | `data/source/wiki/tables/Clan_Castle.json` |
| `data/wiki/tables/Clan_Games.json` | `data/source/wiki/tables/Clan_Games.json` |
| `data/wiki/tables/Clan_Games_Archive.json` | `data/source/wiki/tables/Clan_Games_Archive.json` |
| `data/wiki/tables/Clan_Games_Challenges.json` | `data/source/wiki/tables/Clan_Games_Challenges.json` |
| `data/wiki/tables/Clan_Perks.json` | `data/source/wiki/tables/Clan_Perks.json` |
| `data/wiki/tables/Clan_Rush.json` | `data/source/wiki/tables/Clan_Rush.json` |
| `data/wiki/tables/Clan_War_Leagues.json` | `data/source/wiki/tables/Clan_War_Leagues.json` |
| `data/wiki/tables/Clan_Wars.json` | `data/source/wiki/tables/Clan_Wars.json` |
| `data/wiki/tables/Clans.json` | `data/source/wiki/tables/Clans.json` |
| `data/wiki/tables/Clash_of_Cards.json` | `data/source/wiki/tables/Clash_of_Cards.json` |
| `data/wiki/tables/Clash_of_Clans_Skin_Sets.json` | `data/source/wiki/tables/Clash_of_Clans_Skin_Sets.json` |
| `data/wiki/tables/Clash_with_Haaland.json` | `data/source/wiki/tables/Clash_with_Haaland.json` |
| `data/wiki/tables/Clone_Spell.json` | `data/source/wiki/tables/Clone_Spell.json` |
| `data/wiki/tables/Cookie_Rumble.json` | `data/source/wiki/tables/Cookie_Rumble.json` |
| `data/wiki/tables/Cosmic_Rock.json` | `data/source/wiki/tables/Cosmic_Rock.json` |
| `data/wiki/tables/Crafting_Station.json` | `data/source/wiki/tables/Crafting_Station.json` |
| `data/wiki/tables/Crusher.json` | `data/source/wiki/tables/Crusher.json` |
| `data/wiki/tables/Crusher_Mortar.json` | `data/source/wiki/tables/Crusher_Mortar.json` |
| `data/wiki/tables/Cumulative_Costs.json` | `data/source/wiki/tables/Cumulative_Costs.json` |
| `data/wiki/tables/Cumulative_Costs_Home_Village.json` | `data/source/wiki/tables/Cumulative_Costs_Home_Village.json` |
| `data/wiki/tables/Dark_Barracks.json` | `data/source/wiki/tables/Dark_Barracks.json` |
| `data/wiki/tables/Dark_Crown.json` | `data/source/wiki/tables/Dark_Crown.json` |
| `data/wiki/tables/Dark_Deal.json` | `data/source/wiki/tables/Dark_Deal.json` |
| `data/wiki/tables/Dark_Elixir_Drill.json` | `data/source/wiki/tables/Dark_Elixir_Drill.json` |
| `data/wiki/tables/Dark_Elixir_Storage.json` | `data/source/wiki/tables/Dark_Elixir_Storage.json` |
| `data/wiki/tables/Dark_Elixir_Troops.json` | `data/source/wiki/tables/Dark_Elixir_Troops.json` |
| `data/wiki/tables/Dark_Orb.json` | `data/source/wiki/tables/Dark_Orb.json` |
| `data/wiki/tables/Dark_Spell_Factory.json` | `data/source/wiki/tables/Dark_Spell_Factory.json` |
| `data/wiki/tables/Dark_Spells.json` | `data/source/wiki/tables/Dark_Spells.json` |
| `data/wiki/tables/Debt_Collector.json` | `data/source/wiki/tables/Debt_Collector.json` |
| `data/wiki/tables/Defensive_Buildings_Home_Village.json` | `data/source/wiki/tables/Defensive_Buildings_Home_Village.json` |
| `data/wiki/tables/Diggy.json` | `data/source/wiki/tables/Diggy.json` |
| `data/wiki/tables/Double_Cannon.json` | `data/source/wiki/tables/Double_Cannon.json` |
| `data/wiki/tables/Dragon.json` | `data/source/wiki/tables/Dragon.json` |
| `data/wiki/tables/Dragon_Dash.json` | `data/source/wiki/tables/Dragon_Dash.json` |
| `data/wiki/tables/Dragon_Duke.json` | `data/source/wiki/tables/Dragon_Duke.json` |
| `data/wiki/tables/Dragon_Festival.json` | `data/source/wiki/tables/Dragon_Festival.json` |
| `data/wiki/tables/Dragon_Pinata.json` | `data/source/wiki/tables/Dragon_Pinata.json` |
| `data/wiki/tables/Dragon_Rider.json` | `data/source/wiki/tables/Dragon_Rider.json` |
| `data/wiki/tables/Drop_Ship.json` | `data/source/wiki/tables/Drop_Ship.json` |
| `data/wiki/tables/Drop_Ship_Skeleton.json` | `data/source/wiki/tables/Drop_Ship_Skeleton.json` |
| `data/wiki/tables/Druid.json` | `data/source/wiki/tables/Druid.json` |
| `data/wiki/tables/Druid_Bear.json` | `data/source/wiki/tables/Druid_Bear.json` |
| `data/wiki/tables/Eagle_Artillery.json` | `data/source/wiki/tables/Eagle_Artillery.json` |
| `data/wiki/tables/Earthquake_Boots.json` | `data/source/wiki/tables/Earthquake_Boots.json` |
| `data/wiki/tables/Earthquake_Spell.json` | `data/source/wiki/tables/Earthquake_Spell.json` |
| `data/wiki/tables/El_Primo.json` | `data/source/wiki/tables/El_Primo.json` |
| `data/wiki/tables/Electro_Boots.json` | `data/source/wiki/tables/Electro_Boots.json` |
| `data/wiki/tables/Electro_Dragon.json` | `data/source/wiki/tables/Electro_Dragon.json` |
| `data/wiki/tables/Electro_Fangs.json` | `data/source/wiki/tables/Electro_Fangs.json` |
| `data/wiki/tables/Electro_Owl.json` | `data/source/wiki/tables/Electro_Owl.json` |
| `data/wiki/tables/Electro_Titan.json` | `data/source/wiki/tables/Electro_Titan.json` |
| `data/wiki/tables/Electrofire_Wizard.json` | `data/source/wiki/tables/Electrofire_Wizard.json` |
| `data/wiki/tables/Elephant_Rider.json` | `data/source/wiki/tables/Elephant_Rider.json` |
| `data/wiki/tables/Elephant_Rider_Elephant.json` | `data/source/wiki/tables/Elephant_Rider_Elephant.json` |
| `data/wiki/tables/Elephant_Rider_Rider.json` | `data/source/wiki/tables/Elephant_Rider_Rider.json` |
| `data/wiki/tables/Elixir_Collector_Home_Village.json` | `data/source/wiki/tables/Elixir_Collector_Home_Village.json` |
| `data/wiki/tables/Elixir_Spells.json` | `data/source/wiki/tables/Elixir_Spells.json` |
| `data/wiki/tables/Elixir_Storage.json` | `data/source/wiki/tables/Elixir_Storage.json` |
| `data/wiki/tables/Elixir_Storage_Home_Village.json` | `data/source/wiki/tables/Elixir_Storage_Home_Village.json` |
| `data/wiki/tables/Elixir_Troops.json` | `data/source/wiki/tables/Elixir_Troops.json` |
| `data/wiki/tables/Endless_Haste_Spell.json` | `data/source/wiki/tables/Endless_Haste_Spell.json` |
| `data/wiki/tables/Equipment_Blast.json` | `data/source/wiki/tables/Equipment_Blast.json` |
| `data/wiki/tables/Eternal_Tome.json` | `data/source/wiki/tables/Eternal_Tome.json` |
| `data/wiki/tables/Events.json` | `data/source/wiki/tables/Events.json` |
| `data/wiki/tables/Experience.json` | `data/source/wiki/tables/Experience.json` |
| `data/wiki/tables/Fancy_Shop.json` | `data/source/wiki/tables/Fancy_Shop.json` |
| `data/wiki/tables/Fire_Heart.json` | `data/source/wiki/tables/Fire_Heart.json` |
| `data/wiki/tables/Fireball.json` | `data/source/wiki/tables/Fireball.json` |
| `data/wiki/tables/Firecracker.json` | `data/source/wiki/tables/Firecracker.json` |
| `data/wiki/tables/Firecrackers.json` | `data/source/wiki/tables/Firecrackers.json` |
| `data/wiki/tables/Firespitter.json` | `data/source/wiki/tables/Firespitter.json` |
| `data/wiki/tables/Flame_Blower.json` | `data/source/wiki/tables/Flame_Blower.json` |
| `data/wiki/tables/Flame_Flinger.json` | `data/source/wiki/tables/Flame_Flinger.json` |
| `data/wiki/tables/Flame_Spinner.json` | `data/source/wiki/tables/Flame_Spinner.json` |
| `data/wiki/tables/Flying_Fortress.json` | `data/source/wiki/tables/Flying_Fortress.json` |
| `data/wiki/tables/Flying_Fortress_Skeleton_Glider.json` | `data/source/wiki/tables/Flying_Fortress_Skeleton_Glider.json` |
| `data/wiki/tables/Football_Camp.json` | `data/source/wiki/tables/Football_Camp.json` |
| `data/wiki/tables/Forge.json` | `data/source/wiki/tables/Forge.json` |
| `data/wiki/tables/Freeze_Spell.json` | `data/source/wiki/tables/Freeze_Spell.json` |
| `data/wiki/tables/Freeze_Trap.json` | `data/source/wiki/tables/Freeze_Trap.json` |
| `data/wiki/tables/Friend_or_Foe.json` | `data/source/wiki/tables/Friend_or_Foe.json` |
| `data/wiki/tables/Frost_Flake.json` | `data/source/wiki/tables/Frost_Flake.json` |
| `data/wiki/tables/Frost_Spell.json` | `data/source/wiki/tables/Frost_Spell.json` |
| `data/wiki/tables/Frosty.json` | `data/source/wiki/tables/Frosty.json` |
| `data/wiki/tables/Frosty_Frostmite.json` | `data/source/wiki/tables/Frosty_Frostmite.json` |
| `data/wiki/tables/Frozen_Arrow.json` | `data/source/wiki/tables/Frozen_Arrow.json` |
| `data/wiki/tables/Furnace.json` | `data/source/wiki/tables/Furnace.json` |
| `data/wiki/tables/Furnace_Firemite.json` | `data/source/wiki/tables/Furnace_Firemite.json` |
| `data/wiki/tables/Game_Tips.json` | `data/source/wiki/tables/Game_Tips.json` |
| `data/wiki/tables/Gems.json` | `data/source/wiki/tables/Gems.json` |
| `data/wiki/tables/Giant.json` | `data/source/wiki/tables/Giant.json` |
| `data/wiki/tables/Giant_Arrow.json` | `data/source/wiki/tables/Giant_Arrow.json` |
| `data/wiki/tables/Giant_Bomb.json` | `data/source/wiki/tables/Giant_Bomb.json` |
| `data/wiki/tables/Giant_Cannon.json` | `data/source/wiki/tables/Giant_Cannon.json` |
| `data/wiki/tables/Giant_Gauntlet.json` | `data/source/wiki/tables/Giant_Gauntlet.json` |
| `data/wiki/tables/Giant_Giant.json` | `data/source/wiki/tables/Giant_Giant.json` |
| `data/wiki/tables/Giant_Skeleton.json` | `data/source/wiki/tables/Giant_Skeleton.json` |
| `data/wiki/tables/Giant_Thrower.json` | `data/source/wiki/tables/Giant_Thrower.json` |
| `data/wiki/tables/Giga_Bomb.json` | `data/source/wiki/tables/Giga_Bomb.json` |
| `data/wiki/tables/Gingerbread_Bakery.json` | `data/source/wiki/tables/Gingerbread_Bakery.json` |
| `data/wiki/tables/Glossary.json` | `data/source/wiki/tables/Glossary.json` |
| `data/wiki/tables/Goblin.json` | `data/source/wiki/tables/Goblin.json` |
| `data/wiki/tables/Goblin_Thrower.json` | `data/source/wiki/tables/Goblin_Thrower.json` |
| `data/wiki/tables/Goblin_Workers.json` | `data/source/wiki/tables/Goblin_Workers.json` |
| `data/wiki/tables/Gold_Mine_Home_Village.json` | `data/source/wiki/tables/Gold_Mine_Home_Village.json` |
| `data/wiki/tables/Gold_Rush.json` | `data/source/wiki/tables/Gold_Rush.json` |
| `data/wiki/tables/Gold_Storage.json` | `data/source/wiki/tables/Gold_Storage.json` |
| `data/wiki/tables/Gold_Storage_Home_Village.json` | `data/source/wiki/tables/Gold_Storage_Home_Village.json` |
| `data/wiki/tables/Golden_Dragon.json` | `data/source/wiki/tables/Golden_Dragon.json` |
| `data/wiki/tables/Golem.json` | `data/source/wiki/tables/Golem.json` |
| `data/wiki/tables/Golem_Golemite.json` | `data/source/wiki/tables/Golem_Golemite.json` |
| `data/wiki/tables/Grand_Warden.json` | `data/source/wiki/tables/Grand_Warden.json` |
| `data/wiki/tables/Grand_Warden_Altar.json` | `data/source/wiki/tables/Grand_Warden_Altar.json` |
| `data/wiki/tables/Grand_Warden_Skin_Features.json` | `data/source/wiki/tables/Grand_Warden_Skin_Features.json` |
| `data/wiki/tables/Graveyard_Spell.json` | `data/source/wiki/tables/Graveyard_Spell.json` |
| `data/wiki/tables/Greedy_Raven.json` | `data/source/wiki/tables/Greedy_Raven.json` |
| `data/wiki/tables/Guard.json` | `data/source/wiki/tables/Guard.json` |
| `data/wiki/tables/Guard_Post.json` | `data/source/wiki/tables/Guard_Post.json` |
| `data/wiki/tables/Hall_of_Fame.json` | `data/source/wiki/tables/Hall_of_Fame.json` |
| `data/wiki/tables/Haste_Spell.json` | `data/source/wiki/tables/Haste_Spell.json` |
| `data/wiki/tables/Haste_Vial.json` | `data/source/wiki/tables/Haste_Vial.json` |
| `data/wiki/tables/Headhunter.json` | `data/source/wiki/tables/Headhunter.json` |
| `data/wiki/tables/Healer.json` | `data/source/wiki/tables/Healer.json` |
| `data/wiki/tables/Healer_Puppet.json` | `data/source/wiki/tables/Healer_Puppet.json` |
| `data/wiki/tables/Healing_Spell.json` | `data/source/wiki/tables/Healing_Spell.json` |
| `data/wiki/tables/Healing_Spell_Home_Village.json` | `data/source/wiki/tables/Healing_Spell_Home_Village.json` |
| `data/wiki/tables/Healing_Tome.json` | `data/source/wiki/tables/Healing_Tome.json` |
| `data/wiki/tables/Helper_Hut.json` | `data/source/wiki/tables/Helper_Hut.json` |
| `data/wiki/tables/Henchmen_Puppet.json` | `data/source/wiki/tables/Henchmen_Puppet.json` |
| `data/wiki/tables/Henchmen_Puppet_Henchmen.json` | `data/source/wiki/tables/Henchmen_Puppet_Henchmen.json` |
| `data/wiki/tables/Hero_Banner.json` | `data/source/wiki/tables/Hero_Banner.json` |
| `data/wiki/tables/Hero_Bell.json` | `data/source/wiki/tables/Hero_Bell.json` |
| `data/wiki/tables/Hero_Equipment.json` | `data/source/wiki/tables/Hero_Equipment.json` |
| `data/wiki/tables/Hero_Hall.json` | `data/source/wiki/tables/Hero_Hall.json` |
| `data/wiki/tables/Hero_Hunter.json` | `data/source/wiki/tables/Hero_Hunter.json` |
| `data/wiki/tables/Hero_Rush.json` | `data/source/wiki/tables/Hero_Rush.json` |
| `data/wiki/tables/Hero_s_Journey.json` | `data/source/wiki/tables/Hero_s_Journey.json` |
| `data/wiki/tables/Heroes.json` | `data/source/wiki/tables/Heroes.json` |
| `data/wiki/tables/Heroic_Torch.json` | `data/source/wiki/tables/Heroic_Torch.json` |
| `data/wiki/tables/Hidden_Mega_Tesla.json` | `data/source/wiki/tables/Hidden_Mega_Tesla.json` |
| `data/wiki/tables/Hidden_Tesla_Home_Village.json` | `data/source/wiki/tables/Hidden_Tesla_Home_Village.json` |
| `data/wiki/tables/Hog_Glider.json` | `data/source/wiki/tables/Hog_Glider.json` |
| `data/wiki/tables/Hog_Raiders.json` | `data/source/wiki/tables/Hog_Raiders.json` |
| `data/wiki/tables/Hog_Rider.json` | `data/source/wiki/tables/Hog_Rider.json` |
| `data/wiki/tables/Hog_Rider_Puppet.json` | `data/source/wiki/tables/Hog_Rider_Puppet.json` |
| `data/wiki/tables/Hog_Wizard.json` | `data/source/wiki/tables/Hog_Wizard.json` |
| `data/wiki/tables/Hook_Tower.json` | `data/source/wiki/tables/Hook_Tower.json` |
| `data/wiki/tables/Hot_Candle.json` | `data/source/wiki/tables/Hot_Candle.json` |
| `data/wiki/tables/Hydra_Headstone.json` | `data/source/wiki/tables/Hydra_Headstone.json` |
| `data/wiki/tables/Ice_Block_Spell.json` | `data/source/wiki/tables/Ice_Block_Spell.json` |
| `data/wiki/tables/Ice_Golem.json` | `data/source/wiki/tables/Ice_Golem.json` |
| `data/wiki/tables/Ice_Hound.json` | `data/source/wiki/tables/Ice_Hound.json` |
| `data/wiki/tables/Ice_Hound_Ice_Pup.json` | `data/source/wiki/tables/Ice_Hound_Ice_Pup.json` |
| `data/wiki/tables/Ice_Minion.json` | `data/source/wiki/tables/Ice_Minion.json` |
| `data/wiki/tables/Ice_Wizard.json` | `data/source/wiki/tables/Ice_Wizard.json` |
| `data/wiki/tables/In-App_Purchases.json` | `data/source/wiki/tables/In-App_Purchases.json` |
| `data/wiki/tables/Individual_Costs.json` | `data/source/wiki/tables/Individual_Costs.json` |
| `data/wiki/tables/Individual_Costs_Home_Village.json` | `data/source/wiki/tables/Individual_Costs_Home_Village.json` |
| `data/wiki/tables/Inferno_Dragon.json` | `data/source/wiki/tables/Inferno_Dragon.json` |
| `data/wiki/tables/Inferno_Dragon_Home_Village.json` | `data/source/wiki/tables/Inferno_Dragon_Home_Village.json` |
| `data/wiki/tables/Inferno_Tower.json` | `data/source/wiki/tables/Inferno_Tower.json` |
| `data/wiki/tables/Inferno_Tower_Home_Village.json` | `data/source/wiki/tables/Inferno_Tower_Home_Village.json` |
| `data/wiki/tables/Invisibility_Spell.json` | `data/source/wiki/tables/Invisibility_Spell.json` |
| `data/wiki/tables/Invisibility_Vial.json` | `data/source/wiki/tables/Invisibility_Vial.json` |
| `data/wiki/tables/Jump_Spell.json` | `data/source/wiki/tables/Jump_Spell.json` |
| `data/wiki/tables/Jump_Spell_Home_Village.json` | `data/source/wiki/tables/Jump_Spell_Home_Village.json` |
| `data/wiki/tables/K.A.N.E.json` | `data/source/wiki/tables/K.A.N.E.json` |
| `data/wiki/tables/L.A.S.S.I.json` | `data/source/wiki/tables/L.A.S.S.I.json` |
| `data/wiki/tables/Lab_Assistant.json` | `data/source/wiki/tables/Lab_Assistant.json` |
| `data/wiki/tables/Laboratory.json` | `data/source/wiki/tables/Laboratory.json` |
| `data/wiki/tables/Lava_Hound.json` | `data/source/wiki/tables/Lava_Hound.json` |
| `data/wiki/tables/Lava_Hound_Lava_Pup.json` | `data/source/wiki/tables/Lava_Hound_Lava_Pup.json` |
| `data/wiki/tables/Lava_Launcher.json` | `data/source/wiki/tables/Lava_Launcher.json` |
| `data/wiki/tables/Lava_Launcher_Home_Village.json` | `data/source/wiki/tables/Lava_Launcher_Home_Village.json` |
| `data/wiki/tables/Lavaloon.json` | `data/source/wiki/tables/Lavaloon.json` |
| `data/wiki/tables/Lavaloon_Lavaloon_Pup.json` | `data/source/wiki/tables/Lavaloon_Lavaloon_Pup.json` |
| `data/wiki/tables/Lavaloon_Puppet.json` | `data/source/wiki/tables/Lavaloon_Puppet.json` |
| `data/wiki/tables/Lavaloon_Puppet_Lavaloon.json` | `data/source/wiki/tables/Lavaloon_Puppet_Lavaloon.json` |
| `data/wiki/tables/Layouts_Home_Village.json` | `data/source/wiki/tables/Layouts_Home_Village.json` |
| `data/wiki/tables/Life_Gem.json` | `data/source/wiki/tables/Life_Gem.json` |
| `data/wiki/tables/Light_Beam.json` | `data/source/wiki/tables/Light_Beam.json` |
| `data/wiki/tables/Lightning_Spell.json` | `data/source/wiki/tables/Lightning_Spell.json` |
| `data/wiki/tables/Lightning_Spell_Home_Village.json` | `data/source/wiki/tables/Lightning_Spell_Home_Village.json` |
| `data/wiki/tables/Loading_Screen_Hints.json` | `data/source/wiki/tables/Loading_Screen_Hints.json` |
| `data/wiki/tables/Loading_Screens.json` | `data/source/wiki/tables/Loading_Screens.json` |
| `data/wiki/tables/Log_Launcher.json` | `data/source/wiki/tables/Log_Launcher.json` |
| `data/wiki/tables/Log_Trap.json` | `data/source/wiki/tables/Log_Trap.json` |
| `data/wiki/tables/Logger.json` | `data/source/wiki/tables/Logger.json` |
| `data/wiki/tables/Longshot.json` | `data/source/wiki/tables/Longshot.json` |
| `data/wiki/tables/Loot_Cart.json` | `data/source/wiki/tables/Loot_Cart.json` |
| `data/wiki/tables/M.E.C.H.A.json` | `data/source/wiki/tables/M.E.C.H.A.json` |
| `data/wiki/tables/Magic_Items.json` | `data/source/wiki/tables/Magic_Items.json` |
| `data/wiki/tables/Magic_Items_List.json` | `data/source/wiki/tables/Magic_Items_List.json` |
| `data/wiki/tables/Magic_Mirror.json` | `data/source/wiki/tables/Magic_Mirror.json` |
| `data/wiki/tables/Magic_Snacks.json` | `data/source/wiki/tables/Magic_Snacks.json` |
| `data/wiki/tables/Mashup_Madness.json` | `data/source/wiki/tables/Mashup_Madness.json` |
| `data/wiki/tables/Mashup_Mania.json` | `data/source/wiki/tables/Mashup_Mania.json` |
| `data/wiki/tables/Master_Builder_s_Boat.json` | `data/source/wiki/tables/Master_Builder_s_Boat.json` |
| `data/wiki/tables/Master_Builder_s_Hut.json` | `data/source/wiki/tables/Master_Builder_s_Hut.json` |
| `data/wiki/tables/Mega_Mine.json` | `data/source/wiki/tables/Mega_Mine.json` |
| `data/wiki/tables/Mega_Sparky.json` | `data/source/wiki/tables/Mega_Sparky.json` |
| `data/wiki/tables/Mega_Tesla.json` | `data/source/wiki/tables/Mega_Tesla.json` |
| `data/wiki/tables/Meltdown_Mayhem.json` | `data/source/wiki/tables/Meltdown_Mayhem.json` |
| `data/wiki/tables/Metal_Pants.json` | `data/source/wiki/tables/Metal_Pants.json` |
| `data/wiki/tables/Meteor_Golem.json` | `data/source/wiki/tables/Meteor_Golem.json` |
| `data/wiki/tables/Meteor_Golem_Meteormite.json` | `data/source/wiki/tables/Meteor_Golem_Meteormite.json` |
| `data/wiki/tables/Meteor_Staff.json` | `data/source/wiki/tables/Meteor_Staff.json` |
| `data/wiki/tables/Mighty_Yak.json` | `data/source/wiki/tables/Mighty_Yak.json` |
| `data/wiki/tables/Mine.json` | `data/source/wiki/tables/Mine.json` |
| `data/wiki/tables/Miner.json` | `data/source/wiki/tables/Miner.json` |
| `data/wiki/tables/Mini-Minion_Hive.json` | `data/source/wiki/tables/Mini-Minion_Hive.json` |
| `data/wiki/tables/Minion.json` | `data/source/wiki/tables/Minion.json` |
| `data/wiki/tables/Minion_Horde.json` | `data/source/wiki/tables/Minion_Horde.json` |
| `data/wiki/tables/Minion_Prince.json` | `data/source/wiki/tables/Minion_Prince.json` |
| `data/wiki/tables/Money_in_the_Bank_Rush.json` | `data/source/wiki/tables/Money_in_the_Bank_Rush.json` |
| `data/wiki/tables/Monolith.json` | `data/source/wiki/tables/Monolith.json` |
| `data/wiki/tables/Monolith_Arrow.json` | `data/source/wiki/tables/Monolith_Arrow.json` |
| `data/wiki/tables/Mortar.json` | `data/source/wiki/tables/Mortar.json` |
| `data/wiki/tables/Mountain_Golem.json` | `data/source/wiki/tables/Mountain_Golem.json` |
| `data/wiki/tables/Multi-Archer_Tower.json` | `data/source/wiki/tables/Multi-Archer_Tower.json` |
| `data/wiki/tables/Multi-Gear_Tower.json` | `data/source/wiki/tables/Multi-Gear_Tower.json` |
| `data/wiki/tables/Multi_Cannon.json` | `data/source/wiki/tables/Multi_Cannon.json` |
| `data/wiki/tables/Multi_Mortar.json` | `data/source/wiki/tables/Multi_Mortar.json` |
| `data/wiki/tables/Multiplayer_Battles.json` | `data/source/wiki/tables/Multiplayer_Battles.json` |
| `data/wiki/tables/Night_Witch.json` | `data/source/wiki/tables/Night_Witch.json` |
| `data/wiki/tables/Night_Witch_Bat.json` | `data/source/wiki/tables/Night_Witch_Bat.json` |
| `data/wiki/tables/Noble_Iron.json` | `data/source/wiki/tables/Noble_Iron.json` |
| `data/wiki/tables/O.T.T.O_s_Outpost.json` | `data/source/wiki/tables/O.T.T.O_s_Outpost.json` |
| `data/wiki/tables/Ores.json` | `data/source/wiki/tables/Ores.json` |
| `data/wiki/tables/Other_Buildings_Home_Village.json` | `data/source/wiki/tables/Other_Buildings_Home_Village.json` |
| `data/wiki/tables/Overgrowth_Spell.json` | `data/source/wiki/tables/Overgrowth_Spell.json` |
| `data/wiki/tables/P.E.K.K.A.json` | `data/source/wiki/tables/P.E.K.K.A.json` |
| `data/wiki/tables/Party_Wizard.json` | `data/source/wiki/tables/Party_Wizard.json` |
| `data/wiki/tables/Pet_House.json` | `data/source/wiki/tables/Pet_House.json` |
| `data/wiki/tables/Pets.json` | `data/source/wiki/tables/Pets.json` |
| `data/wiki/tables/Phoenix.json` | `data/source/wiki/tables/Phoenix.json` |
| `data/wiki/tables/Player_Profile.json` | `data/source/wiki/tables/Player_Profile.json` |
| `data/wiki/tables/Poison_Lizard.json` | `data/source/wiki/tables/Poison_Lizard.json` |
| `data/wiki/tables/Poison_Spell.json` | `data/source/wiki/tables/Poison_Spell.json` |
| `data/wiki/tables/Portal_Panic.json` | `data/source/wiki/tables/Portal_Panic.json` |
| `data/wiki/tables/Portal_Pendant.json` | `data/source/wiki/tables/Portal_Pendant.json` |
| `data/wiki/tables/Power_P.E.K.K.A.json` | `data/source/wiki/tables/Power_P.E.K.K.A.json` |
| `data/wiki/tables/Practice_Mode.json` | `data/source/wiki/tables/Practice_Mode.json` |
| `data/wiki/tables/Prospector.json` | `data/source/wiki/tables/Prospector.json` |
| `data/wiki/tables/Pumpkin_Barbarian.json` | `data/source/wiki/tables/Pumpkin_Barbarian.json` |
| `data/wiki/tables/Pumpkin_Bomb.json` | `data/source/wiki/tables/Pumpkin_Bomb.json` |
| `data/wiki/tables/Push_Trap.json` | `data/source/wiki/tables/Push_Trap.json` |
| `data/wiki/tables/Rage_Gem.json` | `data/source/wiki/tables/Rage_Gem.json` |
| `data/wiki/tables/Rage_Spell.json` | `data/source/wiki/tables/Rage_Spell.json` |
| `data/wiki/tables/Rage_Spell_Home_Village.json` | `data/source/wiki/tables/Rage_Spell_Home_Village.json` |
| `data/wiki/tables/Rage_Vial.json` | `data/source/wiki/tables/Rage_Vial.json` |
| `data/wiki/tables/Raged_Barbarian.json` | `data/source/wiki/tables/Raged_Barbarian.json` |
| `data/wiki/tables/Raid_Cart.json` | `data/source/wiki/tables/Raid_Cart.json` |
| `data/wiki/tables/Raid_Cart_Post.json` | `data/source/wiki/tables/Raid_Cart_Post.json` |
| `data/wiki/tables/Raid_Weekends.json` | `data/source/wiki/tables/Raid_Weekends.json` |
| `data/wiki/tables/Ram_Rider.json` | `data/source/wiki/tables/Ram_Rider.json` |
| `data/wiki/tables/Ranked_Battles.json` | `data/source/wiki/tables/Ranked_Battles.json` |
| `data/wiki/tables/Rapid_Rockets.json` | `data/source/wiki/tables/Rapid_Rockets.json` |
| `data/wiki/tables/Recall_Spell.json` | `data/source/wiki/tables/Recall_Spell.json` |
| `data/wiki/tables/Reflector.json` | `data/source/wiki/tables/Reflector.json` |
| `data/wiki/tables/Removed_features.json` | `data/source/wiki/tables/Removed_features.json` |
| `data/wiki/tables/Resource_Buildings_Home_Village.json` | `data/source/wiki/tables/Resource_Buildings_Home_Village.json` |
| `data/wiki/tables/Revenge_Deck.json` | `data/source/wiki/tables/Revenge_Deck.json` |
| `data/wiki/tables/Revenge_Tower.json` | `data/source/wiki/tables/Revenge_Tower.json` |
| `data/wiki/tables/Revive_Spell.json` | `data/source/wiki/tables/Revive_Spell.json` |
| `data/wiki/tables/Ricochet_Cannon.json` | `data/source/wiki/tables/Ricochet_Cannon.json` |
| `data/wiki/tables/Roaster.json` | `data/source/wiki/tables/Roaster.json` |
| `data/wiki/tables/Roaster_Home_Village.json` | `data/source/wiki/tables/Roaster_Home_Village.json` |
| `data/wiki/tables/Rocket_Artillery.json` | `data/source/wiki/tables/Rocket_Artillery.json` |
| `data/wiki/tables/Rocket_Backpack.json` | `data/source/wiki/tables/Rocket_Backpack.json` |
| `data/wiki/tables/Rocket_Balloon.json` | `data/source/wiki/tables/Rocket_Balloon.json` |
| `data/wiki/tables/Rocket_Balloon_Home_Village.json` | `data/source/wiki/tables/Rocket_Balloon_Home_Village.json` |
| `data/wiki/tables/Rocket_Spear.json` | `data/source/wiki/tables/Rocket_Spear.json` |
| `data/wiki/tables/Rocking_Reindeer.json` | `data/source/wiki/tables/Rocking_Reindeer.json` |
| `data/wiki/tables/Root_Rider.json` | `data/source/wiki/tables/Root_Rider.json` |
| `data/wiki/tables/Royal_Champion.json` | `data/source/wiki/tables/Royal_Champion.json` |
| `data/wiki/tables/Royal_Champion_Altar.json` | `data/source/wiki/tables/Royal_Champion_Altar.json` |
| `data/wiki/tables/Royal_Champion_Skin_Features.json` | `data/source/wiki/tables/Royal_Champion_Skin_Features.json` |
| `data/wiki/tables/Royal_Gem.json` | `data/source/wiki/tables/Royal_Gem.json` |
| `data/wiki/tables/Royal_Ghost.json` | `data/source/wiki/tables/Royal_Ghost.json` |
| `data/wiki/tables/Ruin_Witch.json` | `data/source/wiki/tables/Ruin_Witch.json` |
| `data/wiki/tables/Ruin_Witch_Ruin_Knight.json` | `data/source/wiki/tables/Ruin_Witch_Ruin_Knight.json` |
| `data/wiki/tables/Rumbling_Goblins.json` | `data/source/wiki/tables/Rumbling_Goblins.json` |
| `data/wiki/tables/Santa_Strike.json` | `data/source/wiki/tables/Santa_Strike.json` |
| `data/wiki/tables/Santa_s_Surprise.json` | `data/source/wiki/tables/Santa_s_Surprise.json` |
| `data/wiki/tables/Scattershot.json` | `data/source/wiki/tables/Scattershot.json` |
| `data/wiki/tables/Season_Challenges.json` | `data/source/wiki/tables/Season_Challenges.json` |
| `data/wiki/tables/Season_Challenges_Archive.json` | `data/source/wiki/tables/Season_Challenges_Archive.json` |
| `data/wiki/tables/Season_Challenges_Archive_2019.json` | `data/source/wiki/tables/Season_Challenges_Archive_2019.json` |
| `data/wiki/tables/Season_Challenges_Archive_2020.json` | `data/source/wiki/tables/Season_Challenges_Archive_2020.json` |
| `data/wiki/tables/Season_Challenges_Archive_2021.json` | `data/source/wiki/tables/Season_Challenges_Archive_2021.json` |
| `data/wiki/tables/Season_Challenges_Archive_2022.json` | `data/source/wiki/tables/Season_Challenges_Archive_2022.json` |
| `data/wiki/tables/Season_Challenges_Archive_2023.json` | `data/source/wiki/tables/Season_Challenges_Archive_2023.json` |
| `data/wiki/tables/Season_Challenges_List.json` | `data/source/wiki/tables/Season_Challenges_List.json` |
| `data/wiki/tables/Seeking_Air_Mine.json` | `data/source/wiki/tables/Seeking_Air_Mine.json` |
| `data/wiki/tables/Seeking_Shield.json` | `data/source/wiki/tables/Seeking_Shield.json` |
| `data/wiki/tables/Shield.json` | `data/source/wiki/tables/Shield.json` |
| `data/wiki/tables/Shrink_Trap.json` | `data/source/wiki/tables/Shrink_Trap.json` |
| `data/wiki/tables/Siege_Barracks.json` | `data/source/wiki/tables/Siege_Barracks.json` |
| `data/wiki/tables/Siege_Machines.json` | `data/source/wiki/tables/Siege_Machines.json` |
| `data/wiki/tables/Single_Player_Campaign.json` | `data/source/wiki/tables/Single_Player_Campaign.json` |
| `data/wiki/tables/Skeleton.json` | `data/source/wiki/tables/Skeleton.json` |
| `data/wiki/tables/Skeleton_Barrel.json` | `data/source/wiki/tables/Skeleton_Barrel.json` |
| `data/wiki/tables/Skeleton_Barrel_Home_Village.json` | `data/source/wiki/tables/Skeleton_Barrel_Home_Village.json` |
| `data/wiki/tables/Skeleton_Spell.json` | `data/source/wiki/tables/Skeleton_Spell.json` |
| `data/wiki/tables/Skeleton_Spell_Skeleton.json` | `data/source/wiki/tables/Skeleton_Spell_Skeleton.json` |
| `data/wiki/tables/Skeleton_Trap.json` | `data/source/wiki/tables/Skeleton_Trap.json` |
| `data/wiki/tables/Sky_Wagon.json` | `data/source/wiki/tables/Sky_Wagon.json` |
| `data/wiki/tables/Smasher.json` | `data/source/wiki/tables/Smasher.json` |
| `data/wiki/tables/Snake.json` | `data/source/wiki/tables/Snake.json` |
| `data/wiki/tables/Snake_Barrel.json` | `data/source/wiki/tables/Snake_Barrel.json` |
| `data/wiki/tables/Snake_Barrel_Snake.json` | `data/source/wiki/tables/Snake_Barrel_Snake.json` |
| `data/wiki/tables/Snake_Bracelet.json` | `data/source/wiki/tables/Snake_Bracelet.json` |
| `data/wiki/tables/Snake_Bracelet_Snake.json` | `data/source/wiki/tables/Snake_Bracelet_Snake.json` |
| `data/wiki/tables/Snake_Festival.json` | `data/source/wiki/tables/Snake_Festival.json` |
| `data/wiki/tables/Snake_Shrine.json` | `data/source/wiki/tables/Snake_Shrine.json` |
| `data/wiki/tables/Sneak_Peeks.json` | `data/source/wiki/tables/Sneak_Peeks.json` |
| `data/wiki/tables/Sneaky_Archer.json` | `data/source/wiki/tables/Sneaky_Archer.json` |
| `data/wiki/tables/Sneaky_Goblin.json` | `data/source/wiki/tables/Sneaky_Goblin.json` |
| `data/wiki/tables/Sneezy.json` | `data/source/wiki/tables/Sneezy.json` |
| `data/wiki/tables/Sneezy_Booger.json` | `data/source/wiki/tables/Sneezy_Booger.json` |
| `data/wiki/tables/Sound_of_Clash.json` | `data/source/wiki/tables/Sound_of_Clash.json` |
| `data/wiki/tables/Soundtrack.json` | `data/source/wiki/tables/Soundtrack.json` |
| `data/wiki/tables/Sour_Elixir_Cauldron.json` | `data/source/wiki/tables/Sour_Elixir_Cauldron.json` |
| `data/wiki/tables/Spear_Thrower.json` | `data/source/wiki/tables/Spear_Thrower.json` |
| `data/wiki/tables/Spear_Trap.json` | `data/source/wiki/tables/Spear_Trap.json` |
| `data/wiki/tables/Spell_Factory.json` | `data/source/wiki/tables/Spell_Factory.json` |
| `data/wiki/tables/Spell_Tower.json` | `data/source/wiki/tables/Spell_Tower.json` |
| `data/wiki/tables/Spells.json` | `data/source/wiki/tables/Spells.json` |
| `data/wiki/tables/Spiky_Ball.json` | `data/source/wiki/tables/Spiky_Ball.json` |
| `data/wiki/tables/Spirit_Fox.json` | `data/source/wiki/tables/Spirit_Fox.json` |
| `data/wiki/tables/Spring_Trap_Home_Village.json` | `data/source/wiki/tables/Spring_Trap_Home_Village.json` |
| `data/wiki/tables/Star_Bonus.json` | `data/source/wiki/tables/Star_Bonus.json` |
| `data/wiki/tables/Starter_Challenges.json` | `data/source/wiki/tables/Starter_Challenges.json` |
| `data/wiki/tables/Stick_Horse.json` | `data/source/wiki/tables/Stick_Horse.json` |
| `data/wiki/tables/Stone_Slammer.json` | `data/source/wiki/tables/Stone_Slammer.json` |
| `data/wiki/tables/Streak_Event.json` | `data/source/wiki/tables/Streak_Event.json` |
| `data/wiki/tables/Strongman_s_Caravan.json` | `data/source/wiki/tables/Strongman_s_Caravan.json` |
| `data/wiki/tables/Stun_Blaster.json` | `data/source/wiki/tables/Stun_Blaster.json` |
| `data/wiki/tables/Suggested_Updates.json` | `data/source/wiki/tables/Suggested_Updates.json` |
| `data/wiki/tables/Super_Archer.json` | `data/source/wiki/tables/Super_Archer.json` |
| `data/wiki/tables/Super_Barbarian.json` | `data/source/wiki/tables/Super_Barbarian.json` |
| `data/wiki/tables/Super_Barbarian_Home_Village.json` | `data/source/wiki/tables/Super_Barbarian_Home_Village.json` |
| `data/wiki/tables/Super_Bowler.json` | `data/source/wiki/tables/Super_Bowler.json` |
| `data/wiki/tables/Super_Dragon.json` | `data/source/wiki/tables/Super_Dragon.json` |
| `data/wiki/tables/Super_Dragon_Home_Village.json` | `data/source/wiki/tables/Super_Dragon_Home_Village.json` |
| `data/wiki/tables/Super_Dragon_Post.json` | `data/source/wiki/tables/Super_Dragon_Post.json` |
| `data/wiki/tables/Super_Giant.json` | `data/source/wiki/tables/Super_Giant.json` |
| `data/wiki/tables/Super_Giant_Home_Village.json` | `data/source/wiki/tables/Super_Giant_Home_Village.json` |
| `data/wiki/tables/Super_Giant_Post.json` | `data/source/wiki/tables/Super_Giant_Post.json` |
| `data/wiki/tables/Super_Hog_Rider.json` | `data/source/wiki/tables/Super_Hog_Rider.json` |
| `data/wiki/tables/Super_Hog_Rider_Super_Hog.json` | `data/source/wiki/tables/Super_Hog_Rider_Super_Hog.json` |
| `data/wiki/tables/Super_Hog_Rider_Super_Rider.json` | `data/source/wiki/tables/Super_Hog_Rider_Super_Rider.json` |
| `data/wiki/tables/Super_Ice_Bath.json` | `data/source/wiki/tables/Super_Ice_Bath.json` |
| `data/wiki/tables/Super_Miner.json` | `data/source/wiki/tables/Super_Miner.json` |
| `data/wiki/tables/Super_Miner_Home_Village.json` | `data/source/wiki/tables/Super_Miner_Home_Village.json` |
| `data/wiki/tables/Super_Minion.json` | `data/source/wiki/tables/Super_Minion.json` |
| `data/wiki/tables/Super_Troop_Spotlight.json` | `data/source/wiki/tables/Super_Troop_Spotlight.json` |
| `data/wiki/tables/Super_Troops.json` | `data/source/wiki/tables/Super_Troops.json` |
| `data/wiki/tables/Super_Valkyrie.json` | `data/source/wiki/tables/Super_Valkyrie.json` |
| `data/wiki/tables/Super_Wall_Breaker.json` | `data/source/wiki/tables/Super_Wall_Breaker.json` |
| `data/wiki/tables/Super_Witch.json` | `data/source/wiki/tables/Super_Witch.json` |
| `data/wiki/tables/Super_Witch_Big_Boy.json` | `data/source/wiki/tables/Super_Witch_Big_Boy.json` |
| `data/wiki/tables/Super_Wizard.json` | `data/source/wiki/tables/Super_Wizard.json` |
| `data/wiki/tables/Super_Wizard_Home_Village.json` | `data/source/wiki/tables/Super_Wizard_Home_Village.json` |
| `data/wiki/tables/Super_Wizard_Tower.json` | `data/source/wiki/tables/Super_Wizard_Tower.json` |
| `data/wiki/tables/Super_Wizard_Tower_Home_Village.json` | `data/source/wiki/tables/Super_Wizard_Tower_Home_Village.json` |
| `data/wiki/tables/Super_Yeti.json` | `data/source/wiki/tables/Super_Yeti.json` |
| `data/wiki/tables/Super_Yeti_Electromite.json` | `data/source/wiki/tables/Super_Yeti_Electromite.json` |
| `data/wiki/tables/Supercharge.json` | `data/source/wiki/tables/Supercharge.json` |
| `data/wiki/tables/Temporary_Troops.json` | `data/source/wiki/tables/Temporary_Troops.json` |
| `data/wiki/tables/The_Disarmer.json` | `data/source/wiki/tables/The_Disarmer.json` |
| `data/wiki/tables/Thrower.json` | `data/source/wiki/tables/Thrower.json` |
| `data/wiki/tables/Tornado_Trap.json` | `data/source/wiki/tables/Tornado_Trap.json` |
| `data/wiki/tables/Totem_Spell.json` | `data/source/wiki/tables/Totem_Spell.json` |
| `data/wiki/tables/Totem_Thrower.json` | `data/source/wiki/tables/Totem_Thrower.json` |
| `data/wiki/tables/Town_Hall.json` | `data/source/wiki/tables/Town_Hall.json` |
| `data/wiki/tables/Town_Hall_Giga_Inferno.json` | `data/source/wiki/tables/Town_Hall_Giga_Inferno.json` |
| `data/wiki/tables/Town_Hall_Giga_Inferno_TH13.json` | `data/source/wiki/tables/Town_Hall_Giga_Inferno_TH13.json` |
| `data/wiki/tables/Town_Hall_Giga_Inferno_TH14.json` | `data/source/wiki/tables/Town_Hall_Giga_Inferno_TH14.json` |
| `data/wiki/tables/Town_Hall_Giga_Inferno_TH15.json` | `data/source/wiki/tables/Town_Hall_Giga_Inferno_TH15.json` |
| `data/wiki/tables/Town_Hall_Giga_Inferno_TH16.json` | `data/source/wiki/tables/Town_Hall_Giga_Inferno_TH16.json` |
| `data/wiki/tables/Town_Hall_Giga_Tesla.json` | `data/source/wiki/tables/Town_Hall_Giga_Tesla.json` |
| `data/wiki/tables/Town_Hall_Giga_Weapons.json` | `data/source/wiki/tables/Town_Hall_Giga_Weapons.json` |
| `data/wiki/tables/Town_Hall_Guardians.json` | `data/source/wiki/tables/Town_Hall_Guardians.json` |
| `data/wiki/tables/Town_Hall_Inferno_Artillery.json` | `data/source/wiki/tables/Town_Hall_Inferno_Artillery.json` |
| `data/wiki/tables/Town_Hall_Trivia.json` | `data/source/wiki/tables/Town_Hall_Trivia.json` |
| `data/wiki/tables/Town_Hall_Unlocks.json` | `data/source/wiki/tables/Town_Hall_Unlocks.json` |
| `data/wiki/tables/Town_Hall_Upgrade_Differences.json` | `data/source/wiki/tables/Town_Hall_Upgrade_Differences.json` |
| `data/wiki/tables/Toyshop_Throwdown.json` | `data/source/wiki/tables/Toyshop_Throwdown.json` |
| `data/wiki/tables/Traps.json` | `data/source/wiki/tables/Traps.json` |
| `data/wiki/tables/Traps_Home_Village.json` | `data/source/wiki/tables/Traps_Home_Village.json` |
| `data/wiki/tables/Treasure.json` | `data/source/wiki/tables/Treasure.json` |
| `data/wiki/tables/Treasure_Chests.json` | `data/source/wiki/tables/Treasure_Chests.json` |
| `data/wiki/tables/Treasure_Hunt.json` | `data/source/wiki/tables/Treasure_Hunt.json` |
| `data/wiki/tables/Treasury.json` | `data/source/wiki/tables/Treasury.json` |
| `data/wiki/tables/Troop_Launcher.json` | `data/source/wiki/tables/Troop_Launcher.json` |
| `data/wiki/tables/Troop_Movement_Speed.json` | `data/source/wiki/tables/Troop_Movement_Speed.json` |
| `data/wiki/tables/Troops.json` | `data/source/wiki/tables/Troops.json` |
| `data/wiki/tables/Trophies.json` | `data/source/wiki/tables/Trophies.json` |
| `data/wiki/tables/Trophy_Leagues.json` | `data/source/wiki/tables/Trophy_Leagues.json` |
| `data/wiki/tables/Unicorn.json` | `data/source/wiki/tables/Unicorn.json` |
| `data/wiki/tables/Valkyrie.json` | `data/source/wiki/tables/Valkyrie.json` |
| `data/wiki/tables/Vampstache.json` | `data/source/wiki/tables/Vampstache.json` |
| `data/wiki/tables/Versus_Battles.json` | `data/source/wiki/tables/Versus_Battles.json` |
| `data/wiki/tables/Village_Edit_Mode.json` | `data/source/wiki/tables/Village_Edit_Mode.json` |
| `data/wiki/tables/Wall.json` | `data/source/wiki/tables/Wall.json` |
| `data/wiki/tables/Wall_Breaker.json` | `data/source/wiki/tables/Wall_Breaker.json` |
| `data/wiki/tables/Wall_Home_Village.json` | `data/source/wiki/tables/Wall_Home_Village.json` |
| `data/wiki/tables/Wall_Wrecker.json` | `data/source/wiki/tables/Wall_Wrecker.json` |
| `data/wiki/tables/Walls_Home_Village.json` | `data/source/wiki/tables/Walls_Home_Village.json` |
| `data/wiki/tables/War_Alliances.json` | `data/source/wiki/tables/War_Alliances.json` |
| `data/wiki/tables/Wise_Warriors.json` | `data/source/wiki/tables/Wise_Warriors.json` |
| `data/wiki/tables/Witch.json` | `data/source/wiki/tables/Witch.json` |
| `data/wiki/tables/Witch_Golem.json` | `data/source/wiki/tables/Witch_Golem.json` |
| `data/wiki/tables/Witch_Golem_Big_Boy.json` | `data/source/wiki/tables/Witch_Golem_Big_Boy.json` |
| `data/wiki/tables/Witch_Golem_Skeleton.json` | `data/source/wiki/tables/Witch_Golem_Skeleton.json` |
| `data/wiki/tables/Witch_Skeleton.json` | `data/source/wiki/tables/Witch_Skeleton.json` |
| `data/wiki/tables/Wizard.json` | `data/source/wiki/tables/Wizard.json` |
| `data/wiki/tables/Wizard_Tower.json` | `data/source/wiki/tables/Wizard_Tower.json` |
| `data/wiki/tables/Wizard_Vendor.json` | `data/source/wiki/tables/Wizard_Vendor.json` |
| `data/wiki/tables/Workshop.json` | `data/source/wiki/tables/Workshop.json` |
| `data/wiki/tables/X-Bow.json` | `data/source/wiki/tables/X-Bow.json` |
| `data/wiki/tables/X-Bow_Home_Village.json` | `data/source/wiki/tables/X-Bow_Home_Village.json` |
| `data/wiki/tables/YEETer.json` | `data/source/wiki/tables/YEETer.json` |
| `data/wiki/tables/YEETer_Tribal_Tag_Team.json` | `data/source/wiki/tables/YEETer_Tribal_Tag_Team.json` |
| `data/wiki/tables/Yellow_Card.json` | `data/source/wiki/tables/Yellow_Card.json` |
| `data/wiki/tables/Yeti.json` | `data/source/wiki/tables/Yeti.json` |
| `data/wiki/tables/Yeti_Undertaker.json` | `data/source/wiki/tables/Yeti_Undertaker.json` |
| `data/wiki/tables/Yeti_Undertaker_Skeletons_of_Darkness.json` | `data/source/wiki/tables/Yeti_Undertaker_Skeletons_of_Darkness.json` |
| `data/wiki/tables/Yeti_Yetimite.json` | `data/source/wiki/tables/Yeti_Yetimite.json` |
| `data/wiki/tables/Zap_Trap.json` | `data/source/wiki/tables/Zap_Trap.json` |
| `data/wiki/text/Action_Figure.txt` | `data/source/wiki/text/Action_Figure.txt` |
| `data/wiki/text/Air_Bomb.txt` | `data/source/wiki/text/Air_Bomb.txt` |
| `data/wiki/text/Air_Bombs.txt` | `data/source/wiki/text/Air_Bombs.txt` |
| `data/wiki/text/Air_Bombs_Home_Village.txt` | `data/source/wiki/text/Air_Bombs_Home_Village.txt` |
| `data/wiki/text/Air_Defense.txt` | `data/source/wiki/text/Air_Defense.txt` |
| `data/wiki/text/Air_Defense_Home_Village.txt` | `data/source/wiki/text/Air_Defense_Home_Village.txt` |
| `data/wiki/text/Air_Sweeper.txt` | `data/source/wiki/text/Air_Sweeper.txt` |
| `data/wiki/text/Airship.txt` | `data/source/wiki/text/Airship.txt` |
| `data/wiki/text/Alchemist.txt` | `data/source/wiki/text/Alchemist.txt` |
| `data/wiki/text/Angry_Jelly.txt` | `data/source/wiki/text/Angry_Jelly.txt` |
| `data/wiki/text/Angry_Spell.txt` | `data/source/wiki/text/Angry_Spell.txt` |
| `data/wiki/text/Anime_Clash.txt` | `data/source/wiki/text/Anime_Clash.txt` |
| `data/wiki/text/Anime_Fury_Medal_Event.txt` | `data/source/wiki/text/Anime_Fury_Medal_Event.txt` |
| `data/wiki/text/Apprentice_Warden.txt` | `data/source/wiki/text/Apprentice_Warden.txt` |
| `data/wiki/text/Archer.txt` | `data/source/wiki/text/Archer.txt` |
| `data/wiki/text/Archer_Puppet.txt` | `data/source/wiki/text/Archer_Puppet.txt` |
| `data/wiki/text/Archer_Queen.txt` | `data/source/wiki/text/Archer_Queen.txt` |
| `data/wiki/text/Archer_Queen_Altar.txt` | `data/source/wiki/text/Archer_Queen_Altar.txt` |
| `data/wiki/text/Archer_Queen_Skin_Features.txt` | `data/source/wiki/text/Archer_Queen_Skin_Features.txt` |
| `data/wiki/text/Archer_Tower.txt` | `data/source/wiki/text/Archer_Tower.txt` |
| `data/wiki/text/Archer_Tower_Home_Village.txt` | `data/source/wiki/text/Archer_Tower_Home_Village.txt` |
| `data/wiki/text/Army.txt` | `data/source/wiki/text/Army.txt` |
| `data/wiki/text/Army_Buildings_Home_Village.txt` | `data/source/wiki/text/Army_Buildings_Home_Village.txt` |
| `data/wiki/text/Army_Camp_Home_Village.txt` | `data/source/wiki/text/Army_Camp_Home_Village.txt` |
| `data/wiki/text/Attack_Challenges.txt` | `data/source/wiki/text/Attack_Challenges.txt` |
| `data/wiki/text/Attack_Challenges_Archive.txt` | `data/source/wiki/text/Attack_Challenges_Archive.txt` |
| `data/wiki/text/Attack_Challenges_Archive_2022.txt` | `data/source/wiki/text/Attack_Challenges_Archive_2022.txt` |
| `data/wiki/text/Attack_Challenges_Archive_2023.txt` | `data/source/wiki/text/Attack_Challenges_Archive_2023.txt` |
| `data/wiki/text/Attack_Challenges_Archive_Pre-2022.txt` | `data/source/wiki/text/Attack_Challenges_Archive_Pre-2022.txt` |
| `data/wiki/text/Attack_Challenges_Controllable_Heroes_Cookie_Chaos.txt` | `data/source/wiki/text/Attack_Challenges_Controllable_Heroes_Cookie_Chaos.txt` |
| `data/wiki/text/Attack_Challenges_Hero_Campaign_Dragon_Escape.txt` | `data/source/wiki/text/Attack_Challenges_Hero_Campaign_Dragon_Escape.txt` |
| `data/wiki/text/Awesome_Medal_Event.txt` | `data/source/wiki/text/Awesome_Medal_Event.txt` |
| `data/wiki/text/Azure_Dragon.txt` | `data/source/wiki/text/Azure_Dragon.txt` |
| `data/wiki/text/B.O.B_s_Hut.txt` | `data/source/wiki/text/B.O.B_s_Hut.txt` |
| `data/wiki/text/Baby_Dragon.txt` | `data/source/wiki/text/Baby_Dragon.txt` |
| `data/wiki/text/Baby_Dragon_Home_Village.txt` | `data/source/wiki/text/Baby_Dragon_Home_Village.txt` |
| `data/wiki/text/Bag_of_Frostmites.txt` | `data/source/wiki/text/Bag_of_Frostmites.txt` |
| `data/wiki/text/Balloon.txt` | `data/source/wiki/text/Balloon.txt` |
| `data/wiki/text/Barbarian.txt` | `data/source/wiki/text/Barbarian.txt` |
| `data/wiki/text/Barbarian_Home_Village.txt` | `data/source/wiki/text/Barbarian_Home_Village.txt` |
| `data/wiki/text/Barbarian_Kicker.txt` | `data/source/wiki/text/Barbarian_Kicker.txt` |
| `data/wiki/text/Barbarian_King.txt` | `data/source/wiki/text/Barbarian_King.txt` |
| `data/wiki/text/Barbarian_King_Altar.txt` | `data/source/wiki/text/Barbarian_King_Altar.txt` |
| `data/wiki/text/Barbarian_King_Skin_Features.txt` | `data/source/wiki/text/Barbarian_King_Skin_Features.txt` |
| `data/wiki/text/Barbarian_Puppet.txt` | `data/source/wiki/text/Barbarian_Puppet.txt` |
| `data/wiki/text/Barcher.txt` | `data/source/wiki/text/Barcher.txt` |
| `data/wiki/text/Barracks.txt` | `data/source/wiki/text/Barracks.txt` |
| `data/wiki/text/Bat.txt` | `data/source/wiki/text/Bat.txt` |
| `data/wiki/text/Bat_Spell.txt` | `data/source/wiki/text/Bat_Spell.txt` |
| `data/wiki/text/Bat_Spell_Bat.txt` | `data/source/wiki/text/Bat_Spell_Bat.txt` |
| `data/wiki/text/Battle_Blimp.txt` | `data/source/wiki/text/Battle_Blimp.txt` |
| `data/wiki/text/Battle_Copter.txt` | `data/source/wiki/text/Battle_Copter.txt` |
| `data/wiki/text/Battle_Copter_Altar.txt` | `data/source/wiki/text/Battle_Copter_Altar.txt` |
| `data/wiki/text/Battle_Drill.txt` | `data/source/wiki/text/Battle_Drill.txt` |
| `data/wiki/text/Battle_Machine.txt` | `data/source/wiki/text/Battle_Machine.txt` |
| `data/wiki/text/Battle_Machine_Altar.txt` | `data/source/wiki/text/Battle_Machine_Altar.txt` |
| `data/wiki/text/Battle_Ram.txt` | `data/source/wiki/text/Battle_Ram.txt` |
| `data/wiki/text/Battle_Ram_Home_Village.txt` | `data/source/wiki/text/Battle_Ram_Home_Village.txt` |
| `data/wiki/text/Beta_Minion.txt` | `data/source/wiki/text/Beta_Minion.txt` |
| `data/wiki/text/Birthday_Boom.txt` | `data/source/wiki/text/Birthday_Boom.txt` |
| `data/wiki/text/Blacksmith.txt` | `data/source/wiki/text/Blacksmith.txt` |
| `data/wiki/text/Blast_Bow.txt` | `data/source/wiki/text/Blast_Bow.txt` |
| `data/wiki/text/Boat.txt` | `data/source/wiki/text/Boat.txt` |
| `data/wiki/text/Bomb.txt` | `data/source/wiki/text/Bomb.txt` |
| `data/wiki/text/Bomb_Hive.txt` | `data/source/wiki/text/Bomb_Hive.txt` |
| `data/wiki/text/Bomb_Tower.txt` | `data/source/wiki/text/Bomb_Tower.txt` |
| `data/wiki/text/Bomb_Tower_Home_Village.txt` | `data/source/wiki/text/Bomb_Tower_Home_Village.txt` |
| `data/wiki/text/Bomber.txt` | `data/source/wiki/text/Bomber.txt` |
| `data/wiki/text/Bowler.txt` | `data/source/wiki/text/Bowler.txt` |
| `data/wiki/text/Boxer_Giant.txt` | `data/source/wiki/text/Boxer_Giant.txt` |
| `data/wiki/text/Broom_Witch.txt` | `data/source/wiki/text/Broom_Witch.txt` |
| `data/wiki/text/Broom_Witch_Witch_Spirit.txt` | `data/source/wiki/text/Broom_Witch_Witch_Spirit.txt` |
| `data/wiki/text/Builder.txt` | `data/source/wiki/text/Builder.txt` |
| `data/wiki/text/Builder_Battles.txt` | `data/source/wiki/text/Builder_Battles.txt` |
| `data/wiki/text/Builder_s_Apprentice.txt` | `data/source/wiki/text/Builder_s_Apprentice.txt` |
| `data/wiki/text/Builder_s_Hut.txt` | `data/source/wiki/text/Builder_s_Hut.txt` |
| `data/wiki/text/C.O.O.K.I.E.txt` | `data/source/wiki/text/C.O.O.K.I.E.txt` |
| `data/wiki/text/Cake-A-Pult.txt` | `data/source/wiki/text/Cake-A-Pult.txt` |
| `data/wiki/text/Cannon.txt` | `data/source/wiki/text/Cannon.txt` |
| `data/wiki/text/Cannon_Cart.txt` | `data/source/wiki/text/Cannon_Cart.txt` |
| `data/wiki/text/Cannon_Home_Village.txt` | `data/source/wiki/text/Cannon_Home_Village.txt` |
| `data/wiki/text/Chief_s_Journey.txt` | `data/source/wiki/text/Chief_s_Journey.txt` |
| `data/wiki/text/Clan_Badge.txt` | `data/source/wiki/text/Clan_Badge.txt` |
| `data/wiki/text/Clan_Castle.txt` | `data/source/wiki/text/Clan_Castle.txt` |
| `data/wiki/text/Clan_Games.txt` | `data/source/wiki/text/Clan_Games.txt` |
| `data/wiki/text/Clan_Games_Archive.txt` | `data/source/wiki/text/Clan_Games_Archive.txt` |
| `data/wiki/text/Clan_Games_Challenges.txt` | `data/source/wiki/text/Clan_Games_Challenges.txt` |
| `data/wiki/text/Clan_Perks.txt` | `data/source/wiki/text/Clan_Perks.txt` |
| `data/wiki/text/Clan_Rush.txt` | `data/source/wiki/text/Clan_Rush.txt` |
| `data/wiki/text/Clan_War_Leagues.txt` | `data/source/wiki/text/Clan_War_Leagues.txt` |
| `data/wiki/text/Clan_Wars.txt` | `data/source/wiki/text/Clan_Wars.txt` |
| `data/wiki/text/Clans.txt` | `data/source/wiki/text/Clans.txt` |
| `data/wiki/text/Clash_of_Cards.txt` | `data/source/wiki/text/Clash_of_Cards.txt` |
| `data/wiki/text/Clash_of_Clans_Skin_Sets.txt` | `data/source/wiki/text/Clash_of_Clans_Skin_Sets.txt` |
| `data/wiki/text/Clash_with_Haaland.txt` | `data/source/wiki/text/Clash_with_Haaland.txt` |
| `data/wiki/text/Clone_Spell.txt` | `data/source/wiki/text/Clone_Spell.txt` |
| `data/wiki/text/Cookie_Rumble.txt` | `data/source/wiki/text/Cookie_Rumble.txt` |
| `data/wiki/text/Cosmic_Rock.txt` | `data/source/wiki/text/Cosmic_Rock.txt` |
| `data/wiki/text/Crafting_Station.txt` | `data/source/wiki/text/Crafting_Station.txt` |
| `data/wiki/text/Crusher.txt` | `data/source/wiki/text/Crusher.txt` |
| `data/wiki/text/Crusher_Mortar.txt` | `data/source/wiki/text/Crusher_Mortar.txt` |
| `data/wiki/text/Cumulative_Costs.txt` | `data/source/wiki/text/Cumulative_Costs.txt` |
| `data/wiki/text/Cumulative_Costs_Home_Village.txt` | `data/source/wiki/text/Cumulative_Costs_Home_Village.txt` |
| `data/wiki/text/Dark_Barracks.txt` | `data/source/wiki/text/Dark_Barracks.txt` |
| `data/wiki/text/Dark_Crown.txt` | `data/source/wiki/text/Dark_Crown.txt` |
| `data/wiki/text/Dark_Deal.txt` | `data/source/wiki/text/Dark_Deal.txt` |
| `data/wiki/text/Dark_Elixir_Drill.txt` | `data/source/wiki/text/Dark_Elixir_Drill.txt` |
| `data/wiki/text/Dark_Elixir_Storage.txt` | `data/source/wiki/text/Dark_Elixir_Storage.txt` |
| `data/wiki/text/Dark_Elixir_Troops.txt` | `data/source/wiki/text/Dark_Elixir_Troops.txt` |
| `data/wiki/text/Dark_Orb.txt` | `data/source/wiki/text/Dark_Orb.txt` |
| `data/wiki/text/Dark_Spell_Factory.txt` | `data/source/wiki/text/Dark_Spell_Factory.txt` |
| `data/wiki/text/Dark_Spells.txt` | `data/source/wiki/text/Dark_Spells.txt` |
| `data/wiki/text/Debt_Collector.txt` | `data/source/wiki/text/Debt_Collector.txt` |
| `data/wiki/text/Defensive_Buildings_Home_Village.txt` | `data/source/wiki/text/Defensive_Buildings_Home_Village.txt` |
| `data/wiki/text/Diggy.txt` | `data/source/wiki/text/Diggy.txt` |
| `data/wiki/text/Double_Cannon.txt` | `data/source/wiki/text/Double_Cannon.txt` |
| `data/wiki/text/Dragon.txt` | `data/source/wiki/text/Dragon.txt` |
| `data/wiki/text/Dragon_Dash.txt` | `data/source/wiki/text/Dragon_Dash.txt` |
| `data/wiki/text/Dragon_Duke.txt` | `data/source/wiki/text/Dragon_Duke.txt` |
| `data/wiki/text/Dragon_Festival.txt` | `data/source/wiki/text/Dragon_Festival.txt` |
| `data/wiki/text/Dragon_Pinata.txt` | `data/source/wiki/text/Dragon_Pinata.txt` |
| `data/wiki/text/Dragon_Rider.txt` | `data/source/wiki/text/Dragon_Rider.txt` |
| `data/wiki/text/Drop_Ship.txt` | `data/source/wiki/text/Drop_Ship.txt` |
| `data/wiki/text/Drop_Ship_Skeleton.txt` | `data/source/wiki/text/Drop_Ship_Skeleton.txt` |
| `data/wiki/text/Druid.txt` | `data/source/wiki/text/Druid.txt` |
| `data/wiki/text/Druid_Bear.txt` | `data/source/wiki/text/Druid_Bear.txt` |
| `data/wiki/text/Eagle_Artillery.txt` | `data/source/wiki/text/Eagle_Artillery.txt` |
| `data/wiki/text/Earthquake_Boots.txt` | `data/source/wiki/text/Earthquake_Boots.txt` |
| `data/wiki/text/Earthquake_Spell.txt` | `data/source/wiki/text/Earthquake_Spell.txt` |
| `data/wiki/text/El_Primo.txt` | `data/source/wiki/text/El_Primo.txt` |
| `data/wiki/text/Electro_Boots.txt` | `data/source/wiki/text/Electro_Boots.txt` |
| `data/wiki/text/Electro_Dragon.txt` | `data/source/wiki/text/Electro_Dragon.txt` |
| `data/wiki/text/Electro_Fangs.txt` | `data/source/wiki/text/Electro_Fangs.txt` |
| `data/wiki/text/Electro_Owl.txt` | `data/source/wiki/text/Electro_Owl.txt` |
| `data/wiki/text/Electro_Titan.txt` | `data/source/wiki/text/Electro_Titan.txt` |
| `data/wiki/text/Electrofire_Wizard.txt` | `data/source/wiki/text/Electrofire_Wizard.txt` |
| `data/wiki/text/Elephant_Rider.txt` | `data/source/wiki/text/Elephant_Rider.txt` |
| `data/wiki/text/Elephant_Rider_Elephant.txt` | `data/source/wiki/text/Elephant_Rider_Elephant.txt` |
| `data/wiki/text/Elephant_Rider_Rider.txt` | `data/source/wiki/text/Elephant_Rider_Rider.txt` |
| `data/wiki/text/Elixir_Collector_Home_Village.txt` | `data/source/wiki/text/Elixir_Collector_Home_Village.txt` |
| `data/wiki/text/Elixir_Spells.txt` | `data/source/wiki/text/Elixir_Spells.txt` |
| `data/wiki/text/Elixir_Storage.txt` | `data/source/wiki/text/Elixir_Storage.txt` |
| `data/wiki/text/Elixir_Storage_Home_Village.txt` | `data/source/wiki/text/Elixir_Storage_Home_Village.txt` |
| `data/wiki/text/Elixir_Troops.txt` | `data/source/wiki/text/Elixir_Troops.txt` |
| `data/wiki/text/Endless_Haste_Spell.txt` | `data/source/wiki/text/Endless_Haste_Spell.txt` |
| `data/wiki/text/Equipment_Blast.txt` | `data/source/wiki/text/Equipment_Blast.txt` |
| `data/wiki/text/Eternal_Tome.txt` | `data/source/wiki/text/Eternal_Tome.txt` |
| `data/wiki/text/Events.txt` | `data/source/wiki/text/Events.txt` |
| `data/wiki/text/Experience.txt` | `data/source/wiki/text/Experience.txt` |
| `data/wiki/text/Fancy_Shop.txt` | `data/source/wiki/text/Fancy_Shop.txt` |
| `data/wiki/text/Fire_Heart.txt` | `data/source/wiki/text/Fire_Heart.txt` |
| `data/wiki/text/Fireball.txt` | `data/source/wiki/text/Fireball.txt` |
| `data/wiki/text/Firecracker.txt` | `data/source/wiki/text/Firecracker.txt` |
| `data/wiki/text/Firecrackers.txt` | `data/source/wiki/text/Firecrackers.txt` |
| `data/wiki/text/Firespitter.txt` | `data/source/wiki/text/Firespitter.txt` |
| `data/wiki/text/Flame_Blower.txt` | `data/source/wiki/text/Flame_Blower.txt` |
| `data/wiki/text/Flame_Flinger.txt` | `data/source/wiki/text/Flame_Flinger.txt` |
| `data/wiki/text/Flame_Spinner.txt` | `data/source/wiki/text/Flame_Spinner.txt` |
| `data/wiki/text/Flying_Fortress.txt` | `data/source/wiki/text/Flying_Fortress.txt` |
| `data/wiki/text/Flying_Fortress_Skeleton_Glider.txt` | `data/source/wiki/text/Flying_Fortress_Skeleton_Glider.txt` |
| `data/wiki/text/Football_Camp.txt` | `data/source/wiki/text/Football_Camp.txt` |
| `data/wiki/text/Forge.txt` | `data/source/wiki/text/Forge.txt` |
| `data/wiki/text/Freeze_Spell.txt` | `data/source/wiki/text/Freeze_Spell.txt` |
| `data/wiki/text/Freeze_Trap.txt` | `data/source/wiki/text/Freeze_Trap.txt` |
| `data/wiki/text/Friend_or_Foe.txt` | `data/source/wiki/text/Friend_or_Foe.txt` |
| `data/wiki/text/Frost_Flake.txt` | `data/source/wiki/text/Frost_Flake.txt` |
| `data/wiki/text/Frost_Spell.txt` | `data/source/wiki/text/Frost_Spell.txt` |
| `data/wiki/text/Frosty.txt` | `data/source/wiki/text/Frosty.txt` |
| `data/wiki/text/Frosty_Frostmite.txt` | `data/source/wiki/text/Frosty_Frostmite.txt` |
| `data/wiki/text/Frozen_Arrow.txt` | `data/source/wiki/text/Frozen_Arrow.txt` |
| `data/wiki/text/Furnace.txt` | `data/source/wiki/text/Furnace.txt` |
| `data/wiki/text/Furnace_Firemite.txt` | `data/source/wiki/text/Furnace_Firemite.txt` |
| `data/wiki/text/Game_Tips.txt` | `data/source/wiki/text/Game_Tips.txt` |
| `data/wiki/text/Gems.txt` | `data/source/wiki/text/Gems.txt` |
| `data/wiki/text/Giant.txt` | `data/source/wiki/text/Giant.txt` |
| `data/wiki/text/Giant_Arrow.txt` | `data/source/wiki/text/Giant_Arrow.txt` |
| `data/wiki/text/Giant_Bomb.txt` | `data/source/wiki/text/Giant_Bomb.txt` |
| `data/wiki/text/Giant_Cannon.txt` | `data/source/wiki/text/Giant_Cannon.txt` |
| `data/wiki/text/Giant_Gauntlet.txt` | `data/source/wiki/text/Giant_Gauntlet.txt` |
| `data/wiki/text/Giant_Giant.txt` | `data/source/wiki/text/Giant_Giant.txt` |
| `data/wiki/text/Giant_Skeleton.txt` | `data/source/wiki/text/Giant_Skeleton.txt` |
| `data/wiki/text/Giant_Thrower.txt` | `data/source/wiki/text/Giant_Thrower.txt` |
| `data/wiki/text/Giga_Bomb.txt` | `data/source/wiki/text/Giga_Bomb.txt` |
| `data/wiki/text/Gingerbread_Bakery.txt` | `data/source/wiki/text/Gingerbread_Bakery.txt` |
| `data/wiki/text/Glossary.txt` | `data/source/wiki/text/Glossary.txt` |
| `data/wiki/text/Goblin.txt` | `data/source/wiki/text/Goblin.txt` |
| `data/wiki/text/Goblin_Thrower.txt` | `data/source/wiki/text/Goblin_Thrower.txt` |
| `data/wiki/text/Goblin_Workers.txt` | `data/source/wiki/text/Goblin_Workers.txt` |
| `data/wiki/text/Gold_Mine_Home_Village.txt` | `data/source/wiki/text/Gold_Mine_Home_Village.txt` |
| `data/wiki/text/Gold_Rush.txt` | `data/source/wiki/text/Gold_Rush.txt` |
| `data/wiki/text/Gold_Storage.txt` | `data/source/wiki/text/Gold_Storage.txt` |
| `data/wiki/text/Gold_Storage_Home_Village.txt` | `data/source/wiki/text/Gold_Storage_Home_Village.txt` |
| `data/wiki/text/Golden_Dragon.txt` | `data/source/wiki/text/Golden_Dragon.txt` |
| `data/wiki/text/Golem.txt` | `data/source/wiki/text/Golem.txt` |
| `data/wiki/text/Golem_Golemite.txt` | `data/source/wiki/text/Golem_Golemite.txt` |
| `data/wiki/text/Grand_Warden.txt` | `data/source/wiki/text/Grand_Warden.txt` |
| `data/wiki/text/Grand_Warden_Altar.txt` | `data/source/wiki/text/Grand_Warden_Altar.txt` |
| `data/wiki/text/Grand_Warden_Skin_Features.txt` | `data/source/wiki/text/Grand_Warden_Skin_Features.txt` |
| `data/wiki/text/Graveyard_Spell.txt` | `data/source/wiki/text/Graveyard_Spell.txt` |
| `data/wiki/text/Greedy_Raven.txt` | `data/source/wiki/text/Greedy_Raven.txt` |
| `data/wiki/text/Guard.txt` | `data/source/wiki/text/Guard.txt` |
| `data/wiki/text/Guard_Post.txt` | `data/source/wiki/text/Guard_Post.txt` |
| `data/wiki/text/Hall_of_Fame.txt` | `data/source/wiki/text/Hall_of_Fame.txt` |
| `data/wiki/text/Haste_Spell.txt` | `data/source/wiki/text/Haste_Spell.txt` |
| `data/wiki/text/Haste_Vial.txt` | `data/source/wiki/text/Haste_Vial.txt` |
| `data/wiki/text/Headhunter.txt` | `data/source/wiki/text/Headhunter.txt` |
| `data/wiki/text/Healer.txt` | `data/source/wiki/text/Healer.txt` |
| `data/wiki/text/Healer_Puppet.txt` | `data/source/wiki/text/Healer_Puppet.txt` |
| `data/wiki/text/Healing_Spell.txt` | `data/source/wiki/text/Healing_Spell.txt` |
| `data/wiki/text/Healing_Spell_Home_Village.txt` | `data/source/wiki/text/Healing_Spell_Home_Village.txt` |
| `data/wiki/text/Healing_Tome.txt` | `data/source/wiki/text/Healing_Tome.txt` |
| `data/wiki/text/Helper_Hut.txt` | `data/source/wiki/text/Helper_Hut.txt` |
| `data/wiki/text/Henchmen_Puppet.txt` | `data/source/wiki/text/Henchmen_Puppet.txt` |
| `data/wiki/text/Henchmen_Puppet_Henchmen.txt` | `data/source/wiki/text/Henchmen_Puppet_Henchmen.txt` |
| `data/wiki/text/Hero_Banner.txt` | `data/source/wiki/text/Hero_Banner.txt` |
| `data/wiki/text/Hero_Bell.txt` | `data/source/wiki/text/Hero_Bell.txt` |
| `data/wiki/text/Hero_Equipment.txt` | `data/source/wiki/text/Hero_Equipment.txt` |
| `data/wiki/text/Hero_Hall.txt` | `data/source/wiki/text/Hero_Hall.txt` |
| `data/wiki/text/Hero_Hunter.txt` | `data/source/wiki/text/Hero_Hunter.txt` |
| `data/wiki/text/Hero_Rush.txt` | `data/source/wiki/text/Hero_Rush.txt` |
| `data/wiki/text/Hero_s_Journey.txt` | `data/source/wiki/text/Hero_s_Journey.txt` |
| `data/wiki/text/Heroes.txt` | `data/source/wiki/text/Heroes.txt` |
| `data/wiki/text/Heroic_Torch.txt` | `data/source/wiki/text/Heroic_Torch.txt` |
| `data/wiki/text/Hidden_Mega_Tesla.txt` | `data/source/wiki/text/Hidden_Mega_Tesla.txt` |
| `data/wiki/text/Hidden_Tesla_Home_Village.txt` | `data/source/wiki/text/Hidden_Tesla_Home_Village.txt` |
| `data/wiki/text/Hog_Glider.txt` | `data/source/wiki/text/Hog_Glider.txt` |
| `data/wiki/text/Hog_Raiders.txt` | `data/source/wiki/text/Hog_Raiders.txt` |
| `data/wiki/text/Hog_Rider.txt` | `data/source/wiki/text/Hog_Rider.txt` |
| `data/wiki/text/Hog_Rider_Puppet.txt` | `data/source/wiki/text/Hog_Rider_Puppet.txt` |
| `data/wiki/text/Hog_Wizard.txt` | `data/source/wiki/text/Hog_Wizard.txt` |
| `data/wiki/text/Hook_Tower.txt` | `data/source/wiki/text/Hook_Tower.txt` |
| `data/wiki/text/Hot_Candle.txt` | `data/source/wiki/text/Hot_Candle.txt` |
| `data/wiki/text/Hydra_Headstone.txt` | `data/source/wiki/text/Hydra_Headstone.txt` |
| `data/wiki/text/Ice_Block_Spell.txt` | `data/source/wiki/text/Ice_Block_Spell.txt` |
| `data/wiki/text/Ice_Golem.txt` | `data/source/wiki/text/Ice_Golem.txt` |
| `data/wiki/text/Ice_Hound.txt` | `data/source/wiki/text/Ice_Hound.txt` |
| `data/wiki/text/Ice_Hound_Ice_Pup.txt` | `data/source/wiki/text/Ice_Hound_Ice_Pup.txt` |
| `data/wiki/text/Ice_Minion.txt` | `data/source/wiki/text/Ice_Minion.txt` |
| `data/wiki/text/Ice_Wizard.txt` | `data/source/wiki/text/Ice_Wizard.txt` |
| `data/wiki/text/In-App_Purchases.txt` | `data/source/wiki/text/In-App_Purchases.txt` |
| `data/wiki/text/Individual_Costs.txt` | `data/source/wiki/text/Individual_Costs.txt` |
| `data/wiki/text/Individual_Costs_Home_Village.txt` | `data/source/wiki/text/Individual_Costs_Home_Village.txt` |
| `data/wiki/text/Inferno_Dragon.txt` | `data/source/wiki/text/Inferno_Dragon.txt` |
| `data/wiki/text/Inferno_Dragon_Home_Village.txt` | `data/source/wiki/text/Inferno_Dragon_Home_Village.txt` |
| `data/wiki/text/Inferno_Tower.txt` | `data/source/wiki/text/Inferno_Tower.txt` |
| `data/wiki/text/Inferno_Tower_Home_Village.txt` | `data/source/wiki/text/Inferno_Tower_Home_Village.txt` |
| `data/wiki/text/Invisibility_Spell.txt` | `data/source/wiki/text/Invisibility_Spell.txt` |
| `data/wiki/text/Invisibility_Vial.txt` | `data/source/wiki/text/Invisibility_Vial.txt` |
| `data/wiki/text/Jump_Spell.txt` | `data/source/wiki/text/Jump_Spell.txt` |
| `data/wiki/text/Jump_Spell_Home_Village.txt` | `data/source/wiki/text/Jump_Spell_Home_Village.txt` |
| `data/wiki/text/K.A.N.E.txt` | `data/source/wiki/text/K.A.N.E.txt` |
| `data/wiki/text/L.A.S.S.I.txt` | `data/source/wiki/text/L.A.S.S.I.txt` |
| `data/wiki/text/Lab_Assistant.txt` | `data/source/wiki/text/Lab_Assistant.txt` |
| `data/wiki/text/Laboratory.txt` | `data/source/wiki/text/Laboratory.txt` |
| `data/wiki/text/Lava_Hound.txt` | `data/source/wiki/text/Lava_Hound.txt` |
| `data/wiki/text/Lava_Hound_Lava_Pup.txt` | `data/source/wiki/text/Lava_Hound_Lava_Pup.txt` |
| `data/wiki/text/Lava_Launcher.txt` | `data/source/wiki/text/Lava_Launcher.txt` |
| `data/wiki/text/Lava_Launcher_Home_Village.txt` | `data/source/wiki/text/Lava_Launcher_Home_Village.txt` |
| `data/wiki/text/Lavaloon.txt` | `data/source/wiki/text/Lavaloon.txt` |
| `data/wiki/text/Lavaloon_Lavaloon_Pup.txt` | `data/source/wiki/text/Lavaloon_Lavaloon_Pup.txt` |
| `data/wiki/text/Lavaloon_Puppet.txt` | `data/source/wiki/text/Lavaloon_Puppet.txt` |
| `data/wiki/text/Lavaloon_Puppet_Lavaloon.txt` | `data/source/wiki/text/Lavaloon_Puppet_Lavaloon.txt` |
| `data/wiki/text/Layouts_Home_Village.txt` | `data/source/wiki/text/Layouts_Home_Village.txt` |
| `data/wiki/text/Life_Gem.txt` | `data/source/wiki/text/Life_Gem.txt` |
| `data/wiki/text/Light_Beam.txt` | `data/source/wiki/text/Light_Beam.txt` |
| `data/wiki/text/Lightning_Spell.txt` | `data/source/wiki/text/Lightning_Spell.txt` |
| `data/wiki/text/Lightning_Spell_Home_Village.txt` | `data/source/wiki/text/Lightning_Spell_Home_Village.txt` |
| `data/wiki/text/Loading_Screen_Hints.txt` | `data/source/wiki/text/Loading_Screen_Hints.txt` |
| `data/wiki/text/Loading_Screens.txt` | `data/source/wiki/text/Loading_Screens.txt` |
| `data/wiki/text/Log_Launcher.txt` | `data/source/wiki/text/Log_Launcher.txt` |
| `data/wiki/text/Log_Trap.txt` | `data/source/wiki/text/Log_Trap.txt` |
| `data/wiki/text/Logger.txt` | `data/source/wiki/text/Logger.txt` |
| `data/wiki/text/Longshot.txt` | `data/source/wiki/text/Longshot.txt` |
| `data/wiki/text/Loot_Cart.txt` | `data/source/wiki/text/Loot_Cart.txt` |
| `data/wiki/text/M.E.C.H.A.txt` | `data/source/wiki/text/M.E.C.H.A.txt` |
| `data/wiki/text/Magic_Items.txt` | `data/source/wiki/text/Magic_Items.txt` |
| `data/wiki/text/Magic_Items_List.txt` | `data/source/wiki/text/Magic_Items_List.txt` |
| `data/wiki/text/Magic_Mirror.txt` | `data/source/wiki/text/Magic_Mirror.txt` |
| `data/wiki/text/Magic_Snacks.txt` | `data/source/wiki/text/Magic_Snacks.txt` |
| `data/wiki/text/Mashup_Madness.txt` | `data/source/wiki/text/Mashup_Madness.txt` |
| `data/wiki/text/Mashup_Mania.txt` | `data/source/wiki/text/Mashup_Mania.txt` |
| `data/wiki/text/Master_Builder_s_Boat.txt` | `data/source/wiki/text/Master_Builder_s_Boat.txt` |
| `data/wiki/text/Master_Builder_s_Hut.txt` | `data/source/wiki/text/Master_Builder_s_Hut.txt` |
| `data/wiki/text/Mega_Mine.txt` | `data/source/wiki/text/Mega_Mine.txt` |
| `data/wiki/text/Mega_Sparky.txt` | `data/source/wiki/text/Mega_Sparky.txt` |
| `data/wiki/text/Mega_Tesla.txt` | `data/source/wiki/text/Mega_Tesla.txt` |
| `data/wiki/text/Meltdown_Mayhem.txt` | `data/source/wiki/text/Meltdown_Mayhem.txt` |
| `data/wiki/text/Metal_Pants.txt` | `data/source/wiki/text/Metal_Pants.txt` |
| `data/wiki/text/Meteor_Golem.txt` | `data/source/wiki/text/Meteor_Golem.txt` |
| `data/wiki/text/Meteor_Golem_Meteormite.txt` | `data/source/wiki/text/Meteor_Golem_Meteormite.txt` |
| `data/wiki/text/Meteor_Staff.txt` | `data/source/wiki/text/Meteor_Staff.txt` |
| `data/wiki/text/Mighty_Yak.txt` | `data/source/wiki/text/Mighty_Yak.txt` |
| `data/wiki/text/Mine.txt` | `data/source/wiki/text/Mine.txt` |
| `data/wiki/text/Miner.txt` | `data/source/wiki/text/Miner.txt` |
| `data/wiki/text/Mini-Minion_Hive.txt` | `data/source/wiki/text/Mini-Minion_Hive.txt` |
| `data/wiki/text/Minion.txt` | `data/source/wiki/text/Minion.txt` |
| `data/wiki/text/Minion_Horde.txt` | `data/source/wiki/text/Minion_Horde.txt` |
| `data/wiki/text/Minion_Prince.txt` | `data/source/wiki/text/Minion_Prince.txt` |
| `data/wiki/text/Money_in_the_Bank_Rush.txt` | `data/source/wiki/text/Money_in_the_Bank_Rush.txt` |
| `data/wiki/text/Monolith.txt` | `data/source/wiki/text/Monolith.txt` |
| `data/wiki/text/Monolith_Arrow.txt` | `data/source/wiki/text/Monolith_Arrow.txt` |
| `data/wiki/text/Mortar.txt` | `data/source/wiki/text/Mortar.txt` |
| `data/wiki/text/Mountain_Golem.txt` | `data/source/wiki/text/Mountain_Golem.txt` |
| `data/wiki/text/Multi-Archer_Tower.txt` | `data/source/wiki/text/Multi-Archer_Tower.txt` |
| `data/wiki/text/Multi-Gear_Tower.txt` | `data/source/wiki/text/Multi-Gear_Tower.txt` |
| `data/wiki/text/Multi_Cannon.txt` | `data/source/wiki/text/Multi_Cannon.txt` |
| `data/wiki/text/Multi_Mortar.txt` | `data/source/wiki/text/Multi_Mortar.txt` |
| `data/wiki/text/Multiplayer_Battles.txt` | `data/source/wiki/text/Multiplayer_Battles.txt` |
| `data/wiki/text/Night_Witch.txt` | `data/source/wiki/text/Night_Witch.txt` |
| `data/wiki/text/Night_Witch_Bat.txt` | `data/source/wiki/text/Night_Witch_Bat.txt` |
| `data/wiki/text/Noble_Iron.txt` | `data/source/wiki/text/Noble_Iron.txt` |
| `data/wiki/text/O.T.T.O_s_Outpost.txt` | `data/source/wiki/text/O.T.T.O_s_Outpost.txt` |
| `data/wiki/text/Ores.txt` | `data/source/wiki/text/Ores.txt` |
| `data/wiki/text/Other_Buildings_Home_Village.txt` | `data/source/wiki/text/Other_Buildings_Home_Village.txt` |
| `data/wiki/text/Overgrowth_Spell.txt` | `data/source/wiki/text/Overgrowth_Spell.txt` |
| `data/wiki/text/P.E.K.K.A.txt` | `data/source/wiki/text/P.E.K.K.A.txt` |
| `data/wiki/text/Party_Wizard.txt` | `data/source/wiki/text/Party_Wizard.txt` |
| `data/wiki/text/Pet_House.txt` | `data/source/wiki/text/Pet_House.txt` |
| `data/wiki/text/Pets.txt` | `data/source/wiki/text/Pets.txt` |
| `data/wiki/text/Phoenix.txt` | `data/source/wiki/text/Phoenix.txt` |
| `data/wiki/text/Player_Profile.txt` | `data/source/wiki/text/Player_Profile.txt` |
| `data/wiki/text/Poison_Lizard.txt` | `data/source/wiki/text/Poison_Lizard.txt` |
| `data/wiki/text/Poison_Spell.txt` | `data/source/wiki/text/Poison_Spell.txt` |
| `data/wiki/text/Portal_Panic.txt` | `data/source/wiki/text/Portal_Panic.txt` |
| `data/wiki/text/Portal_Pendant.txt` | `data/source/wiki/text/Portal_Pendant.txt` |
| `data/wiki/text/Power_P.E.K.K.A.txt` | `data/source/wiki/text/Power_P.E.K.K.A.txt` |
| `data/wiki/text/Practice_Mode.txt` | `data/source/wiki/text/Practice_Mode.txt` |
| `data/wiki/text/Prospector.txt` | `data/source/wiki/text/Prospector.txt` |
| `data/wiki/text/Pumpkin_Barbarian.txt` | `data/source/wiki/text/Pumpkin_Barbarian.txt` |
| `data/wiki/text/Pumpkin_Bomb.txt` | `data/source/wiki/text/Pumpkin_Bomb.txt` |
| `data/wiki/text/Push_Trap.txt` | `data/source/wiki/text/Push_Trap.txt` |
| `data/wiki/text/Rage_Gem.txt` | `data/source/wiki/text/Rage_Gem.txt` |
| `data/wiki/text/Rage_Spell.txt` | `data/source/wiki/text/Rage_Spell.txt` |
| `data/wiki/text/Rage_Spell_Home_Village.txt` | `data/source/wiki/text/Rage_Spell_Home_Village.txt` |
| `data/wiki/text/Rage_Vial.txt` | `data/source/wiki/text/Rage_Vial.txt` |
| `data/wiki/text/Raged_Barbarian.txt` | `data/source/wiki/text/Raged_Barbarian.txt` |
| `data/wiki/text/Raid_Cart.txt` | `data/source/wiki/text/Raid_Cart.txt` |
| `data/wiki/text/Raid_Cart_Post.txt` | `data/source/wiki/text/Raid_Cart_Post.txt` |
| `data/wiki/text/Raid_Weekends.txt` | `data/source/wiki/text/Raid_Weekends.txt` |
| `data/wiki/text/Ram_Rider.txt` | `data/source/wiki/text/Ram_Rider.txt` |
| `data/wiki/text/Ranked_Battles.txt` | `data/source/wiki/text/Ranked_Battles.txt` |
| `data/wiki/text/Rapid_Rockets.txt` | `data/source/wiki/text/Rapid_Rockets.txt` |
| `data/wiki/text/Recall_Spell.txt` | `data/source/wiki/text/Recall_Spell.txt` |
| `data/wiki/text/Reflector.txt` | `data/source/wiki/text/Reflector.txt` |
| `data/wiki/text/Removed_features.txt` | `data/source/wiki/text/Removed_features.txt` |
| `data/wiki/text/Resource_Buildings_Home_Village.txt` | `data/source/wiki/text/Resource_Buildings_Home_Village.txt` |
| `data/wiki/text/Revenge_Deck.txt` | `data/source/wiki/text/Revenge_Deck.txt` |
| `data/wiki/text/Revenge_Tower.txt` | `data/source/wiki/text/Revenge_Tower.txt` |
| `data/wiki/text/Revive_Spell.txt` | `data/source/wiki/text/Revive_Spell.txt` |
| `data/wiki/text/Ricochet_Cannon.txt` | `data/source/wiki/text/Ricochet_Cannon.txt` |
| `data/wiki/text/Roaster.txt` | `data/source/wiki/text/Roaster.txt` |
| `data/wiki/text/Roaster_Home_Village.txt` | `data/source/wiki/text/Roaster_Home_Village.txt` |
| `data/wiki/text/Rocket_Artillery.txt` | `data/source/wiki/text/Rocket_Artillery.txt` |
| `data/wiki/text/Rocket_Backpack.txt` | `data/source/wiki/text/Rocket_Backpack.txt` |
| `data/wiki/text/Rocket_Balloon.txt` | `data/source/wiki/text/Rocket_Balloon.txt` |
| `data/wiki/text/Rocket_Balloon_Home_Village.txt` | `data/source/wiki/text/Rocket_Balloon_Home_Village.txt` |
| `data/wiki/text/Rocket_Spear.txt` | `data/source/wiki/text/Rocket_Spear.txt` |
| `data/wiki/text/Rocking_Reindeer.txt` | `data/source/wiki/text/Rocking_Reindeer.txt` |
| `data/wiki/text/Root_Rider.txt` | `data/source/wiki/text/Root_Rider.txt` |
| `data/wiki/text/Royal_Champion.txt` | `data/source/wiki/text/Royal_Champion.txt` |
| `data/wiki/text/Royal_Champion_Altar.txt` | `data/source/wiki/text/Royal_Champion_Altar.txt` |
| `data/wiki/text/Royal_Champion_Skin_Features.txt` | `data/source/wiki/text/Royal_Champion_Skin_Features.txt` |
| `data/wiki/text/Royal_Gem.txt` | `data/source/wiki/text/Royal_Gem.txt` |
| `data/wiki/text/Royal_Ghost.txt` | `data/source/wiki/text/Royal_Ghost.txt` |
| `data/wiki/text/Ruin_Witch.txt` | `data/source/wiki/text/Ruin_Witch.txt` |
| `data/wiki/text/Ruin_Witch_Ruin_Knight.txt` | `data/source/wiki/text/Ruin_Witch_Ruin_Knight.txt` |
| `data/wiki/text/Rumbling_Goblins.txt` | `data/source/wiki/text/Rumbling_Goblins.txt` |
| `data/wiki/text/Santa_Strike.txt` | `data/source/wiki/text/Santa_Strike.txt` |
| `data/wiki/text/Santa_s_Surprise.txt` | `data/source/wiki/text/Santa_s_Surprise.txt` |
| `data/wiki/text/Scattershot.txt` | `data/source/wiki/text/Scattershot.txt` |
| `data/wiki/text/Season_Challenges.txt` | `data/source/wiki/text/Season_Challenges.txt` |
| `data/wiki/text/Season_Challenges_Archive.txt` | `data/source/wiki/text/Season_Challenges_Archive.txt` |
| `data/wiki/text/Season_Challenges_Archive_2019.txt` | `data/source/wiki/text/Season_Challenges_Archive_2019.txt` |
| `data/wiki/text/Season_Challenges_Archive_2020.txt` | `data/source/wiki/text/Season_Challenges_Archive_2020.txt` |
| `data/wiki/text/Season_Challenges_Archive_2021.txt` | `data/source/wiki/text/Season_Challenges_Archive_2021.txt` |
| `data/wiki/text/Season_Challenges_Archive_2022.txt` | `data/source/wiki/text/Season_Challenges_Archive_2022.txt` |
| `data/wiki/text/Season_Challenges_Archive_2023.txt` | `data/source/wiki/text/Season_Challenges_Archive_2023.txt` |
| `data/wiki/text/Season_Challenges_List.txt` | `data/source/wiki/text/Season_Challenges_List.txt` |
| `data/wiki/text/Seeking_Air_Mine.txt` | `data/source/wiki/text/Seeking_Air_Mine.txt` |
| `data/wiki/text/Seeking_Shield.txt` | `data/source/wiki/text/Seeking_Shield.txt` |
| `data/wiki/text/Shield.txt` | `data/source/wiki/text/Shield.txt` |
| `data/wiki/text/Shrink_Trap.txt` | `data/source/wiki/text/Shrink_Trap.txt` |
| `data/wiki/text/Siege_Barracks.txt` | `data/source/wiki/text/Siege_Barracks.txt` |
| `data/wiki/text/Siege_Machines.txt` | `data/source/wiki/text/Siege_Machines.txt` |
| `data/wiki/text/Single_Player_Campaign.txt` | `data/source/wiki/text/Single_Player_Campaign.txt` |
| `data/wiki/text/Skeleton.txt` | `data/source/wiki/text/Skeleton.txt` |
| `data/wiki/text/Skeleton_Barrel.txt` | `data/source/wiki/text/Skeleton_Barrel.txt` |
| `data/wiki/text/Skeleton_Barrel_Home_Village.txt` | `data/source/wiki/text/Skeleton_Barrel_Home_Village.txt` |
| `data/wiki/text/Skeleton_Spell.txt` | `data/source/wiki/text/Skeleton_Spell.txt` |
| `data/wiki/text/Skeleton_Spell_Skeleton.txt` | `data/source/wiki/text/Skeleton_Spell_Skeleton.txt` |
| `data/wiki/text/Skeleton_Trap.txt` | `data/source/wiki/text/Skeleton_Trap.txt` |
| `data/wiki/text/Sky_Wagon.txt` | `data/source/wiki/text/Sky_Wagon.txt` |
| `data/wiki/text/Smasher.txt` | `data/source/wiki/text/Smasher.txt` |
| `data/wiki/text/Snake.txt` | `data/source/wiki/text/Snake.txt` |
| `data/wiki/text/Snake_Barrel.txt` | `data/source/wiki/text/Snake_Barrel.txt` |
| `data/wiki/text/Snake_Barrel_Snake.txt` | `data/source/wiki/text/Snake_Barrel_Snake.txt` |
| `data/wiki/text/Snake_Bracelet.txt` | `data/source/wiki/text/Snake_Bracelet.txt` |
| `data/wiki/text/Snake_Bracelet_Snake.txt` | `data/source/wiki/text/Snake_Bracelet_Snake.txt` |
| `data/wiki/text/Snake_Festival.txt` | `data/source/wiki/text/Snake_Festival.txt` |
| `data/wiki/text/Snake_Shrine.txt` | `data/source/wiki/text/Snake_Shrine.txt` |
| `data/wiki/text/Sneak_Peeks.txt` | `data/source/wiki/text/Sneak_Peeks.txt` |
| `data/wiki/text/Sneaky_Archer.txt` | `data/source/wiki/text/Sneaky_Archer.txt` |
| `data/wiki/text/Sneaky_Goblin.txt` | `data/source/wiki/text/Sneaky_Goblin.txt` |
| `data/wiki/text/Sneezy.txt` | `data/source/wiki/text/Sneezy.txt` |
| `data/wiki/text/Sneezy_Booger.txt` | `data/source/wiki/text/Sneezy_Booger.txt` |
| `data/wiki/text/Sound_of_Clash.txt` | `data/source/wiki/text/Sound_of_Clash.txt` |
| `data/wiki/text/Soundtrack.txt` | `data/source/wiki/text/Soundtrack.txt` |
| `data/wiki/text/Sour_Elixir_Cauldron.txt` | `data/source/wiki/text/Sour_Elixir_Cauldron.txt` |
| `data/wiki/text/Spear_Thrower.txt` | `data/source/wiki/text/Spear_Thrower.txt` |
| `data/wiki/text/Spear_Trap.txt` | `data/source/wiki/text/Spear_Trap.txt` |
| `data/wiki/text/Spell_Factory.txt` | `data/source/wiki/text/Spell_Factory.txt` |
| `data/wiki/text/Spell_Tower.txt` | `data/source/wiki/text/Spell_Tower.txt` |
| `data/wiki/text/Spells.txt` | `data/source/wiki/text/Spells.txt` |
| `data/wiki/text/Spiky_Ball.txt` | `data/source/wiki/text/Spiky_Ball.txt` |
| `data/wiki/text/Spirit_Fox.txt` | `data/source/wiki/text/Spirit_Fox.txt` |
| `data/wiki/text/Spring_Trap_Home_Village.txt` | `data/source/wiki/text/Spring_Trap_Home_Village.txt` |
| `data/wiki/text/Star_Bonus.txt` | `data/source/wiki/text/Star_Bonus.txt` |
| `data/wiki/text/Starter_Challenges.txt` | `data/source/wiki/text/Starter_Challenges.txt` |
| `data/wiki/text/Stick_Horse.txt` | `data/source/wiki/text/Stick_Horse.txt` |
| `data/wiki/text/Stone_Slammer.txt` | `data/source/wiki/text/Stone_Slammer.txt` |
| `data/wiki/text/Streak_Event.txt` | `data/source/wiki/text/Streak_Event.txt` |
| `data/wiki/text/Strongman_s_Caravan.txt` | `data/source/wiki/text/Strongman_s_Caravan.txt` |
| `data/wiki/text/Stun_Blaster.txt` | `data/source/wiki/text/Stun_Blaster.txt` |
| `data/wiki/text/Suggested_Updates.txt` | `data/source/wiki/text/Suggested_Updates.txt` |
| `data/wiki/text/Super_Archer.txt` | `data/source/wiki/text/Super_Archer.txt` |
| `data/wiki/text/Super_Barbarian.txt` | `data/source/wiki/text/Super_Barbarian.txt` |
| `data/wiki/text/Super_Barbarian_Home_Village.txt` | `data/source/wiki/text/Super_Barbarian_Home_Village.txt` |
| `data/wiki/text/Super_Bowler.txt` | `data/source/wiki/text/Super_Bowler.txt` |
| `data/wiki/text/Super_Dragon.txt` | `data/source/wiki/text/Super_Dragon.txt` |
| `data/wiki/text/Super_Dragon_Home_Village.txt` | `data/source/wiki/text/Super_Dragon_Home_Village.txt` |
| `data/wiki/text/Super_Dragon_Post.txt` | `data/source/wiki/text/Super_Dragon_Post.txt` |
| `data/wiki/text/Super_Giant.txt` | `data/source/wiki/text/Super_Giant.txt` |
| `data/wiki/text/Super_Giant_Home_Village.txt` | `data/source/wiki/text/Super_Giant_Home_Village.txt` |
| `data/wiki/text/Super_Giant_Post.txt` | `data/source/wiki/text/Super_Giant_Post.txt` |
| `data/wiki/text/Super_Hog_Rider.txt` | `data/source/wiki/text/Super_Hog_Rider.txt` |
| `data/wiki/text/Super_Hog_Rider_Super_Hog.txt` | `data/source/wiki/text/Super_Hog_Rider_Super_Hog.txt` |
| `data/wiki/text/Super_Hog_Rider_Super_Rider.txt` | `data/source/wiki/text/Super_Hog_Rider_Super_Rider.txt` |
| `data/wiki/text/Super_Ice_Bath.txt` | `data/source/wiki/text/Super_Ice_Bath.txt` |
| `data/wiki/text/Super_Miner.txt` | `data/source/wiki/text/Super_Miner.txt` |
| `data/wiki/text/Super_Miner_Home_Village.txt` | `data/source/wiki/text/Super_Miner_Home_Village.txt` |
| `data/wiki/text/Super_Minion.txt` | `data/source/wiki/text/Super_Minion.txt` |
| `data/wiki/text/Super_Troop_Spotlight.txt` | `data/source/wiki/text/Super_Troop_Spotlight.txt` |
| `data/wiki/text/Super_Troops.txt` | `data/source/wiki/text/Super_Troops.txt` |
| `data/wiki/text/Super_Valkyrie.txt` | `data/source/wiki/text/Super_Valkyrie.txt` |
| `data/wiki/text/Super_Wall_Breaker.txt` | `data/source/wiki/text/Super_Wall_Breaker.txt` |
| `data/wiki/text/Super_Witch.txt` | `data/source/wiki/text/Super_Witch.txt` |
| `data/wiki/text/Super_Witch_Big_Boy.txt` | `data/source/wiki/text/Super_Witch_Big_Boy.txt` |
| `data/wiki/text/Super_Wizard.txt` | `data/source/wiki/text/Super_Wizard.txt` |
| `data/wiki/text/Super_Wizard_Home_Village.txt` | `data/source/wiki/text/Super_Wizard_Home_Village.txt` |
| `data/wiki/text/Super_Wizard_Tower.txt` | `data/source/wiki/text/Super_Wizard_Tower.txt` |
| `data/wiki/text/Super_Wizard_Tower_Home_Village.txt` | `data/source/wiki/text/Super_Wizard_Tower_Home_Village.txt` |
| `data/wiki/text/Super_Yeti.txt` | `data/source/wiki/text/Super_Yeti.txt` |
| `data/wiki/text/Super_Yeti_Electromite.txt` | `data/source/wiki/text/Super_Yeti_Electromite.txt` |
| `data/wiki/text/Supercharge.txt` | `data/source/wiki/text/Supercharge.txt` |
| `data/wiki/text/Temporary_Troops.txt` | `data/source/wiki/text/Temporary_Troops.txt` |
| `data/wiki/text/The_Disarmer.txt` | `data/source/wiki/text/The_Disarmer.txt` |
| `data/wiki/text/Thrower.txt` | `data/source/wiki/text/Thrower.txt` |
| `data/wiki/text/Tornado_Trap.txt` | `data/source/wiki/text/Tornado_Trap.txt` |
| `data/wiki/text/Totem_Spell.txt` | `data/source/wiki/text/Totem_Spell.txt` |
| `data/wiki/text/Totem_Thrower.txt` | `data/source/wiki/text/Totem_Thrower.txt` |
| `data/wiki/text/Town_Hall.txt` | `data/source/wiki/text/Town_Hall.txt` |
| `data/wiki/text/Town_Hall_Giga_Inferno.txt` | `data/source/wiki/text/Town_Hall_Giga_Inferno.txt` |
| `data/wiki/text/Town_Hall_Giga_Inferno_TH13.txt` | `data/source/wiki/text/Town_Hall_Giga_Inferno_TH13.txt` |
| `data/wiki/text/Town_Hall_Giga_Inferno_TH14.txt` | `data/source/wiki/text/Town_Hall_Giga_Inferno_TH14.txt` |
| `data/wiki/text/Town_Hall_Giga_Inferno_TH15.txt` | `data/source/wiki/text/Town_Hall_Giga_Inferno_TH15.txt` |
| `data/wiki/text/Town_Hall_Giga_Inferno_TH16.txt` | `data/source/wiki/text/Town_Hall_Giga_Inferno_TH16.txt` |
| `data/wiki/text/Town_Hall_Giga_Tesla.txt` | `data/source/wiki/text/Town_Hall_Giga_Tesla.txt` |
| `data/wiki/text/Town_Hall_Giga_Weapons.txt` | `data/source/wiki/text/Town_Hall_Giga_Weapons.txt` |
| `data/wiki/text/Town_Hall_Guardians.txt` | `data/source/wiki/text/Town_Hall_Guardians.txt` |
| `data/wiki/text/Town_Hall_Inferno_Artillery.txt` | `data/source/wiki/text/Town_Hall_Inferno_Artillery.txt` |
| `data/wiki/text/Town_Hall_Trivia.txt` | `data/source/wiki/text/Town_Hall_Trivia.txt` |
| `data/wiki/text/Town_Hall_Unlocks.txt` | `data/source/wiki/text/Town_Hall_Unlocks.txt` |
| `data/wiki/text/Town_Hall_Upgrade_Differences.txt` | `data/source/wiki/text/Town_Hall_Upgrade_Differences.txt` |
| `data/wiki/text/Toyshop_Throwdown.txt` | `data/source/wiki/text/Toyshop_Throwdown.txt` |
| `data/wiki/text/Traps.txt` | `data/source/wiki/text/Traps.txt` |
| `data/wiki/text/Traps_Home_Village.txt` | `data/source/wiki/text/Traps_Home_Village.txt` |
| `data/wiki/text/Treasure.txt` | `data/source/wiki/text/Treasure.txt` |
| `data/wiki/text/Treasure_Chests.txt` | `data/source/wiki/text/Treasure_Chests.txt` |
| `data/wiki/text/Treasure_Hunt.txt` | `data/source/wiki/text/Treasure_Hunt.txt` |
| `data/wiki/text/Treasury.txt` | `data/source/wiki/text/Treasury.txt` |
| `data/wiki/text/Troop_Launcher.txt` | `data/source/wiki/text/Troop_Launcher.txt` |
| `data/wiki/text/Troop_Movement_Speed.txt` | `data/source/wiki/text/Troop_Movement_Speed.txt` |
| `data/wiki/text/Troops.txt` | `data/source/wiki/text/Troops.txt` |
| `data/wiki/text/Trophies.txt` | `data/source/wiki/text/Trophies.txt` |
| `data/wiki/text/Trophy_Leagues.txt` | `data/source/wiki/text/Trophy_Leagues.txt` |
| `data/wiki/text/Unicorn.txt` | `data/source/wiki/text/Unicorn.txt` |
| `data/wiki/text/Valkyrie.txt` | `data/source/wiki/text/Valkyrie.txt` |
| `data/wiki/text/Vampstache.txt` | `data/source/wiki/text/Vampstache.txt` |
| `data/wiki/text/Versus_Battles.txt` | `data/source/wiki/text/Versus_Battles.txt` |
| `data/wiki/text/Village_Edit_Mode.txt` | `data/source/wiki/text/Village_Edit_Mode.txt` |
| `data/wiki/text/Wall.txt` | `data/source/wiki/text/Wall.txt` |
| `data/wiki/text/Wall_Breaker.txt` | `data/source/wiki/text/Wall_Breaker.txt` |
| `data/wiki/text/Wall_Home_Village.txt` | `data/source/wiki/text/Wall_Home_Village.txt` |
| `data/wiki/text/Wall_Wrecker.txt` | `data/source/wiki/text/Wall_Wrecker.txt` |
| `data/wiki/text/Walls_Home_Village.txt` | `data/source/wiki/text/Walls_Home_Village.txt` |
| `data/wiki/text/War_Alliances.txt` | `data/source/wiki/text/War_Alliances.txt` |
| `data/wiki/text/Wise_Warriors.txt` | `data/source/wiki/text/Wise_Warriors.txt` |
| `data/wiki/text/Witch.txt` | `data/source/wiki/text/Witch.txt` |
| `data/wiki/text/Witch_Golem.txt` | `data/source/wiki/text/Witch_Golem.txt` |
| `data/wiki/text/Witch_Golem_Big_Boy.txt` | `data/source/wiki/text/Witch_Golem_Big_Boy.txt` |
| `data/wiki/text/Witch_Golem_Skeleton.txt` | `data/source/wiki/text/Witch_Golem_Skeleton.txt` |
| `data/wiki/text/Witch_Skeleton.txt` | `data/source/wiki/text/Witch_Skeleton.txt` |
| `data/wiki/text/Wizard.txt` | `data/source/wiki/text/Wizard.txt` |
| `data/wiki/text/Wizard_Tower.txt` | `data/source/wiki/text/Wizard_Tower.txt` |
| `data/wiki/text/Wizard_Vendor.txt` | `data/source/wiki/text/Wizard_Vendor.txt` |
| `data/wiki/text/Workshop.txt` | `data/source/wiki/text/Workshop.txt` |
| `data/wiki/text/X-Bow.txt` | `data/source/wiki/text/X-Bow.txt` |
| `data/wiki/text/X-Bow_Home_Village.txt` | `data/source/wiki/text/X-Bow_Home_Village.txt` |
| `data/wiki/text/YEETer.txt` | `data/source/wiki/text/YEETer.txt` |
| `data/wiki/text/YEETer_Tribal_Tag_Team.txt` | `data/source/wiki/text/YEETer_Tribal_Tag_Team.txt` |
| `data/wiki/text/Yellow_Card.txt` | `data/source/wiki/text/Yellow_Card.txt` |
| `data/wiki/text/Yeti.txt` | `data/source/wiki/text/Yeti.txt` |
| `data/wiki/text/Yeti_Undertaker.txt` | `data/source/wiki/text/Yeti_Undertaker.txt` |
| `data/wiki/text/Yeti_Undertaker_Skeletons_of_Darkness.txt` | `data/source/wiki/text/Yeti_Undertaker_Skeletons_of_Darkness.txt` |
| `data/wiki/text/Yeti_Yetimite.txt` | `data/source/wiki/text/Yeti_Yetimite.txt` |
| `data/wiki/text/Zap_Trap.txt` | `data/source/wiki/text/Zap_Trap.txt` |
| `data/your-levels-pre-live.json` | `data/source/your-levels-pre-live.json` |

## Directory relocation inventory

These directory moves include empty directory shells as well as the file paths
listed above. The new `source`, `generated` and `licenses` ownership directories
are created by G5a; no compatibility symlinks remain.

| Before | After |
| --- | --- |
| `data/battle-policies/` | `data/source/battle-policies/` |
| `data/builder-bases/` | `data/source/builder-bases/` |
| `data/builder-bases/screens/` | `data/source/builder-bases/screens/` |
| `data/gamecsv/` | `data/source/gamecsv/` |
| `data/gamecsv/v18.200.9/` | `data/source/gamecsv/v18.200.9/` |
| `data/live/` | `data/source/live/` |
| `data/playbooks/` | `data/source/playbooks/` |
| `data/reference-bases/` | `data/source/reference-bases/` |
| `data/reference-bases/ranked-2026-10-24/` | `data/source/reference-bases/ranked-2026-10-24/` |
| `data/reference-bases/ranked-th18-2026-10-25/` | `data/source/reference-bases/ranked-th18-2026-10-25/` |
| `data/replays/` | `data/source/replays/` |
| `data/wiki/` | `data/source/wiki/` (ignored) |
| `data/wiki/pages/` | `data/source/wiki/pages/` (ignored) |
| `data/wiki/tables/` | `data/source/wiki/tables/` (ignored) |
| `data/wiki/text/` | `data/source/wiki/text/` (ignored) |
| `rust/data/` | `data/generated/` |

## Frozen G5a SHA-256 values

Before changes, `/tmp/clash-g5a-goldens-before.sha256` recorded the three golden
files. After changes, `sha256sum -c` confirms all three byte hashes. No golden
record command was run. The seven pinned generated files also match the
original tracked bytes; all other source moves preserve their input payloads
except the four operational history/replay path updates described above.
The five source files with existing CRLF checkout bytes preserve those bytes;
normalizing their line endings for comparison matches HEAD.

| Current path | SHA-256 before and after |
| --- | --- |
| `fixtures/golden/cases.jsonl` | `cea706d86516a2100876f9aa4ec7cdd5de32f691202f9a6d049b64e690d172ab` |
| `fixtures/golden/expected.jsonl` | `40446127d538f7bab2a86ab9c7fcae8b3a725c4ceb462fd2d95236cb38af0ab4` |
| `fixtures/golden/plans.jsonl` | `3ea43b38a16c4608aa04ab308c2a0e1ba645ed2cd3b89ad386235d8c44d32681` |
| `data/generated/base_rules.json` | `9b2e389104a7319eb3e0607e25326c585799362cdb250f9b3532fd43602bd58b` |
| `data/generated/catalog.json` | `91f122ee1649c50fca3cda9bb4d36b837dd2714e071e025b010613a5424979cc` |
| `data/generated/clan_castle.json` | `a7ffb1d265d51ddfa7fc853ee42bc6fcb9b23d59b3e88d08d73f3a280fd207c3` |
| `data/generated/manifest.json` | `ef6aa5c1db3dec2c82d5b463a54fb4a082514a78ea94359cc2708ef4542d716d` |
| `data/generated/registry.json` | `c05e9f3378c2164e1c8ae177d2b38b2d0f67cf61f5f82a41d8202e153a6e1c08` |
| `data/generated/target17.json` | `5eaebfc7b5912fa6b55783cd742f3eb106979d9b204d2ae61e8783e41a690ff6` |
| `data/generated/target18.json` | `47e88a7f1caa79f6110e2a09260dad57a10eb03c16c3b802a865012a4a0a9a03` |

## Additional native acceptance

With the existing mirror explicitly selected at `data/source/wiki/`, the native
source acceptance test passes all 961 pinned source-hash checks, exact registry
LF-byte reproduction, complete canonical catalog equality and the synthetic
source-only perturbation test. No generated data is used as builder input and
no pinned output is overwritten:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-g5
CLASH_CATALOG_WIKI="$PWD/data/source/wiki" \
  cargo test -p clash-dataimport --release --locked --offline \
  complete_source_pipeline -- --ignored --nocapture
```

Result: **1 passed, 0 failed**, 23.12 seconds. Receipt:
`/tmp/clash-g5a-source-acceptance.log`.

CLI smoke checks run from `/tmp` with the final rebuilt executable:

- Unset catalog variables resolve the relocated workspace default.
- The legacy variable alone is honored, including rejection of a missing file.
- A valid `CLASH_CATALOG` overrides an invalid legacy path; an invalid current
  path rejects even when the legacy path is valid.
- Explicit compile `--catalog` overrides both invalid environment values and
  produces the README's example plan from the relocated army/playbook inputs.
- Fidelity's root-relative explicit `--catalog data/generated/catalog.json`
  overrides an invalid environment path and loads successfully; a deliberately
  absent replay then fails at the replay reader as expected.

Receipt: `/tmp/clash-g5a-smoke.log`; all checks passed. Smoke outputs and expected
rejection logs stay under `/tmp/clash-g5a-smoke/`, outside Git.

The relocation audit checks all 1,694 old paths are absent and every destination
exists, and compares the 125 tracked moves against HEAD: 116 match raw HEAD
bytes, five retain existing CRLF checkout bytes (LF-normalized contents match
HEAD), and only four history/replay files change operational paths.
Receipt: `/tmp/clash-g5a-data-audit.log`. The seven generated-file hashes and
three golden-file hashes are checked separately without line-ending normalization.

`cargo tree -p clash-engine --offline` still contains only data and layout,
including the development/test dependency closure. The workspace manifests and
lockfile are unchanged. Shell syntax, workspace formatting and `git diff --check`
pass. The ordinary gate requires no wiki mirror, local corpus, source video,
provider, credentials or ignored inputs. All results are regression/source
consistency evidence, not real-game calibration. Windows verification is not
claimed by this WSL-only task.

## Final G5a workspace gate (WSL)

Final invocation, with the caller working directory set to `/tmp`:

```sh
. ~/.cargo/env
export CARGO_TARGET_DIR=/tmp/clash-target-g5
/mnt/c/Users/jarod/Documents/clash-lab/scripts/verify.sh \
  > /tmp/clash-g5a-verify.log 2>&1
```

Exit status **0**, final line **`ALL CHECKS PASSED`**. This final run includes
the fidelity explicit-path adjustment and uses the final Rust source. The
installed toolchain is Rust/Cargo 1.99.1 with existing Rustfmt and Clippy;
nothing is downloaded or installed.

| Check | Result |
| --- | --- |
| `cargo fmt --all -- --check` | Passed. |
| Locked offline workspace/all-targets release build | Passed. |
| Locked offline workspace release tests | Passed, including native fidelity/dataimport/playbook/search/video synthetic coverage. |
| Strict all-targets release Clippy, `-D warnings` | Passed. |
| Battle goldens, one worker | 868/868 passed. |
| Battle goldens, four workers | 868/868 passed. |
| Compiled-plan goldens | 1354/1354 passed. |
| Guardian fixtures | 50/50 declared synthetic fixtures passed. |
| Army-search proof | 4096 legality cases and 4096 program cases; fingerprints, thread determinism, cache/resume, budget and holdout checks passed. |
| Layout proof | Complete importer equality, TH16/17/18 inventories and geometry passed; 100000 mutations, 2944 accepted engine builds, 97056 structured rejections, all 23 corpus layouts covered. |
| Base-search proposal proof | 93000 attempts, 81864 accepted engine builds, 3000 crossovers; deterministic worker counts 1/4/16/1 passed. |
| Final video tests | 24/24 passed. |
| Golden SHA-256 before/after | All three identical; saved before/after checksum files compare byte-for-byte. |
| Pinned generated SHA-256 | All seven original artifacts byte-identical. |
| Source regeneration acceptance | Complete local-mirror test passed separately, as recorded above. |
| Runtime catalog precedence and outside-root CLI checks | Passed, including legacy fallback, explicit override and relative fidelity path. |
| Shell syntax / final diff whitespace | Passed. |
| Old data/Rust paths | Every moved old file absent, every destination present; `rust/` does not exist. |

The earlier successful gate is retained at `/tmp/clash-g5a-verify-preflight.log`.
The first attempted gate caught the importer provenance-string mismatch and was
superseded by the successful runs; no data or golden was regenerated to fix it.
Final byte receipts are `/tmp/clash-g5a-goldens-before.sha256`,
`/tmp/clash-g5a-goldens-after.sha256` and `/tmp/clash-g5a-generated.sha256`.
The tree is left uncommitted and unstaged for review; the initial unrelated CI
edit and untracked build artifacts remain untouched.
