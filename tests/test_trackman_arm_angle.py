"""Geometry, identity safety, missingness, and research-output boundaries."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from visualbaseball.trackman_arm_angle import (
    Assumptions, HEIGHT_COLUMNS, TM_COLUMNS, collect_heights, elevation_3d,
    frontal_angle, load_height_table, load_season, parse_kbo_profile, run, score,
    validate_reference,
)


def frame(height=180.):
    return pd.DataFrame({"rel_side": [.60, -.60, .60], "rel_height": [1.80, 1.80, .50],
                         "extension": [1.8, 1.8, 1.8], "height_cm": [height]*3,
                         "pitcher_hand": ["Right", "Left", "Right"]})


def test_measured_frontal_geometry_is_symmetric_and_signed():
    np.testing.assert_allclose(frontal_angle([.7, -.7, .7], [1.8, 1.8, .8], [.2, -.2, .2], 1.3), [45, 45, -45])
    assert np.isnan(frontal_angle(.2, 1.3, .2, 1.3))
    assert frontal_angle(.2, 1.8, .2, 1.3) == 90


def test_extension_affects_3d_but_not_frontal():
    a = score(frame())
    other = frame(); other["extension"] = [.8, 2.8, np.nan]
    b = score(other)
    np.testing.assert_allclose(a.estimated_frontal_deg, b.estimated_frontal_deg)
    assert a.extension_height_ratio.iat[0] != b.extension_height_ratio.iat[0]
    angles = elevation_3d(.7, 1.8, [1.5, 2.], .2, 1.3, 1.5)
    np.testing.assert_allclose(angles, [45, np.degrees(np.arctan2(.5, np.sqrt(.5)))])
    assert np.isnan(elevation_3d(.7, 1.8, 1.5, .2, 1.3, np.nan))


def test_missing_heights_never_receive_population_default():
    scored = score(frame(np.nan))
    assert scored.estimated_frontal_deg.isna().all()
    assert scored.scenario_low_deg.isna().all()
    assert scored.extension_height_ratio.isna().all()
    assert scored.fixed_130cm_proxy_deg.notna().all()
    assert set(scored.estimate_status) == {"missing_height"}


def test_personalized_symmetry_and_range():
    scored = score(frame())
    assert scored.estimated_frontal_deg.iat[0] == scored.estimated_frontal_deg.iat[1]
    assert scored.estimated_frontal_deg.iat[2] < 0
    assert scored.estimated_frontal_deg.between(scored.scenario_low_deg, scored.scenario_high_deg).all()
    assert scored.scenario_low_deg.between(-90, 90).all()
    assert scored.scenario_high_deg.between(-90, 90).all()


def test_sensitivity_includes_interior_lateral_alignment():
    f = frame(); f["rel_side"] = [.18, -.18, .18]
    scored = score(f)
    assert scored.scenario_high_deg.iat[0] == 90
    assert scored.scenario_low_deg.iat[2] == -90
    # Dense shoulder sweep is contained in the analytically computed rectangle.
    for sx in np.linspace(-.02, .38, 30):
        for sz in np.linspace(.65*1.8, .80*1.8, 30):
            angle = frontal_angle(.18, 1.80, sx, sz)
            assert scored.scenario_low_deg.iat[0] <= angle <= scored.scenario_high_deg.iat[0]


def test_invalid_release_and_extension_are_separate():
    f = frame(); f.loc[0, "extension"] = .007; f.loc[1, "rel_height"] = 10
    f.loc[2, "pitcher_hand"] = "Unknown"
    scored = score(f)
    assert not scored.extension_valid.iat[0] and np.isfinite(scored.estimated_frontal_deg.iat[0])
    assert scored.estimate_status.iat[1] == "invalid_release"
    assert scored.estimate_status.iat[2] == "unknown_hand"
    assert np.isnan(scored.fixed_130cm_proxy_deg.iat[1])


def test_kbo_profile_parser_checks_name_and_labelled_height():
    html = '<span id="ctl00_lblName">김 투수</span><span id="ctl00_lblHeightWeight">188cm / 92kg</span>'
    assert parse_kbo_profile(html, "김투수") == 188
    with pytest.raises(ValueError, match="identity"):
        parse_kbo_profile(html, "다른투수")
    with pytest.raises(ValueError, match="height"):
        parse_kbo_profile('<span id="lblName">김투수</span><p>188cm</p>', "김투수")


def test_height_provenance_and_unique_identity(tmp_path):
    bio = pd.DataFrame({"player_id": ["61101"], "player_name": ["김투수"]})
    row = dict(zip(HEIGHT_COLUMNS, ["61101", "김투수", 188., "https://www.koreabaseball.com/a", "a"*64, "2026-10-02T00:00:00Z"]))
    path = tmp_path / "heights.csv"
    pd.DataFrame([row]).to_csv(path, index=False)
    assert load_height_table(path, bio).height_cm.iat[0] == 188
    pd.DataFrame([row, row]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="one non-null"):
        load_height_table(path, bio)
    pd.DataFrame([{**row, "player_name": "동명이 아닌 선수"}]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="identity"):
        load_height_table(path, bio)


def test_collector_stops_on_proxy_denial_and_preserves_missing(tmp_path, monkeypatch):
    import requests
    attempts = []
    def blocked(url, **kwargs):
        attempts.append(url)
        raise requests.exceptions.ProxyError("denied")
    monkeypatch.setattr(requests, "get", blocked)
    bio = pd.DataFrame({"player_id": ["61101", "61102"], "player_name": ["가", "나"]})
    path = tmp_path / "heights.csv"
    events = collect_heights(bio, path, bio, tmp_path / "cache")
    assert len(attempts) == 1 and events[0]["status"] == "proxy_blocked"
    assert pd.read_csv(path).empty


def make_sources(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    root = tmp_path / "repo"
    bio = pd.DataFrame({"player_id": ["61101"], "player_name": ["김투수"], "height_cm": [np.nan]})
    directory = root / "data/curated/players"; directory.mkdir(parents=True)
    pq.write_table(pa.Table.from_pandas(bio), directory / "player_bio.parquet")
    row = dict(zip(TM_COLUMNS, ["t1", 2024, "2024-04-01", "123456", "Right", "LG_TWI", "KIA_TIG", "Fastball", 1.8, .6, 1.8]))
    raw = pd.DataFrame([row, {**row, "trackman_id": "t2", "pitcher_trackman_id": "99999"},
                        {**row, "trackman_id": "t3", "batter_team": "MIN_LGT"}])
    source_dir = root / "data/tracking/raw/season=2024"; source_dir.mkdir(parents=True)
    path = source_dir / "trackman_history.csv"; raw.to_csv(path, index=False)
    crosswalk = {"seasons": {"2024": {"trackman_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "roles": {"pitcher": {"pairs": [{"trackman_id": "123456", "visualbaseball_id": "61101"}]}}}}}
    overlap = {"seasons": {"2024": {"roles": {"pitcher": {"shared_ids": []}}}}}
    for name, data in (("player_id_crosswalk", crosswalk), ("player_id_overlap", overlap)):
        (root / f"data/tracking/{name}.json").write_text(json.dumps(data))
    return root, bio, crosswalk, overlap, path


def test_first_team_scope_crosswalk_and_hash_guard(tmp_path):
    root, bio, cw, overlap, path = make_sources(tmp_path)
    data, report = load_season(root, 2024, bio, cw, overlap)
    assert len(data) == 2 and report["excluded_non_major"] == 1
    assert data.player_id.iat[0] == "61101" and pd.isna(data.player_id.iat[1])
    assert data.identity_method.iat[0] == "accepted_crosswalk"
    path.write_text(path.read_text().replace("1.8", "1.9"))
    with pytest.raises(ValueError, match="no longer matches"):
        load_season(root, 2024, bio, cw, overlap)


def test_full_run_keeps_raw_and_bio_unchanged_and_does_not_invent_height(tmp_path):
    root, _, _, _, raw = make_sources(tmp_path)
    original = raw.read_bytes()
    bio_path = root / "data/curated/players/player_bio.parquet"; bio_original = bio_path.read_bytes()
    report = run(root, tmp_path / "out", [2024], tmp_path / "heights.csv")
    assert report["major_pitches"] == 2 and report["personalized_pitches"] == 0
    assert report["statuses"] == {"missing_height": 2}
    assert raw.read_bytes() == original and bio_path.read_bytes() == bio_original
    summaries = pd.read_csv(tmp_path / "out/pitchers.csv")
    assert summaries.pitches.sum() == 2 and len(summaries) == 2
    assert summaries.estimated_median_deg.isna().all()


def test_reference_validation_requires_same_definition_and_actual_estimates(tmp_path):
    f = score(frame()).assign(season=2024, trackman_id=["1", "2", "3"], player_id=["a", "b", "a"])
    labels = f[["season", "trackman_id"]].copy()
    labels["reference_angle_deg"] = f.estimated_frontal_deg + 2
    labels["source_url"] = "https://example.org/video"
    labels["definition"] = "frontal_shoulder_to_ball"
    path = tmp_path / "labels.csv"; labels.to_csv(path, index=False)
    result, observations = validate_reference(f, path)
    assert result["n"] == 3 and result["pitchers"] == 2
    assert result["mae_deg"] == pytest.approx(2) and result["bias_deg"] == pytest.approx(-2)
    labels["definition"] = "3d_elevation"; labels.to_csv(path, index=False)
    with pytest.raises(ValueError, match="same frontal"):
        validate_reference(f, path)


def test_bad_assumption_order_is_rejected():
    with pytest.raises(ValueError, match="ordered"):
        Assumptions(shoulder_height_ratio_low=.9)
