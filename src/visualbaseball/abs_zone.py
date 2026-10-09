"""ABS strike-zone geometry for the experimental ABS Zone Explorer (data/experimental/abs/).

Official KBO rules (league announcements; analysis/abs/README.md lists the sources):
- zone top/bottom are fixed shares of the batter's registered height:
  2024 56.35% / 27.64%, 2025- 55.75% / 27.04% (the zone moved down, its size did not change);
- width 47.18 cm (43.18 cm plate + 2 cm each side), called at the plate's middle plane;
- top and bottom must hold at both the middle plane and the back plane; the back-plane zone
  bottom sits 1.5 cm lower to allow for gravity.

VB coordinates are feet from the plate origin, catcher view. The middle plane is y = 8.5/12 ft,
the back plane y = 0, the front plane y = 17/12 ft. Every function is vectorised over numpy
arrays and returns NaN instead of guessing when a trajectory or zone input is missing.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CM_PER_FOOT = 30.48
MID_PLANE_Y_FT = 8.5 / 12
BACK_PLANE_Y_FT = 0.0
FRONT_PLANE_Y_FT = 17 / 12
# A ball touching the zone is a strike. Official ball circumference is 22.9-23.5 cm (radius 3.64-3.74 cm);
# 3.62 cm is the effective radius that best reproduces recorded 2024-2026 calls from VB coordinates
# (analysis/abs/README.md, Phase 1 radius scan). It is fitted, not an official constant.
BALL_RADIUS_CM = 3.62
# Recorded sz_top/sz_bottom in ABS seasons may be rounded; a height whose two implied values differ by
# more than this is treated as inconsistent rather than averaged.
HEIGHT_TOLERANCE_CM = 1.0


@dataclass(frozen=True)
class AbsRule:
    season: int
    top_ratio: float
    bottom_ratio: float
    width_cm: float = 47.18
    back_bottom_offset_cm: float = 1.5

    @property
    def half_width_cm(self) -> float:
        return self.width_cm / 2


ABS_RULES = {
    2024: AbsRule(2024, .5635, .2764),
    2025: AbsRule(2025, .5575, .2704),
    # 2026 keeps the 2025 rule; VB sz_top/sz_bottom carry exactly the 2025 ratio (analysis/abs/README.md).
    2026: AbsRule(2026, .5575, .2704),
}
ABS_SEASONS = tuple(sorted(ABS_RULES))


def rule_for(season: int) -> AbsRule:
    try:
        return ABS_RULES[int(season)]
    except KeyError:
        raise ValueError(f"No ABS rule for season {season}; human umpires called pitches before 2024") from None


def _as_float(values) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in values], dtype=float) if isinstance(values, list) else np.asarray(values, dtype=float)


def plane_position_cm(x0, y0, z0, vx0, vy0, vz0, ax, ay, az, plane_y_ft):
    """(x, z) in cm where the constant-acceleration trajectory crosses y = plane_y_ft.

    Mirrors curated._at_plane: the root nearest t = 0, no solution beyond one second.
    """
    x0, y0, z0, vx0, vy0, vz0, ax, ay, az = (_as_float(v) for v in (x0, y0, z0, vx0, vy0, vz0, ax, ay, az))
    with np.errstate(invalid="ignore", divide="ignore"):
        disc = vy0 * vy0 - 2 * ay * (y0 - plane_y_ft)
        root = np.sqrt(disc)
        first, second = (-vy0 + root) / ay, (-vy0 - root) / ay
        quadratic = np.where(np.abs(first) <= np.abs(second), first, second)
        linear = (plane_y_ft - y0) / vy0
        t = np.where(np.abs(ay) < 1e-12, linear, quadratic)
    t = np.where(np.isfinite(t) & (np.abs(t) <= 1), t, np.nan)
    x = (x0 + vx0 * t + .5 * ax * t * t) * CM_PER_FOOT
    z = (z0 + vz0 * t + .5 * az * t * t) * CM_PER_FOOT
    return x, z


def implied_height_cm(sz_top_ft, sz_bottom_ft, season: int) -> np.ndarray:
    """Registered height implied by VB's ABS zone; NaN when top and bottom disagree."""
    rule = rule_for(season)
    top, bottom = _as_float(sz_top_ft) * CM_PER_FOOT, _as_float(sz_bottom_ft) * CM_PER_FOOT
    from_top, from_bottom = top / rule.top_ratio, bottom / rule.bottom_ratio
    consistent = np.abs(from_top - from_bottom) <= HEIGHT_TOLERANCE_CM
    return np.where(consistent, (from_top + from_bottom) / 2, np.nan)


def zone_bounds_cm(height_cm, season: int) -> tuple[np.ndarray, np.ndarray]:
    """Middle-plane zone (top, bottom) in cm for a registered height."""
    rule = rule_for(season)
    height = _as_float(height_cm)
    return height * rule.top_ratio, height * rule.bottom_ratio


def zone_margins_cm(x_mid, z_mid, z_back, top_cm, bottom_cm, season: int, ball_radius_cm: float = BALL_RADIUS_CM) -> dict:
    """Signed margin (cm) of each ABS constraint; positive means the ball satisfies it by that much.

    The pitch is a strike when every margin is >= 0. The smallest margin is how far the ball would
    have to move along one axis to change the call (``zone_margin_cm``).
    """
    rule = rule_for(season)
    x_mid, z_mid, z_back = _as_float(x_mid), _as_float(z_mid), _as_float(z_back)
    top, bottom = _as_float(top_cm), _as_float(bottom_cm)
    r = ball_radius_cm
    return {
        "side": rule.half_width_cm + r - np.abs(x_mid),
        "top_mid": top + r - z_mid,
        "bottom_mid": z_mid - (bottom - r),
        "top_back": top + r - z_back,
        "bottom_back": z_back - (bottom - rule.back_bottom_offset_cm - r),
    }


MARGIN_EDGES = ("side", "top_mid", "bottom_mid", "top_back", "bottom_back")


def zone_margin_cm(margins: dict) -> tuple[np.ndarray, np.ndarray]:
    """Smallest margin and the index into MARGIN_EDGES of the constraint that sets it (-1 when unknown)."""
    stack = np.vstack([margins[e] for e in MARGIN_EDGES])
    known = np.all(np.isfinite(stack), axis=0)
    filled = np.where(np.isfinite(stack), stack, np.inf)
    edge = np.where(known, np.argmin(filled, axis=0), -1)
    return np.where(known, np.min(filled, axis=0), np.nan), edge


def edge_group(edge_index) -> np.ndarray:
    """Collapse the binding constraint to side / top / bottom ('' when unknown)."""
    names = np.array(["side", "top", "bottom", "top", "bottom", ""])
    return names[np.where(np.asarray(edge_index) < 0, 5, edge_index)]


def abs_strike(margin_cm) -> np.ndarray:
    """1.0 strike, 0.0 ball, NaN when the margin cannot be computed."""
    margin = _as_float(margin_cm)
    return np.where(np.isfinite(margin), (margin >= 0).astype(float), np.nan)


def flip_probability(margin_cm, sigma_cm: float) -> np.ndarray:
    """Chance an assumed N(0, sigma) one-axis coordinate error moves the ball across its binding edge.

    A sensitivity scenario only: sigma is an assumption, not an observed tracking error.
    """
    from scipy.stats import norm
    margin = _as_float(margin_cm)
    if sigma_cm <= 0:
        return np.where(np.isfinite(margin), 0.0, np.nan)
    return norm.sf(np.abs(margin) / sigma_cm)
