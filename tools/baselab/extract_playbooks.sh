#!/bin/bash
# Extract an attack playbook from every harvested transcript with Codex
# (docs/playbook-extraction.md), then verify each against its transcript
# (check_playbook.py drops anything not quoted). Resumable: transcripts with
# a .raw reply are skipped. Usage: tools/baselab/extract_playbooks.sh [PARALLEL]
cd "$(dirname "$0")/../.."
PAR=${1:-3}
mkdir -p output/sources/playbooks
one() {
  vid="$1"
  out="output/sources/playbooks/$vid.raw"
  [ -s "$out" ] && return 0
  ~/bin/codex-ask "Follow the instructions in docs/playbook-extraction.md exactly. Read the transcript file output/sources/transcripts/$vid.json and reply with only the JSON object it specifies, for video_id $vid." > "$out.tmp" 2>&1 && mv "$out.tmp" "$out"
  PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/baselab/check_playbook.py "$vid"
}
export -f one
PYTHONIOENCODING=utf-8 .venv/Scripts/python -c "
import json, pathlib
for p in sorted(pathlib.Path('output/sources/transcripts').glob('*.json')):
    r = json.loads(p.read_text(encoding='utf-8'))
    if r.get('lines'):
        print(p.stem)
" | xargs -P "$PAR" -I{} bash -c 'one {}'
PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/baselab/check_playbook.py --all | tail -1
