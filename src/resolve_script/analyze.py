"""Static analyzer (M6): syntax, unused imports, manifest + API coverage.

``analyze_project()`` scans an extension directory and reports:

- MANIFEST     validation errors (reuses ``manifest/validation.py``)
- SYNTAX       compile failures per .py file
- UNUSED_IMPORT imports bound but never referenced afterwards
- API_UNMOCKED calls to methods missing from the mock sandbox
- ATTR_KEY     ``GetAttrs()``-style keys that the mock does not define
- TARGET       target-name problems (already covered by MANIFEST)

The API surfaces are introspected from the mock itself (``sandbox/api.py``), so
the checker stays in sync with what ``dev``/``test`` actually provide.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .manifest.validation import validate_manifest
from .sandbox.api import (
    FakeClip,
    FakeComp,
    FakeFolder,
    FakeFusion,
    FakeKey,
    FakeMediaPool,
    FakeMediaPoolItem,
    FakeProject,
    FakeProjectManager,
    FakeResolve,
    FakeSpline,
    FakeStroke,
    FakeTimeline,
    FakeTool,
)

# Conventional names practitioners use for Resolve API root objects.
KNOWN_ROOTS = {
    "resolve",
    "project",
    "projectManager",
    "timeline",
    "clip",
    "mediaPool",
    "mediaPoolItem",
    "mediapoolitem",
    "folder",
    "fusion",
    "comp",
    "tool",
    "stroke",
    "spline",
    "key",
    "currentComp",
    "currentTool",
}

_SKIP_PARTS = {"__pycache__", ".venv", "venv", "build", "dist", ".git", "node_modules"}
_ATTR_KEY_RE = re.compile(r"^(TOOLS|COMPS|SPLINES|STROKES|INPOINT|OUTPOINT|EDIT|FRAME)_[A-Z0-9_]+$")


@dataclass
class Issue:
    code: str
    severity: str  # "error" | "warning" | "info"
    file: str
    line: int
    message: str


@dataclass
class Analysis:
    issues: list[Issue] = field(default_factory=list)
    api_used: set[str] = field(default_factory=set)
    api_mocked: set[str] = field(default_factory=set)
    attr_keys_used: set[str] = field(default_factory=set)
    attr_keys_mocked: set[str] = field(default_factory=set)

    def api_report(self) -> list[str]:
        lines = [
            f"API coverage: {len(self.api_used & self.api_mocked)} of "
            f"{len(self.api_mocked)} mocked methods used",
        ]
        missing = sorted(self.api_used - self.api_mocked)
        unused = sorted(self.api_mocked - self.api_used)
        if missing:
            lines.append(f"  called but not mocked: {', '.join(missing)}")
        if unused:
            lines.append(f"  mocked but unused: {', '.join(unused)}")
        attr_missing = sorted(self.attr_keys_used - self.attr_keys_mocked)
        if attr_missing:
            lines.append(f"  attr keys not in mock: {', '.join(attr_missing)}")
        return lines


def _mocked_api_surface() -> set[str]:
    classes = (
        FakeResolve,
        FakeProjectManager,
        FakeProject,
        FakeTimeline,
        FakeClip,
        FakeMediaPoolItem,
        FakeFolder,
        FakeMediaPool,
        FakeKey,
        FakeSpline,
        FakeStroke,
        FakeTool,
        FakeComp,
        FakeFusion,
    )
    return {
        name
        for cls in classes
        for name in dir(cls)
        if not name.startswith("_") and callable(getattr(cls, name, None))
    }


def _mock_attr_keys() -> set[str]:
    """Extract keys from ``self._attrs = {...}`` in sandbox/api.py (stays in sync)."""
    source = Path(__file__).resolve().parent / "sandbox" / "api.py"
    tree = ast.parse(source.read_text("utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Attribute) and target.attr == "_attrs"):
                continue
            if not (isinstance(target.value, ast.Name) and target.value.id == "self"):
                continue
            if isinstance(node.value, ast.Dict):
                keys.update(
                    key.value
                    for key in node.value.keys
                    if isinstance(key, ast.Constant) and isinstance(key.value, str)
                )
    return keys


def _is_skip(rel: Path) -> bool:
    return any(part in _SKIP_PARTS for part in rel.parts)


def _unused_imports(tree: ast.AST, rel: Path, analysis: Analysis) -> None:
    names_used = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    names_used.update(
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        if isinstance(node.value, ast.Name)
    )
    for node in ast.walk(tree):
        aliases: list[ast.alias] = []
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            aliases = node.names
        for alias in aliases:
            name = alias.asname or (alias.name.split(".")[0])
            if name == "*":
                continue
            if name in {"__version__"}:
                continue
            count = sum(1 for token in names_used if token == name)
            if count <= 1:  # only the binding itself
                analysis.issues.append(
                    Issue(
                        "UNUSED_IMPORT",
                        "warning",
                        rel.as_posix(),
                        node.lineno,
                        f"imported name '{name}' is never used",
                    )
                )


def _collect_api(tree: ast.AST, analysis: Analysis) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        attr = node.func
        if not isinstance(attr, ast.Attribute):
            continue
        base = attr.value
        if isinstance(base, ast.Attribute):
            while isinstance(base, ast.Attribute):
                base = base.value
        if isinstance(base, ast.Name) and base.id in KNOWN_ROOTS:
            analysis.api_used.add(attr.attr)


def _collect_attr_keys(tree: ast.AST, analysis: Analysis) -> None:
    seen_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for text in seen_constants:
        if _ATTR_KEY_RE.match(text) or text in {"TOOLS_RegID", "COMPS_Name"}:
            analysis.attr_keys_used.add(text)


def analyze_project(root: Path, manifest=None) -> Analysis:
    root = Path(root).resolve()
    analysis = Analysis()
    analysis.api_mocked = _mocked_api_surface()
    analysis.attr_keys_mocked = _mock_attr_keys()

    if manifest is not None:
        for message in validate_manifest(manifest):
            analysis.issues.append(
                Issue("MANIFEST", "error", "manifest.json", 0, message)
            )

    for py in sorted(root.rglob("*.py")):
        try:
            rel = py.relative_to(root)
        except ValueError:
            rel = Path(py.name)
        if _is_skip(rel):
            continue
        try:
            tree = ast.parse(py.read_text("utf-8"), filename=str(py))
        except SyntaxError as exc:
            analysis.issues.append(
                Issue(
                    "SYNTAX",
                    "error",
                    rel.as_posix(),
                    exc.lineno or 0,
                    f"syntax error: {exc.msg}",
                )
            )
            continue
        except UnicodeDecodeError:
            continue
        _unused_imports(tree, rel, analysis)
        _collect_api(tree, analysis)
        _collect_attr_keys(tree, analysis)

    for name in sorted(analysis.api_used - analysis.api_mocked):
        analysis.issues.append(
            Issue(
                "API_UNMOCKED",
                "info",
                "",
                0,
                f"'{name}()' is called but not provided by the mock sandbox",
            )
        )
    for key in sorted(analysis.attr_keys_used - analysis.attr_keys_mocked):
        analysis.issues.append(
            Issue(
                "ATTR_KEY",
                "info",
                "",
                0,
                f"attr key '{key}' is read but not defined by the mock sandbox",
            )
        )
    return analysis


def issues_to_json(analysis: Analysis) -> str:
    return json.dumps(
        [issue.__dict__ for issue in analysis.issues], indent=2, default=str
    )
