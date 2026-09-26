"""Fixtures for the xybench tests.

Most tests run against the frozen corpus committed under ``data/frozen`` and need no XY
install. Tests that generate charts are skipped when ``xy`` is missing (it needs
Python ≥ 3.11).
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from xybench.corpus import load_corpus, xy_version  # noqa: E402

FROZEN_ROOT = ROOT / "data" / "frozen"


def frozen_corpus_dir() -> Path:
    dirs = sorted(p for p in FROZEN_ROOT.glob("*") if (p / "manifest.json").exists())
    assert len(dirs) == 1, f"expected exactly one frozen corpus, found {dirs}"
    return dirs[0]


@pytest.fixture(scope="session")
def corpus():
    return load_corpus(frozen_corpus_dir())


needs_xy = pytest.mark.skipif(xy_version() is None, reason="the XY charting library is not installed")
