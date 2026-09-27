"""Cluster-level inference. The resampling unit is the chart, never the case: six
instructions share a layout and are not independent.

* Interval: cluster bootstrap over charts (seeded; percentile interval).
* Test: paired cluster permutation on per-chart differences, sign-flipped. Pairing is valid
  because both arms see byte-identical cases.
* Minimum detectable effect — fixed here, before any model result exists:

      MDE = (z_0.975 + z_0.80) × SE_paired = 2.80 × SE_paired

  where SE_paired is the cluster-bootstrap standard error of the paired difference. If the
  arms are identical in every cluster SE_paired is 0 and says nothing, so the rule falls back
  to the unpaired SE, sqrt(SE_A² + SE_B²), and the report flags the fallback. With an
  observed difference of exactly zero the permutation p is 1.000 by construction; the MDE
  is the number to read.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

Clustered = Dict[str, List[float]]  # cluster id -> per-case values

Z_ALPHA = 1.959963984540054  # two-sided 0.05
Z_POWER = 0.8416212335729143  # 80 % power


def pooled_mean(values: Clustered) -> float:
    n = sum(len(v) for v in values.values())
    return sum(sum(v) for v in values.values()) / n if n else float("nan")


@dataclass(frozen=True)
class Interval:
    estimate: float
    lower: float
    upper: float
    se: float
    n_cases: int
    n_clusters: int


def cluster_bootstrap(values: Clustered, n_boot: int = 2000, seed: int = 0) -> Interval:
    clusters = sorted(values)
    sums = {c: sum(values[c]) for c in clusters}
    sizes = {c: len(values[c]) for c in clusters}
    rng = random.Random(seed)
    estimates: List[float] = []
    for _ in range(n_boot):
        picked = [rng.choice(clusters) for _ in clusters]
        n = sum(sizes[c] for c in picked)
        estimates.append(sum(sums[c] for c in picked) / n if n else float("nan"))
    estimates.sort()
    lo = estimates[int(math.floor(0.025 * (n_boot - 1)))]
    hi = estimates[int(math.ceil(0.975 * (n_boot - 1)))]
    mean_b = sum(estimates) / n_boot
    se = math.sqrt(sum((e - mean_b) ** 2 for e in estimates) / (n_boot - 1))
    return Interval(pooled_mean(values), lo, hi, se, sum(sizes.values()), len(clusters))


def _paired_clusters(a: Clustered, b: Clustered) -> Tuple[List[str], Dict[str, float], Dict[str, int]]:
    clusters = sorted(set(a) & set(b))
    diffs: Dict[str, float] = {}
    sizes: Dict[str, int] = {}
    for c in clusters:
        if len(a[c]) != len(b[c]):
            raise ValueError(f"cluster {c}: arms have different case counts ({len(a[c])} vs {len(b[c])})")
        sizes[c] = len(a[c])
        diffs[c] = (sum(a[c]) - sum(b[c])) / sizes[c]
    return clusters, diffs, sizes


@dataclass(frozen=True)
class PairedResult:
    difference: float
    p_value: float
    mde: float
    mde_fallback: bool
    se_paired: float
    n_clusters: int


def paired_cluster_test(a: Clustered, b: Clustered, n_perm: int = 10000, n_boot: int = 2000, seed: int = 0) -> PairedResult:
    """``a − b``: case-weighted mean of per-cluster differences, sign-flip permutation p,
    and the pre-registered MDE."""
    clusters, diffs, sizes = _paired_clusters(a, b)
    total = sum(sizes.values())

    def statistic(signs: Sequence[int]) -> float:
        return sum(s * diffs[c] * sizes[c] for s, c in zip(signs, clusters)) / total

    observed = statistic([1] * len(clusters))
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_perm):
        signs = [rng.choice((-1, 1)) for _ in clusters]
        if abs(statistic(signs)) >= abs(observed) - 1e-12:
            extreme += 1
    p = (1 + extreme) / (1 + n_perm)

    # bootstrap SE of the paired statistic (resample paired clusters)
    boot = random.Random(seed + 1)
    ests: List[float] = []
    for _ in range(n_boot):
        picked = [boot.choice(clusters) for _ in clusters]
        n = sum(sizes[c] for c in picked)
        ests.append(sum(diffs[c] * sizes[c] for c in picked) / n)
    mean_b = sum(ests) / n_boot
    se_paired = math.sqrt(sum((e - mean_b) ** 2 for e in ests) / (n_boot - 1))

    fallback = se_paired == 0.0
    if fallback:
        se = math.sqrt(cluster_bootstrap(a, n_boot, seed).se ** 2 + cluster_bootstrap(b, n_boot, seed).se ** 2)
    else:
        se = se_paired
    return PairedResult(observed, p, (Z_ALPHA + Z_POWER) * se, fallback, se_paired, len(clusters))


def random_selection_reference(ks: Sequence[int]) -> float:
    """Expected identification accuracy of a uniform guess: mean of 1/K over cases."""
    return sum(1.0 / k for k in ks) / len(ks) if ks else float("nan")
