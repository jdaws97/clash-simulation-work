#!/bin/sh
# Original-design search: screen freeform (and a few styled) layouts that
# are not derived from any existing base, fine-tune the best three with the
# full move set (including freeform wall rewiring), then score them against
# the user's bases and the remixed winner on unseen attacks.
# Waits for the deep search (run_deep.sh) so the two do not share the CPU.
cd "$(dirname "$0")/../.."
PY=.venv/Scripts/python
mkdir -p output/evals
until [ -f output/deep.done ]; do sleep 30; done
BASELAB_EVAL_LOG=output/evals/originals-ranked.jsonl $PY tools/baselab/optimize_base.py --mode ranked --designs 0 --originals 90 --styled 12 --originals-only --top 3 --steps 450 \
  --search-angles 8 --search-seeds 3 --compare output/bases-deep/ranked-winner.json --out output/originals > output/originals-ranked.out 2>&1
echo done > output/originals.done
