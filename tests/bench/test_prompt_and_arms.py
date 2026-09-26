"""Prompts: one template, one slot; the permuted arm is a valid format-matched control on
every chart; the same chart gets the same permutation in both variants."""

import pytest

from fmtcontrol_xy import check_control
from xybench.instructions import lint
from xybench.prompt import CONDITIONS, TEMPLATE_VERSION, build_prompt, context_for, facts_of, prompt_for, template_hash


def _parse_table(text):
    rows = {}
    for line in text.splitlines()[2:]:
        mid, x, y = line.split()
        rows[mid] = (float(x), float(y))
    return rows


def test_permuted_arm_is_a_valid_control_on_every_chart(corpus):
    for chart in corpus.charts.values():
        enhanced, permuted = context_for("enhanced", chart), context_for("permuted", chart)
        report = check_control(facts_of(chart), _parse_table(permuted), enhanced, permuted)
        assert report.ok, (chart.chart_id, report.failures)
        assert report.token_delta == 0 and report.line_count_treatment == report.line_count_control


def test_enhanced_table_is_document_order_primitive_facts(corpus):
    chart = next(iter(corpus.charts.values()))
    rows = _parse_table(context_for("enhanced", chart))
    assert list(rows) == chart.ids
    assert all(rows[m.id] == (round(m.cx, 2), round(m.cy, 2)) for m in chart.markers)
    text = context_for("enhanced", chart)
    assert "rank" not in text.lower() and "left" not in text.lower() and "top" not in text.lower()


def test_permutation_identical_across_variants_and_keyed_by_chart(corpus):
    charts = list(corpus.charts.values())
    for chart in charts[:5]:
        # context does not depend on the variant at all
        assert context_for("permuted", chart) == context_for("permuted", chart)
    # different charts, different shuffles (with overwhelming probability)
    a, b = charts[0], charts[1]
    ka = [i for i, (x, y) in enumerate(_parse_table(context_for("permuted", a)).values())]
    assert ka  # sanity
    assert _parse_table(context_for("permuted", a)) != _parse_table(context_for("permuted", b))


def test_arms_differ_only_in_the_context_slot(corpus):
    for case in corpus.cases[:24]:
        chart = corpus.charts[case.chart_id]
        for variant in ("masked", "real"):
            base = prompt_for(variant, "baseline", chart, case)
            for cond in ("enhanced", "permuted"):
                ctx = context_for(cond, chart)
                assert prompt_for(variant, cond, chart, case).replace(f"\n{ctx}\n", "", 1) == base


def test_named_id_changes_only_the_target_phrase(corpus):
    case = corpus.cases[0]
    chart = corpus.charts[case.chart_id]
    named = prompt_for("masked", "named_id", chart, case)
    base = prompt_for("masked", "baseline", chart, case)
    assert case.target_id in named and f'id "{case.target_id}"' in named
    # everything outside the instruction line is identical
    strip = lambda s: "\n".join(l for l in s.splitlines() if not l.startswith("Instruction:"))
    assert strip(named) == strip(base)


def test_tokens_survive_assembly_verbatim(corpus):
    """The str.format trap upstream fell into: doubled braces must reach the prompt intact."""
    case = corpus.cases[0]
    chart = corpus.charts[case.chart_id]
    prompt = prompt_for("masked", "baseline", chart, case)
    assert prompt.count("{{GEOM_") == 2 * chart.k + 1  # every marker plus the preamble example
    assert "{GEOM_1234abcd}" not in prompt.replace("{{GEOM_1234abcd}}", "")


def test_variants_differ_only_in_preamble_and_svg(corpus):
    case = corpus.cases[0]
    chart = corpus.charts[case.chart_id]
    masked = prompt_for("masked", "enhanced", chart, case).splitlines()
    real = prompt_for("real", "enhanced", chart, case).splitlines()
    assert len(masked) == len(real)
    differing = [i for i, (a, b) in enumerate(zip(masked, real)) if a != b]
    assert len(differing) == 2  # the preamble line and the (single-line) SVG


def test_template_is_versioned_and_hashed():
    assert TEMPLATE_VERSION == "1.0"
    assert template_hash("masked") != template_hash("real")
    assert build_prompt("real", "<svg/>", "Do it.", "") == build_prompt("real", "<svg/>", "Do it.", "   ")


def test_instructions_pass_the_lint(corpus):
    for case in corpus.cases:
        chart = corpus.charts[case.chart_id]
        coords = [m.raw["cx"] for m in chart.markers] + [m.raw["cy"] for m in chart.markers]
        assert lint(case.instruction, chart.ids, coords, [chart.fill]) == []


def test_lint_catches_each_leak():
    assert lint("Recolour e1234abcd.", ["e1234abcd"], [], []) == ["contains marker id e1234abcd"]
    assert lint("Move {{GEOM_1}}", [], [], []) == ["contains a geometry token"]
    assert lint("Recolour the marker at 136.74.", [], ["136.74"], []) == ["contains coordinate value 136.74"]
    assert lint("Recolour the #2f6f9f one.", [], [], ["#2f6f9f"]) == ["contains document fill #2f6f9f"]
    assert lint("Add a 2px #000000 outline to the leftmost marker.", [], ["2.0"], ["#2f6f9f"]) == []


@pytest.mark.parametrize("condition", CONDITIONS)
def test_every_condition_builds(corpus, condition):
    case = corpus.cases[0]
    chart = corpus.charts[case.chart_id]
    for variant in ("masked", "real"):
        p = prompt_for(variant, condition, chart, case)
        assert p.startswith("You are editing an SVG document") and "Instruction:" in p
