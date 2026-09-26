"""The hand-rolled generator against CPython's ``random`` — an oracle a non-Python
implementer would not have, so it is used exhaustively here.

SPEC §8 pins Level 2 to CPython's MT19937, seeding, ``getrandbits``, ``_randbelow`` and
``shuffle``. Each is compared separately so a divergence names the stage that diverged.
"""

import random

import pytest

from fmtcontrol_xy import MT19937

SEEDS = [
    0,
    1,
    2,
    7,
    991,
    12345,
    2**31 - 1,
    2**31,
    2**32 - 1,
    2**32,           # first seed needing two 32-bit limbs
    2**32 + 1,
    2**64 - 1,
    2**64,           # three limbs
    2**100 + 7,
    17571205385367795926,  # derived seed of vector basic-3
    4664424899711252242,   # derived seed of vector large-16
]


@pytest.mark.parametrize("seed", SEEDS)
def test_raw_stream_matches_cpython(seed):
    ours = MT19937(seed)
    ref = random.Random(seed)
    # Cross a twist boundary (624 outputs) more than once.
    assert [ours.genrand_uint32() for _ in range(1500)] == [ref.getrandbits(32) for _ in range(1500)]


@pytest.mark.parametrize("seed", SEEDS[:8])
def test_getrandbits_matches_cpython_for_all_widths(seed):
    ours = MT19937(seed)
    ref = random.Random(seed)
    for k in list(range(1, 80)) + [100, 128, 129, 1000]:
        assert ours.getrandbits(k) == ref.getrandbits(k), k


def test_getrandbits_zero_consumes_nothing():
    a, b = MT19937(5), MT19937(5)
    assert a.getrandbits(0) == 0
    assert a.genrand_uint32() == b.genrand_uint32()


@pytest.mark.parametrize("seed", SEEDS[:8])
def test_randbelow_matches_cpython(seed):
    ours = MT19937(seed)
    ref = random.Random(seed)
    for n in list(range(1, 70)) + [100, 255, 256, 257, 1000, 2**31, 2**33 + 5]:
        assert ours.randbelow(n) == ref._randbelow(n), n


@pytest.mark.parametrize("seed", SEEDS)
def test_shuffle_matches_cpython(seed):
    ours = MT19937(seed)
    ref = random.Random(seed)
    for n in range(0, 40):
        a = list(range(n))
        b = list(range(n))
        ours.shuffle(a)
        ref.shuffle(b)
        assert a == b, n


def test_negative_seed_uses_magnitude_like_cpython():
    assert [MT19937(-991).genrand_uint32() for _ in range(5)] == [
        random.Random(-991).getrandbits(32) for _ in range(5)
    ]


def test_first_output_of_the_reference_seed_by_array():
    # mt19937ar.c's own check value: init_by_array({0x123, 0x234, 0x345, 0x456}) -> 1067595299
    rng = MT19937(0)
    rng._init_by_array([0x123, 0x234, 0x345, 0x456])
    assert rng.genrand_uint32() == 1067595299


def test_randbelow_rejects_non_positive():
    with pytest.raises(ValueError):
        MT19937(1).randbelow(0)
    with pytest.raises(ValueError):
        MT19937(1).getrandbits(-1)
