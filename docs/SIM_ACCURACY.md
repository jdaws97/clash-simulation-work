# Accuracy evidence contract

Passing native regression checks establishes repeatability over pinned inputs;
it does not establish agreement with the game. Keep synthetic fixtures, public
source claims, model assumptions and measured observations distinguishable.
The dated [October 20 scorecard](history/SIM_ACCURACY_2026-10-20.md) is historical.

| Question | Current evidence workflow |
| --- | --- |
| Do source numbers rebuild? | [Native catalog acceptance](DATA_PIPELINE.md), with explicit normalized wiki inputs and source hashes. Python source cross-checks remain pending ports. |
| Are mechanics internally consistent? | `scripts/verify.sh`, native engine tests, [goldens](GOLDEN.md), [RM1 evidence](RM1_EVIDENCE.md) and explicit unsupported-content rejection. |
| Are attack recipes supported by evidence? | [Playbook validation](PLAYBOOK_PIPELINE.md) against `local/sources/transcripts`; unresolved wiki-only support and timing drift require review. |
| Do forecasts fit held-out observations? | [Native fidelity](FIDELITY_RUST.md) with explicit private logs/snapshots, disjoint training/evaluation ancestry, baseline comparisons and labeled scouting policies. |
| Do timings and mechanics match observations? | [Video measurements](VIDEO_MEASUREMENTS.md) and [probe cards](PROBE_CARDS.md), preserving sampling limits and unmeasured fields. |
| Are search winners robust? | [Native base-search reports](../crates/clash-basesearch/README.md), paired independent finals, complete physical-battle accounting and sensitivity to model assumptions. |

Fit on training observations only. Report failed or insufficient measurements
explicitly; matching a historical average or a small selected example does not
establish a calibrated ranking. Aggregate/meta fitting and policy/surrogate
research remain Python workflows until their separate native ports are complete.
