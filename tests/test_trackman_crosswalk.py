import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("crosswalk", Path(__file__).parents[1] / "scripts" / "build_trackman_id_crosswalk.py")
crosswalk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crosswalk)


def test_accepts_a_dominant_one_to_one_pair_with_a_different_id():
    accepted, rejected = crosswalk.accept_pairs({("658792", "53546"): 300, ("658792", "50001"): 3, ("50001", "50001"): 200})
    pairs = {item["trackman_id"]: item["visualbaseball_id"] for item in accepted}
    assert pairs == {"658792": "53546", "50001": "50001"}
    assert not next(item for item in accepted if item["trackman_id"] == "658792")["same_id"]
    assert rejected == []


def test_rejects_thin_split_and_many_to_one_pairs():
    counts = {("1", "10"): 5,                      # too few aligned pitches
              ("2", "20"): 60, ("2", "21"): 40,    # split across two VB IDs
              ("3", "30"): 50, ("4", "30"): 50}    # two TrackMan IDs claim one VB ID
    accepted, rejected = crosswalk.accept_pairs(counts)
    assert accepted == []
    reasons = {item["trackman_id"]: item["reasons"] for item in rejected}
    assert reasons["1"] == ["support"]
    assert "share" in reasons["2"]
    assert all("reverse_share" in reasons[tm] or reasons[tm] == ["many_to_one"] for tm in ("3", "4"))
