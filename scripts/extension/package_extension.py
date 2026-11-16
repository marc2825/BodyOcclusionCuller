#!/usr/bin/env python3
"""Use Blender's official validator and builder; no homebrew fallback ZIP."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import zipfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blender", default=os.environ.get("BLENDER"), required=not os.environ.get("BLENDER"))
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "addon/underwhere/blender_manifest.toml").read_text())["version"]
    package = ROOT / "dist" / f"underwhere-{version}.zip"
    (ROOT / "dist").mkdir(exist_ok=True)
    for arguments in [
        ["validate", "addon/underwhere"],
        ["build", "--source-dir", "addon/underwhere", "--output-dir", "dist"],
        ["validate", str(package.relative_to(ROOT))],
    ]:
        subprocess.run([args.blender, "--command", "extension", *arguments],
                       cwd=ROOT, check=True)
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        assert "blender_manifest.toml" in names and "__init__.py" in names
        assert not any(n.endswith((".pyc", ".blend", ".vrm", ".fbx")) or
                       n.startswith("tests/") for n in names)
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    package.with_suffix(".zip.sha256").write_text(f"{checksum}  {package.name}\n")
    print(f"Built and validated {package} ({len(names)} files); SHA256 {checksum}")


if __name__ == "__main__":
    main()
