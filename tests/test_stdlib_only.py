"""The package must import nothing outside the standard library, and nothing from any
benchmark. Checked by parsing the source, not by trusting a claim in a README."""

import ast
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "fmtcontrol_xy"

# Fallback for Python 3.9, which has no sys.stdlib_module_names.
_ALLOWED_FALLBACK = {"hashlib", "json", "sys", "dataclasses", "pathlib", "typing", "__future__"}


def _top_level_imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside the package
                continue
            assert node.module is not None
            yield node.module.split(".")[0]


def test_only_standard_library_imports():
    stdlib = getattr(sys, "stdlib_module_names", None) or _ALLOWED_FALLBACK
    offenders = {}
    for module in sorted(PACKAGE.glob("*.py")):
        bad = {name for name in _top_level_imports(module) if name not in stdlib}
        if bad:
            offenders[module.name] = bad
    assert not offenders, offenders


def test_permute_and_checks_do_not_depend_on_the_random_module():
    """SPEC I5: determinism must not ride on interpreter state. ``random`` is used only
    in tests, as an oracle — never by the implementation."""
    for module in ("control.py", "mt19937.py", "__init__.py"):
        assert "random" not in set(_top_level_imports(PACKAGE / module)), module
