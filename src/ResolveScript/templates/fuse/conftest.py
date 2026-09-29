"""Shared pytest setup for the @NAME@ project.

Puts the project root on ``sys.path`` so ``import @NAME@`` works from
``tests/``. The mock Resolve API is not needed here — a fuse is Lua, and the
closest thing to running it is compiling it, which is what the smoke tests do.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
