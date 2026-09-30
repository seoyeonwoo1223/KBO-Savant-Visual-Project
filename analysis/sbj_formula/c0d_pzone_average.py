"""C0d: C0c-A + p_zone seed 5개 평균 (gates.md C0d). python analysis/sbj_formula/c0d_pzone_average.py 2019

결과: results/c0d_<season>.json. B0 수치는 results/c0a_<season>.json(같은 seed·섭동 경기)에서 읽는다.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from c0_deterministic import losses, mean_abs  # noqa: E402
from c0c_calibration import ece  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

RESULTS = Path(__file__).with_name("results")
SET1 = tuple(range(E.RS, E.RS + 5))
SET2 = tuple(range(E.RS + 5, E.RS + 10))
KW = {"pswing_es": False, "calibration": "always"}  # p_swing: C0c-A, 단일 seed(결정적)


def main():
    y = int(sys.argv[1]); fields = zd.pzone_fields(y); rows = E.rows_for(y)
    ref = json.loads((RESULTS / f"c0a_{y}.json").read_text())
    b0 = ref["B0"]; drop = ref["dropped_games"]; b0_runs = b0["runs"]
    b0_seed = float(np.mean([d["mean"] for d in b0["seed_abs_delta"].values()]))
    b0_pert = float(np.mean([d["mean"] for d in b0["perturbation"]]))
    b0_ps_max = max(r["pswing_log_loss"] for r in b0_runs.values())
    b0_pz_max = max(r["pzone_take_log_loss"] for r in b0_runs.values())
    t_b0 = b0_runs[str(E.RS)]["seconds"]

    base_run = E.crossfit(rows, fields)
    fb = E.frame(base_run)
    assert abs(float(E.bernoulli_loss(fb.swing, fb.p_swing).mean()) - b0_runs[str(E.RS)]["pswing_log_loss"]) < 1e-12

    runs = {name: E.crossfit(rows, fields, pzone_seeds=s, **KW) for name, s in (("set1", SET1), ("set2", SET2))}
    f1 = E.frame(runs["set1"])
    pert = []
    for g in drop:
        res = E.crossfit(rows, fields, drop_game=g, pzone_seeds=SET1, **KW)
        pert.append(mean_abs(E.player_sbj(f1[f1.game_id != g]), E.player_sbj(E.frame(res))) | {"game": g})
    seed_d = mean_abs(E.player_sbj(f1), E.player_sbj(E.frame(runs["set2"])))
    c = losses(runs["set1"]); c_pert = float(np.mean([d["mean"] for d in pert]))
    out = {"season": y, "dropped_games": drop, "pzone_seed_sets": [list(SET1), list(SET2)],
           "B0": {"pswing_log_loss_seed_max": b0_ps_max, "pzone_take_log_loss_seed_max": b0_pz_max, "seed_mean_abs": b0_seed,
                  "perturbation_mean_abs": b0_pert, "seconds": t_b0, "pswing_ece": ece(fb.swing, fb.p_swing),
                  "block_reproducibility": E.block_reproducibility(fb)},
           "runs": {k: losses(r) for k, r in runs.items()}, "seed_abs_delta": seed_d, "perturbation": pert,
           "pswing_ece": ece(f1.swing, f1.p_swing), "block_reproducibility": E.block_reproducibility(f1),
           "sbj_vs_b0": mean_abs(E.player_sbj(fb), E.player_sbj(f1))}
    out["gates"] = {
        "C0d-1": {"pswing": [c["pswing_log_loss"], b0_ps_max], "pzone": [c["pzone_take_log_loss"], b0_pz_max],
                  "pass": c["pswing_log_loss"] <= b0_ps_max and c["pzone_take_log_loss"] <= b0_pz_max},
        "C0d-2": {"candidate": seed_d["mean"], "b0": b0_seed, "ratio": seed_d["mean"] / b0_seed, "pass": seed_d["mean"] <= .5 * b0_seed},
        "C0d-3": {"candidate": c_pert, "b0": b0_pert, "ratio": c_pert / b0_pert, "pass": c_pert <= .5 * b0_pert},
        "C0d-4": {"candidate_seconds": c["seconds"], "b0_seconds": t_b0, "ratio": c["seconds"] / t_b0, "pass": c["seconds"] <= 2 * t_b0},
    }
    out["gates"]["pass"] = all(g["pass"] for g in out["gates"].values())
    (RESULTS / f"c0d_{y}.json").write_text(json.dumps(out, indent=1) + "\n")
    print(y, json.dumps(out["gates"]), flush=True)


if __name__ == "__main__":
    main()
