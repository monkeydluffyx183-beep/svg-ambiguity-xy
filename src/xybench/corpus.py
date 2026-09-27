"""Corpus generation: real XY charts, two renderings, ground truth from the pixels.

A corpus is a deterministic function of ``(CorpusConfig, xy version)``. Every chart is a
single-series XY scatter of K ∈ [4, 7] markers that share fill, radius and opacity — an
*ambiguity set* in which nothing but geometry distinguishes one marker from another.
There are no distractor series, so the random-selection reference is exactly ``mean(1/K)``.

Two renderings of every chart are written:

``real``
    XY's export with a deterministic ``id`` inserted on each marker. Coordinates are
    legible in the source (``cx="136.74"``).
``masked``
    The same bytes with each marker's ``cx`` and ``cy`` replaced by an opaque
    ``{{GEOM_xxxxxxxx}}`` token — upstream's information gap, recreated on real markup.

Ground truth is computed from the rendered pixel geometry parsed out of XY's SVG, never
from the data values that produced it, because the instruction refers to the picture.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import instructions as ins
from . import predicates as pred
from .svgdoc import assign_ids, find_markers, geom_token, marker_id, mask_geometry, plot_rect

GENERATOR_VERSION = "1.0"
XY_VERSION_REQUIRED = "0.0.7"

#: Seed for the permuted arm. SPEC I7: must be independent of the corpus seed, which it is
#: by fiat — it is a different constant, never derived from ``CorpusConfig.seed``.
PERMUTATION_SEED = 4093


@dataclass(frozen=True)
class CorpusConfig:
    seed: int = 20260926
    n_charts: int = 30
    cases_per_chart: int = 6
    k_min: int = 4
    k_max: int = 7
    margin_px: float = pred.DEFAULT_MARGIN_PX
    width: int = 720
    height: int = 480
    marker_size: float = 7.0  # XY size; rendered radius is size / 2
    title: str = "Observations"
    palette: Tuple[str, ...] = ("#2f6f9f", "#8c5a3c", "#4f8a4f", "#8a4f7d")
    x_range: Tuple[float, float] = (0.0, 100.0)
    y_range: Tuple[float, float] = (0.0, 50.0)
    max_attempts_per_chart: int = 60
    max_cases_per_target: int = 2

    def config_hash(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode("utf-8")).hexdigest()


@dataclass
class MarkerGeom:
    id: str
    index: int
    cx: float
    cy: float
    r: float
    raw: Dict[str, str]  # attribute strings exactly as XY wrote them


@dataclass
class Chart:
    chart_id: str
    k: int
    fill: str
    plot_rect: Tuple[float, float, float, float]
    markers: List[MarkerGeom]
    attempts: int
    real_svg: str = field(repr=False, default="")
    masked_svg: str = field(repr=False, default="")

    @property
    def centres(self) -> Dict[str, Tuple[float, float]]:
        return {m.id: (m.cx, m.cy) for m in self.markers}

    @property
    def ids(self) -> List[str]:
        return [m.id for m in self.markers]

    def svg(self, variant: str) -> str:
        if variant == "real":
            return self.real_svg
        if variant == "masked":
            return self.masked_svg
        raise ValueError(f"unknown variant {variant!r}")


@dataclass
class Case:
    case_id: str
    chart_id: str
    k: int
    predicate: str
    target_id: str
    target_index: int
    gap_px: float
    operation: str
    params: Dict[str, Any]
    target_variant: int
    operation_variant: int
    template_id: str
    instruction: str


@dataclass
class Corpus:
    root: Path
    manifest: Dict[str, Any]
    charts: Dict[str, Chart]
    cases: List[Case]

    @property
    def dataset_hash(self) -> str:
        return str(self.manifest["dataset_hash"])


VARIANTS = ("masked", "real")


# -- rendering ----------------------------------------------------------------------------


def xy_version() -> Optional[str]:
    try:
        import xy  # type: ignore
    except ImportError:
        return None
    return getattr(xy, "__version__", "unknown")


def render_chart_svg(cfg: CorpusConfig, xs: List[float], ys: List[float], fill: str) -> str:
    try:
        import xy  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "corpus generation needs the XY charting library: pip install 'fmtcontrol-xy[bench]' "
            "(requires Python >= 3.11)"
        ) from exc
    chart = xy.scatter_chart(
        xy.scatter(xs, ys, color=fill, size=cfg.marker_size),
        title=cfg.title,
        width=cfg.width,
        height=cfg.height,
    )
    svg = chart.to_svg()
    if not isinstance(svg, str):
        raise RuntimeError("xy.Chart.to_svg() did not return a string")
    return svg


# -- generation -----------------------------------------------------------------------------


def _choose_predicates(
    cfg: CorpusConfig, valid: Dict[str, Tuple[str, float]], rng: random.Random
) -> List[str]:
    """Pick ``cases_per_chart`` predicates, preferring distinct targets (a corner marker is
    often also an extreme). Cap per target first, then fill."""
    order = list(valid)
    rng.shuffle(order)
    chosen: List[str] = []
    per_target: Counter = Counter()
    for p in order:
        if len(chosen) == cfg.cases_per_chart:
            break
        target = valid[p][0]
        if per_target[target] < cfg.max_cases_per_target:
            chosen.append(p)
            per_target[target] += 1
    for p in order:
        if len(chosen) == cfg.cases_per_chart:
            break
        if p not in chosen:
            chosen.append(p)
    return chosen


def _params_for(operation: str, rng: random.Random) -> Dict[str, Any]:
    if operation == "recolor_fill":
        return {"fill": rng.choice(ins.EDIT_COLOURS)}
    if operation == "add_stroke":
        return {"stroke": rng.choice(ins.STROKE_COLOURS), "stroke_width": rng.choice(ins.STROKE_WIDTHS)}
    if operation == "delete":
        return {}
    if operation == "resize":
        return {"factor": ins.RESIZE_FACTOR}
    raise ValueError(operation)


def _try_chart(cfg: CorpusConfig, chart_index: int, attempt: int, rng: random.Random) -> Tuple[Optional[Chart], Optional[List[Case]], str]:
    chart_id = f"xy{chart_index:03d}"
    k = rng.randint(cfg.k_min, cfg.k_max)
    xs = [round(rng.uniform(*cfg.x_range), 2) for _ in range(k)]
    ys = [round(rng.uniform(*cfg.y_range), 2) for _ in range(k)]
    fill = rng.choice(cfg.palette)

    svg = render_chart_svg(cfg, xs, ys, fill)
    raw_markers = find_markers(svg)
    if len(raw_markers) != k:
        return None, None, f"xy emitted {len(raw_markers)} markers for {k} points"

    ids = [marker_id(cfg.seed, chart_id, i) for i in range(k)]
    real = assign_ids(svg, ids)
    markers = [
        MarkerGeom(id=m.attrs["id"], index=m.index, cx=float(m.attrs["cx"]), cy=float(m.attrs["cy"]),
                   r=float(m.attrs["r"]), raw=dict(m.attrs))
        for m in find_markers(real)
    ]
    rect = plot_rect(real)
    centres = {m.id: (m.cx, m.cy) for m in markers}

    valid: Dict[str, Tuple[str, float]] = {}
    for p in pred.PREDICATES:
        target, gap = pred.resolve(p, centres, rect, cfg.margin_px)
        if target is not None:
            valid[p] = (target, gap)
    if len(valid) < cfg.cases_per_chart:
        return None, None, f"only {len(valid)} of {len(pred.PREDICATES)} predicates unique with margin"

    chosen = _choose_predicates(cfg, valid, rng)
    ops = list(ins.OPERATIONS)
    rng.shuffle(ops)
    index_of = {m.id: m.index for m in markers}

    cases: List[Case] = []
    for j, p in enumerate(chosen):
        target, gap = valid[p]
        operation = ops[j % len(ops)]
        params = _params_for(operation, rng)
        tv, ov = rng.randint(0, 1), rng.randint(0, 1)
        instruction = ins.render_instruction(p, operation, tv, ov, params)
        problems = ins.lint(
            instruction,
            marker_ids=ids,
            coordinate_values=[m.raw["cx"] for m in markers] + [m.raw["cy"] for m in markers],
            fills=[fill],
        )
        if problems:
            return None, None, f"instruction lint: {problems}"
        cases.append(
            Case(
                case_id=f"{chart_id}-{j:02d}", chart_id=chart_id, k=k, predicate=p, target_id=target,
                target_index=index_of[target], gap_px=round(gap, 3), operation=operation, params=params,
                target_variant=tv, operation_variant=ov, template_id=ins.template_id(p, operation, tv, ov),
                instruction=instruction,
            )
        )

    masked = mask_geometry(real, lambda mid, attr: geom_token(cfg.seed, chart_id, mid, attr))
    chart = Chart(chart_id=chart_id, k=k, fill=fill, plot_rect=rect, markers=markers, attempts=attempt,
                  real_svg=real, masked_svg=masked)
    return chart, cases, ""


def generate(cfg: CorpusConfig) -> Tuple[List[Chart], List[Case], Dict[str, Any]]:
    """Generate charts and cases in memory. Deterministic in ``cfg`` and the XY version."""
    rng = random.Random(cfg.seed)
    charts: List[Chart] = []
    cases: List[Case] = []
    rejections: Dict[str, Any] = {"per_chart": {}, "reasons": Counter()}
    for i in range(cfg.n_charts):
        for attempt in range(1, cfg.max_attempts_per_chart + 1):
            chart, chart_cases, reason = _try_chart(cfg, i, attempt, rng)
            if chart is not None and chart_cases is not None:
                charts.append(chart)
                cases.extend(chart_cases)
                rejections["per_chart"][chart.chart_id] = attempt - 1
                break
            rejections["reasons"][reason.split(":")[0]] += 1
        else:
            raise RuntimeError(f"chart {i}: no acceptable layout in {cfg.max_attempts_per_chart} attempts")
    rejections["reasons"] = dict(rejections["reasons"])
    rejections["total"] = sum(rejections["per_chart"].values())
    return charts, cases, rejections


# -- persistence ------------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_listing(root: Path) -> List[Tuple[str, str]]:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel == "manifest.json":
            continue
        rows.append((rel, _sha256_bytes(path.read_bytes())))
    return rows


def dataset_hash_of(root: Path) -> str:
    h = hashlib.sha256()
    for rel, digest in _file_listing(root):
        h.update(f"{rel}\0{digest}\n".encode("utf-8"))
    return h.hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def write_corpus(cfg: CorpusConfig, charts: List[Chart], cases: List[Case], rejections: Dict[str, Any], out_root: Path) -> Path:
    """Write ``out_root/<dataset_hash>/`` and return that directory."""
    staging = out_root / "_staging"
    if staging.exists():
        for p in sorted(staging.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    staging.mkdir(parents=True)

    for c in charts:
        _write_text(staging / "charts" / f"{c.chart_id}.real.svg", c.real_svg)
        _write_text(staging / "charts" / f"{c.chart_id}.masked.svg", c.masked_svg)
    _write_text(
        staging / "charts.jsonl",
        "".join(
            json.dumps(
                {
                    "chart_id": c.chart_id, "k": c.k, "fill": c.fill, "plot_rect": c.plot_rect,
                    "attempts": c.attempts,
                    "markers": [asdict(m) for m in c.markers],
                },
                sort_keys=True,
            ) + "\n"
            for c in charts
        ),
    )
    _write_text(staging / "cases.jsonl", "".join(json.dumps(asdict(k), sort_keys=True) + "\n" for k in cases))
    _write_text(staging / "rejections.json", json.dumps(rejections, sort_keys=True, indent=2) + "\n")

    digest = dataset_hash_of(staging)
    manifest = {
        "dataset_hash": digest,
        "config": asdict(cfg),
        "config_hash": cfg.config_hash(),
        "generator_version": GENERATOR_VERSION,
        "permutation_seed": PERMUTATION_SEED,
        "xy_version": xy_version(),
        "python_version": platform.python_version(),
        "n_charts": len(charts),
        "n_cases": len(cases),
        "variants": list(VARIANTS),
        "files": [{"path": rel, "sha256": h} for rel, h in _file_listing(staging)],
    }
    _write_text(staging / "manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")

    final = out_root / digest
    if final.exists():
        for p in sorted(staging.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
        staging.rmdir()
        return final
    staging.rename(final)
    return final


def build(cfg: CorpusConfig, out_root: Path) -> Path:
    charts, cases, rejections = generate(cfg)
    return write_corpus(cfg, charts, cases, rejections, out_root)


def load_corpus(root: Path) -> Corpus:
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    charts: Dict[str, Chart] = {}
    for line in (root / "charts.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        markers = [MarkerGeom(**m) for m in row["markers"]]
        chart = Chart(
            chart_id=row["chart_id"], k=row["k"], fill=row["fill"], plot_rect=tuple(row["plot_rect"]),
            markers=markers, attempts=row["attempts"],
            real_svg=(root / "charts" / f"{row['chart_id']}.real.svg").read_text(encoding="utf-8"),
            masked_svg=(root / "charts" / f"{row['chart_id']}.masked.svg").read_text(encoding="utf-8"),
        )
        charts[chart.chart_id] = chart
    cases = [Case(**json.loads(line)) for line in (root / "cases.jsonl").read_text(encoding="utf-8").splitlines()]
    return Corpus(root=root, manifest=manifest, charts=charts, cases=cases)


def verify_files(root: Path) -> List[str]:
    """Integrity certificate: every listed file present with its hash, no extra files, and
    the dataset hash equal to the directory name and to the manifest."""
    root = Path(root)
    problems: List[str] = []
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    listed = {f["path"]: f["sha256"] for f in manifest["files"]}
    actual = dict(_file_listing(root))
    for rel, digest in listed.items():
        if rel not in actual:
            problems.append(f"missing file {rel}")
        elif actual[rel] != digest:
            problems.append(f"hash mismatch {rel}")
    for rel in actual:
        if rel not in listed:
            problems.append(f"unlisted file {rel}")
    digest = dataset_hash_of(root)
    if digest != manifest["dataset_hash"]:
        problems.append("dataset hash does not match manifest")
    if root.name != manifest["dataset_hash"]:
        problems.append("directory name does not match dataset hash")
    return problems


def verify_regeneration(root: Path, scratch: Path) -> Tuple[bool, str, str]:
    """Tier 3: regenerate from the manifest's config and compare dataset hashes."""
    manifest = json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))
    cfg_dict = dict(manifest["config"])
    for key in ("palette", "x_range", "y_range"):
        cfg_dict[key] = tuple(cfg_dict[key])
    cfg = CorpusConfig(**cfg_dict)
    regenerated = build(cfg, scratch)
    return regenerated.name == manifest["dataset_hash"], manifest["dataset_hash"], regenerated.name
