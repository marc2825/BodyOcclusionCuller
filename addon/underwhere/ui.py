"""Sidebar panels and undoable operators.

The sidebar follows three steps: Set up (Body, clothing, analyze), Review
(result, next steps, decide unsure faces) and Export. Every visible string is
an English message id translated with i18n.t()."""
from collections import Counter
import json
import re
import time

import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
    IntProperty, PointerProperty, StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup, UIList
from bpy_extras.io_utils import ExportHelper
from mathutils import Vector

from . import blender_adapter as adapter, workflow
from .core.contracts import (
    CANDIDATE, KEEP, REVIEW, RESTORE_EXPOSED, RESTORE_UNRESOLVED, UNCERTAIN, UNSAFE,
    existing_mask_warning,
)
from .i18n import CTX, t, tip

JOBS = []
PRESET_APPLY = set()
HISTORY_CANCELLED_SCENES = set()

REASON_LABELS = {
    "EXPOSURE_WITNESS": "Seen along a sampled ray",
    "ALL_REQUIRED_FINITE_SAMPLES_OCCLUDED": "Hidden in every sample",
    "SURFACE_INTERSECTION": "Body and clothing intersect",
    "CONTACT_OR_DEPTH_TIE": "Touching the clothing, or depth unclear",
    "OCCLUDER_TOPOLOGY_AMBIGUITY": "Clothing shape could not be resolved",
    "OPENING_BUDGET_EXCEEDED": "Clothing has too many openings",
    "NONMANIFOLD_OCCLUDER": "Clothing mesh is non-manifold",
    "SOLIDIFY_OPENING_UNRESOLVED": "Opening in Solidify clothing",
    "SPATIAL_COVER_INCOMPLETE_OR_DEGENERATE": "Sampling too coarse, or a degenerate face",
    "ALPHA_OR_TRANSMISSION_UNTRUSTED": "Material may be see-through",
    "UNSUPPORTED_SHADER": "Shader not supported",
    "MISSING_MATERIAL": "Clothing has no material",
    "NODE_SURFACE_REQUIRED": "Material needs a node surface",
    "ANIMATED_MATERIAL_UNSUPPORTED": "Material is animated",
    "BACKFACE_CULLING_UNTRUSTED": "Backface culling is on",
    "NO_COMPLETE_EVIDENCE": "Not enough evidence",
    REVIEW: "Unsure", KEEP: "Visible", CANDIDATE: "Hideable",
    UNSAFE: "Mask hides a visible face",
    UNCERTAIN: "Mask hides an unsure face",
    "EXISTING_MASK_DISABLED": "The existing mask is turned off",
    "EXISTING_MASK_HIDES_NOTHING": "The existing mask hides nothing",
    "EXISTING_MASK_HIDES_EVERYTHING": "The existing mask hides every face (check Invert)",
}

# One-line next step for each reason a face is unsure.
_OPAQUE_HINT = "If it is fully opaque, mark it Opaque and analyze again"
_LOOK_HINT = "Look at it, and choose Hide if it is covered"
_FIT_HINT = "Fix the fit or weights; choose Hide only to hide poke-through"
REASON_HINTS = {
    "ALPHA_OR_TRANSMISSION_UNTRUSTED": _OPAQUE_HINT,
    "UNSUPPORTED_SHADER": _OPAQUE_HINT,
    "NODE_SURFACE_REQUIRED": _OPAQUE_HINT,
    "MISSING_MATERIAL": "Give the clothing a material and analyze again",
    "ANIMATED_MATERIAL_UNSUPPORTED": _LOOK_HINT,
    "BACKFACE_CULLING_UNTRUSTED": "Turn culling off and analyze again, or decide by eye",
    "SURFACE_INTERSECTION": _FIT_HINT,
    "CONTACT_OR_DEPTH_TIE": _FIT_HINT,
    "OCCLUDER_TOPOLOGY_AMBIGUITY": "Fix the named clothing mesh, or decide by eye",
    "SOLIDIFY_OPENING_UNRESOLVED": _LOOK_HINT,
    "SPATIAL_COVER_INCOMPLETE_OR_DEGENERATE":
        "Choose Fine and analyze again; if every face shows this, check the Body's scale",
    "NO_COMPLETE_EVIDENCE": _LOOK_HINT,
}
#: Reason codes that describe evidence rather than a cause to act on.
INFORMATIONAL_REASONS = {"EXPOSURE_WITNESS", "ALL_REQUIRED_FINITE_SAMPLES_OCCLUDED"}

#: How an error code reads to a person: what happened and how to fix it.
#: {name} is the object named in the message, {detail} the whole message.
ERROR_TEXT = {
    "OBJECT_MODE_REQUIRED": "Switch to Object Mode first.",
    "BODY_MESH_REQUIRED": "Choose a mesh as the Body.",
    "BODY_PART_REQUIRED": "Remove the empty entries from the Body parts.",
    "OCCLUDER_MESH_REQUIRED": "Add at least one clothing mesh, and remove empty entries.",
    "DUPLICATE_OBJECT": "An object is listed twice. The Body and its parts cannot also be clothing.",
    "MULTI_BODY_AUDIT_UNSUPPORTED": "Checking an existing mask works on one Body object at a time.",
    "EMPTY_OR_NON_MESH": "{name} is not a mesh with faces.",
    "LINKED_OR_READ_ONLY": "{name} is linked or read-only. Make a local copy first.",
    "HIDDEN_INPUT": "{name} is hidden. Show it in this view layer.",
    "RENDER_HIDDEN_INPUT": "{name} is hidden in renders. Turn rendering on for it.",
    "CAMERA_VISIBILITY_UNTRUSTED": "{name} is invisible to the camera, a holdout or a shadow catcher.",
    "COLLECTION_VISIBILITY_UNTRUSTED": "A collection of {name} is excluded from rendering, a holdout or indirect only.",
    "INSTANCING_UNSUPPORTED": "{name} uses instancing, which is not supported.",
    "SINGULAR_TRANSFORM": "{name} has a zero or flattened scale. Fix the scale, or apply it (Ctrl+A > Scale) on a working copy.",
    "MASK_REQUIRED": "Choose the vertex-group Mask modifier to check.",
    "SMOOTH_MASK_UNSUPPORTED": "Turn off Smooth on the Mask modifier, on a working copy.",
    "MASK_GROUP_MISSING": "The vertex group of the Mask modifier is missing.",
    "MASK_VISIBILITY_MISMATCH": "Give the Mask modifier the same viewport and render visibility.",
    "MASK_MUST_BE_LAST": "Move the Mask modifier to the bottom of the stack.",
    "MODIFIER_UNSUPPORTED": "The modifier {name} is not supported. Use a working copy with it applied.",
    "MODIFIER_VISIBILITY_MISMATCH": "The modifier {name} has different viewport and render visibility.",
    "TOPOLOGY_CORRESPONDENCE_FAILED": "{name} changes its faces when evaluated. Use a working copy with its modifiers applied.",
    "EMPTY_EVALUATED_MESH": "{name} has no faces after its modifiers.",
    "NONFINITE_GEOMETRY": "{name} has invalid vertex positions.",
    "MASK_EVALUATION_MISMATCH": "Blender's result did not match the plan, so nothing was changed. Please report this.",
    "OUTPUT_EVALUATION_MISMATCH": "Blender's result did not match the plan, so nothing was changed. Please report this.",
    "DELETED_COPY_EVALUATION_MISMATCH": "Blender's result did not match the plan, so nothing was changed. Please report this.",
    "FRAMES_REQUIRED": "Enter the frames as numbers separated by commas, for example 1, 10, 20.",
    "FRAME_LIMIT": "Choose between 1 and 32 valid frames.",
    "STATE_TOPOLOGY_OR_MASK_CHANGED": "The Body's faces or the existing mask change between frames, which is not supported.",
    "INPUT_CHANGED_DURING_ANALYSIS": "Something changed during the analysis. Analyze again.",
    "ANALYSIS_ALREADY_RUNNING": "An analysis is already running.",
    "ANALYSIS_REQUIRED": "Analyze first.",
    "EDIT_MODE_ELSEWHERE": "Leave Edit Mode on {name} first (Tab).",
    "OTHER_MODE_ELSEWHERE": "Switch {name} back to Object Mode first.",
}


def reason_label(code):
    return t(REASON_LABELS.get(code, code))


def reason_hint(code):
    hint = REASON_HINTS.get(code)
    return None if hint is None else t(hint)


BREAK_AFTER = "、。）」』！？・ "
NO_LINE_START = "、。）」』！？ー"


def wrap(text, width=None):
    """Split text into sidebar-width lines (labels never wrap by themselves)."""
    cjk = any(ord(character) > 0x2E7F for character in text)
    width = width or (21 if cjk else 40)
    if cjk:
        lines = []
        while len(text) > width:
            low = max(1, width - 8)
            after = [text.rfind(mark, low, width) + 1 for mark in BREAK_AFTER]
            before = [text.rfind(mark, low, width) for mark in "「『（"]  # break before an opening bracket
            cut = max([position for position in after + before if position > 1], default=width)
            if text[cut - 1] in "「『（":
                cut -= 1
            while cut < len(text) and text[cut] in NO_LINE_START:
                cut += 1
            lines.append(text[:cut])
            text = text[cut:]
        return lines + [text] if text else (lines or [""])
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return lines + [line] if line else (lines or [""])


def describe_message(text):
    """A stored status or error message, as a sentence for people."""
    if text.startswith("STALE"):
        return t(stale_explanation(text)[0]) + " " + t("Analyze again to continue.")
    match = re.match(r"^([A-Z][A-Z0-9_]+)(?::\s*(.*))?$", text, re.S)
    if match and match.group(1) in ERROR_TEXT:
        code, detail = match.group(1), match.group(2) or ""
        name = detail.split(";")[0].strip()
        return t(ERROR_TEXT[code], name=name, detail=detail) + f" ({code})"
    return t(text)


def review_reason_counts(report):
    counts = {}
    for face in report["faces"]:
        if face["verdict"] == REVIEW or face["finding"]:
            for code in face["reason_codes"]:
                if code not in INFORMATIONAL_REASONS:
                    counts[code] = counts.get(code, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def editing_comparison(context):
    return (context.mode == 'EDIT_MESH' and context.edit_object is not None
            and adapter.is_preview(context.edit_object))


def leave_other_edit_mode_message(context):
    return f"EDIT_MODE_ELSEWHERE: {context.edit_object.name}"


def start_comparison_selection(context, obj, *, clear=True):
    """Enter face-select Edit Mode on the comparison mesh.

    With clear=False the faces selected there before are kept (used to resume
    after a failed Keep / Hide)."""
    import bmesh
    if context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for other in context.selected_objects:
        other.select_set(False)
    obj.hide_select = False
    obj.select_set(True)
    context.view_layer.objects.active = obj
    context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.object.mode_set(mode='EDIT')
    if clear:
        mesh = bmesh.from_edit_mesh(obj.data)
        for element in list(mesh.verts) + list(mesh.edges) + list(mesh.faces):
            element.select_set(False)
        bmesh.update_edit_mesh(obj.data)


def editing_body(context, settings):
    return (context.mode == 'EDIT_MESH' and context.edit_object is not None
            and context.edit_object in adapter.body_objects(settings))


def body_layout(settings):
    """(object, first face index) for each Body object, matching the current result."""
    bodies = adapter.body_objects(settings)
    parts = adapter.body_parts(workflow.read_report(settings))
    if len(parts) != len(bodies) or any(obj is None or len(obj.data.polygons) != part["face_count"]
                                        for obj, part in zip(bodies, parts)):
        raise adapter.InputError("STALE: Body objects changed; Analyze again")
    return [(obj, part["face_offset"]) for obj, part in zip(bodies, parts)]


def face_caption(report, index):
    """'Face 12', or 'Head face 12' when the Body has several objects."""
    parts = adapter.body_parts(report)
    if len(parts) > 1:
        for part in parts:
            if part["face_offset"] <= index < part["face_offset"] + part["face_count"]:
                return t("{part} face {index}", part=part["name"], index=index - part["face_offset"])
    return t("Face {index}", index=index)


def comparison_filter(settings):
    return set(settings.preview_show) if settings.preview_mode == 'CLASSIFY' else None


def draw_comparison(context, settings, report):
    return adapter.preview(context, report, settings.preview_mode, show=comparison_filter(settings))


def preview_filter_changed(self, context):
    scene = getattr(context, "scene", None)
    if scene is None or self.preview_mode != 'CLASSIFY' or adapter.current_preview(scene) is None:
        return
    try:
        was_selecting = editing_comparison(context)
        if was_selecting:
            bpy.ops.object.mode_set(mode='OBJECT')
        obj = draw_comparison(context, self, workflow.fresh_report(context, self, verify=False))
        if was_selecting and obj is not None:
            start_comparison_selection(context, obj)
    except Exception as exc:  # A property update cannot report; show it in the status box.
        self.status = str(exc)


def select_body_faces(context, settings, indices):
    """Select exactly `indices` (result face indices) on the Body objects in Edit Mode."""
    import bmesh
    layout = body_layout(settings)
    objects = [obj for obj, _ in layout]
    if context.mode == 'EDIT_MESH':
        # Leaving the comparison is harmless; any other mesh may hold user edits.
        if context.edit_object not in objects and not editing_comparison(context):
            raise adapter.InputError(leave_other_edit_mode_message(context))
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = objects[0]
    context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.object.mode_set(mode='EDIT')  # Several selected meshes enter Edit Mode together.
    wanted = set(indices)
    for obj, offset in layout:
        mesh = bmesh.from_edit_mesh(obj.data)
        for element in list(mesh.verts) + list(mesh.edges) + list(mesh.faces):
            element.select_set(False)
        for face in mesh.faces:
            if offset + face.index in wanted:
                face.select_set(True)
        mesh.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)
    if context.space_data and context.space_data.type == 'VIEW_3D' and indices:
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if region:
            with context.temp_override(region=region):
                bpy.ops.view3d.view_selected(use_all_regions=False)


def input_changed(self, context):
    if context and context.scene:
        workflow.DIRTY.add(workflow.scene_key(context.scene))


def preset_changed(self, context):
    if self.preset != 'CUSTOM':
        PRESET_APPLY.add(self.as_pointer())
        try:
            self.spatial_step, self.angle = {
                'QUICK': (0.1, 60.0), 'BALANCED': (0.05, 45.0), 'DETAILED': (0.025, 30.0),
            }[self.preset]
        finally:
            PRESET_APPLY.discard(self.as_pointer())
    input_changed(self, context)


def budget_changed(self, context):
    if self.as_pointer() not in PRESET_APPLY:
        self.preset = 'CUSTOM'
    input_changed(self, context)


def mesh_poll(self, obj):
    return obj.type == 'MESH' and not adapter.is_preview(obj)


class UNDERWHERE_Issue(PropertyGroup):
    face: IntProperty()
    label: StringProperty()


def issue_changed(self, context):
    if 0 <= self.issue_index < len(self.issues):
        self.face_index = self.issues[self.issue_index].face


class UNDERWHERE_Occluder(PropertyGroup):
    object: PointerProperty(type=bpy.types.Object, poll=mesh_poll, update=input_changed)


STEPS = [
    ('SETUP', "Set up", "Choose the Body and its clothing, then analyze"),
    ('REVIEW', "Review", "See the result and decide the unsure faces"),
    ('EXPORT', "Export", "Create the output copy"),
]


class UNDERWHERE_Settings(PropertyGroup):
    body: PointerProperty(name="Body", type=bpy.types.Object, poll=mesh_poll, update=input_changed,
                          description="The avatar's body mesh. It is never changed",
                          translation_context=CTX)
    use_extra_bodies: BoolProperty(
        name="Body has several objects", update=input_changed, translation_context=CTX,
        description="Also inspect separate Body objects such as a head; each gets its own output copy. "
                    "Body objects do not hide each other, only the clothing does")
    extra_bodies: CollectionProperty(type=UNDERWHERE_Occluder)
    extra_body_index: IntProperty(default=0)
    occluders: CollectionProperty(type=UNDERWHERE_Occluder)
    occluder_index: IntProperty(default=0)
    mode: EnumProperty(name="Purpose", translation_context=CTX, items=[
        ('GENERATE', "Find hideable faces", "Find the Body faces that the clothing covers"),
        ('AUDIT', "Check an existing mask", "Check a vertex-group Mask modifier that already hides faces"),
    ], update=input_changed)
    existing_mask: StringProperty(name="Existing mask", update=input_changed, translation_context=CTX)
    scope: EnumProperty(name="Poses", translation_context=CTX, items=[
        ('CURRENT_POSE_ONLY', "Current pose", "Inspect only the pose on the current frame"),
        ('EXPLICIT_FRAMES', "Current pose and listed frames",
         "Also inspect the listed frames. A face is hideable only if every inspected frame hides it; "
         "poses between frames are not checked"),
    ], update=input_changed)
    frames: StringProperty(name="Frames", default="1, 10, 20", update=input_changed, translation_context=CTX,
                           description="Frame numbers separated by commas")
    issues: CollectionProperty(type=UNDERWHERE_Issue)
    issue_index: IntProperty(update=issue_changed)
    preset: EnumProperty(name="Detail", translation_context=CTX, items=[
        ('QUICK', "Fast", "Coarse sampling for a quick first look"),
        ('BALANCED', "Standard", "Recommended sampling"),
        ('DETAILED', "Fine", "Finer sampling; slower"),
        ('CUSTOM', "Custom", "Your own sampling values"),
    ], default='BALANCED', update=preset_changed)
    spatial_step: FloatProperty(name="Sample spacing (metres)", default=0.05, translation_context=CTX,
                                min=0.00001, max=100.0, update=budget_changed)
    angle: FloatProperty(name="Direction step (degrees)", default=45.0, min=15.0, translation_context=CTX,
                        max=90.0, update=budget_changed)
    touch_tolerance: FloatProperty(name="Contact tolerance (metres)", default=0.00001, translation_context=CTX,
                                  min=0.0000001, max=0.01, precision=7, update=budget_changed)
    advanced: BoolProperty(name="Advanced")
    status: StringProperty(default="Choose Body and occluders")
    #: Preflight details for the status box (JSON, this session only).
    notice: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})
    # Compatibility field name; contains only a small session revision reference.
    result_json: StringProperty(options={'HIDDEN'})
    #: Your Keep / Hide choices, saved with the file and restored when the faces match.
    saved_choices: StringProperty(options={'HIDDEN'})
    progress: FloatProperty(min=0.0, max=1.0, subtype='FACTOR', options={'SKIP_SAVE'})
    cancel_requested: BoolProperty(options={'SKIP_SAVE'})
    ui_step: EnumProperty(name="Step", items=STEPS, default='SETUP', translation_context=CTX)
    face_index: IntProperty(name="Face", min=0, translation_context=CTX)
    selection_target: EnumProperty(name="Select on", translation_context=CTX, items=[
        ('COMPARISON', "Comparison", "Select on the coloured copy beside the Body"),
        ('BODY', "Body", "Select on the Body itself"),
    ], default='COMPARISON')
    override_review_only: BoolProperty(
        name="Only change unsure faces", default=True, translation_context=CTX,
        description="Keep and Hide change only the unsure faces in your selection (and faces an existing mask "
                    "hides wrongly), so a rough selection never changes decided faces")
    preview_mode: EnumProperty(name="Show", translation_context=CTX, items=[
        ('CLASSIFY', "Verdicts", "Colour each face by its verdict"),
        ('ORIGINAL', "Without mask", "Show the Body without any mask"),
        ('OUTPUT', "After output", "Show the Body as the output will look"),
        ('DIFF', "Before / After", "Colour faces by how the output changes the existing mask"),
        ('POSES', "Poses", "Colour faces by the share of inspected frames that hide them"),
        ('OFF', "Off", "Remove the coloured copy"),
    ], default='CLASSIFY')
    preview_show: EnumProperty(name="Colours shown", options={'ENUM_FLAG'}, translation_context=CTX, items=[
        ('HIDE_CANDIDATE', "Hideable", "Show hideable faces"),
        ('KEEP_EXPOSED', "Visible", "Show faces seen in an inspected pose"),
        ('REVIEW', "Unsure", "Show unsure faces"),
        ('UNSAFE_EXISTING_MASK', "Mask hides visible", "Show visible faces that the existing mask hides"),
        ('UNCERTAIN_EXISTING_MASK', "Mask hides unsure", "Show unsure faces that the existing mask hides"),
        ('MANUAL_HIDE', "Hidden by you", "Show faces you chose to hide"),
        ('MANUAL_KEEP', "Kept by you", "Show faces you chose to keep"),
    ], default={'HIDE_CANDIDATE', 'KEEP_EXPOSED', 'REVIEW', 'UNSAFE_EXISTING_MASK',
                'UNCERTAIN_EXISTING_MASK', 'MANUAL_HIDE', 'MANUAL_KEEP'},
        update=preview_filter_changed)


class SafeOperator:
    bl_translation_context = CTX

    def fail(self, context, exc):
        context.scene.underwhere.status = str(exc)
        self.report({'ERROR'}, describe_message(str(exc)))
        return {'CANCELLED'}

    def available(self, context):
        if workflow.scene_key(context.scene) in workflow.BUSY:
            raise adapter.InputError("Wait for the analysis to finish, or cancel it.")
        migrate_settings(context.scene)


def after_analysis(context, settings):
    """Show the result right away: move to Review and draw the coloured copy."""
    settings.ui_step = 'REVIEW'
    if settings.preview_mode == 'OFF':
        return
    try:
        draw_comparison(context, settings, workflow.read_report(settings))
    except Exception as exc:  # The comparison is a convenience; the result itself stands.
        settings.status = str(exc)


class UNDERWHERE_OT_setup(SafeOperator, Operator):
    bl_idname = "underwhere.use_selection"
    bl_label = "Use selection"
    bl_description = "Set the active mesh as the Body and the other selected meshes as clothing. Select the Body last"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            self.available(context)
            body = context.active_object
            if body is None or not mesh_poll(None, body):
                raise adapter.InputError("Select the Body last, so that it is the active mesh.")
            s = context.scene.underwhere
            s.body = body
            s.occluders.clear()
            parts = set(adapter.body_objects(s)[1:])
            for obj in context.selected_objects:
                if obj != body and obj not in parts and mesh_poll(None, obj):
                    s.occluders.add().object = obj
            s.ui_step = 'SETUP'
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_occluder(SafeOperator, Operator):
    bl_idname = "underwhere.occluder"
    bl_label = "Edit clothing list"
    bl_description = "Add a clothing slot, or remove the chosen one"
    bl_options = {'REGISTER', 'UNDO'}
    remove: BoolProperty()

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            if self.remove:
                if 0 <= s.occluder_index < len(s.occluders):
                    s.occluders.remove(s.occluder_index)
                    s.occluder_index = max(0, min(s.occluder_index, len(s.occluders) - 1))
            else:
                s.occluders.add()
            input_changed(s, context)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_body_part(SafeOperator, Operator):
    bl_idname = "underwhere.body_part"
    bl_label = "Edit Body parts"
    bl_description = ("Add the selected meshes that are not used yet (or an empty slot) as Body parts, "
                      "or remove the chosen one")
    bl_options = {'REGISTER', 'UNDO'}
    remove: BoolProperty()

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            if self.remove:
                if 0 <= s.extra_body_index < len(s.extra_bodies):
                    s.extra_bodies.remove(s.extra_body_index)
                    s.extra_body_index = max(0, min(s.extra_body_index, len(s.extra_bodies) - 1))
            else:
                used = set(adapter.body_objects(s)) | {item.object for item in s.occluders}
                fresh = [obj for obj in context.selected_objects
                         if obj not in used and mesh_poll(None, obj)]
                for obj in fresh or [None]:
                    s.extra_bodies.add().object = obj
                s.extra_body_index = len(s.extra_bodies) - 1
            input_changed(s, context)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_preflight(SafeOperator, Operator):
    bl_idname = "underwhere.preflight"
    bl_label = "Check inputs"
    bl_description = "Check the Body, clothing, modifiers and materials without analyzing"

    def execute(self, context):
        key = workflow.scene_key(context.scene)
        try:
            self.available(context)
            workflow.BUSY.add(key)
            s = context.scene.underwhere
            state, _ = adapter.snapshot(context, s)
            verdicts = Counter(m["verdict"] for o in state["occluders"] for m in o["materials"]
                               if m["verdict"] not in TRUSTED_MATERIALS)
            notice = {
                "size": state["body_size_metres"], "factor": state["settings"]["scale_normalization"],
                "untrusted": dict(verdicts.most_common(3)),
                "untrusted_total": sum(verdicts.values()) + sum(not o["materials"] for o in state["occluders"]),
                "mask_warning": existing_mask_warning(s.mode, state["existing_mask"],
                                                      len(state["body"]["polygons"])),
            }
            s.notice = json.dumps(notice)
            s.status = "Preflight OK"
            lines = preflight_lines(notice)
            self.report({'WARNING'} if notice["untrusted_total"] or notice["mask_warning"] else {'INFO'},
                        " ".join(lines))
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)
        finally:
            workflow.BUSY.discard(key)


class UNDERWHERE_OT_analyze(SafeOperator, Operator):
    bl_idname = "underwhere.analyze"
    bl_label = "Analyze"
    bl_description = "Find the Body faces that the clothing covers. Press Esc over this view, or Cancel, to stop"
    bl_options = {'REGISTER', 'UNDO'}
    _iterator = None
    _timer = None

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            workflow.run_sync(context, s)
            after_analysis(context, s)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)

    def invoke(self, context, event):
        if bpy.app.background:
            return self.execute(context)
        self._cleaned = False
        try:
            self.available(context)
            self._scene = context.scene
            self._key = workflow.scene_key(self._scene)
            self._area = context.area
            self._window = context.window
            self._wm = context.window_manager
            s = self._scene.underwhere
            s.cancel_requested = False
            self._iterator, self._elapsed = workflow.start(context, s)
            self._token = time.monotonic_ns()
            workflow.MODAL_OWNERS[self._key] = self._token
            self._timer = self._wm.event_timer_add(0.03, window=context.window)
            self._wm.modal_handler_add(self)
            JOBS.append(self)
            return {'RUNNING_MODAL'}
        except Exception as exc:
            self.cleanup()
            return self.fail(context, exc)

    def cleanup(self):
        if getattr(self, '_cleaned', False):
            return
        self._cleaned = True
        try:
            if self._iterator:
                self._iterator.close()
        except (ReferenceError, RuntimeError):
            pass
        finally:
            self._iterator = None
            if self._timer:
                try:
                    self._wm.event_timer_remove(self._timer)
                except (ReferenceError, RuntimeError):
                    pass
                self._timer = None
            key = getattr(self, '_key', None)
            if workflow.MODAL_OWNERS.get(key) == getattr(self, '_token', None):
                workflow.MODAL_OWNERS.pop(key, None)
                workflow.BUSY.discard(key)
            if self in JOBS:
                JOBS.remove(self)

    def cancel(self, context):
        self.cleanup()

    def modal(self, context, event):
        try:
            if self._iterator is None:
                self.cleanup()
                return {'CANCELLED'}
            s = self._scene.underwhere
            local_escape = (event.type == 'ESC' and context.window == self._window
                            and self._area.x <= event.mouse_x < self._area.x + self._area.width
                            and self._area.y <= event.mouse_y < self._area.y + self._area.height)
            if local_escape or s.cancel_requested or context.scene != self._scene:
                self.cleanup()
                s.status = "Cancelled; source unchanged"
                return {'CANCELLED'}
            if event.type != 'TIMER':
                return {'PASS_THROUGH'}
            deadline = time.perf_counter() + 0.025
            while time.perf_counter() < deadline:
                try:
                    step = next(self._iterator)
                except StopIteration as done:
                    workflow.finish(context, s, done.value, self._elapsed)
                    self.cleanup()
                    after_analysis(context, s)
                    return {'FINISHED'}
                s.status = step["stage"]
                s.progress = step["progress"]
            if context.area:
                context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        except Exception as exc:
            self.cleanup()
            try:
                return self.fail(context, exc)
            except ReferenceError:
                return {'CANCELLED'}


class UNDERWHERE_OT_cancel(Operator):
    bl_idname = "underwhere.cancel"
    bl_label = "Cancel"
    bl_description = "Stop the analysis. Nothing is changed"
    bl_translation_context = CTX

    def execute(self, context):
        context.scene.underwhere.cancel_requested = True
        return {'FINISHED'}


class UNDERWHERE_OT_preview(SafeOperator, Operator):
    bl_idname = "underwhere.preview"
    bl_label = "Update comparison"
    bl_description = "Redraw the coloured copy beside the Body"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            was_selecting = editing_comparison(context)
            if was_selecting:
                # clear_preview never removes a mesh in Edit Mode.
                bpy.ops.object.mode_set(mode='OBJECT')
            if s.preview_mode == 'OFF':
                adapter.clear_preview(context.scene)
            else:
                report = workflow.fresh_report(context, s)
                obj = draw_comparison(context, s, report)
                if was_selecting and obj is not None:
                    start_comparison_selection(context, obj)
            return {'FINISHED'}
        except Exception as exc:
            adapter.clear_preview(context.scene)
            return self.fail(context, exc)


class UNDERWHERE_OT_face(SafeOperator, Operator):
    bl_idname = "underwhere.face"
    bl_label = "Inspect face"
    bl_description = "Select a face on the Body, go to the next unsure face, or look along the ray that saw it"
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(translation_context=CTX, items=[('SELECT', "Select", ""), ('NEXT', "Next", ""),
                                                         ('VIEW', "View ray", "")])

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            report = workflow.fresh_report(context, s, verify=False)
            if self.action == 'NEXT':
                count = len(report["faces"])
                for offset in range(1, count + 1):
                    index = (s.face_index + offset) % count
                    if report["faces"][index]["finding"] or report["faces"][index]["verdict"] == REVIEW:
                        s.face_index = index
                        break
            face = report["faces"][min(s.face_index, len(report["faces"]) - 1)]
            if self.action == 'VIEW':
                if not face["witness"]:
                    raise adapter.InputError("No ray was recorded for this face.")
                if context.space_data.type != 'VIEW_3D':
                    raise adapter.InputError("Use View ray from a 3D View.")
                witness = face["witness"]
                if (context.scene.frame_current, context.scene.frame_subframe) != (
                        witness['frame'], witness['subframe']):
                    context.scene.frame_set(witness['frame'], subframe=witness['subframe'])
                view = context.space_data.region_3d
                view.view_location = Vector(witness["point"])
                view.view_rotation = Vector(witness["direction"]).to_track_quat('Z', 'Y')
                view.view_distance = max(report['input']['settings']['r'] * 10, 0.1)
                view.view_perspective = 'ORTHO'
            else:
                select_body_faces(context, s, [face["face"]])
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


def review_faces_only(report, indices):
    faces = report["faces"]
    return [i for i in indices
            if 0 <= i < len(faces) and (faces[i]["verdict"] == REVIEW or faces[i]["finding"])]


SELECTION_TOOLS = {
    'BOX': "builtin.select_box",
    'LASSO': "builtin.select_lasso",
    'CIRCLE': "builtin.select_circle",
}


def selecting_on(context, settings):
    """'COMPARISON' or 'BODY' while faces are being chosen there, else None."""
    if context.mode != 'EDIT_MESH' or context.edit_object is None:
        return None
    if adapter.is_preview(context.edit_object):
        return 'COMPARISON'
    return 'BODY' if context.edit_object in adapter.body_objects(settings) else None


def active_selection_tool(context):
    """'BOX', 'LASSO' or 'CIRCLE' when that tool is active in the 3D View, else None."""
    try:
        tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
    except (AttributeError, TypeError, RuntimeError):
        return None
    idname = getattr(tool, "idname", None)
    return next((key for key, value in SELECTION_TOOLS.items() if value == idname), None)


class UNDERWHERE_OT_edit_selection(SafeOperator, Operator):
    bl_idname = "underwhere.edit_selection"
    bl_label = "Select faces"
    bl_description = ("Start selecting faces with this tool, on the coloured copy or on the Body. "
                      "Switching tools keeps the selection")
    bl_options = {'REGISTER', 'UNDO'}
    target: EnumProperty(translation_context=CTX, items=[
        ('COMPARISON', "Comparison", "Select on the coloured copy beside the Body"),
        ('BODY', "Body", "Select on the Body itself"),
    ])
    tool: EnumProperty(translation_context=CTX, items=[
        ('NONE', "Current tool", "Keep the active selection tool"),
        ('BOX', "Box", "Drag a rectangle"),
        ('LASSO', "Lasso", "Draw a free-form outline"),
        ('CIRCLE', "Brush", "Paint over faces with a circle brush (the mouse wheel changes its size)"),
    ], default='NONE')

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            workflow.fresh_report(context, s, verify=False)
            if self.target == 'BODY':
                if not editing_body(context, s):
                    select_body_faces(context, s, [])
            else:
                obj = adapter.current_preview(context.scene)
                if obj is None:
                    # Show the comparison instead of asking for another click.
                    if context.mode == 'EDIT_MESH' and not editing_body(context, s):
                        raise adapter.InputError(leave_other_edit_mode_message(context))
                    if s.preview_mode == 'OFF':
                        s.preview_mode = 'CLASSIFY'
                    obj = draw_comparison(context, s, workflow.fresh_report(context, s))
                if context.edit_object != obj:
                    if context.mode == 'EDIT_MESH' and not editing_body(context, s) \
                            and not editing_comparison(context):
                        raise adapter.InputError(leave_other_edit_mode_message(context))
                    start_comparison_selection(context, obj)
            if self.tool != 'NONE' and context.area and context.area.type == 'VIEW_3D':
                bpy.ops.wm.tool_set_by_id(name=SELECTION_TOOLS[self.tool])
            self.report({'INFO'}, t("Drag over faces. Shift adds, Ctrl removes. Then choose Keep or Hide."))
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_finish_selection(Operator):
    bl_idname = "underwhere.finish_selection"
    bl_label = "Done"
    bl_description = "Stop selecting faces and return to Object Mode"
    bl_options = {'REGISTER', 'UNDO'}
    bl_translation_context = CTX

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context):
        obj = context.edit_object
        comparison = editing_comparison(context)
        bpy.ops.object.mode_set(mode='OBJECT')
        if comparison:
            # The comparison is a view; hand selection back to the Body.
            obj.select_set(False)
            obj.hide_select = True
            body = context.scene.underwhere.body
            if body and body.name in context.view_layer.objects:
                body.select_set(True)
                context.view_layer.objects.active = body
        return {'FINISHED'}


class UNDERWHERE_OT_select_group(SafeOperator, Operator):
    bl_idname = "underwhere.select_group"
    bl_label = "Select faces at once"
    bl_description = "Select every matching face on the Body, then choose Keep or Hide for all of them"
    bl_options = {'REGISTER', 'UNDO'}
    group: EnumProperty(translation_context=CTX, items=[
        ('REVIEW', "All unsure", "Every face that could not be decided"),
        ('EXISTING', "Mask issues", "Faces the existing mask hides although they are visible or unsure"),
        ('REASON', "By reason", "Unsure or mask-issue faces with one reason"),
    ])
    reason: StringProperty()

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            report = workflow.fresh_report(context, s, verify=False)
            if self.group == 'REVIEW':
                indices = [f["face"] for f in report["faces"] if f["verdict"] == REVIEW]
            elif self.group == 'EXISTING':
                indices = [f["face"] for f in report["faces"] if f["finding"]]
            else:
                indices = [f["face"] for f in report["faces"]
                           if (f["verdict"] == REVIEW or f["finding"]) and self.reason in f["reason_codes"]]
            if not indices:
                raise adapter.InputError("No matching faces")
            select_body_faces(context, s, indices)
            self.report({'INFO'}, t("Selected: {count}. Keep or Hide applies to all of them.",
                                    count=len(indices)))
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


ACTION_CAPTIONS = {'KEEP': "Keep", 'HIDE': "Hide", 'RESET': "Clear choice"}


class UNDERWHERE_OT_override(SafeOperator, Operator):
    bl_idname = "underwhere.override"
    bl_label = "Keep or hide faces"
    bl_description = "Change the output for the selected faces. The original verdicts stay recorded"
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(translation_context=CTX, items=[('KEEP', "Keep", ""), ('HIDE', "Hide", ""),
                                                         ('RESET', "Clear choice", "")])
    selected: BoolProperty(name="Use selected faces", default=True, translation_context=CTX)
    review_only: BoolProperty(name="Only change unsure faces", default=False, translation_context=CTX)

    def invoke(self, context, event):
        if self.action == 'HIDE':
            return context.window_manager.invoke_confirm(
                self, event, title=t("Hide these faces?"),
                message=t("Hide can cover a face that was seen or unsure. Ctrl+Z undoes it."))
        return self.execute(context)

    @classmethod
    def description(cls, context, properties):
        return tip({
            'KEEP': "Always keep the selected faces in the output",
            'HIDE': "Hide the selected faces in the output. Asks first; Ctrl+Z undoes it",
            'RESET': "Remove your choice from the selected faces and use the automatic verdict",
        }.get(properties.action, cls.bl_description))

    def execute(self, context):
        preview_obj = context.edit_object if editing_comparison(context) else None
        editing_preview = preview_obj is not None
        was_edit = context.mode == 'EDIT_MESH' and not editing_preview
        redrawn = None
        try:
            self.available(context)
            s = context.scene.underwhere
            preview_indices = None
            if editing_preview:
                preview_indices = adapter.selected_preview_faces(preview_obj)
                if not preview_indices:
                    # Checked before leaving Edit Mode so the user can simply drag.
                    raise adapter.InputError("No faces selected: drag over the comparison first")
                bpy.ops.object.mode_set(mode='OBJECT')
            elif was_edit and not editing_body(context, s):
                raise adapter.InputError(leave_other_edit_mode_message(context))
            if was_edit:
                bpy.ops.object.mode_set(mode='OBJECT')
            report = workflow.fresh_report(context, s).copy()
            report['overrides'] = report['overrides'].copy()
            if preview_indices is not None:
                indices = preview_indices
            elif self.selected:
                indices = [offset + p.index for obj, offset in body_layout(s)
                           for p in obj.data.polygons if p.select]
            else:
                indices = [s.face_index]
            if not indices:
                raise adapter.InputError("No faces selected: press Box, Lasso or Brush, then drag over faces")
            if self.review_only and self.action != 'RESET':
                indices = review_faces_only(report, indices)
                if not indices:
                    raise adapter.InputError(
                        "No unsure faces in the selection. Turn off Only change unsure faces to change others.")
            for index in indices:
                if index >= len(report["faces"]):
                    raise adapter.InputError("Face index out of range")
                if self.action == 'RESET':
                    report["overrides"].pop(str(index), None)
                else:
                    report["overrides"][str(index)] = self.action
            report["output_verification"] = adapter.measure_plan(context, s, report)
            workflow.save_report(s, report)
            if s.preview_mode != 'OFF' and (editing_preview or adapter.current_preview(context.scene)):
                redrawn = draw_comparison(context, s, workflow.read_report(s))
            else:
                adapter.clear_preview(context.scene)
            message = t("{action}: {count}", action=t(ACTION_CAPTIONS[self.action]), count=len(indices))
            if editing_preview and redrawn:
                message += " " + t("Select more, or press Done.")
            self.report({'INFO'}, message)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)
        finally:
            if was_edit and context.mode == 'OBJECT':
                bpy.ops.object.mode_set(mode='EDIT')
            elif editing_preview and context.mode == 'OBJECT':
                # Keep the user in selection: a fresh comparison after success,
                # or the same faces still selected after a refusal.
                self.resume_selection(context, redrawn, preview_obj)

    @staticmethod
    def resume_selection(context, redrawn, previous):
        try:
            if redrawn is not None:
                start_comparison_selection(context, redrawn)
            elif previous is not None and previous.name in bpy.data.objects:
                start_comparison_selection(context, previous, clear=False)
        except (ReferenceError, RuntimeError):
            pass  # The comparison was removed; Object Mode is a safe place to stop.


class UNDERWHERE_OT_clear_choices(SafeOperator, Operator):
    bl_idname = "underwhere.clear_choices"
    bl_label = "Clear all choices"
    bl_description = "Remove every Keep and Hide you chose, and use the automatic verdicts again"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title=t("Clear all choices?"),
            message=t("Every Keep and Hide you chose is removed. Ctrl+Z undoes it."))

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            report = workflow.fresh_report(context, s).copy()
            report["overrides"] = {}
            report["carried_choices"] = 0
            report["output_verification"] = adapter.measure_plan(context, s, report)
            workflow.save_report(s, report)
            if adapter.current_preview(context.scene) and s.preview_mode != 'OFF':
                draw_comparison(context, s, workflow.read_report(s))
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_apply(SafeOperator, Operator):
    bl_idname = "underwhere.apply"
    bl_label = "Create output copy"
    bl_description = "Create a copy of the Body that hides the hideable faces. The original is not changed"
    bl_options = {'REGISTER', 'UNDO'}
    deleted: BoolProperty(name="Remove the faces", default=False, translation_context=CTX,
                         description="Delete the faces on the copy instead of masking them, keeping shape keys, "
                                     "weights and UVs (for FBX)")

    def invoke(self, context, event):
        try:
            self.available(context)
            workflow.fresh_report(context, context.scene.underwhere, verify=False)
            return context.window_manager.invoke_props_dialog(self, width=440)
        except Exception as exc:
            return self.fail(context, exc)

    def draw(self, context):
        report = workflow.read_report(context.scene.underwhere)
        plan = report["output_plan"]
        layout = self.layout
        layout.label(text=t("Faces hidden: {faces} ({triangles} triangles)",
                            faces=f"{plan['hidden_polygon_count']:,}",
                            triangles=f"{plan['hidden_triangle_count']:,}"), translate=False)
        layout.label(text=t("The copy is placed where the Body is. The original is not changed."),
                     translate=False)
        layout.label(text=t("Inspected frames: {frames}", frames=workflow.state_caption(report)[:60]),
                     translate=False)
        layout.prop(self, 'deleted')
        if plan["manual_risk_faces"]:
            layout.label(text=t("Faces you hid that were judged visible or unsure: {count}",
                                count=len(plan['manual_risk_faces'])), icon='ERROR', translate=False)
        if plan.get("retained_uncertain_faces"):
            layout.label(text=t("Unsure faces still hidden by the existing mask: {count}",
                                count=len(plan['retained_uncertain_faces'])), icon='ERROR', translate=False)

    def execute(self, context):
        key = workflow.scene_key(context.scene)
        try:
            self.available(context)
            s = context.scene.underwhere
            report = workflow.fresh_report(context, s)
            workflow.BUSY.add(key)
            began = time.perf_counter()
            output = adapter.apply_duplicate(context, s, report, deleted=self.deleted)
            output["seconds"] = time.perf_counter() - began
            report = report.copy()
            report['outputs'] = report['outputs'] + [output]
            workflow.save_report(s, report)
            self.report({'INFO'}, t("Created {names}. The original is unchanged.",
                                    names=", ".join(output.get("objects", [output["object"]]))))
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)
        finally:
            workflow.BUSY.discard(key)


class UNDERWHERE_OT_select_output(SafeOperator, Operator):
    bl_idname = "underwhere.select_output"
    bl_label = "Select the copy"
    bl_description = "Select the copies made by the last output, ready to export"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            outputs = workflow.read_report(context.scene.underwhere)["outputs"]
            names = (outputs[-1].get("objects") or [outputs[-1]["object"]]) if outputs else []
            objects = [bpy.data.objects[name] for name in names if name in bpy.data.objects]
            if not objects:
                raise adapter.InputError("The copy no longer exists.")
            if context.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            for obj in context.selected_objects:
                obj.select_set(False)
            for obj in objects:
                obj.select_set(True)
            context.view_layer.objects.active = objects[0]
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_export(SafeOperator, Operator, ExportHelper):
    bl_idname = "underwhere.export"
    bl_label = "Export shareable report"
    bl_description = "Save a summary without mesh coordinates, connectivity, object or material names, or personal paths"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})
    private: BoolProperty(name="Include full diagnostics (contains mesh data)", default=False,
                          translation_context=CTX,
                          description="Includes purchased mesh geometry and names; never attach it to a public issue")

    def execute(self, context):
        try:
            self.available(context)
            workflow.export_report(context, context.scene.underwhere, self.filepath, private=self.private)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_repair_policy(SafeOperator, Operator):
    bl_idname = "underwhere.repair_policy"
    bl_label = "Repair policy"
    bl_description = "Choose which faces hidden by the existing mask are shown again. The verdicts do not change"
    bl_options = {'REGISTER', 'UNDO'}
    policy: EnumProperty(translation_context=CTX, items=[
        (RESTORE_UNRESOLVED, "Show visible and unsure faces again",
         "Keep only faces confirmed hidden under the mask (strict)"),
        (RESTORE_EXPOSED, "Show visible faces again",
         "Keep the existing mask wherever no face was seen; unsure faces stay hidden"),
    ])

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            report = workflow.fresh_report(context, s).copy()
            if report["input"]["mode"] != "AUDIT":
                raise adapter.InputError("The repair policy applies only when checking an existing mask.")
            report["repair_policy"] = self.policy
            report["output_verification"] = adapter.measure_plan(context, s, report)
            workflow.save_report(s, report)
            adapter.clear_preview(context.scene)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_go_step(Operator):
    bl_idname = "underwhere.go_step"
    bl_label = "Go to step"
    bl_description = "Switch the sidebar to this step"
    bl_translation_context = CTX
    step: EnumProperty(items=STEPS, translation_context=CTX)

    def execute(self, context):
        context.scene.underwhere.ui_step = self.step
        return {'FINISHED'}


def colours_hidden(context):
    """True when this 3D View would not show the comparison's colours."""
    space = getattr(context, "space_data", None)
    if space is None or space.type != 'VIEW_3D':
        return False
    shading = space.shading
    return shading.type == 'WIREFRAME' or (shading.type == 'SOLID' and shading.color_type != 'MATERIAL')


class UNDERWHERE_OT_show_colours(Operator):
    bl_idname = "underwhere.show_colours"
    bl_label = "Show colours"
    bl_description = "Show material colours in this 3D View, so the verdict colours appear"
    bl_options = {'REGISTER', 'UNDO'}
    bl_translation_context = CTX

    @classmethod
    def poll(cls, context):
        return getattr(context, "space_data", None) is not None and context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        shading = context.space_data.shading
        if shading.type == 'WIREFRAME':
            shading.type = 'SOLID'
        if shading.type == 'SOLID':
            shading.color_type = 'MATERIAL'
        return {'FINISHED'}


class UNDERWHERE_UL_occluders(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "object", text="", emboss=True)


class UNDERWHERE_UL_issues(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        try:
            caption = face_caption(workflow.read_report(context.scene.underwhere), item.face)
        except (adapter.InputError, KeyError):
            caption = t("Face {index}", index=item.face)
        layout.label(text=f"{caption}: {reason_label(item.label)}", icon='ERROR', translate=False)


def is_busy(context):
    return workflow.scene_key(context.scene) in workflow.BUSY


def current_report(context):
    s = context.scene.underwhere
    if not s.result_json or is_busy(context):
        return None
    try:
        return workflow.read_report(s)
    except (ValueError, adapter.InputError):
        return None


#: Verdict legend; each entry also toggles that colour on the comparison.
CLASSIFY_LEGEND = [
    ("Hideable", 'COLLECTION_COLOR_04', 'HIDE_CANDIDATE'),
    ("Visible", 'COLLECTION_COLOR_05', 'KEEP_EXPOSED'),
    ("Unsure", 'COLLECTION_COLOR_03', 'REVIEW'),
    ("Mask hides visible", 'COLLECTION_COLOR_01', 'UNSAFE_EXISTING_MASK'),
    ("Mask hides unsure", 'COLLECTION_COLOR_06', 'UNCERTAIN_EXISTING_MASK'),
    ("Hidden by you", 'COLLECTION_COLOR_07', 'MANUAL_HIDE'),
    ("Kept by you", 'OUTLINER_COLLECTION', 'MANUAL_KEEP'),
]
AUDIT_ONLY = {'UNSAFE_EXISTING_MASK', 'UNCERTAIN_EXISTING_MASK'}

LEGENDS = {
    'DIFF': [("Newly hidden", 'COLLECTION_COLOR_04'), ("Shown again", 'COLLECTION_COLOR_05'),
             ("Still hidden", 'COLLECTION_COLOR_08'), ("Visible", 'OUTLINER_COLLECTION')],
    'POSES': [("Hidden in all", 'COLLECTION_COLOR_04'), ("Hidden in 75%+", 'COLLECTION_COLOR_03'),
              ("Hidden in 50%+", 'COLLECTION_COLOR_02'), ("Hidden in some", 'COLLECTION_COLOR_01'),
              ("Never hidden", 'COLLECTION_COLOR_05'), ("Undecided", 'OUTLINER_COLLECTION')],
}

VERDICT_ROW = [(CANDIDATE, "Hideable", 'COLLECTION_COLOR_04'), (KEEP, "Visible", 'COLLECTION_COLOR_05'),
               (REVIEW, "Unsure", 'COLLECTION_COLOR_03')]

TRUSTED_MATERIALS = ("CONSTANT_OPAQUE_PRINCIPLED", "USER_ASSUMED_OPAQUE")
#: Witness verdicts that mean "a clothing material could not be trusted".
MATERIAL_REASONS = {"ALPHA_OR_TRANSMISSION_UNTRUSTED", "UNSUPPORTED_SHADER", "NODE_SURFACE_REQUIRED",
                    "ANIMATED_MATERIAL_UNSUPPORTED", "MISSING_MATERIAL"}


def size_caption(size, factor):
    if factor == 1.0:
        return t("Body size: {size} m", size=f"{size:.3g}")
    return t("The Body is {size} m in scene units; it was analyzed as {scaled} m.",
             size=f"{size:.3g}", scaled=f"{size * factor:.3g}")


def preflight_lines(notice):
    lines = [t("Inputs look fine."), size_caption(notice["size"], notice["factor"])]
    if notice["untrusted_total"]:
        lines.append(t("Materials not confirmed opaque: {count}",
                       count=notice["untrusted_total"]))
        for verdict, count in notice["untrusted"].items():
            lines.append(f"{reason_label(verdict)}: {count}")
    if notice["mask_warning"]:
        lines.append(reason_label(notice["mask_warning"]))
    return lines


def material_blockers(report):
    """(material name, unsure face count) for untrusted clothing materials, largest first."""
    counts = Counter(face["witness"].get("material") for face in report["faces"]
                     if face["verdict"] == REVIEW and face["witness"]
                     and face["witness"].get("material_verdict") in MATERIAL_REASONS)
    return counts.most_common()


def stale_explanation(status):
    """Two short message ids on why the result is out of date."""
    reason = "This result no longer matches the scene."
    if "loaded" in status or "expired" in status or "loading" in status or not status.startswith("STALE"):
        reason = "Results are not saved in .blend files."
    elif "enabled" in status:
        reason = "Results were cleared when the add-on was enabled."
    elif any(word in status for word in ("inputs changed", "no longer supported", "frame changed",
                                         "texture", "Body objects changed")):
        reason = "The Body, clothing, materials or frames changed."
    return [reason, "Your Keep and Hide choices are kept. Analyze again to continue."]


def stale_guard(layout, settings):
    """Say why a result panel is disabled, then return its disabled body layout."""
    if not settings.status.startswith("STALE"):
        return layout
    layout.label(text=t("Out of date. Use Analyze again at the top."), icon='ERROR', translate=False)
    body = layout.column()
    body.enabled = False
    return body


def removal_share(report):
    """(faces the output hides, all faces, share 0..1)."""
    total = len(report["faces"])
    hidden = report["output_plan"]["hidden_polygon_count"]
    return hidden, total, (hidden / total if total else 0.0)


def summary_line(report):
    hidden, _, share = removal_share(report)
    return t("Removable faces: {count} ({percent}%)", count=f"{hidden:,}", percent=round(share * 100))


KNOWN_STATUS = ("READY", "Choose Body and occluders", "Analyzing", "Cancelled", "CHECK", "STALE",
                "Preflight OK", "Frame ", "Build ", "Sample ", "Face ")


def status_view(context, settings, report):
    """(kind, lines) for the status box: what is going on and what to do next."""
    status = settings.status
    if status.startswith("Cancelled"):
        return 'info', [t("The analysis was cancelled. Nothing was changed.")]
    if status == "Preflight OK":
        try:
            notice = json.loads(settings.notice)
        except ValueError:
            notice = None
        if notice:
            warn = notice["untrusted_total"] or notice["mask_warning"]
            return ('warn' if warn else 'ok'), preflight_lines(notice)
    if status.startswith("CHECK"):
        return 'info', wrap(t("The inputs changed. They are checked again at the next step."))
    if not status.startswith(KNOWN_STATUS):
        return 'error', wrap(describe_message(status))
    if report is not None:
        return None, []
    if settings.body is None or not any(item.object for item in settings.occluders):
        return 'start', [t("Choose the Body and its clothing.")] + wrap(
            t("Select the clothing, then the Body last, and press Use selection."))
    return 'start', [t("Ready to analyze."), t("Press Analyze below.")]


STATUS_ICONS = {'ok': 'CHECKMARK', 'warn': 'ERROR', 'error': 'CANCEL', 'info': 'INFO', 'start': 'INFO'}


def draw_status(layout, context, settings, report):
    if not is_busy(context) and not settings.status.startswith("STALE") and report is not None \
            and status_view(context, settings, report)[0] is None:
        return
    box = layout.box()
    column = box.column(align=True)
    if is_busy(context):
        column.label(text=t("Analyzing…"), icon='TIME', translate=False)
        column.progress(factor=settings.progress, type='BAR', text=f"{round(settings.progress * 100)}%")
        box.operator("underwhere.cancel", text=t("Cancel"), icon='CANCEL', translate=False)
        return
    if settings.status.startswith("STALE") or (settings.result_json and report is None):
        for number, line in enumerate(stale_explanation(settings.status)):
            for part in wrap(t(line)):
                column.label(text=part, icon='ERROR' if number == 0 else 'BLANK1', translate=False)
                number = 1
        row = box.row()
        row.scale_y = 1.3
        row.operator("underwhere.analyze", text=t("Analyze again"), icon='FILE_REFRESH', translate=False)
        return
    kind, lines = status_view(context, settings, report)
    for number, line in enumerate(lines):
        column.label(text=line, icon=STATUS_ICONS[kind] if number == 0 else 'BLANK1', translate=False)


def next_steps(report):
    """What still needs a person, most important first.

    Each item: level ('attention', 'decide', 'done', 'info'), text, and actions
    such as ('opaque', material), ('analyze',), ('review',), ('export',)."""
    plan = report["output_plan"]
    overrides = report.get("overrides", {})
    attention, decide, info = [], [], []
    mask_warning = existing_mask_warning(report["input"]["mode"], report["existing_mask"], len(report["faces"]))
    if mask_warning:
        attention.append({"text": reason_label(mask_warning), "actions": []})
    findings = report.get("findings", {})
    if findings.get(UNSAFE):
        attention.append({"text": t("Visible faces hidden by the existing mask: {count}. Choose a repair policy under Check and decide.", count=f"{findings[UNSAFE]:,}"),
                          "actions": []})
    for issue in report.get("occluder_issues", []):
        reasons = ", ".join(reason_label(code) for code in issue["reason_codes"])
        attention.append({"text": t("{object}: {reasons}. Faces it covers stay unsure.",
                                    object=issue["object"], reasons=reasons), "actions": []})
    if plan["manual_risk_faces"]:
        attention.append({"text": t("Faces you hid that were judged visible or unsure: {count}. Check them before you export.", count=len(plan["manual_risk_faces"])),
                          "actions": []})
    if plan.get("retained_uncertain_faces"):
        attention.append({"text": t("Unsure faces still hidden by the existing mask: {count}",
                                    count=len(plan["retained_uncertain_faces"])), "actions": []})
    for name, count in material_blockers(report)[:3]:
        if name:
            text = t("{material} is not confirmed opaque. Unsure faces because of it: {count}",
                     material=name, count=f"{count:,}")
            decide.append({"text": text, "count": count, "actions": [("opaque", name), ("analyze",)]})
        else:
            decide.append({"text": t("Clothing without a material. Unsure faces because of it: {count}",
                                     count=f"{count:,}"), "count": count, "actions": []})
    open_faces = sum(1 for face in report["faces"]
                     if face["verdict"] == REVIEW and str(face["face"]) not in overrides)
    if open_faces:
        decide.append({"text": t("Unsure faces left: {count}. Look at them and choose Keep or Hide.",
                                 count=f"{open_faces:,}"), "count": open_faces, "actions": [("review",)]})
    factor = report["input"]["settings"].get("scale_normalization", 1.0)
    if factor != 1.0:
        info.append({"text": size_caption(report["input"].get("body_size_metres") or 0.0, factor), "actions": []})
    if plan.get("kept_at_shared_vertices"):
        info.append({"text": t("Hideable faces kept because they share vertices with visible faces: {count}. No action is needed.", count=f"{len(plan['kept_at_shared_vertices']):,}"),
                     "actions": []})
    assumed = report.get("assumptions", {}).get("dependent_candidate_faces", 0)
    if assumed:
        info.append({"text": t("Hideable faces that rely on your Opaque setting: {count}", count=f"{assumed:,}"),
                     "actions": []})
    items = [dict(item, level='attention') for item in attention]
    items += [dict(item, level='decide') for item in sorted(decide, key=lambda item: -item["count"])]
    if not items:
        items.append({"level": 'done', "text": t("Nothing is left to decide. You can export now."),
                      "actions": [("export",)]})
    items += [dict(item, level='info') for item in info]
    return items


LEVEL_ICONS = {'attention': 'ERROR', 'decide': 'QUESTION', 'done': 'CHECKMARK', 'info': 'INFO'}


def draw_next_step(layout, item):
    box = layout.box()
    column = box.column(align=True)
    for number, line in enumerate(wrap(item["text"])):
        column.label(text=line, icon=LEVEL_ICONS[item["level"]] if number == 0 else 'BLANK1', translate=False)
    row = box.column(align=True) if any(action[0] == "review" for action in item["actions"]) \
        else box.row(align=True)
    for action in item["actions"]:
        if action[0] == "opaque":
            material = bpy.data.materials.get(action[1])
            if material is not None and not adapter.material_policy(material)["assumption_blocked"]:
                row.prop(material, "underwhere_assume_opaque", text=t("Opaque"), translate=False)
        elif action[0] == "analyze":
            row.operator("underwhere.analyze", text=t("Analyze again"), icon='FILE_REFRESH', translate=False)
        elif action[0] == "review":
            op = row.operator("underwhere.edit_selection", text=t("Pick on the comparison"),
                              icon='SELECT_SET', translate=False)
            op.target = 'COMPARISON'
            op.tool = 'BOX'
            row.operator("underwhere.select_group", text=t("Select all on the Body"),
                         icon='RESTRICT_SELECT_OFF', translate=False).group = 'REVIEW'
        elif action[0] == "export":
            row.operator("underwhere.go_step", text=t("Go to Export"), icon='FORWARD',
                         translate=False).step = 'EXPORT'


class UNDERWHERE_PT_main(Panel):
    bl_label = "UnderWhere"
    bl_idname = "UNDERWHERE_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "UnderWhere"
    bl_translation_context = CTX

    def draw(self, context):
        s = context.scene.underwhere
        report = current_report(context)
        layout = self.layout
        draw_status(layout, context, s, report)
        row = layout.row(align=True)
        row.scale_y = 1.2
        row.prop(s, "ui_step", expand=True)
        if s.ui_step != 'SETUP' and report is None and not is_busy(context):
            box = layout.box()
            box.label(text=t("Analyze first to see a result here."), icon='INFO', translate=False)
            box.operator("underwhere.go_step", text=t("Go to Set up"), icon='BACK',
                         translate=False).step = 'SETUP'


class SubPanel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "UnderWhere"
    bl_parent_id = "UNDERWHERE_PT_main"
    bl_translation_context = CTX
    step = 'SETUP'
    needs_report = False

    @classmethod
    def poll(cls, context):
        s = context.scene.underwhere
        if s.ui_step != cls.step:
            return False
        return not cls.needs_report or current_report(context) is not None


class ResultPanel(SubPanel):
    step = 'REVIEW'
    needs_report = True


class UNDERWHERE_PT_inputs(SubPanel, Panel):
    bl_label = "Body and clothing"
    bl_idname = "UNDERWHERE_PT_inputs"

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not is_busy(context)
        row = layout.row()
        row.scale_y = 1.2
        row.operator("underwhere.use_selection", text=t("Use selection"), icon='RESTRICT_SELECT_OFF',
                     translate=False)
        layout.prop(s, "body")
        layout.prop(s, "use_extra_bodies")
        if s.use_extra_bodies:
            row = layout.row()
            row.template_list("UNDERWHERE_UL_occluders", "body_parts", s, "extra_bodies",
                              s, "extra_body_index", rows=2)
            buttons = row.column(align=True)
            buttons.operator("underwhere.body_part", text="", icon='ADD')
            buttons.operator("underwhere.body_part", text="", icon='REMOVE').remove = True
            layout.label(text=t("+ adds the selected meshes."), icon='INFO', translate=False)
        layout.label(text=t("Clothing"), translate=False)
        row = layout.row()
        row.template_list("UNDERWHERE_UL_occluders", "", s, "occluders", s, "occluder_index", rows=3)
        buttons = row.column(align=True)
        buttons.operator("underwhere.occluder", text="", icon='ADD')
        buttons.operator("underwhere.occluder", text="", icon='REMOVE').remove = True


class UNDERWHERE_PT_inspection(SubPanel, Panel):
    bl_label = "Analysis"
    bl_idname = "UNDERWHERE_PT_inspection"

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not is_busy(context)
        column = layout.column(align=True)
        column.label(text=t("Detail"), translate=False)
        column.row(align=True).prop(s, "preset", expand=True)
        if s.mode == 'AUDIT':
            layout.label(text=t("Checking the existing mask {mask}", mask=s.existing_mask or "-"),
                         icon='MOD_MASK', translate=False)
        if s.scope == 'EXPLICIT_FRAMES':
            layout.label(text=t("Also inspecting frames {frames}", frames=s.frames), icon='TIME', translate=False)
        row = layout.row()
        row.scale_y = 1.6
        row.operator("underwhere.analyze", text=t("Analyze"), icon='PLAY', translate=False)
        layout.operator("underwhere.preflight", text=t("Check inputs only"), icon='CHECKMARK', translate=False)


class UNDERWHERE_PT_options(SubPanel, Panel):
    bl_label = "Poses and purpose"
    bl_idname = "UNDERWHERE_PT_options"
    bl_parent_id = "UNDERWHERE_PT_inspection"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not is_busy(context)
        layout.label(text=t("Poses"), translate=False)
        layout.prop(s, "scope", expand=True)
        if s.scope == 'EXPLICIT_FRAMES':
            layout.prop(s, "frames")
        layout.label(text=t("Purpose"), translate=False)
        layout.prop(s, "mode", expand=True)
        if s.mode == 'AUDIT' and s.body:
            layout.prop_search(s, "existing_mask", s.body, "modifiers", icon='MOD_MASK')


class UNDERWHERE_PT_materials(SubPanel, Panel):
    bl_label = "Clothing materials"
    bl_idname = "UNDERWHERE_PT_materials"
    bl_parent_id = "UNDERWHERE_PT_inspection"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not is_busy(context)
        materials = {slot.material for item in s.occluders if item.object
                     for slot in item.object.material_slots if slot.material}
        if not materials:
            layout.label(text=t("The clothing has no materials."), translate=False)
            return
        for line in wrap(t("Opaque is your own statement that the whole material blocks the view.")):
            layout.label(text=line, translate=False)
        for material in sorted(materials, key=lambda m: m.name):
            policy = adapter.material_policy(material)
            trusted = policy['automatic_verdict'] == "CONSTANT_OPAQUE_PRINCIPLED"
            column = layout.column(align=True)
            row = column.row()
            row.label(text=material.name, icon='MATERIAL', translate=False)
            toggle = row.row()
            toggle.enabled = not policy['assumption_blocked'] and not trusted
            toggle.prop(material, 'underwhere_assume_opaque', text=t("Opaque"), translate=False)
            if trusted:
                column.label(text=t("Confirmed opaque automatically"), icon='CHECKMARK', translate=False)
            elif policy['assumption_blocked']:
                column.label(text=t("Backface culling is on, so it cannot be marked opaque"), icon='ERROR',
                             translate=False)
            else:
                detail = f" ({', '.join(policy['animation'])})" if policy.get('animation') else ""
                column.label(text=reason_label(policy['automatic_verdict']) + detail, icon='QUESTION',
                             translate=False)


class UNDERWHERE_PT_advanced(SubPanel, Panel):
    bl_label = "Sampling values"
    bl_idname = "UNDERWHERE_PT_advanced"
    bl_parent_id = "UNDERWHERE_PT_inspection"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not is_busy(context)
        layout.prop(s, "spatial_step")
        layout.prop(s, "angle")
        layout.prop(s, "touch_tolerance")
        layout.label(text=t("Scene scale: {scale} m per unit",
                            scale=f"{context.scene.unit_settings.scale_length:g}"), translate=False)


class UNDERWHERE_PT_results(ResultPanel, Panel):
    bl_label = "Result"
    bl_idname = "UNDERWHERE_PT_results"

    def draw(self, context):
        s = context.scene.underwhere
        report = current_report(context)
        layout = stale_guard(self.layout, s)
        counts = report["counts"]
        hidden, total, share = removal_share(report)
        column = layout.column(align=True)
        column.label(text=summary_line(report), icon='MOD_MASK', translate=False)
        column.progress(factor=share, type='BAR',
                        text=t("{hidden} of {total} faces", hidden=f"{hidden:,}", total=f"{total:,}"))
        grid = layout.grid_flow(columns=3, even_columns=True, align=True)
        for label, caption, icon in VERDICT_ROW:
            grid.label(text=f"{t(caption)} {counts.get(label, 0):,}", icon=icon, translate=False)
        if report.get("carried_choices"):
            row = layout.row()
            row.label(text=t("Earlier choices kept: {count}", count=report["carried_choices"]), icon='INFO',
                      translate=False)
            row.operator("underwhere.clear_choices", text=t("Clear"), translate=False)
        if report["input"]["mode"] == "AUDIT":
            plan = report["output_plan"]
            box = layout.box()
            box.label(text=t("Faces the existing mask hides: {count}",
                             count=f"{len(report['existing_mask']['hidden_faces']):,}"), icon='MOD_MASK',
                      translate=False)
            box.label(text=t("Shown again: {restored}. Newly hidden: {added}.",
                             restored=len(plan['restored_existing_faces']), added=len(plan['newly_hidden_faces'])),
                      translate=False)
        layout.label(text=t("Next steps"), translate=False)
        for item in next_steps(report):
            draw_next_step(layout, item)


class UNDERWHERE_PT_review(ResultPanel, Panel):
    bl_label = "Check and decide"
    bl_idname = "UNDERWHERE_PT_review"

    def draw(self, context):
        s = context.scene.underwhere
        report = current_report(context)
        layout = stale_guard(self.layout, s)

        column = layout.column(align=True)
        row = column.row(align=True)
        row.prop(s, "preview_mode", text="")
        row.operator("underwhere.preview", text=t("Update"), icon='FILE_REFRESH', translate=False)
        if s.preview_mode == 'CLASSIFY':
            grid = column.grid_flow(columns=2, even_columns=True, align=True)
            audit = report["input"]["mode"] == "AUDIT"
            for caption, icon, key in CLASSIFY_LEGEND:
                if audit or key not in AUDIT_ONLY:
                    grid.prop_enum(s, "preview_show", key, text=t(caption), icon=icon)
            column.label(text=t("Click a colour to show or hide it."), translate=False)
        elif LEGENDS.get(s.preview_mode):
            grid = column.grid_flow(columns=2, even_columns=True, align=True)
            for caption, icon in LEGENDS[s.preview_mode]:
                grid.label(text=t(caption), icon=icon, translate=False)
            if s.preview_mode == 'POSES':
                states = len(report.get("sampled_states", []))
                if states < 2:
                    column.label(text=t("Inspect several frames to see shades."), icon='ERROR', translate=False)
                else:
                    column.label(text=t("Share of {count} inspected frames", count=states), translate=False)
        if s.preview_mode != 'OFF' and colours_hidden(context):
            column.operator("underwhere.show_colours", text=t("Show colours in this view"), icon='SHADING_SOLID',
                            translate=False)

        box = layout.box()
        selecting = selecting_on(context, s)
        tool = active_selection_tool(context) if selecting else None
        box.label(text=t("Choose faces"), translate=False)
        box.prop(s, "selection_target", expand=True)
        row = box.row(align=True)
        row.scale_y = 1.3
        for key, caption, icon in [('BOX', "Box", 'SELECT_SET'), ('LASSO', "Lasso", 'CURVE_BEZCURVE'),
                                   ('CIRCLE', "Brush", 'BRUSH_DATA')]:
            op = row.operator("underwhere.edit_selection", text=t(caption), icon=icon, translate=False,
                              depress=selecting == s.selection_target and tool == key)
            op.target = s.selection_target
            op.tool = key
        hint = box.column(align=True)
        if not selecting:
            for line in wrap(t("Press Box, Lasso or Brush to start.")):
                hint.label(text=line, translate=False)
        else:
            count = sum(obj.data.total_face_sel for obj in context.objects_in_mode if obj.type == 'MESH')
            if count:
                hint.label(text=t("Selected: {count}", count=f"{count:,}"), icon='CHECKMARK', translate=False)
            else:
                hint.label(text=t("Drag over faces"), icon='MOUSE_LMB_DRAG', translate=False)
            hint.label(text=t("Shift adds, Ctrl removes"), icon='BLANK1', translate=False)
        box.separator()
        box.label(text=t("Decide"), translate=False)
        box.prop(s, "override_review_only")
        row = box.row(align=True)
        row.scale_y = 1.3
        for action, icon in [('KEEP', 'HIDE_OFF'), ('HIDE', 'HIDE_ON'), ('RESET', 'X')]:
            op = row.operator("underwhere.override", text=t(ACTION_CAPTIONS[action]), icon=icon, translate=False)
            op.action = action
            op.review_only = s.override_review_only
        if selecting:
            box.operator("underwhere.finish_selection", text=t("Done"), icon='CHECKMARK', translate=False)

        if report["input"]["mode"] == "AUDIT":
            policy = report["output_plan"].get("repair_policy") or RESTORE_UNRESOLVED
            layout.label(text=t("Repair the existing mask"), translate=False)
            column = layout.column(align=True)
            for value, caption in [(RESTORE_UNRESOLVED, "Show visible and unsure faces again"),
                                   (RESTORE_EXPOSED, "Show visible faces again")]:
                column.operator("underwhere.repair_policy", text=t(caption), translate=False,
                                depress=policy == value).policy = value
        row = layout.row()
        row.scale_y = 1.3
        row.operator("underwhere.go_step", text=t("Go to Export"), icon='FORWARD', translate=False).step = 'EXPORT'


class UNDERWHERE_PT_reasons(ResultPanel, Panel):
    bl_label = "Select by reason"
    bl_idname = "UNDERWHERE_PT_reasons"
    bl_parent_id = "UNDERWHERE_PT_review"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.underwhere
        layout = stale_guard(self.layout, s)
        reasons = review_reason_counts(current_report(context))
        if not reasons:
            layout.label(text=t("No unsure faces"), icon='CHECKMARK', translate=False)
            return
        layout.label(text=t("Selects on the Body; then choose Keep or Hide."), translate=False)
        column = layout.column(align=True)
        for code, count in reasons[:8]:
            op = column.operator("underwhere.select_group", text=f"{reason_label(code)} ({count:,})", icon='DOT',
                                 translate=False)
            op.group = 'REASON'
            op.reason = code
            hint = reason_hint(code)
            if hint:
                for line in wrap(hint):
                    column.label(text=line, icon='BLANK1', translate=False)


class UNDERWHERE_PT_faces(ResultPanel, Panel):
    bl_label = "One face at a time"
    bl_idname = "UNDERWHERE_PT_faces"
    bl_parent_id = "UNDERWHERE_PT_review"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.underwhere
        report = current_report(context)
        layout = stale_guard(self.layout, s)
        if s.issues:
            layout.template_list('UNDERWHERE_UL_issues', '', s, 'issues', s, 'issue_index', rows=4)
        else:
            layout.label(text=t("No unsure faces"), icon='CHECKMARK', translate=False)
        box = layout.box()
        box.prop(s, "face_index")
        if s.face_index < len(report["faces"]):
            face = report["faces"][s.face_index]
            box.label(text=reason_label(face["finding"] or face["verdict"]), translate=False)
            for reason in face["reason_codes"]:
                box.label(text=reason_label(reason), translate=False)
            if face["witness"] and face["witness"].get("material"):
                box.label(text=t("Material: {name}", name=face["witness"]["material"]), icon='MATERIAL',
                          translate=False)
            hints = {reason_hint(code) for code in face["reason_codes"]} - {None}
            for hint in sorted(hints):
                for number, line in enumerate(wrap(hint)):
                    box.label(text=line, icon='LIGHT' if number == 0 else 'BLANK1', translate=False)
        row = box.row(align=True)
        row.operator("underwhere.face", text=t("Select"), icon='RESTRICT_SELECT_OFF', translate=False).action = 'SELECT'
        row.operator("underwhere.face", text=t("Next"), icon='TRIA_RIGHT', translate=False).action = 'NEXT'
        row.operator("underwhere.face", text=t("View ray"), icon='HIDE_OFF', translate=False).action = 'VIEW'


class UNDERWHERE_PT_output(SubPanel, Panel):
    bl_label = "Export"
    bl_idname = "UNDERWHERE_PT_output"
    step = 'EXPORT'
    needs_report = True

    def draw(self, context):
        s = context.scene.underwhere
        report = current_report(context)
        layout = stale_guard(self.layout, s)
        hidden, _, share = removal_share(report)
        layout.label(text=t("Faces the output hides: {count} ({percent}%)", count=f"{hidden:,}",
                            percent=round(share * 100)), icon='MOD_MASK', translate=False)
        if any(item["level"] == 'attention' for item in next_steps(report)):
            box = layout.box()
            column = box.column(align=True)
            for number, line in enumerate(wrap(t("Some points still need attention. See Review."))):
                column.label(text=line, icon='ERROR' if number == 0 else 'BLANK1', translate=False)
            box.operator("underwhere.go_step", text=t("Go to Review"), icon='BACK', translate=False).step = 'REVIEW'
        for caption, icon, deleted, explanation in [
                ("Create masked copy", 'MOD_MASK', False,
                 "Hides the faces with a Mask modifier. Easy to undo."),
                ("Create copy with faces removed", 'MESH_DATA', True,
                 "Deletes the faces but keeps shape keys, UVs and weights. Use this for FBX (VRChat).")]:
            box = layout.box()
            row = box.row()
            row.scale_y = 1.3
            row.operator("underwhere.apply", text=t(caption), icon=icon, translate=False).deleted = deleted
            column = box.column(align=True)
            for line in wrap(t(explanation)):
                column.label(text=line, translate=False)
        outputs = report.get("outputs", [])
        if outputs:
            names = ", ".join(outputs[-1].get("objects") or [outputs[-1]["object"]])
            box = layout.box()
            box.label(text=t("Created: {names}", names=names), icon='CHECKMARK', translate=False)
            box.operator("underwhere.select_output", text=t("Select the copy"), icon='RESTRICT_SELECT_OFF',
                         translate=False)
            column = box.column(align=True)
            for line in wrap(t("For FBX, select the copy and its Armature, then export with Selected Objects "
                               "on and Apply Modifiers off.")):
                column.label(text=line, translate=False)
        layout.separator()
        layout.operator("underwhere.export", text=t("Export shareable report"), icon='EXPORT', translate=False)
        layout.label(text=t("The original Body is never changed."), icon='INFO', translate=False)


@persistent
def on_load(_):
    stop_jobs(None)
    workflow.LIVE_RUNS.clear()
    workflow.LIVE_GUARDS.clear()
    workflow.REPORT_CACHE.clear()
    workflow.BUSY.clear()
    workflow.DIRTY.clear()
    for scene in bpy.data.scenes:
        if scene.library or scene.override_library or not scene.is_editable:
            continue
        workflow.discard_legacy_report(scene.underwhere)
        if hasattr(scene, "underwhere") and scene.underwhere.result_json:
            scene.underwhere.status = "STALE: file loaded; Analyze again"
        adapter.clear_preview(scene)
        migrate_settings(scene)


def migrate_settings(scene):
    """Adopt settings saved before the final name; never reuse old evidence."""
    if scene.library or scene.override_library or not scene.is_editable:
        return
    for material in bpy.data.materials:
        if material.library or material.override_library or not material.is_editable:
            continue
        if 'underwhere_assume_opaque' not in material and 'obma_assume_opaque' in material:
            material.underwhere_assume_opaque = bool(material['obma_assume_opaque'])
            del material['obma_assume_opaque']
    settings = scene.underwhere
    if settings.body or settings.occluders:
        return
    source_key = next((key for key in ('body_occlusion_mask', 'obma_beta') if scene.get(key)), None)
    if source_key is None:
        return
    legacy = scene[source_key]
    skipped = {'rna_type', 'result_json', 'status', 'progress', 'cancel_requested', 'issues', 'occluders'}
    for prop in settings.bl_rna.properties:
        name = prop.identifier
        if name in skipped or prop.is_readonly or prop.type == 'COLLECTION':
            continue
        if name in legacy:
            # Raw EnumProperty ID values are integers; assignment through the
            # ID-property interface preserves their stable item ordering.
            value = legacy[name]
            if source_key == 'obma_beta' and name in ('spatial_step', 'touch_tolerance'):
                value *= scene.unit_settings.scale_length
            settings[name] = value
    for item in legacy.get('occluders', []):
        settings.occluders.add().object = item.get('object')
    settings.status = "STALE: settings migrated to UnderWhere; Analyze again"
    adapter.clear_preview(scene)
    del scene[source_key]


@persistent
def stop_jobs(_):
    for job in list(JOBS):
        job.cleanup()


@persistent
def on_history_pre(_):
    HISTORY_CANCELLED_SCENES.clear()
    for job in list(JOBS):
        try:
            HISTORY_CANCELLED_SCENES.add(job._scene.name_full)
        except ReferenceError:
            pass
        job.cleanup()


@persistent
def on_undo(_):
    # Undo restores the tiny revision token. Keep the bounded in-memory
    # revisions so previous overrides/output metadata remain recoverable.
    for scene in bpy.data.scenes:
        if scene.library or scene.override_library or not scene.is_editable:
            continue
        workflow.DIRTY.add(workflow.scene_key(scene))
        workflow.discard_legacy_report(scene.underwhere)
        if scene.name_full in HISTORY_CANCELLED_SCENES:
            scene.underwhere.status = "Cancelled: analysis stopped by Undo/Redo"
            scene.underwhere.progress = 0.0
    HISTORY_CANCELLED_SCENES.clear()


@persistent
def on_update(scene, depsgraph):
    if scene.library or scene.override_library or not scene.is_editable:
        return
    key = workflow.scene_key(scene)
    if key in workflow.BUSY or not hasattr(scene, "underwhere"):
        return
    if not scene.underwhere.result_json:
        return
    # Pixel payloads are not part of the lightweight material graph hash.
    # Any image/texture update conservatively expires the session, including
    # dependencies buried in a color node group.
    if any(isinstance(u.id, (bpy.types.Image, bpy.types.Texture)) for u in depsgraph.updates):
        try:
            workflow.LIVE_RUNS.discard(workflow.read_report(scene.underwhere)["run_id"])
        except (ValueError, KeyError):
            pass
        scene.underwhere.status = "STALE: image/texture dependency changed"
    settings = scene.underwhere
    objects = set(adapter.body_objects(settings)) | {item.object for item in settings.occluders}
    objects.discard(None)
    rigs = {mod.object for obj in objects for mod in obj.modifiers if mod.type == 'ARMATURE'}
    data = {obj.data for obj in objects}
    materials = {slot.material for obj in objects for slot in obj.material_slots if slot.material}
    # Selection-only Object/Scene updates have no geometry/transform/shading
    # flags. The comparison's own object, mesh, materials, node trees and
    # collection link never dirty this result; otherwise the freshness timer
    # deletes every comparison right after creating it. Visibility and material
    # slot assignment are covered by workflow.guard instead.
    preview_trees = None

    def relevant(update):
        nonlocal preview_trees
        original = update.id.original
        if original in objects | rigs:
            # Shading-only Object updates fire for every object whenever any
            # material is added (including the comparison's own). Material
            # contents are caught below; slot assignment is in workflow.guard.
            return update.is_updated_geometry or update.is_updated_transform
        if original in data | materials or isinstance(update.id, bpy.types.Action):
            return True
        if isinstance(update.id, bpy.types.NodeTree):
            if preview_trees is None:
                preview_trees = {m.node_tree for m in bpy.data.materials
                                 if m.node_tree and adapter.is_preview_material(m)}
            return original not in preview_trees
        return False

    if any(relevant(u) for u in depsgraph.updates):
        workflow.DIRTY.add(key)


def freshness_timer():
    # Never evaluate meshes or shape keys from a polling timer.
    try:
        context = bpy.context
        if context.scene and hasattr(context.scene, "underwhere"):
            migrate_settings(context.scene)
            key = workflow.scene_key(context.scene)
            s = context.scene.underwhere
            workflow.discard_legacy_report(s)
            if s.result_json and key not in workflow.BUSY:
                try:
                    report = workflow.read_report(s)
                except adapter.InputError as exc:
                    adapter.clear_preview(context.scene)
                    s.status = str(exc)
                    return 0.75
                if report["run_id"] not in workflow.LIVE_RUNS:
                    adapter.clear_preview(context.scene)
                    s.status = "STALE: extension enabled; Analyze again"
                elif key in workflow.DIRTY or workflow.LIVE_GUARDS.get(
                        report['run_id']) != workflow.guard(context, s):
                    if not s.status.startswith('CHECK'):
                        adapter.clear_preview(context.scene)
                    if not s.status.startswith('Cancelled'):
                        s.status = "CHECK: inputs updated; verified on next operation"
    except Exception as exc:
        # Keep the timer registered after deleted RNA, undo or corrupt data.
        workflow.LIVE_RUNS.clear()
        try:
            context.scene.underwhere.status = "STALE: freshness check failed; Analyze again"
        except (AttributeError, ReferenceError):
            pass
        print(f"UnderWhere freshness check: {type(exc).__name__}")
    return 0.75


CLASSES = (
    UNDERWHERE_Issue, UNDERWHERE_Occluder, UNDERWHERE_Settings, UNDERWHERE_OT_setup, UNDERWHERE_OT_occluder,
    UNDERWHERE_OT_body_part,
    UNDERWHERE_OT_preflight, UNDERWHERE_OT_analyze, UNDERWHERE_OT_cancel,
    UNDERWHERE_OT_preview, UNDERWHERE_OT_face, UNDERWHERE_OT_override, UNDERWHERE_OT_clear_choices,
    UNDERWHERE_OT_apply, UNDERWHERE_OT_select_output,
    UNDERWHERE_OT_export, UNDERWHERE_OT_repair_policy, UNDERWHERE_OT_select_group,
    UNDERWHERE_OT_edit_selection, UNDERWHERE_OT_finish_selection,
    UNDERWHERE_OT_go_step, UNDERWHERE_OT_show_colours,
    UNDERWHERE_UL_occluders, UNDERWHERE_UL_issues,
    UNDERWHERE_PT_main, UNDERWHERE_PT_inputs, UNDERWHERE_PT_inspection, UNDERWHERE_PT_options,
    UNDERWHERE_PT_materials, UNDERWHERE_PT_advanced, UNDERWHERE_PT_results, UNDERWHERE_PT_review,
    UNDERWHERE_PT_reasons, UNDERWHERE_PT_faces, UNDERWHERE_PT_output,
)

HANDLERS = [(bpy.app.handlers.load_pre, stop_jobs), (bpy.app.handlers.load_post, on_load),
            (bpy.app.handlers.undo_pre, on_history_pre), (bpy.app.handlers.redo_pre, on_history_pre),
            (bpy.app.handlers.undo_post, on_undo), (bpy.app.handlers.redo_post, on_undo),
            (bpy.app.handlers.depsgraph_update_post, on_update)]


def register():
    registered = []
    try:
        for cls in CLASSES:
            bpy.utils.register_class(cls)
            registered.append(cls)
        bpy.types.Scene.underwhere = PointerProperty(type=UNDERWHERE_Settings)
        bpy.types.Material.underwhere_assume_opaque = BoolProperty(
            name="Opaque", default=False, update=input_changed, translation_context=CTX,
            description="Your statement that this whole material is opaque on both sides, with no transmission "
                        "or displacement. Recorded in reports; not an automatic proof")
        for handlers, callback in HANDLERS:
            handlers.append(callback)
        bpy.app.timers.register(freshness_timer, persistent=True)
        # Blender's official enable path forbids bpy.data/context access here.
        # File-load handler and the first UI timer handle saved result expiry.
        workflow.LIVE_RUNS.clear()
    except Exception:
        if bpy.app.timers.is_registered(freshness_timer):
            bpy.app.timers.unregister(freshness_timer)
        for handlers, callback in HANDLERS:
            if callback in handlers:
                handlers.remove(callback)
        if hasattr(bpy.types.Scene, "underwhere"):
            del bpy.types.Scene.underwhere
        if hasattr(bpy.types.Material, "underwhere_assume_opaque"):
            del bpy.types.Material.underwhere_assume_opaque
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        raise


def unregister():
    for job in list(JOBS):
        job.cleanup()
    if bpy.app.timers.is_registered(freshness_timer):
        bpy.app.timers.unregister(freshness_timer)
    for handlers, callback in HANDLERS:
        if callback in handlers:
            handlers.remove(callback)
    workflow.LIVE_RUNS.clear()
    workflow.REPORT_CACHE.clear()
    workflow.LIVE_GUARDS.clear()
    workflow.BUSY.clear()
    workflow.DIRTY.clear()
    for scene in bpy.data.scenes:
        adapter.clear_preview(scene)
    if hasattr(bpy.types.Scene, "underwhere"):
        del bpy.types.Scene.underwhere
    if hasattr(bpy.types.Material, "underwhere_assume_opaque"):
        del bpy.types.Material.underwhere_assume_opaque
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
