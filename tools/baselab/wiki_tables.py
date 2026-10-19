"""Parse mirrored wiki pages into structured tables and searchable text.

Output:
  data/wiki/tables/<page>.json  {"title", "source", "revid", "tables": [...]}
      each table: {"heading", "kind": "infobox"|"stats"|"other",
                   "columns": [...], "rows": [[...], ...]} or
                  {"kind": "infobox", "fields": {name: value}}
  data/wiki/text/<page>.txt     readable body text (navboxes removed)
  data/wiki/catalog.json        compact per-page summary (infobox + stat columns)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "data" / "wiki"


def clean(text: str) -> str:
    text = re.sub(r"\[\d+\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def expand(table):
    """Return a grid of cell texts with rowspan/colspan expanded, plus a
    parallel grid marking header cells."""
    grid: list[list] = []
    heads: list[list] = []
    spans: dict = {}
    for r, tr in enumerate(table.find_all("tr")):
        row, hrow = [], []
        c = 0
        cells = tr.find_all(["td", "th"], recursive=False)
        it = iter(cells)
        while True:
            if (r, c) in spans:
                text, is_h = spans.pop((r, c))
                row.append(text)
                hrow.append(is_h)
                c += 1
                continue
            cell = next(it, None)
            if cell is None:
                break
            text = clean(cell.get_text(" "))
            is_h = cell.name == "th"
            cs = int(cell.get("colspan", 1) or 1)
            rs = int(cell.get("rowspan", 1) or 1)
            for k in range(cs):
                row.append(text)
                hrow.append(is_h)
                for dr in range(1, rs):
                    spans[(r + dr, c + k)] = (text, is_h)
            c += cs
        while (r, c) in spans:
            text, is_h = spans.pop((r, c))
            row.append(text)
            hrow.append(is_h)
            c += 1
        if row:
            grid.append(row)
            heads.append(hrow)
    return grid, heads


def classify(grid, heads):
    if not grid:
        return None
    n_head = 0
    while n_head < len(heads) and all(heads[n_head]) and n_head < 3:
        n_head += 1
    if n_head == 0:
        return {"kind": "other", "rows": grid}
    width = max(len(r) for r in grid)
    cols = []
    for c in range(width):
        parts = []
        for r in range(n_head):
            v = grid[r][c] if c < len(grid[r]) else ""
            if v and (not parts or parts[-1] != v):
                parts.append(v)
        cols.append(" / ".join(parts))
    body = grid[n_head:]
    if len(body) == 1 and n_head == 1:
        return {"kind": "infobox", "fields": {cols[i]: body[0][i] for i in range(min(len(cols), len(body[0])))}}
    first = cols[0].lower() if cols else ""
    kind = "stats" if first in ("level", "charge", "charge level", "town hall level", "walls level") else "other"
    return {"kind": kind, "columns": cols, "rows": body}


def parse_page(page: dict):
    soup = BeautifulSoup(page["html"], "lxml")
    for junk in soup.select(".navbox, .toc, .mw-editsection, script, style, .reference"):
        junk.decompose()
    tables = []
    for t in soup.find_all("table"):
        if t.find_parent("table") is not None:
            continue
        heading = None
        prev = t.find_previous(["h2", "h3", "h4"])
        if prev is not None:
            heading = clean(prev.get_text(" "))
        grid, heads = expand(t)
        info = classify(grid, heads)
        if info is None:
            continue
        txt = json.dumps(info)
        if "Tapping this icon" in txt:
            continue
        info["heading"] = heading
        tables.append(info)
    body = soup.select_one(".mw-parser-output") or soup
    paras = []
    for el in body.find_all(["h2", "h3", "p", "li"]):
        if el.find_parent("table") is not None:
            continue
        txt = clean(el.get_text(" "))
        if not txt:
            continue
        paras.append(("\n## " + txt) if el.name in ("h2", "h3") else txt)
    return tables, "\n".join(paras)


def main():
    pages_dir = WIKI / "pages"
    (WIKI / "tables").mkdir(parents=True, exist_ok=True)
    (WIKI / "text").mkdir(parents=True, exist_ok=True)
    catalog = {}
    for path in sorted(pages_dir.glob("*.json")):
        page = json.loads(path.read_text(encoding="utf-8"))
        if "html" not in page:
            continue
        tables, text = parse_page(page)
        out = {"title": page["title"], "source": page["source"], "revid": page["revid"], "retrieved_utc": page["retrieved_utc"], "tables": tables}
        (WIKI / "tables" / path.name).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        (WIKI / "text" / (path.stem + ".txt")).write_text(f"# {page['title']}\n{page['source']}\n\n{text}", encoding="utf-8")
        catalog[page["title"]] = {
            "infobox": [t["fields"] for t in tables if t["kind"] == "infobox"],
            "stats_columns": [t["columns"] for t in tables if t["kind"] == "stats"],
            "max_level_rows": [t["rows"][-1] for t in tables if t["kind"] == "stats" and t["rows"]],
        }
    (WIKI / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"parsed {len(catalog)} pages")


if __name__ == "__main__":
    sys.exit(main())
