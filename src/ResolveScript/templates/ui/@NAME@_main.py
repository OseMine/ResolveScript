#!/usr/bin/env python3
"""In-app entry script for @NAME@.

This file is copied to the Resolve Scripts directory during installation
and serves as the entry point when running from Resolve's script menu.

It imports and runs the main() function from the package.
"""

import sys
from pathlib import Path

# Ensure the package can be imported when running from Resolve's script directory
# The package is installed alongside this file in the Scripts directory
sys.path.insert(0, str(Path(__file__).parent))

try:
    from @NAME@.main import main
except ImportError as exc:
    print(f"Failed to import @NAME@: {exc}", file=sys.stderr)
    sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())