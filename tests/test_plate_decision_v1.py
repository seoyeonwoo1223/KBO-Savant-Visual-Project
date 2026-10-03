from pathlib import Path

from visualbaseball.plate_decision_v1 import _load_park_factors


def test_legacy_duplicate_headers_use_fixed_pitch_order():
    root = Path(__file__).parents[1]
    factors = _load_park_factors(root, 2022)
    assert factors[("고척", "FF")] == (-0.226, -8.394)
    assert factors[("고척", "SL")] == (-4.434, -9.319)
