import json, re
from pathlib import Path

S = Path(r"C:/Users/jarod/AppData/Local/Temp/claude/C--Users-jarod-AppData-Roaming-Claude-scratch-workspaces-f0a725c7-0a20-4b95-9a1a-a6a6dea5666b-97ba9717-5dea-4079-960d-1b84207c407d-scratch-2026-10-15-6523e4/b9aa4227-2025-48e8-b106-6957b35d5ea9/scratchpad/digitize")
L = "https://link.clashofclans.com/en/?action=OpenLayout&id="
out = []

# --- Blueprint CoC
out.append(dict(
    id="bp-ranked-2026-06", source="Blueprint CoC", source_url="https://blueprintcoc.com/blogs/town-hall-16/best-th16-trophy-base",
    builder="Blueprint CoC builder team (article by Loki)", date="2026-06-22", name="Best TH16 Ranked Mode/Trophy Base 2026",
    purpose="ranked / Legend trophy; tested vs RC-walk Root Riders, Clone Hydra, Super Archer spam, Bat Witches",
    image_url="https://cdn.shopify.com/s/files/1/0472/7265/7051/files/TH16_ranked.jpg",
    extra_images={"trap_view": "https://cdn.shopify.com/s/files/1/0472/7265/7051/files/th16_trap_view.jpg"}, image_size=[2880, 1620],
    layout_link=L + "TH16%3AHV%3AAAAAQgAAAAJUMcThgSfkw1SX7Qoe6MuZ",
    image_quality=dict(view="layout editor, top-down isometric, cyan building pads", all_buildings=True,
                       walls="all visible except the bottom corner (x+y >= ~80) and a few behind tall buildings",
                       traps="separate trap-view image; traps stacked too densely to read tile by tile", watermark=False, clean=True),
    inspected=True, status="DIGITIZED: data/builder-bases/blueprint-ranked-2026-06.json"))
top5 = [("Toxic Ring Control Base", "war / anti-Root Rider", "TH16%3AWB%3AAAAAVQAAAAHsVvtVl8MaGJXDkIdmvYn_"),
        ("Toxic Box Anti-RC Base", "anti-Root Rider / anti-Royal-Champion", "TH16%3AWB%3AAAAAVQAAAAHsVyc3R7qQOntzSA2uadGy"),
        ("Hybrid Diamond Disruptor", "hybrid", "TH16%3AHV%3AAAAAVQAAAAHsWRjDM0UPS3RMZb1VPdwi"),
        ("Symmetrical Control War Base", "war", "TH16%3AHV%3AAAAAVQAAAAHsWVCPV7-IOqPLsrCLNAyL"),
        ("Anti-Three Star Trap Base", "hybrid / anti-3-star", "TH16%3AHV%3AAAAAVQAAAAHsWYW2cp9my0xkR3ED5vNQ")]
for i, (n, p, lid) in enumerate(top5, 1):
    out.append(dict(
        id=f"bp-top5-2026-03-{i}", source="Blueprint CoC", source_url="https://blueprintcoc.com/blogs/town-hall-16/best-th16-base-layouts",
        builder="Blueprint CoC base builders (article by Loki)", date="2026-03-11", name=n, purpose=p, image_url=None, image_size=None,
        layout_link=L + lid,
        image_quality=dict(view=None, clean=False, note="no image on the page (only a YouTube video); needs an in-game screenshot of the layout link"),
        inspected=True, status="no image"))

# --- AllClash monthly PRO bases (made public a month later)
t = (S / "html" / "allclash.html").read_text(encoding="utf-8")
seen = set()
months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
for m in re.finditer(r'<img[^>]+src="(https://www\.allclash\.com/wp-content/uploads/[^"]*?th16-[a-z-]*base-[^"]+?)"[^>]*>', t):
    url = m.group(1)
    if url in seen or re.search(r"-\d+x\d+\.", url):
        continue
    alt = re.search(r'alt="([^"]*)"', m.group(0))
    alt = alt.group(1) if alt else ""
    mm = re.search(r"(War / CWL|Trophy) Base, (\w+) (\d{4})", alt)
    if not mm:
        continue
    seen.add(url)
    link = re.search(r"OpenLayout&#038;id=([^\"&<]+)", t[m.end():m.end() + 4000]).group(1)
    kind, mon, yr = mm.groups()
    month = months.index(mon) + 1
    th = link.split("%3A")[0]
    status = "exclude: TH17 layout link" if th != "TH16" else ("exclude: 2025" if yr == "2025" else "candidate (low image quality)")
    out.append(dict(
        id=f"allclash-{'war' if kind.startswith('War') else 'trophy'}-{yr}-{month:02d}", source="AllClash",
        source_url="https://www.allclash.com/the-best-th16-war-trophy-farming-base-layouts/",
        builder="AllClash PRO base (site staff; individual builder not named)", date=f"{yr}-{month:02d}-01", name=alt,
        purpose="war / CWL" if kind.startswith("War") else "trophy / ranked", image_url=url, image_size=[940, 636], layout_link=L + link,
        image_quality=dict(view="village screenshot, zoomed in", all_buildings=False, walls="most", traps="not checked",
                           watermark="diagonal AllClash watermark", clean=False,
                           note="left and right village corners and part of the outer ring are cropped; ~13 px per tile half-width"),
        inspected=True, status=status))

# --- Clash Champs community uploads (TH16, 2026, non-farm); images inspected on contact sheets
cc_obs = {
    "101661": "full village, dark pirate scenery, good contrast, 1884x1080",
    "96154": "full village, dark green, 1318x927",
    "99548": "full village, lava, 1318x927",
    "98476": "full village, lava, 1318x927",
    "101332": "full village, green with lake, 1318x927",
    "100088": "full village, lava, 1920x893",
    "101710": "full village, green, 1696x1080",
    "101184": "scouted (attack-view) screenshot - no traps, lava, 1318x758",
    "92137": "full village, lava, 1920x916",
    "92583": "full village, green, 1765x1080",
    "93040": "full village, green, hex ring, 1920x894",
    "101110": "full village, lava, side icons, 1318x758",
    "101729": "lava, bottom edge slightly cut, 1920x916",
    "100863": "arena scenery, full village, 1442x821",
    "101170": "scouted (attack-view) screenshot - no traps, lava, 1318x758",
    "102126": "PILOT 2: bottom corner cut (x+y >= ~70), traps visible, unmerged (7 cannons), 1920x886",
    "102027": "full village, cartoon scenery, 1660x768",
    "102108": "green, top edge cut, 1920x897",
    "98958": "full village, lava, 1421x1080",
    "99655": "full village, lava, 1920x916",
    "99253": "arena scenery, full village, 1920x916",
}
rows = {}
for f in sorted((S / "html").glob("cc*.html")):
    for blk in f.read_text(encoding="utf-8", errors="replace").split('class="vc_column baseItem"')[1:]:
        def g(p):
            r = re.search(p, blk, re.S)
            return r.group(1) if r else None
        bid = g(r"#(\d+)\s*</div>")
        if bid:
            rows[bid] = dict(b=g(r'data-builder="([^"]*)"'), tag=g(r'<span class="special">TH16</span>\s*<span>([^<]*)</span>'),
                             up=g(r"Uploaded:\s*([0-9-]+)"), dl=g(r"(\d+) downloads"),
                             img=g(r'href="(https://clashchamps.com/cdn-cgi/imagedelivery/[^"]+/image1920)"'), link=g(r'OpenLayout&amp;id=([^"]+)"'))
for bid, obs in cc_obs.items():
    r = rows[bid]
    size = re.search(r"(\d{3,4})x(\d{3,4})", obs)
    out.append(dict(
        id=f"clashchamps-{bid}", source="Clash Champs (community upload)",
        source_url="https://www.clashchamps.com/i-need-a-base/?search_player_townhalls=16&order_by=1",
        builder=(r["b"] or "").strip(), date=r["up"], name=f"Clash Champs base #{bid}",
        purpose=(r["tag"] or "").strip() + f" (Clash Champs tag; {r['dl']} downloads on 2026-10-21)",
        image_url=r["img"], image_size=[int(size[1]), int(size[2])] if size else None, layout_link=L + r["link"],
        image_quality=dict(view="village screenshot (no building pads)", all_buildings="full village" in obs,
                           walls="visible; auto-detection weakened under the watermark",
                           traps="visible in own-village screenshots, not in scouted ones", watermark="large Clash Champs logo over the centre",
                           clean=False, note=obs + "; merge status (Ricochet/Multi-Archer vs 7 Cannons/8 ATs) not checked"),
        inspected=True,
        status="DIGITIZED (draft, low confidence): data/builder-bases/thakur-trophy-2026-10-draft.json" if bid == "102126" else "candidate"))

usable = [o for o in out if not o["status"].startswith("exclude")]
doc = dict(
    created="2026-10-21", town_hall=16,
    notes=("Scouted TH16 layout candidates for digitizing. 'clean' = top-down layout-editor image with building pads and no watermark; "
           "only the Blueprint ranked base meets that bar. Clash Champs images are full-village screenshots with a centre watermark and ~16 px "
           "per tile half-width; AllClash images are cropped at the left/right corners. Every candidate has an in-game layout link: the most "
           "reliable way to get a usable image is to open the link in game and take a layout-editor screenshot plus a trap-view screenshot "
           "(user action). Excluded: TH17/18 bases, farm/progress bases, AllClash Dec 2025 bases and the Jan 2026 AllClash entries whose "
           "links are TH17. Clash Champs 'Pro' is the site's style tag, not a builder credential; builders there are community uploaders."),
    counts=dict(total=len(out), usable=len(usable),
                clean_images=sum(1 for o in usable if o["image_quality"].get("clean")),
                full_village_images=sum(1 for o in usable if o["image_quality"].get("all_buildings") is True),
                no_image=sum(1 for o in usable if not o["image_url"])),
    candidates=out)
p = Path(r"C:/Users/jarod/Documents/clash-lab/data/builder-bases/candidates.json")
p.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
print(doc["counts"])
print([o["id"] for o in out if o["status"].startswith("exclude")])
print(sorted({o["source"] for o in usable}), len({o["builder"] for o in usable}))
