"""연구 입력·고정 helper·오차 정의를 공유한다. 운영 파일에는 쓰지 않는다."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
SEED = 20261007
BASE_SEED = 20261006
FF = ["height_m", "left_hand", "z55_over_height", "side55_over_height",
      "ff_speed55", "ff_armside_vx_over_minus_vy", "ff_vz_over_minus_vy",
      "ff_flight55_to_plate", "ff_movement_axis_arm_sin", "ff_movement_axis_up_cos", "ff_movement_size_m"]
SI_GEOMETRY = ["height_m", "left_hand", "type_SI_z55_over_height", "type_SI_side55_over_height"]
SI_PHYSICS = SI_GEOMETRY + ["type_SI_speed55", "type_SI_ivb_in", "type_SI_hb_arm_in"]
EXTRA = ["share_FF", "share_SI", "share_FC", "primary_share", "primary_hb_arm_in", "primary_ivb_in",
         "primary_minus_FF_z55_over_height", "primary_minus_FF_side55_over_height",
         "primary_minus_FF_ivb_in", "primary_minus_FF_hb_arm_in",
         "game_height_ivb", "game_side_hb", "game_pair_support"]
EXTRA += [a + "*" + b for a in ["share_SI", "share_FC"]
          for b in ["primary_hb_arm_in", "primary_ivb_in", "primary_minus_FF_ivb_in"]]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def save(name, value):
    def encode(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        raise TypeError(type(x).__name__)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                      allow_nan=False, default=encode) + "\n")


def legacy_helpers():
    """원판 helper의 SHA를 검증한 뒤 임시 폴더에서 불러온다."""
    manifest = json.loads((OUT / "inputs/source_manifest.json").read_text())
    archive = OUT / "inputs/frozen_helpers.zip"
    assert sha(archive) == manifest["frozen_helpers_sha256"]
    folder = Path(tempfile.gettempdir()) / ("eaa-frozen-" + sha(archive)[:16])
    folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            path = folder / name
            assert path.resolve().is_relative_to(folder.resolve())
            if not path.exists() or hashlib.sha256(z.read(name)).hexdigest() != sha(path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(z.read(name))
    sys.path[:0] = [str(folder / "src"), str(folder / "analysis/arm_angle")]
    from multi_pitch_eaa_models import ridge_fit
    from multi_pitch_eaa_features import training_weights
    from orthogonal_residual_eaa_models import base_matrix, fit_projection, apply_projection
    return ridge_fit, training_weights, base_matrix, fit_projection, apply_projection


def load(population, labelled=False):
    d = pd.read_parquet(OUT / "inputs" / (population + "_inputs.parquet"))
    assert "arm_angle" not in d
    if labelled:
        target = pd.read_parquet(OUT / "inputs" / (population + "_targets.parquet"))
        d = d.merge(target, on="row_id", how="left", validate="one_to_one")
    return d


def read_csv(path):
    return pd.read_csv(path, dtype={"pitcher": str}, float_precision="round_trip")


def eligible_si(d, require_label=False):
    result = d.primary4.eq("SI") & d.type_SI_count.ge(100) & d.n.ge(100)
    result &= np.isfinite(d[SI_PHYSICS]).all(axis=1)
    if require_label:
        result &= d.arm_angle.notna()
        if "label95" in d: result &= d.label95.fillna(False)
    return result


def evaluation_groups(d):
    result = {"all": np.ones(len(d), bool)}
    for g in ["FF", "SI"]: result[g] = d.primary4.eq(g).to_numpy()
    result["SI_IVB_le10"] = (d.primary4.eq("SI") & d.type_SI_ivb_in.le(10)).to_numpy()
    result["FF100"] = d.n_ff.ge(100).to_numpy()
    result["FFlow"] = d.n_ff.lt(100).to_numpy()
    if "arm_angle" in d:
        result["high60"] = d.arm_angle.ge(60).to_numpy()
        result["low20"] = d.arm_angle.lt(20).to_numpy()
    return result


def player_errors(d, prediction):
    error = np.asarray(prediction) - d.arm_angle.to_numpy()
    return pd.DataFrame({"pitcher": d.pitcher.to_numpy(), "MAE": abs(error),
                         "bias": error, "downside": np.maximum(-error, 0),
                         "upside": np.maximum(error, 0)}).groupby("pitcher").mean()


def metrics(d, prediction, groups=None):
    output = {}
    for name, mask in (evaluation_groups(d) if groups is None else groups).items():
        valid = np.asarray(mask) & np.isfinite(prediction) & d.arm_angle.notna().to_numpy()
        t = player_errors(d.loc[valid], np.asarray(prediction)[valid])
        record = {"rows": int(valid.sum()), "players": len(t), "players_under20": len(t) < 20}
        if len(t):
            record.update({key: float(t[key].mean()) for key in t})
            record["downside_tail20"] = float(t.downside.nlargest(max(1, int(np.ceil(len(t)*.2)))).mean())
        output[name] = record
    return output


def paired(d, reference, candidate, groups=None):
    output = {}
    for name, mask in (evaluation_groups(d) if groups is None else groups).items():
        valid = np.asarray(mask) & np.isfinite(reference) & np.isfinite(candidate) & d.arm_angle.notna().to_numpy()
        b = player_errors(d.loc[valid], np.asarray(reference)[valid])
        c = player_errors(d.loc[valid], np.asarray(candidate)[valid])
        record = {"rows": int(valid.sum()), "players": len(b), "players_under20": len(b) < 20}
        if len(b):
            rng = np.random.default_rng(SEED)
            indices = rng.integers(0, len(b), size=(2000, len(b)))
            for key in ["MAE", "downside", "upside"]:
                gain = b[key].to_numpy() - c[key].to_numpy()
                record[key + "_gain"] = {"mean": float(gain.mean()),
                    "bootstrap95": np.quantile(gain[indices].mean(axis=1), [.025, .975]).tolist() if len(b) >= 2 else None}
            bv, cv = b.bias.to_numpy(), c.bias.to_numpy()
            record["abs_population_bias_gain"] = {"mean": float(abs(bv.mean()) - abs(cv.mean())),
                "bootstrap95": np.quantile(abs(bv[indices].mean(axis=1))-abs(cv[indices].mean(axis=1)), [.025,.975]).tolist() if len(b)>=2 else None}
        output[name] = record
    return output
