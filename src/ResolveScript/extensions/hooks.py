"""Plugin lifecycle hook dispatch."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from .errors import PluginError
from .loader import load_plugin_module
from .registry import discover_plugins


def _call_hook(module: Any, hook_spec: str, *args, **kwargs) -> Any:
    """Call a hook function specified as ``module.path:function_name``."""
    if ":" not in hook_spec:
        raise PluginError(f"invalid hook spec {hook_spec!r}, expected 'module.path:function_name'")
    module_path, _, function_name = hook_spec.partition(":")
    if not module_path or not function_name:
        raise PluginError(f"invalid hook spec {hook_spec!r}, expected 'module.path:function_name'")

    # The hook module is relative to the plugin's package directory.
    # We need to add the plugin directory to sys.path for the import to work.
    plugin_path = Path(module.__file__).parent if module.__file__ else None
    if plugin_path is None:
        raise PluginError(f"could not determine plugin path for {module.__name__}")

    old_path = list(sys.path)
    sys.path.insert(0, str(plugin_path))
    try:
        hook_module = importlib.import_module(module_path)
    except ImportError as exc:
        raise PluginError(f"failed to import hook module {module_path!r}: {exc}") from exc
    finally:
        sys.path[:] = old_path

    hook_func = getattr(hook_module, function_name, None)
    if not callable(hook_func):
        raise PluginError(f"hook {hook_spec!r} not found or not callable")
    return hook_func(*args, **kwargs)


def dispatch_plugin_hooks(hook_name: str, *args, **kwargs) -> list[tuple[str, Any]]:
    """Dispatch a lifecycle hook to all loaded plugins that declare it.

    Returns a list of ``(plugin_name, result)`` for plugins that handled the hook.
    Plugins that don't declare the hook or fail to load it are skipped silently
    (errors are logged as warnings but don't crash the CLI).
    """
    results: list[tuple[str, Any]] = []
    try:
        entries = discover_plugins()
    except PluginError as exc:
        print(f"resolvescript: warning: plugin registry unavailable: {exc}", file=sys.stderr)
        return results

    for entry in entries:
        try:
            entry.manifest.check_requires()
            hook_spec = entry.manifest.hooks.get(hook_name)
            if not hook_spec:
                continue
            module = load_plugin_module(entry)
            result = _call_hook(module, hook_spec, *args, **kwargs)
            results.append((entry.name, result))
        except PluginError as exc:
            print(
                f"resolvescript: warning: plugin '{entry.name}' hook '{hook_name}' failed: {exc}",
                file=sys.stderr,
            )
        except Exception as exc:  # plugin code is third-party: never crash the CLI
            print(
                f"resolvescript: warning: plugin '{entry.name}' hook '{hook_name}' crashed: {exc}",
                file=sys.stderr,
            )
    return results
