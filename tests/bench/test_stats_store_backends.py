"""Inference helpers, the append-only store, and both model backends against a fake
HTTP server — the response shapes of Ollama and OpenAI-compatible APIs, finish reasons,
retries on 5xx, and the API-key header."""

import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from xybench.solvers import OllamaBackend, OpenAIBackend, make_backend
from xybench.stats import cluster_bootstrap, paired_cluster_test, random_selection_reference
from xybench.store import ResponseStore

# -- stats --


def _clustered(values):
    return {f"c{i}": list(v) for i, v in enumerate(values)}


def test_bootstrap_interval_brackets_the_mean():
    data = _clustered([[1, 0, 0, 1, 0, 0]] * 15 + [[0, 0, 0, 0, 0, 1]] * 15)
    iv = cluster_bootstrap(data, n_boot=500, seed=1)
    assert math.isclose(iv.estimate, (15 * 2 + 15 * 1) / 180)
    assert iv.lower <= iv.estimate <= iv.upper and iv.se > 0
    assert iv.n_cases == 180 and iv.n_clusters == 30


def test_identical_arms_give_p_one_and_fallback_mde():
    a = _clustered([[1, 0, 0, 0], [0, 0, 0, 0], [1, 1, 0, 0], [0, 0, 1, 0]] * 5)
    res = paired_cluster_test(a, a, n_perm=200, n_boot=200, seed=0)
    assert res.difference == 0.0 and res.p_value == 1.0
    assert res.mde_fallback and res.mde > 0


def test_clear_effect_is_detected():
    a = _clustered([[1, 1, 1, 0], [1, 1, 0, 0], [1, 1, 1, 1], [1, 0, 1, 1]] * 5)
    b = _clustered([[0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1], [1, 0, 0, 0]] * 5)
    res = paired_cluster_test(a, b, n_perm=2000, n_boot=200, seed=0)
    assert math.isclose(res.difference, 0.5)
    assert res.p_value < 0.01 and not res.mde_fallback
    assert res.mde == pytest.approx(2.8016 * res.se_paired, rel=1e-3)


def test_paired_test_rejects_unequal_clusters():
    with pytest.raises(ValueError):
        paired_cluster_test(_clustered([[1, 0]]), _clustered([[1, 0, 0]]))


def test_reference_is_mean_of_one_over_k():
    assert random_selection_reference([4, 5]) == pytest.approx((0.25 + 0.2) / 2)


# -- store --


def test_store_resumes_and_refuses_mixing(tmp_path):
    s = ResponseStore(tmp_path / "exp")
    m = {"dataset_hash": "h", "variant": "masked", "condition": "enhanced", "solver": "oracle", "model": None,
         "template_version": "1.0", "scoring_version": "1.0"}
    s.open(m)
    s.append({"case_id": "a", "response": "x"})
    s.append({"case_id": "b", "response": "y"})
    assert s.done_case_ids() == {"a", "b"}
    s.open(m)  # same experiment: fine
    with pytest.raises(RuntimeError):
        ResponseStore(tmp_path / "exp").open({**m, "condition": "permuted"})


# -- backends --


class _Handler(BaseHTTPRequestHandler):
    calls = []
    fail_first = {"count": 0}

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        _Handler.calls.append((self.path, dict(self.headers), body))
        if self.path.endswith("/flaky") or (self.path == "/api/chat" and _Handler.fail_first["count"] > 0):
            _Handler.fail_first["count"] -= 1
            self.send_response(503)
            self.end_headers()
            return
        if self.path == "/api/chat":
            payload = {"message": {"role": "assistant", "content": "<svg/>"}, "done_reason": "length", "eval_count": 7}
        elif self.path == "/v1/chat/completions":
            payload = {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}], "usage": {"total_tokens": 3}}
        else:
            self.send_response(404)
            self.end_headers()
            return
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_ollama_backend_request_and_finish_reason(server, monkeypatch):
    monkeypatch.setattr("xybench.solvers.time.sleep", lambda s: None)
    _Handler.calls.clear()
    _Handler.fail_first["count"] = 1  # first attempt 503, then success
    b = OllamaBackend("qwen2.5-coder:3b", host=server, max_tokens=123, num_ctx=4096, seed=9)
    c = b.complete("PROMPT")
    assert c.text == "<svg/>" and c.finish_reason == "length" and c.meta["eval_count"] == 7
    path, headers, body = _Handler.calls[-1]
    assert path == "/api/chat" and body["stream"] is False
    assert body["options"] == {"temperature": 0, "seed": 9, "num_predict": 123, "num_ctx": 4096}
    assert body["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert len(_Handler.calls) == 2  # retried once


def test_openai_backend_request_and_key(server, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("XYBENCH_API_KEY", "sk-test")
    _Handler.calls.clear()
    b = make_backend("openai", "gpt-x", base_url=server + "/v1", max_tokens=50, seed=1)
    c = b.complete("PROMPT")
    assert c.text == "hello" and c.finish_reason == "stop" and c.meta["usage"]["total_tokens"] == 3
    path, headers, body = _Handler.calls[-1]
    assert path == "/v1/chat/completions" and headers["Authorization"] == "Bearer sk-test"
    assert body["temperature"] == 0 and body["max_tokens"] == 50 and body["seed"] == 1


def test_non_retryable_http_error_raises(server):
    b = OpenAIBackend("m", base_url=server + "/nope")
    with pytest.raises(RuntimeError, match="HTTP 404"):
        b.complete("x")
