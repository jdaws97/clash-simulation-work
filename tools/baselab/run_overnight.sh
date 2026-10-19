#!/bin/sh
# Overnight multi-fidelity base search (tools/baselab/funnel.py), 2026-10-15.
# 1. predictor data  2. train  3. ranked funnel x3 (independent seeds)
# 4. war funnel  5. final comparison on fresh battles. Each step logs to
# output/funnel/*.out; a failed step is logged and the chain continues.
cd "$(dirname "$0")/../.."
PY=.venv/Scripts/python
F=output/funnel
mkdir -p $F
REFS="data/reference-bases/your-base.json data/reference-bases/real-l6x.json output/bases-deep/ranked-winner.json output/bases-deep/war-winner.json"
step() { echo "$(date +%H:%M) $*" >> $F/progress.log; }

step "data"
# resumable: top the data up to ~1300 rows (a different seed per attempt so bases are new)
HAVE=$(cat $F/data.jsonl 2>/dev/null | wc -l)
if [ "$HAVE" -lt 1200 ]; then
  $PY -u tools/baselab/funnel.py data --n $((1300 - HAVE)) --seed $((7 + HAVE)) --out $F/data.jsonl >> $F/data.out 2>&1
fi
step "train"
$PY -u tools/baselab/funnel.py train --data $F/data.jsonl --out-dir $F > $F/train.out 2>&1

run_funnel() {  # mode seed gens final_adaptive
  D=$F/$1-$2
  [ -f $D/evolve/holdout.json ] && { step "skip $1-$2 (done)"; return; }
  step "screen $1-$2"
  Q=500; [ "$1" = "ranked" ] && Q=1200  # ranked predictor is a coarse filter (rank corr ~0.5): simulate more
  [ -s $D/population.json ] || $PY -u tools/baselab/funnel.py screen --mode $1 --seed $2 --candidates 15000 --quick $Q --full 60 --keep 20 --out $D > $D.screen.out 2>&1
  step "evolve $1-$2"
  EXTRA=""
  [ "$4" = "yes" ] && EXTRA="--final-adaptive"
  BASELAB_EVAL_LOG=output/evals/funnel-$1-$2.jsonl $PY -u tools/baselab/evolve_bases.py --meta --mode $1 --resume $D/population.json \
    --pop 20 --children 16 --gens $3 --search-angles 8 --search-seeds 2 --adapt-every 4 --adapt-share 0.35 --surrogate 3 \
    $EXTRA --compare $REFS --out $D/evolve > $D.evolve.out 2>&1
}
run_funnel ranked 1 8 yes
run_funnel ranked 2 5 no
run_funnel ranked 3 5 no
run_funnel war 1 6 yes
step "final compare"
$PY -u tools/baselab/final_compare.py > $F/final.out 2>&1
step "done"
echo done > $F/overnight.done
