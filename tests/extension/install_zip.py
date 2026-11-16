"""Official Extension install/enable/disable/re-enable/uninstall in an isolated repo."""
import hashlib
import importlib
import json
from pathlib import Path
import sys
import uuid
import tomllib

import addon_utils
import bpy

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/underwhere"
version = tomllib.loads((ROOT / 'addon/underwhere/blender_manifest.toml').read_text())["version"]
package = ROOT / "dist" / f"underwhere-{version}.zip"
destination = OUT / ("install_" + uuid.uuid4().hex)
destination.mkdir(parents=True)
bpy.context.preferences.use_preferences_save = False
repo = bpy.context.preferences.extensions.repos.new(
    name="UnderWhere isolated package test", module="underwhere_local_test",
    custom_directory=str(destination))
repo.use_remote_url = False
repo.use_custom_directory = True
module = "bl_ext." + repo.module + ".underwhere"
checks = []
try:
    result = bpy.ops.extensions.package_install_files(
        filepath=str(package), repo=repo.module, enable_on_install=True)
    assert result == {'FINISHED'}, result
    extension = importlib.import_module(module)
    assert Path(extension.__file__).is_relative_to(destination)
    assert extension.ui.UNDERWHERE_PT_main.bl_label == 'UnderWhere'
    assert extension.ui.UNDERWHERE_PT_main.bl_category == 'UnderWhere'
    installed_manifest = tomllib.loads((destination / 'underwhere/blender_manifest.toml').read_text())
    assert installed_manifest['id'] == 'underwhere'
    assert installed_manifest['name'] == 'UnderWhere'
    assert installed_manifest['website'] == 'https://github.com/marc2825/BodyOcclusionCuller'
    assert hasattr(bpy.types.Scene, "underwhere")
    checks.append("official_zip_install_enable")
    sys.path.insert(0, str(ROOT / "tests/extension"))
    import fixtures
    fixtures.setup()
    assert bpy.ops.underwhere.analyze() == {'FINISHED'}
    assert bpy.ops.underwhere.preview() == {'FINISHED'}
    assert bpy.ops.underwhere.apply() == {'FINISHED'}
    assert bpy.ops.underwhere.apply(deleted=True) == {'FINISHED'}
    workflow = importlib.import_module(module + ".workflow")
    workflow.export_report(bpy.context, bpy.context.scene.underwhere,
                           str(OUT / "installed_package_report.json"))
    shared = json.loads((OUT / 'installed_package_report.json').read_text())
    assert shared['report_kind'] == 'SHAREABLE_SUMMARY'
    assert shared['current_pose_always_included']
    assert len(bpy.context.scene.underwhere.result_json) < 256
    assert 'preview_vertices' not in shared and 'source_polygons' not in shared
    checks.append("installed_generate_preview_apply_export")
    body, _, settings = fixtures.setup("tube")
    fixtures.mask(body)
    assert bpy.ops.underwhere.analyze() == {'FINISHED'}
    report = workflow.read_report(settings)
    assert report["findings"] == {"UNSAFE_EXISTING_MASK": 6}
    checks.append("installed_audit")
    _, shell, settings = fixtures.slit(.00001)
    settings.preset = 'BALANCED'
    shell.modifiers.new('Rim', 'SOLIDIFY')
    assert bpy.ops.underwhere.analyze() == {'FINISHED'}
    assert workflow.read_report(settings)['output_plan']['hidden_polygon_count'] == 0
    checks.append('installed_solidify_slit_refusal')
    body, _, settings = fixtures.setup()
    body.location.x = 0
    body.keyframe_insert('location', frame=1)
    body.location.x = 4
    body.keyframe_insert('location', frame=5)
    bpy.context.scene.frame_set(5)
    settings.scope = 'EXPLICIT_FRAMES'
    settings.frames = '1'
    assert bpy.ops.underwhere.analyze() == {'FINISHED'}
    assert workflow.read_report(settings)['counts'] == {'KEEP_EXPOSED': 6}
    checks.append('installed_current_pose_protection')
    _, shell, settings = fixtures.setup()
    shell.data.materials[0].use_backface_culling = True
    shell.data.materials[0].underwhere_assume_opaque = True
    assert bpy.ops.underwhere.analyze() == {'FINISHED'}
    assert workflow.read_report(settings)['counts'] == {'REVIEW': 6}
    checks.append('installed_culling_assumption_refusal')
    addon_utils.disable(module, default_set=True)
    assert not hasattr(bpy.types.Scene, "underwhere")
    addon_utils.enable(module, default_set=True)
    assert hasattr(bpy.types.Scene, "underwhere")
    checks.append("disable_reenable")
    # Installed files match the built ZIP, not repository imports.
    import zipfile
    with zipfile.ZipFile(package) as archive:
        for info in archive.infolist():
            if not info.is_dir():
                assert (destination / "underwhere" / info.filename).read_bytes() == archive.read(info)
    checks.append("installed_file_integrity")
    result = bpy.ops.extensions.package_uninstall(
        repo_index=list(bpy.context.preferences.extensions.repos).index(repo), pkg_id="underwhere")
    assert result == {'FINISHED'}
    assert not (destination / "underwhere").exists()
    assert not hasattr(bpy.types.Scene, "underwhere")
    checks.append("official_uninstall")
finally:
    # This process never saves preferences; leave user repositories untouched.
    bpy.context.preferences.extensions.repos.remove(repo)

(OUT / "install_summary.json").write_text(json.dumps({
    "blender": bpy.app.version_string, "status": "PASS", "checks": checks,
    "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
    "repository": str(destination), "preferences_saved": False,
}, indent=2))
print("INSTALL_TEST_PASS", len(checks))
