"""EAA-TR1 검토 검산: 좌표 부호, 비행시간 정규화 항등식, 구종별 잔차 중심, 위치 입력의 기여.
새 후보·각도 계산이 아니다. 상대 패키지(tracking_rebuilt_20261009)는 읽기만 하며, 먼저 그 run.py로 로컬 캐시를 만들어야 한다."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import PolynomialFeatures, StandardScaler

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "analysis/arm_angle/tracking_rebuilt_20261009"
FT = .3048


def oof_mae(X, cols, y, idx, groups):
    x = np.column_stack([X[c] for c in cols])[idx]
    basis = PolynomialFeatures(2, include_bias=False).fit_transform(x)
    r = np.full((len(idx), 2), np.nan)
    for tr, te in GroupKFold(5).split(basis, groups=groups):
        c = pd.Series(groups[tr]).value_counts(); w = np.array([1/c[q] for q in groups[tr]]); w /= w.mean()
        s = StandardScaler().fit(basis[tr], sample_weight=w)
        m = Ridge(alpha=100).fit(s.transform(basis[tr]), y[idx[tr]], sample_weight=w)
        r[te] = y[idx[te]] - m.predict(s.transform(basis[te]))
    t = pd.DataFrame({"p": groups, "hb": abs(r[:, 0]), "ivb": abs(r[:, 1])}).groupby("p").mean()
    return r, {"hb_arm_MAE_cm": float(t.hb.mean()), "ivb_MAE_cm": float(t.ivb.mean())}


def main():
    d = pd.read_parquet(SRC / "inputs/selected_2026.parquet")
    f = pd.read_parquet(ROOT / ".cache/arm_angle/tracking_rebuilt_20261009/derived_pitches.parquet")
    assert (f.pitch_id.to_numpy() == d.pitch_id.to_numpy()).all()
    kind = d.pitch_type_code.replace({"FT": "SI"}); out = {}

    signs = {}
    for hand in ["Right", "Left"]:
        m = (kind == "FF") & f.basic_valid & (d.pitcher_hand == hand)
        signs[hand] = {"FF_pitches": int(m.sum()), **{c+"_median": float(f.loc[m, c].median()) for c in
                       ["x55_m", "vx55_mps", "armside55_over_height", "hb50_cm", "hb_arm_over_dt2_mps2", "armside_vx55_over_minus_vy"]}}
    out["sign_check_FF"] = signs

    out["flight_normalization_identity_max_abs_mps2"] = {p: float((f["movement%s_cm" % p]/100/(f.tfront_s-f["t%s_s" % p])**2
                                                                   - f.movement_over_dt2_mps2).abs().max()) for p in ["55", "50", "238", "10"]}

    o = (f.oof_fold >= 0).to_numpy(); centers = {}
    for k in ["FF", "SI"]:
        m = o & (kind == k).to_numpy()
        g = pd.DataFrame({"p": d.pitcher_id[m], "hb": f.location_oof_hb_arm_residual_cm[m],
                          "ivb": f.location_oof_ivb_residual_cm[m]}).groupby("p").mean()
        centers[k] = {"pitches": int(m.sum()), "players": len(g), "pitcher_equal_hb_arm_mean_cm": float(g.hb.mean()),
                      "pitcher_equal_ivb_mean_cm": float(g.ivb.mean())}
    out["residual_center_by_type"] = centers

    hand = d.pitcher_hand.map({"Right": 1., "Left": -1.}).to_numpy(float)
    top, bot = d.sz_top.to_numpy(float), d.sz_bottom.to_numpy(float)
    X = {"px": -hand*d.px.to_numpy(float)*FT, "pz": (d.pz.to_numpy(float)-(top+bot)/2)/((top-bot)/2),
         "speed": f.speed55_mps.to_numpy(), "height": d.height_cm.to_numpy(float)/100,
         "left": (hand < 0).astype(float), "si": d.pitch_type_code.isin(["FT", "SI"]).to_numpy(float)}
    y = np.column_stack([-hand*f.hb50_cm, f.ivb50_cm])
    idx = np.flatnonzero(o); groups = d.pitcher_id.to_numpy()[idx]
    r_full, full = oof_mae(X, list(X), y, idx, groups)
    _, no_loc = oof_mae(X, ["speed", "height", "left", "si"], y, idx, groups)
    ff = (d.pitch_type_code == "FF").to_numpy()[idx]
    out["location_contribution"] = {
        "reimplementation_max_abs_diff_cm": float(np.nanmax(abs(r_full - f[["location_oof_hb_arm_residual_cm", "location_oof_ivb_residual_cm"]].to_numpy()[idx]))),
        "with_location": full, "without_px_pz": no_loc,
        "FF_pitch_corr_px_arm_vs_hb_arm": float(np.corrcoef(X["px"][idx][ff], y[idx][ff, 0])[0, 1]),
        "FF_pitch_corr_pz_norm_vs_ivb": float(np.corrcoef(X["pz"][idx][ff], y[idx][ff, 1])[0, 1])}
    out["registered"] = False; out["new_candidate"] = False; out["angle_computed"] = False
    (Path(__file__).parent / "review_tr1.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
