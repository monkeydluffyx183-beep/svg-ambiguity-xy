"""Each SPEC §7 check must catch the silent failure it exists for — and nothing else."""

import pytest

from fmtcontrol_xy import check_control, permute

FACTS = {"host-a": (12, 340), "host-b": (87, 120), "host-c": (45, 980), "host-d": (3, 45)}


def render(facts):
    lines = ["host    cpu%  p99ms"]
    for host, (cpu, p99) in facts.items():
        lines.append(f"{host:<7} {cpu:>4} {p99:>6}")
    return "\n".join(lines)


def test_a_valid_control_passes_and_reports_counts():
    control = permute(FACTS, "case-1", 991)
    report = check_control(FACTS, control, render(FACTS), render(control))
    assert report.ok and report.failures == ()
    assert report.n_entities == 4
    assert report.displaced >= 1
    assert report.token_delta == 0
    assert report.line_count_treatment == report.line_count_control == 5
    assert "OK" in str(report)


def test_identity_control_fails_i4_and_text_identity():
    report = check_control(FACTS, dict(FACTS), render(FACTS), render(FACTS))
    assert not report.ok
    assert any(f.startswith("I4") for f in report.failures)
    assert any("identical" in f for f in report.failures)


def test_missing_and_extra_entities_fail_i1():
    control = permute(FACTS, "case-1", 991)
    del control["host-d"]
    control["host-z"] = (0, 0)
    report = check_control(FACTS, control, render(FACTS), render(control))
    assert any(f.startswith("I1") and "host-d" in f and "host-z" in f for f in report.failures)


def test_reordered_entities_fail_i2():
    control = permute(FACTS, "case-1", 991)
    reordered = dict(reversed(list(control.items())))
    report = check_control(FACTS, reordered, render(FACTS), render(reordered))
    assert any(f.startswith("I2") for f in report.failures)
    assert not any(f.startswith("I1") for f in report.failures)


def test_altered_value_fails_i3():
    control = permute(FACTS, "case-1", 991)
    control["host-a"] = (999, 999)
    report = check_control(FACTS, control, render(FACTS), render(control))
    assert any(f.startswith("I3") for f in report.failures)


def test_multiset_check_handles_unhashable_values_and_duplicates():
    treatment = {"a": [1], "b": [1], "c": [2]}
    good = {"a": [2], "b": [1], "c": [1]}
    bad = {"a": [2], "b": [2], "c": [1]}
    assert not any(f.startswith("I3") for f in check_control(treatment, good, "t", "c").failures)
    assert any(f.startswith("I3") for f in check_control(treatment, bad, "t", "c").failures)


def test_token_and_line_count_confounds_are_reported_with_deltas():
    control = permute(FACTS, "case-1", 991)
    treatment_text = render(FACTS)
    control_text = render(control) + "\nnote: values shuffled"
    report = check_control(FACTS, control, treatment_text, control_text)
    assert report.token_delta == 3
    assert report.line_count_control == report.line_count_treatment + 1
    assert any("token count" in f for f in report.failures)
    assert any("line count" in f for f in report.failures)


def test_token_tolerance_is_absolute_and_symmetric():
    control = permute(FACTS, "case-1", 991)
    shorter = "\n".join(render(control).split("\n")[:-1]) + "\n" + "x"  # same lines, fewer tokens
    report = check_control(FACTS, control, render(FACTS), shorter, token_tolerance=2)
    assert report.token_delta == -2
    assert not any("token count" in f for f in report.failures)
    report = check_control(FACTS, control, render(FACTS), shorter, token_tolerance=1)
    assert any("token count" in f for f in report.failures)


def test_custom_tokenizer_is_used_for_the_count():
    control = permute(FACTS, "case-1", 991)
    chars = check_control(FACTS, control, render(FACTS), render(control), tokenizer=list)
    assert chars.token_count_treatment == len(render(FACTS))
    assert chars.ok


def test_negative_tolerance_rejected():
    with pytest.raises(ValueError):
        check_control(FACTS, FACTS, "a", "b", token_tolerance=-1)
