"""Markdown report over one or more evaluated experiments."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .corpus import Corpus
from .predicates import PREDICATES
from .scoring import OUTCOMES
from .stats import Clustered, cluster_bootstrap, paired_cluster_test, random_selection_reference

Rows = List[Dict[str, Any]]


def _clustered(rows: Rows, key: str) -> Clustered:
    out: Clustered = defaultdict(list)
    for r in rows:
        out[r["chart_id"]].append(1.0 if r[key] else 0.0)
    return dict(out)


def _rate(rows: Rows, pred) -> float:
    return sum(1 for r in rows if pred(r)) / len(rows) if rows else float("nan")


def _label(rows: Rows) -> str:
    r = rows[0]
    who = r["model"] or r["solver"]
    return f"{r['variant']}/{r['condition']}/{who}"


def _group(experiments: Sequence[Tuple[str, Rows]]) -> Dict[Tuple[str, str, str], Rows]:
    grouped: Dict[Tuple[str, str, str], Rows] = {}
    for _, rows in experiments:
        if not rows:
            continue
        r = rows[0]
        grouped[(r["variant"], r["condition"], r["model"] or r["solver"])] = rows
    return grouped


def _mde_note(res) -> str:
    if res.mde == 0.0:
        return "no between-chart variance in either arm; MDE undefined"
    if res.mde_fallback:
        return "MDE from unpaired SE (arms identical in every chart)"
    return ""


def build_report(corpus: Corpus, experiments: Sequence[Tuple[str, Rows]], seed: int = 0) -> str:
    grouped = _group(experiments)
    ks = [c.k for c in corpus.cases]
    ref = random_selection_reference(ks)
    lines: List[str] = []
    lines.append(f"# xybench report")
    lines.append("")
    lines.append(
        f"corpus `{corpus.dataset_hash[:12]}` · {len(corpus.cases)} cases · {len(corpus.charts)} charts "
        f"(clusters) · random-selection reference {ref:.4f} · CI = cluster bootstrap 95 %"
    )
    lines.append("")

    # -- per-arm table --
    lines.append("## Arms")
    lines.append("")
    lines.append(
        "| variant | condition | solver / model | n | identification (exclusive) | inclusive | strict | "
        "NO_EDIT | ABSTAINED | REFUSED_PROSE | MALFORMED | multi-edit |"
    )
    lines.append("|---|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    for (variant, condition, who), rows in sorted(grouped.items()):
        ci = cluster_bootstrap(_clustered(rows, "identified"), seed=seed)
        inc = _rate(rows, lambda r: r["identified_inclusive"])
        strict = _rate(rows, lambda r: r["outcome"] == "CORRECT_STRICT")
        counts = Counter(r["outcome"] for r in rows)
        n = len(rows)
        multi = _rate(rows, lambda r: r["n_changed"] > 1)
        lines.append(
            f"| {variant} | {condition} | {who} | {n} | {ci.estimate:.4f} [{ci.lower:.4f}, {ci.upper:.4f}] | "
            f"{inc:.4f} | {strict:.4f} | {counts['NO_EDIT'] / n:.3f} | {counts['ABSTAINED'] / n:.3f} | "
            f"{counts['REFUSED_PROSE'] / n:.3f} | {counts['MALFORMED'] / n:.3f} | {multi:.3f} |"
        )
    lines.append("")

    # -- pairwise, within variant & solver --
    pairs = [("enhanced", "permuted"), ("permuted", "baseline"), ("enhanced", "baseline"), ("named_id", "enhanced")]
    solvers = sorted({who for (_, _, who) in grouped})
    variants = sorted({v for (v, _, _) in grouped})
    lines.append("## Pairwise differences (identification, exclusive) — paired cluster permutation")
    lines.append("")
    lines.append("| variant | solver / model | comparison | difference | p | MDE | note |")
    lines.append("|---|---|---|---:|---:|---:|---|")
    any_pair = False
    for variant in variants:
        for who in solvers:
            for a, b in pairs:
                ra, rb = grouped.get((variant, a, who)), grouped.get((variant, b, who))
                if not ra or not rb:
                    continue
                res = paired_cluster_test(_clustered(ra, "identified"), _clustered(rb, "identified"), seed=seed)
                note = _mde_note(res)
                lines.append(
                    f"| {variant} | {who} | {a} − {b} | {res.difference:+.4f} | {res.p_value:.3f} | {res.mde:.4f} | {note} |"
                )
                any_pair = True
    if not any_pair:
        lines.append("| — | — | — | — | — | — | no comparable arm pairs |")
    lines.append("")

    # -- cross-variant --
    lines.append("## Cross-variant differences (real − masked), same condition and solver")
    lines.append("")
    lines.append("| condition | solver / model | difference | p | MDE |")
    lines.append("|---|---|---:|---:|---:|")
    any_cross = False
    for (variant, condition, who), rows in sorted(grouped.items()):
        if variant != "real":
            continue
        other = grouped.get(("masked", condition, who))
        if not other:
            continue
        res = paired_cluster_test(_clustered(rows, "identified"), _clustered(other, "identified"), seed=seed)
        lines.append(f"| {condition} | {who} | {res.difference:+.4f} | {res.p_value:.3f} | {res.mde:.4f} |")
        any_cross = True
    if not any_cross:
        lines.append("| — | — | — | — | — |")
    lines.append("")

    # -- per predicate --
    lines.append("## Identification by predicate (exclusive)")
    lines.append("")
    header = "| variant | condition | solver / model | " + " | ".join(PREDICATES) + " |"
    lines.append(header)
    lines.append("|---|---|---|" + "---:|" * len(PREDICATES))
    for (variant, condition, who), rows in sorted(grouped.items()):
        by_pred = defaultdict(list)
        for r in rows:
            by_pred[r["predicate"]].append(r)
        cells = []
        for p in PREDICATES:
            sub = by_pred.get(p, [])
            cells.append(f"{_rate(sub, lambda r: r['identified']):.2f} (n={len(sub)})" if sub else "—")
        lines.append(f"| {variant} | {condition} | {who} | " + " | ".join(cells) + " |")
    lines.append("")

    # -- selection position --
    lines.append("## Selection-position distribution")
    lines.append("")
    lines.append(
        "Document index of the single edited marker, among responses that edited exactly one. "
        "A uniform guess is flat; a fixed policy ('always the first') is a spike at 0 with the same mean."
    )
    lines.append("")
    max_k = max(ks) if ks else 0
    lines.append("| variant | condition | solver / model | n single-edit | " + " | ".join(str(i) for i in range(max_k)) + " |")
    lines.append("|---|---|---|---:|" + "---:|" * max_k)
    for (variant, condition, who), rows in sorted(grouped.items()):
        single = [r for r in rows if r["selected_index"] is not None]
        counts = Counter(r["selected_index"] for r in single)
        cells = [f"{counts[i] / len(single):.2f}" if single else "—" for i in range(max_k)]
        lines.append(f"| {variant} | {condition} | {who} | {len(single)} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)
