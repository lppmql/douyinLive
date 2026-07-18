import ast
from pathlib import Path


VERSIONS_DIR = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def test_alembic_op_execute_uses_current_single_statement_api():
    incompatible_calls: list[str] = []

    for migration_path in VERSIONS_DIR.glob("*.py"):
        tree = ast.parse(migration_path.read_text(encoding="utf-8"), filename=str(migration_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not isinstance(node.func.value, ast.Name):
                continue
            if node.func.value.id == "op" and node.func.attr == "execute" and len(node.args) > 1:
                incompatible_calls.append(f"{migration_path.name}:{node.lineno}")

    assert incompatible_calls == []
