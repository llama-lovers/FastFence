"""Reject dataclasses and dynamic imports that bypass import contracts."""

from __future__ import annotations

import ast
from pathlib import Path


def violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    errors = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
            names.extend(f"{node.module}.{a.name}" for a in node.names)
        for name in names:
            if name == "dataclasses" or name.startswith(
                ("dataclasses.", "pydantic.dataclasses")
            ):
                errors.append(
                    f"{path}:{node.lineno}: dataclasses are forbidden; use Pydantic"
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"__import__", "eval", "exec"}:
                errors.append(
                    f"{path}:{node.lineno}: dynamic execution bypasses import contracts"
                )
    return errors


def main() -> None:
    paths = [
        p
        for root in ["src", "tests", "evaluation", "integrations"]
        for p in Path(root).rglob("*.py")
    ]
    errors = [error for path in paths for error in violations(path)]
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Architecture AST checks passed for {len(paths)} Python files")


if __name__ == "__main__":
    main()
