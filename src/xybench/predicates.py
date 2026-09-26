"""Spatial predicates over rendered marker geometry, and the uniqueness rule.

Only the spatial family is used. XY markers in this corpus share one radius, so the size
family (largest / second largest / …) would be resolvable from ``r`` in the source text
and would not be an information-gap task. Eight predicates remain: four one-dimensional
extremes and four corner predicates.

Geometry is in **rendered pixel space** as parsed from the SVG — the picture the
instruction refers to — with SVG's convention that ``y`` grows downward. "Topmost" is
therefore the smallest ``cy``.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

PlotRect = Tuple[float, float, float, float]  # x, y, width, height
Point = Tuple[float, float]

EXTREME_PREDICATES = ("leftmost", "rightmost", "topmost", "bottommost")
CORNER_PREDICATES = ("top_left", "top_right", "bottom_left", "bottom_right")
PREDICATES = EXTREME_PREDICATES + CORNER_PREDICATES

#: Required gap, in pixels, between the best and second-best marker on a predicate's
#: score. Below this the instruction is arguably ambiguous to a human and the case is
#: rejected rather than scored. Recorded in the manifest.
DEFAULT_MARGIN_PX = 24.0


def _corner(rect: PlotRect, predicate: str) -> Point:
    x, y, w, h = rect
    return {
        "top_left": (x, y),
        "top_right": (x + w, y),
        "bottom_left": (x, y + h),
        "bottom_right": (x + w, y + h),
    }[predicate]


def score(predicate: str, centre: Point, rect: PlotRect) -> float:
    """Lower is better: the predicate's target is the argmin."""
    cx, cy = centre
    if predicate == "leftmost":
        return cx
    if predicate == "rightmost":
        return -cx
    if predicate == "topmost":
        return cy
    if predicate == "bottommost":
        return -cy
    if predicate in CORNER_PREDICATES:
        kx, ky = _corner(rect, predicate)
        return math.hypot(cx - kx, cy - ky)
    raise ValueError(f"unknown predicate {predicate!r}")


def resolve(
    predicate: str,
    centres: Dict[str, Point],
    rect: PlotRect,
    margin_px: float = DEFAULT_MARGIN_PX,
) -> Tuple[Optional[str], float]:
    """Return ``(target_id, gap)``; ``target_id`` is ``None`` when the best two markers are
    closer than ``margin_px`` on the score, i.e. the predicate does not pick out a unique
    marker with the required clearance."""
    if len(centres) < 2:
        raise ValueError("need at least two markers")
    ranked: List[Tuple[float, str]] = sorted((score(predicate, c, rect), mid) for mid, c in centres.items())
    gap = ranked[1][0] - ranked[0][0]
    if gap < margin_px:
        return None, gap
    return ranked[0][1], gap
