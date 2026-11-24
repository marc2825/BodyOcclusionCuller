"""UnderWhere: find and hide body faces covered by clothing."""

from pathlib import Path
import tomllib

# The manifest is the sole version authority, including installed packages.
VERSION = tomllib.loads(Path(__file__).with_name("blender_manifest.toml").read_text(
    encoding="utf-8"))["version"]


def register():
    from . import i18n, ui
    i18n.register()
    try:
        ui.register()
    except Exception:
        i18n.unregister()
        raise


def unregister():
    from . import i18n, ui
    ui.unregister()
    i18n.unregister()
