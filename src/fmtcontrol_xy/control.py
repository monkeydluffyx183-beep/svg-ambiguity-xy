"""The format-matched control: ``permute`` (SPEC §4) and ``check_control`` (SPEC §7).

Implemented from the Format-Matched Control Specification v1.0 and its conformance
vectors alone. Choices the specification did not determine are marked ``SPEC_NOTES §Nx``
and discussed in that file.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, Hashable, List, Mapping, Optional, Sequence, Tuple, TypeVar

from .mt19937 import MT19937

SPEC_VERSION = "1.0"

#: SPEC §4: the shuffle is retried at most this many times before refusing.
MAX_ATTEMPTS = 64

E = TypeVar("E", bound=Hashable)
V = TypeVar("V")


class NoControlError(ValueError):
    """No format-matched control exists for this input (SPEC §5, invariant I9).

    Raised — never silently degraded to an identity mapping — for fewer than two
    entities and for inputs where no displacing permutation can be found.
    """


# -- value comparison -------------------------------------------------------------------


def _same(a: Any, b: Any) -> bool:
    """Equality with a reflexivity shortcut, i.e. Python container semantics.

    SPEC I4 says displacement is judged *by value, not identity*. ``a is b or a == b`` is
    still a by-value comparison; the identity shortcut only makes it reflexive for values
    such as NaN that are unequal to themselves. SPEC_NOTES §N7.
    """
    return a is b or bool(a == b)


def _displaced_positions(before: Sequence[Any], after: Sequence[Any]) -> int:
    return sum(1 for a, b in zip(before, after) if not _same(a, b))


def _all_same(values: Sequence[Any]) -> bool:
    first = values[0]
    return all(_same(first, v) for v in values[1:])


def _same_multiset(xs: Sequence[Any], ys: Sequence[Any]) -> bool:
    """Multiset equality without requiring values to be hashable or orderable."""
    if len(xs) != len(ys):
        return False
    pool: List[Any] = list(ys)
    for x in xs:
        for i, y in enumerate(pool):
            if _same(x, y):
                del pool[i]
                break
        else:
            return False
    return not pool


# -- argument validation ----------------------------------------------------------------


def _check_seed(seed: Any) -> None:
    # bool is an int subclass but formats as "True"/"False", which would silently change
    # the digest. SPEC_NOTES §N5.
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError(f"seed must be an int, got {type(seed).__name__}")


def _check_key(key: Any) -> None:
    if not isinstance(key, str):
        raise TypeError(f"key must be a str (it is hashed as UTF-8), got {type(key).__name__}")


# -- SPEC §4 ----------------------------------------------------------------------------


def derive_rng_seed(key: str, seed: int) -> int:
    """The integer that seeds the generator: SPEC §4, first two lines after the guard.

    ``SHA-256(UTF-8("{seed}:{key}"))``, first eight bytes read as a big-endian unsigned
    integer. Exposed so another implementation can check the digest step in isolation
    before comparing whole permutations (SPEC_NOTES §N12 lists the values for every
    published vector).
    """
    _check_seed(seed)
    _check_key(key)
    digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def permute(facts: Mapping[E, V], key: str, seed: int) -> Dict[E, V]:
    """Return the control mapping for ``facts``: same entities, same order, values moved.

    ``facts``
        The treatment, entity -> fact. Any ``Mapping``; iterated in its own order (I2).
        It is not modified (I8). Facts are opaque and are moved by reference, never
        copied, inspected or altered (I3).
    ``key``
        Identifier of the item being permuted — a query id, a document id. Different
        keys give different permutations (I6). Must be ``str``; it is hashed as UTF-8.
    ``seed``
        Experiment-level integer. Must be independent of any seed that generated the
        data (I7 — a caller obligation this function cannot check).

    Raises :class:`NoControlError` when no control exists (I9): fewer than two entities,
    or no permutation that displaces at least one value *by value* (§5.1, §5.2).
    Raises ``TypeError`` for a non-``int`` seed or non-``str`` key.
    """
    _check_seed(seed)
    _check_key(key)

    entities: List[E] = []
    values: List[V] = []
    for entity, value in facts.items():
        entities.append(entity)
        values.append(value)

    if len(entities) < 2:
        raise NoControlError(
            f"fewer than two entities ({len(entities)}): every permutation is the "
            "identity, so no format-matched control exists (SPEC §5.1)"
        )
    # §5.2 stated directly. Outcome-identical to letting the loop below exhaust its 64
    # attempts, but cheaper and with a truthful message. SPEC_NOTES §N4.
    if _all_same(values):
        raise NoControlError(
            "no displacing permutation: all values are equal, so the control would "
            "render identically to the treatment (SPEC §5.2)"
        )

    rng = MT19937(derive_rng_seed(key, seed))
    for _ in range(MAX_ATTEMPTS):
        shuffled = list(values)  # fresh copy each attempt; see SPEC_NOTES §N3 for why it cannot matter
        rng.shuffle(shuffled)
        if _displaced_positions(values, shuffled) > 0:
            return dict(zip(entities, shuffled))
    raise NoControlError(
        f"no displacing permutation found in {MAX_ATTEMPTS} attempts (SPEC §4, I9)"
    )


# -- SPEC §7 ----------------------------------------------------------------------------

Tokenizer = Callable[[str], Sequence[Any]]


def _whitespace_tokens(text: str) -> Sequence[str]:
    return text.split()


@dataclass(frozen=True)
class ControlReport:
    """Outcome of :func:`check_control`. ``ok`` is ``not failures``; the counts are
    reported regardless of verdict, as SPEC §7 asks (*"report the delta rather than only
    a verdict"*)."""

    ok: bool
    failures: Tuple[str, ...]
    n_entities: int
    displaced: int
    token_count_treatment: int
    token_count_control: int
    token_delta: int
    token_tolerance: int
    line_count_treatment: int
    line_count_control: int

    def __str__(self) -> str:  # pragma: no cover - presentation only
        verdict = "OK" if self.ok else "FAIL"
        lines = [
            f"control check: {verdict}",
            f"  entities        {self.n_entities}",
            f"  displaced       {self.displaced}",
            f"  tokens          treatment={self.token_count_treatment} control={self.token_count_control} "
            f"delta={self.token_delta:+d} (tolerance {self.token_tolerance})",
            f"  lines           treatment={self.line_count_treatment} control={self.line_count_control}",
        ]
        lines.extend(f"  ! {f}" for f in self.failures)
        return "\n".join(lines)


def check_control(
    treatment: Mapping[E, V],
    control: Mapping[E, V],
    treatment_text: str,
    control_text: str,
    *,
    token_tolerance: int = 0,
    tokenizer: Optional[Tokenizer] = None,
) -> ControlReport:
    """Validate a candidate control against its treatment, structurally and as rendered.

    Both texts must come from the *same* renderer (SPEC §6); this function cannot verify
    that and does not try. Checks, in the order of SPEC §7:

    * I1 — same entity set; I2 — same order; I3 — same multiset of values;
      I4 — at least one value displaced (by value)
    * token count within ``token_tolerance`` (absolute). Default tokenizer is whitespace
      splitting; pass e.g. a BPE ``encode`` to measure what your model sees (SPEC_NOTES §N8)
    * line count identical (``str.splitlines``; SPEC_NOTES §N9)
    * rendered texts differ
    """
    if token_tolerance < 0:
        raise ValueError("token_tolerance must be non-negative")
    tokens = tokenizer if tokenizer is not None else _whitespace_tokens

    failures: List[str] = []

    t_entities = list(treatment.keys())
    c_entities = list(control.keys())
    t_values = [treatment[e] for e in t_entities]
    c_values = [control[e] for e in c_entities]

    if set(t_entities) != set(c_entities):
        missing = [e for e in t_entities if e not in control]
        extra = [e for e in c_entities if e not in treatment]
        failures.append(f"I1 entity set differs: missing={missing!r} extra={extra!r}")
    elif t_entities != c_entities:
        failures.append("I2 entity order differs between arms")

    if not _same_multiset(t_values, c_values):
        failures.append("I3 value multiset differs: values were altered, added or dropped")

    displaced = 0
    if t_entities == c_entities:
        displaced = _displaced_positions(t_values, c_values)
        if displaced == 0:
            failures.append("I4 no value displaced: the control is a second copy of the treatment")

    t_tokens = len(tokens(treatment_text))
    c_tokens = len(tokens(control_text))
    token_delta = c_tokens - t_tokens
    if abs(token_delta) > token_tolerance:
        failures.append(
            f"token count differs by {token_delta:+d} (tolerance {token_tolerance}): "
            "prompt length is a confound"
        )

    t_lines = len(treatment_text.splitlines())
    c_lines = len(control_text.splitlines())
    if t_lines != c_lines:
        failures.append(f"line count differs: treatment={t_lines} control={c_lines}")

    if treatment_text == control_text:
        failures.append("rendered texts are identical: no manipulation occurred")

    return ControlReport(
        ok=not failures,
        failures=tuple(failures),
        n_entities=len(t_entities),
        displaced=displaced,
        token_count_treatment=t_tokens,
        token_count_control=c_tokens,
        token_delta=token_delta,
        token_tolerance=token_tolerance,
        line_count_treatment=t_lines,
        line_count_control=c_lines,
    )
