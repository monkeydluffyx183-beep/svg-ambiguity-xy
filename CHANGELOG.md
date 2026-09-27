# Changelog

Protocol-bearing versions are listed with each release so a result can always be tied to
the exact instrument that produced it (`python -m xybench status` prints the live values).

## 0.1.0 — 2026-09-27

### fmtcontrol_xy
- Independent, specification-only implementation of the Format-Matched Control
  Specification v1.0. Level 2: 10/10 conformance vectors bit-exact, 2/2 `must_raise` cases
  raise. MT19937 and CPython's seeding / `getrandbits` / `_randbelow` / `shuffle`
  conventions reimplemented; the `random` module is not imported by the package.
- `SPEC_NOTES.md`: conformance report and thirteen places the specification
  under-determines the result (N1–N13), with probe measurements.

### xybench
- Corpus generator on XY 0.0.7 exports; two variants (`masked`, `real`); 8 spatial
  predicates with a 24 px uniqueness margin; operations recolor / stroke / delete / resize.
- Frozen corpus `9344ea07056f508eb719705ac7c12e1fc5e6a20eaf3966d5c2c6c8709974cc80`
  (seed 20260926, 30 charts, 180 cases per variant), generator 1.0.
- Prompt template `edit_xy_v1` 1.0 (one slot; per-variant preamble sentence).
- Scoring 1.0; abstention rule 2.0 (adds `REFUSED_PROSE`, widens clarifying-question
  forms). Primary metric: exclusive identification; inclusive reported alongside.
- Inference: cluster bootstrap, paired cluster permutation, MDE = 2.80 × SE_paired with
  unpaired fallback.
- Runner: Ollama and OpenAI-compatible backends; append-only, manifest-pinned, resumable.
- Pre-registration draft written before any model output exists; freeze tag not yet
  applied.
