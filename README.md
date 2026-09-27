# svg-ambiguity-xy

Two things, built on each other:

1. **`fmtcontrol_xy`** — an independent, specification-only implementation of the
   format-matched control, the method behind
   [svg-ambiguity-bench](https://github.com/NITISH-R-G/svg-ambiguity-bench), written from its
   [`SPEC.md`](https://github.com/NITISH-R-G/svg-ambiguity-bench/blob/master/src/fmtcontrol/SPEC.md)
   and conformance vectors without reading the reference code. Level 2 conformant.
2. **`xybench`** — that benchmark's SVG reference-resolution study rebuilt on **real chart
   SVGs exported by the [XY](https://github.com/reflex-dev/xy) charting library**, in two
   renderings of the same 30 charts: coordinates masked (upstream's information gap on
   real markup) and coordinates legible. Frozen corpus, pre-registration draft, model
   runner for Ollama and OpenAI-compatible endpoints. **No model has been run yet.**

[![CI](https://github.com/monkeydluffyx183-beep/svg-ambiguity-xy/actions/workflows/ci.yml/badge.svg)](https://github.com/monkeydluffyx183-beep/svg-ambiguity-xy/actions/workflows/ci.yml)

Upstream's `CONTRIBUTING.md` lists an independent implementation as the contribution it
values most and cannot produce itself, because *"it tests whether the specification is
actually sufficient — a claim the author cannot check, having written both."* This
repository is that test, for Python, with the answer and the caveats written down.

## Part 1 — `fmtcontrol_xy`

### Result

| | |
|---|---|
| Spec version | 1.0 |
| Conformance | **Level 2 — 10/10 vectors bit-exact, 2/2 `must_raise` cases raise** |
| Reference Python read | **None** of `control.py`, `admits.py`, `__init__.py` or their tests — see the reading list in [`SPEC_NOTES.md`](SPEC_NOTES.md) |
| PRNG | MT19937 and CPython's seeding / `getrandbits` / `_randbelow` / `shuffle` conventions **reimplemented from the algorithm and §8's prose**; the `random` module is used only as a test oracle |
| Dependencies | none — standard library, enforced by a test |
| Where the spec was insufficient | 13 items, two of which would make a non-Python implementation fail Level 2 — [`SPEC_NOTES.md`](SPEC_NOTES.md) |

The short version of the findings: the specification is **sufficient for Level 1 and
nearly sufficient for Level 2**. The gap is that §8 pins the generator to CPython *by
reference* rather than by description — how a 64-bit integer becomes MT19937 state, and
which bits `getrandbits` keeps, are not stated, and most natural alternatives reproduce
0–4 of the 10 vectors. One convention (the number of 32-bit seed limbs) is not pinned by
the vectors at all. None of this is a defect in the method; all of it is fixable with a
few sentences.

### What part 1 is not

It ran **no models** and makes **no empirical claims**. The study results, pre-registration,
DOI and provenance in upstream's README belong to upstream; nothing here reproduces or
disputes them. This is an implementation of the instrument, not a replication of the
measurement.

### Try it — no install

```bash
git clone https://github.com/monkeydluffyx183-beep/svg-ambiguity-xy
cd svg-ambiguity-xy

PYTHONPATH=src python -m fmtcontrol_xy.conformance   # the 12 published cases, ~1 s
python examples/ops_table_control.py                 # the three arms in a non-SVG domain
```

The example builds baseline / enhanced / permuted arms for an operations table, runs the
validation checks, and shows the three-way decomposition under three deterministic
solvers — including a **pure format effect** that a two-arm comparison would report as
information, and the **sorted-entity-order trap** from SPEC §6b that no check can catch.

### Use it

```bash
pip install -e ".[dev]" && python -m pytest    # 775 tests, ~8 s (698 for part 1)
```

```python
from fmtcontrol_xy import permute, check_control

facts    = {"doc_1": ("Paris", 2.1), "doc_2": ("Berlin", 3.4), "doc_3": ("Rome", 0.7)}
permuted = permute(facts, key="query_42", seed=991)   # same entities, same order, values moved

enhanced_text = render(facts)        # ONE renderer for both arms (SPEC §6) —
permuted_text = render(permuted)     # otherwise the format is not held fixed

report = check_control(facts, permuted, enhanced_text, permuted_text)
assert report.ok, report.failures    # I1–I4, token delta, line count, texts differ
```

`permute` refuses rather than degrades: fewer than two entities, or all values equal,
raises `NoControlError` instead of handing back a copy of the treatment (SPEC I9).

Or just copy `src/fmtcontrol_xy/{mt19937,control}.py` — two files, standard library only.

### Layout

```
src/fmtcontrol_xy/
  control.py                 permute (SPEC §4) · check_control (§7) · NoControlError (I9)
  mt19937.py                 the generator, seeded and consumed the way CPython does it
  conformance.py             python -m fmtcontrol_xy.conformance
  conformance_vectors.json   byte-for-byte copy of upstream's (see THIRD_PARTY_NOTICES.md)
tests/
  test_conformance.py        Level 2, plus a pinned SHA-256 of the vectors file
  test_invariants.py         Level 1 over 600 generated cases; cross-process determinism
  test_mt19937.py            generator vs CPython, stage by stage
  test_check_control.py      each check catches the failure it exists for
  test_stdlib_only.py        no third-party imports, and no `random`
examples/ops_table_control.py
SPEC_NOTES.md                the conformance report and every place the spec forced a guess

src/xybench/                 part 2 — corpus · predicates · instructions · prompt · scoring · solvers · stats · report · audit · cli
data/frozen/<hash>/          the frozen corpus: 60 SVGs, cases, geometry, rejections, certificate
docs/xybench/                DESIGN · PREREGISTRATION · RUNBOOK
results/                     audit output and reference-solver report at freeze
tests/bench/                 77 tests for part 2 (two need XY; they skip without it)
```

### Reporting upstream

The first half of [`SPEC_NOTES.md`](SPEC_NOTES.md) follows upstream's
`independent-implementation` issue template and can be pasted into
[a new issue there](https://github.com/NITISH-R-G/svg-ambiguity-bench/issues/new?template=independent-implementation.md)
as-is. Its last section is a note on the §6b sorted-table corollary, offered for the
proofs review upstream also solicits.

## Part 2 — `xybench`: the study on real XY charts

Upstream's limitations open with *"One synthetic corpus. Opaque geometry tokens that do not
occur in real SVGs."* `xybench` addresses that sentence: the same three-arm design, on SVGs
that a charting library actually emits.

```
<circle id="e2ee9009d" cx="80.23" cy="51.26" r="3.5" fill="#8c5a3c" fill-opacity="0.8"/>   real
<circle id="e2ee9009d" cx="{{GEOM_23810120}}" cy="{{GEOM_32405f3c}}" r="3.5" fill="#8c5a3c" fill-opacity="0.8"/>   masked
```

Real markup changes the question. In XY's output the position *is* in the text, so
"make the top-left marker blue" is no longer a reference the document cannot support — it
is two numbers per element. Rather than pick, the corpus is written twice: `masked`
recreates upstream's information gap byte-for-byte on real markup; `real` leaves the
coordinates in. Everything else — ids, order, instructions, context tables, the permutation
— is identical, so `real − masked` per condition measures what legible coordinates are
worth.

| | |
|---|---|
| Corpus | 30 single-series XY scatter charts, K ∈ {4..7} identical markers, **180 cases × 2 variants**, ground truth from rendered pixels with a 24 px margin, frozen at `data/frozen/9344ea07…` with a per-file certificate; regenerates bit-exactly from its seed under `xy==0.0.7` (CI checks) |
| Conditions | `baseline` · `enhanced` (id, centre_x, centre_y in document order) · `permuted` (via `fmtcontrol_xy`, same shuffle in both variants) · `named_id` |
| Predicates / operations | 8 spatial predicates; recolor, stroke, delete, resize |
| Scoring | upstream's outcome classes plus **`REFUSED_PROSE`** — the FA-013 fix: a prose refusal is no longer `MALFORMED`. Primary metric: *exclusive* identification (target changed, nothing else); upstream's inclusive definition reported alongside |
| Inference | cluster bootstrap over charts, paired cluster permutation, MDE fixed in advance |
| Validated | 23 audit checks with no model, including seven deterministic solvers through the whole scorer (`oracle` 1.000, `random` ≈ 0.19, `first` shows up as a spike in the selection-position table) |

```bash
python -m xybench status                        # protocol identity
python -m xybench audit                         # 23 checks, ~3 s, no model, no XY needed
python -m xybench prompt --variant masked --condition permuted --case xy000-04

python -m xybench run --variant masked --condition enhanced --solver ollama --model qwen2.5-coder:3b
python -m xybench evaluate experiments/* && python -m xybench report experiments/*
```

Read, in this order: [`docs/xybench/DESIGN.md`](docs/xybench/DESIGN.md) (what and why,
what differs from upstream, threats), [`docs/xybench/PREREGISTRATION.md`](docs/xybench/PREREGISTRATION.md)
(hypotheses, primary comparison, falsifiers — written before any model output exists, and
how to tag the freeze), [`docs/xybench/RUNBOOK.md`](docs/xybench/RUNBOOK.md) (running it).
`results/audit.txt` and `results/reference-solvers.md` are the instrument's state at freeze.

The corpus depends on XY's exact SVG serialisation, so `xy==0.0.7` is pinned in the `bench`
extra (Python ≥ 3.11); scoring and reporting need only the standard library on 3.9+.

## Attribution and licence

The specification, the conformance vectors and the method are the work of Nitish R G
(svg-ambiguity-bench, MIT). `conformance_vectors.json` is included **unmodified**
(SHA-256 `cea747eeee90456b5326c1022696fefcd7709d0fb15a746b265d9e3299807be9`, upstream
commit `305ae55`); the pinned hash is asserted by the tests so it cannot drift silently.
See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

XY (`xy` on PyPI) is by the Reflex team, Apache-2.0; it is a build-time dependency of the
corpus and is not redistributed. The frozen SVGs under `data/frozen/` are XY exports with
ids inserted.

Everything else in this repository is original and MIT licensed — see [`LICENSE`](LICENSE).
