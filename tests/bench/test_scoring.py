"""The scorer, one behaviour per test: every outcome class, both identification
definitions, colour and number canonicalisation, and the FA-013 distinction between a
prose refusal and broken output."""

import pytest

from xybench.scoring import (
    OUTCOMES,
    attrs_equal,
    detects_abstention,
    evaluate_response,
    extract_svg,
    normalise_colour,
)
from xybench.solvers import apply_edit, deterministic_response


def _case(corpus, operation=None, predicate=None):
    for c in corpus.cases:
        if (operation is None or c.operation == operation) and (predicate is None or c.predicate == predicate):
            return c, corpus.charts[c.chart_id]
    raise AssertionError("no such case")


@pytest.mark.parametrize("variant", ["masked", "real"])
@pytest.mark.parametrize("operation", ["recolor_fill", "add_stroke", "delete", "resize"])
def test_oracle_is_correct_strict_for_every_operation(corpus, variant, operation):
    case, chart = _case(corpus, operation)
    ev = evaluate_response(case, chart, variant, deterministic_response("oracle", case, chart, variant))
    assert ev.outcome == "CORRECT_STRICT" and ev.identified and ev.identified_inclusive and ev.edit_correct
    assert ev.changed_ids == [case.target_id] and ev.selected_index == case.target_index
    assert not ev.non_marker_changed and ev.extra_markers == 0


def test_wrong_target_when_the_edit_lands_elsewhere(corpus):
    case, chart = _case(corpus, "recolor_fill")
    other = next(i for i in chart.ids if i != case.target_id)
    ev = evaluate_response(case, chart, "masked", apply_edit(chart.masked_svg, other, case.operation, case.params))
    assert ev.outcome == "WRONG_TARGET" and not ev.identified and not ev.identified_inclusive
    assert ev.changed_ids == [other]


def test_right_target_wrong_edit_is_wrong_target_but_identified(corpus):
    case, chart = _case(corpus, "recolor_fill")
    resp = apply_edit(chart.masked_svg, case.target_id, "add_stroke", {"stroke": "#000000", "stroke_width": 2})
    ev = evaluate_response(case, chart, "masked", resp)
    assert ev.outcome == "WRONG_TARGET"
    assert ev.identified and ev.target_changed and not ev.edit_correct


def test_collateral_makes_it_loose_and_breaks_exclusive_identification(corpus):
    case, chart = _case(corpus, "recolor_fill")
    other = next(i for i in chart.ids if i != case.target_id)
    resp = apply_edit(chart.masked_svg, case.target_id, case.operation, case.params)
    resp = apply_edit(resp, other, "recolor_fill", {"fill": "#123456"})
    ev = evaluate_response(case, chart, "masked", resp)
    assert ev.outcome == "CORRECT_LOOSE"
    assert ev.identified_inclusive and not ev.identified
    assert ev.collateral == [other] and ev.n_changed == 2 and ev.selected_index is None


def test_editing_every_marker_identifies_nothing_exclusively(corpus):
    case, chart = _case(corpus, "recolor_fill")
    resp = chart.masked_svg
    for mid in chart.ids:
        resp = apply_edit(resp, mid, case.operation, case.params)
    ev = evaluate_response(case, chart, "masked", resp)
    assert ev.outcome == "CORRECT_LOOSE" and ev.identified_inclusive and not ev.identified
    assert ev.n_changed == chart.k


def test_no_edit_and_abstained(corpus):
    case, chart = _case(corpus)
    assert evaluate_response(case, chart, "masked", chart.masked_svg).outcome == "NO_EDIT"
    assert evaluate_response(case, chart, "masked", "```svg\n" + chart.masked_svg + "\n```").outcome == "NO_EDIT"
    hedged = "I cannot determine which marker is meant, so here is the document unchanged:\n" + chart.masked_svg
    ev = evaluate_response(case, chart, "masked", hedged)
    assert ev.outcome == "ABSTAINED" and ev.abstention_signal
    assert evaluate_response(case, chart, "masked", "There is not enough information to identify the marker.").outcome == "ABSTAINED"


def test_prose_refusal_is_not_malformed(corpus):
    """FA-013: a model that declines in words the regexes do not match is REFUSED_PROSE."""
    case, chart = _case(corpus)
    ev = evaluate_response(case, chart, "masked", "Happy to help — which of the markers did you have in mind? Please clarify.")
    # a clarifying question *does* match the abstention rule
    assert ev.outcome == "ABSTAINED"
    ev = evaluate_response(case, chart, "masked", "Sure! Open the file in an editor and change the attribute you want.")
    assert ev.outcome == "REFUSED_PROSE" and ev.malformed_reason is None
    assert evaluate_response(case, chart, "masked", "").outcome == "REFUSED_PROSE"


def test_malformed_variants(corpus):
    case, chart = _case(corpus)
    half = chart.masked_svg[: len(chart.masked_svg) // 2]
    ev = evaluate_response(case, chart, "masked", half)
    assert ev.outcome == "MALFORMED" and "truncated" in ev.malformed_reason
    broken = chart.masked_svg.replace("</g>", "<g>", 1)
    assert evaluate_response(case, chart, "masked", broken).malformed_reason == "xml parse error"
    renamed = chart.masked_svg
    for mid in chart.ids:
        renamed = renamed.replace(f'id="{mid}"', f'id="new_{mid}"')
    ev = evaluate_response(case, chart, "masked", renamed)
    assert ev.outcome == "MALFORMED" and ev.malformed_reason.startswith("alignment")


def test_truncation_flag_comes_from_finish_reason(corpus):
    case, chart = _case(corpus)
    ev = evaluate_response(case, chart, "masked", chart.masked_svg, finish_reason="length")
    assert ev.truncated and ev.outcome == "NO_EDIT"


def test_last_svg_block_wins():
    assert extract_svg("first <svg a='1'></svg> then <svg a='2'></svg>") == "<svg a='2'></svg>"
    assert extract_svg("no document here") is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("I can't tell which marker you mean.", True),
        ("Unable to identify the target.", True),
        ("Positions are redacted, so the leftmost marker cannot be identified.", True),
        ("I changed the second marker's fill.", False),
        ("Here is the edited document.", False),
    ],
)
def test_abstention_rule(text, expected):
    assert detects_abstention(text) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("#0000FF", "#0000ff"), ("#00f", "#0000ff"), ("blue", "#0000ff"), ("rgb(0, 0, 255)", "#0000ff"),
        ("rgb(0%, 0%, 100%)", "#0000ff"), ("rgba(0,0,255,0.5)", "#0000ff"), ("#0000ff80", "#0000ff"),
        ("lime", "#00ff00"), ("green", "#008000"), ("magenta", "#ff00ff"), ("fuchsia", "#ff00ff"), ("none", "none"),
    ],
)
def test_colour_canonicalisation(value, expected):
    assert normalise_colour(value) == expected


def test_recolor_accepts_any_spelling_and_style_attribute(corpus):
    case, chart = _case(corpus, "recolor_fill")
    want = case.params["fill"]
    named = {"#ff0000": "red", "#00ff00": "lime", "#0000ff": "blue", "#ff00ff": "magenta"}[want]
    for spelling in (want.upper(), named, f"rgb({int(want[1:3], 16)},{int(want[3:5], 16)},{int(want[5:7], 16)})"):
        resp = apply_edit(chart.real_svg, case.target_id, "recolor_fill", {"fill": spelling})
        assert evaluate_response(case, chart, "real", resp).outcome == "CORRECT_STRICT", spelling
    styled = chart.real_svg.replace(f'id="{case.target_id}"', f'id="{case.target_id}" style="fill: {want}"', 1)
    assert evaluate_response(case, chart, "real", styled).outcome == "CORRECT_STRICT"


def test_numeric_tolerance_and_px_units():
    assert attrs_equal({"r": "3.5"}, {"r": "3.50"})
    assert attrs_equal({"stroke-width": "2"}, {"stroke-width": "2px"})
    assert not attrs_equal({"r": "3.5"}, {"r": "3.6"})
    assert not attrs_equal({"r": "3.5"}, {"r": "3.5", "stroke": "none"})


def test_resize_and_stroke_execution_checks(corpus):
    case, chart = _case(corpus, "resize")
    wrong = apply_edit(chart.real_svg, case.target_id, "resize", {"factor": 3.0})
    ev = evaluate_response(case, chart, "real", wrong)
    assert ev.outcome == "WRONG_TARGET" and ev.identified and not ev.edit_correct
    case, chart = _case(corpus, "add_stroke")
    wrong_width = apply_edit(chart.real_svg, case.target_id, "add_stroke", {"stroke": case.params["stroke"], "stroke_width": 9})
    assert not evaluate_response(case, chart, "real", wrong_width).edit_correct


def test_outcomes_are_the_documented_set(corpus):
    seen = set()
    case, chart = _case(corpus, "delete")
    for solver in ("oracle", "echo", "abstain", "prose", "truncated"):
        seen.add(evaluate_response(case, chart, "masked", deterministic_response(solver, case, chart, "masked")).outcome)
    assert seen <= set(OUTCOMES) and len(seen) == 5
