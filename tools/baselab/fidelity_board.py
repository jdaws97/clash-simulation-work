"""Fidelity scoreboard: the simulator against the user's real games.

User (TH16 ranked, 2026-10-24): "I want the simulation fixed always" -- no
search runs until these checks pass. Every engine fix is judged here, and
each run appends one line to output/fidelity/history.jsonl.

  A  real defenses (replay_log.py): 3-star calibration and Brier, destruction
     error, time to 3 stars, and how long FAILED attacks last (real ones run
     128-180 s; the sim wiped armies at ~105 s on 2026-10-24).
  B  observed replays (replay_observed.py): the real attacker's exact plays;
     destruction-curve error every 4 s and star-time error.
  C  Town Hall order: on the user's base, each family's TH17 builds must not
     three-star less often than its TH16 builds.
  D  exposed Eagle: on qd-1212 (Eagle on the edge) attackers must open on it.

Usage: python tools/baselab/fidelity_board.py --label "after snipe fix" [--quick]
"""

from __future__ import annotations

import argparse
import json
import math
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))
OUT = ROOT / "output" / "fidelity"
PY = sys.executable


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def check_a(quick):
    path = OUT / "replay_log.json"
    seeds = "2" if quick else "3"
    r = run([PY, "tools/baselab/replay_log.py", "data/live/battles.jsonl", "--seeds", seeds, "--out", str(path)])
    if r.returncode:
        return {"error": r.stderr[-800:]}
    rows = json.loads(path.read_text())
    real3 = [r["real_stars"] >= 3 for r in rows]
    fails = [r for r in rows if r["real_stars"] < 3]
    sim_fail_times = [t for r in rows for t, s in zip(r["sim_times"], r["sim_stars"]) if s < 3]
    t3 = [(r["sim_time_3star"], r["real_time"]) for r in rows if r["real_stars"] >= 3 and r["sim_time_3star"]]
    return {
        "defenses": len(rows),
        "real_3star": round(st.mean(real3), 3),
        "sim_3star": round(st.mean(r["p3"] for r in rows), 3),
        "brier": round(st.mean((r["p3"] - (r["real_stars"] >= 3)) ** 2 for r in rows), 3),
        "destruction_mae": round(st.mean(abs(r["pct"] - r["real_pct"]) for r in rows), 1),
        "time_to_3star_ratio": round(st.mean(a / b for a, b in t3), 2) if t3 else None,
        "real_failed_median_s": st.median(r["real_time"] for r in fails) if fails else None,
        "sim_failed_median_s": round(st.median(sim_fail_times), 1) if sim_fail_times else None,
        "real_timeout_share": round(st.mean(r["real_time"] >= 179 for r in rows), 3),
        "sim_timeout_share": round(st.mean(r["sim_timeout"] for r in rows), 3),
    }


def check_b(quick):
    out = {}
    for replay in sorted((ROOT / "data" / "replays").glob("*.json")):
        real = json.loads(replay.read_text(encoding="utf-8"))
        if not real.get("deployments") or not real.get("destruction_every_2s"):
            continue
        path = OUT / f"observed-{replay.stem}.json"
        r = run([PY, "tools/baselab/replay_observed.py", str(replay), "--seeds", "4" if quick else "6",
                 "--strength", "calibrated", "--levels", "observed", "--out", str(path)])
        if r.returncode:
            out[replay.stem] = {"error": r.stderr[-800:]}
            continue
        from replay_observed import at

        res = json.loads(path.read_text())
        curve = [(c["t"], c["pct"]) for c in real["destruction_every_2s"]]
        end = max(t for t, _ in curve)
        errs = [st.mean(at(x["curve"], t) for x in res) - at(curve, t) for t in range(4, int(end) + 1, 4)]
        stars = {}
        for s in real.get("stars", []):
            ts = sorted(x["stars_t"].get(s["star"], x["stars_t"].get(str(s["star"]), 999)) for x in res)
            stars[f"star{s['star']}"] = {"real": s["t"], "sim_median": ts[len(ts) // 2]}
        out[replay.stem] = {
            "curve_bias_pts": round(st.mean(errs), 1),
            "curve_mae_pts": round(st.mean(abs(e) for e in errs), 1),
            "stars": stars,
        }
    return out


def check_c(quick):
    from baselab.evaluate import STRENGTH, meta_scenarios, run_batch
    from baselab.layout import Layout
    from funnel import own_levels

    own = own_levels()
    lay = Layout.load(ROOT / "data/reference-bases/your-base.json")
    lay.levels, lay.wall_level, lay.hero_levels = dict(own["levels"]), own["wall_level"], dict(own["hero_levels"])
    rates = {}
    for th in (16, 17):
        sc = meta_scenarios("ranked", 4 if quick else 8, (7,), th_mix={th: 1.0})
        rows = run_batch([(lay.to_json(), s, STRENGTH.get(s.army, 1.0)) for s in sc])
        fam = {}
        for s, r in zip(sc, rows):
            f = s.army.split(":")[1].rsplit("-", 2)[0]
            fam.setdefault(f, []).append(r[0] >= 3)
        rates[th] = {f: round(st.mean(v), 3) for f, v in fam.items()}
    both = sorted(set(rates[16]) & set(rates[17]))
    return {
        "th16": rates[16],
        "th17": rates[17],
        "inversions": [f for f in both if rates[17][f] + 0.05 < rates[16][f]],
    }


def check_d(quick):
    from baselab.engine.battle import Battle
    from baselab.evaluate import STRENGTH, skill
    from baselab.layout import Layout
    from baselab.meta_armies import make_plan

    lay = Layout.load(ROOT / "output/overnight/qd-main/qd-1212.json")
    armies = ["meta:e-drag-spam-17-5", "meta:mass-dragons-17-1", "meta:root-rider-17-1",
              "meta:mass-thrower-17-1", "meta:root-rider-16-1", "meta:mass-dragons-16-1"]
    opened = falls = n = 0
    for army in armies:
        th = int(army.rsplit("-", 2)[1])
        for k in range(2 if quick else 4):
            plan = make_plan(army, 0.3 + k * math.pi / 2, th, 11 + k)
            plan.strength = STRENGTH.get(army, 1.0) * skill(11 + k)
            battle = Battle(lay, plan, seed=11 + k, town_hall=16, record=True)
            battle.run()
            eagle = next(b for b in battle.buildings if b.key == "eagle")
            opened += any(log[2] == eagle.id for log in plan.snipe_log)
            fell = [e[0] for e in battle.log if e[1] == "destroyed" and e[2] == "eagle"]
            falls += bool(fell) and fell[0] <= 30.0
            n += 1
    return {"battles": n, "opening_on_eagle": round(opened / n, 3), "eagle_down_by_30s": round(falls / n, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", default="ABCD")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    board = {"label": args.label, "when": time.strftime("%Y-%m-%d %H:%M"), "quick": args.quick}
    for key, fn in (("A_real_defenses", check_a), ("B_observed_replays", check_b),
                    ("C_th_order", check_c), ("D_exposed_eagle", check_d)):
        if key[0] in args.only:
            board[key] = fn(args.quick)
            print(key, json.dumps(board[key]), flush=True)
    board["seconds"] = round(time.time() - t0)
    with open(OUT / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(board) + "\n")


if __name__ == "__main__":
    main()
