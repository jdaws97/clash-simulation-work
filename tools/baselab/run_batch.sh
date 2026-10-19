#!/bin/sh
# Final optimization batch (engine v2). Logs in output/opt-*.out
cd "$(dirname "$0")/../.."
PY=.venv/Scripts/python
$PY tools/baselab/optimize_base.py --mode ranked --designs 40 --top 2 --steps 150 > output/opt-ranked.out 2>&1
$PY tools/baselab/optimize_base.py --mode war --designs 40 --top 2 --steps 150 > output/opt-war.out 2>&1
$PY tools/baselab/optimize_base.py --mode target17 --designs 30 --top 1 --steps 120 > output/opt-target17.out 2>&1
$PY tools/baselab/optimize_base.py --mode target18 --designs 30 --top 1 --steps 120 > output/opt-target18.out 2>&1
echo done > output/opt-batch.done
