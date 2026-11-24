"""Automated GUI event-loop smoke in a fresh, disposable Blender window.

This is not a human usability review. Writes evidence then closes only its own
Blender process. Do not run in a working scene.
"""
from pathlib import Path
import json
import sys
import traceback
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))
sys.path.insert(0, str(Path(__file__).parent))
import underwhere
from underwhere import workflow, ui, overlay
import fixtures as fx

OUT = ROOT / "outputs/underwhere"
OUT.mkdir(parents=True, exist_ok=True)
underwhere.register()
bpy.context.preferences.view.show_splash = False
stage = 0
checks = []
ticks = 0


def tick():
    global stage, ticks
    try:
        area = next(a for a in bpy.context.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(area=area, region=region):
            s = bpy.context.scene.underwhere
            if stage == 0:
                fx.setup()
                bpy.ops.ed.undo_push(message='Before modal edit')
                s.angle = 60
                bpy.ops.ed.undo_push(message='Modal input edit')
                assert bpy.ops.underwhere.analyze('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
                bpy.ops.ed.undo()
                assert not workflow.BUSY
                assert bpy.context.scene.underwhere.status.startswith('Cancelled')
                checks.append('undo_during_modal_cleanup')
                checks.append('undo_cancellation_status')
                fx.setup()
                s = bpy.context.scene.underwhere
                area.spaces.active.show_region_ui = True
                area.spaces.active.region_3d.view_location = Vector((0, 0, 0))
                area.spaces.active.region_3d.view_distance = 4
                # Hide clothing only for a later screenshot; inputs are visible
                # during all analyses.
                assert bpy.ops.underwhere.analyze('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
                s.cancel_requested = True
                stage = 1
            elif stage == 1:
                if workflow.BUSY:
                    ticks += 1
                    assert ticks < 100, "cancel timeout"
                    return .1
                assert s.status.startswith("Cancelled") and not s.result_json
                checks.append("modal_cancel")
                assert bpy.ops.underwhere.analyze('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
                stage = 2
            elif stage == 2:
                if workflow.BUSY:
                    ticks += 1
                    assert ticks < 100, "analysis timeout"
                    return .1
                workflow.fresh_report(bpy.context, s)
                assert s.status == "READY"
                checks.append("modal_complete")
                bpy.ops.ed.undo_push(message="Analysis")
                s.angle = 60
                bpy.ops.ed.undo_push(message="Adjusted input")
                assert bpy.ops.underwhere.analyze('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
                bpy.ops.ed.undo()
                s = bpy.context.scene.underwhere
                assert s.result_json and s.status.startswith('Cancelled')
                ui.freshness_timer()
                assert s.status.startswith('Cancelled')
                workflow.fresh_report(bpy.context, s)
                checks.append('undo_cancellation_with_previous_result')
                bpy.ops.underwhere.override(action='KEEP', selected=False)
                bpy.ops.ed.undo_push(message="Manual Keep")
                bpy.ops.ed.undo()
                assert not workflow.read_report(bpy.context.scene.underwhere)["overrides"]
                bpy.ops.ed.redo()
                assert workflow.read_report(bpy.context.scene.underwhere)["overrides"] == {"0": "KEEP"}
                assert len(bpy.context.scene.underwhere.result_json) < 256
                checks.append("manual_undo_redo")
                checks.append('compact_reference_undo_redo')
                stage = 3
            elif stage == 3:
                before = len(bpy.data.objects)
                bpy.ops.underwhere.apply()
                bpy.ops.ed.undo_push(message="Apply")
                assert len(bpy.data.objects) == before + 1
                bpy.ops.ed.undo()
                assert len(bpy.data.objects) == before
                bpy.ops.ed.redo()
                assert len(bpy.data.objects) == before + 1
                checks.append("apply_undo_redo")
                stage = 4
            elif stage == 4:
                fx.setup('tube')
                assert bpy.ops.underwhere.analyze() == {'FINISHED'}
                bpy.ops.underwhere.face(action='SELECT')
                bpy.ops.underwhere.face(action='NEXT')
                bpy.ops.underwhere.face(action='SELECT')
                bpy.ops.underwhere.face(action='VIEW')
                assert bpy.context.mode == 'EDIT_MESH'
                bpy.ops.object.mode_set(mode='OBJECT')
                checks.append('edit_select_next_focus_view')
                bpy.ops.underwhere.apply(deleted=True)
                checks.append('deleted_copy_operator')
                bpy.ops.underwhere.preview()
                # The colours drawn on the Body itself, through and behind the clothing.
                s.display_target = 'ON_BODY'
                assert overlay.is_shown(bpy.context.scene), s.status
                for xray in (True, False):
                    s.overlay_xray = xray
                    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                    assert overlay.STATS["last_error"] is None, overlay.STATS["last_error"]
                assert overlay.STATS["draws"] >= 2, "on-Body colours were not drawn"
                s.display_target = 'BESIDE'
                checks.append("on_body_overlay_draw")
                for material in bpy.context.scene.underwhere.occluders[0].object.data.materials:
                    material.use_backface_culling = True
                area.spaces.active.shading.color_type = 'MATERIAL'
                area.spaces.active.region_3d.view_location = Vector((.5, 0, 0))
                checks.append("preview_operator")
                bpy.ops.wm.call_panel(name="UNDERWHERE_PT_main", keep_open=True)
                checks.append("panel_draw_popup")
                stage = 5
            elif stage == 5:
                bpy.ops.screen.screenshot(filepath=str(OUT / "gui_smoke.png"))
                checks.append("viewport_screenshot")
                temporary = bpy.data.scenes.new('Modal scene deletion')
                bpy.context.window.scene = temporary
                fx.setup()
                assert bpy.ops.underwhere.analyze('INVOKE_DEFAULT') == {'RUNNING_MODAL'}
                bpy.data.scenes.remove(temporary)
                stage = 6
            elif stage == 6:
                if workflow.BUSY:
                    ticks += 1
                    assert ticks < 100, 'deleted scene cleanup timeout'
                    return .1
                checks.append('scene_deleted_during_modal_cleanup')
                underwhere.unregister()
                underwhere.register()
                checks.append("gui_disable_reenable")
                (OUT / "gui_summary.json").write_text(json.dumps({
                    "status": "PASS", "blender": bpy.app.version_string,
                    "checks": checks, "human_review": False,
                }, indent=2))
                bpy.ops.wm.quit_blender()
                return None
        return .25
    except Exception:
        (OUT / "gui_summary.json").write_text(json.dumps({
            "status": "FAIL", "stage": stage, "checks": checks,
            "traceback": traceback.format_exc(),
        }, indent=2))
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(tick, first_interval=1)
