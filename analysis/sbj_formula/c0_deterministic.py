"""C0 결정적 적합 실험 (gates.md C0). python analysis/sbj_formula/c0_deterministic.py 2019 [--variant a|b]

결과: results/c0_<variant>_<season>.json. 기준 run의 확률은 C1 입력용으로 캐시에 남긴다.
"""
import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

VARIANTS = {
    # C0a: 조기 종료 끔, 단일 seed. C0b: 조기 종료 auto, seed 5개 평균 (C0a가 C0-1에서만 미달일 때).
    "a": {"es": False, "seed_sets": [(E.RS,), (1,)]},
    "b": {"es": "auto", "seed_sets": [tuple(range(E.RS, E.RS + 5)), tuple(range(E.RS + 5, E.RS + 10))]},
}


def losses(res):
    df = E.frame(res)
    take = df[df.swing == 0]
    return {"pswing_log_loss": float(E.bernoulli_loss(df.swing, df.p_swing).mean()),
            "pzone_take_log_loss": float(E.bernoulli_loss(take.take_cs, take.p_zone).mean()),
            "seconds": res["seconds"], "calibration_applied": res["calibration_applied"]}


def mean_abs(a, b):
    ids = a.index.intersection(b.index)
    d = (a[ids] - b[ids]).abs()
    return {"mean": float(d.mean()), "max": float(d.max()), "players": len(ids)}


def perturbation(rows, fields, full, games, seeds, es):
    base = E.frame(full)
    out = []
    for g in games:
        res = E.crossfit(rows, fields, seeds=seeds, es=es, drop_game=g)
        keep = base[base.game_id != g]
        out.append(mean_abs(E.player_sbj(keep), E.player_sbj(E.frame(res))) | {"game": g, "seconds": res["seconds"]})
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("season", type=int); ap.add_argument("--variant", default="a")
    args = ap.parse_args(); y = args.season; v = VARIANTS[args.variant]
    fields = zd.pzone_fields(y); rows = E.rows_for(y)
    games = sorted({r["game_id"] for r in rows})
    drop = list(np.random.default_rng(20260930).choice(games, 3, replace=False))
    out = {"season": y, "variant": args.variant, "dropped_games": drop}

    # B0: 운영 설정, seed 3개
    b0 = {s: E.crossfit(rows, fields, seeds=(s,)) for s in (E.RS, 1, 2)}
    np.savez(E.CACHE / f"b0_{y}.npz", p_swing=b0[E.RS]["p_swing"], p_zone=b0[E.RS]["p_zone"])
    out["B0"] = {"runs": {str(s): losses(r) for s, r in b0.items()}}
    sbj0 = {s: E.player_sbj(E.frame(r)) for s, r in b0.items()}
    out["B0"]["seed_abs_delta"] = {f"{a}-{b}": mean_abs(sbj0[a], sbj0[b]) for a, b in combinations(sbj0, 2)}
    out["B0"]["perturbation"] = perturbation(rows, fields, b0[E.RS], drop, (E.RS,), "auto")

    # 후보
    cand = [E.crossfit(rows, fields, seeds=s, es=v["es"]) for s in v["seed_sets"]]
    np.savez(E.CACHE / f"c0{args.variant}_{y}.npz", p_swing=cand[0]["p_swing"], p_zone=cand[0]["p_zone"])
    out["C0"] = {"runs": [losses(r) | {"seeds": list(s)} for r, s in zip(cand, v["seed_sets"])]}
    out["C0"]["seed_abs_delta"] = mean_abs(E.player_sbj(E.frame(cand[0])), E.player_sbj(E.frame(cand[1])))
    out["C0"]["perturbation"] = perturbation(rows, fields, cand[0], drop, v["seed_sets"][0], v["es"])

    # 판정 (gates.md)
    b0_ps = [r["pswing_log_loss"] for r in out["B0"]["runs"].values()]
    b0_pz = [r["pzone_take_log_loss"] for r in out["B0"]["runs"].values()]
    c = out["C0"]["runs"][0]
    b0_seed = np.mean([d["mean"] for d in out["B0"]["seed_abs_delta"].values()])
    b0_pert = np.mean([d["mean"] for d in out["B0"]["perturbation"]])
    c_pert = np.mean([d["mean"] for d in out["C0"]["perturbation"]])
    seed_d = out["C0"]["seed_abs_delta"]
    c02 = seed_d["max"] < 1e-6 if args.variant == "a" else False
    c02 = c02 or seed_d["mean"] <= .5 * b0_seed
    t_b0 = out["B0"]["runs"][str(E.RS)]["seconds"]
    out["gates"] = {
        "C0-1": {"pswing": [c["pswing_log_loss"], max(b0_ps)], "pzone": [c["pzone_take_log_loss"], max(b0_pz)],
                 "pass": c["pswing_log_loss"] <= max(b0_ps) and c["pzone_take_log_loss"] <= max(b0_pz)},
        "C0-2": {"candidate_seed_delta": seed_d, "b0_seed_mean_abs": float(b0_seed), "pass": bool(c02)},
        "C0-3": {"candidate": float(c_pert), "b0": float(b0_pert), "ratio": float(c_pert / b0_pert), "pass": bool(c_pert <= .5 * b0_pert)},
        "C0-4": {"candidate_seconds": c["seconds"], "b0_seconds": t_b0, "ratio": c["seconds"] / t_b0, "pass": c["seconds"] <= 2 * t_b0},
    }
    out["reproducibility"] = {"B0": E.block_reproducibility(E.frame(b0[E.RS])), "C0": E.block_reproducibility(E.frame(cand[0]))}
    dest = Path(__file__).with_name("results") / f"c0{args.variant}_{y}.json"
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out["gates"], indent=1))


if __name__ == "__main__":
    main()
