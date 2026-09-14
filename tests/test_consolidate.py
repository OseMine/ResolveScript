"""M3 — consolidator edge matrix and parity tests."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from resolve_script.consolidate import (
    BuildConfig,
    ConsolidateError,
    collect_python_files,
    config_from_manifest,
    consolidate,
    module_dotted_name,
    order_modules,
    read_module_content,
    strip_internal_imports,
)
from resolve_script.manifest.json_reader import loads as manifest_loads


def write_package(root: Path, files: dict[str, str]) -> Path:
    """Write a source tree under ``root/<name>`` and return the package dir."""
    pkg = root / "pkg"
    for rel, content in files.items():
        target = pkg / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return pkg


def build(pkg: Path, output: Path | None = None, **kwargs) -> str:
    """Consolidate a package and return the resulting file text."""
    out = output or pkg.parent / "dist" / "pkg.py"
    config = BuildConfig(package_root=pkg, output=out, **kwargs)
    result = consolidate(config)
    assert result.output == out
    return out.read_text(encoding="utf-8")


def import_output(out: Path, modname: str) -> object:
    """Import a consolidated file as a module (the importable-library contract)."""
    spec = importlib.util.spec_from_file_location(modname, out)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


# --- edge matrix: external imports stay -------------------------------------


def test_external_import_kept(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {"__init__.py": "", "mod.py": "import externalmod\n"},
    )
    text = build(pkg)
    assert "import externalmod\n" in text
    assert "# import externalmod" not in text


def test_from_external_kept(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {"__init__.py": "", "mod.py": "from externalmod import thing\n"},
    )
    text = build(pkg)
    assert "from externalmod import thing\n" in text


def test_import_as_alias_kept(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {"__init__.py": "", "mod.py": "import externalmod as ext\n"},
    )
    text = build(pkg)
    assert "import externalmod as ext\n" in text


# --- edge matrix: internal imports are commented out ------------------------


def test_relative_submodule_import_commented_and_bound(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "from . import core\n",
            "core.py": "VALUE = 1\n",
        },
    )
    text = build(pkg)
    assert "# from . import core" in text
    assert "core = _rs_shared" in text


def test_absolute_package_import_commented(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "top.py": "from pkg.core import VALUE\nimport pkg.util\n",
            "core.py": "VALUE = 1\n",
            "util.py": "def helper() -> None: pass\n",
        },
    )
    text = build(pkg)
    assert "# from pkg.core import VALUE" in text
    assert re.search(r"^from pkg\.core import VALUE$", text, flags=re.MULTILINE) is None
    assert "# import pkg.util" in text
    assert "pkg = _rs_shared" in text
    assert "pkg.util = _rs_shared" in text


def test_multiline_internal_import_commented(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "mod.py": "from pkg.core import (\n    VALUE,\n    OTHER,\n)\n",
            "core.py": "VALUE = 1\nOTHER = 2\n",
        },
    )
    text = build(pkg)
    assert "# from pkg.core import (" in text
    assert "#     VALUE," in text
    assert "#     OTHER," in text
    assert "# )" in text
    assert "VALUE," in text  # definition still present in core module


def test_no_false_positive_prefix(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {"__init__.py": "", "mod.py": "import pkgame\nfrom pkgish import x\n"},
    )
    text = build(pkg)
    assert "import pkgame\n" in text
    assert "from pkgish import x\n" in text


# --- edge matrix: ordering --------------------------------------------------


def test_dependency_order_info_before_use(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "from . import core\nfrom . import app\n",
            "core.py": "def core_value() -> str: return 'core'\n",
            "app.py": "from . import core\n\nNAME = core.core_value()\n",
        },
    )
    text = build(pkg)
    assert text.index("def core_value") < text.index("NAME = core.core_value()")
    output = import_output(pkg.parent / "dist" / "pkg.py", "pkg")
    assert output.NAME == "core"


def test_init_reexports_commented_but_names_survive(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "from . import core\nfrom .core import shared\n",
            "core.py": "shared = 'value'\n",
        },
    )
    text = build(pkg)
    assert "# from . import core" in text
    assert "core = _rs_shared" in text
    assert "# from .core import shared" in text
    assert "shared = 'value'" in text


def test_circular_imports_still_emitted(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "a.py": "from .b import B\nA = 'a'\n",
            "b.py": "from .a import A\nB = 'b'\n",
        },
    )
    config = BuildConfig(package_root=pkg, output=pkg.parent / "dist" / "pkg.py")
    result = consolidate(config)
    assert {"pkg.a", "pkg.b"} <= set(result.modules)
    output = import_output(result.output, "pkg")
    assert output.A == "a"
    assert output.B == "b"


def test_type_checking_guard_local_import_commented(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "mod.py": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from pkg.core import TYPE_ONLY\n"
                "\n"
                "def f() -> None:\n"
                "    pass\n"
            ),
            "core.py": "TYPE_ONLY = 'annotation only'\n",
        },
    )
    text = build(pkg)
    assert "pass  # from pkg.core import TYPE_ONLY" in text
    assert not re.search(r"^    from pkg", text, flags=re.MULTILINE)  # no live import left
    output = import_output(pkg.parent / "dist" / "pkg.py", "pkg")
    assert hasattr(output, "f")


def test_type_checking_guard_external_import_kept(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "mod.py": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from externalmod import Thing\n"
            ),
        },
    )
    text = build(pkg)
    assert "    from externalmod import Thing" in text


def test_all_controlled_exports_preserved(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "mod.py": "__all__ = ['public']\npublic = 1\n_private = 2\n",
        },
    )
    text = build(pkg)
    assert "__all__ = ['public']" in text


# --- stdlib hoisting + future imports ---------------------------------------


def test_stdlib_imports_hoisted(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "mod.py": "import os\nimport pathlib\n",
        },
    )
    text = build(pkg)
    assert text.index("# Standard library imports") < text.index("# ==== Module:")
    assert "import os" in text
    assert "import pathlib" in text


def test_future_imports_hoisted_and_deduplicated(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "a.py": "from __future__ import annotations\n\ndef f() -> None: pass\n",
            "b.py": "from __future__ import annotations\n\ndef g() -> None: pass\n",
        },
    )
    text = build(pkg)
    assert text.count("from __future__ import annotations") == 1
    assert text.index("from __future__ import annotations") < text.index("# ==== Module:")


# --- main-guard / library contract ------------------------------------------


def test_main_guard_is_an_error(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {"__init__.py": "", "mod.py": "if __name__ == '__main__':\n    print('run')\n"},
    )
    with pytest.raises(ConsolidateError, match="__main__"):
        build(pkg)


def test_main_guard_with_docstring_only_is_allowed(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "mod.py": "if __name__ == '__main__':\n    '''Documentation only.'''\n",
        },
    )
    build(pkg)


def test_missing_entry_is_an_error(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {"__init__.py": "", "core.py": "VALUE = 1\n"},
    )
    with pytest.raises(ConsolidateError, match="consolidate.entry"):
        build(pkg, entry="pkg/nope.py")


# --- exclude / no_comment ---------------------------------------------------


def test_exclude_pattern_skips_files(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "app.py": "VALUE = 1\n",
            "tests/test_app.py": "def test_app() -> None: pass\n",
        },
    )
    text = build(pkg, exclude=("tests",))
    assert "test_app" not in text
    assert "VALUE = 1" in text
    files = collect_python_files(pkg, exclude=("tests",))
    assert all("tests" not in f.as_posix() for f in files)


def test_no_comment_keeps_internal_imports(tmp_path: Path) -> None:
    pkg = write_package(
        tmp_path,
        {
            "__init__.py": "",
            "hazard.py": "from . import core\n",
            "core.py": "CORE = True\n",
        },
    )
    text = build(pkg, no_comment=("pkg.hazard",))
    assert "from . import core" in text
    assert "# from . import core" not in text


# --- manifest-driven config -------------------------------------------------


def test_config_from_manifest(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("__version__ = '0.1.0'\n", encoding="utf-8")
    (tmp_path / "pkg" / "core.py").write_text("VALUE = 7\n", encoding="utf-8")
    manifest = manifest_loads(
        """
        {
          "name": "pkg",
          "version": "0.1.0",
          "package_dir": "pkg",
          "consolidate": {
            "enabled": true,
            "output": "pkg.py",
            "entry": "pkg/__init__.py",
            "exclude": ["tests"],
            "no_comment": []
          }
        }
        """
    )
    config = config_from_manifest(tmp_path, manifest)
    assert config.package_root == tmp_path / "pkg"
    assert config.output == tmp_path / "dist" / "pkg.py"
    assert config.entry == "pkg/__init__.py"

    result = consolidate(config)
    assert result.output.exists()
    output = import_output(result.output, "pkg")
    assert output.__version__ == "0.1.0"
    assert output.VALUE == 7


# --- unit-level helpers -----------------------------------------------------


def test_module_dotted_name() -> None:
    root = Path("pkg")
    assert module_dotted_name(root / "__init__.py", root, "pkg") == "pkg"
    assert module_dotted_name(root / "core.py", root, "pkg") == "pkg.core"
    assert module_dotted_name(root / "sub" / "__init__.py", root, "pkg") == "pkg.sub"


def test_order_modules_cycles_reported() -> None:
    ordered, cycles = order_modules({"pkg.a": {"pkg.b"}, "pkg.b": {"pkg.a"}})
    assert set(ordered) == {"pkg.a", "pkg.b"}
    assert set(cycles) == {"pkg.a", "pkg.b"}


def test_order_modules_no_edges_sorted() -> None:
    ordered, cycles = order_modules({"pkg.c": set(), "pkg.a": set()})
    assert ordered == ["pkg.a", "pkg.c"]
    assert cycles == ()


def test_read_module_content_strips_shebang_and_future(tmp_path: Path) -> None:
    mod = tmp_path / "m.py"
    mod.write_text(
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n"
        "import os\n",
        encoding="utf-8",
    )
    content, future, binds = read_module_content(mod, tmp_path, "pkg")
    assert future == ["from __future__ import annotations"]
    assert binds == set()
    assert "#!/usr/bin/env python3" not in content
    assert "from __future__" not in content
    assert "import os" in content


def test_strip_internal_imports_multiline_and_normal(tmp_path: Path) -> None:
    content = (
        "import os\n"
        "from . import core\n"
        "from pkg.sub import (\n"
        "    A,\n"
        "    B,\n"
        ")\n"
        "x = 1\n"
    )
    stripped = strip_internal_imports(content, "pkg")
    assert "import os" in stripped
    assert "# from . import core" in stripped
    assert "# from pkg.sub import (" in stripped
    assert "#     A," in stripped
    assert "# )" in stripped
    assert "x = 1" in stripped


# --- CLI wiring -------------------------------------------------------------


def test_cli_build_from_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from resolve_script import cli

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        '{ "name": "pkg", "version": "0.1.0", "package_dir": "pkg",'
        ' "consolidate": { "entry": "pkg/__init__.py" } }',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert cli.main(["build"]) == 0
    assert (tmp_path / "dist" / "pkg.py").is_file()


def test_cli_build_output_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from resolve_script import cli

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(
        '{ "name": "pkg", "version": "0.1.0", "package_dir": "pkg" }',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "out" / "custom.py"
    assert cli.main(["build", "--output", str(target)]) == 0
    assert target.is_file()


def test_cli_build_missing_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from resolve_script import cli

    monkeypatch.chdir(tmp_path)
    assert cli.main(["build"]) == 1


def test_cli_consolidate_manifest_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from resolve_script import cli

    pkg = write_package(tmp_path, {"__init__.py": "", "core.py": "VALUE = 2\n"})
    out = tmp_path / "single.py"
    monkeypatch.chdir(tmp_path)
    assert cli.main(["consolidate", str(pkg), "--output", str(out)]) == 0
    assert out.is_file()
    assert "VALUE = 2" in out.read_text(encoding="utf-8")
