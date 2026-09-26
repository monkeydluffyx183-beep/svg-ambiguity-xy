"""Instrument audits that need no model. If one fails, a run still produces a number; it
is just the wrong number.

    python -m xybench audit --corpus data/frozen/<hash>
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from fmtcontrol_xy import check_control

from . import instructions as ins
from . import predicates as pred
from .corpus import VARIANTS, Corpus, verify_files
from .prompt import CONDITIONS, context_for, prompt_for
from .scoring import evaluate_response
from .solvers import DETERMINISTIC_SOLVERS, deterministic_response
from .stats import random_selection_reference
from .svgdoc import GEOM_TOKEN_RE, find_markers, unmask_geometry


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


def _check(checks: List[Check], name: str, ok: bool, detail: str = "") -> None:
    checks.append(Check(name, ok, detail))


def audit_corpus(corpus: Corpus) -> List[Check]:
    checks: List[Check] = []
    cfg = corpus.manifest["config"]

    problems = verify_files(corpus.root)
    _check(checks, "integrity certificate", not problems, "; ".join(problems))

    # -- structure and ground truth --
    bad: List[str] = []
    for chart in corpus.charts.values():
        if not (cfg["k_min"] <= chart.k <= cfg["k_max"]) or chart.k != len(chart.markers):
            bad.append(f"{chart.chart_id}: K={chart.k}")
        if len(set(chart.ids)) != chart.k:
            bad.append(f"{chart.chart_id}: duplicate ids")
        for variant in VARIANTS:
            ids = [m.id for m in find_markers(chart.svg(variant))]
            if ids != chart.ids:
                bad.append(f"{chart.chart_id}/{variant}: marker ids in file differ from record")
    _check(checks, "charts: K in range, ids unique, files match records", not bad, "; ".join(bad[:5]))

    bad = []
    by_chart: Dict[str, List] = {}
    for case in corpus.cases:
        chart = corpus.charts[case.chart_id]
        by_chart.setdefault(case.chart_id, []).append(case)
        target, gap = pred.resolve(case.predicate, chart.centres, chart.plot_rect, cfg["margin_px"])
        if target != case.target_id:
            bad.append(f"{case.case_id}: ground truth {case.target_id} != recomputed {target}")
        if abs(gap - case.gap_px) > 1e-3:
            bad.append(f"{case.case_id}: gap {case.gap_px} != recomputed {gap:.3f}")
        if chart.markers[case.target_index].id != case.target_id:
            bad.append(f"{case.case_id}: target_index inconsistent")
    _check(checks, "cases: ground truth recomputes with margin", not bad, "; ".join(bad[:5]))
    counts = Counter(len(v) for v in by_chart.values())
    _check(checks, "cases per chart", set(counts) == {cfg["cases_per_chart"]}, str(dict(counts)))

    bad = []
    for case in corpus.cases:
        chart = corpus.charts[case.chart_id]
        coords = [m.raw["cx"] for m in chart.markers] + [m.raw["cy"] for m in chart.markers]
        p = ins.lint(case.instruction, chart.ids, coords, [chart.fill])
        if p:
            bad.append(f"{case.case_id}: {p}")
    _check(checks, "instruction lint: no ids, tokens, coordinates or fills", not bad, "; ".join(bad[:5]))

    # -- masking --
    bad = []
    for chart in corpus.charts.values():
        masked = chart.masked_svg
        tokens = GEOM_TOKEN_RE.findall(masked)
        for m in find_markers(masked):
            if not (GEOM_TOKEN_RE.fullmatch(m.attrs["cx"]) and GEOM_TOKEN_RE.fullmatch(m.attrs["cy"])):
                bad.append(f"{chart.chart_id}: marker {m.id} not masked")
        if len(tokens) != 2 * chart.k or len(set(tokens)) != len(tokens):
            bad.append(f"{chart.chart_id}: {len(tokens)} tokens, {len(set(tokens))} distinct, expected {2 * chart.k}")
        raw = {m.id: m.raw for m in chart.markers}
        if unmask_geometry(masked, chart.centres, raw) != chart.real_svg:
            bad.append(f"{chart.chart_id}: masked ≠ real after unmasking")
    _check(checks, "masked variant: every marker coordinate is an opaque token; unmask == real", not bad, "; ".join(bad[:5]))

    # -- arms --
    bad = []
    deltas: List[int] = []
    for chart in corpus.charts.values():
        enhanced, permuted = context_for("enhanced", chart), context_for("permuted", chart)
        facts = {m.id: (m.cx, m.cy) for m in chart.markers}
        shuffled = {}
        for line in permuted.splitlines()[2:]:
            mid, x, y = line.split()
            shuffled[mid] = (float(x), float(y))
        report = check_control(facts, shuffled, enhanced, permuted)
        deltas.append(report.token_delta)
        if not report.ok:
            bad.append(f"{chart.chart_id}: {report.failures}")
    _check(checks, "permuted arm passes check_control on every chart", not bad,
           f"token deltas: {sorted(set(deltas))}" if not bad else "; ".join(bad[:3]))

    bad = []
    for case in corpus.cases[: len(corpus.cases)]:
        chart = corpus.charts[case.chart_id]
        for variant in VARIANTS:
            base = prompt_for(variant, "baseline", chart, case)
            for cond in ("enhanced", "permuted"):
                ctx = context_for(cond, chart)
                stripped = prompt_for(variant, cond, chart, case).replace(f"\n{ctx}\n", "", 1)
                if stripped != base:
                    bad.append(f"{case.case_id}/{variant}/{cond}: arms differ outside the context slot")
            if variant == "masked":
                p = prompt_for(variant, "baseline", chart, case)
                if p.count("{{GEOM_") != 2 * chart.k + 1:  # markers + the one in the preamble
                    bad.append(f"{case.case_id}: tokens not verbatim in prompt")
    _check(checks, "arms differ only in the context slot; tokens verbatim in prompts", not bad, "; ".join(bad[:5]))

    # -- document-order leakage --
    ks = [c.k for c in corpus.cases]
    ref = random_selection_reference(ks)
    first_share = sum(1 for c in corpus.cases if c.target_index == 0) / len(corpus.cases)
    pos = Counter(c.target_index for c in corpus.cases)
    _check(
        checks,
        "target position: 'first marker' policy scores near the uniform reference",
        abs(first_share - ref) < 0.10,
        f"share of targets at index 0 = {first_share:.3f}, reference mean(1/K) = {ref:.3f}, distribution {dict(sorted(pos.items()))}",
    )

    # -- deterministic solver sweep (the scorer, end to end) --
    expectations: Dict[str, Tuple[str, Callable[[Dict[str, int], int], bool]]] = {
        "oracle": ("CORRECT_STRICT", lambda c, n: c["CORRECT_STRICT"] == n),
        "echo": ("NO_EDIT", lambda c, n: c["NO_EDIT"] == n),
        "abstain": ("ABSTAINED", lambda c, n: c["ABSTAINED"] == n),
        "prose": ("REFUSED_PROSE", lambda c, n: c["REFUSED_PROSE"] == n),
        "truncated": ("MALFORMED", lambda c, n: c["MALFORMED"] == n),
    }
    for variant in VARIANTS:
        for solver in DETERMINISTIC_SOLVERS:
            outcomes: Counter = Counter()
            identified = 0
            for case in corpus.cases:
                chart = corpus.charts[case.chart_id]
                ev = evaluate_response(case, chart, variant, deterministic_response(solver, case, chart, variant))
                outcomes[ev.outcome] += 1
                identified += ev.identified
            n = len(corpus.cases)
            acc = identified / n
            if solver in expectations:
                expected, ok_fn = expectations[solver]
                ok = ok_fn(outcomes, n) and (acc == 1.0 if solver == "oracle" else acc == 0.0)
                _check(checks, f"{variant}: {solver} -> {expected} on all cases", ok, f"outcomes {dict(outcomes)}, identification {acc:.3f}")
            else:
                ok = abs(acc - ref) < 0.10
                _check(checks, f"{variant}: {solver} identification ≈ reference", ok, f"{acc:.3f} vs {ref:.3f}, outcomes {dict(outcomes)}")
    return checks


def format_checks(checks: List[Check]) -> str:
    width = max(len(c.name) for c in checks)
    lines = [f"{'PASS' if c.ok else 'FAIL'}  {c.name:<{width}}  {c.detail}" for c in checks]
    n_ok = sum(c.ok for c in checks)
    lines.append(f"\n{n_ok}/{len(checks)} checks passed")
    return "\n".join(lines)
