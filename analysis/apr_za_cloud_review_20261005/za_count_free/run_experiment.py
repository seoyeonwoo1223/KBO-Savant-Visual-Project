"""ZA 전용 카운트 입력 제거. 사건·가치 모델과 운영 writer는 실행하지 않는다."""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import os
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

from visualbaseball import zone_decision as zd
from visualbaseball import plate_decision_v1 as old
from visualbaseball.batter_stance import resolved_batter_stance
from metrics import player_scores, score_summary

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = "6495992497af77df9abef861d235443a3302f130"
INPUTS = {}


def record(path):
    rel = str(path.relative_to(ROOT))
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    INPUTS[rel] = {"sha256": digest, "bytes": path.stat().st_size}
    return path


def json_input(path):
    return json.loads(record(ROOT/path).read_text())


def read_months(kind, year, columns):
    summary = json_input("data/curated/summary.json")
    frames = []
    for month in summary["seasons"][str(year)]["months"]:
        path = record(ROOT/f"data/curated/{kind}/season={year}/month={month}.parquet")
        # ParquetFile는 season= 등의 경로를 hive partition으로 다시 해석하지 않는다.
        frame = pq.ParquetFile(path).read(columns=columns)
        if "season" in columns:
            assert np.all(frame["season"].to_numpy() == year)
        else:
            assert all(str(g).startswith(str(year)) for g in frame["game_id"].to_pylist())
        frames.append(frame)
    import pyarrow as pa
    table = pa.concat_tables(frames)
    assert len(table) == summary["seasons"][str(year)]["tables"][kind]["rows"]
    return table.to_pylist()


def load_human(year):
    # 실제 자격·반이닝 신뢰도·상대 위치·손·구장 보정에 쓰는 컬럼만 읽는다.
    pitch_cols = ["game_id", "game_date", "event_seq", "season", "inning", "inning_half", "runs_on_pitch",
        "away_score_before", "away_score_after", "home_score_before", "home_score_after", "parse_status",
        "pitch_call_code", "is_pa_terminal", "pa_type", "pa_result", "px", "pz", "sz_top", "sz_bottom",
        "batter_id", "batter_name", "batter_team", "batter_stance", "pitcher_id", "release_x_50",
        "balls_before", "strikes_before", "outs_before", "base_state_code_before",
        "balls_after", "strikes_after", "outs_after", "base_state_code_after",
        "horizontal_movement_cm", "vertical_movement_cm", "pitch_type", "pitch_type_code", "pitch_type_kr",
        "stadium", "velocity_kmh", "release_height_cm"]
    event_cols = ["game_id", "inning", "inning_half", "event_seq", "event_code", "event_type", "parse_status",
        "runs_on_event", "away_score_before", "away_score_after", "home_score_before", "home_score_after"]
    rows = read_months("pitches", year, pitch_cols)
    events = read_months("events", year, event_cols)
    raw_n = len(rows)
    rows, quality = zd.reliable_halves(rows, events)
    bio = record(ROOT/"data/curated/players/player_bio.parquet")
    bios = pq.ParquetFile(bio).read(columns=["player_id", "bats", "throws"]).to_pylist()
    hands = {str(r["player_id"]): str(r.get("bats") or "") for r in bios}
    throws = {str(r["player_id"]): str(r.get("throws") or "") for r in bios}
    valid = []
    for r in rows:
        event = zd.outcome(r)
        if not zd._eligible(r) or not r.get("batter_id") or not r.get("batter_name") or event is None:
            continue
        r["x_relative"], r["z_relative"] = zd._relative_location(r)
        r["decision_type"] = "Swing" if event in zd.EVENTS[:3] else "Take"
        r["event"] = event
        r["batter_stance"] = resolved_batter_stance(r, hands)
        r["pitcher_throws"] = zd.pitcher_throws(r, throws)
        r["region"] = zd.region(r)
        valid.append(r)
    record(zd.park_workbook(ROOT, year))
    movement = old._movement_adjust(valid, ROOT, year)
    keep = set(zd.NUMERIC + old.PZONE_NUMERIC + zd.PZONE_ABS + zd.PSWING_CATEGORICAL +
               ("game_id", "game_date", "season", "batter_id", "batter_name", "batter_team", "event", "region", "decision_type"))
    keep.update(f"{k}_{w}" for k in ("base_state_code", "outs", "balls", "strikes") for w in ("before", "after"))
    valid = [{k: v for k, v in r.items() if k in keep} for r in valid]
    # 운영 loader와 같은 stable game_id 순서. DV용 보정은 p_swing에 사용되지 않아 생략한다.
    valid.sort(key=lambda r: r["game_id"])
    return valid, {"raw_rows": raw_n, "eligible_rows": len(valid), "quality": quality,
                   "movement": movement, "pitch_columns": pitch_cols, "event_columns": event_cols}


def propensity_only():
    """운영 fit_predict에서 propensity/보정 AST만 추출해 그대로 실행한다."""
    body = ast.parse(inspect.getsource(zd.fit_predict)).body[0].body
    start = next(i for i, node in enumerate(body) if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple)
                 and [n.id for n in node.targets[0].elts] == ["sa", "sb"])
    stop = next(i for i, node in enumerate(body) if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "probs")
    function = ast.parse("def policy(train, test, pzone_features, test_pzone, calibration=True):\n    pass\n").body[0]
    actions = next(node for node in body if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                   and node.targets[0].id == "actions")
    function.body = [actions] + body[start:stop] + [ast.parse("return p, raw_p").body[0]]
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    env = {"np": np, "encode": zd.encode, "fit_model": zd.fit_model, "pswing_classifier": zd.pswing_classifier,
           "predict_pzone": zd.predict_pzone, "GroupKFold": GroupKFold, "IsotonicRegression": IsotonicRegression,
           "PSWING_CATEGORICAL": zd.PSWING_CATEGORICAL}
    exec(compile(module, "<existing-propensity-path>", "exec"), env)
    return env["policy"]


def pzone_with_controls(train, test, fields):
    take = [r for r in train if r["decision_type"] == "Take"]
    y = np.array([str(r.get("pitch_call_code") or "").upper() == "T" or r["event"] == "CalledStrike" for r in take], int)
    x = old._encode_numeric(take, fields); xt = old._encode_numeric(test, fields)
    # 동일 위치의 카운트를 0-0/0-2로 바꾼 반사실 검산. fit 후에만 예측한다.
    sample = test[:min(500, len(test))]
    a = old._encode_numeric([dict(r, balls_before=0, strikes_before=0) for r in sample], fields)
    b = old._encode_numeric([dict(r, balls_before=3, strikes_before=2) for r in sample], fields)
    p = np.zeros(len(test)); pa = np.zeros(len(sample)); pb = pa.copy()
    for seed in zd.PZONE_SEEDS:
        model = old._classifier().set_params(random_state=seed).fit(x, y)
        col = list(model.classes_).index(1)
        p += model.predict_proba(xt)[:, col]
        pa += model.predict_proba(a)[:, col]; pb += model.predict_proba(b)[:, col]
    return np.clip(p/len(zd.PZONE_SEEDS), 1e-6, 1-1e-6), float(np.max(abs(pa-pb))/len(zd.PZONE_SEEDS))


def predictions(year):
    if year >= zd.ABS_FIRST_SEASON:
        path = record(ROOT/f"data/metrics/zone_awareness/{year}/pitches.parquet")
        cols = ["game_id", "game_date", "batter_id", "batter_name", "swing", "p_swing", "raw_p_swing", "p_zone",
                "region", "fold", "balls_before", "strikes_before", "event", *zd.PZONE_ABS]
        df = pq.ParquetFile(path).read(columns=cols).to_pandas().rename(columns={"p_zone": "q_call"})
        df["q_za"] = df.q_call.copy()
        return df, {"source": "저장된 운영 예측 재사용", "q_fields": list(zd.PZONE_ABS),
                    "q_count_control_max_error": 0., "ABS_noop_max_error": float(abs(df.q_call-df.q_za).max())}
    rows, meta = load_human(year)
    days_all = np.array(sorted({r["game_id"][:8] for r in rows}))
    block_metadata = [{"fold": f, "start": str(days[0]), "end": str(days[-1]),
                       "test_n": sum(r["game_id"][:8] in set(days) for r in rows)}
                      for f, days in enumerate(np.array_split(days_all, zd.CROSSFIT_FOLDS))]
    meta.update(q_fields=list(old.PZONE_NUMERIC), blocks=block_metadata)
    cache = OUT/"cache"/f"predictions_{year}.npz"
    key = hashlib.sha256(json.dumps({"inputs": INPUTS, "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "fields": zd.pzone_fields(year),
                                     "model": zd.MODEL_VERSION, "seeds": zd.PZONE_SEEDS}, sort_keys=True).encode()).hexdigest()
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        if str(z["input_key"]) == key:
            df = pd.DataFrame(rows); df["swing"] = (df.decision_type == "Swing").astype(int)
            for k in ("p_swing", "raw_p_swing", "q_call", "q_za", "fold"):
                df[k] = z[k]
            return df, {**meta, "q_count_control_max_error": float(z["count_control"]), "cache_used": True}
    df = pd.DataFrame(rows); df["swing"] = (df.decision_type == "Swing").astype(int)
    for name in ("p_swing", "raw_p_swing", "q_call", "q_za", "fold"):
        df[name] = np.nan
    dates = np.array(sorted({r["game_id"][:8] for r in rows})); policy = propensity_only(); controls = []; blocks = []
    assert not ({"balls_before", "strikes_before"} & set(old.PZONE_NUMERIC))
    for fold, days in enumerate(np.array_split(dates, zd.CROSSFIT_FOLDS)):
        held = set(days); mask = np.array([r["game_id"][:8] in held for r in rows])
        train = [r for r, selected in zip(rows, mask) if not selected]; test = [r for r, selected in zip(rows, mask) if selected]
        print(year, "날짜 블록", fold+1, "q_call 적합", len(train), len(test), flush=True)
        qcall, _ = pzone_with_controls(train, test, zd.pzone_fields(year))
        print(year, "날짜 블록", fold+1, "q_za 카운트 제거 적합", flush=True)
        qfree, err = pzone_with_controls(train, test, old.PZONE_NUMERIC)
        print(year, "날짜 블록", fold+1, "기존 p_swing 보정 재현", flush=True)
        p, raw = policy(train, test, zd.pzone_fields(year), qcall)
        for keyname, value in (("p_swing", p), ("raw_p_swing", raw), ("q_call", qcall), ("q_za", qfree), ("fold", fold)):
            df.loc[mask, keyname] = value
        controls.append(err); blocks.append({"fold": fold, "start": str(days[0]), "end": str(days[-1]), "test_n": len(test)})
    assert max(controls) < 1e-10
    cache.parent.mkdir(exist_ok=True)
    np.savez_compressed(cache, input_key=key, count_control=max(controls), **{n: df[n].to_numpy() for n in ("p_swing", "raw_p_swing", "q_call", "q_za", "fold")})
    return df, {**meta, "q_fields": list(old.PZONE_NUMERIC), "blocks": blocks, "q_count_control_max_error": max(controls), "cache_used": False}


def calibration(df):
    takes = df[df.swing == 0].copy(); y = (takes.event == "CalledStrike").to_numpy(float)
    result = {}
    boundary = takes.q_call.between(.1, .9)
    for key in ("q_call", "q_za"):
        p = takes[key].to_numpy(); loss = -(y*np.log(p)+(1-y)*np.log1p(-p))
        by_count = {}
        for label, mask in {"0_strike": takes.strikes_before == 0, "1_strike": takes.strikes_before == 1,
                            "2_strike": takes.strikes_before == 2, "3_ball": takes.balls_before == 3}.items():
            selected = (mask & boundary).to_numpy()
            by_count[label] = {"n": int(selected.sum()), "observed_minus_pred": float((y[selected]-p[selected]).mean()) if selected.any() else None}
        result[key] = {"take_n": len(takes), "log_loss": float(loss.mean()), "brier": float(np.mean((y-p)**2)),
                       "boundary_calibration": by_count}
    return result


def evaluate(year, df, meta):
    df["batter_id"] = df.batter_id.astype(str)
    p_before = hashlib.sha256(df.p_swing.to_numpy().tobytes()).hexdigest()
    t = player_scores(df)
    t = t.set_index("batter_id")
    public = pd.DataFrame(json_input(f"web/data/zone_awareness/{year}/leaderboard.json")["players"]).set_index("batter_id")
    # 외부 데이터와 섞지 않고 고정 기준의 같은 시즌 운영 집계만 비교한다.
    r = df.swing-df.p_swing
    sa = 100*r.groupby(df.batter_id).mean()
    za = 100*(r*(2*df.q_call-1)).groupby(df.batter_id).mean()
    sizes = df.groupby("batter_id").size()
    old_zj_se = 2*t.Z0_call_se*np.sqrt((t.n_games-1)/t.n_games)
    old_zj_se.loc[t.n_games == 1] = 0.
    baseline = {"same_player_set": set(public.index) == set(sizes.index),
                "pitches": int(len(df)), "public_pitches": int(public.pitches_seen.sum()),
                "max_player_n_error": float(abs(sizes-public.pitches_seen).max()),
                "SA_max_error": float(abs(sa-public.swing_aggression).max()),
                "ZA_raw_max_error": float(abs(za-public.za_raw).max()),
                "ZJ_SE_max_error": float(abs(old_zj_se-public.zj_se).max())}
    baseline["pass"] = baseline["same_player_set"] and baseline["max_player_n_error"] == 0 and max(baseline["SA_max_error"], baseline["ZA_raw_max_error"], baseline["ZJ_SE_max_error"]) < 1e-4
    baseline["prediction_refit_verified_pitchwise"] = year >= zd.ABS_FIRST_SEASON
    assert hashlib.sha256(df.p_swing.to_numpy().tobytes()).hexdigest() == p_before
    summary = score_summary(df)
    t.to_csv(OUT/f"players_{year}.csv", float_format="%.10f")
    return {"season": year, "metadata": meta, "baseline_reproduction": baseline, "p_swing_sha256": p_before,
            "p_swing_candidate_max_change": 0., "calibration": calibration(df), "scores": summary,
            "q_change": {"mean_absolute": float(abs(df.q_za-df.q_call).mean()), "max_absolute": float(abs(df.q_za-df.q_call).max()),
                         "side_flip_fraction": float(((df.q_za >= .5) != (df.q_call >= .5)).mean())}}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--seasons", nargs="+", type=int, default=[2022, 2023, 2026]); args = ap.parse_args()
    assert set(args.seasons) <= {2022, 2023, 2026}
    assert os.environ.get("OMP_NUM_THREADS") == "2" and os.environ.get("PYTHONPATH") == "src"
    constraints = record(ROOT/"constraints-za.txt").read_text()
    packages = {name: version(name) for name in ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy", "openpyxl")}
    for name, v in packages.items():
        assert f"{name}=={v}" in constraints
    for name in ("zone_decision.py", "plate_decision_v1.py", "swing_take.py", "batter_stance.py", "curated.py", "pitch_types.py"):
        p = record(ROOT/f"src/visualbaseball/{name}")
        expected = subprocess.check_output(["git", "show", f"{BASE}:{p.relative_to(ROOT)}"], cwd=ROOT)
        assert p.read_bytes() == expected
    summary = json_input("data/curated/summary.json"); json_input("data/curated/schema.json")
    for year in args.seasons:
        print(year, "자료/예측 준비", flush=True)
        df, metadata = predictions(year)
        result = evaluate(year, df, metadata)
        payload = {"base_commit": BASE, "preregistration_commit": "2036e4da", "model_version": zd.MODEL_VERSION,
                   "summary_generated_at": summary["generated_at"], "python": platform.python_version(), "packages": packages,
                   "OMP_NUM_THREADS": os.environ["OMP_NUM_THREADS"], "result": result, "inputs": INPUTS}
        (OUT/f"results_{year}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
        print(year, "종료", json.dumps(result["baseline_reproduction"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
