# xybench — runbook

How to run the instrument on your machine. Nothing here needs a GPU; upstream's models
(qwen2.5-coder 1.5b–7b, llama3.2 3b) run on a laptop under Ollama. Every command works
from the repository root.

## 0. Install

```bash
python -m pip install -e ".[dev]"          # evaluate / report / audit: Python 3.9+
python -m pip install -e ".[dev,bench]"    # + corpus generation (XY 0.0.7): Python 3.11+
python -m xybench status                   # protocol identity: versions and hashes
python -m xybench audit                    # 23 checks, ~3 s, no model
```

## 1. Look at what a model will see

```bash
python -m xybench prompt --variant masked --condition baseline  --case xy000-04
python -m xybench prompt --variant masked --condition permuted  --case xy000-04
python -m xybench prompt --variant real   --condition named_id  --case xy000-04
```

Prompts are 3.7–6.7 k characters (≈ 1.3–2.3 k tokens). The defaults below leave room:
`num_ctx 16384`, `max_tokens 8192` (the model returns the whole document, ~1.5 k tokens).

## 2. Run the arms

One directory per `(variant, condition, model)` under `experiments/`. Runs are resumable —
interrupt and re-run the same command, finished cases are skipped — and a directory refuses
to accept a different configuration than the one it was created with.

**Ollama** (matches upstream):

```bash
ollama pull qwen2.5-coder:3b
for v in masked real; do
  for c in baseline permuted enhanced named_id; do
    python -m xybench run --variant $v --condition $c --solver ollama --model qwen2.5-coder:3b
  done
done
```

Options: `--host http://127.0.0.1:11434`, `--max-tokens 8192`, `--num-ctx 16384`, `--seed 0`,
`--timeout 600`. Ollama's `done_reason` is stored as the finish reason.

**OpenAI-compatible** (vLLM, LM Studio, llama.cpp server, OpenRouter, hosted APIs):

```bash
export XYBENCH_API_KEY=...        # or OPENAI_API_KEY; local servers accept anything
python -m xybench run --variant masked --condition enhanced --solver openai \
    --model Qwen/Qwen2.5-Coder-7B-Instruct --base-url http://127.0.0.1:8000/v1
```

**Smoke test first.** `--limit 5` runs five cases; then `evaluate` them and read the raw
`responses.jsonl` before committing to 1440 calls. Upstream found their template bug
exactly this way.

A full sweep is 2 variants × 4 conditions × 180 = **1440 calls per model**. At 5–20 s per
call on a 3B model that is 2–8 hours; the order above puts `masked` first because Q1 lives
there.

## 3. Score and report

```bash
python -m xybench evaluate experiments/*
python -m xybench report   experiments/* --out results/<model>.md
```

`evaluate` writes `evaluations.jsonl` next to each `responses.jsonl` (one row per case with
the outcome class, both identification flags, the changed ids, the selected document
index, truncation). `report` produces the arm table, the pairwise comparisons with p and
MDE, the cross-variant table, per-predicate identification and the selection-position
distribution. Pass any subset of experiment directories; comparisons appear when both
arms are present.

## 4. Before reading the numbers

Apply `docs/xybench/PREREGISTRATION.md` in order: the instrument falsifier
(`masked/baseline` above 0.30 means the masking leaks), then the `MALFORMED` exclusion
(20 %), then the refusal and policy rules. Only then the primary comparison,
`enhanced − permuted` in `masked`. If the difference is zero, report the MDE.

## 5. Recording a run

Commit `experiments/<name>/{manifest.json,responses.jsonl,evaluations.jsonl}` and the
report. Raw responses are the artefact that lets someone else re-score with their own
scorer; upstream committed 540 of them for that reason. Response files for a full sweep are
a few MB per model.

## 6. Troubleshooting

| symptom | likely cause | what to do |
|---|---|---|
| every response `MALFORMED`, reason "truncated" | `max_tokens` too small for a whole document | raise `--max-tokens`; check `finish_reason` in `responses.jsonl` |
| `MALFORMED`, reason "alignment: N markers missing" | model dropped or renamed ids | read the response; if it is systematic, it is a finding (record it), not a scorer bug |
| high `REFUSED_PROSE` | model answers in prose | expected for some models; rule 3 in the pre-registration governs reporting |
| `xybench verify --regenerate` differs | different XY version | `python -m xybench status` shows installed vs. required; the hash, not the seed, identifies the corpus |
| `HTTP 404` from the OpenAI backend | `--base-url` should end in `/v1` | check the server's path |
