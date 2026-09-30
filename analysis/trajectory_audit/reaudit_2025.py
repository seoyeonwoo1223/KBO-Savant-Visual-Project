"""2025 궤적–px 불일치 6구 재감사 (za7.3 승인 판단용, 공개 산출물은 바꾸지 않음).

    PYTHONPATH=src OMP_NUM_THREADS=2 python analysis/trajectory_audit/reaudit_2025.py --out /tmp/reaudit

1. 6구 개별 근거표: 원본 JSON 값, 판정면 좌표, 불일치, 경계까지 거리, 같은 타석 레코드 이상
2. 레코드 이상 전수 검사(2024–2026): 한 경기 안 궤적 계수 9개가 완전히 같은 서로 다른 투구,
   궤적 x가 이웃 투구의 px와 맞는 투구 — 1cm 규칙으로 못 잡는 경우(누락) 확인
3. 경험적 ABS 50% 경계와 폭: 2025 테이크에서 좌우·상단·하단 각각 로지스틱 적합
4. 판정면 대체 규칙 기하: |x_mid−px|, |z_front−pz| 분포, 앞면 pz를 중간·끝면에 대입할 때의 편향
5. 2025 SBJ 세 처리안: 현행 궤적 / px 대체(직접효과와 재학습 파급 분리) / 의심 투구 제외
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from visualbaseball import plate_decision_v1 as old
from visualbaseball import zone_decision as zd
from visualbaseball.curated import CM_PER_FOOT, _at_plane, load_rows

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "zone_decision"))
import pswing_input_ablation as ablation  # noqa: E402

SIX = ["20250418NCHH0-20250418NCHH0-085-04", "20250611SKLG0-20250611SKLG0-019-01",
       "20250809OBWO0-20250809OBWO0-083-02", "20250809OBWO0-20250809OBWO0-083-03",
       "20250809OBWO0-20250809OBWO0-083-04", "20250809OBWO0-20250809OBWO0-083-07"]
TRAJ = ("x0", "y0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az")
# 김택연–임지열 9회말 기록 묶음: PA082(결과 없는 1구)와 PA083(불가능한 볼카운트·인플레이 2회·중복 궤적)
CORRUPT_PA = ("20250809OBWO0-20250809OBWO0-082-", "20250809OBWO0-20250809OBWO0-083-")


def raw_pitch(pitch_id: str) -> dict:
    game_id, _, pa, number = pitch_id.split("-")
    payload = json.loads((ROOT / "data/raw/2025" / f"{game_id}.json").read_text(encoding="utf-8-sig"))
    rows = load_rows(ROOT, "pitches", 2025, game_id=game_id, columns=["pitch_id", "event_seq", "pa_id"])
    # curated pitch_id의 타석 번호는 원본 pbpData 안 타석 순서다. 원본을 같은 순서로 펼쳐 찾는다.
    seq = [(half, pa_) for half in payload["pbpData"] for pa_ in half.get("pas") or []]
    for index, (half, record) in enumerate(seq, 1):
        for n, pitch in enumerate(record.get("pitches") or [], 1):
            if f"{index:03d}" == pa and f"{n:02d}" == number:
                return {"raw": pitch, "batter": record.get("batter"), "pitcher": record.get("pitcher"), "pa_result": record.get("result")}
    return {}


def edges(frame: pd.DataFrame) -> dict:
    """테이크의 호출 스트라이크 확률을 경계까지의 부호 거리로 로지스틱 적합: 50% 위치와 척도(cm)."""
    takes = frame[frame.swing == 0]
    side = takes.x_mid_relative.abs() * zd.PLATE_HALF_WIDTH_FT * CM_PER_FOOT
    inside_v = (takes.top_gap_cm < -8) & (takes.bottom_gap_cm > 8)
    inside_h = side < 18
    fits = {}
    for name, value, sel, sign in (("side_cm", side, inside_v & side.between(15, 40), -1),
                                   ("top_gap_cm", takes.top_gap_cm, inside_h & takes.top_gap_cm.between(-12, 15), -1),
                                   ("bottom_gap_cm", takes.bottom_gap_cm, inside_h & takes.bottom_gap_cm.between(-15, 12), 1)):
        x, y = value[sel].to_numpy(float), (takes.event[sel] == "CalledStrike").to_numpy(float)
        X, b = np.c_[np.ones_like(x), sign * x], np.zeros(2)
        for _ in range(50):
            p = 1 / (1 + np.exp(-X @ b)); w = p * (1 - p) + 1e-9
            b += np.linalg.solve(X.T @ (X * w[:, None]) + 1e-6 * np.eye(2), X.T @ (y - p))
        fits[name] = {"edge": float(-b[0] / (sign * b[1])), "scale_cm": float(1 / abs(b[1])), "takes": int(sel.sum())}
    return fits


def call_probability(fits: dict, side_cm: float, top: float, bottom: float) -> float:
    """세 경계 로지스틱의 곱(서로 독립 가정). 위치만으로 본 테이크 스트라이크 확률의 거친 기준."""
    def logistic(z): return 1 / (1 + math.exp(-z))
    return (logistic((fits["side_cm"]["edge"] - side_cm) / fits["side_cm"]["scale_cm"])
            * logistic((fits["top_gap_cm"]["edge"] - top) / fits["top_gap_cm"]["scale_cm"])
            * logistic((bottom - fits["bottom_gap_cm"]["edge"]) / fits["bottom_gap_cm"]["scale_cm"]))


def record_anomalies(season: int) -> dict:
    cols = ["pitch_id", "game_id", "px", "pz", "trajectory_status", *TRAJ]
    d = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=cols))
    d = d[d.trajectory_status == "valid"].sort_values("pitch_id").reset_index(drop=True)
    key = d[list(TRAJ)].round(6).astype(str).agg("|".join, axis=1)
    dup = d.assign(key=key).groupby(["game_id", "key"]).pitch_id.transform("size") > 1
    x_mid = pd.Series([_at_plane(r, zd.PLANE_Y_FT["mid"])[0] for r in d.to_dict("records")]) / CM_PER_FOOT
    own = (x_mid - d.px).abs() * CM_PER_FOOT
    prev_px = d.groupby("game_id").px.shift(1)
    lag = ((x_mid - prev_px).abs() * CM_PER_FOOT < 0.35) & (own > 0.35)
    flagged = own > zd.PLANE_LOCATION_TOLERANCE_CM
    return {"valid_pitches": int(len(d)), "duplicate_trajectory_pitches": int(dup.sum()),
            "duplicate_trajectory_caught_by_1cm_rule": int((dup & flagged).sum()),
            "x_traj_matches_previous_px_not_own": int(lag.sum()), "of_which_caught_by_1cm_rule": int((lag & flagged).sum()),
            "duplicate_examples": d.loc[dup, "pitch_id"].head(12).tolist(),
            "abs_x_mid_minus_px_cm_bands": {band: int(c) for band, c in pd.cut(own, [-.01, .15, .5, 1, 6, 1e9]).astype(str).value_counts().sort_index().items()}}


def duplicate_groups(season: int) -> list[dict]:
    """궤적 계수가 같은 투구 묶음: 위치(px·pz)·구속·구종까지 같은지 보여 준다."""
    cols = ["pitch_id", "game_id", "px", "pz", "velocity_kmh", "pitch_type_kr", "pitch_call_code", "trajectory_status", *TRAJ]
    d = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=cols))
    d = d[d.trajectory_status == "valid"].copy()
    d["key"] = d[list(TRAJ)].round(6).astype(str).agg("|".join, axis=1)
    d = d[d.groupby(["game_id", "key"]).pitch_id.transform("size") > 1]
    return [{"pitch_ids": g.pitch_id.tolist(), "px": g.px.tolist(), "pz": g.pz.tolist(), "velocity": g.velocity_kmh.tolist(),
             "type": g.pitch_type_kr.tolist(), "call": g.pitch_call_code.tolist()} for _, g in d.groupby(["game_id", "key"])]


def geometry(frame_rows: list[dict]) -> dict:
    """앞면 z와 중간·끝면 z의 차이(cm): pz를 두 면 높이에 그대로 대입할 때의 편향 크기."""
    diffs = []
    for r in frame_rows:
        if not r.get("trajectory_valid"):
            continue
        f, m, b = (_at_plane(r, y) for y in (17 / 12, zd.PLANE_Y_FT["mid"], zd.PLANE_Y_FT["back"]))
        if f and m and b:
            diffs.append((f[1] - max(m[1], b[1]), f[1] - min(m[1], b[1]), r.get("pitch_type") or ""))
    g = pd.DataFrame(diffs, columns=["top_bias", "bottom_bias", "type"])
    q = lambda s: [round(float(x), 2) for x in s.quantile([.05, .5, .95])]
    return {"front_minus_higher_plane_cm_p5_p50_p95": q(g.top_bias), "front_minus_lower_plane_cm_p5_p50_p95": q(g.bottom_bias),
            "by_type_median": g.groupby("type")[["top_bias", "bottom_bias"]].median().round(2).to_dict("index")}


def scenarios(out: Path) -> tuple[dict, pd.DataFrame]:
    rows, _ = ablation.load(ROOT, 2025)
    location = {r["pitch_id"]: r for r in load_rows(ROOT, "pitches", 2025, columns=["pitch_id", "px", "pz"])}
    rows = [{**r, "px": location[r["pitch_id"]]["px"], "pz": location[r["pitch_id"]]["pz"]} for r in rows]
    saved = zd.PLANE_LOCATION_TOLERANCE_CM
    zd.PLANE_LOCATION_TOLERANCE_CM = float("inf")               # za7.2: 궤적 그대로
    current = [{**r, **zd.judgment_plane_location(r)} for r in rows]
    zd.PLANE_LOCATION_TOLERANCE_CM = saved                        # za7.3: 불일치 성분 대체
    replaced = [{**r, **zd.judgment_plane_location(r)} for r in rows]
    ids = [r["pitch_id"] for r in rows]
    six = np.isin(ids, SIX)
    frame = pd.DataFrame({"pitch_id": ids, "game_id": [r["game_id"] for r in rows], "batter_id": [str(r["batter_id"]) for r in rows],
                          "batter_name": [r["batter_name"] for r in rows], "swing": [int(r["decision_type"] == "Swing") for r in rows],
                          "event": [r["event"] for r in rows]})
    for c in zd.PZONE_ABS:
        frame[c] = [r[c] for r in current]; frame[f"rep_{c}"] = [r[c] for r in replaced]
    dates = np.array(sorted({r["game_id"][:8] for r in rows}))
    index = {pid: i for i, pid in enumerate(ids)}
    for name in ("A", "B_direct", "B_full", "C_full"):
        frame[f"p_{name}"] = np.nan
    frame["p_swing"] = np.nan
    for block in np.array_split(dates, zd.CROSSFIT_FOLDS):
        held = set(block)
        pos = np.array([i for i, r in enumerate(rows) if r["game_id"][:8] in held])
        train_a = [current[i] for i in range(len(rows)) if rows[i]["game_id"][:8] not in held]
        train_b = [replaced[i] for i in range(len(rows)) if rows[i]["game_id"][:8] not in held]
        train_c = [r for r in train_a if r["pitch_id"] not in SIX]
        test_a, test_b = [current[i] for i in pos], [replaced[i] for i in pos]
        frame.loc[pos, "p_A"] = old.predict_pzone(train_a, test_a, zd.PZONE_ABS)
        frame.loc[pos, "p_B_direct"] = old.predict_pzone(train_a, test_b, zd.PZONE_ABS)   # 모델은 A, 입력만 대체
        frame.loc[pos, "p_B_full"] = old.predict_pzone(train_b, test_b, zd.PZONE_ABS)     # za7.3 그대로(재학습 포함)
        frame.loc[pos, "p_C_full"] = old.predict_pzone(train_c, test_a, zd.PZONE_ABS)     # 6구를 학습에서 뺌
        frame.loc[pos, "p_swing"] = ablation.propensity([rows[i] for i in range(len(rows)) if rows[i]["game_id"][:8] not in held],
                                                        [rows[i] for i in pos], *ablation.CANDIDATES["H1"])[0]
        print("  scenario block", len(pos), flush=True)
    frame["six"] = six
    return frame


def sbj(frame: pd.DataFrame) -> dict:
    def board(p, drop=None):
        j = 100 * (frame.swing - frame.p_swing) * (2 * p - 1)
        keep = ~drop if drop is not None else pd.Series(True, index=frame.index)
        g = pd.DataFrame({"b": frame.batter_id[keep], "j": j[keep]}).groupby("b").j.agg(["mean", "size"])
        g = g[g["size"] >= 300]
        return g["mean"], g["mean"].rank(ascending=False, method="min")
    six = frame.six
    boundary_cross = six & ((frame.p_A > .5) != (frame.p_B_direct > .5))
    cases = {
        "A_current_trajectory": board(frame.p_A),
        "B_px_direct_all_six": board(frame.p_A.where(~six, frame.p_B_direct)),
        "B_px_direct_crossing_four_only": board(frame.p_A.where(~boundary_cross, frame.p_B_direct)),
        "B_px_direct_other_two_only": board(frame.p_A.where(~(six & ~boundary_cross), frame.p_B_direct)),
        "B_px_full_retrained_za7_3": board(frame.p_B_full),
        "B_ripple_only_non_six": board(frame.p_B_full.where(~six, frame.p_A)),
        "C_exclude_six_scoring_only": board(frame.p_A, drop=six),
        "C_exclude_six_and_corrupt_pa_scoring_only": board(frame.p_A, drop=six | frame.pitch_id.str.startswith(CORRUPT_PA)),
        "C_exclude_six_retrained": board(frame.p_C_full, drop=six),
    }
    base, base_rank = cases["A_current_trajectory"]
    result = {}
    focus = sorted(set(frame.batter_id[six]))
    names = frame.drop_duplicates("batter_id").set_index("batter_id").batter_name
    for name, (score, rank) in cases.items():
        delta = (score - base.reindex(score.index)).dropna()
        result[name] = {"qualified": int(len(score)), "players_over_0_01pp": int((delta.abs() > .01).sum()),
                        "players_over_0_05pp": int((delta.abs() > .05).sum()), "max_abs_delta_pp": float(delta.abs().max()),
                        "focus": {f"{b} {names[b]}": {"za": round(float(score[b]), 4), "delta_pp": round(float(delta.get(b, 0.0)), 4),
                                                      "rank": int(rank[b]), "rank_before": int(base_rank[b])} for b in focus if b in score.index}}
    return result


def boundary_agreement(audit_dir: Path) -> dict:
    """audit.py의 테이크 판정 일치율을 경계(5cm 이내) 테이크로 한정해 다시 센다."""
    result = {}
    for season in (2024, 2025, 2026):
        d = pd.read_parquet(audit_dir / f"impact_{season}.parquet")
        takes = d[d.swing == 0]
        for label, sel in (("all_takes", pd.Series(True, index=takes.index)), ("boundary_takes", takes.boundary)):
            for cat, g in takes[sel].groupby(takes.category.where(takes.category.isin(["normal", "extreme_consistent"]), "suspect")):
                agree = lambda p: round(float(((p > .5) == (g.called_strike == 1)).mean()), 4)
                result.setdefault(str(season), {}).setdefault(label, {})[cat] = {
                    "takes": int(len(g)), "current": agree(g.p_zone), "anchored": agree(g.p_zone_alt), "front_model": agree(g.p_zone_front)}
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--out", required=True)
    parser.add_argument("--audit-dir", help="audit.py --out 디렉터리 (경계 테이크 판정 일치 재계산용)")
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    report = {"record_anomalies": {s: record_anomalies(s) for s in (2024, 2025, 2026)}}
    for s in (2024, 2025, 2026):
        report["record_anomalies"][s]["duplicate_groups"] = duplicate_groups(s)
    print(json.dumps(report["record_anomalies"], ensure_ascii=False)[:2000], flush=True)
    frame = scenarios(out)
    report["edges_2025"] = fits = edges(frame)
    report["geometry_2025"] = geometry(ablation.load(ROOT, 2025)[0])
    rows = load_rows(ROOT, "pitches", 2025, columns=["pitch_id", "game_id", "stadium", "inning", "inning_half", "balls_before", "strikes_before",
                                                     "outs_before", "pitcher_name", "batter_name", "pitch_type_kr", "velocity_kmh", "px", "pz",
                                                     "sz_top", "sz_bottom", "pitch_call_code", "description", "source_url", *TRAJ, "trajectory_valid",
                                                     "release_x_55", "pitcher_id"])
    curated = {r["pitch_id"]: r for r in rows}
    release_median = pd.DataFrame(rows).groupby(["game_id", "pitcher_id"]).release_x_55.median()
    table = []
    for pid in SIX:
        r, f = curated[pid], frame.set_index("pitch_id").loc[pid]
        raw = raw_pitch(pid)
        mid, back, front = (_at_plane(r, y) for y in (zd.PLANE_Y_FT["mid"], zd.PLANE_Y_FT["back"], 17 / 12))
        side_now = abs(f.x_mid_relative) * zd.PLATE_HALF_WIDTH_FT * CM_PER_FOOT
        side_rep = abs(f.rep_x_mid_relative) * zd.PLATE_HALF_WIDTH_FT * CM_PER_FOOT
        table.append({
            "pitch_id": pid, "game": pid[:13], "stadium": r["stadium"], "inning": f"{r['inning']}{'초' if r['inning_half'] == 'top' else '말'}",
            "pa": pid.split("-")[-2], "pitch_no": pid.split("-")[-1], "count_outs": f"{r['balls_before']}-{r['strikes_before']}, {r['outs_before']}아웃",
            "pitcher": r["pitcher_name"], "batter": r["batter_name"], "type": r["pitch_type_kr"], "velocity_kmh": r["velocity_kmh"],
            "swing": int(f.swing), "call_raw_r": raw.get("raw", {}).get("r"), "event": f.event,
            "raw_px_ft": raw.get("raw", {}).get("px"), "raw_pz_ft": raw.get("raw", {}).get("pz"), "sz_top_ft": r["sz_top"], "sz_bottom_ft": r["sz_bottom"],
            "traj_x_mid_cm": round(mid[0], 1), "traj_z_mid_cm": round(mid[1], 1), "traj_z_back_cm": round(back[1], 1),
            "x_mismatch_cm": round(mid[0] - r["px"] * CM_PER_FOOT, 1), "z_front_mismatch_cm": round(front[1] - r["pz"] * CM_PER_FOOT, 2),
            "release_x55_dev_from_game_median_cm": round(r["release_x_55"] - release_median[(r["game_id"], r["pitcher_id"])], 1),
            "side_cm_now": round(side_now, 1), "side_cm_px": round(side_rep, 1), "top_gap_cm": round(f.top_gap_cm, 1), "bottom_gap_cm": round(f.bottom_gap_cm, 1),
            "to_side_edge_cm_px": round(fits["side_cm"]["edge"] - side_rep, 1), "to_top_edge_cm": round(fits["top_gap_cm"]["edge"] - f.top_gap_cm, 1),
            "to_bottom_edge_cm": round(f.bottom_gap_cm - fits["bottom_gap_cm"]["edge"], 1),
            "p_zone_now": round(float(f.p_A), 3), "p_zone_px_direct": round(float(f.p_B_direct), 3), "p_zone_px_za7_3": round(float(f.p_B_full), 3),
            "edge_logistic_p_px": round(call_probability(fits, side_rep, f.top_gap_cm, f.bottom_gap_cm), 3),
            "p_swing": round(float(f.p_swing), 3), "vb_page": f"https://visualbaseball.com/game/{pid[:13]}/pbp",
        })
    report["six"] = table
    report["sbj_2025"] = sbj(frame)
    if args.audit_dir:
        report["take_call_agreement"] = boundary_agreement(Path(args.audit_dir))
    frame[frame.six].to_csv(out / "six_scenarios.csv", index=False)
    frame.to_parquet(out / "scenarios_2025.parquet", index=False)
    (out / "reaudit_2025.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("edges_2025", "geometry_2025", "sbj_2025")}, ensure_ascii=False, indent=1, default=str)[:6000])
    print(pd.DataFrame(table).T.to_string())


if __name__ == "__main__":
    main()
