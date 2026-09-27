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


def test_cli_run_against_a_fake_ollama_server(corpus, tmp_path, capsys):
    """The path a real run takes: CLI -> backend -> store -> evaluate, with the backend's
    finish reason and options recorded. The fake server behaves like a model that returns
    the document from the prompt unchanged, so every case scores NO_EDIT."""
    import json as _json
    import re
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = []

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            prompt = body["messages"][0]["content"]
            svg = re.search(r"<svg\b.*?</svg\s*>", prompt, re.DOTALL).group(0)
            data = _json.dumps({"message": {"role": "assistant", "content": "Here you go:\n" + svg},
                                "done_reason": "stop", "eval_count": 5, "prompt_eval_count": 1000}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        c = str(frozen_corpus_dir())
        exps = tmp_path / "experiments"
        rc = main(["run", "--corpus", c, "--experiments", str(exps), "--variant", "masked", "--condition", "enhanced",
                   "--solver", "ollama", "--model", "fake:1b", "--host", f"http://127.0.0.1:{httpd.server_port}",
                   "--max-tokens", "777", "--num-ctx", "4096", "--limit", "6"])
    finally:
        httpd.shutdown()
    assert rc == 0
    exp = exps / "masked-enhanced-fake_1b"
    manifest = json.loads((exp / "manifest.json").read_text())
    assert manifest["backend"] == {"backend": "ollama", "model": "fake:1b", "host": f"http://127.0.0.1:{httpd.server_port}",
                                   "max_tokens": 777, "num_ctx": 4096, "seed": 0, "temperature": 0}
    assert len(seen) == 6 and seen[0]["options"]["num_predict"] == 777 and seen[0]["stream"] is False
    rows = [json.loads(l) for l in (exp / "responses.jsonl").read_text().splitlines()]
    assert len(rows) == 6 and all(r["finish_reason"] == "stop" and r["meta"]["eval_count"] == 5 for r in rows)
    assert all(r["prompt_sha256"] and r["latency_ms"] >= 0 for r in rows)
    evaluated = evaluate_experiment(corpus, exp)
    assert [e["outcome"] for e in evaluated] == ["NO_EDIT"] * 6
    assert all(e["model"] == "fake:1b" and e["variant"] == "masked" for e in evaluated)
