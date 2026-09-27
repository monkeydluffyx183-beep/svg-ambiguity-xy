# Specification notes — a spec-only implementation report

This file records what it took to implement the **Format-Matched Control Specification
v1.0** from the specification and its conformance vectors alone, without reading the
reference implementation. The first half is the conformance report in the shape of
upstream's `independent-implementation` issue template. The second half — *where the
specification was unclear* — is the part upstream says it wants most, and it is written
so that every item is either a defect in the text, a place the vectors do not pin
behaviour, or a choice the text leaves to the implementer. Items are numbered **N1–N13**
and referenced from code comments.

Everything here is about the *specification*. No claim is made or implied about the
empirical results of the study the specification came from.

---

## Implementation

| | |
|---|---|
| **Language / runtime** | Python ≥ 3.9, standard library only (checked by `tests/test_stdlib_only.py`) |
| **Link** | https://github.com/monkeydluffyx183-beep/svg-ambiguity-xy |
| **Spec version implemented** | 1.0 (`spec_version` of the vectors file, SHA-256 `cea747ee…7be9`) |
| **Conformance level attempted** | Level 2 (bit-exact vectors) |
| **Conformance level achieved** | **Level 2: 10/10 vectors, 2/2 `must_raise`** |
| **PRNG** | MT19937 written from the published algorithm; CPython's seeding, `getrandbits`, `_randbelow` and `shuffle` reconstructed from SPEC §8's one-sentence description. `random` is **not** imported by the package; it is used in tests as an oracle |

## Did you read the Python?

**No — implemented from `SPEC.md` alone.** Precisely what was read before and during
implementation:

| read | not read |
|---|---|
| `src/fmtcontrol/SPEC.md` (all of it) | `src/fmtcontrol/control.py` |
| `src/fmtcontrol/conformance_vectors.json` | `src/fmtcontrol/admits.py` |
| `src/fmtcontrol/README.md` (user-facing: API names `permute` / `check_control`, the checks table) | `src/fmtcontrol/__init__.py` |
| Top-level `README.md`, `CONTRIBUTING.md`, the issue templates | `tests/**`, `scripts/generate_conformance_vectors.py`, `src/svgbench/**` |

The public `README.md` fixes the two function names and the signature of `check_control`;
those were adopted so the result is API-comparable. Nothing about *how* they work came from
anywhere but the spec.

A caveat on "clean room" that applies to any Python reimplementation: the author of this
code knows CPython's `random` module from ordinary use. The conventions reconstructed in
N1 and N2 were written from that background knowledge and then *verified* against the
vectors; a Rust or Go implementer without it would have had to guess, and the probe table
in N1 shows what guessing costs.

## Level 1 — invariants

| invariant | holds? | how it is checked |
|---|---|---|
| I1 entity preservation | yes | 600 generated cases + all vectors: `list(control) == list(treatment)` |
| I2 order preservation | yes | same assertion; plus a `Mapping` with a non-insertion iteration order is honoured |
| I3 multiset preservation | yes | multiset of `repr`s equal; values verified to be moved **by reference**, not copied |
| I4 displacement | yes | at least one position differs by value; n=2 always yields the swap; NaN handled (N7) |
| I5 determinism | yes | in-process repeat; **cross-process** with `PYTHONHASHSEED` ∈ {0, 1, 4242, random} |
| I6 key sensitivity | yes (statistical) | 500 keys on 8 entities → ≥ 490 distinct permutations (birthday bound ≈ 3 collisions); same for 500 seeds |
| I7 seed independence | caller obligation | not checkable inside the package; the example uses distinct data and permutation seeds and says why |
| I8 purity | yes | input serialised before/after, on acceptance and on refusal |
| I9 refusal over degradation | yes | `NoControlError` for < 2 entities, all-equal values, and the empty mapping |

## Level 2 — vectors

| vector id | matched? | notes |
|---|---|---|
| basic-3 | yes | |
| k4-tuples | yes | |
| k7-tuples | yes | |
| same-key-different-seed | yes | **the retry loop fires** — first shuffle is the identity, second is returned (N3) |
| same-seed-different-key | yes | |
| partial-ties | yes | |
| strings | yes | |
| unicode-key | yes | |
| negatives-and-floats | yes | |
| large-16 | yes | |
| single-entity (must raise) | yes | `NoControlError`, message contains the vector's `error` phrase (N4) |
| all-values-equal (must raise) | yes | `NoControlError`, message contains the vector's `error` phrase (N4) |

Reproduce: `PYTHONPATH=src python -m fmtcontrol_xy.conformance`.

---

## Where the specification was unclear

Ordered by consequence. **N1 and N2 are the ones that would make a non-Python
implementation fail Level 2**; N3–N4 are pinned by the vectors but not by the text;
N5–N11 are choices the text leaves open; N12–N13 are aids and remarks.

### N1 — How a 64-bit integer seeds MT19937 is not defined by MT19937 (§4, §8)

§4 says *"rng ← MT19937 seeded with big-endian uint64 of digest[0:8]"*. MT19937 has two
seeding procedures — `init_genrand(uint32)` and `init_by_array(uint32[])` — and neither
takes a 64-bit integer. §8 pins the answer by reference (*"as implemented by CPython's
`random.Random`"*) but does not state it. The rule is:

> Take `abs(n)`. Split it into 32-bit limbs, **least significant first**, using **as many
> limbs as the magnitude needs** (one limb, `[0]`, for zero). Call `init_by_array` on
> that array.

Every other natural reading fails the vectors. Measured with `MT19937` variants against
the 10 published vectors:

| reading of "seeded with the uint64" | vectors reproduced |
|---|---|
| `init_by_array(limbs of abs(n), LS-first, as many as needed)` — **CPython** | **10/10** |
| `init_by_array([lo32, hi32])` — always two limbs | **10/10** (see below) |
| `init_genrand(n & 0xFFFFFFFF)` — what `std::mt19937(seed)` does | 1/10 |
| `init_genrand(n >> 32)` | 3/10 |
| `init_by_array([hi32, lo32])` — big-endian limb order | 0/10 |
| `init_by_array(the 8 digest bytes as 8 words)` | 0/10 |
| read `digest[0:8]` little-endian | 0/10 |

(A 64-bit Mersenne Twister — `std::mt19937_64` — is a different generator with 64-bit
outputs and was not probed; it cannot reproduce a pipeline defined on 32-bit outputs.)

**The vectors do not pin the limb-count rule.** "Always two limbs" reproduces all ten
because every published vector's derived seed happens to exceed 2³², as almost all do.
The two readings diverge only when the top four digest bytes are zero — probability
2⁻³² per `(seed, key)` — and then the "two limbs" implementation silently produces a
different permutation from the reference. This cannot be caught by any vector short of
publishing a `(seed, key)` whose SHA-256 begins with 32 zero bits (≈ 2³² hash evaluations
to find; feasible offline, not done here). It can be fixed by one sentence in §4.

**Recommendation.** State the rule above in §4 as normative text, and add to §8 that
`init_genrand`-style seeding and 64-bit MT variants are non-conformant.

### N2 — `getrandbits` and `_randbelow` are named, not defined (§8)

§8 says *"`_randbelow` via `getrandbits`"*. Two conventions have to be right and neither
is stated:

* `getrandbits(k)` for `1 ≤ k ≤ 32` returns the **top** `k` bits of one 32-bit output —
  `genrand_uint32() >> (32 − k)` — not the bottom `k` bits. Masking instead of shifting
  reproduces 4/10 vectors (the three-element vectors, with only five admissible outcomes,
  agree by chance a fair fraction of the time — which is also an argument for the larger
  vectors being the ones that carry the conformance weight).
* `_randbelow(n)` is rejection sampling on `k = bit_length(n)` bits: `r = getrandbits(k);
  while r >= n: r = getrandbits(k)`. Every rejected draw consumes generator state, so a
  modulo reduction (`uint32 % n`) reproduces 1/10.

For `k > 32` CPython fills 32-bit words least-significant first, the final partial word
contributing its top bits. A shuffle never reaches this (`n + 1 ≤ 2³²`), so the vectors
cannot pin it; it is implemented and oracle-tested here for completeness.

**Recommendation.** Write both procedures out in §4 or §8 — four lines of pseudocode.

### N3 — What is reshuffled on a retry (§4)

`shuffled ← Fisher-Yates(values, rng)` inside the loop can be read as "shuffle a fresh
copy of the original values" or "keep shuffling the working list". **The two cannot
differ**: an attempt is only retried when the shuffled list equals the original *by value
at every position*, and Fisher-Yates moves elements only by position, so the next shuffle
of either list yields the same by-value result. What *does* matter — that the generator is
created once and its stream continues across attempts, rather than being re-seeded — is
pinned by the `same-key-different-seed` vector, whose first shuffle is the identity
`[1, 2, 3]` and whose expected value `[3, 1, 2]` is the second. That is a good vector; the
text should say what it pins.

**Recommendation.** Add: *"The generator is seeded once; attempts consume one stream."*
Optionally note the equivalence above so nobody wonders.

### N4 — §5.2 as a pre-check vs. exhausting the loop; the `error` strings

§4's algorithm has no all-equal test — all-equal inputs raise by exhausting 64 attempts.
§5.2 describes the same case as a distinct boundary with its own outcome. Both raise, and
no accepted input is affected, so an implementation may do either; this one pre-checks
(cheaper, and the message can be truthful). Two things the text leaves open:

* Whether the `error` fields in `must_raise` (`"fewer than two entities"`, `"no displacing
  permutation"`) are **normative**. This implementation includes them verbatim in its
  messages, as the cheapest way to be safe; the spec should say whether that is required
  or merely descriptive, and whether the exception type is part of conformance.
* Whether 64 is a design parameter or a safety net. For a valid input, the probability of
  exhausting it is at most `(1/n)^64` (worst case: one distinguished value among `n`);
  it is a safety net, and saying so would stop implementers treating it as tunable.

### N5 — "Decimal seed" (§4)

`f"{seed}"` is unambiguous for non-negative `int`s. The spec does not say whether negative
seeds are permitted (they format as `"-5"`, and are accepted here), and languages with a
`bool ⊂ int` relationship — Python — would silently format `True` as `"True"`. This
implementation rejects `bool` and every non-`int` with `TypeError`; `991.0` would
otherwise digest as `"991.0:key"`.

**Recommendation.** Declare `seed` a non-negative integer, or state the sign formatting.

### N6 — The key's encoding is fixed; its normalisation is not (§4)

*"key as UTF-8"* fixes the encoding of a sequence of Unicode scalar values but not which
sequence: `"é"` as U+00E9 and as U+0065 U+0301 digest differently. This implementation
applies **no normalisation**. The `unicode-key` vector (Cyrillic, no combining marks)
cannot detect a normalising implementation. Runtimes with UTF-16 strings must transcode,
and behaviour on lone surrogates is undefined (CPython raises on encode).

**Recommendation.** State "no normalisation; the key is hashed as given". Consider a
vector containing a precomposed/decomposed pair.

### N7 — "Compared by value" is the host language's equality, and that is coarser than the rendered text (I4, §5)

The justification for comparing by value is *"because the rendered text is unchanged"*. But
structural equality in the host language and equality of rendered text are different
relations:

* `1 == 1.0 == True` in Python, yet they may render as `1`, `1.0`, `True`. Such a
  "displacement" would be missed.
* Values that are unequal but render identically (custom `__str__`, float formatting) would
  be counted as displacement when the text is unchanged.
* `NaN != NaN`, so a naive `!=` would treat an undisplaced NaN as displaced, and would
  *accept* an all-NaN input instead of refusing.

This implementation uses `a is b or a == b` — equality with a reflexivity shortcut, the
same rule Python's own containers use — which fixes the NaN case and nothing else. The
remaining gap is closed by the *text-level* check in `check_control` ("rendered texts
differ"), which is the authoritative one since only the caller can render (§6).

**Recommendation.** State that displacement is judged by the host language's structural
equality, that this is a proxy, and that the rendered-text check is the ground truth.

### N8 — Token count: no tokenizer, no tolerance semantics (§7)

"Token count within tolerance" names neither a tokenizer nor whether tolerance is absolute
or relative. This implementation defaults to whitespace splitting, accepts any
`str → Sequence` callable (a BPE `encode` fits), and treats tolerance as an absolute,
symmetric bound on the count difference. The signed delta is always reported, as §7 asks.
With a whitespace tokenizer the delta for a correctly rendered table is exactly 0 —
alignment padding does not create tokens — which is worth saying, because it means a
non-zero delta under the default tokenizer indicates a renderer bug, not a tolerance
question.

### N9 — Line count (§7)

`splitlines()` and counting `"\n"` disagree on a trailing newline. Immaterial while both
arms use the same measure; noted because a mixed-implementation comparison would trip on
it. This implementation uses `splitlines()`.

### N10 — Output container and value ownership (§4, I3, I8)

The output type is unspecified. This implementation returns a new `dict` in the treatment's
iteration order; the input may be any `Mapping` and is iterated via `items()`. Values are
moved **by reference** — "moved wholesale, never … modified" is read as *not copied*.
A caller who mutates a value object afterwards changes both arms; that is consistent with
the spec but perhaps worth a sentence.

### N11 — Entities

Entities are `Mapping` keys, hence hashable and unique; the spec need say nothing more. An
implementation accepting a list of pairs would have to decide what duplicate entities mean;
by requiring a mapping the question does not arise, and §6's "structured mapping" language
already implies it.

### N12 — Intermediate values for debugging a failing Level 2 attempt

The vectors give only end results, so a mismatch does not say *which* stage diverged. The
derived generator seeds below let an implementer check the digest step in isolation
(`derive_rng_seed(key, seed)` here). They are derived from this implementation, which is
Level 2 conformant, so they are exactly as trustworthy as that.

| vector | `SHA-256("{seed}:{key}")[0:8]` big-endian | 32-bit limbs | shuffle attempts |
|---|---|---|---|
| basic-3 | 17571205385367795926 | 2 | 1 |
| k4-tuples | 7641818633514935877 | 2 | 1 |
| k7-tuples | 13956082503385751232 | 2 | 1 |
| same-key-different-seed | 10686720468346034489 | 2 | **2** |
| same-seed-different-key | 7276330015387154843 | 2 | 1 |
| partial-ties | 4070472514624194451 | 2 | 1 |
| strings | 4080548706051687408 | 2 | 1 |
| unicode-key | 12894151024714193449 | 2 | 1 |
| negatives-and-floats | 13778021978346585993 | 2 | 1 |
| large-16 | 4664424899711252242 | 2 | 1 |

A useful addition to the vectors file would be a `rng_seed` field per vector, and a
"first ten `genrand_uint32` outputs for seed N" vector so the generator can be checked
before the shuffle.

### N13 — I6 and I7 are not implementation invariants in the same sense as the others

I6 ("with high probability") is statistical and I7 is a property of how the caller chose
the seed. Neither can hold or fail *for an input* the way I1–I5, I8, I9 can. This
implementation tests I6 statistically and documents I7 at the call site. The spec might
move I7 to a "caller MUST" list so that "conformant" remains a property of the code.

---

## An observation on §6b, offered for the proofs review

*Outside the conformance report. Tentative — it may rest on a misreading of `P`.*

The corollary on sorted tables says sorting *"would satisfy C2 and destroy the experiment"*
via C3. "Sorted" can mean two things, and the propositions treat them differently:

1. **The entity order is sorted by the quantity of interest before the arms are built.**
   The control preserves that order (I2), so both arms carry the same row order and the
   target sits at the same position in each. `P` is identical across arms (C2 holds); the
   target is a function of row position alone (C3 fails); a strategy reading only
   position is *"perfectly correct and perfectly invariant"* — Proposition 2 exactly. The
   example in this repository (`sorted_entity_order_trap`) reproduces it: 1.000 on every
   arm, zero contrast, every `check_control` passing.
2. **The renderer sorts each arm by its own values.** Then the row order *as a sequence of
   entity labels* differs between arms. If that sequence is part of `P`, C2 fails and
   Proposition 1 (confounded) applies, not Proposition 2. If it is not part of `P`, then
   `P` no longer determines which entity is on top, C3 holds, and the contrast has power.

The practical rule — preserve document order, do not sort — is right under both readings,
but the *reason* differs, and the corollary as worded fits only reading 1. Stating which
sorting is meant would close it. The larger point stands independently of the wording:
reading 1 is a C3 failure that **no structural or textual check can detect**, because it
lives in how the entity order was produced rather than in either rendered text. That seems
worth saying next to §7, where a reader is being told what the checks catch.
