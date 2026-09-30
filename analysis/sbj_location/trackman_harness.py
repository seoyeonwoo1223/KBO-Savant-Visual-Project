"""TrackMan harness H3: trajectory speed vs TrackMan rel_speed inside the PR #29 matcher (read-only).

    python analysis/sbj_location/trackman_harness.py <out dir> [seasons...]

The PR #29 matcher (analysis/trajectory_audit/pa_flow_strict.py) accepts a VB-TrackMan pair only when the
DISPLAYED speed is within TOL of TrackMan after one season-level offset. Before 2024 the displayed speed is a
per-park gun value (results/speed_consistency.json), so this reruns the same run alignment with four speed inputs:

  displayed_season  displayed speed, season offset          (= PR #29)
  displayed_game    displayed speed, per-game offset
  traj_season       trajectory speed |v(y0)|, season offset
  traj_game         trajectory speed, per-game offset        (design doc 9.2 H3)

Per-game offsets are the median (speed - rel_speed) over equal-length runs of that game. Rows without a valid
trajectory have no trajectory speed and fall out as velocity_missing in the traj_* variants. Nothing is written
outside <out dir>; the matcher, the ledger and curated data are untouched.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/trajectory_audit"))
import pa_flow_strict as pf  # noqa: E402
from visualbaseball.curated import load_rows  # noqa: E402

KNOWN = {  # rows judged in the capture cases (README "캡처 기반 사례 대조 기록")
    "20240504OBLG0-20240504OBLG0-073-04": "B: fastball trajectory, shown 123 fork",
    "20240504OBLG0-20240504OBLG0-018-02": "B: label suspected from previous pitch",
    "20210606HHNC0-20210606HHNC0-044-01": "E: shown 137 slider, real 145 fastball",
    "20210512SSKT0-20210512SSKT0-017-01": "E: shown 116 changeup, real 114 curve",
}


def game_offsets(vb, tm, pairs, speed):
    vpos = {ix: i for i, ix in enumerate(vb.index)}; tpos = {ix: i for i, ix in enumerate(tm.index)}
    rows = [(vb.game_id.iat[vpos[a]], speed[vpos[a]] - tm.rel_speed.iat[tpos[b]])
            for v_ix, t_ix in pairs if len(v_ix) == len(t_ix) for a, b in zip(v_ix, t_ix)]
    d = pd.DataFrame(rows, columns=["game_id", "d"]).dropna()
    return d.groupby("game_id").d.median()


def run(vb, tm, games, speed, per_game):
    v = vb.copy(); v["velocity_kmh"] = speed
    pairs, lost = pf.candidate_runs(v, tm, games)
    if per_game:
        off = game_offsets(v, tm, pairs, speed.to_numpy())
        v["velocity_kmh"] = speed - v.game_id.map(off).fillna(0.0).to_numpy()
        offset, spread = 0.0, off
    else:
        offset, spread = pf.season_offset(v, tm, pairs), None
    m, _ = pf.match(v, tm, pairs, lost, offset)
    return m, lost, offset, spread


def analyse(season, out):
    vb, tm, games, _ = pf.load(season)
    t = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=["pitch_id", "vx0", "vy0", "vz0", "trajectory_valid"]))
    t = t.set_index("pitch_id").reindex(vb.pitch_id)
    ok = t.trajectory_valid.fillna(False).astype(bool).to_numpy()
    traj = np.sqrt(t.vx0.astype(float) ** 2 + t.vy0.astype(float) ** 2 + t.vz0.astype(float) ** 2).to_numpy() * 1.09728
    traj = pd.Series(np.where(ok, traj, np.nan), index=vb.index)
    disp = vb.velocity_kmh.astype(float)
    res, matched = {"vb_pitches": int(len(vb)), "trajectory_missing": int((~ok).sum())}, {}
    for name, speed, per_game in (("displayed_season", disp, False), ("displayed_game", disp, True),
                                  ("traj_season", traj, False), ("traj_game", traj, True)):
        m, lost, offset, spread = run(vb, tm, games, speed, per_game)
        pid = vb.pitch_id.to_numpy()
        pair = pd.Series(tm.trackman_id.astype(str).to_numpy()[m.ti], index=pid[m.vi])
        matched[name] = pair
        e = {"matched": int(len(m)), "velocity_out_of_tolerance": int(lost.get("velocity_out_of_tolerance", 0)),
             "velocity_missing": int(lost.get("velocity_missing", 0)), "offset_kmh": round(offset, 2)}
        if spread is not None:
            e["game_offset_kmh"] = {k: round(float(x), 2) for k, x in spread.quantile([.01, .1, .5, .9, .99]).items()}
            e["games_offset_abs_gt2"] = int((spread - spread.median()).abs().gt(2).sum())
            e["games"] = int(len(spread))
        res[name] = e
    base, h3 = matched["displayed_season"], matched["traj_game"]
    both = base.index.intersection(h3.index)
    res["traj_game_vs_pr29"] = {"kept": int(len(both)), "same_partner": int((base[both] == h3[both]).sum()),
                                "only_pr29": int(len(base.index.difference(h3.index))),
                                "only_traj_game": int(len(h3.index.difference(base.index)))}
    # H3 residual on traj_game pairs and on PR #29 pairs (trajectory speed, per-game offset)
    tmv = tm.set_index(tm.trackman_id.astype(str)).rel_speed
    tr = pd.Series(traj.to_numpy(), index=vb.pitch_id.to_numpy())
    gid = pd.Series(vb.game_id.to_numpy(), index=vb.pitch_id.to_numpy())
    for name, pair in (("pr29_pairs", base), ("traj_game_pairs", h3)):
        d = pd.DataFrame({"d": tr[pair.index].to_numpy() - tmv[pair.to_numpy()].to_numpy(), "g": gid[pair.index].to_numpy()},
                         index=pair.index).dropna()
        r = d.d - d.groupby("g").d.transform("median")
        res[f"h3_residual_{name}"] = {"n": int(len(r)), "p50_abs": round(float(r.abs().median()), 2),
                                      "p99_abs": round(float(r.abs().quantile(.99)), 2), "gt3": int(r.abs().gt(3).sum()),
                                      "gt5": int(r.abs().gt(5).sum())}
        if name == "pr29_pairs":
            flag = r[r.abs() > 3].round(1).rename("h3_residual_kmh")
            flag.to_frame().assign(tm_pitch_id=pair[flag.index]).to_csv(out / f"h3_pr29_flags_{season}.csv", index_label="pitch_id")
            res["known_cases"] = {p: {"note": n, "pr29_matched": p in pair.index,
                                      "h3_residual_kmh": round(float(r[p]), 1) if p in r.index else None}
                                  for p, n in KNOWN.items() if p.startswith(str(season))}
    only = h3.index.difference(base.index)
    pd.DataFrame({"pitch_id": only, "tm_pitch_id": h3[only].to_numpy()}).to_csv(out / f"traj_game_only_{season}.csv", index=False)
    return res


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    seasons = [int(s) for s in sys.argv[2:]] or list(pf.SEASONS)
    summary = {}
    for s in seasons:
        summary[s] = analyse(s, out)
        print(s, json.dumps(summary[s], ensure_ascii=False), flush=True)
        (out / "trackman_harness_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
