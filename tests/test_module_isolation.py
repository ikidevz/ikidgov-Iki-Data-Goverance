import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULES_DIR = ROOT / "src" / "ikidgov" / "modules"


def _imports_in(file_path: pathlib.Path) -> list[str]:
    tree = ast.parse(file_path.read_text(
        encoding="utf-8"), filename=str(file_path))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                imports.append(node.module or "")
            else:
                imports.append("relative")
    return imports


def test_no_module_imports_another_modules_internals():
    violations = []
    for module_dir in MODULES_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        impl_path = module_dir / "impl.py"
        if not impl_path.exists():
            continue
        imports = _imports_in(impl_path)
        if any(name and name.startswith("ikidgov.modules") and name.endswith("impl") for name in imports):
            violations.append(str(impl_path))
    assert not violations, "Module isolation violated:\n" + \
        "\n".join(violations)
