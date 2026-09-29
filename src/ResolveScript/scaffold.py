"""Scaffolder for ``resolvescript create``.

Templates are plain files with ``@KEY@`` placeholders (stdlib substitution, no
Jinja dependency). Every placeholder-keyed file in the template tree is copied
into the new project; the ``{{ name }}`` package directory is instantiated to
the project name.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from . import __version__

TEMPLATES_DIR = Path(__file__).parent / "templates"
DEFAULT_VERSION = "0.1.0"

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ScaffoldError(Exception):
    pass


def normalize_name(name: str) -> str:
    """Collapse a requested name into a valid Python package identifier."""
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    if not _NAME_RE.match(slug):
        raise ScaffoldError(f"'{name}' cannot be used as a project/package name (got '{slug}')")
    return slug


def render(text: str, values: dict[str, str]) -> str:
    """Substitute ``@KEY@`` placeholders, preserving leftover placeholders."""

    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"@([A-Za-z0-9_]+)@", _sub, text)


def _walk_templates(root: Path) -> Iterator[Path]:
    cache_dirs = {"__pycache__"}
    return (
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.parent.name not in cache_dirs
        and p.suffix not in {".pyc", ".pyo", ".pyd"}
    )


def build_values(name: str, **overrides: str) -> dict[str, str]:
    label = name.replace("_", " ").strip()
    slug = re.sub(r"[^a-z0-9]+", "", name.lower())
    values = {
        "NAME": name,
        "VERSION": DEFAULT_VERSION,
        "DESCRIPTION": f"{name} — a DaVinci Resolve script built with ResolveScript",
        "AUTHOR": "",
        "RESOLVESCRIPT_VERSION": __version__,
        # Reverse-DNS id, for the things that need one (a Workflow Integration
        # becomes a plugin folder named after it) — and a readable form of the
        # name, since a package identifier is not a menu label.
        "ID": f"com.resolvescript.{slug}" if slug else "com.resolvescript.integration",
        "NAME_LABEL": label.title() if label else name,
    }
    for key, value in overrides.items():
        if value is not None:
            values[key.upper()] = value
    return values


def _fusion_values(name: str) -> dict[str, str]:
    """The extra substitutions a fuse template needs.

    A fuse's identity is a Lua identifier (``FuRegisterClass``) and a
    three-letter registry search code — neither of which can be derived from a
    Python project name without guessing, and both of which Fusion stores
    permanently, so a wrong guess is baked into every composition that uses the
    tool.
    """
    words = [part for part in re.split(r"[^A-Za-z0-9]+", name) if part]
    class_name = "".join(word[:1].upper() + word[1:] for word in words) or "Fuse"
    return {"CLASS_NAME": class_name, "ICON": (class_name[:3] or "Fus").capitalize()}


def scaffold_project(
    name: str,
    *,
    destination: Path | None = None,
    fmt: str = "json",
    template: str = "minimal",
    description: str = "",
    author: str = "",
) -> tuple[Path, list[str]]:
    """Create a new extension project.

    Returns ``(project_root, written_relative_paths)``.

    Available templates:
    - minimal: Basic Python script project
    - pydavinci: Project using pydavinci wrapper (type hints, autocomplete)
    - davinci-rest: Project using davinci-rest REST client
    - lua: Lua script project
    - workflow: DaVinci Resolve Workflow Integration
    - fuse: Fusion fuse (a scripted .fuse plugin)
    """
    pkg_name = normalize_name(name)

    # Map template to its directory
    template_map = {
        "minimal": "extension",
        "pydavinci": "external/pydavinci",
        "davinci-rest": "external/davinci_rest",
        "lua": "lua",
        "workflow": "workflow",
        "fuse": "fuse",
    }

    if template not in template_map:
        raise ScaffoldError(f"unknown template '{template}' (available: {', '.join(template_map.keys())})")

    template_subdir = template_map[template]

    try:
        project_dir = (destination or Path.cwd()) / name
    except TypeError as exc:
        raise ScaffoldError(f"invalid destination: {destination!r}") from exc

    project_dir = project_dir.resolve()
    if project_dir.exists():
        has_entries = any(project_dir.iterdir())
        if has_entries:
            raise ScaffoldError(f"destination {project_dir} already exists and is not empty")
    project_dir.mkdir(parents=True, exist_ok=True)

    template_root = TEMPLATES_DIR / template_subdir
    if not template_root.is_dir():
        raise ScaffoldError(f"template tree missing at {template_root}")

    # Lua, workflow and fuse templates don't have JSON/XML manifest variants:
    # the first has no manifest at all, and the other two carry a block the XML
    # reader does not model.
    if template in ("lua", "workflow", "fuse"):
        selected_manifest = "manifest.json.j2"
    else:
        selected_manifest = f"manifest.{fmt}.j2"
        if fmt not in {"json", "xml"}:
            raise ScaffoldError(f"unknown manifest format '{fmt}' (json|xml)")

    values = build_values(
        pkg_name,
        description=description,
        author=author,
        **_fusion_values(pkg_name),
    )

    written: list[str] = []
    for src in _walk_templates(template_root):
        rel = src.relative_to(template_root)

        # Handle manifest selection
        if rel.name == selected_manifest:
            rel = Path("manifest." + ("json" if template in ("lua", "workflow", "fuse") else fmt))
        elif rel.name.startswith("manifest.") and rel.suffix == ".j2":
            continue  # the unselected manifest variant is not emitted

        # Handle pyproject.toml for Python templates
        elif template != "lua" and rel.name == "pyproject.toml.j2":
            rel = Path("pyproject.toml")
            content = src.read_text(encoding="utf-8")
            # Handle conditional author array
            if author:
                content = content.replace(
                    'authors = [{name = "@AUTHOR@"}] if "@AUTHOR@" else []',
                    f'authors = [{{name = "{author}"}}]'
                )
            else:
                content = content.replace(
                    'authors = [{name = "@AUTHOR@"}] if "@AUTHOR@" else []',
                    'authors = []'
                )
            rel_text = render(str(rel), values)
            target = project_dir / rel_text
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(content, values), encoding="utf-8")
            written.append(str(target.relative_to(project_dir)))
            continue

        rel_text = render(str(rel), values)
        target = project_dir / rel_text
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(src.read_text(encoding="utf-8"), values), encoding="utf-8")
        written.append(str(target.relative_to(project_dir)))

    return project_dir, written
