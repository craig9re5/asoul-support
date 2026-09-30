"""Reject dependency cycles, GUI imports in core and module/argv mutation in desktop."""

import ast
import importlib.util
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def modules():
    return {
        ".".join(path.relative_to(ROOT).with_suffix("").parts).removesuffix(".__init__"): path
        for directory in ("asoul_support", "desktop")
        for path in (ROOT / directory).rglob("*.py")
    }


def inspect():
    paths = modules()
    graph, errors, sizes = {}, [], []
    for module, path in paths.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        package = module if path.name == "__init__.py" else module.rpartition(".")[0]
        dependencies = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                name = (
                    importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                    if node.level
                    else (node.module or "")
                )
                dependencies.add(name)
                dependencies.update(name + "." + alias.name for alias in node.names)
            if module.startswith("desktop") and isinstance(node, (ast.Assign, ast.AugAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if ast.unparse(target) == "sys.argv" or ast.unparse(target).startswith(
                        ("heartbeat.", "hb.")
                    ):
                        errors.append(f"{module}:{node.lineno}: mutable legacy module dependency")
            if isinstance(node, ast.FunctionDef):
                sizes.append(
                    {
                        "module": module,
                        "function": node.name,
                        "lines": node.end_lineno - node.lineno + 1,
                    }
                )
        if module.startswith("asoul_support"):
            forbidden = [
                name
                for name in dependencies
                if name.split(".")[0]
                in {"desktop", "scripts", "heartbeat", "runtime", "members", "videos", "check_auth"}
            ]
            errors.extend(f"{module}: core imports outer layer {name}" for name in forbidden)
        graph[module] = dependencies & paths.keys()
    visiting, visited = set(), set()

    def visit(module):
        if module in visiting:
            errors.append(f"dependency cycle at {module}")
            return
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module]:
            visit(dependency)
        visiting.remove(module)
        visited.add(module)

    for module in graph:
        visit(module)
    return {
        "errors": sorted(set(errors)),
        "modules": len(paths),
        "largest_functions": sorted(sizes, key=lambda row: row["lines"], reverse=True)[:12],
    }


if __name__ == "__main__":
    result = inspect()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(bool(result["errors"]))
