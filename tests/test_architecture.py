"""Finite architectural checks; deliberately not a universal purity proof."""

import ast
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parents[1] / "pipeline"
ILLEGAL_TRANSFORM = Path(__file__).parent / "fixtures" / "io-boundary" / "illegal_transform.py"
ADAPTER_DIRECTORIES = {"sources", "sinks"}

# These are the direct APIs the project currently promises to keep in adapters.
# Dynamic calls and transitive third-party I/O are intentionally outside the check.
IO_IMPORTS = {"entsoe", "httpx", "requests", "sqlalchemy", "urllib"}
IO_CALLS = {
    "open",
    "read_bytes",
    "read_csv",
    "read_json",
    "read_parquet",
    "read_text",
    "to_csv",
    "to_json",
    "to_parquet",
    "urlopen",
    "urlretrieve",
    "write_bytes",
    "write_text",
}


def is_adapter(path: Path) -> bool:
    relative_parts = path.relative_to(PIPELINE_ROOT).parts
    return bool(relative_parts) and relative_parts[0] in ADAPTER_DIRECTORIES


def direct_io_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".")[0] for alias in node.names}
            for root in roots & IO_IMPORTS:
                violations.append(f"{path.name}:{node.lineno}: import {root}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in IO_IMPORTS:
                violations.append(f"{path.name}:{node.lineno}: import {root}")
        elif isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if name in IO_CALLS:
                violations.append(f"{path.name}:{node.lineno}: call {name}")
    return violations


def test_transformations_do_not_perform_direct_io():
    violations = [
        violation
        for path in PIPELINE_ROOT.rglob("*.py")
        if not is_adapter(path)
        for violation in direct_io_violations(path)
    ]
    assert violations == []


def test_io_boundary_detects_a_covered_call():
    assert direct_io_violations(ILLEGAL_TRANSFORM) == ["illegal_transform.py:7: call read_csv"]
