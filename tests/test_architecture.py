"""Enforces the modular-monolith rules and keeps the program safe to freeze into a .exe.

Layers (an arrow means "may import"):
    cli, runner  ->  reporting  ->  analysis       (and probes)
                     analysis   ->  config, utils
                     probes     ->  config, utils      probes and analysis never import each other
                     utils      ->  config
Packages talk to each other only through their __init__ ("public API"), never through the files inside.
"""
import ast
import importlib
import pkgutil
import unittest
from pathlib import Path

import netdiag

ROOT = Path(__file__).resolve().parents[1]
CORE = {"netdiag.config", "netdiag.utils"}
ALLOWED = {  # package -> packages it may import from
    "core": {"core"},
    "probes": {"core", "probes"},
    "analysis": {"core", "analysis"},
    "reporting": {"core", "analysis", "reporting"},
    "top": {"core", "probes", "analysis", "reporting", "top"},  # cli.py, runner.py
}


def package_of(module):
    parts = module.split(".")
    if module in CORE:
        return "core"
    if len(parts) >= 2 and parts[1] in ("probes", "analysis", "reporting"):
        return parts[1]
    return "top"


def module_files():
    for p in sorted((ROOT / "netdiag").rglob("*.py")):
        name = ".".join(p.relative_to(ROOT).with_suffix("").parts)
        yield (name[: -len(".__init__")] if name.endswith(".__init__") else name), p


def imports_of(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module and n.module.split(".")[0] == "netdiag":
            found.add(n.module)
        elif isinstance(n, ast.Import):
            found |= {a.name for a in n.names if a.name.split(".")[0] == "netdiag"}
    return found


class Layering(unittest.TestCase):
    def test_packages_only_import_from_allowed_layers(self):
        for name, path in module_files():
            for dep in imports_of(path):
                self.assertIn(package_of(dep), ALLOWED[package_of(name)], f"{name} must not import {dep}")

    def test_core_modules_stay_at_the_bottom(self):
        graph = {name: imports_of(p) for name, p in module_files()}
        self.assertEqual(graph["netdiag.config"], set())
        self.assertEqual(graph["netdiag.utils"], {"netdiag.config"})

    def test_other_packages_use_the_public_api_not_internal_files(self):
        for name, path in module_files():
            for dep in imports_of(path):
                if package_of(dep) in ("probes", "analysis", "reporting") and dep.count(".") >= 2:
                    self.assertEqual(package_of(name), package_of(dep),
                                     f"{name} reaches into {dep}; import from netdiag.{package_of(dep)} instead")

    def test_no_import_cycles(self):
        graph = {name: imports_of(p) & {n for n, _ in module_files()} for name, p in module_files()}
        state = {}

        def visit(node, trail):
            state[node] = 1
            for dep in graph[node]:
                self.assertNotEqual(state.get(dep), 1, "cycle: " + " -> ".join(trail + [node, dep]))
                if dep not in state:
                    visit(dep, trail + [node])
            state[node] = 2
        for n in graph:
            if n not in state:
                visit(n, [])


class PublicApi(unittest.TestCase):
    def test_every_module_imports(self):
        for m in pkgutil.walk_packages(netdiag.__path__, "netdiag."):
            importlib.import_module(m.name)

    def test_facades_export_exactly_what_they_list(self):
        for pkg in ("probes", "analysis", "reporting"):
            mod = importlib.import_module(f"netdiag.{pkg}")
            self.assertTrue(mod.__all__)
            for name in mod.__all__:
                self.assertTrue(hasattr(mod, name), f"netdiag.{pkg}.__all__ lists missing name {name}")
            self.assertEqual(len(mod.__all__), len(set(mod.__all__)), "duplicate names in __all__")


class FreezeSafety(unittest.TestCase):
    """PyInstaller finds modules by reading import statements, so everything must be a plain static import."""

    def test_no_dynamic_imports_or_file_path_tricks(self):
        banned = ("__import__", "importlib", "pkg_resources", "__file__")
        for name, path in module_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                ident = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
                self.assertNotIn(ident, banned, f"{name} uses {ident}")
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                    self.assertNotIn(n.func.id, ("exec", "eval"), f"{name} calls {n.func.id}")
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    self.assertNotIn("importlib", ast.dump(n))

    def test_every_module_is_reachable_from_the_entry_script(self):
        modules = {name for name, _ in module_files()}
        graph = {name: imports_of(p) for name, p in module_files()}
        seen, todo = set(), sorted(imports_of(ROOT / "network_diag.py"))
        while todo:
            m = todo.pop()
            if m in seen or m not in modules:
                continue
            seen.add(m)
            # importing a module also imports its parent packages
            parts = m.split(".")
            todo += [".".join(parts[:i]) for i in range(1, len(parts))]
            todo += sorted(graph[m])
        self.assertEqual(modules - seen, set(), "these modules would be left out of a frozen .exe")


if __name__ == "__main__":
    unittest.main()
