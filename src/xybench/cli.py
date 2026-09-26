"""``python -m xybench <command>``.

    build      generate a corpus from a seed (needs the XY library)
    verify     integrity certificate; with --regenerate, tier-3 determinism (needs XY)
    audit      instrument audits, no model
    prompt     print one prompt
    run        run one arm with a deterministic solver or a model backend
    evaluate   score a stored experiment
    report     markdown report over evaluated experiments
    status     protocol identity: versions and hashes
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from fmtcontrol_xy import SPEC_VERSION as FMTCONTROL_SPEC_VERSION

from . import __version__
from .audit import audit_corpus, format_checks
from .corpus import GENERATOR_VERSION, PERMUTATION_SEED, XY_VERSION_REQUIRED, CorpusConfig, build, load_corpus, verify_files, verify_regeneration, xy_version
from .evaluate import evaluate_experiment
from .prompt import CONDITIONS, TEMPLATE_ID, TEMPLATE_VERSION, prompt_for, template_hash
from .report import build_report
from .scoring import ABSTENTION_RULE_VERSION, SCORING_VERSION
from .solvers import BACKENDS, DETERMINISTIC_SOLVERS, deterministic_response, make_backend
from .store import ResponseStore

DEFAULT_FROZEN = Path("data/frozen")


def _find_corpus(arg: Optional[str]) -> Path:
    if arg:
        return Path(arg)
    candidates = sorted(p for p in DEFAULT_FROZEN.glob("*") if p.is_dir() and (p / "manifest.json").exists())
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        sys.exit("no corpus found under data/frozen; pass --corpus")
    sys.exit(f"several corpora under data/frozen; pass --corpus: {[c.name for c in candidates]}")


def cmd_build(args: argparse.Namespace) -> int:
    installed = xy_version()
    if installed != XY_VERSION_REQUIRED:
        print(f"warning: xy {installed!r} installed, corpus protocol pins {XY_VERSION_REQUIRED}", file=sys.stderr)
    cfg = CorpusConfig(seed=args.seed, n_charts=args.charts, cases_per_chart=args.cases_per_chart)
    t0 = time.monotonic()
    out = build(cfg, Path(args.out))
    print(f"corpus {out.name}\n  at {out}\n  {time.monotonic() - t0:.1f}s")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    root = _find_corpus(args.corpus)
    problems = verify_files(root)
    print(f"integrity certificate: {'OK' if not problems else 'FAIL'}")
    for p in problems:
        print(f"  - {p}")
    rc = 1 if problems else 0
    if args.regenerate:
        with tempfile.TemporaryDirectory() as tmp:
            same, expected, got = verify_regeneration(root, Path(tmp))
        print(f"regeneration: {'identical' if same else 'DIFFERENT'} (expected {expected[:12]}, got {got[:12]}; xy {xy_version()})")
        rc |= 0 if same else 1
    return rc


def cmd_audit(args: argparse.Namespace) -> int:
    corpus = load_corpus(_find_corpus(args.corpus))
    checks = audit_corpus(corpus)
    print(format_checks(checks))
    return 0 if all(c.ok for c in checks) else 1


def cmd_prompt(args: argparse.Namespace) -> int:
    corpus = load_corpus(_find_corpus(args.corpus))
    case = next((c for c in corpus.cases if c.case_id == args.case), None) if args.case else corpus.cases[0]
    if case is None:
        sys.exit(f"no case {args.case}")
    print(prompt_for(args.variant, args.condition, corpus.charts[case.chart_id], case))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    corpus = load_corpus(_find_corpus(args.corpus))
    is_model = args.solver in BACKENDS
    if is_model and not args.model:
        sys.exit("--model is required for a model backend")
    backend = make_backend(args.solver, args.model, host=args.host, base_url=args.base_url, api_key=args.api_key,
                           max_tokens=args.max_tokens, num_ctx=args.num_ctx, seed=args.seed, timeout=args.timeout) if is_model else None

    name = args.name or (f"{args.variant}-{args.condition}-{args.model or args.solver}".replace(":", "_").replace("/", "_"))
    store = ResponseStore(Path(args.experiments) / name)
    store.open(
        {
            "dataset_hash": corpus.dataset_hash, "variant": args.variant, "condition": args.condition,
            "solver": args.solver, "model": args.model, "backend": backend.describe() if backend else None,
            "template_id": TEMPLATE_ID, "template_version": TEMPLATE_VERSION, "template_hash": template_hash(args.variant),
            "scoring_version": SCORING_VERSION, "abstention_rule_version": ABSTENTION_RULE_VERSION,
            "permutation_seed": PERMUTATION_SEED, "xybench_version": __version__,
        }
    )
    done = store.done_case_ids()
    todo = [c for c in corpus.cases if c.case_id not in done]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{name}: {len(done)} done, {len(todo)} to run")
    t0 = time.monotonic()
    for i, case in enumerate(todo, 1):
        chart = corpus.charts[case.chart_id]
        prompt = prompt_for(args.variant, args.condition, chart, case)
        if backend is None:
            text, finish, latency, meta = deterministic_response(args.solver, case, chart, args.variant, args.seed), "stop", 0, {}
        else:
            completion = backend.complete(prompt)
            text, finish, latency, meta = completion.text, completion.finish_reason, completion.latency_ms, completion.meta
        store.append(
            {
                "case_id": case.case_id, "chart_id": case.chart_id, "variant": args.variant, "condition": args.condition,
                "prompt_sha256": __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest(),
                "prompt_chars": len(prompt), "response": text, "finish_reason": finish, "latency_ms": latency, "meta": meta,
            }
        )
        if backend is not None or i % 60 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} {case.case_id} finish={finish} {latency} ms  ({time.monotonic() - t0:.0f}s)")
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    corpus = load_corpus(_find_corpus(args.corpus))
    for exp in args.experiment:
        rows = evaluate_experiment(corpus, Path(exp))
        from collections import Counter

        print(f"{Path(exp).name}: {len(rows)} rows, {dict(Counter(r['outcome'] for r in rows))}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    corpus = load_corpus(_find_corpus(args.corpus))
    experiments = []
    for exp in args.experiment:
        path = Path(exp) / "evaluations.jsonl"
        if not path.exists():
            rows = evaluate_experiment(corpus, Path(exp))
        else:
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        experiments.append((Path(exp).name, rows))
    text = build_report(corpus, experiments, seed=args.seed)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = _find_corpus(args.corpus) if (args.corpus or DEFAULT_FROZEN.exists()) else None
    info = {
        "xybench_version": __version__,
        "generator_version": GENERATOR_VERSION,
        "template": {"id": TEMPLATE_ID, "version": TEMPLATE_VERSION,
                     "hash_masked": template_hash("masked")[:16], "hash_real": template_hash("real")[:16]},
        "scoring_version": SCORING_VERSION,
        "abstention_rule_version": ABSTENTION_RULE_VERSION,
        "fmtcontrol_spec_version": FMTCONTROL_SPEC_VERSION,
        "permutation_seed": PERMUTATION_SEED,
        "xy_required": XY_VERSION_REQUIRED,
        "xy_installed": xy_version(),
    }
    if root is not None:
        m = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        info["corpus"] = {"dataset_hash": m["dataset_hash"], "config_hash": m["config_hash"], "seed": m["config"]["seed"],
                          "n_charts": m["n_charts"], "n_cases": m["n_cases"], "xy_version_at_build": m["xy_version"]}
    print(json.dumps(info, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="xybench", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build");        b.add_argument("--seed", type=int, default=CorpusConfig.seed)
    b.add_argument("--charts", type=int, default=CorpusConfig.n_charts); b.add_argument("--cases-per-chart", type=int, default=CorpusConfig.cases_per_chart)
    b.add_argument("--out", default=str(DEFAULT_FROZEN)); b.set_defaults(fn=cmd_build)

    v = sub.add_parser("verify");       v.add_argument("--corpus"); v.add_argument("--regenerate", action="store_true"); v.set_defaults(fn=cmd_verify)
    a = sub.add_parser("audit");        a.add_argument("--corpus"); a.set_defaults(fn=cmd_audit)

    pr = sub.add_parser("prompt");      pr.add_argument("--corpus"); pr.add_argument("--variant", choices=("masked", "real"), default="masked")
    pr.add_argument("--condition", choices=CONDITIONS, default="enhanced"); pr.add_argument("--case"); pr.set_defaults(fn=cmd_prompt)

    r = sub.add_parser("run");          r.add_argument("--corpus"); r.add_argument("--variant", choices=("masked", "real"), required=True)
    r.add_argument("--condition", choices=CONDITIONS, required=True)
    r.add_argument("--solver", choices=DETERMINISTIC_SOLVERS + BACKENDS, required=True)
    r.add_argument("--model"); r.add_argument("--name"); r.add_argument("--experiments", default="experiments")
    r.add_argument("--host", default=None, help="ollama host (default http://127.0.0.1:11434)")
    r.add_argument("--base-url", default=None, help="OpenAI-compatible base url (default http://127.0.0.1:8000/v1)")
    r.add_argument("--api-key", default=None); r.add_argument("--max-tokens", type=int, default=None)
    r.add_argument("--num-ctx", type=int, default=None); r.add_argument("--seed", type=int, default=0)
    r.add_argument("--timeout", type=float, default=None); r.add_argument("--limit", type=int, default=0)
    r.set_defaults(fn=cmd_run)

    e = sub.add_parser("evaluate");     e.add_argument("--corpus"); e.add_argument("experiment", nargs="+"); e.set_defaults(fn=cmd_evaluate)
    rp = sub.add_parser("report");      rp.add_argument("--corpus"); rp.add_argument("experiment", nargs="+")
    rp.add_argument("--out"); rp.add_argument("--seed", type=int, default=0); rp.set_defaults(fn=cmd_report)
    s = sub.add_parser("status");       s.add_argument("--corpus"); s.set_defaults(fn=cmd_status)

    args = p.parse_args(argv)
    return int(args.fn(args))
