"""The frozen corpus: integrity, structure, ground truth, masking, and — with XY
installed — bit-exact regeneration from its seed."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from xybench import predicates as pred
from xybench.corpus import (
    PERMUTATION_SEED,
    CorpusConfig,
    build,
    verify_files,
    verify_regeneration,
)
from xybench.svgdoc import GEOM_TOKEN_RE, find_markers, geom_token, marker_id, unmask_geometry

from .conftest import needs_xy


def test_certificate_holds(corpus):
    assert verify_files(corpus.root) == []
    assert corpus.root.name == corpus.dataset_hash


def test_tampering_is_detected(corpus, tmp_path):
    import shutil

    copy = tmp_path / corpus.root.name
    shutil.copytree(corpus.root, copy)
    svg = next(copy.glob("charts/*.real.svg"))
    svg.write_bytes(svg.read_bytes().replace(b'r="3.5"', b'r="3.6"', 1))
    problems = verify_files(copy)
    assert any("hash mismatch" in p for p in problems)
    assert any("dataset hash" in p for p in problems)
    (copy / "charts" / "extra.svg").write_text("<svg/>")
    assert any("unlisted" in p for p in verify_files(copy))


def test_shape(corpus):
    assert len(corpus.charts) == 30 and len(corpus.cases) == 180
    per_chart = Counter(c.chart_id for c in corpus.cases)
    assert set(per_chart.values()) == {6}
    assert {c.k for c in corpus.charts.values()} <= {4, 5, 6, 7}
    assert corpus.manifest["permutation_seed"] == PERMUTATION_SEED
    assert corpus.manifest["config"]["seed"] != PERMUTATION_SEED  # SPEC I7


def test_permutation_seed_is_independent_of_corpus_seed():
    assert CorpusConfig().seed != PERMUTATION_SEED


def test_ids_are_deterministic_content_free_and_unique(corpus):
    for chart in corpus.charts.values():
        assert chart.ids == [marker_id(corpus.manifest["config"]["seed"], chart.chart_id, i) for i in range(chart.k)]
        assert all(re.fullmatch(r"e[0-9a-f]{8}", i) for i in chart.ids)
        assert len(set(chart.ids)) == chart.k


def test_ground_truth_is_from_rendered_pixels_with_margin(corpus):
    margin = corpus.manifest["config"]["margin_px"]
    for case in corpus.cases:
        chart = corpus.charts[case.chart_id]
        target, gap = pred.resolve(case.predicate, chart.centres, chart.plot_rect, margin)
        assert target == case.target_id
        assert gap >= margin
        assert chart.markers[case.target_index].id == case.target_id


def test_every_predicate_and_operation_is_used(corpus):
    assert set(c.predicate for c in corpus.cases) == set(pred.PREDICATES)
    assert set(c.operation for c in corpus.cases) == {"recolor_fill", "add_stroke", "delete", "resize"}
    assert {(c.target_variant, c.operation_variant) for c in corpus.cases} == {(0, 0), (0, 1), (1, 0), (1, 1)}


def test_masked_and_real_differ_only_in_marker_coordinates(corpus):
    seed = corpus.manifest["config"]["seed"]
    for chart in corpus.charts.values():
        masked_markers = find_markers(chart.masked_svg)
        for m in masked_markers:
            assert m.attrs["cx"] == geom_token(seed, chart.chart_id, m.id, "cx")
            assert m.attrs["cy"] == geom_token(seed, chart.chart_id, m.id, "cy")
        tokens = GEOM_TOKEN_RE.findall(chart.masked_svg)
        assert len(tokens) == 2 * chart.k == len(set(tokens))
        raw = {m.id: m.raw for m in chart.markers}
        assert unmask_geometry(chart.masked_svg, chart.centres, raw) == chart.real_svg
        # no marker coordinate survives anywhere inside a marker element
        for m in masked_markers:
            element = chart.masked_svg[m.span[0]: m.span[1]]
            assert not re.search(r'c[xy]="\d', element)


def test_svgs_are_xy_exports_with_nothing_else_carrying_positions(corpus):
    for chart in corpus.charts.values():
        tags = Counter(re.findall(r"<(\w+)", chart.real_svg))
        assert tags["circle"] == chart.k
        assert set(tags) <= {"svg", "defs", "clipPath", "rect", "g", "line", "text", "circle"}
        assert chart.real_svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')


def test_rejection_log_present(corpus):
    rej = json.loads((corpus.root / "rejections.json").read_text())
    assert set(rej["per_chart"]) == set(corpus.charts)
    assert rej["total"] == sum(rej["per_chart"].values())


@needs_xy
def test_regeneration_is_bit_exact(corpus, tmp_path):
    same, expected, got = verify_regeneration(corpus.root, tmp_path)
    assert same, (expected, got)


@needs_xy
def test_different_seed_different_corpus(tmp_path):
    a = build(CorpusConfig(seed=1, n_charts=2), tmp_path / "a")
    b = build(CorpusConfig(seed=2, n_charts=2), tmp_path / "b")
    a2 = build(CorpusConfig(seed=1, n_charts=2), tmp_path / "a2")
    assert a.name != b.name and a.name == a2.name
