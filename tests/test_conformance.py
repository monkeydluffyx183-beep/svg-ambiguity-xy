"""Level 2 conformance: every published vector reproduces, every must_raise case raises.

The vectors file is a byte-for-byte copy of upstream's; its SHA-256 is pinned here so a
silent edit to the vectors cannot masquerade as conformance (SPEC §9).
"""

import hashlib
import json

import pytest

from fmtcontrol_xy import SPEC_VERSION, NoControlError, permute
from fmtcontrol_xy.conformance import BUNDLED_VECTORS, format_report, run_conformance

UPSTREAM_VECTORS_SHA256 = "cea747eeee90456b5326c1022696fefcd7709d0fb15a746b265d9e3299807be9"

DATA = json.loads(BUNDLED_VECTORS.read_text(encoding="utf-8"))


def test_vectors_file_is_the_published_one():
    assert hashlib.sha256(BUNDLED_VECTORS.read_bytes()).hexdigest() == UPSTREAM_VECTORS_SHA256
    assert DATA["spec_version"] == SPEC_VERSION


@pytest.mark.parametrize("vector", DATA["vectors"], ids=[v["id"] for v in DATA["vectors"]])
def test_vector_reproduces_exactly(vector):
    facts = dict(zip(vector["entities"], vector["values"]))
    control = permute(facts, key=vector["key"], seed=vector["seed"])
    # I1/I2 — same entities, same order
    assert list(control.keys()) == vector["entities"]
    # SPEC §10: compare in the JSON domain
    actual = json.loads(json.dumps([control[e] for e in vector["entities"]]))
    assert actual == vector["expected_permuted_values"]


@pytest.mark.parametrize("case", DATA["must_raise"], ids=[c["id"] for c in DATA["must_raise"]])
def test_must_raise_cases_raise(case):
    facts = dict(zip(case["entities"], case["values"]))
    with pytest.raises(NoControlError) as info:
        permute(facts, key=case["key"], seed=case["seed"])
    # The vectors file carries an ``error`` phrase; the spec does not say whether it must
    # be matched (SPEC_NOTES §N4). We match it anyway, as the cheapest way to be safe.
    assert case["error"] in str(info.value)


def test_runner_agrees_with_parametrised_tests():
    result = run_conformance()
    assert result.ok, format_report(result)
    assert len([r for r in result.results if r.kind == "vector"]) == 10
    assert len([r for r in result.results if r.kind == "must_raise"]) == 2


def test_runner_reports_a_failure_honestly(tmp_path):
    broken = json.loads(json.dumps(DATA))
    broken["vectors"][0]["expected_permuted_values"] = list(reversed(broken["vectors"][0]["values"]))
    path = tmp_path / "vectors.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    result = run_conformance(path)
    assert not result.ok
    failed = [r for r in result.results if not r.passed]
    assert [r.id for r in failed] == ["basic-3"]
    assert "expected" in failed[0].detail


def test_runner_flags_major_version_mismatch(tmp_path):
    other = json.loads(json.dumps(DATA))
    other["spec_version"] = "2.0"
    path = tmp_path / "vectors.json"
    path.write_text(json.dumps(other), encoding="utf-8")
    result = run_conformance(path)
    assert not result.ok
    assert result.results[0].id == "spec-version"
