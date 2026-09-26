"""Score a stored experiment: ``responses.jsonl`` → ``evaluations.jsonl``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .corpus import Corpus
from .scoring import SCORING_VERSION, evaluate_response
from .store import ResponseStore


def evaluate_experiment(corpus: Corpus, experiment_dir: Path, write: bool = True) -> List[Dict[str, Any]]:
    store = ResponseStore(experiment_dir)
    manifest = store.manifest()
    if manifest["dataset_hash"] != corpus.dataset_hash:
        raise RuntimeError(
            f"experiment was run on corpus {manifest['dataset_hash'][:12]}, not {corpus.dataset_hash[:12]}"
        )
    variant = manifest["variant"]
    cases = {c.case_id: c for c in corpus.cases}
    rows: List[Dict[str, Any]] = []
    for r in store.rows():
        case = cases[r["case_id"]]
        chart = corpus.charts[case.chart_id]
        ev = evaluate_response(case, chart, variant, r["response"], r.get("finish_reason"))
        rows.append(
            {
                "case_id": case.case_id, "chart_id": case.chart_id, "k": case.k, "predicate": case.predicate,
                "operation": case.operation, "target_index": case.target_index, "variant": variant,
                "condition": manifest["condition"], "solver": manifest["solver"], "model": manifest.get("model"),
                "scoring_version": SCORING_VERSION, **ev.as_dict(),
            }
        )
    if write:
        out = experiment_dir / "evaluations.jsonl"
        out.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    return rows
