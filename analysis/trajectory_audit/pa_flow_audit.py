"""VB 타석 사건 흐름 검증: 전 시즌 탐지와 TrackMan 대조 (연구용, 데이터는 바꾸지 않음).

    PYTHONPATH=src python analysis/trajectory_audit/pa_flow_audit.py --out /tmp/paflow

현재 파서는 VB 타석마다 볼카운트를 0-0에서 시작하고, 볼 3·스트라이크 2에서 멈추며(cap),
마지막 행을 종료 투구로 둔다. 그래서 아래 흐름 오류가 검증을 통과한다. 원본 호출 코드로
카운트를 cap 없이 다시 세어 탐지한다.

타석(VB PA) 규칙
- K_CONT      2스트라이크에서 S/T가 나온 뒤에도 타석이 이어짐
- BB_CONT     3볼에서 B가 나온 뒤에도 타석이 이어짐
- X_NONLAST   인플레이(X) 뒤에도 타석이 이어짐 (X 2회 이상 포함)
- END_MISMATCH 결과 문구와 마지막 투구가 맞지 않음 (삼진인데 3번째 스트라이크가 아님, 볼넷인데 4번째
               볼이 아님, 타구 결과인데 마지막이 X가 아님). 사구·고의사구는 어느 카운트에서도 끝날 수 있다.
- 결과 없는 타석(주자 아웃 등으로 끊긴 기록)은 다음 기록에 따라:
  SPLIT_SAME   같은 반이닝, 같은 타자·같은 투수의 다음 타석 기록이 이어짐 (타석 분리 의심)
  SPLIT_PCHANGE 같은 반이닝, 같은 타자·다른 투수 (투구 도중 투수 교체. 실제 사건이지만 카운트가 0-0으로 다시 시작됨)
  HALF_END     반이닝의 마지막 기록 (주자 아웃 등으로 이닝 종료 가능, 대부분 실제 사건)
  OTHER_OPEN   그 밖의 미종료
행 규칙
- DUP_CONSEC  같은 경기에서 연속한 두 행의 구속·구종·호출·px·pz가 모두 같음
- DUP_TRAJ    같은 경기에서 궤적 계수 9개가 모두 같은 서로 다른 행

TrackMan 대조(2019–2024, (경기, 이닝, 초/말, 타자) 키)
- 투구 수가 같은 키에서 VB 파서 볼카운트와 TrackMan 볼카운트가 다른 투구(count_mismatch_<s>.csv)
- 같은 타석 안 다음 투구의 TrackMan 카운트 변화(볼 +1 / 스트라이크 +1 / 변화 없음)와 VB 호출 코드의 교차표
- VB "B" 중 존 중심에서 가까운 공(d = max(|x|,|z|) 정규화 거리)이 TrackMan에서 스트라이크인 비율
  (ABS 시즌에서 TrackMan 없이 쓸 수 있는 보조 탐지 규칙의 정밀도·재현율)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[2]
SEASONS = tuple(range(2019, 2027))
TRAJ = ("x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")
COLS = ["pitch_id", "pa_id", "game_id", "inning", "inning_half", "batter_id", "batter_name", "pitcher_id", "pitcher_name",
        "pitch_call_code", "pa_type", "pa_result", "velocity_kmh", "pitch_type_kr", "px", "pz", "game_pitch_number",
        "balls_before", "strikes_before", "trajectory_status", "sz_top", "sz_bottom", *TRAJ]
# 결과 문구로 종료 방식을 나눈다(2022–2024 curated에는 pa_type이 비어 있다).
HBP_IBB = ("사구", "고의사")          # 볼카운트와 무관하게 끝날 수 있음 ("사구"=몸에 맞는 공)
STRIKEOUT = ("삼진", "WP", "PB")   # 낫아웃 폭투·포일 포함. "포BO"는 마지막이 0–1스트라이크의 X인 타구 아웃이라 제외


def pitches(season: int) -> pd.DataFrame:
    d = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=COLS))
    d["pitch_number"] = d.pitch_id.str[-2:].astype(int)
    return d.sort_values(["game_id", "game_pitch_number"]).reset_index(drop=True)


def pa_flags(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    groups = list(d.groupby("pa_id", sort=False))
    for k, (pa_id, g) in enumerate(groups):
        codes = g.pitch_call_code.fillna("").str.upper().tolist()
        balls = strikes = 0
        flags, xs = [], 0
        last_state = (0, 0)
        for i, c in enumerate(codes):
            last = i == len(codes) - 1
            last_state = (balls, strikes)
            if not last:
                if c in ("S", "T") and strikes >= 2: flags.append("K_CONT")
                if c == "B" and balls >= 3: flags.append("BB_CONT")
                if c == "X": flags.append("X_NONLAST")
            # V는 구속·궤적이 있는 실제 투구로, 대부분 0스트라이크 번트 상황이다: 파울처럼 센다.
            balls += c == "B"; strikes += c in ("S", "T") or (c in ("F", "V") and strikes < 2); xs += c == "X"
        b, s = last_state; c = codes[-1]; result = str(g.pa_result.iat[0] or "")
        free = any(t in result for t in HBP_IBB)
        if any(t in result for t in STRIKEOUT):
            closes = c in ("S", "T", "F", "V") and s >= 2
        elif "볼넷" in result:
            closes = c == "B" and b >= 3
        elif free:
            closes = True
        elif result:
            closes = c == "X"
        else:
            closes = False                                   # 결과 없음: 주자 아웃 등으로 타석이 끊긴 기록
        if result and not closes: flags.append("END_MISMATCH")
        if not result:
            nxt = groups[k + 1][1] if k + 1 < len(groups) else None
            same_half = nxt is not None and nxt.game_id.iat[0] == g.game_id.iat[0] and (nxt.inning.iat[0], nxt.inning_half.iat[0]) == (g.inning.iat[0], g.inning_half.iat[0])
            if same_half and nxt.batter_id.iat[0] == g.batter_id.iat[0]:
                flags.append("SPLIT_SAME" if nxt.pitcher_id.iat[0] == g.pitcher_id.iat[0] else "SPLIT_PCHANGE")
            elif not same_half:
                flags.append("HALF_END")
            else:
                flags.append("OTHER_OPEN")
        rows.append({"pa_id": pa_id, "game_id": g.game_id.iat[0], "inning": int(g.inning.iat[0]), "half": g.inning_half.iat[0],
                     "batter_id": g.batter_id.iat[0], "batter_name": g.batter_name.iat[0], "pitcher_name": g.pitcher_name.iat[0],
                     "pitches": len(g), "codes": "".join(codes), "pa_type": str(g.pa_type.iat[0] or ""), "pa_result": g.pa_result.iat[0] or "",
                     "flags": ",".join(sorted(set(flags))), "x_count": xs})
    return pd.DataFrame(rows)


def row_flags(d: pd.DataFrame) -> pd.DataFrame:
    key = ["velocity_kmh", "pitch_type_kr", "pitch_call_code", "px", "pz"]
    prev = d.groupby("game_id")[key].shift(1)
    same = (d[key].astype(str) == prev.astype(str)).all(axis=1) & prev.notna().all(axis=1)
    traj = d[list(TRAJ)].round(6).astype(str).agg("|".join, axis=1)
    valid = d.trajectory_status.eq("valid")
    dup_traj = valid & (d.assign(k=traj).groupby(["game_id", "k"]).pitch_id.transform("size") > 1)
    out = pd.DataFrame({"pitch_id": d.pitch_id, "pa_id": d.pa_id, "DUP_CONSEC": same, "DUP_TRAJ": dup_traj})
    return out


def trackman_counts(season: int, d: pd.DataFrame) -> pd.DataFrame | None:
    """(경기, 이닝, 초/말, VB 타자 ID)별 TrackMan 투구 수. 대응표로 타자 ID를 VB로 옮긴다."""
    path = ROOT / "data/tracking/raw" / f"season={season}" / "trackman_history.csv"
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location("crosswalk", ROOT / "scripts" / "build_trackman_id_crosswalk.py")
    cw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cw)
    tm = cw._trackman(ROOT, season)
    games = cw.map_games(tm, cw._visualbaseball(ROOT, season))
    tm = tm[tm.trackman_game_id.isin(games)].copy()
    tm["game_id"] = tm.trackman_game_id.map(games)
    tm["inning"] = tm["inning"].astype(int)
    table = json.loads((ROOT / "data/tracking/player_id_crosswalk.json").read_text(encoding="utf-8"))["seasons"][str(season)]["roles"]["batter"]
    lookup = {p["trackman_id"]: p["visualbaseball_id"] for p in table["pairs"]}
    known = set(d.batter_id)
    tm["batter_id"] = tm.batter_trackman_id.astype(str).map(lambda t: lookup.get(t, t if t in known else None))
    tm = tm.dropna(subset=["batter_id"]).sort_values(["game_id", "pitch_no"])
    return tm


KEY = ["game_id", "inning", "half", "batter_id"]
B_DIST = (0.5, 0.67, 0.8, 1.0)


def zone_distance(d: pd.DataFrame) -> pd.Series:
    """존 경계가 1이 되는 정규화 거리 max(|x|,|z|) (공 반지름 미포함)."""
    center = (d.sz_top.astype(float) + d.sz_bottom.astype(float)) / 2
    half = (d.sz_top.astype(float) - d.sz_bottom.astype(float)) / 2
    return np.maximum((d.px.astype(float) / (10 / 12)).abs(), ((d.pz.astype(float) - center) / half).abs())


def trackman_calls(d: pd.DataFrame, tm: pd.DataFrame, out: Path, season: int) -> dict:
    """투구 수가 같은 키에서 투구별로 맞춰 VB 호출 코드와 TrackMan 카운트 변화를 비교한다."""
    vb = d.rename(columns={"inning_half": "half"}).copy()
    vb["n"] = vb.groupby(KEY).cumcount(); vb["cnt"] = vb.groupby(KEY).pitch_id.transform("size")
    t = tm[KEY + ["pitch_of_pa", "balls_before", "strikes_before", "rel_speed"]].rename(columns={"balls_before": "tb", "strikes_before": "ts"}).copy()
    t["n"] = t.groupby(KEY).cumcount(); t["tcnt"] = t.groupby(KEY).tb.transform("size")
    for c, src in (("nb", "tb"), ("ns", "ts"), ("npa", "pitch_of_pa")):
        t[c] = t.groupby(KEY)[src].shift(-1)
    m = vb.merge(t, on=KEY + ["n"])
    m = m[m.cnt == m.tcnt].copy()
    wrong = m[(m.balls_before.astype(int) != m.tb.astype(int)) | (m.strikes_before.astype(int) != m.ts.astype(int))]
    wrong[["pitch_id", "pa_id", "balls_before", "strikes_before", "tb", "ts"]].to_csv(out / f"count_mismatch_{season}.csv", index=False)
    aligned = len(m)
    speed = (m.velocity_kmh.astype(float) - pd.to_numeric(m.rel_speed, errors="coerce")).abs()
    m = m[m.npa.notna() & (m.npa > 1)].copy()          # TrackMan 기준 같은 타석의 다음 투구가 있는 투구만
    db, ds = m.nb - m.tb, m.ns - m.ts
    m["tm_event"] = np.select([(db == 1) & (ds == 0), (db == 0) & (ds == 1), (db == 0) & (ds == 0)], ["ball", "strike", "none"], "other")
    m["code"] = m.pitch_call_code.fillna("").str.upper()
    m["dist"] = zone_distance(m)
    table = pd.crosstab(m.code, m.tm_event)
    b = m[m.code == "B"]; b_strike = b.tm_event == "strike"
    b[b_strike][["pitch_id", "pa_id", "pa_result", "px", "pz", "dist", "velocity_kmh", "rel_speed", "tb", "ts"]].to_csv(out / f"b_called_strike_by_trackman_{season}.csv", index=False)
    inzone = {f"{code}_{ev}": round(float((m[(m.code == code) & (m.tm_event == ev)].dist <= 1).mean()), 3)
              for code, ev in (("B", "ball"), ("B", "strike"), ("T", "strike"), ("S", "strike"), ("V", "strike"))}
    return {"aligned_pitches": int(aligned), "count_mismatch_pitches": int(len(wrong)),
            "median_abs_speed_diff_kmh": round(float(speed.median()), 2),
            "code_vs_tm_event": {code: {k: int(v) for k, v in row.items()} for code, row in table.iterrows()},
            "inzone_share_by_code_event": inzone,
            "B_near_center_rule": {str(t): {"flagged": int((b.dist <= t).sum()), "precision": round(float(b_strike[b.dist <= t].mean()), 3) if (b.dist <= t).any() else None,
                                            "recall": round(float(b_strike[b.dist <= t].sum() / max(1, b_strike.sum())), 3)} for t in B_DIST}}


FLAGS = ("K_CONT", "BB_CONT", "X_NONLAST", "END_MISMATCH", "SPLIT_SAME", "SPLIT_PCHANGE", "HALF_END", "OTHER_OPEN", "DUP_CONSEC", "DUP_TRAJ")


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--out", required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=list(SEASONS))
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for season in args.seasons:
        d = pitches(season)
        pa = pa_flags(d)
        rf = row_flags(d)
        pa_rows = rf.groupby("pa_id")[["DUP_CONSEC", "DUP_TRAJ"]].sum()
        pa = pa.join(pa_rows, on="pa_id")
        for c in ("DUP_CONSEC", "DUP_TRAJ"):
            pa[c] = pa[c].fillna(0).astype(int)
            pa["flags"] = np.where(pa[c] > 0, pa["flags"].where(pa["flags"] == "", pa["flags"] + ",") + c, pa["flags"])
        entry = {"pas": int(len(pa)), "pitches": int(len(d)), "flag_pas": {}, "flag_pitches": {}}
        for flag in FLAGS:
            sel = pa["flags"].str.contains(flag)
            entry["flag_pas"][flag] = int(sel.sum()); entry["flag_pitches"][flag] = int(pa.pitches[sel].sum())
        # 보조 규칙: 존 중심 가까이의 VB "B" (ABS 시즌에서 TrackMan 없이 쓰는 탐지)
        near = (d.pitch_call_code.fillna("").str.upper() == "B") & (zone_distance(d) <= 0.8)
        entry["B_near_center_0.8"] = int(near.sum())
        d.loc[near, ["pitch_id", "pa_id", "px", "pz", "velocity_kmh"]].to_csv(out / f"b_near_center_{season}.csv", index=False)
        tm_rows = trackman_counts(season, d)
        if tm_rows is not None:
            tm_rows["state"] = tm_rows.balls_before.astype(int).astype(str) + "-" + tm_rows.strikes_before.astype(int).astype(str)
            tm = tm_rows.groupby(KEY).state.agg(list).rename("tm_states")
            d["state"] = d.balls_before.astype(int).astype(str) + "-" + d.strikes_before.astype(int).astype(str)
            vb = d.groupby(["game_id", "inning", "inning_half", "batter_id"]).state.agg(list).rename("vb_states")
            vb.index = vb.index.set_names(KEY)
            both = pd.concat([vb, tm], axis=1, join="inner")
            both["vb_pitches"], both["tm_pitches"] = both.vb_states.str.len(), both.tm_states.str.len()
            both["diff"] = both.vb_pitches - both.tm_pitches
            # 투구 수가 같은 구간에서 SBJ 입력 볼카운트(VB 파서 값)가 TrackMan 볼카운트와 다른 투구 수
            both["count_mismatch"] = [sum(a != b for a, b in zip(v, t)) if len(v) == len(t) else None for v, t in zip(both.vb_states, both.tm_states)]
            equal = both[both["diff"] == 0]
            key = pa.set_index(["game_id", "inning", "half", "batter_id"])
            entry["trackman"] = {"keys_compared": int(len(both)), "baseline_equal_share": round(float((both["diff"] == 0).mean()), 4),
                                 "equal_keys_with_count_mismatch": int((equal.count_mismatch > 0).sum()),
                                 "equal_keys_mismatched_pitches": int(equal.count_mismatch.sum()),
                                 "baseline_diff_counts": {str(k): int(v) for k, v in both["diff"].clip(-3, 3).value_counts().sort_index().items()}}
            per_flag = {}
            for flag in entry["flag_pas"]:
                keys = key[key["flags"].str.contains(flag)].index.unique()
                sub = both.reindex(keys).dropna(subset=["diff"])   # 투구 수가 다른 키도 남긴다
                if len(sub):
                    eq = sub[sub["diff"] == 0]
                    per_flag[flag] = {"keys": int(len(sub)), "vb_more": int((sub["diff"] > 0).sum()), "equal": int((sub["diff"] == 0).sum()),
                                      "vb_fewer": int((sub["diff"] < 0).sum()), "equal_but_count_mismatch": int((eq.count_mismatch > 0).sum())}
            entry["trackman"]["by_flag"] = per_flag
            unflagged = both.drop(key[key["flags"] != ""].index.unique(), errors="ignore")
            entry["trackman"]["unflagged"] = {"keys": int(len(unflagged)), "vb_more": int((unflagged["diff"] > 0).sum()),
                                              "vb_fewer": int((unflagged["diff"] < 0).sum()),
                                              "equal_but_count_mismatch": int((unflagged[unflagged["diff"] == 0].count_mismatch > 0).sum())}
            both.drop(columns=["vb_states", "tm_states"]).reset_index().to_csv(out / f"trackman_keys_{season}.csv", index=False)
            entry["trackman"]["calls"] = trackman_calls(d, tm_rows, out, season)
        summary[season] = entry
        pa[pa["flags"] != ""].to_csv(out / f"flagged_pas_{season}.csv", index=False)
        print(season, json.dumps(entry, ensure_ascii=False), flush=True)
    (out / "pa_flow_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
