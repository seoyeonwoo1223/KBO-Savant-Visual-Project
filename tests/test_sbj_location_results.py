"""Sign consistency of committed SBJ location comparison outputs (analysis/sbj_location/results)."""
import json
from pathlib import Path

import pytest

RESULTS = Path(__file__).resolve().parents[1] / "analysis" / "sbj_location" / "results"
COMPARE = RESULTS / "pzone_bunt_compare.json"


@pytest.mark.skipif(not COMPARE.exists(), reason="comparison output not committed")
@pytest.mark.parametrize("stage", ["pre", "post"])
def test_bunt_compare_overall_a_minus_b_matches_season_summary_and_bins(stage):
    compare = json.loads(COMPARE.read_text(encoding="utf-8"))
    for season, row in compare["seasons"].items():
        name = f"pzone_exp_summary_{season}{'' if stage == 'pre' else '_bunt_corrected'}.json"
        summary = json.loads((RESULTS / name).read_text(encoding="utf-8"))
        overall = row[stage]["logloss_A_minus_B_all"]
        # pzone_experiment.boot(d, A, B) is A-B: the comparison must carry it through unchanged.
        assert overall == summary["logloss_diff_vs_B_za72"]["all"]["A_reported"]
        lo, hi = overall["ci95"]
        assert lo <= overall["mean"] <= hi
        # Edge-distance bins partition the takes, so their take-weighted mean is the overall A-B.
        bins = row[stage]["by_edge_distance"].values()
        takes = sum(b["takes"] for b in bins)
        assert takes == row[stage]["takes"]
        weighted = sum(b["logloss_A_minus_B"]["mean"] * b["takes"] for b in bins) / takes
        assert weighted == pytest.approx(overall["mean"], abs=5e-6)
