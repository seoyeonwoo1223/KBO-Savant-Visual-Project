"""M: DV 사건·가치 모델 무브먼트를 TrackMan 검증 보정(movement_calibration.calibrate)으로 교체 (gates.md M).

python analysis/sbj_formula/m_dv_movement.py repro 2025   # 하네스가 za7.4 dv를 재현하는지 확인
python analysis/sbj_formula/m_dv_movement.py cand 2022    # 후보 run과 판정 -> results/m_<season>.json

운영 zone_decision.load_rows/score_crossfit을 그대로 부르고, 후보는 구장 보정표 경로만 없는 것으로 바꿔
load_rows가 calibrated_movement()를 쓰게 한다. DV는 p_swing·p_zone을 쓰지 않으므로 후보 run의 DV만 비교한다.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from visualbaseball import zone_decision as zd  # noqa: E402

OUT = Path(__file__).with_name("results")
SWING, TAKE = ("Whiff", "Foul", "InPlay"), ("Ball", "CalledStrike", "HBP")
COLS = ["game_id", "batter_id", "stadium", "pitch_type", "event", "swing", "dv"] + [f"p_{e}" for e in SWING + TAKE]


def evidence(y):
    return pq.read_table(ROOT / f"data/metrics/zone_awareness/{y}/pitches.parquet", columns=COLS).to_pandas()


def run(y, candidate):
    if candidate:
        zd.park_workbook = lambda root, season: Path("/nonexistent/park_workbook.xlsx")
    rows, source = zd.load_rows(ROOT, y)
    result, _ = zd.score_crossfit(rows, "staged", zd.SCORE_SETTINGS, zd.pzone_fields(y))
    return pd.DataFrame([{k: r.get(k) for k in COLS} for r in result]), source["movement"]


def event_loss(df):
    """행동별 조건부 사건 확률로 관측 사건의 음의 로그우도."""
    loss = np.full(len(df), np.nan)
    for events, mask in ((SWING, df.swing == 1), (TAKE, df.swing == 0)):
        p = df.loc[mask, [f"p_{e}" for e in events]].to_numpy()
        p = p / p.sum(axis=1, keepdims=True)
        idx = df.loc[mask, "event"].map({e: i for i, e in enumerate(events)}).to_numpy()
        loss[mask.to_numpy()] = -np.log(np.clip(p[np.arange(len(p)), idx.astype(int)], 1e-15, 1))
    return loss


def cluster_z(diff, games):
    d = pd.Series(diff); m = d.mean()
    g = (d - m).groupby(np.asarray(games)).sum(); G = len(g)
    return float(m), float(m / (np.sqrt(G / (G - 1) * (g ** 2).sum()) / len(d)))


def cell_rms_parts(df, action, event):
    sub = df[df.swing == action]
    res = (sub.event == event).astype(float) - sub[f"p_{event}"]
    cell = sub.stadium.astype(str) + "|" + sub.pitch_type.astype(str)
    return pd.DataFrame({"game": sub.game_id.to_numpy(), "cell": cell.to_numpy(), "res": res.to_numpy()})


def rms_ratio(base, cand, action, event, boots=200, seed=20261001):
    pb, pc = cell_rms_parts(base, action, event), cell_rms_parts(cand, action, event)
    games = np.array(sorted(set(pb.game)))
    gi = {g: i for i, g in enumerate(games)}
    cells = sorted(set(pb.cell)); ci = {c: i for i, c in enumerate(cells)}

    def tensors(p):
        s = np.zeros((len(games), len(cells))); n = np.zeros_like(s)
        np.add.at(s, (p.game.map(gi).to_numpy(), p.cell.map(ci).to_numpy()), p.res.to_numpy())
        np.add.at(n, (p.game.map(gi).to_numpy(), p.cell.map(ci).to_numpy()), 1)
        return s, n

    sb, nb = tensors(pb); sc, nc = tensors(pc)

    def rms(w):
        out = []
        for s, n in ((sb, nb), (sc, nc)):
            S, N = w @ s, w @ n
            keep = N >= 300
            mean = S[keep] / N[keep]
            out.append(np.sqrt(np.sum(N[keep] * mean ** 2) / N[keep].sum()))
        return out

    point = rms(np.ones(len(games)))
    rng = np.random.default_rng(seed)
    ratios = [r[1] / r[0] for r in (rms(rng.multinomial(len(games), np.full(len(games), 1 / len(games))).astype(float)) for _ in range(boots))]
    return {"base_rms": float(point[0]), "cand_rms": float(point[1]), "ratio": float(point[1] / point[0]),
            "ci95": [float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))]}


def dv_table(df):
    g = df.groupby("batter_id"); n = g.size(); m = g.dv.mean()
    dev = df.dv - df.batter_id.map(m)
    se = np.sqrt((dev.groupby([df.batter_id, df.game_id]).sum() ** 2).groupby(level=0).sum()) / n
    q = n.index[n >= 300]
    return pd.DataFrame({"dv100": 100 * m[q], "se": 100 * se[q]})


def reliability(t):
    return float(1 - (t.se ** 2).mean() / t.dv100.var(ddof=1))


def main():
    mode, y = sys.argv[1], int(sys.argv[2])
    base = evidence(y)
    df, movement = run(y, mode == "cand")
    assert len(df) == len(base) and (df.game_id.to_numpy() == base.game_id.to_numpy()).all() and (df.event.to_numpy() == base.event.to_numpy()).all()
    if mode == "repro":
        print(y, "max |Δdv|", float(np.abs(df.dv.to_numpy() - base.dv.to_numpy()).max()), movement.get("formula"))
        return
    df.to_parquet(Path("/tmp") / f"m_cand_{y}.parquet")
    lb, lc = event_loss(base), event_loss(df)
    sw = (base.swing == 1).to_numpy()
    m1 = {name: dict(zip(("base", "cand"), (float(lb[m].mean()), float(lc[m].mean()))),
                     **dict(zip(("delta", "z"), cluster_z(lc[m] - lb[m], base.game_id.to_numpy()[m]))))
          for name, m in (("swing_events", sw), ("take_events", ~sw))}
    m2 = {"whiff_on_swings": rms_ratio(base, df, 1, "Whiff"), "called_strike_on_takes": rms_ratio(base, df, 0, "CalledStrike")}
    tb, tc = dv_table(base), dv_table(df)
    ids = tb.index.intersection(tc.index)
    plus = lambda s: 100 + 15 * (s - s.mean()) / s.std(ddof=0)
    pb, pc = plus(tb.dv100[ids]), plus(tc.dv100[ids])
    shift = (pb.rank(ascending=False) - pc.rank(ascending=False)).abs()
    stad = (100 * (df.dv - base.dv)).groupby(base.stadium).mean()
    out = {"season": y, "movement": movement, "M1": m1, "M2": m2,
           "M3": {"base": reliability(tb), "cand": reliability(tc)},
           "players": {"qualified": len(ids), "mean_abs_delta_dv100": float((tc.dv100[ids] - tb.dv100[ids]).abs().mean()),
                       "max_abs_delta_dv100": float((tc.dv100[ids] - tb.dv100[ids]).abs().max()),
                       "spearman_dv_plus": float(pb.rank().corr(pc.rank())), "max_rank_shift": int(shift.max()),
                       "moved_5_or_more": int((shift >= 5).sum()), "mean_abs_delta_dv_plus": float((pc - pb).abs().mean())},
           "stadium_mean_delta_dv_per_100": {str(k): float(v) for k, v in stad.items()}}
    out["gates"] = {
        "M1": {"pass": all(v["z"] < 2 for v in m1.values())},
        "M2": {"pass": all(v["ci95"][1] <= 1.10 for v in m2.values())},
        "M3": {"pass": out["M3"]["cand"] >= out["M3"]["base"] - .03},
    }
    out["gates"]["pass"] = all(g["pass"] for g in out["gates"].values())
    (OUT / f"m_{y}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(y, json.dumps({k: out[k] for k in ("gates", "M1", "M2", "M3", "players")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
