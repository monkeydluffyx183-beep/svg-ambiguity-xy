#!/usr/bin/env python3
"""The format-matched control in a domain that is not SVG: an operations table.

    python examples/ops_table_control.py

Runs on a bare interpreter — no install, no model, no network, standard library only.

Task: "Which host should be restarted? Restart the host with the highest p99 latency."
Context: a table of hosts and their metrics. Three arms:

    baseline   the hosts are named, no metrics
    enhanced   the true table
    permuted   the same table with the metric rows moved between hosts

The 'solvers' below are deterministic functions of the prompt text, not models. They are
here to show what the three-way decomposition *looks like* under three known behaviours —
including the one this control exists to expose: an improvement that is entirely format.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fmtcontrol_xy import check_control, permute  # noqa: E402

Metrics = Tuple[int, int, int]  # (cpu %, mem %, p99 ms)
Facts = Dict[str, Metrics]

INSTRUCTION = "Which host should be restarted? Restart the host with the highest p99 latency."
HOSTS = ["web-01", "web-02", "api-01", "db-01"]

# The seed used for permutation. SPEC I7: independent of the seed that generates the data.
PERMUTE_SEED = 991
DATA_SEED = 20260926


# -- one renderer, used for both arms (SPEC §6) -------------------------------------------


def render_table(facts: Facts) -> str:
    lines = [f"{'host':<8}{'cpu%':>6}{'mem%':>6}{'p99ms':>7}"]
    for host, (cpu, mem, p99) in facts.items():  # document order: never sorted (SPEC §6b)
        lines.append(f"{host:<8}{cpu:>6}{mem:>6}{p99:>7}")
    return "\n".join(lines)


def prompt_for(arm: str, facts: Facts, control: Optional[Facts]) -> str:
    if arm == "baseline":
        context = "Hosts: " + ", ".join(facts)
    elif arm == "enhanced":
        context = render_table(facts)
    elif arm == "permuted":
        assert control is not None
        context = render_table(control)
    else:
        raise ValueError(arm)
    return f"{context}\n\n{INSTRUCTION}\nAnswer with the host name only."


# -- three deterministic 'solvers' ---------------------------------------------------------

Solver = Callable[[str], Optional[str]]


def _table_rows(prompt: str) -> List[Tuple[str, int]]:
    rows = []
    for line in prompt.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] in HOSTS and parts[3].isdigit():
            rows.append((parts[0], int(parts[3])))
    return rows


def reads_the_values(prompt: str) -> Optional[str]:
    """Uses the assignment: which host has the highest p99. Falls back to the first host."""
    rows = _table_rows(prompt)
    if rows:
        return max(rows, key=lambda r: r[1])[0]
    return prompt.split("Hosts: ")[1].split(",")[0] if "Hosts: " in prompt else None


def reads_position_only(prompt: str) -> Optional[str]:
    """Never looks at a value: always names the first host listed."""
    rows = _table_rows(prompt)
    if rows:
        return rows[0][0]
    return prompt.split("Hosts: ")[1].split(",")[0] if "Hosts: " in prompt else None


def answers_only_when_a_table_is_present(prompt: str) -> Optional[str]:
    """Responds to the *shape* of the context: with a table it guesses the last row,
    without one it abstains. This is a pure format effect."""
    rows = _table_rows(prompt)
    return rows[-1][0] if rows else None


SOLVERS: Dict[str, Solver] = {
    "reads the values": reads_the_values,
    "reads position only": reads_position_only,
    "answers only if a table is present": answers_only_when_a_table_is_present,
}


# -- data ---------------------------------------------------------------------------------


def make_case(gen: random.Random) -> Facts:
    p99s = gen.sample(range(20, 2000), len(HOSTS))  # distinct, so the target is unique
    return {h: (gen.randint(1, 99), gen.randint(1, 99), p) for h, p in zip(HOSTS, p99s)}


def target(facts: Facts) -> str:
    return max(facts, key=lambda h: facts[h][2])


# -- main ---------------------------------------------------------------------------------


def show_one_case() -> None:
    gen = random.Random(DATA_SEED)
    facts = make_case(gen)
    control = permute(facts, key="case-0000", seed=PERMUTE_SEED)

    for arm in ("baseline", "enhanced", "permuted"):
        print(f"--- {arm} ---")
        print(prompt_for(arm, facts, control))
        print()

    report = check_control(facts, control, render_table(facts), render_table(control))
    print(report)
    print()
    print(f"target (true highest p99): {target(facts)}")
    print(f"the permuted table says:   {target(control)}")
    print()


def decomposition(n_cases: int = 400) -> None:
    gen = random.Random(DATA_SEED)
    cases = [make_case(gen) for _ in range(n_cases)]
    controls = [permute(f, key=f"case-{i:04d}", seed=PERMUTE_SEED) for i, f in enumerate(cases)]

    # Every control must pass the checks; a failure here would invalidate the arm.
    bad = [
        i
        for i, (f, c) in enumerate(zip(cases, controls))
        if not check_control(f, c, render_table(f), render_table(c)).ok
    ]
    assert not bad, f"invalid controls for cases {bad}"

    arms = ("baseline", "permuted", "enhanced")
    print(f"identification accuracy over {n_cases} cases, {len(HOSTS)} hosts each "
          f"(chance = {1 / len(HOSTS):.3f})\n")
    print(f"{'solver':<36}{'baseline':>10}{'permuted':>10}{'enhanced':>10}"
          f"   {'total':>7}{'format':>8}{'info':>7}")
    effects: Dict[str, Tuple[float, float, float]] = {}
    for name, solver in SOLVERS.items():
        acc = {}
        for arm in arms:
            hits = sum(
                solver(prompt_for(arm, f, c)) == target(f) for f, c in zip(cases, controls)
            )
            acc[arm] = hits / n_cases
        total = acc["enhanced"] - acc["baseline"]
        fmt = acc["permuted"] - acc["baseline"]
        info = acc["enhanced"] - acc["permuted"]
        effects[name] = (total, fmt, info)
        print(f"{name:<36}{acc['baseline']:>10.3f}{acc['permuted']:>10.3f}{acc['enhanced']:>10.3f}"
              f"   {total:>+7.3f}{fmt:>+8.3f}{info:>+7.3f}")

    values_total, values_fmt, _ = effects["reads the values"]
    table_total, table_fmt, table_info = effects["answers only if a table is present"]
    print()
    print("total  = enhanced - baseline    what a two-arm comparison reports")
    print("format = permuted - baseline    the part the third arm attributes to shape alone")
    print("info   = enhanced - permuted    the part that survives destroying the assignment")
    print()
    print(f"Row 3 is the case the control exists for. A two-arm study would report {table_total:+.3f}")
    print(f"as the value of supplying metrics; the third arm shows {table_fmt:+.3f} of it is format")
    print(f"and {table_info:+.3f} is information.")
    print("Row 2 is SPEC §6b, Proposition 2: a strategy that depends on the context only")
    print("through its presentation scores identically on both matched arms, so the")
    print("contrast has no power against it, however good or bad it is.")
    print(f"Row 1's format term is {values_fmt:+.3f}, below zero: for a solver that trusts the table,")
    print("the permuted arm does not merely withhold the answer, it supplies a wrong one.")
    print("That is the open condition C4 in SPEC §6a — misinformed is not the same as")
    print("uninformed — and it is a property of the solver, not of the representation.")


def sorted_entity_order_trap(n_cases: int = 400) -> None:
    """SPEC §6b, corollary on sorted tables — the failure the checks cannot see.

    Order the *entities* by the quantity of interest before building the arms. The control
    preserves that order (I2), so both arms put the true target in row 1. Every check
    passes: same shape, values displaced, texts differ. Yet a solver that reads nothing but
    row position is perfectly correct on both arms, so the contrast is powerless (§6b,
    Proposition 2) — the target now factors through presentation (C3 fails), and no
    structural or textual check can detect that, because it is a property of how the
    entity order was produced, not of the two texts.
    """
    gen = random.Random(DATA_SEED)
    cases = []
    for _ in range(n_cases):
        facts = make_case(gen)
        cases.append(dict(sorted(facts.items(), key=lambda kv: -kv[1][2])))  # the trap
    controls = [permute(f, key=f"case-{i:04d}", seed=PERMUTE_SEED) for i, f in enumerate(cases)]
    assert all(check_control(f, c, render_table(f), render_table(c)).ok for f, c in zip(cases, controls))

    solver = reads_position_only
    acc = {
        arm: sum(solver(prompt_for(arm, f, c)) == target(f) for f, c in zip(cases, controls)) / n_cases
        for arm in ("baseline", "permuted", "enhanced")
    }
    print()
    print("--- the sorted-entity-order trap (SPEC §6b, sorted tables) ---")
    print(f"entities pre-sorted by p99; every check_control passes; solver = 'reads position only'")
    print(f"baseline {acc['baseline']:.3f}   permuted {acc['permuted']:.3f}   enhanced {acc['enhanced']:.3f}"
          f"   ->  info = {acc['enhanced'] - acc['permuted']:+.3f}")
    print("Perfectly correct, perfectly invariant, zero contrast. The checks are about the two")
    print("texts; this is about where the row order came from. Keep document order (I2).")


if __name__ == "__main__":
    show_one_case()
    decomposition()
    sorted_entity_order_trap()
