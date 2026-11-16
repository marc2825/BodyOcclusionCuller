#!/usr/bin/env python3
"""Run the unit tests and, with --blender, the Blender integration tests."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", default=os.environ.get("BLENDER"))
    parser.add_argument("--python-only", action="store_true")
    args = parser.parse_args()
    commands = [[sys.executable, "-m", "unittest", "discover", "-s", "tests/extension",
                 "-p", "test_*.py", "-v"]]
    if not args.python_only:
        if not args.blender:
            parser.error("--blender is required; use --python-only to explicitly skip Blender")
        commands.append([args.blender, "--background", "--factory-startup", "--offline-mode",
                         "--python-exit-code", "1", "--python",
                         "tests/extension/blender_integration.py"])
    for command in commands:
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
