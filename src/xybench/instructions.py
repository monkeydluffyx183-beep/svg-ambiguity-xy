"""Instruction phrasing, edit operations and the leakage lint.

Two banks — how the target is referred to, how the edit is stated — composed into one
sentence, each in two registers, so a (predicate, operation) pair has four wordings.
Following upstream's design: a single wording per predicate would confound phrasing with
capability (CanItEdit, arXiv 2312.12450).

An instruction must never contain anything a model could match against the markup: no
id, no geometry token, no coordinate value, no fill colour already in the document. The
lint enforces that per instruction rather than trusting the templates.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

TARGET_PHRASES: Dict[str, Tuple[str, str]] = {
    "top_left": ("the top-left marker", "the marker nearest the top-left corner of the plot"),
    "top_right": ("the top-right marker", "the marker nearest the top-right corner of the plot"),
    "bottom_left": ("the bottom-left marker", "the marker nearest the bottom-left corner of the plot"),
    "bottom_right": ("the bottom-right marker", "the marker nearest the bottom-right corner of the plot"),
    "leftmost": ("the leftmost marker", "the marker furthest to the left"),
    "rightmost": ("the rightmost marker", "the marker furthest to the right"),
    "topmost": ("the topmost marker", "the marker furthest towards the top"),
    "bottommost": ("the bottommost marker", "the marker furthest towards the bottom"),
}

OPERATION_PHRASES: Dict[str, Tuple[str, str]] = {
    "recolor_fill": ("Change the fill of {target} to {fill}.", "Recolour {target} to {fill}."),
    "add_stroke": (
        "Add a {stroke_width}px {stroke} outline to {target}.",
        "Give {target} a {stroke_width}px {stroke} border.",
    ),
    "delete": ("Delete {target}.", "Remove {target} from the document."),
    # Rotation is meaningless for a circle about its own centre, so the fourth operation
    # is a radius change. "Twice as big" is ambiguous between radius and area; the
    # wording names the radius.
    "resize": (
        "Double the radius of {target}.",
        "Set the radius of {target} to twice its current value.",
    ),
}

OPERATIONS = tuple(OPERATION_PHRASES)

# Edit colours are far from every palette entry, so a requested colour never coincides
# with a fill already present. Verified per instruction by the lint, not assumed.
EDIT_COLOURS: Tuple[str, ...] = ("#ff0000", "#00ff00", "#0000ff", "#ff00ff")
STROKE_COLOURS: Tuple[str, ...] = ("#000000", "#ffffff")
STROKE_WIDTHS: Tuple[int, ...] = (2, 3)
RESIZE_FACTOR = 2.0


def named_id_phrase(marker_id: str) -> str:
    """The V2-style condition: the target named by id, everything else unchanged."""
    return f'the marker with id "{marker_id}"'


def template_id(predicate: str, operation: str, target_variant: int, operation_variant: int) -> str:
    return f"{predicate}.{operation}.t{target_variant}o{operation_variant}"


def render(operation: str, target_phrase: str, operation_variant: int, params: Dict[str, object]) -> str:
    return OPERATION_PHRASES[operation][operation_variant].format(target=target_phrase, **params)


def render_instruction(
    predicate: str, operation: str, target_variant: int, operation_variant: int, params: Dict[str, object]
) -> str:
    return render(operation, TARGET_PHRASES[predicate][target_variant], operation_variant, params)


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def lint(instruction: str, marker_ids: Iterable[str], coordinate_values: Iterable[str], fills: Iterable[str]) -> List[str]:
    """Return the leakage problems with an instruction (empty when clean).

    Numbers are permitted only when they are operation parameters (stroke width); any
    number that equals a coordinate string in the document is a leak.
    """
    problems: List[str] = []
    low = instruction.lower()
    for mid in marker_ids:
        if mid.lower() in low:
            problems.append(f"contains marker id {mid}")
    if "{{" in instruction or "geom_" in low:
        problems.append("contains a geometry token")
    coords = set(coordinate_values)
    for number in _NUMBER_RE.findall(instruction):
        if number in coords:
            problems.append(f"contains coordinate value {number}")
    for fill in fills:
        if fill.lower() in low:
            problems.append(f"contains document fill {fill}")
    return problems
