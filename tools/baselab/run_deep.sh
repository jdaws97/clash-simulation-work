#!/bin/sh
# Long search from the user's strongest real layouts with design-scale moves,
# less noisy scoring (8 angles x 3 seeds) and a validation guard.
cd "$(dirname "$0")/../.."
PY=.venv/Scripts/python
$PY tools/baselab/optimize_base.py --mode ranked --designs 0 --top 2 --steps 400 --search-angles 8 --search-seeds 3 --seeds-from real-l6x your-base --out output/bases-deep > output/deep-ranked.out 2>&1
$PY tools/baselab/optimize_base.py --mode war --designs 0 --top 2 --steps 300 --search-angles 8 --search-seeds 3 --seeds-from your-base real-l6x --out output/bases-deep > output/deep-war.out 2>&1
echo done > output/deep.done
