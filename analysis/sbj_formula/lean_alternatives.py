"""탐색(사전 등록 아님): 지표 후보별 소극 쏠림(SA와의 Spearman)과 다음 시즌 결과와의 관계.

후보: APR(현행), ZA(옛 SBJ), SEAGER식(선택성 − 칠 공 놓친 비율), APR·ZA 백분위 평균,
공격성 중립 APR(타자 자신의 평균 S − p를 뺀 판단 DV를 add_apr로 환산).
python analysis/sbj_formula/lean_alternatives.py -> results/lean_alternatives.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
from v_execution import cluster_mean, woba  # noqa: E402
from visualbaseball import zone_decision as zd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("results")
CANDS = ("apr", "za", "seager", "apr_za_blend", "apr_neutral")


def season(y):
    ev = pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet",
                       columns=["game_id", "batter_id", "swing", "p_swing", "delta_v", "dv"]).to_pandas()
    ev["batter_id"] = ev.batter_id.astype(str)
    ev["r"] = ev.swing - ev.p_swing
    ev["r_neutral"] = ev.r - ev.groupby("batter_id").r.transform("mean")
    ev["jdv_neutral"] = 2 * ev.r_neutral * ev.delta_v
    t = cluster_mean(ev.jdv_neutral, ev.batter_id, ev.game_id)
    players = [{"batter_id": b, "pitches_seen": int(t.n[b]), "qualified_300": bool(t.n[b] >= 300),
                "jdv_per_100": float(100 * t["mean"][b]), "jdv_se": float(100 * t.se[b])} for b in t.index]
    zd.add_apr(players, 100 * float(ev.dv.mean()), 100 * float(ev.jdv_neutral.mean()))
    neutral = pd.DataFrame(players).set_index("batter_id").apr
    take, swing = ev.swing == 0, ev.swing == 1
    good = (swing & (ev.delta_v > 0)) | (take & (ev.delta_v < 0))
    g = ev.assign(ht=(take & (ev.delta_v > 0)), tk=take, sel=(take & (ev.delta_v < 0)), good=good).groupby("batter_id")[["ht", "tk", "sel", "good"]].sum()
    seager = g.sel / g.good - g.ht / g.tk
    b = pd.DataFrame(json.loads((ROOT / f"web/data/zone_awareness/{y}/leaderboard.json").read_text(encoding="utf-8"))["players"])
    b["batter_id"] = b.batter_id.astype(str); b = b.set_index("batter_id"); b = b[b.qualified_300]
    tab = pd.DataFrame({"name": b.batter_name, "sa": b.swing_aggression, "apr": b.apr, "za": b.za_raw,
                        "seager": seager[b.index], "apr_neutral": neutral[b.index],
                        "apr_za_blend": (b.apr_percentile + b.za_percentile) / 2})
    return tab


def main():
    tabs = {y: season(y) for y in range(2019, 2027)}
    res = {"spearman_with_sa": {c: {y: float(t[c].rank().corr(t.sa.rank())) for y, t in tabs.items()} for c in CANDS}}
    w = {y: woba(y) for y in range(2020, 2027)}
    frames = []
    for y in range(2019, 2026):
        t = tabs[y].join(w[y + 1], how="inner"); t = t[t.pa >= 150]
        frames.append((t[list(CANDS) + ["sa", "woba"]] - t[list(CANDS) + ["sa", "woba"]].mean()))
    d = pd.concat(frames)
    res["next_season_woba_corr"] = {c: float(d[c].corr(d.woba)) for c in CANDS}
    res["year_to_year"] = {c: float(pd.concat([pd.DataFrame({"a": tabs[y][c], "b": tabs[y + 1][c]}).dropna() for y in range(2019, 2026)]).corr().iloc[0, 1]) for c in CANDS}
    t25 = tabs[2025]
    res["2025_rank_kwon"] = {c: int(t25[c].rank(ascending=False)[t25.name == "권희동"].iloc[0]) for c in CANDS}
    res["2025_top10"] = {c: t25.sort_values(c, ascending=False).name.head(10).tolist() for c in CANDS}
    (OUT / "lean_alternatives.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in CANDS:
        s = res["spearman_with_sa"][c]
        print(f"{c:13s} SA상관 {min(s.values()):+.2f}~{max(s.values()):+.2f}  다음시즌wOBA {res['next_season_woba_corr'][c]:+.3f}  시즌간 {res['year_to_year'][c]:.2f}  권희동2025 {res['2025_rank_kwon'][c]}위  top10 {res['2025_top10'][c][:5]}")


if __name__ == "__main__":
    main()
