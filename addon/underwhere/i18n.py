"""UI text: English message ids, translated through Blender's own system.

Labels use the private context CTX, so Blender's built-in catalog (which
already translates common words such as "Keep" or "Body") never overrides the
add-on's own wording. Tooltips are looked up in the default context, so
multi-word messages are registered there as well."""
import bpy

from .core.texts_ja import JA

CTX = "UnderWhere"


def t(message, **values):
    """Translated UI text; `values` fill the {placeholders}."""
    text = bpy.app.translations.pgettext_iface(message, CTX)
    return text.format(**values) if values else text


def tip(message):
    """Translated tooltip text."""
    return bpy.app.translations.pgettext_tip(message)


def translations():
    table = {}
    for english, japanese in JA.items():
        table[(CTX, english)] = japanese
        if " " in english:  # tooltips; single words would leak into other add-ons
            table[("*", english)] = japanese
    return {"ja_JP": table}


def register():
    bpy.app.translations.register(__package__, translations())


def unregister():
    try:
        bpy.app.translations.unregister(__package__)
    except (ValueError, RuntimeError):
        pass
