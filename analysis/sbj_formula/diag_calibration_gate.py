"""진단: C0 섭동 run에서 p_swing 등위 보정 게이트가 뒤집히는지와 선수 SBJ 변화의 관계 (읽기 전용).

python analysis/sbj_formula/diag_calibration_gate.py 2022  ->  results/diag_calibration_gate_<season>.json
c0_deterministic.py와 같은 섭동 경기(default_rng(20260930))를 쓴다.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import sbj_exp as E  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

y = int(sys.argv[1]); rows = E.rows_for(y); fields = zd.pzone_fields(y)
games = sorted({r["game_id"] for r in rows})
drop = list(np.random.default_rng(20260930).choice(games, 3, replace=False))
out = {"season": y, "dropped_games": drop, "configs": {}}
for name, es in (("B0", "auto"), ("C0a", False)):
    full = E.crossfit(rows, fields, es=es); base = E.frame(full)
    runs = []
    for g in drop:
        res = E.crossfit(rows, fields, es=es, drop_game=g)
        keep = base[base.game_id != g]
        a, b = E.player_sbj(keep), E.player_sbj(E.frame(res))
        runs.append({"game": g, "calibration_applied": res["calibration_applied"],
                     "flip": res["calibration_applied"] != full["calibration_applied"],
                     "mean_abs_delta_sbj": float((a - b[a.index]).abs().mean())})
    out["configs"][name] = {"full_calibration_applied": full["calibration_applied"], "perturbations": runs}
dest = Path(__file__).with_name("results") / f"diag_calibration_gate_{y}.json"
dest.write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
