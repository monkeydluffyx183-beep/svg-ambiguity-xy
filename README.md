# svg-ambiguity-xy

**An independent, specification-only implementation of the format-matched control** —
the method behind [svg-ambiguity-bench](https://github.com/NITISH-R-G/svg-ambiguity-bench),
written from its [`SPEC.md`](https://github.com/NITISH-R-G/svg-ambiguity-bench/blob/master/src/fmtcontrol/SPEC.md)
and conformance vectors without reading the reference code.

[![CI](https://github.com/monkeydluffyx183-beep/svg-ambiguity-xy/actions/workflows/ci.yml/badge.svg)](https://github.com/monkeydluffyx183-beep/svg-ambiguity-xy/actions/workflows/ci.yml)

Upstream's `CONTRIBUTING.md` lists an independent implementation as the contribution it
values most and cannot produce itself, because *"it tests whether the specification is
actually sufficient — a claim the author cannot check, having written both."* This
repository is that test, for Python, with the answer and the caveats written down.

## Result

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

## What this repository is not

It ran **no models** and makes **no empirical claims**. The study results, pre-registration,
DOI and provenance in upstream's README belong to upstream; nothing here reproduces or
disputes them. This is an implementation of the instrument, not a replication of the
measurement.

## Try it — no install

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

## Use it

```bash
pip install -e ".[dev]" && python -m pytest    # 698 tests, ~3 s
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

## Layout

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
```

## Reporting upstream

The first half of [`SPEC_NOTES.md`](SPEC_NOTES.md) follows upstream's
`independent-implementation` issue template and can be pasted into
[a new issue there](https://github.com/NITISH-R-G/svg-ambiguity-bench/issues/new?template=independent-implementation.md)
as-is. Its last section is a note on the §6b sorted-table corollary, offered for the
proofs review upstream also solicits.

## Attribution and licence

The specification, the conformance vectors and the method are the work of Nitish R G
(svg-ambiguity-bench, MIT). `conformance_vectors.json` is included **unmodified**
(SHA-256 `cea747eeee90456b5326c1022696fefcd7709d0fb15a746b265d9e3299807be9`, upstream
commit `305ae55`); the pinned hash is asserted by the tests so it cannot drift silently.
See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Everything else in this repository is original and MIT licensed — see [`LICENSE`](LICENSE).
