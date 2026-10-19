"""First-pass check of Codex audit findings (output/checks/audit-*.md).

For every MISMATCH / MISSING row, every quoted wiki phrase (in “...” or
"...") must appear in the local wiki copy (data/wiki/pages, any page,
punctuation and case ignored). Rows whose quotes all check out are
"quote-verified" and go to review; rows with a missing quote are flagged.
The engine side of each finding is still checked by reading the code
before anything changes.

Writes docs/audit-ledger.md: one line per finding with its fix id, verdict,
quote check and status (open / applied / rejected), keeping any status
already recorded there.

Usage: python tools/baselab/verify_audit.py
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def norm(s):
    s = s.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9%.' ]+", " ", s.lower())).strip()


def corpus():
    parts = []
    for f in glob.glob(str(ROOT / "data" / "wiki" / "pages" / "*.json")):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        t = d.get("wikitext", "")
        t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)  # [[Link|text]] -> text
        t = re.sub(r"\{\{H\|([^}|]*)(?:\|[^}]*)?\}\}", r"\1", t)
        t = re.sub(r"'''?", "", t)
        parts.append(norm(t))
    return " \n ".join(parts)


def main():
    text = corpus()
    ledger_p = ROOT / "docs" / "audit-ledger.md"
    status = {}
    if ledger_p.exists():
        for line in ledger_p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\| (\S+) \| .* \| (open|applied|rejected|deferred)[^|]*\|", line)
            if m:
                status[m.group(1)] = line.rsplit("|", 2)[-2].strip()
    rows = []
    for f in sorted(glob.glob(str(ROOT / "output" / "checks" / "audit-*.md"))):
        cat = Path(f).stem.replace("audit-", "")
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            if not line.startswith("|") or not re.search(r"MISMATCH|MISSING", line):
                continue
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) < 4:
                continue
            fix = re.search(r"\b(F\d+[a-z]?)\b", cols[-1])
            fid = f"{cat}:{fix.group(1)}" if fix else f"{cat}:row{len(rows)}"
            quotes = re.findall(r"[“\"]([^”\"]{6,})[”\"]", cols[1])
            ok = [q for q in quotes if norm(q) and norm(q) in text]
            verdict = "MISMATCH" if "MISMATCH" in cols[-1] else "MISSING"
            qs = f"{len(ok)}/{len(quotes)}" if quotes else "no quote"
            rows.append((fid, cat, cols[0][:70], verdict, qs, status.get(fid, "open")))
    seen, out = set(), []
    for r in rows:
        if r[0] in seen:
            continue
        seen.add(r[0])
        out.append(r)
    lines = ["# Audit ledger", "", "Findings from the Codex category audits (output/checks/audit-*.md). Quote check: wiki quotes found in the local wiki copy / quotes given. Status: open, applied, rejected (with reason) or deferred.", "",
             "| id | category | mechanic | verdict | quotes found | status |", "|---|---|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {d} | {e} | {s} |" for a, b, c, d, e, s in out]
    ledger_p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    n_ok = sum(1 for r in out if "/" in r[4] and r[4].split("/")[0] == r[4].split("/")[1])
    print(f"{len(out)} findings; quotes fully found for {n_ok}; partial or none for {len(out) - n_ok}")


if __name__ == "__main__":
    main()
