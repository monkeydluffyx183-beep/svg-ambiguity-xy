"""Level 1: the nine invariants of SPEC §3, checked over many generated inputs.

Case generation uses ``random.Random`` with its own fixed seed. That is deliberate and is
also the point of I7: the generator's seed has nothing to do with the ``seed`` passed to
``permute``.
"""

import json
import os
import random
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

import pytest

from fmtcontrol_xy import MAX_ATTEMPTS, NoControlError, derive_rng_seed, permute

GEN = random.Random(20260926)
SRC = Path(__file__).resolve().parents[1] / "src"


def _value(kind: str):
    if kind == "int":
        return GEN.randint(0, 3)  # tiny alphabet: lots of ties, some all-equal cases
    if kind == "float":
        return GEN.choice([-1.5, 0.0, 2.25, -99.75, 1e-9])
    if kind == "str":
        return GEN.choice(["Paris", "Berlin", "Rome", "Oslo"])
    if kind == "tuple":
        return (GEN.randint(0, 2), GEN.choice(["a", "b"]))
    if kind == "list":  # unhashable, mutable facts are allowed: they are opaque
        return [GEN.randint(0, 2)]
    raise AssertionError(kind)


def _cases(count: int):
    for i in range(count):
        n = GEN.randint(1, 12)
        kind = GEN.choice(["int", "float", "str", "tuple", "list"])
        facts = OrderedDict((f"e{j}", _value(kind)) for j in range(n))
        yield i, facts, f"key-{i}", GEN.choice([1, 991, 12345, 2**40])


def _all_equal(values):
    return all(v == values[0] for v in values)


CASES = list(_cases(600))


@pytest.mark.parametrize("i,facts,key,seed", CASES, ids=[f"case{c[0]}-n{len(c[1])}" for c in CASES])
def test_invariants_hold_or_it_refuses(i, facts, key, seed):
    entities = list(facts)
    values = list(facts.values())
    snapshot = json.dumps([[e, v] for e, v in facts.items()])

    if len(entities) < 2 or _all_equal(values):
        with pytest.raises(NoControlError):  # I9
            permute(facts, key, seed)
        assert json.dumps([[e, v] for e, v in facts.items()]) == snapshot  # I8 even on refusal
        return

    control = permute(facts, key, seed)

    assert list(control) == entities                                   # I1 + I2
    assert sorted(map(repr, control.values())) == sorted(map(repr, values))  # I3
    assert any(control[e] != facts[e] for e in entities)               # I4, by value
    assert permute(facts, key, seed) == control                        # I5 (in-process)
    assert json.dumps([[e, v] for e, v in facts.items()]) == snapshot  # I8
    assert control is not facts


def test_values_are_moved_by_reference_not_copied():
    facts = {"a": [1], "b": [2], "c": [3]}
    control = permute(facts, "k", 1)
    assert all(any(cv is tv for tv in facts.values()) for cv in control.values())


def test_i5_determinism_across_processes_and_hash_seeds():
    """A different PYTHONHASHSEED must not change anything: the digest is SHA-256, not hash()."""
    program = (
        "import json, sys; sys.path.insert(0, sys.argv[1]);"
        "from fmtcontrol_xy import permute;"
        "facts = {'x': 'Paris', 'y': 'Berlin', 'z': 'Rome', 'w': 'Oslo'};"
        "print(json.dumps(permute(facts, 'q-7', 991)))"
    )
    outputs = set()
    for hash_seed in ("0", "1", "4242", "random"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        out = subprocess.run(
            [sys.executable, "-c", program, str(SRC)], env=env, capture_output=True, text=True, check=True
        ).stdout.strip()
        outputs.add(out)
    assert len(outputs) == 1
    assert json.loads(outputs.pop()) == permute({"x": "Paris", "y": "Berlin", "z": "Rome", "w": "Oslo"}, "q-7", 991)


def test_i6_key_sensitivity():
    facts = {f"e{i}": i for i in range(8)}  # 8! = 40320 arrangements
    seen = {tuple(permute(facts, f"item-{k}", 991).values()) for k in range(500)}
    # Birthday bound: ~3 collisions expected among 500 draws from 40320; demand near-distinct.
    assert len(seen) >= 490


def test_i6_seed_sensitivity():
    facts = {f"e{i}": i for i in range(8)}
    seen = {tuple(permute(facts, "item-1", s).values()) for s in range(500)}
    assert len(seen) >= 490


def test_derived_seed_is_the_specified_digest():
    # SHA-256("991:item-1")[0:8] big-endian, computed independently with hashlib here.
    import hashlib

    digest = hashlib.sha256(b"991:item-1").digest()
    assert derive_rng_seed("item-1", 991) == int.from_bytes(digest[:8], "big")
    assert derive_rng_seed("item-1", 991) == 17571205385367795926


def test_key_is_hashed_as_utf8_not_repr_or_utf16():
    a = derive_rng_seed("запрос-42", 42)
    import hashlib

    assert a == int.from_bytes(hashlib.sha256("42:запрос-42".encode("utf-8")).digest()[:8], "big")
    assert a != int.from_bytes(hashlib.sha256("42:запрос-42".encode("utf-16")).digest()[:8], "big")


def test_retry_loop_is_bounded_and_the_two_reshuffle_readings_agree():
    """SPEC §4 leaves open whether each attempt reshuffles the original or the previous
    result. They cannot differ: a failed attempt equals the original by value at every
    position. Demonstrated on the one published vector that needs a second attempt."""
    from fmtcontrol_xy.mt19937 import MT19937

    facts = {"a": 1, "b": 2, "c": 3}
    n = derive_rng_seed("item-1", 12345)

    rng = MT19937(n)
    working = [1, 2, 3]
    attempts = 0
    while True:
        attempts += 1
        rng.shuffle(working)  # keep shuffling the same list
        if working != [1, 2, 3]:
            break
    assert attempts == 2  # the retry fired
    assert list(permute(facts, "item-1", 12345).values()) == working == [3, 1, 2]
    assert attempts <= MAX_ATTEMPTS


@pytest.mark.parametrize(
    "bad_seed", [True, 1.0, "991", None], ids=["bool", "float", "str", "None"]
)
def test_seed_must_be_a_real_int(bad_seed):
    with pytest.raises(TypeError):
        permute({"a": 1, "b": 2}, "k", bad_seed)


@pytest.mark.parametrize("bad_key", [b"k", 1, None], ids=["bytes", "int", "None"])
def test_key_must_be_str(bad_key):
    with pytest.raises(TypeError):
        permute({"a": 1, "b": 2}, bad_key, 1)


def test_empty_mapping_refuses():
    with pytest.raises(NoControlError):
        permute({}, "k", 1)


def test_two_distinct_values_always_swap():
    # With n=2 the only displacing permutation is the swap; the loop must find it.
    for k in range(200):
        assert list(permute({"a": "x", "b": "y"}, f"k{k}", 3).values()) == ["y", "x"]


def test_nan_is_treated_as_equal_to_itself():
    """SPEC_NOTES §N7: reflexivity shortcut. [nan, nan] must refuse (nothing could render
    differently); [nan, 1.0] must produce the swap."""
    nan = float("nan")
    with pytest.raises(NoControlError):
        permute({"a": nan, "b": nan}, "k", 1)
    control = permute({"a": nan, "b": 1.0}, "k", 1)
    assert control["a"] == 1.0 and control["b"] is nan


def test_accepts_any_mapping_and_preserves_its_iteration_order():
    class Reversed(dict):
        def __iter__(self):
            return iter(sorted(super().keys(), reverse=True))

        def items(self):
            return [(k, self[k]) for k in self]

        def keys(self):
            return list(self)

    facts = Reversed(a=1, b=2, c=3)
    control = permute(facts, "k", 991)
    assert list(control) == ["c", "b", "a"]
