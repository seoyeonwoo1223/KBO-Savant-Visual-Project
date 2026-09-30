"""Prioritised independent-verification sample (read-only). Deterministic picks."""
import pandas as pd, numpy as np
from pathlib import Path
from visualbaseball.curated import load_rows
import sys
R = Path(__file__).resolve().parents[2]; A = sys.argv[1]; W = Path(sys.argv[2])   # audit dir, experiment work dir
COLS = ["pitch_id","pa_id","game_id","inning","inning_half","batter_name","pitcher_name","pitch_number","pitch_call_code","velocity_kmh","pitch_type_kr","balls_before","strikes_before","outs_before","pa_result","stadium"]
picks = []
def seq(vb, pa):
    g = vb[vb.pa_id == pa]
    return " ".join(f"{int(n)}{str(c or '').upper()}{int(v) if pd.notna(v) else '?'}" for n, c, v in zip(g.pitch_number, g.pitch_call_code, g.velocity_kmh))
for s in (2024, 2025, 2026):
    vb = pd.DataFrame(load_rows(R, "pitches", s, columns=COLS)).sort_values(["game_id","pitch_id"])
    q = pd.read_csv(f"{A}/sbj_pitch_quality_{s}.csv.gz", dtype=str)
    e = pd.read_parquet(W / f"pzone_exp_{s}.parquet")[["pitch_id","B_za72","A_reported","event"]]
    d = vb.merge(q[["pitch_id","flags","review_level"] + (["tm_event","count_mismatch","run_kind","tm_balls_before","tm_strikes_before"] if s == 2024 else [])], on="pitch_id").merge(e, on="pitch_id", how="left")
    d["flags"] = d["flags"].fillna("")
    # PA order inside the half inning (1-based) so a viewer can find it in the relay
    first = d.groupby("pa_id").pitch_id.first().sort_values()
    order = d.drop_duplicates("pa_id")[["pa_id","game_id","inning","inning_half"]].sort_values("pa_id")
    order["pa_in_half"] = order.groupby(["game_id","inning","inning_half"]).cumcount() + 1
    d = d.merge(order[["pa_id","pa_in_half"]], on="pa_id")
    def add(rows, prio, why):
        for _, r in rows.iterrows():
            picks.append({"priority": prio, "why": why, "season": s, **{k: r[k] if k in r.index else None for k in ["pitch_id","game_id","stadium","inning","inning_half","pa_in_half","batter_name","pitcher_name","pitch_number","pitch_call_code","velocity_kmh","pitch_type_kr","balls_before","strikes_before","outs_before","pa_result","flags"]},
                          "tm_event": r.get("tm_event"), "tm_count": (f"{r.get('tm_balls_before')}-{r.get('tm_strikes_before')}" if s == 2024 and pd.notna(r.get("tm_balls_before")) else None),
                          "p_zone_za72": None if pd.isna(r.get("B_za72")) else round(float(r["B_za72"]), 3), "vb_pa_sequence": seq(vb, r["pa_id"]),
                          "naver_relay": f"https://m.sports.naver.com/game/{r['game_id']}{s}/relay"})
    if s == 2025:
        add(d[d.pa_id.isin(["20250809OBWO0-082","20250809OBWO0-083"]) & d.pitch_number.eq(1)], "P0", "김택연-임지열: 타석 분리·종료 후 행·위치 불일치(구조 오류 기준 사례). 타석 전체 캡처")
        add(d[d["flags"].str.contains("PLATE_X_DISAGREE") & ~d.game_id.eq("20250809OBWO0")], "P2", "보고 px와 궤적 x가 1m 이상 불일치: 행 혼합 여부")
    if s == 2024:
        bc = d[d["flags"].str.contains("B_NEAR_CENTER") & d.tm_event.eq("strike") & ~d["flags"].str.contains("DUP|SPLIT|CONT|MISMATCH|OPEN|HALF")]
        add(bc.sort_values("B_za72", ascending=False).drop_duplicates("game_id").head(6), "P1", "VB B·존 중심·TM 다음 카운트 스트라이크: 볼/루킹/헛스윙 판별")
        add(d[d.pitch_call_code.str.upper().eq("V") & d.tm_event.eq("strike")].drop_duplicates("game_id").head(4), "P1", "VB V 호출의 실제 행동(체크스윙·파울팁·기타)")
        cm = d[d.count_mismatch.eq("True") & d.run_kind.eq("equal_length") & ~d["flags"].str.contains("B_NEAR") ]
        prev_ok = cm[~cm.pa_id.isin(d[d.pitch_call_code.str.upper().isin(["V"]) | (d.pitch_call_code.str.upper().eq("B") & d.tm_event.eq("strike"))].pa_id)]
        add(prev_ok.drop_duplicates("pa_id").head(3), "P2", "카운트 불일치인데 앞선 B→TM스트라이크·V가 없는 경우: 원인 미상")
        add(d[d["flags"].str.contains("BB_CONT")].drop_duplicates("pa_id").head(2), "P2", "볼넷 뒤 투구 지속(BB_CONT): 볼 4개 뒤 타석 계속")
        ctl = d[d.run_kind.eq("equal_length") & d.count_mismatch.eq("False") & d.review_level.eq("none") & d.pitch_call_code.str.upper().eq("B") & d.tm_event.eq("ball")]
        add(ctl.sample(2, random_state=0), "C", "대조군: VB·TM 모두 볼, 플래그 없음 (판독 절차 확인용)")
    if s in (2025, 2026):
        add(d[d["flags"].str.contains("END_MISMATCH") & d.pitch_number.eq(1)].drop_duplicates("game_id").head(2), "P3", "TrackMan 없는 시즌의 결과 불일치 타석(END_MISMATCH)")
out = pd.DataFrame(picks); out.to_csv(W / "capture_list.csv", index=False)
print(len(out)); print(out[["priority","season","pitch_id","inning","inning_half","pa_in_half","batter_name","pitcher_name","pitch_number","pitch_call_code","tm_event","tm_count","p_zone_za72","vb_pa_sequence"]].to_string(index=False))
