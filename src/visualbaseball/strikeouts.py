"""Strikeout rule shared by trendline, conditional finder and plate discipline."""
from __future__ import annotations


def third_strike(strikes_before, pitch_call_code) -> bool:
    """A PA ending on a called/swinging strike with two strikes is a strikeout.

    VB leaves the result blank for 2,623 such 2019 PAs (type=out, result="") and records
    dropped-third-strike advances only as WP/포실, so the result text alone undercounts.
    """
    return strikes_before == 2 and pitch_call_code in {"S", "T"}


def is_strikeout(pa_type, pa_result, strikes_before, pitch_call_code) -> bool:
    return pa_type == "k" or str(pa_result or "").strip() == "삼진" or third_strike(strikes_before, pitch_call_code)
