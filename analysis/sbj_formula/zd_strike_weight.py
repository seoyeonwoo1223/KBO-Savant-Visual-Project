"""Z-d: 스트라이크 수 비용 가중 ZA 절충안 (gates.md Z-d). zb_neutral_za 하네스를 재사용한다.

python analysis/sbj_formula/zd_strike_weight.py [외부 대조 CSV] -> results/zb_neutral_za_strike.json, results/zb_neutral_za_strike_<Y>.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.argv.insert(1, "--recenter")
sys.path.insert(0, str(Path(__file__).parent))
import zb_neutral_za as Z  # noqa: E402

Z.CANDS = ("Z0", "N4", "N5", "N6")
Z.CELLS = {"Z0": 0, "N5": 3, "N6": 12, "N4": 15}
Z.TAG = "_strike"
base_weights = Z.weights


def weights(ev):
    w = base_weights(ev)
    absw = lambda keys: ev.delta_v.abs().groupby([ev[k] for k in keys]).transform("mean").to_numpy()
    w["N5"] = absw(["strikes_before"])
    balls = ev.get("balls_before")
    w["N6"] = absw(["balls_before", "strikes_before"]) if balls is not None else w["N5"]
    return {k: v / v.mean() for k, v in w.items()}


_load = Z.load


def load(y):
    import pyarrow.parquet as pq
    ev = _load(y)
    ev["balls_before"] = pq.read_table(Z.ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet", columns=["balls_before"]).column(0).to_numpy()
    return ev


Z.weights, Z.load = weights, load

if __name__ == "__main__":
    Z.main()
    res = json.loads((Z.OUT / "zb_neutral_za_strike.json").read_text(encoding="utf-8"))
    corr = {c: {} for c in Z.CANDS}
    for y in Z.YEARS:
        t = pd.read_csv(Z.OUT / f"zb_neutral_za_strike_{y}.csv", dtype={"batter_id": str}).set_index("batter_id")
        lb = pd.DataFrame(json.loads((Z.ROOT / f"web/data/zone_awareness/{y}/leaderboard.json").read_text(encoding="utf-8"))["players"])
        lb = lb.assign(batter_id=lb.batter_id.astype(str)).set_index("batter_id")
        for c in Z.CANDS:
            corr[c][y] = float(t[c].rank().corr(lb.apr[t.index].rank()))
    res["ZG7_spearman_apr"] = corr
    res["ZG7_mean"] = {c: float(np.mean(list(v.values()))) for c, v in corr.items()}
    n4_lo = res["candidates"]["N4"]["ZG6_x4_ci95"][0]
    for c in ("N5", "N6"):
        v = res["candidates"][c]
        v["pass"]["ZG7"] = res["ZG7_mean"][c] < res["ZG7_mean"]["N4"]
        v["pass"]["ZG8"] = v["ZG6_x4"] >= n4_lo
        v["all_pass"] = all(v["pass"].values())
    res["recommended_zd"] = "N5" if res["candidates"]["N5"]["all_pass"] else "N4"
    res["weights_by_season"] = {y: {c: res["seasons"][str(y)]["weights"].get(c) for c in ("N4",)} for y in Z.YEARS}
    (Z.OUT / "zb_neutral_za_strike.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("ZG7 mean spearman with APR", {c: round(v, 3) for c, v in res["ZG7_mean"].items()})
    print({c: res["candidates"][c].get("pass") for c in ("N5", "N6")}, "recommended", res["recommended_zd"])
