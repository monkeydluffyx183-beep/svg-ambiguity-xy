"""MT19937 with the seeding, bit-extraction and shuffle conventions of CPython.

Written from the published algorithm (Matsumoto & Nishimura, 1998 — the reference
``mt19937ar.c``) and from SPEC.md §8, which pins Level 2 conformance to *"MT19937 as
implemented by CPython's random.Random, and Fisher-Yates as implemented by CPython's
random.shuffle (descending index, j = _randbelow(i + 1), _randbelow via getrandbits)"*.

Nothing in this module was taken from ``Lib/random.py`` or ``Modules/_randommodule.c``.
The conventions below that the spec does *not* state, and that had to be reconstructed,
are listed in ``SPEC_NOTES.md`` — chiefly how a 64-bit seed becomes MT state (§N1) and
which bits ``getrandbits`` keeps (§N2).

The class deliberately exposes only what the control needs: ``genrand_uint32``,
``getrandbits``, ``randbelow`` and ``shuffle``. It is not a general-purpose RNG and has no
floating-point output.
"""

from __future__ import annotations

from typing import List, MutableSequence, Sequence

_N = 624
_M = 397
_MATRIX_A = 0x9908B0DF
_UPPER_MASK = 0x80000000
_LOWER_MASK = 0x7FFFFFFF
_MASK32 = 0xFFFFFFFF


class MT19937:
    """Mersenne Twister, seeded the way CPython seeds ``random.Random(int)``."""

    __slots__ = ("_mt", "_index")

    def __init__(self, seed: int) -> None:
        self._mt: List[int] = [0] * _N
        self._index = _N
        self.seed(seed)

    # -- seeding -----------------------------------------------------------------------

    def _init_genrand(self, s: int) -> None:
        mt = self._mt
        mt[0] = s & _MASK32
        for i in range(1, _N):
            prev = mt[i - 1]
            mt[i] = (1812433253 * (prev ^ (prev >> 30)) + i) & _MASK32
        self._index = _N

    def _init_by_array(self, key: Sequence[int]) -> None:
        mt = self._mt
        self._init_genrand(19650218)
        i, j = 1, 0
        key_length = len(key)
        for _ in range(max(_N, key_length)):
            prev = mt[i - 1]
            mt[i] = ((mt[i] ^ ((prev ^ (prev >> 30)) * 1664525)) + key[j] + j) & _MASK32
            i += 1
            j += 1
            if i >= _N:
                mt[0] = mt[_N - 1]
                i = 1
            if j >= key_length:
                j = 0
        for _ in range(_N - 1):
            prev = mt[i - 1]
            mt[i] = ((mt[i] ^ ((prev ^ (prev >> 30)) * 1566083941)) - i) & _MASK32
            i += 1
            if i >= _N:
                mt[0] = mt[_N - 1]
                i = 1
        mt[0] = 0x80000000
        self._index = _N

    def seed(self, n: int) -> None:
        """Seed from an arbitrary-precision integer the way CPython does.

        ``abs(n)`` is split into 32-bit limbs, least significant first, using as many
        limbs as the magnitude needs (one limb for zero), and fed to ``init_by_array``.
        See SPEC_NOTES.md §N1: this is *not* ``init_genrand(n & 0xFFFFFFFF)`` and it is
        not a 64-bit Mersenne Twister; both reproduce none of the conformance vectors.
        """
        n = abs(int(n))
        key: List[int] = []
        while n:
            key.append(n & _MASK32)
            n >>= 32
        if not key:
            key = [0]
        self._init_by_array(key)

    # -- generation --------------------------------------------------------------------

    def _twist(self) -> None:
        mt = self._mt
        for kk in range(_N):
            y = (mt[kk] & _UPPER_MASK) | (mt[(kk + 1) % _N] & _LOWER_MASK)
            mt[kk] = mt[(kk + _M) % _N] ^ (y >> 1) ^ (_MATRIX_A if y & 1 else 0)
        self._index = 0

    def genrand_uint32(self) -> int:
        """Next tempered 32-bit output."""
        if self._index >= _N:
            self._twist()
        y = self._mt[self._index]
        self._index += 1
        y ^= y >> 11
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= y >> 18
        return y & _MASK32

    def getrandbits(self, k: int) -> int:
        """``k`` random bits as a non-negative integer.

        For ``k <= 32`` the result is the *top* ``k`` bits of one 32-bit output. For larger
        ``k`` 32-bit words are consumed least-significant-word first and the final,
        partial word contributes its top bits. See SPEC_NOTES.md §N2.
        """
        if k < 0:
            raise ValueError("number of bits must be non-negative")
        if k == 0:
            return 0
        if k <= 32:
            return self.genrand_uint32() >> (32 - k)
        result = 0
        shift = 0
        while k > 0:
            word = self.genrand_uint32()
            if k < 32:
                word >>= 32 - k
            result |= word << shift
            shift += 32
            k -= 32
        return result

    def randbelow(self, n: int) -> int:
        """Uniform integer in ``[0, n)`` by rejection sampling on ``bit_length(n)`` bits.

        This is the ``_randbelow`` the spec names. The rejection loop matters for
        conformance: every rejected draw consumes generator state.
        """
        if n <= 0:
            raise ValueError("n must be positive")
        k = n.bit_length()
        r = self.getrandbits(k)
        while r >= n:
            r = self.getrandbits(k)
        return r

    def shuffle(self, x: MutableSequence) -> None:
        """In-place Fisher-Yates, descending index, ``j = randbelow(i + 1)`` (SPEC §8)."""
        for i in range(len(x) - 1, 0, -1):
            j = self.randbelow(i + 1)
            x[i], x[j] = x[j], x[i]
