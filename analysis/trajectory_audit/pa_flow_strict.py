"""VB–TrackMan 투구 단위 엄격 매칭으로 흐름 검증 수치를 다시 계산한다 (연구용, 데이터는 바꾸지 않음).

    PYTHONPATH=src python analysis/trajectory_audit/pa_flow_strict.py --out /tmp/paflow_strict

`pa_flow_audit.py`의 TrackMan 대조는 (경기, 이닝, 초/말, 타자) 키에서 투구 수가 같으면 순서로 붙이고
구속은 전체 중앙값만 봤다. 여기서는 볼·스트라이크 카운트를 매칭 조건에서 빼고(검증 대상이므로),
아래 독립 조건을 모두 통과한 모호하지 않은 쌍만 쓴다.

1. 경기: `build_trackman_id_crosswalk.map_games` (같은 날짜 투수 ID 집합 Jaccard, 모호·중복 경기 제외)
2. 선수: TrackMan 투수·타자 ID를 대응표(없으면 VB에 있는 같은 ID)로 VB ID로 옮긴다. 옮기지 못하면 탈락.
   대응표는 선수 단위(20구 이상, 양방향 90% 이상)라 투구 단위 카운트 오류에 좌우되지 않는다.
3. 구간(run): 반이닝 안에서 (투수, 타자)가 연속한 투구 묶음. VB 타석 분리·중복은 구간을 바꾸지 않는다.
   양쪽 반이닝의 구간 순서를 차례 맞춤(SequenceMatcher)으로 짝짓고, 짝이 없는 구간은 탈락.
4. 투구: 짝지은 구간 안에서 순서를 지키는 대응 중 모든 쌍이
   - 아웃 수(투구 전)가 같고
   - 구속 차(VB − TrackMan 릴리스)가 시즌 중앙값 ± TOL(기본 2.0km/h) 안인 것만 허용한다.
   투구 수가 같으면 대응은 하나뿐이고, 한 쌍이라도 조건을 어기면 구간 전체를 버린다.
   투구 수가 다르면(차이 3 이하) 가능한 대응을 모두 세어 정확히 하나일 때만 받고, 여럿이면 '모호', 없으면 '대응 없음'.

집계
- 카운트 불일치: 매칭 쌍에서 VB 파서 카운트(투구 전)가 TrackMan 카운트와 다른 투구
- 호출 대조: 매칭 쌍 i와 TrackMan 다음 투구 i+1이 같은 TrackMan 타석이고 i+1도 매칭된 경우,
  TrackMan 카운트 변화(볼 +1 / 스트라이크 +1 / 변화 없음)와 VB 호출 코드의 교차표.
  TrackMan 카운트 변화는 실제 행동(헛스윙·루킹)이나 어느 기록이 옳은지를 알려 주지 않는다.
- 2024년 존 중심(d ≤ 0.8) VB B: 분모, 매칭 품질, 탈락 사유를 함께 기록한다.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from visualbaseball.curated import load_rows

ROOT = Path(__file__).resolve().parents[2]
SEASONS = tuple(range(2019, 2025))
TOL = 2.0   # --tol로 바꿀 수 있다
MAX_GAP = 3
VB_COLS = ["pitch_id", "pa_id", "game_id", "inning", "inning_half", "game_pitch_number", "pitcher_id", "batter_id",
           "outs_before", "balls_before", "strikes_before", "pitch_call_code", "velocity_kmh", "pitch_type_kr",
           "px", "pz", "sz_top", "sz_bottom", "pa_result"]
VB_GROUP = {"포심": "fastball", "투심": "fastball", "슬라이더": "breaking", "커브": "breaking", "체인지업": "offspeed", "포크": "offspeed"}


HBP_IBB = ("사구", "고의사")
STRIKEOUT = ("삼진", "WP", "PB")


def pa_consistent(codes: list[str], result: str, v_is_strike: bool = True) -> bool | None:
    """VB 한 타석의 호출 코드 흐름이 결과 문구와 맞는지 (cap 없이). 결과가 없으면 None.

    TrackMan을 쓰지 않는 VB 내부 근거다. V는 v_is_strike면 파울처럼(2스트라이크 전까지) 센다.
    """
    if not result:
        return None
    balls = strikes = 0
    for i, c in enumerate(codes):
        last = i == len(codes) - 1
        if not last and ((c in ("S", "T") and strikes >= 2) or (c == "B" and balls >= 3) or c == "X"):
            return False
        if last:
            break
        balls += c == "B"; strikes += c in ("S", "T") or (c in ("F",) + (("V",) if v_is_strike else ()) and strikes < 2)
    c = codes[-1]
    if any(t in result for t in STRIKEOUT):
        return c in ("S", "T", "F", "V") and strikes >= 2
    if "볼넷" in result:
        return c == "B" and balls >= 3
    if any(t in result for t in HBP_IBB):
        return True
    return c == "X"


def internal_evidence(vb: pd.DataFrame, pitch_ids) -> pd.Series:
    """해당 B를 스트라이크로 바꿨을 때 VB 타석 흐름이 어떻게 되는지로 분류한다."""
    codes = vb.groupby("pa_id").pitch_call_code.agg(lambda c: [str(x or "").upper() for x in c])
    result = vb.groupby("pa_id").pa_result.first().fillna("")
    number = vb.set_index("pitch_id")
    out = {}
    for pid in pitch_ids:
        pa = number.pa_id[pid]; seq = codes[pa]; k = int(pid[-2:]) - 1
        recoded = seq[:k] + ["T"] + seq[k + 1:]
        a, b = pa_consistent(seq, result[pa]), pa_consistent(recoded, result[pa])
        out[pid] = ("no_result" if a is None else "vb_flow_supports_strike" if (not a and b) else "vb_flow_supports_ball" if (a and not b)
                    else "vb_flow_undecided" if (a and b) else "vb_flow_broken_either_way")
    return pd.Series(out)


def _crosswalk():
    spec = importlib.util.spec_from_file_location("crosswalk", ROOT / "scripts" / "build_trackman_id_crosswalk.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def agreement(frame: pd.DataFrame) -> float | None:
    """구종군 일치율(커터·너클 등 군을 정하지 않은 VB 구종은 뺀다). 매칭 품질의 보조 지표."""
    known = frame[frame.vb_group.notna()]
    return round(float((known.vb_group == known.tm_pitch_type_group).mean()), 4) if len(known) else None


def zone_distance(d: pd.DataFrame) -> pd.Series:
    center = (d.sz_top.astype(float) + d.sz_bottom.astype(float)) / 2
    half = (d.sz_top.astype(float) - d.sz_bottom.astype(float)) / 2
    return np.maximum((d.px.astype(float) / (10 / 12)).abs(), ((d.pz.astype(float) - center) / half).abs())


def load(season: int):
    cw = _crosswalk()
    vb = pd.DataFrame(load_rows(ROOT, "pitches", season, columns=VB_COLS))
    vb = vb.rename(columns={"inning_half": "half"}).sort_values(["game_id", "game_pitch_number"]).reset_index(drop=True)
    vb["inning"] = vb.inning.astype(int)
    for c in ("pitcher_id", "batter_id"):
        vb[c] = vb[c].astype(str)
    tm = cw._trackman(ROOT, season)
    games = cw.map_games(tm, cw._visualbaseball(ROOT, season))
    tm = tm[tm.trackman_game_id.isin(games)].copy()
    tm["game_id"] = tm.trackman_game_id.map(games)
    tm["inning"] = tm.inning.astype(int)
    tm["rel_speed"] = pd.to_numeric(tm.rel_speed, errors="coerce")
    roles = json.loads((ROOT / "data/tracking/player_id_crosswalk.json").read_text(encoding="utf-8"))["seasons"][str(season)]["roles"]
    for role, col in (("pitcher", "pitcher_trackman_id"), ("batter", "batter_trackman_id")):
        lookup = {p["trackman_id"]: p["visualbaseball_id"] for p in roles[role]["pairs"]}
        known = set(vb[f"{role}_id"])
        tm[f"{role}_id"] = tm[col].astype(str).map(lambda t: lookup.get(t, t if t in known else None))
    tm = tm.sort_values(["game_id", "pitch_no"]).reset_index(drop=True)
    return vb, tm, set(games.values())


def runs(frame: pd.DataFrame) -> list[tuple[tuple, np.ndarray]]:
    key = list(zip(frame.pitcher_id, frame.batter_id))
    out, start = [], 0
    for i in range(1, len(key) + 1):
        if i == len(key) or key[i] != key[start]:
            out.append((key[start], frame.index.to_numpy()[start:i])); start = i
    return out


class Lost(Counter):
    """탈락한 VB 투구 수를 사유별로 세고, 투구(행 번호)별 사유도 남긴다."""

    def __init__(self):
        super().__init__(); self.reason = {}

    def add(self, reason, ids):
        ids = list(ids); self[reason] += len(ids); self.reason.update(dict.fromkeys(ids, reason))


def candidate_runs(vb: pd.DataFrame, tm: pd.DataFrame, games: set) -> tuple[list, "Lost"]:
    """반이닝별 구간을 짝짓는다. 짝이 없는 VB 투구는 사유별로 센다."""
    lost = Lost()
    lost.add("game_unmapped", vb.index[~vb.game_id.isin(games)])
    pairs = []
    tm_halves = dict(tuple(tm.groupby(["game_id", "inning", "half"], sort=False)))
    for key, v in vb[vb.game_id.isin(games)].groupby(["game_id", "inning", "half"], sort=False):
        t = tm_halves.get(key)
        if t is None:
            lost.add("half_inning_missing_in_trackman", v.index); continue
        vr, tr = runs(v), runs(t)
        vk = [k for k, _ in vr]; tk = [k if None not in k else ("?", i) for i, (k, _) in enumerate(tr)]
        for op, a0, a1, b0, b1 in SequenceMatcher(None, vk, tk, autojunk=False).get_opcodes():
            if op == "equal":
                pairs.extend((vr[a0 + i][1], tr[b0 + i][1]) for i in range(a1 - a0))
            else:
                unresolved = any("?" == tk[j][0] for j in range(b0, b1))
                for i in range(a0, a1):
                    lost.add("run_unresolved_trackman_id" if unresolved else "run_sequence_mismatch", vr[i][1])
    return pairs, lost


def compatible(vb, tm, vi, ti, offset):
    a, b = vb.velocity_kmh.iat[vi], tm.rel_speed.iat[ti]
    if pd.isna(a) or pd.isna(b):
        return "velocity_missing"
    if int(vb.outs_before.iat[vi]) != int(tm.outs_before.iat[ti]):
        return "outs_mismatch"
    return None if abs(float(a) - float(b) - offset) <= TOL else "velocity_out_of_tolerance"


def match(vb: pd.DataFrame, tm: pd.DataFrame, pairs: list, lost: Counter, offset: float) -> tuple[pd.DataFrame, dict]:
    matched, runs_stat = [], Counter()
    vpos = {ix: i for i, ix in enumerate(vb.index)}; tpos = {ix: i for i, ix in enumerate(tm.index)}
    for v_ix, t_ix in pairs:
        vi = [vpos[x] for x in v_ix]; ti = [tpos[x] for x in t_ix]
        n, m = len(vi), len(ti)
        if n == m:
            reasons = [compatible(vb, tm, a, b, offset) for a, b in zip(vi, ti)]
            bad = [r for r in reasons if r]
            if bad:
                lost.add(Counter(bad).most_common(1)[0][0], vi); runs_stat["rejected_equal_length"] += 1; continue
            matched.extend((a, b, "equal_length") for a, b in zip(vi, ti)); runs_stat["accepted_equal_length"] += 1
            continue
        if abs(n - m) > MAX_GAP:
            lost.add("length_gap_gt3", vi); runs_stat["rejected_gap"] += 1; continue
        short, long_, vb_short = (vi, ti, True) if n < m else (ti, vi, False)
        feasible = []
        for pick in combinations(range(len(long_)), len(short)):
            pair = [(short[k], long_[p]) if vb_short else (long_[p], short[k]) for k, p in enumerate(pick)]
            if all(compatible(vb, tm, a, b, offset) is None for a, b in pair):
                feasible.append(pair)
                if len(feasible) > 1:
                    break
        if len(feasible) == 1:
            kind = "gap_vb_extra" if n > m else "gap_tm_extra"
            matched.extend((a, b, kind) for a, b in feasible[0]); runs_stat[f"accepted_{kind}"] += 1
            used = {a for a, _ in feasible[0]}
            lost.add(f"unpaired_in_{kind}", [a for a in vi if a not in used])
        else:
            lost.add("ambiguous_alignment" if feasible else "no_feasible_alignment", vi)
            runs_stat["rejected_" + ("ambiguous" if feasible else "infeasible")] += 1
    m = pd.DataFrame(matched, columns=["vi", "ti", "run_kind"])
    return m, dict(runs_stat)


def season_offset(vb, tm, pairs) -> float:
    vpos = {ix: i for i, ix in enumerate(vb.index)}; tpos = {ix: i for i, ix in enumerate(tm.index)}
    diffs = []
    for v_ix, t_ix in pairs:
        if len(v_ix) == len(t_ix):
            diffs.extend(vb.velocity_kmh.iat[vpos[a]] - tm.rel_speed.iat[tpos[b]] for a, b in zip(v_ix, t_ix))
    return float(np.nanmedian(np.asarray(diffs, dtype=float)))


def analyse(season: int, out: Path, loose: dict, loose_dir: str | None) -> dict:
    vb, tm, games = load(season)
    pairs, lost = candidate_runs(vb, tm, games)
    offset = season_offset(vb, tm, pairs)
    m, runs_stat = match(vb, tm, pairs, lost, offset)
    p = pd.concat([vb.iloc[m.vi].reset_index(drop=True).add_prefix("vb_"), tm.iloc[m.ti].reset_index(drop=True).add_prefix("tm_"), m[["run_kind", "ti"]]], axis=1)
    p["dv"] = p.vb_velocity_kmh.astype(float) - p.tm_rel_speed - offset
    p["vb_group"] = p.vb_pitch_type_kr.map(VB_GROUP)
    p["count_mismatch"] = (p.vb_balls_before.astype(int) != p.tm_balls_before.astype(int)) | (p.vb_strikes_before.astype(int) != p.tm_strikes_before.astype(int))
    # TrackMan 다음 투구(같은 타석, 역시 매칭됨)로 본 카운트 변화
    matched_ti = set(m.ti)
    nxt = tm.shift(-1)
    t_idx = p.ti.to_numpy()
    same_pa = ((nxt.game_id.to_numpy()[t_idx] == tm.game_id.to_numpy()[t_idx]) & (nxt.pitch_of_pa.to_numpy()[t_idx] == tm.pitch_of_pa.to_numpy()[t_idx] + 1)
               & (nxt.batter_trackman_id.to_numpy()[t_idx] == tm.batter_trackman_id.to_numpy()[t_idx]))
    p["has_transition"] = same_pa & np.array([t + 1 in matched_ti for t in t_idx])
    db = nxt.balls_before.to_numpy()[t_idx] - tm.balls_before.to_numpy()[t_idx]
    ds = nxt.strikes_before.to_numpy()[t_idx] - tm.strikes_before.to_numpy()[t_idx]
    p["tm_event"] = np.where(~p.has_transition, "", np.select([(db == 1) & (ds == 0), (db == 0) & (ds == 1), (db == 0) & (ds == 0)], ["ball", "strike", "none"], "other"))
    p["code"] = p.vb_pitch_call_code.fillna("").str.upper()
    tr = p[p.has_transition]
    cross = pd.crosstab(tr.code, tr.tm_event)
    b = tr[tr.code == "B"]; v = tr[tr.code == "V"]
    total = len(vb)
    entry = {
        "vb_pitches": total, "vb_pitches_in_mapped_games": int(vb.game_id.isin(games).sum()),
        "velocity_offset_kmh": round(offset, 2), "tolerance_kmh": TOL,
        "matched": int(len(p)), "matched_share": round(len(p) / total, 4),
        "matched_by_kind": {k: int(n) for k, n in p.run_kind.value_counts().items()},
        "lost_vb_pitches_by_reason": {k: int(n) for k, n in sorted(lost.items(), key=lambda x: -x[1])},
        "runs": runs_stat,
        "abs_dv_p50_p95_max": [round(float(x), 2) for x in p.dv.abs().quantile([.5, .95, 1]).to_numpy()],
        "pitch_group_agreement": agreement(p),
        "count_mismatch": {"pitches": int(p.count_mismatch.sum()), "denominator": int(len(p)), "rate": round(float(p.count_mismatch.mean()), 4)},
        "transitions": int(len(tr)),
        "code_vs_tm_event": {code: {k: int(n) for k, n in row.items() if n} for code, row in cross.iterrows()},
        "B_to_tm_strike": {"pitches": int((b.tm_event == "strike").sum()), "denominator_B_transitions": int(len(b)), "rate": round(float((b.tm_event == "strike").mean()), 4)},
        "V_to_tm_strike": {"pitches": int((v.tm_event == "strike").sum()), "denominator_V_transitions": int(len(v))},
        "loose": loose.get(str(season)),
    }
    # 존 중심 VB B
    vb["dist"] = zone_distance(vb)
    tr_d = tr.merge(vb[["pitch_id", "dist"]], left_on="vb_pitch_id", right_on="pitch_id")
    entry["inzone_share_by_code_event"] = {f"{c}_{e}": {"n": int(len(g)), "inzone": round(float((g.dist <= 1).mean()), 3)}
                                           for (c, e), g in tr_d.groupby(["code", "tm_event"]) if len(g) >= 20 and c in ("B", "T", "S", "V")}
    near = vb[(vb.pitch_call_code.fillna("").str.upper() == "B") & (vb.dist <= 0.8)]
    pos = {ix: i for i, ix in enumerate(vb.index)}
    pn = p[p.vb_pitch_id.isin(near.pitch_id)]
    pt = pn[pn.has_transition]
    unmatched = near[~near.pitch_id.isin(p.vb_pitch_id)]
    reason_of = lambda ids: {k: int(n) for k, n in Counter(lost.reason.get(pos[i], "unknown") for i in ids).most_common()}
    entry["B_near_center_0.8"] = {
        "all_vb": int(len(near)), "matched": int(len(pn)), "matched_with_transition": int(len(pt)),
        "matched_without_transition": int(len(pn) - len(pt)), "unmatched": int(len(unmatched)),
        "unmatched_by_reason": reason_of(unmatched.index),
        "tm_event": {k: int(n) for k, n in pt.tm_event.value_counts().items()},
        "precision_tm_strike": round(float((pt.tm_event == "strike").mean()), 4) if len(pt) else None,
        "abs_dv_p50_p95_max": [round(float(x), 2) for x in pt.dv.abs().quantile([.5, .95, 1]).to_numpy()] if len(pt) else None,
        "pitch_group_agreement": agreement(pt),
    }
    loose_ids = Path(loose_dir) / f"b_called_strike_by_trackman_{season}.csv" if loose_dir else Path("/nonexistent")
    if loose_ids.exists():
        old = pd.read_csv(loose_ids)
        old_near = old[old.dist <= 0.8]
        s = p.set_index("vb_pitch_id")
        kept = old_near.pitch_id.isin(s.index)
        with_tr = old_near.pitch_id.map(lambda x: bool(s.has_transition.get(x, False)))
        ev = old_near.pitch_id.map(lambda x: s.tm_event.get(x, ""))
        by_id = pd.Series(vb.index, index=vb.pitch_id)
        dropped = old_near[~kept].pitch_id.map(by_id)
        entry["loose_near_center_strike_cases"] = {"loose_cases": int(len(old_near)), "strict_matched": int(kept.sum()),
                                                   "dropped_by_reason": reason_of(dropped),
                                                   "strict_with_transition": int(with_tr.sum()),
                                                   "strict_tm_event": {k: int(n) for k, n in ev[with_tr].value_counts().items()}}
    # 불일치 첫 발생 원인: 같은 TrackMan 타석에서 바로 앞 TrackMan 투구가 매칭돼 있고 카운트가 맞았던 경우만 원인을 붙인다
    p = p.sort_values("ti").reset_index(drop=True)
    onset = Counter()
    prev = None
    for r in p.itertuples():
        if r.count_mismatch:
            adjacent = prev is not None and prev.ti == r.ti - 1 and int(r.tm_pitch_of_pa) == int(prev.tm_pitch_of_pa) + 1
            if not adjacent:
                onset["first_pitch_of_tm_pa" if int(r.tm_pitch_of_pa) == 1 else "after_unmatched_pitch"] += 1
            elif not prev.count_mismatch:
                onset["vb_pa_split" if r.vb_pa_id != prev.vb_pa_id else f"prev_vb_{prev.code or '?'}_tm_{prev.tm_event or 'n/a'}"] += 1
        prev = r
    entry["mismatch_onset"] = {k: int(n) for k, n in onset.most_common(12)}
    # VB 내부 근거: B→TrackMan 스트라이크 사례, V가 든 타석
    bs = p[(p.code == "B") & (p.tm_event == "strike")]
    ev = internal_evidence(vb, bs.vb_pitch_id)
    entry["B_to_tm_strike_vb_internal"] = {k: int(n) for k, n in ev.value_counts().items()}
    pb = p[(p.code == "B") & (p.tm_event == "ball")].sample(n=min(5000, int(((p.code == "B") & (p.tm_event == "ball")).sum())), random_state=0)
    entry["B_to_tm_ball_vb_internal_sample5000"] = {k: int(n) for k, n in internal_evidence(vb, pb.vb_pitch_id).value_counts().items()}
    codes = vb.groupby("pa_id").pitch_call_code.agg(lambda c: [str(x or "").upper() for x in c])
    result = vb.groupby("pa_id").pa_result.first().fillna("")
    v_pas = codes[codes.map(lambda c: "V" in c)].index
    entry["V_pa_consistency"] = {"pas_with_V": int(len(v_pas)),
                                 "consistent_if_V_strike": int(sum(pa_consistent(codes[x], result[x], True) is True for x in v_pas)),
                                 "consistent_if_V_ignored": int(sum(pa_consistent(codes[x], result[x], False) is True for x in v_pas)),
                                 "no_result": int(sum(not result[x] for x in v_pas))}
    p = p.merge(ev.rename("vb_internal"), left_on="vb_pitch_id", right_index=True, how="left")
    if season == 2024:
        naver_candidates(vb, tm, p, out)
    cols = ["vb_pitch_id", "vb_pa_id", "vb_pa_result", "code", "vb_velocity_kmh", "tm_rel_speed", "dv", "vb_pitch_type_kr", "tm_tagged_pitch_type",
            "vb_balls_before", "vb_strikes_before", "tm_balls_before", "tm_strikes_before", "tm_event", "run_kind", "vb_internal"]
    p[(p.code == "B") & (p.tm_event == "strike")].merge(vb[["pitch_id", "dist"]], left_on="vb_pitch_id", right_on="pitch_id").drop(columns="pitch_id")[cols + ["dist"]].to_csv(out / f"strict_b_tm_strike_{season}.csv", index=False)
    p[p.code == "V"][cols].to_csv(out / f"strict_v_{season}.csv", index=False)
    p[["vb_pitch_id", "count_mismatch", "tm_event", "code", "dv", "run_kind"]].to_csv(out / f"strict_pairs_{season}.csv.gz", index=False)
    return entry


def naver_candidates(vb, tm, p, out):
    """네이버 중계로 직접 확인할 표본: B→TrackMan 스트라이크(VB 내부 근거별·존 안팎)와 V."""
    names = pd.DataFrame(load_rows(ROOT, "pitches", 2024, columns=["pitch_id", "batter_name", "pitcher_name"]))
    d = p.merge(vb[["pitch_id", "dist"]], left_on="vb_pitch_id", right_on="pitch_id").merge(names, on="pitch_id")
    picks = []
    bs = d[(d.code == "B") & (d.tm_event == "strike")]
    for label, sel in (("B·VB흐름이 스트라이크 지지·존 안", (bs.vb_internal == "vb_flow_supports_strike") & (bs.dist <= 0.8)),
                       ("B·VB흐름이 스트라이크 지지·존 밖", (bs.vb_internal == "vb_flow_supports_strike") & (bs.dist > 1.2)),
                       ("B·흐름 판별 불가·존 안(d≤0.8)", (bs.vb_internal == "vb_flow_undecided") & (bs.dist <= 0.8)),
                       ("B·흐름 판별 불가·존 밖", (bs.vb_internal == "vb_flow_undecided") & (bs.dist > 1.2))):
        picks.append(bs[sel].sort_values("vb_pitch_id").head(2).assign(case=label))
    vv = d[d.code == "V"]
    picks.append(vv[vv.vb_pa_result.fillna("").str.contains("삼진")].sort_values("vb_pitch_id").head(2).assign(case="V·삼진 타석"))
    picks.append(vv[~vv.vb_pa_result.fillna("").str.contains("삼진")].sort_values("vb_pitch_id").head(2).assign(case="V·그 밖 타석"))
    c = pd.concat(picks)
    seq = vb.groupby("pa_id").apply(lambda g: " ".join(f"{int(n[-2:])}{str(x or '').upper()}{int(v)}" for n, x, v in zip(g.pitch_id, g.pitch_call_code, g.velocity_kmh)))
    c["vb_pa_sequence"] = c.vb_pa_id.map(seq)
    c["naver_relay"] = "https://m.sports.naver.com/game/" + c.vb_pitch_id.str[:13] + "2024/relay"
    c[["case", "vb_pitch_id", "batter_name", "pitcher_name", "code", "vb_velocity_kmh", "tm_rel_speed", "vb_pitch_type_kr", "tm_tagged_pitch_type",
       "vb_balls_before", "vb_strikes_before", "tm_balls_before", "tm_strikes_before", "dist", "vb_pa_result", "vb_pa_sequence", "vb_internal", "naver_relay"]
      ].to_csv(out / "naver_candidates_2024.csv", index=False)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--out", required=True)
    parser.add_argument("--seasons", nargs="+", type=int, default=list(SEASONS))
    parser.add_argument("--tol", type=float, default=TOL, help="구속 차 허용폭(km/h, 시즌 중앙값 기준)")
    parser.add_argument("--loose-dir", help="pa_flow_audit.py 출력 디렉터리 (순서 연결 방식의 B→스트라이크 목록 비교용)")
    parser.add_argument("--loose-summary", default=str(ROOT / "analysis/trajectory_audit/results/pa_flow_summary.json"))
    args = parser.parse_args()
    globals()["TOL"] = args.tol
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    loose_all = json.loads(Path(args.loose_summary).read_text(encoding="utf-8"))
    loose = {s: {"count_mismatch_pitches": e["trackman"]["calls"]["count_mismatch_pitches"], "aligned_pitches": e["trackman"]["calls"]["aligned_pitches"],
                 "B_to_tm_strike": e["trackman"]["calls"]["code_vs_tm_event"]["B"].get("strike", 0),
                 "B_transitions": sum(e["trackman"]["calls"]["code_vs_tm_event"]["B"].values()),
                 "V_to_tm_strike": e["trackman"]["calls"]["code_vs_tm_event"].get("V", {}).get("strike", 0)}
             for s, e in loose_all.items() if e.get("trackman")}
    summary = {}
    for season in args.seasons:
        summary[season] = analyse(season, out, loose, args.loose_dir)
        print(season, json.dumps(summary[season], ensure_ascii=False), flush=True)
    (out / "pa_flow_strict_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
