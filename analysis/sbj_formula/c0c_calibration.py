"""C0c p_swing 보정 게이트 제거 실험 (gates.md C0c). python analysis/sbj_formula/c0c_calibration.py 2019

결과: results/c0c_<season>.json. B0 수치는 results/c0a_<season>.json(같은 seed·섭동 경기)에서 읽는다.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from c0_deterministic import losses, mean_abs  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

RESULTS = Path(__file__).with_name("results")
VARIANTS = {"A": "always", "N": "never"}


def ece(y, p, bins=20):
    """20 분위 구간 기대 보정 오차."""
    order = np.argsort(p); y, p = np.asarray(y)[order], np.asarray(p)[order]
    return float(sum(len(c) * abs(y[c].mean() - p[c].mean()) for c in np.array_split(np.arange(len(p)), bins)) / len(p))


def main():
    y = int(sys.argv[1]); fields = zd.pzone_fields(y); rows = E.rows_for(y)
    ref = json.loads((RESULTS / f"c0a_{y}.json").read_text())
    b0 = ref["B0"]; drop = ref["dropped_games"]
    b0_runs = b0["runs"]
    b0_seed = float(np.mean([d["mean"] for d in b0["seed_abs_delta"].values()]))
    b0_pert = float(np.mean([d["mean"] for d in b0["perturbation"]]))
    b0_ps_max = max(r["pswing_log_loss"] for r in b0_runs.values())
    t_b0 = b0_runs[str(E.RS)]["seconds"]

    base_run = E.crossfit(rows, fields)  # B0 seed 20260903: ECE·재현성 진단용 (c0a와 같은 값)
    fb = E.frame(base_run)
    assert abs(float(E.bernoulli_loss(fb.swing, fb.p_swing).mean()) - b0_runs[str(E.RS)]["pswing_log_loss"]) < 1e-12
    out = {"season": y, "dropped_games": drop,
           "B0": {"pswing_log_loss_seed_max": b0_ps_max, "seed_mean_abs": b0_seed, "perturbation_mean_abs": b0_pert,
                  "seconds": t_b0, "pswing_ece": ece(fb.swing, fb.p_swing), "block_reproducibility": E.block_reproducibility(fb)},
           "variants": {}}
    for key, mode in VARIANTS.items():
        kw = {"pswing_es": False, "calibration": mode}
        runs = {s: E.crossfit(rows, fields, seeds=(s,), **kw) for s in (E.RS, 1)}
        f0 = E.frame(runs[E.RS])
        pert = []
        for g in drop:
            res = E.crossfit(rows, fields, drop_game=g, **kw)
            pert.append(mean_abs(E.player_sbj(f0[f0.game_id != g]), E.player_sbj(E.frame(res))) | {"game": g})
        seed_d = mean_abs(E.player_sbj(f0), E.player_sbj(E.frame(runs[1])))
        c = losses(runs[E.RS]); c_pert = float(np.mean([d["mean"] for d in pert]))
        v = {"calibration": mode, "runs": {str(s): losses(r) for s, r in runs.items()}, "seed_abs_delta": seed_d,
             "perturbation": pert, "pswing_ece": ece(f0.swing, f0.p_swing), "block_reproducibility": E.block_reproducibility(f0),
             "sbj_vs_b0": mean_abs(E.player_sbj(fb), E.player_sbj(f0))}
        v["gates"] = {
            "C0c-1": {"candidate": c["pswing_log_loss"], "b0_seed_max": b0_ps_max, "pass": c["pswing_log_loss"] <= b0_ps_max},
            "C0c-2": {"candidate": seed_d["mean"], "b0": b0_seed, "ratio": seed_d["mean"] / b0_seed, "pass": seed_d["mean"] <= .5 * b0_seed},
            "C0c-3": {"candidate": c_pert, "b0": b0_pert, "ratio": c_pert / b0_pert, "pass": c_pert <= .5 * b0_pert},
            "C0c-4": {"candidate_seconds": c["seconds"], "b0_seconds": t_b0, "ratio": c["seconds"] / t_b0, "pass": c["seconds"] <= 2 * t_b0},
        }
        v["gates"]["pass"] = all(g["pass"] for g in v["gates"].values())
        out["variants"][key] = v
        print(y, key, json.dumps(v["gates"]), flush=True)
    (RESULTS / f"c0c_{y}.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
