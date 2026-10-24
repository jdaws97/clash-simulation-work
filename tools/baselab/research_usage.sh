#!/bin/bash
# Continuous game-usage research (user, 2026-10-24): one web-enabled Codex
# agent per troop/spell/hero/equipment/pet/siege, then per technique.
# Resumable: subjects with a finished file are skipped; short/failed replies
# are retried on the next pass. Usage: tools/baselab/research_usage.sh [PARALLEL]
cd "$(dirname "$0")/../.."
PAR=${1:-4}
OUT=output/research/usage
mkdir -p "$OUT"
one() {
  kind="$1"; name="$2"
  slug=$(echo "$name" | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//')
  f="$OUT/$slug.md"
  [ -s "$f" ] && [ "$(wc -c < "$f")" -gt 1500 ] && return 0
  brief=$(sed "s/{KIND}/$kind/g; s/{NAME}/$name/g" output/research/brief-entity.txt)
  ~/bin/codex-research "$brief" > "$f.tmp" 2>&1
  if [ "$(wc -c < "$f.tmp")" -gt 1500 ]; then mv "$f.tmp" "$f"; echo "done  $kind | $name ($(wc -c < "$f") bytes)"; else echo "FAIL  $kind | $name"; rm -f "$f.tmp"; fi
}
export -f one
export OUT
for pass in 1 2; do
  while IFS=$'\t' read -r kind name; do printf '%s\0%s\0' "$kind" "$name"; done < output/research/queue.tsv \
    | xargs -0 -n 2 -P "$PAR" bash -c 'one "$0" "$1"'
done
echo "== research pass complete: $(ls $OUT/*.md | wc -l) files"
