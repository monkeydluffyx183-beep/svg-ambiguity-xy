"""The audit passes on the frozen corpus, and the CLI's run → evaluate → report path works
end to end with deterministic solvers, including resume."""

import json
from pathlib import Path

from xybench.audit import audit_corpus
from xybench.cli import main
from xybench.evaluate import evaluate_experiment
from xybench.report import build_report

from .conftest import frozen_corpus_dir


def test_audit_passes(corpus):
    checks = audit_corpus(corpus)
    failed = [c for c in checks if not c.ok]
    assert not failed, [(c.name, c.detail) for c in failed]
    assert len(checks) >= 20


def test_cli_roundtrip(corpus, tmp_path, capsys):
    c = str(frozen_corpus_dir())
    exps = tmp_path / "experiments"
    assert main(["run", "--corpus", c, "--experiments", str(exps), "--variant", "masked", "--condition", "enhanced",
                 "--solver", "oracle", "--limit", "7"]) == 0
    assert main(["run", "--corpus", c, "--experiments", str(exps), "--variant", "masked", "--condition", "enhanced",
                 "--solver", "oracle"]) == 0
    out = capsys.readouterr().out
    assert "7 done, 173 to run" in out
    for cond in ("baseline", "permuted"):
        assert main(["run", "--corpus", c, "--experiments", str(exps), "--variant", "masked", "--condition", cond,
                     "--solver", "random"]) == 0
    rows = [json.loads(l) for l in (exps / "masked-enhanced-oracle" / "responses.jsonl").read_text().splitlines()]
    assert len(rows) == 180 and len({r["case_id"] for r in rows}) == 180
    assert all(r["prompt_sha256"] and r["finish_reason"] == "stop" for r in rows)

    dirs = sorted(str(p) for p in exps.iterdir())
    assert main(["evaluate", "--corpus", c, *dirs]) == 0
    assert (exps / "masked-enhanced-oracle" / "evaluations.jsonl").exists()
    report_path = tmp_path / "report.md"
    assert main(["report", "--corpus", c, *dirs, "--out", str(report_path)]) == 0
    text = report_path.read_text()
    assert "| masked | enhanced | oracle | 180 | 1.0000 [1.0000, 1.0000]" in text
    assert "permuted − baseline" in text and "Selection-position distribution" in text

    capsys.readouterr()
    assert main(["status", "--corpus", c]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["corpus"]["dataset_hash"] == corpus.dataset_hash
    assert status["abstention_rule_version"] == "2.0"
    assert main(["verify", "--corpus", c]) == 0
    assert main(["prompt", "--corpus", c, "--variant", "real", "--condition", "named_id"]) == 0
    assert 'the marker with id "' in capsys.readouterr().out


def test_evaluate_refuses_other_corpus(corpus, tmp_path):
    from xybench.store import ResponseStore

    s = ResponseStore(tmp_path / "e")
    s.open({"dataset_hash": "not-this-one", "variant": "masked", "condition": "baseline", "solver": "echo", "model": None,
            "template_version": "1.0", "scoring_version": "1.0"})
    try:
        evaluate_experiment(corpus, tmp_path / "e")
    except RuntimeError as exc:
        assert "not" in str(exc)
    else:
        raise AssertionError("expected a corpus mismatch error")


def test_report_handles_a_single_experiment(corpus, tmp_path):
    from xybench.store import ResponseStore
    from xybench.solvers import deterministic_response

    s = ResponseStore(tmp_path / "solo")
    s.open({"dataset_hash": corpus.dataset_hash, "variant": "real", "condition": "baseline", "solver": "first", "model": None,
            "template_version": "1.0", "scoring_version": "1.0"})
    for case in corpus.cases:
        chart = corpus.charts[case.chart_id]
        s.append({"case_id": case.case_id, "response": deterministic_response("first", case, chart, "real"), "finish_reason": "stop"})
    rows = evaluate_experiment(corpus, tmp_path / "solo", write=False)
    text = build_report(corpus, [("solo", rows)])
    assert "no comparable arm pairs" in text
    assert "| real | baseline | first | 180 |" in text
