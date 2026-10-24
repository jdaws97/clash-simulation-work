#!/bin/bash
# Research-vs-engine gap audit (user, 2026-10-24): one read-only Codex agent per
# finished usage file in output/research/usage; resumable. Re-run to pick up
# newly finished research. Usage: tools/baselab/audit_usage.sh [PARALLEL]
cd "$(dirname "$0")/../.."
PAR=${1:-3}
one() {
  f="$1"; slug=$(basename "$f" .md); out="output/research/gaps/$slug.md"
  [ -s "$out" ] && [ "$(wc -c < "$out")" -gt 800 ] && return 0
  name=$(head -1 "$f" | sed 's/^# *//')
  brief=$(sed "s/{SLUG}/$slug/g; s/{NAME}/$name/g" output/research/brief-gap.txt)
  ~/bin/codex-ask "$brief" > "$out.tmp" 2>&1
  if [ "$(wc -c < "$out.tmp")" -gt 800 ]; then mv "$out.tmp" "$out"; echo "audited $slug"; else rm -f "$out.tmp"; echo "FAIL $slug"; fi
}
export -f one
ls output/research/usage/*.md | xargs -P "$PAR" -I{} bash -c 'one {}'
echo "== audit pass complete: $(ls output/research/gaps/*.md 2>/dev/null | wc -l) files"
