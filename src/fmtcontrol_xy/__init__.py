"""fmtcontrol_xy — an independent, specification-only implementation of the
format-matched control (Format-Matched Control Specification v1.0).

    from fmtcontrol_xy import permute, check_control

    facts     = {"doc_1": ("Paris", 2.1), "doc_2": ("Berlin", 3.4), "doc_3": ("Rome", 0.7)}
    permuted  = permute(facts, key="query_42", seed=991)

    enhanced_text = render(facts)      # one renderer,
    permuted_text = render(permuted)   # both arms

    report = check_control(facts, permuted, enhanced_text, permuted_text)
    assert report.ok, report.failures

Standard library only. ``permute`` is the control, ``check_control`` the validation, and
``NoControlError`` the refusal (SPEC I9). ``python -m fmtcontrol_xy.conformance`` runs the
published conformance vectors.
"""

from .control import (
    MAX_ATTEMPTS,
    SPEC_VERSION,
    ControlReport,
    NoControlError,
    check_control,
    derive_rng_seed,
    permute,
)
from .mt19937 import MT19937

__version__ = "0.1.0"

__all__ = [
    "MAX_ATTEMPTS",
    "MT19937",
    "SPEC_VERSION",
    "ControlReport",
    "NoControlError",
    "check_control",
    "derive_rng_seed",
    "permute",
    "__version__",
]
