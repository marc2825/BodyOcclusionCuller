"""UnderWhere: find and hide body faces covered by clothing."""

from pathlib import Path
import tomllib

# The manifest is the sole version authority, including installed packages.
VERSION = tomllib.loads(Path(__file__).with_name("blender_manifest.toml").read_text(
    encoding="utf-8"))["version"]


def register():
    from . import ui
    ui.register()


def unregister():
    from . import ui
    ui.unregister()
