"""Run the published conformance vectors against this implementation (SPEC §8, §10).

    python -m fmtcontrol_xy.conformance            # bundled vectors
    python -m fmtcontrol_xy.conformance path.json  # another vectors file

Exit status is 0 only if every vector reproduces and every ``must_raise`` case raises.
Comparison is done in the JSON domain, as §10 instructs, so a tuple/list difference is
not reported as a conformance failure.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .control import SPEC_VERSION, NoControlError, permute

BUNDLED_VECTORS = Path(__file__).with_name("conformance_vectors.json")


@dataclass(frozen=True)
class VectorResult:
    id: str
    kind: str  # "vector" | "must_raise"
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class ConformanceResult:
    spec_version: str
    results: Tuple[VectorResult, ...]

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def summary(self) -> str:
        vectors = [r for r in self.results if r.kind == "vector"]
        raises = [r for r in self.results if r.kind == "must_raise"]
        return (
            f"spec {self.spec_version}: "
            f"{sum(r.passed for r in vectors)}/{len(vectors)} vectors reproduced, "
            f"{sum(r.passed for r in raises)}/{len(raises)} must_raise cases raised"
        )


def _json_domain(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _run_vector(vector: Dict[str, Any]) -> VectorResult:
    facts = dict(zip(vector["entities"], vector["values"]))
    expected = vector["expected_permuted_values"]
    try:
        control = permute(facts, key=vector["key"], seed=vector["seed"])
    except Exception as exc:  # noqa: BLE001 - any exception is a conformance failure here
        return VectorResult(vector["id"], "vector", False, f"raised {type(exc).__name__}: {exc}")
    actual = [control[e] for e in vector["entities"]]
    if list(control.keys()) != list(vector["entities"]):
        return VectorResult(vector["id"], "vector", False, "entity order changed")
    if _json_domain(actual) != _json_domain(expected):
        return VectorResult(vector["id"], "vector", False, f"expected {expected!r}, got {actual!r}")
    return VectorResult(vector["id"], "vector", True)


def _run_must_raise(case: Dict[str, Any]) -> VectorResult:
    facts = dict(zip(case["entities"], case["values"]))
    try:
        result = permute(facts, key=case["key"], seed=case["seed"])
    except NoControlError as exc:
        return VectorResult(case["id"], "must_raise", True, f"NoControlError: {exc}")
    except Exception as exc:  # noqa: BLE001
        return VectorResult(
            case["id"], "must_raise", False, f"raised {type(exc).__name__}, not NoControlError: {exc}"
        )
    return VectorResult(case["id"], "must_raise", False, f"returned {result!r} instead of raising")


def run_conformance(path: Optional[Path] = None) -> ConformanceResult:
    """Execute every vector and must_raise case in ``path`` (default: the bundled file)."""
    data = json.loads((path or BUNDLED_VECTORS).read_text(encoding="utf-8"))
    results: List[VectorResult] = []
    spec_version = str(data.get("spec_version", "?"))
    if spec_version.split(".")[0] != SPEC_VERSION.split(".")[0]:
        results.append(
            VectorResult(
                "spec-version",
                "vector",
                False,
                f"vectors are for spec {spec_version}; this implements {SPEC_VERSION} "
                "(SPEC §9: vectors are only stable within a major version)",
            )
        )
    results.extend(_run_vector(v) for v in data.get("vectors", []))
    results.extend(_run_must_raise(c) for c in data.get("must_raise", []))
    return ConformanceResult(spec_version=spec_version, results=tuple(results))


def format_report(result: ConformanceResult) -> str:
    """Markdown table in the shape of upstream's independent-implementation issue template."""
    rows = ["| vector id | matched? | notes |", "|---|---|---|"]
    for r in result.results:
        label = r.id + (" (must raise)" if r.kind == "must_raise" else "")
        rows.append(f"| {label} | {'yes' if r.passed else 'NO'} | {r.detail} |")
    rows.append("")
    rows.append(result.summary)
    return "\n".join(rows)


def main(argv: Sequence[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else None
    result = run_conformance(path)
    print(format_report(result))
    return 0 if result.ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv))
