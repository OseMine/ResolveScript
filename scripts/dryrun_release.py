#!/usr/bin/env python
"""Local dry-run of the release pipeline.

Runs all steps that the release workflow would do, but:
- No git push
- No GitHub Release creation
- No PyPI publish
- Artifacts saved to ./release-dryrun/
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path.cwd().resolve()
DRYRUN_DIR = ROOT / "release-dryrun"
DIST_DIR = DRYRUN_DIR / "dist"


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return result."""
    print(f"\n{'='*60}")
    print(f"$ {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=cwd or ROOT, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print("SUCCESS")
    return result


def main():
    print(">>> ResolveScript Release Dry-Run")
    print(f"Working directory: {ROOT}")
    print(f"Output directory: {DRYRUN_DIR}")

    # Clean previous run
    if DRYRUN_DIR.exists():
        shutil.rmtree(DRYRUN_DIR)
    DRYRUN_DIR.mkdir(parents=True)
    DIST_DIR.mkdir(parents=True)

    # 1. Validate version
    print("\n=== Step 1: Validate version ===")
    result = run([sys.executable, "-m", "ResolveScript.cli", "--version"])
    version = result.stdout.strip().split()[-1]
    print(f"Version: {version}")

    # 2. Analyze
    print("\n=== Step 2: Analyze (static checks) ===")
    run([sys.executable, "-m", "ResolveScript.cli", "analyze"])

    # 3. Build
    print("\n=== Step 3: Build (consolidate) ===")
    run([sys.executable, "-m", "ResolveScript.cli", "build", "--output", str(DIST_DIR / f"resolvescript-{version}.py")])

    # 4. Test
    print("\n=== Step 4: Test ===")
    run([sys.executable, "-m", "ResolveScript.cli", "test", "-q", "--tb=short"])

    # 5. Package
    print("\n=== Step 5: Package ===")
    run([sys.executable, "-m", "ResolveScript.cli", "package", "--dist", str(DIST_DIR)])

    # 6. Security scan (if tools available)
    print("\n=== Step 6: Security scan ===")
    for tool in ["pip-audit", "safety", "bandit"]:
        if shutil.which(tool):
            run([tool, "."], check=False)
        else:
            print(f"  [WARN] {tool} not installed, skipping")

    # 7. Dependency check (if tools available)
    print("\n=== Step 7: Dependency check ===")
    for tool in ["pipdeptree", "pip-licenses"]:
        if shutil.which(tool):
            run([tool], check=False)
        else:
            print(f"  [WARN] {tool} not installed, skipping")

    # 8. Show artifacts
    print("\n=== Step 8: Artifacts ===")
    for f in DIST_DIR.iterdir():
        size = f.stat().st_size
        sha256 = hashlib.sha256(f.read_bytes()).hexdigest()[:16] + "..."
        print(f"  {f.name} ({size:,} bytes, SHA256: {sha256})")

    # 9. Simulate release notes
    print("\n=== Step 9: Release notes (simulated) ===")
    notes = f"""## Release {version}

### Changes
- Full release pipeline dry-run completed locally

### Artifacts
- `resolvescript-{version}.py` -- Consolidated single-file module
- `resolvescript-{version}.zip` -- Release package with SHA256SUMS.txt

### Installation
```bash
# Via resolvescript
resolvescript add resolvescript

# Or manually copy to Scripts/Utility
```
"""
    (DIST_DIR / "RELEASE_NOTES.md").write_text(notes)
    print(notes)

    print(f"\n=== Dry-run complete! Artifacts in: {DIST_DIR} ===")
    print("\nTo create actual release:")
    print(f"  git tag v{version}")
    print(f"  git push origin v{version}")
    print("  # GitHub Actions will build, test, and create release")


if __name__ == "__main__":
    main()