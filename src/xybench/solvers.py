"""Solvers: deterministic reference solvers for validating the instrument, and two model
backends (Ollama, OpenAI-compatible) for running it.

Deterministic solvers are functions of the case and the document, not of the prompt; they
exist to prove the scorer end-to-end before any model is involved:

    oracle      edits the ground-truth target correctly           -> CORRECT_STRICT, identified
    random      edits a uniformly chosen marker (seeded per case) -> identification ≈ mean(1/K)
    first       always edits the first marker in document order   -> ≈ mean(1/K) iff order leaks nothing
    echo        returns the document unchanged                    -> NO_EDIT
    abstain     declines explicitly, no document                  -> ABSTAINED
    prose       answers in prose without a document               -> REFUSED_PROSE
    truncated   returns the first half of the document            -> MALFORMED

Model backends use only ``urllib``. Decoding is temperature 0 with a fixed seed where the
API accepts one; replicates are not used (identical calls at temperature 0 would imply a
robustness that does not exist — upstream ADR-0010).
"""

from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from .corpus import Case, Chart
from .svgdoc import find_markers

DETERMINISTIC_SOLVERS = ("oracle", "random", "first", "echo", "abstain", "prose", "truncated")
BACKENDS = ("ollama", "openai")


@dataclass
class Completion:
    text: str
    finish_reason: Optional[str] = None
    latency_ms: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)


# -- editing a document the way a correct model would --------------------------------------------


def apply_edit(svg_text: str, marker_id: str, operation: str, params: Dict[str, Any]) -> str:
    """Perform ``operation`` on the marker with ``marker_id`` by text substitution."""
    for m in find_markers(svg_text):
        if m.id != marker_id:
            continue
        start, end = m.span
        original = svg_text[start:end]
        if operation == "delete":
            edited = ""
        elif operation == "recolor_fill":
            edited = re.sub(r'fill="[^"]*"', f'fill="{params["fill"]}"', original, count=1)
        elif operation == "add_stroke":
            edited = original[:-2] + f' stroke="{params["stroke"]}" stroke-width="{params["stroke_width"]}"/>'
        elif operation == "resize":
            r = float(m.attrs["r"]) * float(params["factor"])
            edited = original.replace(f'r="{m.attrs["r"]}"', f'r="{r:g}"', 1)
        else:
            raise ValueError(operation)
        return svg_text[:start] + edited + svg_text[end:]
    raise KeyError(marker_id)


def deterministic_response(solver: str, case: Case, chart: Chart, variant: str, seed: int = 0) -> str:
    svg = chart.svg(variant)
    if solver == "oracle":
        return apply_edit(svg, case.target_id, case.operation, case.params)
    if solver == "random":
        rng = random.Random(f"{seed}:{case.case_id}")
        return apply_edit(svg, rng.choice(chart.ids), case.operation, case.params)
    if solver == "first":
        return apply_edit(svg, chart.ids[0], case.operation, case.params)
    if solver == "echo":
        return svg
    if solver == "abstain":
        return (
            "I cannot determine which marker the instruction refers to. The document does not "
            "contain enough information to identify it, so rather than guessing I am leaving it unchanged."
        )
    if solver == "prose":
        return (
            "Sure. To do that, open the SVG in an editor, locate the marker you mean in the plot "
            "area, and update its attributes accordingly. Let me know if you want me to walk "
            "through the exact steps for your editor."
        )
    if solver == "truncated":
        return svg[: len(svg) // 2]
    raise ValueError(f"unknown deterministic solver {solver!r}")


# -- model backends ----------------------------------------------------------------------------


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float, retries: int = 3) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    last: Optional[Exception] = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (408, 409, 425, 429, 500, 502, 503, 504):
                detail = exc.read().decode("utf-8", "replace")[:500]
                raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        time.sleep(2 ** attempt)
    raise RuntimeError(f"request to {url} failed after {retries} attempts: {last}")


class OllamaBackend:
    """``POST {host}/api/chat`` with streaming off. Records ``done_reason`` as the finish reason."""

    name = "ollama"

    def __init__(self, model: str, host: str = "http://127.0.0.1:11434", max_tokens: int = 8192,
                 num_ctx: int = 16384, seed: int = 0, timeout: float = 600.0) -> None:
        self.model, self.host, self.max_tokens, self.num_ctx, self.seed, self.timeout = (
            model, host.rstrip("/"), max_tokens, num_ctx, seed, timeout
        )

    def describe(self) -> Dict[str, Any]:
        return {"backend": self.name, "model": self.model, "host": self.host, "max_tokens": self.max_tokens,
                "num_ctx": self.num_ctx, "seed": self.seed, "temperature": 0}

    def complete(self, prompt: str) -> Completion:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0, "seed": self.seed, "num_predict": self.max_tokens, "num_ctx": self.num_ctx},
        }
        t0 = time.monotonic()
        data = _post_json(f"{self.host}/api/chat", payload, {}, self.timeout)
        latency = int((time.monotonic() - t0) * 1000)
        text = str(data.get("message", {}).get("content", ""))
        return Completion(
            text=text, finish_reason=data.get("done_reason"), latency_ms=latency,
            meta={k: data.get(k) for k in ("prompt_eval_count", "eval_count", "total_duration", "model")},
        )


class OpenAIBackend:
    """``POST {base_url}/chat/completions``. API key from ``--api-key``, else ``XYBENCH_API_KEY``,
    else ``OPENAI_API_KEY``; local servers usually accept anything."""

    name = "openai"

    def __init__(self, model: str, base_url: str = "http://127.0.0.1:8000/v1", api_key: Optional[str] = None,
                 max_tokens: int = 8192, seed: int = 0, timeout: float = 600.0) -> None:
        self.model, self.base_url, self.max_tokens, self.seed, self.timeout = (
            model, base_url.rstrip("/"), max_tokens, seed, timeout
        )
        self.api_key = api_key or os.environ.get("XYBENCH_API_KEY") or os.environ.get("OPENAI_API_KEY") or "none"

    def describe(self) -> Dict[str, Any]:
        return {"backend": self.name, "model": self.model, "base_url": self.base_url,
                "max_tokens": self.max_tokens, "seed": self.seed, "temperature": 0}

    def complete(self, prompt: str) -> Completion:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "seed": self.seed,
        }
        t0 = time.monotonic()
        data = _post_json(f"{self.base_url}/chat/completions", payload, {"Authorization": f"Bearer {self.api_key}"}, self.timeout)
        latency = int((time.monotonic() - t0) * 1000)
        choice = (data.get("choices") or [{}])[0]
        text = str((choice.get("message") or {}).get("content") or "")
        return Completion(
            text=text, finish_reason=choice.get("finish_reason"), latency_ms=latency,
            meta={"usage": data.get("usage"), "model": data.get("model")},
        )


Backend = Callable[[str], Completion]


def make_backend(kind: str, model: str, **kwargs: Any):
    if kind == "ollama":
        return OllamaBackend(model, **{k: v for k, v in kwargs.items() if v is not None and k in ("host", "max_tokens", "num_ctx", "seed", "timeout")})
    if kind == "openai":
        return OpenAIBackend(model, **{k: v for k, v in kwargs.items() if v is not None and k in ("base_url", "api_key", "max_tokens", "seed", "timeout")})
    raise ValueError(f"unknown backend {kind!r}")
