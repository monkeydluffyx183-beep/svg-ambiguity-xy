"""Scoring: from a raw model response to one outcome class.

Frozen with the corpus. The rules follow upstream's pre-registered design (outcome classes,
identification as primary, abstention checked before no-op) with one deliberate change,
taken from their FA-013: a response that declines **in prose without an SVG** is its own
class, ``REFUSED_PROSE``, rather than ``MALFORMED``. Upstream's abstention regexes were
calibrated on one model's refusal style; models that declined differently were scored as
broken output and tripped a data-quality falsifier. Here the regexes still decide
``ABSTAINED`` (an explicit "cannot identify" signal), but their failure to match no longer
turns a refusal into a parse error. ``MALFORMED`` is reserved for responses that *tried* to
return a document — an ``<svg`` is present — and failed.

Identification is reported two ways:

* **exclusive** (primary here): the target marker changed and no other marker did. This
  is the literal reading of "which element it identified"; a response that edits every
  marker identifies nothing.
* **inclusive** (upstream's primary): the target changed, regardless of collateral.

Both are in every evaluation row; the report shows both.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from .corpus import Case, Chart

SCORING_VERSION = "1.0"
ABSTENTION_RULE_VERSION = "2.0"  # 1.0 = upstream's regex-only rule; 2.0 adds REFUSED_PROSE

OUTCOMES = (
    "CORRECT_STRICT",
    "CORRECT_LOOSE",
    "WRONG_TARGET",
    "NO_EDIT",
    "ABSTAINED",
    "REFUSED_PROSE",
    "MALFORMED",
)

_SVG_RE = re.compile(r"<svg\b.*?</svg\s*>", re.IGNORECASE | re.DOTALL)

_ABSTENTION_PATTERNS = (
    r"\bcannot determine\b",
    r"\bcan(?:'|no)?t (?:tell|determine|identify|know) which\b",
    r"\bunable to (?:determine|identify|tell)\b",
    r"\bno way to (?:tell|know|determine)\b",
    r"\bdoes not (?:say|specify|indicate|contain|encode) which\b",
    r"\bdoesn'?t (?:say|specify|indicate|contain|encode) which\b",
    r"\bwhich .{0,40}(?:did|do) you (?:mean|have in mind|refer to|intend)\b",
    r"\bwhich .{0,40}are you referring to\b",
    r"\b(?:please|could you|can you|would you) (?:clarify|specify)\b",
    r"\brather than guess(?:ing)?\b",
    r"\binsufficient information\b",
    r"\bnot enough information\b",
    r"\bno positional information\b",
    r"\bpositions? (?:are|is|have been) (?:redacted|not available|unknown)\b",
    r"\bambiguous\b.{0,60}\bcannot\b",
    r"\bcannot (?:be )?(?:reliably )?identif(?:y|ied)\b",
)
_ABSTENTION_RE = re.compile("|".join(_ABSTENTION_PATTERNS), re.IGNORECASE | re.DOTALL)

NUMERIC_ATTRS = {"cx", "cy", "r", "stroke-width", "fill-opacity", "opacity", "stroke-opacity"}
_NUMBER_TOLERANCE = 1e-6

_NAMED_COLOURS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000", "lime": "#00ff00", "blue": "#0000ff",
    "magenta": "#ff00ff", "fuchsia": "#ff00ff", "yellow": "#ffff00", "cyan": "#00ffff", "aqua": "#00ffff",
    "green": "#008000", "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0", "maroon": "#800000",
    "navy": "#000080", "olive": "#808000", "purple": "#800080", "teal": "#008080", "orange": "#ffa500",
}
_RGB_RE = re.compile(r"rgba?\(\s*([^)]+)\)", re.IGNORECASE)


@dataclass
class Evaluation:
    outcome: str
    identified: bool
    identified_inclusive: bool
    target_changed: bool
    edit_correct: bool
    changed_ids: List[str]
    collateral: List[str]
    n_changed: int
    selected_index: Optional[int]
    non_marker_changed: bool
    extra_markers: int
    abstention_signal: bool
    malformed_reason: Optional[str]
    truncated: bool

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -- text level -------------------------------------------------------------------------------


def extract_svg(response: str) -> Optional[str]:
    """The LAST complete ``<svg>…</svg>`` block: models that narrate leave the document
    last, models that revise leave the corrected one last."""
    matches = _SVG_RE.findall(response)
    return matches[-1] if matches else None


def detects_abstention(response: str) -> bool:
    return bool(_ABSTENTION_RE.search(response))


# -- canonicalisation -------------------------------------------------------------------------


def normalise_colour(value: str) -> str:
    v = value.strip().lower()
    if not v:
        return ""
    if v in _NAMED_COLOURS:
        return _NAMED_COLOURS[v]
    if v.startswith("#"):
        hexpart = v[1:]
        if len(hexpart) == 3:
            return "#" + "".join(ch * 2 for ch in hexpart)
        if len(hexpart) == 4:  # #rgba -> drop alpha
            return "#" + "".join(ch * 2 for ch in hexpart[:3])
        if len(hexpart) == 8:
            return "#" + hexpart[:6]
        return "#" + hexpart
    m = _RGB_RE.match(v)
    if m:
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1)) if p.strip()]
        try:
            channels = []
            for p in parts[:3]:
                if p.endswith("%"):
                    channels.append(round(float(p[:-1]) * 255 / 100))
                else:
                    channels.append(round(float(p)))
            if len(channels) == 3:
                return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in channels)
        except ValueError:
            pass
    return v


def _parse_number(value: str) -> Optional[float]:
    v = value.strip().lower()
    if v.endswith("px"):
        v = v[:-2]
    try:
        return float(v)
    except ValueError:
        return None


def normalise_attrs(attrs: Dict[str, str]) -> Dict[str, str]:
    """Merge ``style`` declarations into attributes (style wins, as in CSS), canonicalise
    colours, and strip whitespace. Numeric comparison is done in :func:`attrs_equal`."""
    out = {k: v.strip() for k, v in attrs.items() if k != "style"}
    style = attrs.get("style", "")
    for decl in style.split(";"):
        if ":" in decl:
            k, v = decl.split(":", 1)
            out[k.strip()] = v.strip()
    for key in ("fill", "stroke"):
        if key in out:
            out[key] = normalise_colour(out[key])
    return out


def attrs_equal(a: Dict[str, str], b: Dict[str, str]) -> bool:
    if set(a) != set(b):
        return False
    for key in a:
        va, vb = a[key], b[key]
        if key in NUMERIC_ATTRS:
            fa, fb = _parse_number(va), _parse_number(vb)
            if fa is not None and fb is not None:
                if not math.isclose(fa, fb, rel_tol=_NUMBER_TOLERANCE, abs_tol=_NUMBER_TOLERANCE):
                    return False
                continue
        if va != vb:
            return False
    return True


# -- document level ---------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_document(svg_text: str) -> Optional[Tuple[Dict[str, Dict[str, str]], int, List[Tuple[str, Tuple[Tuple[str, str], ...], str]]]]:
    """Return ``(markers_by_id, unidentified_markers, non_marker_signature)`` or ``None`` if
    the text is not well-formed XML."""
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return None
    markers: Dict[str, Dict[str, str]] = {}
    extra = 0
    others: List[Tuple[str, Tuple[Tuple[str, str], ...], str]] = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag == "circle":
            mid = el.get("id")
            if mid is None or mid in markers:
                extra += 1
            else:
                markers[mid] = normalise_attrs(dict(el.attrib))
        else:
            others.append((tag, tuple(sorted(el.attrib.items())), (el.text or "").strip()))
    return markers, extra, sorted(others)


def edit_is_correct(operation: str, params: Dict[str, Any], original: Dict[str, str], returned: Optional[Dict[str, str]]) -> bool:
    """Whether the requested operation was performed on this element — distinct from
    whether the element changed."""
    if operation == "delete":
        return returned is None
    if returned is None:
        return False
    if operation == "recolor_fill":
        return returned.get("fill", "") == normalise_colour(str(params["fill"]))
    if operation == "add_stroke":
        width = _parse_number(returned.get("stroke-width", ""))
        return (
            returned.get("stroke", "") == normalise_colour(str(params["stroke"]))
            and width is not None
            and math.isclose(width, float(params["stroke_width"]), rel_tol=1e-6, abs_tol=1e-6)
        )
    if operation == "resize":
        r0 = _parse_number(original.get("r", ""))
        r1 = _parse_number(returned.get("r", ""))
        return r0 is not None and r1 is not None and math.isclose(r1, r0 * float(params["factor"]), rel_tol=1e-3)
    raise ValueError(f"unknown operation {operation!r}")


def _malformed(reason: str, abstention: bool, truncated: bool) -> Evaluation:
    return Evaluation(
        outcome="MALFORMED", identified=False, identified_inclusive=False, target_changed=False,
        edit_correct=False, changed_ids=[], collateral=[], n_changed=0, selected_index=None,
        non_marker_changed=False, extra_markers=0, abstention_signal=abstention,
        malformed_reason=reason, truncated=truncated,
    )


def evaluate_response(case: Case, chart: Chart, variant: str, response: str, finish_reason: Optional[str] = None) -> Evaluation:
    """Classify one response against the document the model was shown."""
    truncated = finish_reason in ("length", "max_tokens")
    abstention = detects_abstention(response)
    svg_text = extract_svg(response)

    if svg_text is None:
        if "<svg" in response.lower():
            return _malformed("truncated or unterminated <svg>", abstention, truncated)
        outcome = "ABSTAINED" if abstention else "REFUSED_PROSE"
        ev = _malformed("", abstention, truncated)
        ev.outcome = outcome
        ev.malformed_reason = None
        return ev

    parsed = parse_document(svg_text)
    if parsed is None:
        return _malformed("xml parse error", abstention, truncated)
    returned, extra, others_returned = parsed

    original_doc = parse_document(chart.svg(variant))
    assert original_doc is not None
    original, _, others_original = original_doc

    missing = [mid for mid in original if mid not in returned]
    if len(missing) >= 2:
        return _malformed(f"alignment: {len(missing)} markers missing", abstention, truncated)

    changed: List[str] = []
    for mid, attrs in original.items():
        if mid not in returned or not attrs_equal(attrs, returned[mid]):
            changed.append(mid)

    target = case.target_id
    target_changed = target in changed
    collateral = [mid for mid in changed if mid != target]
    edit_correct = edit_is_correct(case.operation, case.params, original[target], returned.get(target))

    if edit_correct:
        outcome = "CORRECT_LOOSE" if collateral else "CORRECT_STRICT"
    elif changed:
        outcome = "WRONG_TARGET"
    else:
        outcome = "ABSTAINED" if abstention else "NO_EDIT"

    index_of = {m.id: m.index for m in chart.markers}
    selected_index = index_of[changed[0]] if len(changed) == 1 else None

    return Evaluation(
        outcome=outcome,
        identified=target_changed and not collateral,
        identified_inclusive=target_changed,
        target_changed=target_changed,
        edit_correct=edit_correct,
        changed_ids=changed,
        collateral=collateral,
        n_changed=len(changed),
        selected_index=selected_index,
        non_marker_changed=others_returned != others_original,
        extra_markers=extra,
        abstention_signal=abstention,
        malformed_reason=None,
        truncated=truncated,
    )
