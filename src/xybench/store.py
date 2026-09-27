"""Append-only response store: one directory per experiment.

``manifest.json`` pins what the experiment is — corpus hash, variant, condition, solver or
backend, template and scoring versions — and ``responses.jsonl`` accumulates one row per
case. A run resumes by skipping cases already present, and refuses to append to a
directory whose manifest describes a different experiment, so two configurations can
never be mixed in one file.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set


class ResponseStore:
    def __init__(self, directory: Path) -> None:
        self.dir = Path(directory)
        self.manifest_path = self.dir / "manifest.json"
        self.rows_path = self.dir / "responses.jsonl"

    # -- manifest --

    def open(self, manifest: Dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            existing = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            pinned = {k: existing.get(k) for k in _PINNED}
            asked = {k: manifest.get(k) for k in _PINNED}
            if pinned != asked:
                raise RuntimeError(
                    f"{self.dir} already holds a different experiment:\n  existing {pinned}\n  requested {asked}"
                )
            return
        manifest = dict(manifest)
        manifest["created_utc"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        self.manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def manifest(self) -> Dict[str, Any]:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    # -- rows --

    def rows(self) -> Iterator[Dict[str, Any]]:
        if not self.rows_path.exists():
            return iter(())
        return (json.loads(line) for line in self.rows_path.read_text(encoding="utf-8").splitlines() if line.strip())

    def done_case_ids(self) -> Set[str]:
        return {row["case_id"] for row in self.rows()}

    def append(self, row: Dict[str, Any]) -> None:
        with open(self.rows_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def load(self) -> List[Dict[str, Any]]:
        return list(self.rows())


_PINNED = ("dataset_hash", "variant", "condition", "solver", "model", "template_version", "scoring_version")
