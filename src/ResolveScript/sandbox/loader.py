"""Module loading helpers: source packages and consolidated single files."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def purge_module(prefix: str) -> None:
    """Remove a module (and its submodules) from ``sys.modules``."""
    for key in [k for k in list(sys.modules) if k == prefix or k.startswith(prefix + ".")]:
        del sys.modules[key]
    importlib.invalidate_caches()


def _entry_file(module_name: str, package_dir: Path) -> tuple[Path, str | None]:
    """Locate the on-disk entry file for ``module_name``.

    Returns ``(file, package)`` where ``package`` is the package name for a
    ``__init__.py`` entry (drives ``__package__``/``__path__``) or ``None`` for
    a single-file module.
    """
    package_dir = Path(package_dir)
    rel_dotted = module_name.replace(".", "/")
    init = package_dir / rel_dotted / "__init__.py"
    if init.is_file():
        return init, module_name
    single = package_dir / f"{rel_dotted}.py"
    if single.is_file():
        return single, None
    raise ImportError(f"cannot find entrypoint for module '{module_name}' under {package_dir}")


def load_source_module(module_name: str, package_dir: Path) -> ModuleType:
    """Import ``module_name`` fresh from ``package_dir``.

    The entry file is compiled directly from source (bypassing the bytecode
    cache) so re-installs and rebuilds always see the current code.
    """
    purge_module(module_name)
    package_dir = Path(package_dir).resolve()
    if str(package_dir) not in sys.path:
        sys.path.insert(0, str(package_dir))

    file_path, package = _entry_file(module_name, package_dir)
    module = ModuleType(module_name)
    module.__file__ = str(file_path)
    module.__package__ = package or ""
    if package:
        module.__path__ = [str(file_path.parent)]
    code = compile(file_path.read_text(encoding="utf-8"), str(file_path), "exec")
    sys.modules[module_name] = module
    exec(code, module.__dict__)
    return module


def load_built_module(module_name: str, built_file: Path) -> ModuleType:
    """Import a consolidated single-file build under ``module_name``."""
    purge_module(module_name)
    built_file = Path(built_file).resolve()
    if not built_file.is_file():
        raise FileNotFoundError(f"built package not found: {built_file}")
    spec = importlib.util.spec_from_file_location(module_name, built_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {built_file} as a Python module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
