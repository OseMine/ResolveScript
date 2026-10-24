"""Windows context menu integration for ResolveScript.

Registers "Add to Resolve Scripts" in the context menu for .py files and directories.
"""

from __future__ import annotations

import sys
import winreg

PROG = "resolvescript"
MENU_TEXT = "Add to Resolve Scripts"
ICON_PATH = ""  # Optional: path to .ico file


def _get_hkey_classes_root() -> int:
    return winreg.HKEY_CLASSES_ROOT  # type: ignore[attr-defined]


def _get_reg_sz() -> int:
    return getattr(winreg, "REG_SZ", 1)  # type: ignore[attr-defined]


def _get_create_key():
    return winreg.CreateKey  # type: ignore[attr-defined]


def _get_delete_key():
    return winreg.DeleteKey  # type: ignore[attr-defined]


def _get_set_value():
    return winreg.SetValue  # type: ignore[attr-defined]


def _get_delete_key_func():
    return winreg.DeleteKey  # type: ignore[attr-defined]


PROG = "resolvescript"
MENU_TEXT = "Add to Resolve Scripts"
ICON_PATH = ""  # Optional: path to .ico file


def register_context_menu() -> bool:
    """Register the context menu handler for .py files and directories."""
    if sys.platform != "win32":
        print("Context menu registration only available on Windows")
        return False

    try:
        # Get the resolvescript executable path
        import shutil
        resolvescript_exe = shutil.which("resolvescript")
        if not resolvescript_exe:
            print("resolvescript not found in PATH")
            return False

        # Register for .py files
        _register_file_extension(".py", resolvescript_exe)
        # Register for directories
        _register_directory(resolvescript_exe)
        print("Context menu registered successfully")
        return True
    except Exception as exc:
        print(f"Failed to register context menu: {exc}")
        return False


def unregister_context_menu() -> bool:
    """Unregister the context menu handler."""
    if sys.platform != "win32":
        print("Context menu unregistration only available on Windows")
        return False

    try:
        _unregister_file_extension(".py")
        _unregister_directory()
        print("Context menu unregistered successfully")
        return True
    except Exception as exc:
        print(f"Failed to unregister context menu: {exc}")
        return False


def _register_file_extension(ext: str, exe_path: str) -> None:
    """Register context menu for a file extension."""
    # HKEY_CLASSES_ROOT\.py\shell\resolvescript
    key_path = f"{ext}\\shell\\{PROG}"
    create_key = _get_create_key()
    hkey = _get_hkey_classes_root()
    reg_sz = _get_reg_sz()
    set_value = _get_set_value()

    with create_key(hkey, key_path) as key:
        set_value(key, "", reg_sz, MENU_TEXT)
        if ICON_PATH:
            set_value(key, "Icon", reg_sz, ICON_PATH)

    # Command subkey
    cmd_path = f"{key_path}\\command"
    with create_key(hkey, cmd_path) as key:
        set_value(key, "", reg_sz, f'{exe_path}" add "%1"')


def _unregister_file_extension(ext: str) -> None:
    """Unregister context menu for a file extension."""
    key_path = f"{ext}\\shell\\{PROG}"
    delete_key = _get_delete_key_func()
    hkey = _get_hkey_classes_root()
    try:
        delete_key(hkey, f"{key_path}\\command")
        delete_key(hkey, key_path)
    except FileNotFoundError:
        pass


def _register_directory(exe_path: str) -> None:
    """Register context menu for directories."""
    # HKEY_CLASSES_ROOT\Directory\shell\resolvescript
    key_path = f"Directory\\shell\\{PROG}"
    create_key = _get_create_key()
    hkey = _get_hkey_classes_root()
    reg_sz = _get_reg_sz()
    set_value = _get_set_value()

    with create_key(hkey, key_path) as key:
        set_value(key, "", reg_sz, MENU_TEXT)
        if ICON_PATH:
            set_value(key, "Icon", reg_sz, ICON_PATH)

    # Command subkey
    cmd_path = f"{key_path}\\command"
    with create_key(hkey, cmd_path) as key:
        set_value(key, "", reg_sz, f'{exe_path}" add "%V"')


def _unregister_directory() -> None:
    """Unregister context menu for directories."""
    key_path = f"Directory\\shell\\{PROG}"
    delete_key = _get_delete_key_func()
    hkey = _get_hkey_classes_root()
    try:
        delete_key(hkey, f"{key_path}\\command")
        delete_key(hkey, key_path)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Windows context menu integration")
    parser.add_argument("--register", action="store_true", help="Register context menu")
    parser.add_argument("--unregister", action="store_true", help="Unregister context menu")
    args = parser.parse_args()

    if args.register:
        sys.exit(0 if register_context_menu() else 1)
    elif args.unregister:
        sys.exit(0 if unregister_context_menu() else 1)
    else:
        parser.print_help()
