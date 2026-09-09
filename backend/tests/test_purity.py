import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"

FORBIDDEN_MODULES = {"httpx", "requests", "random", "datetime", "app.llm"}
FORBIDDEN_MODULE_PREFIXES = ("app.llm",)


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _assert_no_forbidden_imports(path: Path) -> None:
    imported = _imported_names(path)
    for forbidden in FORBIDDEN_MODULES:
        assert forbidden not in imported, f"{path.name} imports forbidden module {forbidden!r}"
    for name in imported:
        for prefix in FORBIDDEN_MODULE_PREFIXES:
            assert not name.startswith(prefix), f"{path.name} imports forbidden module {name!r}"


def test_mapping_has_no_forbidden_imports() -> None:
    _assert_no_forbidden_imports(APP_DIR / "core" / "mapping.py")


def test_rules_has_no_forbidden_imports() -> None:
    _assert_no_forbidden_imports(APP_DIR / "core" / "rules.py")


def test_planner_has_no_forbidden_imports() -> None:
    _assert_no_forbidden_imports(APP_DIR / "core" / "planner.py")
