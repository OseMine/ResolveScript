"""Shared pytest setup for the @NAME@ project.

Installs the mock DaVinciResolveScript sandbox (via the ResolveScript CLI's own
fixtures) and puts the project root on ``sys.path`` so ``import @NAME@`` works
from ``tests/``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest_plugins = ["resolve_script.testing.fixtures"]