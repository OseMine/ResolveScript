"""Shared pytest setup for the @NAME@ plugin.

Installs the ResolveScript plugin sandbox fixtures and puts the project
root on ``sys.path`` so ``import @NAME@`` works from ``tests/``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytest_plugins = ["ResolveScript.testing.fixtures"]