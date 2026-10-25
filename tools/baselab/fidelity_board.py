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
       [--attacker generic|playbook] (A only; or BASELAB_REPLAY_PLAYBOOKS=1)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics as st
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools" / "baselab"))
OUT = ROOT / "output" / "fidelity"
PY = sys.executable


def run(cmd):
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )


def defense_metrics(rows):
    attacker_counts = Counter(r.get("attacker", "unrecorded") for r in rows)
    fallback_counts = Counter(
        r["attacker_fallback"] for r in rows if r.get("attacker_fallback")
    )
    end_reasons = Counter()
    for row in rows:
        end_reasons.update(row.get("sim_end_reason_counts", {}))
    counts = {
        "attacker_counts": dict(attacker_counts),
        "attacker_fallback_counts": dict(fallback_counts),
        # Actual simulated battles, before best-side selection duplicates outcomes.
        "sim_end_reason_counts": dict(end_reasons),
        "sim_end_reason_unrecorded_defenses": sum(
            "sim_end_reason_counts" not in row for row in rows
        ),
    }
    if not rows:
        return {
            "defenses": 0,
            **counts,
            "real_failed_n": 0,
            "sim_failed_n": 0,
            "sim_failed_matched_median_s": None,
            "sim_failed_matched_n": 0,
        }
    real3 = [r["real_stars"] >= 3 for r in rows]
    fails = [r for r in rows if r["real_stars"] < 3]
    sim_fail_times = [
        t for r in rows for t, s in zip(r["sim_times"], r["sim_stars"]) if s < 3
    ]
    # output/fidelity/diag/d1.out: compare failures on the same real defenses.
    # Selected simulated failures retain the pooled metric's scouting weights.
    matched_fail_times = [
        t for r in fails for t, s in zip(r["sim_times"], r["sim_stars"]) if s < 3
    ]
    t3 = [
        (r["sim_time_3star"], r["real_time"])
        for r in rows
        if r["real_stars"] >= 3 and r["sim_time_3star"]
    ]
    return {
        "defenses": len(rows),
        **counts,
        "real_3star": round(st.mean(real3), 3),
        "sim_3star": round(st.mean(r["p3"] for r in rows), 3),
        "brier": round(
            st.mean((r["p3"] - (r["real_stars"] >= 3)) ** 2 for r in rows), 3
        ),
        "destruction_mae": round(
            st.mean(abs(r["pct"] - r["real_pct"]) for r in rows), 1
        ),
        "time_to_3star_ratio": round(st.mean(a / b for a, b in t3), 2) if t3 else None,
        "real_failed_median_s": (
            st.median(r["real_time"] for r in fails) if fails else None
        ),
        "real_failed_n": len(fails),
        "sim_failed_median_s": (
            round(st.median(sim_fail_times), 1) if sim_fail_times else None
        ),
        "sim_failed_n": len(sim_fail_times),
        "sim_failed_matched_median_s": (
            round(st.median(matched_fail_times), 1) if matched_fail_times else None
        ),
        "sim_failed_matched_n": len(matched_fail_times),
        "real_timeout_share": round(st.mean(r["real_time"] >= 179 for r in rows), 3),
        "sim_timeout_share": round(st.mean(r["sim_timeout"] for r in rows), 3),
    }


def ancestry_battle_ids(ancestry):
    """Read the self-contained prior snapshots; missing provenance is unknown."""
    if not isinstance(ancestry, list):
        return None
    fitted = set()
    for prior in ancestry:
        if not isinstance(prior, dict) or not prior.get("calibration"):
            return None
        identities = prior.get("battle_ids")
        ancestors = ancestry_battle_ids(prior.get("ancestry"))
        if (
            not isinstance(identities, list)
            or not all(isinstance(identity, str) for identity in identities)
            or ancestors is None
        ):
            return None
        fitted.update(identities)
        fitted.update(ancestors)
    return fitted


def fitted_battle_ids(report_path=None, *, calibration_path=None):
    """Identify training rows from the selected calibration's matching report.

    Older reports lack identities: reconstruct only when both input hashes,
    family counts and historical layout hashes still match exactly. Missing
    prior ancestry is unknown, so callers must treat every row as in-sample.
    """
    from calibrate_defenses import observations
    from replay_log import HISTORY

    calibration = Path(
        calibration_path
        or os.environ.get("BASELAB_CALIBRATION")
        or ROOT / "data/meta-calibration-r8.json"
    )
    selected = json.loads(calibration.read_text(encoding="utf-8"))
    entries = [v for v in selected.values() if isinstance(v, dict)]
    if not any("defense_group" in v for v in entries) and not any(
        k.startswith("defense-th") for k in selected
    ):
        # data/meta-calibration-r8.json was fitted to public meta rates, not logs.
        known = (
            calibration.resolve() == (ROOT / "data/meta-calibration-r8.json").resolve()
        )
        return (set() if known else None), {
            "fit_status": "not defense-fitted" if known else "ancestry unknown",
            "calibration": str(calibration),
            "ancestry": [] if known else None,
        }
    provenance = [v["provenance"] for v in entries if v.get("provenance")]
    candidates = (
        [Path(report_path)]
        if report_path
        else [
            calibration.with_name("report-" + calibration.name),
            calibration.with_suffix(".report.json"),
            *sorted((ROOT / "data").glob("*report*.json")),
            *sorted((ROOT / "output/overnight").glob("*report*.json")),
        ]
    )
    log = ROOT / "data/live/battles.jsonl"
    for path in dict.fromkeys(candidates):
        if not path.is_file():
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(report, dict)
            or report.get("provenance") not in provenance
            or not report.get("groups")
        ):
            continue
        declared_groups = {
            k: v for k, v in selected.items() if k.startswith("defense-th")
        }
        reported_groups = {
            "defense-th" + key[2:].replace(":", "-", 1): value
            for key, value in report["groups"].items()
        }
        if declared_groups.keys() != reported_groups.keys() or any(
            value["n"] != reported_groups[key]["n"]
            or value["strength"] != reported_groups[key]["correction"]
            for key, value in declared_groups.items()
        ):
            continue
        if report.get("inputs_changed_during_run"):
            continue
        info = {
            "fit_status": "identified",
            "calibration": str(calibration),
            "calibration_report": str(path),
            "ancestry": report.get("ancestry"),
        }
        ancestors = ancestry_battle_ids(info["ancestry"])
        if ancestors is None:
            info["fit_status"] = "ancestry unknown"
            return None, info
        identities = report.get("battle_ids")
        if identities is not None and len(identities) == report["n"]:
            return set(identities) | ancestors, info
        hashes = report.get("inputs", {})
        if (
            hashes.get("battle_log_sha256")
            != hashlib.sha256(log.read_bytes()).hexdigest()
            or hashes.get("history_sha256")
            != hashlib.sha256(HISTORY.read_bytes()).hexdigest()
        ):
            continue
        ths = {int(key.split(":")[0][2:]) for key in report["groups"]}
        rows, _ = observations(log, HISTORY, ths)
        expected = Counter()
        expected_layouts = Counter()
        for key, group in report["groups"].items():
            th = int(key.split(":")[0][2:])
            expected.update(
                {(th, family): n for family, n in group["family_counts"].items()}
            )
            expected_layouts.update(
                {(v["path"], v["sha256"]): v["n"] for v in group["layouts"]}
            )
        if (
            len(rows) == report["n"]
            and Counter((r["th"], r["family"]) for r in rows) == expected
            and Counter((r["layout_path"], r["layout_sha256"]) for r in rows)
            == expected_layouts
        ):
            info["fit_status"] = "reconstructed from matching inputs"
            return {r["battle_id"] for r in rows} | ancestors, info
    return None, {
        "fit_status": "ancestry unknown",
        "calibration": str(calibration),
        "ancestry": None,
    }


def check_a(quick, exclude_fitted=False, calibration_report=None, attacker=None):
    from replay_log import battle_identity, default_attacker, read_battles

    attacker = attacker or default_attacker()
    path = OUT / "replay_log.json"
    seeds = "2" if quick else "5"
    r = run(
        [
            PY,
            "tools/baselab/replay_log.py",
            "data/live/battles.jsonl",
            "--seeds",
            seeds,
            "--attacker",
            attacker,
            "--exclude-unknown",
            "--report",
            "--out",
            str(path),
        ]
    )
    if r.returncode:
        return {"engine": "python", "attacker": attacker, "error": r.stderr[-800:]}
    report = json.loads(path.read_text())
    rows = report["rows"] if isinstance(report, dict) else report
    excluded_unknown = (
        report.get("excluded_unknown", 0) if isinstance(report, dict) else 0
    )
    excluded_unknown += sum(bool(row.get("unknown")) for row in rows)
    rows = [row for row in rows if not row.get("unknown")]
    fitted, info = fitted_battle_ids(calibration_report)
    # Support old cached replay output, whose n refers to the archived log index.
    if any("battle_id" not in row for row in rows):
        items = read_battles(ROOT / "data/live/battles.jsonl")
        rows = [
            dict(
                row, battle_id=row.get("battle_id") or battle_identity(items[row["n"]])
            )
            for row in rows
        ]
    in_sample = (
        [row for row in rows if row["battle_id"] in fitted]
        if fitted is not None
        else list(rows)
    )
    out_of_sample = (
        [row for row in rows if row["battle_id"] not in fitted]
        if fitted is not None
        else []
    )
    scored = out_of_sample if exclude_fitted else rows
    return {
        "engine": "python",
        "attacker": attacker,
        **info,
        **defense_metrics(scored),
        "excluded_unknown": excluded_unknown,
        "fitted_defenses": 0 if exclude_fitted else len(in_sample),
        "excluded_fitted": len(in_sample) if exclude_fitted else 0,
        "in_sample": defense_metrics([] if exclude_fitted else in_sample),
        "out_of_sample": defense_metrics(out_of_sample),
    }


def check_b(quick):
    out = {}
    for replay in sorted((ROOT / "data" / "replays").glob("*.json")):
        real = json.loads(replay.read_text(encoding="utf-8"))
        if not real.get("deployments") or not real.get("destruction_every_2s"):
            continue
        path = OUT / f"observed-{replay.stem}.json"
        r = run(
            [
                PY,
                "tools/baselab/replay_observed.py",
                str(replay),
                "--seeds",
                "4" if quick else "6",
                "--strength",
                "calibrated",
                "--levels",
                "observed",
                "--out",
                str(path),
            ]
        )
        if r.returncode:
            out[replay.stem] = {"error": r.stderr[-800:]}
            continue
        from replay_observed import at

        res = json.loads(path.read_text())
        curve = [(c["t"], c["pct"]) for c in real["destruction_every_2s"]]
        end = max(t for t, _ in curve)
        errs = [
            st.mean(at(x["curve"], t) for x in res) - at(curve, t)
            for t in range(4, int(end) + 1, 4)
        ]
        stars = {}
        for s in real.get("stars", []):
            ts = sorted(
                x["stars_t"].get(s["star"], x["stars_t"].get(str(s["star"]), 999))
                for x in res
            )
            stars[f"star{s['star']}"] = {"real": s["t"], "sim_median": ts[len(ts) // 2]}
        out[replay.stem] = {
            "curve_bias_pts": round(st.mean(errs), 1),
            "curve_mae_pts": round(st.mean(abs(e) for e in errs), 1),
            "stars": stars,
        }
    return {"engine": "python", "replays": out}


def check_c(quick):
    from baselab.evaluate import STRENGTH, meta_scenarios, run_batch, summarise
    from baselab.layout import Layout
    from funnel import own_levels

    own = own_levels()
    lay = Layout.load(ROOT / "data/reference-bases/your-base.json")
    lay.levels, lay.wall_level, lay.hero_levels = (
        dict(own["levels"]),
        own["wall_level"],
        dict(own["hero_levels"]),
    )
    rates = {}
    raw = {}
    for th in (16, 17):
        sc = meta_scenarios("ranked", 4 if quick else 8, (7,), th_mix={th: 1.0})
        rows = run_batch([(lay.to_json(), s, STRENGTH.get(s.army, 1.0)) for s in sc])
        fam = {}
        for s, r in zip(sc, rows):
            f = s.army.split(":")[1].rsplit("-", 2)[0]
            fam.setdefault(f, []).append((s, r))
        rates[th] = {
            f: round(summarise([s for s, _ in v], [r for _, r in v]).three_star_rate, 3)
            for f, v in fam.items()
        }
        raw[th] = {
            f: round(st.mean(r[0] >= 3 for _, r in v), 3) for f, v in fam.items()
        }
    both = sorted(set(rates[16]) & set(rates[17]))
    return {
        "engine": "rust" if os.environ.get("BASELAB_ENGINE") == "rust" else "python",
        "th16": rates[16],
        "th17": rates[17],
        "raw": {"th16": raw[16], "th17": raw[17]},
        "inversions": [f for f in both if rates[17][f] + 0.05 < rates[16][f]],
    }


def check_d(quick):
    from baselab.engine.battle import Battle
    from baselab.evaluate import STRENGTH, skill
    from baselab.layout import Layout
    from baselab.meta_armies import make_plan

    lay = Layout.load(ROOT / "output/overnight/qd-main/qd-1212.json")
    armies = [
        "meta:e-drag-spam-17-5",
        "meta:mass-dragons-17-1",
        "meta:root-rider-17-1",
        "meta:mass-thrower-17-1",
        "meta:root-rider-16-1",
        "meta:mass-dragons-16-1",
    ]
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
    return {
        "engine": "python",
        "battles": n,
        "opening_on_eagle": round(opened / n, 3),
        "eagle_down_by_30s": round(falls / n, 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", default="ABCD")
    ap.add_argument(
        "--attacker",
        choices=["playbook", "generic"],
        help="A: attacker policy (default: generic; BASELAB_REPLAY_PLAYBOOKS=1 selects playbook)",
    )
    ap.add_argument(
        "--exclude-fitted",
        action="store_true",
        help="A: score only verified out-of-sample defenses",
    )
    ap.add_argument(
        "--calibration-report",
        type=Path,
        help="A: report for the selected defense calibration",
    )
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    board = {
        "label": args.label,
        "when": time.strftime("%Y-%m-%d %H:%M"),
        "quick": args.quick,
    }
    for key, fn in (
        ("A_real_defenses", check_a),
        ("B_observed_replays", check_b),
        ("C_th_order", check_c),
        ("D_exposed_eagle", check_d),
    ):
        if key[0] in args.only:
            board[key] = (
                fn(
                    args.quick,
                    args.exclude_fitted,
                    args.calibration_report,
                    args.attacker,
                )
                if key.startswith("A_")
                else fn(args.quick)
            )
            print(key, json.dumps(board[key]), flush=True)
    board["seconds"] = round(time.time() - t0)
    with open(OUT / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(board) + "\n")


if __name__ == "__main__":
    main()
