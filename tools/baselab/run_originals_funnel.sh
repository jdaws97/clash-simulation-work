#!/bin/sh
# Originals-only ranked funnel (2026-10-16, the user asked for completely new
# designs): from-scratch layouts only, equal quotas per Town Hall zone
# (center / mid / edge) at every stage, niche-protected evolution, then the
# best of each zone faces the user's bases, the remixes and last night's
# funnel winner. Resumable like run_overnight.sh.
cd "$(dirname "$0")/../.."
PY=.venv/Scripts/python
F=output/funnel
D=$F/originals-ranked
step() { echo "$(date +%H:%M) $*" >> $F/progress.log; }
REFS="data/reference-bases/your-base.json data/reference-bases/real-l6x.json output/bases-deep/ranked-winner.json output/winners/ranked-funnel1.json"
step "originals screen"
[ -s $D/population.json ] || $PY -u tools/baselab/funnel.py screen --mode ranked --seed 11 --originals-only --candidates 15000 --quick 1200 --full 60 --keep 21 --out $D > $D.screen.out 2>&1
step "originals evolve"
[ -f $D/evolve/holdout.json ] || BASELAB_EVAL_LOG=output/evals/funnel-originals.jsonl $PY -u tools/baselab/evolve_bases.py --meta --mode ranked --niche \
  --resume $D/population.json --pop 21 --children 16 --gens 12 --search-angles 8 --search-seeds 2 --adapt-every 4 --adapt-share 0.35 \
  --surrogate 3 --final-adaptive --compare $REFS --out $D/evolve > $D.evolve.out 2>&1
step "originals done"
echo done > $F/originals.done
