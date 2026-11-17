"""Sidebar panels and undoable operators."""
import json
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

JOBS = []
PRESET_APPLY = set()
HISTORY_CANCELLED_SCENES = set()

REASON_LABELS = {
    "EXPOSURE_WITNESS": "露出する光線を検出",
    "ALL_REQUIRED_FINITE_SAMPLES_OCCLUDED": "検査サンプルはすべて遮蔽",
    "SURFACE_INTERSECTION": "身体と衣装が交差",
    "CONTACT_OR_DEPTH_TIE": "接触または奥行きが不明確",
    "OCCLUDER_TOPOLOGY_AMBIGUITY": "遮蔽物の形状に未解決の問題",
    "OPENING_BUDGET_EXCEEDED": "開口数が検査上限を超過",
    "NONMANIFOLD_OCCLUDER": "非多様体の遮蔽物",
    "SOLIDIFY_OPENING_UNRESOLVED": "厚み付き開口は自動非表示の対象外",
    "SPATIAL_COVER_INCOMPLETE_OR_DEGENERATE": "検査密度不足または退化面",
    "ALPHA_OR_TRANSMISSION_UNTRUSTED": "透明度・透過を確認できない",
    "UNSUPPORTED_SHADER": "未対応のシェーダー",
    "MISSING_MATERIAL": "マテリアル未指定",
    "NODE_SURFACE_REQUIRED": "ノードの表面出力が必要",
    "ANIMATED_MATERIAL_UNSUPPORTED": "マテリアルのアニメーションは未対応",
    "BACKFACE_CULLING_UNTRUSTED": "裏面カリングを信頼できない",
    "NO_COMPLETE_EVIDENCE": "検査の根拠が不足",
    REVIEW: "要確認", KEEP: "露出・残す", CANDIDATE: "非表示の候補",
    "UNSAFE_EXISTING_MASK": "既存マスクが露出面を隠す",
    "UNCERTAIN_EXISTING_MASK": "既存マスクが未確認面を隠す",
    "EXISTING_MASK_DISABLED": "既存マスクが無効になっている",
    "EXISTING_MASK_HIDES_NOTHING": "既存マスクは何も隠していない",
    "EXISTING_MASK_HIDES_EVERYTHING": "既存マスクがすべての面を隠している（Invert を確認）",
}


# One-line next step for each Review reason (Japanese UI / English UI).
REASON_HINTS = {
    "ALPHA_OR_TRANSMISSION_UNTRUSTED": ("本当に不透明なら Materials で Opaque にして再解析",
                                        "If truly opaque, set Opaque in Materials and re-analyze"),
    "UNSUPPORTED_SHADER": ("本当に不透明なら Materials で Opaque にして再解析",
                           "If truly opaque, set Opaque in Materials and re-analyze"),
    "NODE_SURFACE_REQUIRED": ("本当に不透明なら Materials で Opaque にして再解析",
                              "If truly opaque, set Opaque in Materials and re-analyze"),
    "MISSING_MATERIAL": ("衣装にマテリアルを割り当てて再解析",
                         "Assign a material to the clothing and re-analyze"),
    "ANIMATED_MATERIAL_UNSUPPORTED": ("目視で確認し、隠すなら Hide", "Check visually; Hide if hidden"),
    "BACKFACE_CULLING_UNTRUSTED": ("カリングを切れるなら切って再解析、無理なら目視で判断",
                                   "Disable culling and re-analyze, or check visually"),
    "SURFACE_INTERSECTION": ("衣装の位置やウェイトを直す。突き抜けを隠すだけなら Hide",
                             "Fix fit or weights; Hide only to conceal poke-through"),
    "CONTACT_OR_DEPTH_TIE": ("衣装の位置やウェイトを直す。突き抜けを隠すだけなら Hide",
                             "Fix fit or weights; Hide only to conceal poke-through"),
    "OCCLUDER_TOPOLOGY_AMBIGUITY": ("表示された衣装のメッシュを直して再解析、または目視で判断",
                                    "Fix the named clothing mesh, or check visually"),
    "SOLIDIFY_OPENING_UNRESOLVED": ("目視で確認し、隠すなら Hide", "Check visually; Hide if hidden"),
    "SPATIAL_COVER_INCOMPLETE_OR_DEGENERATE": ("処理量を Detailed にして再解析",
                                               "Use Detailed and re-analyze"),
    "NO_COMPLETE_EVIDENCE": ("目視で確認し、隠すなら Hide", "Check visually; Hide if hidden"),
}
#: Reason codes that describe evidence rather than a cause to act on.
INFORMATIONAL_REASONS = {"EXPOSURE_WITNESS", "ALL_REQUIRED_FINITE_SAMPLES_OCCLUDED"}


def is_japanese():
    return bpy.context.preferences.view.language.startswith('ja')


def reason_hint(code):
    hint = REASON_HINTS.get(code)
    return None if hint is None else hint[0 if is_japanese() else 1]


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
    return f"Leave Edit Mode on {context.edit_object.name} first (Tab), then press Box, Lasso or Brush"


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


def select_body_faces(context, settings, indices):
    """Select exactly `indices` on the configured Body in Edit Mode and frame them."""
    import bmesh
    if context.mode == 'EDIT_MESH':
        # Leaving the comparison is harmless; any other mesh may hold user edits.
        if context.edit_object != settings.body and not editing_comparison(context):
            raise adapter.InputError(leave_other_edit_mode_message(context))
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in context.selected_objects:
        obj.select_set(False)
    settings.body.select_set(True)
    context.view_layer.objects.active = settings.body
    context.tool_settings.mesh_select_mode = (False, False, True)
    bpy.ops.object.mode_set(mode='EDIT')
    mesh = bmesh.from_edit_mesh(settings.body.data)
    for element in list(mesh.verts) + list(mesh.edges) + list(mesh.faces):
        element.select_set(False)
    mesh.faces.ensure_lookup_table()
    for index in indices:
        mesh.faces[index].select_set(True)
    mesh.select_flush_mode()
    bmesh.update_edit_mesh(settings.body.data)
    if context.space_data and context.space_data.type == 'VIEW_3D' and indices:
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if region:
            with context.temp_override(region=region):
                bpy.ops.view3d.view_selected(use_all_regions=False)


def reason_label(code):
    return REASON_LABELS.get(code, code) if bpy.context.preferences.view.language.startswith('ja') else code.replace('_', ' ').capitalize()


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


class UNDERWHERE_Settings(PropertyGroup):
    body: PointerProperty(name="Body", type=bpy.types.Object, poll=mesh_poll, update=input_changed)
    occluders: CollectionProperty(type=UNDERWHERE_Occluder)
    occluder_index: IntProperty(default=0)
    mode: EnumProperty(name="Mode", items=[
        ('GENERATE', "Generate Mask", "Find finite-sample hide candidates"),
        ('AUDIT', "Audit Existing Mask", "Inspect an existing vertex-group Mask Modifier"),
    ], update=input_changed)
    existing_mask: StringProperty(name="Existing Mask", update=input_changed)
    scope: EnumProperty(name="States", items=[
        ('CURRENT_POSE_ONLY', "Current Pose", "Inspect the current frame and subframe"),
        ('EXPLICIT_FRAMES', "Current + Selected Frames", "Always inspect the current frame/subframe, plus listed frames; no guarantee between frames"),
    ], update=input_changed)
    frames: StringProperty(name="Frames", default="1, 10, 20", update=input_changed)
    issues: CollectionProperty(type=UNDERWHERE_Issue)
    issue_index: IntProperty(update=issue_changed)
    preset: EnumProperty(name="Work budget", items=[
        ('QUICK', "Quick", "Coarser finite sampling; not a safety level"),
        ('BALANCED', "Balanced", "Moderate finite sampling; not a safety level"),
        ('DETAILED', "Detailed", "Finer finite sampling; not a safety level"),
        ('CUSTOM', "Custom", "Manually edited sample settings"),
    ], default='BALANCED', update=preset_changed)
    spatial_step: FloatProperty(name="Spatial step (metres)", default=0.05,
                                min=0.00001, max=100.0, update=budget_changed)
    angle: FloatProperty(name="Angular step (degrees)", default=45.0, min=15.0,
                        max=90.0, update=budget_changed)
    touch_tolerance: FloatProperty(name="Contact tolerance (metres)", default=0.00001,
                                  min=0.0000001, max=0.01, precision=7, update=budget_changed)
    advanced: BoolProperty(name="Advanced")
    status: StringProperty(default="Choose Body and occluders")
    # Compatibility field name; contains only a small session revision reference.
    result_json: StringProperty(options={'HIDDEN'})
    progress: FloatProperty(min=0.0, max=1.0, subtype='FACTOR', options={'SKIP_SAVE'})
    cancel_requested: BoolProperty(options={'SKIP_SAVE'})
    face_index: IntProperty(name="Source face", min=0)
    selection_target: EnumProperty(name="Select on", items=[
        ('COMPARISON', "Comparison", "Select on the colored comparison mesh beside the Body"),
        ('BODY', "Body", "Select on the Body itself"),
    ], default='COMPARISON')
    override_review_only: BoolProperty(
        name="Only change Review faces", default=True,
        description="Keep / Hide affect only Review and existing-mask issue faces in the selection, "
                    "so a rough box, lasso or paint selection never overrides Keep faces")
    preview_mode: EnumProperty(name="Compare", items=[
        ('CLASSIFY', "Classification", "Color evidence on a comparison mesh beside the source"),
        ('ORIGINAL', "Unmasked", "Show the unmasked sampled geometry beside the source"),
        ('OUTPUT', "Output", "Show the proposed vertex Mask output beside the source"),
        ('DIFF', "Before / After", "Color faces by how the output changes the existing mask"),
        ('OFF', "Off", "Remove comparison objects"),
    ], default='CLASSIFY')


class SafeOperator:
    def fail(self, context, exc):
        context.scene.underwhere.status = str(exc)
        self.report({'ERROR'}, str(exc))
        return {'CANCELLED'}

    def available(self, context):
        if workflow.scene_key(context.scene) in workflow.BUSY:
            raise adapter.InputError("Wait for analysis or cancel it first")
        migrate_settings(context.scene)


class UNDERWHERE_OT_setup(SafeOperator, Operator):
    bl_idname = "underwhere.use_selection"
    bl_label = "Use Selection"
    bl_description = "Active mesh is Body; other selected meshes become occluders"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            self.available(context)
            body = context.active_object
            if body is None or not mesh_poll(None, body):
                raise adapter.InputError("Select the Body last so it is the active mesh")
            s = context.scene.underwhere
            s.body = body
            s.occluders.clear()
            for obj in context.selected_objects:
                if obj != body and mesh_poll(None, obj):
                    s.occluders.add().object = obj
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_occluder(SafeOperator, Operator):
    bl_idname = "underwhere.occluder"
    bl_label = "Edit Occluder List"
    bl_description = "Add an occluder slot or remove the selected entry; Analyze again after changes"
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


class UNDERWHERE_OT_preflight(SafeOperator, Operator):
    bl_idname = "underwhere.preflight"
    bl_label = "Preflight"
    bl_description = "Check inputs without analyzing: geometry, modifiers, material trust and the existing mask"

    def execute(self, context):
        key = workflow.scene_key(context.scene)
        try:
            self.available(context)
            workflow.BUSY.add(key)
            s = context.scene.underwhere
            state, _ = adapter.snapshot(context, s)
            untrusted = sum(m["verdict"] not in ("CONSTANT_OPAQUE_PRINCIPLED", "USER_ASSUMED_OPAQUE")
                            for o in state["occluders"] for m in o["materials"])
            missing = sum(not o["materials"] for o in state["occluders"])
            mask_warning = existing_mask_warning(
                s.mode, state["existing_mask"], len(state["body"]["polygons"]))
            text = f"Preflight OK; {untrusted + missing} untrusted material slots/objects"
            if mask_warning:
                text += "; " + reason_label(mask_warning)
            s.status = text
            self.report({'WARNING'} if untrusted + missing or mask_warning else {'INFO'}, text)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)
        finally:
            workflow.BUSY.discard(key)


class UNDERWHERE_OT_analyze(SafeOperator, Operator):
    bl_idname = "underwhere.analyze"
    bl_label = "Analyze"
    bl_description = "Inspect the selected states; use Cancel Analysis or Esc in this viewport to stop"
    bl_options = {'REGISTER', 'UNDO'}
    _iterator = None
    _timer = None

    def execute(self, context):
        try:
            self.available(context)
            workflow.run_sync(context, context.scene.underwhere)
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
    bl_label = "Cancel Analysis"
    bl_description = "Stop the active analysis and leave the source unchanged"

    def execute(self, context):
        context.scene.underwhere.cancel_requested = True
        return {'FINISHED'}


class UNDERWHERE_OT_preview(SafeOperator, Operator):
    bl_idname = "underwhere.preview"
    bl_label = "Update Comparison"
    bl_description = "Show classification, sampled geometry or proposed output beside the Body"
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
                obj = adapter.preview(context, report, s.preview_mode)
                if was_selecting and obj is not None:
                    start_comparison_selection(context, obj)
            return {'FINISHED'}
        except Exception as exc:
            adapter.clear_preview(context.scene)
            return self.fail(context, exc)


class UNDERWHERE_OT_face(SafeOperator, Operator):
    bl_idname = "underwhere.face"
    bl_label = "Inspect Source Face"
    bl_description = "Select and focus a source face, browse issues, or view its recorded ray"
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('SELECT', "Select", ""), ('NEXT', "Next Issue", ""),
                                ('VIEW', "View Witness", "")])

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
                    raise adapter.InputError("This face has no ray witness")
                if context.space_data.type != 'VIEW_3D':
                    raise adapter.InputError("Use View Witness in a 3D View")
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
    return 'BODY' if context.edit_object == settings.body else None


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
    bl_label = "Select Faces"
    bl_description = ("Start face selection on the colored comparison (or the Body) with the chosen "
                      "tool, then use Keep / Hide. Switching tools keeps the current selection")
    bl_options = {'REGISTER', 'UNDO'}
    target: EnumProperty(items=[
        ('COMPARISON', "On Comparison", "Select on the colored comparison mesh beside the Body"),
        ('BODY', "On Body", "Select on the Body itself"),
    ])
    tool: EnumProperty(items=[
        ('NONE', "Current tool", "Keep the active selection tool"),
        ('BOX', "Box", "Drag a rectangle"),
        ('LASSO', "Lasso", "Draw a free-form outline"),
        ('CIRCLE', "Brush", "Paint over faces with a circle brush (mouse wheel changes its size)"),
    ], default='NONE')

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            workflow.fresh_report(context, s, verify=False)
            if self.target == 'BODY':
                if context.edit_object != s.body:
                    select_body_faces(context, s, [])
            else:
                obj = adapter.current_preview(context.scene)
                if obj is None:
                    # Show the comparison instead of asking for another click.
                    if context.mode == 'EDIT_MESH' and context.edit_object != s.body:
                        raise adapter.InputError(leave_other_edit_mode_message(context))
                    if s.preview_mode == 'OFF':
                        s.preview_mode = 'CLASSIFY'
                    obj = adapter.preview(context, workflow.fresh_report(context, s), s.preview_mode)
                if context.edit_object != obj:
                    if context.mode == 'EDIT_MESH' and context.edit_object not in (s.body, None) \
                            and not editing_comparison(context):
                        raise adapter.InputError(leave_other_edit_mode_message(context))
                    start_comparison_selection(context, obj)
            if self.tool != 'NONE' and context.area and context.area.type == 'VIEW_3D':
                bpy.ops.wm.tool_set_by_id(name=SELECTION_TOOLS[self.tool])
            self.report({'INFO'}, "Drag over faces; Shift adds, Ctrl removes. Then Keep / Hide")
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_finish_selection(Operator):
    bl_idname = "underwhere.finish_selection"
    bl_label = "Done"
    bl_description = "Stop selecting faces and return to Object Mode"
    bl_options = {'REGISTER', 'UNDO'}

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
    bl_label = "Select Faces in Bulk"
    bl_description = "Select every matching Body face in Edit Mode, then use Keep / Hide on them at once"
    bl_options = {'REGISTER', 'UNDO'}
    group: EnumProperty(items=[
        ('REVIEW', "All Review", "Every face that could not be decided"),
        ('EXISTING', "Existing mask issues", "Faces the existing mask hides although they are exposed or undecided"),
        ('REASON', "By reason", "Review or existing-mask faces with one reason code"),
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
            self.report({'INFO'}, f"Selected {len(indices)} faces; Keep / Hide applies to all of them")
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_override(SafeOperator, Operator):
    bl_idname = "underwhere.override"
    bl_label = "Manual Face Override"
    bl_description = "Change requested output; original evidence and warnings remain"
    bl_options = {'REGISTER', 'UNDO'}
    action: EnumProperty(items=[('KEEP', "Keep", ""), ('HIDE', "Hide", ""),
                                ('RESET', "Clear Override", "")])
    selected: BoolProperty(name="Use selected faces", default=True)
    review_only: BoolProperty(name="Only change Review faces", default=False)

    def invoke(self, context, event):
        if self.action == 'HIDE':
            return context.window_manager.invoke_confirm(
                self, event, title="Manual Hide", message="Hide can override exposure or uncertainty. Evidence stays visible.")
        return self.execute(context)

    @classmethod
    def description(cls, context, properties):
        return {
            'KEEP': "Always show the selected faces in the output",
            'HIDE': "Hide the selected faces in the output. Asks first; Ctrl+Z undoes it",
            'RESET': "Remove your Keep / Hide from the selected faces and use the automatic result",
        }.get(properties.action, cls.bl_description)

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
            elif was_edit and context.edit_object != s.body:
                raise adapter.InputError(leave_other_edit_mode_message(context))
            if was_edit:
                bpy.ops.object.mode_set(mode='OBJECT')
            report = workflow.fresh_report(context, s).copy()
            report['overrides'] = report['overrides'].copy()
            if preview_indices is not None:
                indices = preview_indices
            elif self.selected:
                indices = [p.index for p in s.body.data.polygons if p.select]
            else:
                indices = [s.face_index]
            if not indices:
                raise adapter.InputError("No faces selected: press Box, Lasso or Brush, then drag over faces")
            if self.review_only and self.action != 'RESET':
                indices = review_faces_only(report, indices)
                if not indices:
                    raise adapter.InputError(
                        "No Review faces in the selection; turn off 'Only change Review faces' to change others")
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
                redrawn = adapter.preview(context, workflow.read_report(s), s.preview_mode)
            else:
                adapter.clear_preview(context.scene)
            caption = {'KEEP': "Keep", 'HIDE': "Hide", 'RESET': "Clear"}[self.action]
            follow_up = "; select more or press Done" if editing_preview and redrawn else ""
            self.report({'INFO'}, f"{caption} applied to {len(indices)} faces{follow_up}")
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


class UNDERWHERE_OT_apply(SafeOperator, Operator):
    bl_idname = "underwhere.apply"
    bl_label = "Apply to New Copy"
    bl_description = "Create an independent Body copy with a new group and Mask; preserve source"
    bl_options = {'REGISTER', 'UNDO'}
    deleted: BoolProperty(name="Create deleted copy", default=False,
                         description="Remove verified vertices on a new copy, preserving shape keys, weights and UVs for FBX")

    def invoke(self, context, event):
        try:
            self.available(context)
            report = workflow.fresh_report(context, context.scene.underwhere, verify=False)
            plan = report["output_plan"]
            self.report({'INFO'}, f"Output: {plan['hidden_polygon_count']} polygons hidden")
            return context.window_manager.invoke_props_dialog(self, width=440)
        except Exception as exc:
            return self.fail(context, exc)

    def draw(self, context):
        report = workflow.read_report(context.scene.underwhere)
        plan = report["output_plan"]
        self.layout.label(text=f"Output hides {plan['hidden_polygon_count']} polygons / "
                               f"{plan['hidden_triangle_count']} triangles")
        self.layout.label(text="Creates a copy at the source position.")
        self.layout.label(text="Original object and its masks are preserved.")
        self.layout.label(text="Inspected frames (first = current pose):")
        caption = workflow.state_caption(report)
        for offset in range(0, len(caption), 60):
            self.layout.label(text=caption[offset:offset + 60])
        self.layout.prop(self, 'deleted')
        if plan["manual_risk_faces"]:
            self.layout.label(text=f"{len(plan['manual_risk_faces'])} risky manual Hide overrides",
                              icon='ERROR')
        if plan.get("retained_uncertain_faces"):
            self.layout.label(text=f"{len(plan['retained_uncertain_faces'])} undecided faces stay hidden "
                                   "(existing mask kept)", icon='ERROR')

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
            self.report({'INFO'}, f"Created {output['object']}; source preserved")
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)
        finally:
            workflow.BUSY.discard(key)


class UNDERWHERE_OT_export(SafeOperator, Operator, ExportHelper):
    bl_idname = "underwhere.export"
    bl_label = "Export Shareable Report"
    bl_description = "Save a summary without mesh coordinates, connectivity, object/material names or personal paths"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})
    private: BoolProperty(name="Private full diagnostics (contains mesh data)", default=False,
                          description="Includes purchased mesh geometry and names; do not attach to public issues")

    def execute(self, context):
        try:
            self.available(context)
            workflow.export_report(context, context.scene.underwhere, self.filepath, private=self.private)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_OT_repair_policy(SafeOperator, Operator):
    bl_idname = "underwhere.repair_policy"
    bl_label = "Repair Policy"
    bl_description = "Choose which existing hides an Audit restores; evidence is unchanged"
    bl_options = {'REGISTER', 'UNDO'}
    policy: EnumProperty(items=[
        (RESTORE_UNRESOLVED, "Restore exposed + undecided",
         "Keep only confirmed candidates hidden (strict)"),
        (RESTORE_EXPOSED, "Restore exposed only",
         "Keep the existing mask where no exposure was observed; undecided faces stay hidden"),
    ])

    def execute(self, context):
        try:
            self.available(context)
            s = context.scene.underwhere
            report = workflow.fresh_report(context, s).copy()
            if report["input"]["mode"] != "AUDIT":
                raise adapter.InputError("Repair policy applies to Audit results only")
            report["repair_policy"] = self.policy
            report["output_verification"] = adapter.measure_plan(context, s, report)
            workflow.save_report(s, report)
            adapter.clear_preview(context.scene)
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(context, exc)


class UNDERWHERE_UL_occluders(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "object", text="", emboss=True)


class UNDERWHERE_UL_issues(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=f"Face {item.face}: {reason_label(item.label)}", icon='ERROR')


def status_icon(status):
    if status.startswith("STALE"):
        return 'ERROR'
    if status.startswith("CHECK"):
        return 'TIME'
    if status.startswith("Cancelled"):
        return 'CANCEL'
    if status == "READY" or status.startswith("Preflight OK"):
        return 'CHECKMARK'
    return 'INFO'


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


LEGENDS = {
    'CLASSIFY': [("Candidate", 'COLLECTION_COLOR_04'), ("Keep", 'COLLECTION_COLOR_05'),
                 ("Review", 'COLLECTION_COLOR_03'), ("Mask hides exposed", 'COLLECTION_COLOR_01'),
                 ("Mask hides undecided", 'COLLECTION_COLOR_06')],
    'DIFF': [("Newly hidden", 'COLLECTION_COLOR_04'), ("Restored", 'COLLECTION_COLOR_05'),
             ("Still hidden", 'COLLECTION_COLOR_08'), ("Visible", 'OUTLINER_COLLECTION')],
}


class UNDERWHERE_PT_main(Panel):
    bl_label = "UnderWhere"
    bl_idname = "UNDERWHERE_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "UnderWhere"

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        box = layout.box()
        box.label(text=s.status, icon=status_icon(s.status))
        if is_busy(context):
            box.prop(s, "progress", text="Progress")
            box.operator("underwhere.cancel", icon='CANCEL')
        elif s.result_json and current_report(context) is None:
            box.label(text="Result unavailable; Analyze again", icon='ERROR')


class SubPanel:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "UnderWhere"
    bl_parent_id = "UNDERWHERE_PT_main"


class ResultPanel(SubPanel):
    @classmethod
    def poll(cls, context):
        return current_report(context) is not None


class UNDERWHERE_PT_inputs(SubPanel, Panel):
    bl_label = "1  Inputs"
    bl_idname = "UNDERWHERE_PT_inputs"

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not is_busy(context)
        layout.operator("underwhere.use_selection", icon='RESTRICT_SELECT_OFF')
        layout.prop(s, "body")
        layout.label(text="Occluders")
        row = layout.row()
        row.template_list("UNDERWHERE_UL_occluders", "", s, "occluders", s, "occluder_index", rows=3)
        buttons = row.column(align=True)
        buttons.operator("underwhere.occluder", text="", icon='ADD')
        buttons.operator("underwhere.occluder", text="", icon='REMOVE').remove = True
        layout.prop(s, "mode", expand=True)
        if s.mode == 'AUDIT' and s.body:
            layout.prop_search(s, "existing_mask", s.body, "modifiers", icon='MOD_MASK')


class UNDERWHERE_PT_inspection(SubPanel, Panel):
    bl_label = "2  Inspection"
    bl_idname = "UNDERWHERE_PT_inspection"

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not is_busy(context)
        layout.label(text="States")
        layout.prop(s, "scope", expand=True)
        if s.scope == 'EXPLICIT_FRAMES':
            layout.prop(s, "frames")
        layout.label(text="Work budget")
        layout.prop(s, "preset", expand=True)
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("underwhere.preflight", icon='CHECKMARK')
        row.operator("underwhere.analyze", icon='PLAY')


class UNDERWHERE_PT_materials(SubPanel, Panel):
    bl_label = "Materials"
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
            layout.label(text="No occluder materials")
            return
        layout.label(text="Assume opaque is your own assumption", icon='INFO')
        for material in sorted(materials, key=lambda m: m.name):
            policy = adapter.material_policy(material)
            trusted = policy['automatic_verdict'] == "CONSTANT_OPAQUE_PRINCIPLED"
            column = layout.column(align=True)
            row = column.row()
            row.label(text=material.name, icon='MATERIAL')
            toggle = row.row()
            toggle.enabled = not policy['assumption_blocked'] and not trusted
            toggle.prop(material, 'underwhere_assume_opaque', text="Opaque")
            if trusted:
                column.label(text="Auto: trusted", icon='CHECKMARK')
            elif policy['assumption_blocked']:
                column.label(text="Backface culling: cannot assume", icon='ERROR')
            else:
                column.label(text="Auto: " + reason_label(policy['automatic_verdict']), icon='QUESTION')


class UNDERWHERE_PT_advanced(SubPanel, Panel):
    bl_label = "Advanced"
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
        layout.label(text=f"Scene scale: {context.scene.unit_settings.scale_length:g} m / unit")


class UNDERWHERE_PT_results(ResultPanel, Panel):
    bl_label = "3  Results"
    bl_idname = "UNDERWHERE_PT_results"

    def draw(self, context):
        s = context.scene.underwhere
        report = current_report(context)
        plan = report["output_plan"]
        counts = report["counts"]
        layout = self.layout
        grid = layout.grid_flow(columns=3, even_columns=True, align=True)
        for label, caption, icon in [(CANDIDATE, "Candidate", 'COLLECTION_COLOR_04'),
                                     (KEEP, "Keep", 'COLLECTION_COLOR_05'),
                                     (REVIEW, "Review", 'COLLECTION_COLOR_03')]:
            grid.label(text=f"{caption} {counts.get(label, 0)}", icon=icon)
        layout.label(text=f"Output hides {plan['hidden_polygon_count']} faces", icon='MOD_MASK')
        layout.label(text="States: " + workflow.state_caption(report)[:48], icon='TIME')
        if report["input"]["mode"] == "AUDIT":
            box = layout.box()
            existing = len(report["existing_mask"]["hidden_faces"])
            box.label(text=f"Existing mask hides {existing} faces", icon='MOD_MASK')
            findings = report["findings"]
            if findings.get(UNSAFE):
                box.label(text=f"Hides exposed faces: {findings[UNSAFE]}", icon='COLLECTION_COLOR_01')
            if findings.get(UNCERTAIN):
                box.label(text=f"Hides undecided faces: {findings[UNCERTAIN]}", icon='COLLECTION_COLOR_06')
            box.label(text=f"Restored {len(plan['restored_existing_faces'])}, "
                           f"newly hidden {len(plan['newly_hidden_faces'])}")
        warnings = []
        mask_warning = existing_mask_warning(report["input"]["mode"], report["existing_mask"],
                                             len(report["faces"]))
        if mask_warning:
            warnings.append(reason_label(mask_warning))
        for issue in report.get("occluder_issues", []):
            reasons = ", ".join(reason_label(code) for code in issue["reason_codes"])
            warnings.append(f"{issue['object']}: {reasons}")
        if plan["manual_risk_faces"]:
            warnings.append(f"Manual Hide over Keep/Review: {len(plan['manual_risk_faces'])} faces")
        if plan.get("retained_uncertain_faces"):
            warnings.append(f"Undecided faces kept hidden: {len(plan['retained_uncertain_faces'])}")
        assumed = report.get("assumptions", {}).get("dependent_candidate_faces", 0)
        if assumed:
            warnings.append(f"Candidates relying on Assume opaque: {assumed}")
        if plan.get("kept_at_shared_vertices"):
            warnings.append(f"Candidates kept at shared vertices: {len(plan['kept_at_shared_vertices'])}")
        if warnings:
            box = layout.box()
            for line in warnings:
                box.label(text=line, icon='ERROR')


class UNDERWHERE_PT_review(ResultPanel, Panel):
    bl_label = "4  Review and Fix"
    bl_idname = "UNDERWHERE_PT_review"

    def draw(self, context):
        s = context.scene.underwhere
        report = current_report(context)
        layout = self.layout
        layout.enabled = not s.status.startswith("STALE")

        column = layout.column(align=True)
        row = column.row(align=True)
        row.prop(s, "preview_mode", text="")
        row.operator("underwhere.preview", text="Update Comparison", icon='FILE_REFRESH')
        legend = LEGENDS.get(s.preview_mode)
        if legend:
            grid = column.grid_flow(columns=2, even_columns=True, align=True)
            for caption, icon in legend:
                grid.label(text=caption, icon=icon)
        column.label(text="Shown beside the Body; use Material Preview", icon='INFO')

        layout.label(text="Fix faces")
        box = layout.box()
        selecting = selecting_on(context, s)
        tool = active_selection_tool(context) if selecting else None

        box.label(text="1  Choose faces")
        box.prop(s, "selection_target", expand=True)
        row = box.row(align=True)
        row.scale_y = 1.3
        for key, caption, icon in [('BOX', "Box", 'SELECT_SET'), ('LASSO', "Lasso", 'CURVE_BEZCURVE'),
                                   ('CIRCLE', "Brush", 'BRUSH_DATA')]:
            op = row.operator("underwhere.edit_selection", text=caption, icon=icon,
                              depress=selecting == s.selection_target and tool == key)
            op.target = s.selection_target
            op.tool = key
        hint = box.column(align=True)
        if not selecting:
            hint.label(text="Press Box, Lasso or Brush to start", icon='INFO')
        else:
            count = context.edit_object.data.total_face_sel
            where = "comparison" if selecting == 'COMPARISON' else "Body"
            if count:
                hint.label(text=f"{count} faces selected on the {where}", icon='CHECKMARK')
            else:
                hint.label(text=f"Drag over faces on the {where}", icon='MOUSE_LMB_DRAG')
            hint.label(text="Shift adds, Ctrl removes", icon='BLANK1')
        review_count = report["counts"].get(REVIEW, 0)
        existing_count = sum(report["findings"].values())
        if review_count or existing_count:
            row = box.row(align=True)
            if review_count:
                row.operator("underwhere.select_group", text=f"All Review ({review_count})",
                             icon='RESTRICT_SELECT_OFF').group = 'REVIEW'
            if existing_count:
                row.operator("underwhere.select_group", text=f"Mask issues ({existing_count})",
                             icon='RESTRICT_SELECT_OFF').group = 'EXISTING'

        box.separator()
        box.label(text="2  Change them")
        box.prop(s, "override_review_only", text="Only change Review faces")
        row = box.row(align=True)
        row.scale_y = 1.3
        for action, caption, icon in [('KEEP', "Keep", 'HIDE_OFF'), ('HIDE', "Hide", 'HIDE_ON'),
                                      ('RESET', "Clear", 'X')]:
            op = row.operator("underwhere.override", text=caption, icon=icon)
            op.action = action
            op.review_only = s.override_review_only
        if selecting:
            box.operator("underwhere.finish_selection", text="Done (back to Object Mode)",
                         icon='CHECKMARK')

        if report["input"]["mode"] == "AUDIT":
            policy = report["output_plan"].get("repair_policy") or RESTORE_UNRESOLVED
            layout.label(text="Repair existing mask")
            column = layout.column(align=True)
            for value, caption in [(RESTORE_UNRESOLVED, "Restore exposed + undecided"),
                                   (RESTORE_EXPOSED, "Restore exposed only")]:
                column.operator("underwhere.repair_policy", text=caption,
                                depress=policy == value).policy = value


class UNDERWHERE_PT_reasons(ResultPanel, Panel):
    bl_label = "Select by Reason"
    bl_idname = "UNDERWHERE_PT_reasons"
    bl_parent_id = "UNDERWHERE_PT_review"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not s.status.startswith("STALE")
        reasons = review_reason_counts(current_report(context))
        if not reasons:
            layout.label(text="No undecided faces", icon='CHECKMARK')
            return
        layout.label(text="Selects on the Body; then Keep / Hide above", icon='INFO')
        column = layout.column(align=True)
        for code, count in reasons[:8]:
            op = column.operator("underwhere.select_group",
                                 text=f"{reason_label(code)} ({count})", icon='DOT')
            op.group = 'REASON'
            op.reason = code
            hint = reason_hint(code)
            if hint:
                column.label(text=hint, icon='LIGHT')


class UNDERWHERE_PT_faces(ResultPanel, Panel):
    bl_label = "Face by Face"
    bl_idname = "UNDERWHERE_PT_faces"
    bl_parent_id = "UNDERWHERE_PT_review"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.underwhere
        report = current_report(context)
        layout = self.layout
        layout.enabled = not s.status.startswith("STALE")
        if s.issues:
            layout.template_list('UNDERWHERE_UL_issues', '', s, 'issues', s, 'issue_index', rows=4)
        else:
            layout.label(text="No issues", icon='CHECKMARK')
        box = layout.box()
        box.prop(s, "face_index")
        if s.face_index < len(report["faces"]):
            face = report["faces"][s.face_index]
            box.label(text=reason_label(face["finding"] or face["verdict"]))
            for reason in face["reason_codes"]:
                box.label(text=reason_label(reason))
            if face["witness"] and face["witness"].get("material"):
                box.label(text="Material: " + face["witness"]["material"], icon='MATERIAL')
            hints = {reason_hint(code) for code in face["reason_codes"]} - {None}
            for hint in sorted(hints):
                box.label(text=hint, icon='LIGHT')
        row = box.row(align=True)
        row.operator("underwhere.face", text="Select", icon='RESTRICT_SELECT_OFF').action = 'SELECT'
        row.operator("underwhere.face", text="Next", icon='TRIA_RIGHT').action = 'NEXT'
        row.operator("underwhere.face", text="View Ray", icon='HIDE_OFF').action = 'VIEW'
        layout.label(text="Select puts the face on the Body; then Keep / Hide above", icon='INFO')


class UNDERWHERE_PT_output(ResultPanel, Panel):
    bl_label = "5  Output"
    bl_idname = "UNDERWHERE_PT_output"

    def draw(self, context):
        s = context.scene.underwhere
        layout = self.layout
        layout.enabled = not s.status.startswith("STALE")
        column = layout.column(align=True)
        column.scale_y = 1.2
        column.operator("underwhere.apply", text="Apply to New Copy", icon='MOD_MASK')
        column.operator("underwhere.apply", text="Create Deleted Copy (FBX)",
                        icon='MESH_DATA').deleted = True
        layout.operator("underwhere.export", icon='EXPORT')
        layout.label(text="Object Mode; the source is not modified", icon='INFO')


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
    objects = {settings.body} | {item.object for item in settings.occluders}
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
    UNDERWHERE_OT_preflight, UNDERWHERE_OT_analyze, UNDERWHERE_OT_cancel,
    UNDERWHERE_OT_preview, UNDERWHERE_OT_face, UNDERWHERE_OT_override, UNDERWHERE_OT_apply,
    UNDERWHERE_OT_export, UNDERWHERE_OT_repair_policy, UNDERWHERE_OT_select_group,
    UNDERWHERE_OT_edit_selection, UNDERWHERE_OT_finish_selection,
    UNDERWHERE_UL_occluders, UNDERWHERE_UL_issues,
    UNDERWHERE_PT_main, UNDERWHERE_PT_inputs, UNDERWHERE_PT_inspection, UNDERWHERE_PT_materials,
    UNDERWHERE_PT_advanced, UNDERWHERE_PT_results, UNDERWHERE_PT_review,
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
            name="Assume opaque", default=False, update=input_changed,
            description="User assumption: this entire material is opaque on both sides, with no transmission or displacement. Recorded in reports; not automatic proof")
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
