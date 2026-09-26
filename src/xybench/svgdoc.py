"""Text-level operations on XY's exported SVG.

Everything here works on the SVG *string* with position-preserving substitutions, never
by re-serialising through an XML library, so the document a model sees is XY's own output
plus exactly the edits described: an ``id`` on every marker, and — in the masked variant —
opaque tokens in place of marker coordinates.

XY 0.0.7 emits scatter markers as self-closing ``<circle …/>`` elements in data order, with
``cx``, ``cy``, ``r``, ``fill`` and ``fill-opacity``. Nothing else in the document carries a
marker position (checked by ``xybench.audit``).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

_CIRCLE_RE = re.compile(r"<circle\b[^>]*?/>")
_ATTR_RE = re.compile(r'([A-Za-z_:][-A-Za-z0-9_:.]*)="([^"]*)"')
_CLIP_RECT_RE = re.compile(
    r"<clipPath\b[^>]*>\s*<rect\b([^>]*)/>", re.DOTALL
)
GEOM_TOKEN_RE = re.compile(r"\{\{GEOM_[0-9a-f]{8}\}\}")


@dataclass(frozen=True)
class Marker:
    index: int  # document order among markers
    span: Tuple[int, int]
    attrs: Dict[str, str]

    @property
    def id(self) -> Optional[str]:
        return self.attrs.get("id")


def parse_attrs(tag_text: str) -> Dict[str, str]:
    return {k: v for k, v in _ATTR_RE.findall(tag_text)}


def find_markers(svg_text: str) -> List[Marker]:
    return [
        Marker(index=i, span=m.span(), attrs=parse_attrs(m.group(0)))
        for i, m in enumerate(_CIRCLE_RE.finditer(svg_text))
    ]


def plot_rect(svg_text: str) -> Tuple[float, float, float, float]:
    """The plot area (x, y, width, height), taken from XY's clipPath rectangle."""
    m = _CLIP_RECT_RE.search(svg_text)
    if not m:
        raise ValueError("no clipPath rect found; is this an XY export?")
    a = parse_attrs(m.group(1))
    return float(a["x"]), float(a["y"]), float(a["width"]), float(a["height"])


def _rewrite_markers(svg_text: str, rewrite: Callable[[Marker], str]) -> str:
    out: List[str] = []
    last = 0
    for marker in find_markers(svg_text):
        start, end = marker.span
        out.append(svg_text[last:start])
        out.append(rewrite(marker))
        last = end
    out.append(svg_text[last:])
    return "".join(out)


def marker_id(seed: int, chart_id: str, index: int) -> str:
    """Deterministic, content-free id: ``e`` + 8 hex of a hash. Hash-shaped rather than
    ordinal so the id itself carries no document-position hint."""
    digest = hashlib.sha256(f"{seed}:{chart_id}:marker:{index}".encode("utf-8")).hexdigest()
    return "e" + digest[:8]


def assign_ids(svg_text: str, ids: List[str]) -> str:
    """Insert ``id="…"`` as the first attribute of each marker, in document order."""
    markers = find_markers(svg_text)
    if len(markers) != len(ids):
        raise ValueError(f"{len(markers)} markers but {len(ids)} ids")
    if len(set(ids)) != len(ids):
        raise ValueError("ids must be unique")

    def rewrite(m: Marker) -> str:
        original = svg_text[m.span[0]: m.span[1]]
        if "id=" in m.attrs or m.id is not None:
            raise ValueError("marker already has an id")
        return original.replace("<circle", f'<circle id="{ids[m.index]}"', 1)

    return _rewrite_markers(svg_text, rewrite)


def geom_token(seed: int, chart_id: str, marker: str, attr: str) -> str:
    digest = hashlib.sha256(f"{seed}:{chart_id}:{marker}:{attr}".encode("utf-8")).hexdigest()
    return "{{GEOM_" + digest[:8] + "}}"


def mask_geometry(svg_text: str, token_for: Callable[[str, str], str]) -> str:
    """Replace every marker's ``cx`` and ``cy`` value with an opaque token.

    ``token_for(marker_id, attr)`` supplies the token. Attribute names, order and every
    other byte of the document are unchanged, so the masked and real variants differ only
    in those values — the same discipline the control applies between arms.
    """

    def rewrite(m: Marker) -> str:
        original = svg_text[m.span[0]: m.span[1]]
        if m.id is None:
            raise ValueError("assign ids before masking")
        text = original
        for attr in ("cx", "cy"):
            value = m.attrs[attr]
            text = text.replace(f'{attr}="{value}"', f'{attr}="{token_for(m.id, attr)}"', 1)
        return text

    return _rewrite_markers(svg_text, rewrite)


def unmask_geometry(masked_text: str, values: Dict[str, Tuple[float, float]], raw: Dict[str, Dict[str, str]]) -> str:
    """Inverse of :func:`mask_geometry`, used by the audit to prove the two variants are
    the same document apart from the masked values. ``raw`` holds each marker's original
    attribute strings so the exact formatting round-trips."""

    def rewrite(m: Marker) -> str:
        text = masked_text[m.span[0]: m.span[1]]
        for attr in ("cx", "cy"):
            text = text.replace(f'{attr}="{m.attrs[attr]}"', f'{attr}="{raw[m.id][attr]}"', 1)
        return text

    return _rewrite_markers(masked_text, rewrite)
