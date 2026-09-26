"""Prompt assembly: one template per corpus variant, one context slot.

Within a variant, arms differ **only** in what fills the context slot — empty for
``baseline`` and ``named_id``, a fixed-width table for ``enhanced`` and ``permuted``. The
audit diffs arm prompts mechanically and asserts the difference is confined to that slot.

The two variants differ in one sentence of the preamble: ``masked`` explains the tokens,
``real`` states where the coordinates are. Both mention ``cx``/``cy`` so neither variant
carries an extra paragraph the other lacks. That sentence is the *only* difference between
the variants' prompts for the same case besides the SVG itself, and it is recorded here so
the cross-variant comparison is read with it in mind.

Assembly uses ``str.replace`` on unique placeholders rather than ``str.format``: upstream's
first template silently rendered ``{{GEOM_…}}`` as ``{GEOM_…}`` because ``format``
collapses doubled braces (their CHANGELOG, template 1.0 → 1.1). A test asserts that a
token appears in the prompt exactly as it appears in the document.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Tuple

from fmtcontrol_xy import permute

from .corpus import PERMUTATION_SEED, Case, Chart
from .instructions import TARGET_PHRASES, named_id_phrase, render

TEMPLATE_ID = "edit_xy_v1"
TEMPLATE_VERSION = "1.0"

CONDITIONS = ("baseline", "permuted", "enhanced", "named_id")

_PREAMBLE = {
    "masked": (
        "The cx and cy attributes of every <circle> marker have been redacted and replaced "
        "with an opaque placeholder such as `{{GEOM_1234abcd}}`. This is intentional. Copy every "
        "placeholder through to your output exactly as it appears; do not attempt to reconstruct "
        "or repair it."
    ),
    "real": (
        "Each <circle> marker carries its rendered position in its cx and cy attributes."
    ),
}

_TEMPLATE = """\
You are editing an SVG document exported from a charting library.

@@PREAMBLE@@

SVG:
@@SVG@@
@@CONTEXT@@
Instruction: @@INSTRUCTION@@

Return the complete edited SVG document and nothing else. Change only what the \
instruction asks for; leave every other element exactly as it is.

If the document does not contain enough information to identify which element the \
instruction refers to, say so instead of guessing.
"""


def template_hash(variant: str) -> str:
    return hashlib.sha256((_TEMPLATE + "\n" + _PREAMBLE[variant]).encode("utf-8")).hexdigest()


def build_prompt(variant: str, svg: str, instruction: str, context: str) -> str:
    block = f"\n{context}\n" if context.strip() else ""
    return (
        _TEMPLATE.replace("@@PREAMBLE@@", _PREAMBLE[variant])
        .replace("@@SVG@@", svg.strip())
        .replace("@@CONTEXT@@", block)
        .replace("@@INSTRUCTION@@", instruction)
    )


# -- context providers ------------------------------------------------------------------------


def _format_facts(rows) -> str:
    """Fixed-width table. Identical formatting for ``enhanced`` and ``permuted`` so the only
    difference between those arms is which numbers sit in which row (SPEC §6)."""
    lines = ["Marker geometry (rendered):", "  id           centre_x  centre_y"]
    for marker_id, x, y in rows:
        lines.append(f"  {marker_id:<12} {x:8.2f}  {y:8.2f}")
    return "\n".join(lines)


def facts_of(chart: Chart) -> Dict[str, Tuple[float, float]]:
    """Primitive facts in document order: no ranks, no labels, no predicate names."""
    return {m.id: (m.cx, m.cy) for m in chart.markers}


def context_for(condition: str, chart: Chart) -> str:
    if condition in ("baseline", "named_id"):
        return ""
    facts = facts_of(chart)
    if condition == "enhanced":
        return _format_facts([(mid, x, y) for mid, (x, y) in facts.items()])
    if condition == "permuted":
        # Keyed by chart id only, so the same chart receives the same permutation in both
        # variants and the cross-variant comparison is not confounded by the shuffle.
        shuffled = permute(facts, key=chart.chart_id, seed=PERMUTATION_SEED)
        return _format_facts([(mid, *shuffled[mid]) for mid in facts])
    raise ValueError(f"unknown condition {condition!r}")


def instruction_for(condition: str, case: Case) -> str:
    if condition != "named_id":
        return case.instruction
    return render(case.operation, named_id_phrase(case.target_id), case.operation_variant, case.params)


def prompt_for(variant: str, condition: str, chart: Chart, case: Case) -> str:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    return build_prompt(variant, chart.svg(variant), instruction_for(condition, case), context_for(condition, chart))


def target_phrase_of(case: Case) -> str:
    return TARGET_PHRASES[case.predicate][case.target_variant]
