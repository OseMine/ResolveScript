"""Installer core: per-OS script roots, atomic install, registry, uninstall."""

from .discovery import default_scripts_root, resolve_scripts_root, target_dir
from .installer import (
    InstalledFile,
    InstallError,
    InstallOptions,
    InstallResult,
    discover_entrypoint,
    install_package,
    install_project,
    select_files,
    uninstall_package,
)
from .registry import (
    REGISTRY_REL,
    SCHEMA_VERSION,
    RegistryError,
    add_or_update_entry,
    get_extension,
    read_registry,
    registry_path,
    remove_entry,
    write_registry,
)

__all__ = [
    "REGISTRY_REL",
    "SCHEMA_VERSION",
    "InstallError",
    "InstallOptions",
    "InstallResult",
    "InstalledFile",
    "RegistryError",
    "add_or_update_entry",
    "default_scripts_root",
    "discover_entrypoint",
    "get_extension",
    "install_package",
    "install_project",
    "read_registry",
    "registry_path",
    "remove_entry",
    "resolve_scripts_root",
    "select_files",
    "target_dir",
    "uninstall_package",
    "write_registry",
]
