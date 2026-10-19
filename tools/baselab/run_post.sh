#!/bin/sh
# After the optimization batch: defense comparison, attack tests, report.
cd "$(dirname "$0")/../.."
PY=.venv/Scripts/python
export PYTHONIOENCODING=utf-8
$PY tools/baselab/final_eval.py > output/final-eval.log 2>&1 || exit 1
$PY tools/baselab/recommend_armies.py --angles 6 --th17 3 --modifiers none,legend1 --out output/army-recommendations-typical.json > output/recommend-typical.log 2>&1 || exit 1
$PY tools/baselab/recommend_armies.py --only --extra data/reference-bases/real-l1x.json --angles 16 --modifiers none,legend1 --out output/thrower-base/attack-l1x.json > output/thrower-base/attack-l1x.log 2>&1 || exit 1
$PY tools/baselab/build_report.py > output/report-build.log 2>&1 || exit 1
echo done > output/post.done
