"""Create an original synthetic demo in a new Blender process.

blender --background --factory-startup --python scripts/extension/create_sample.py
No real avatar, external material, texture or model is used.
"""
from pathlib import Path
import sys
import re
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))
sys.path.insert(0, str(ROOT / "tests/extension"))
import underwhere
import fixtures

if not hasattr(bpy.types.Scene, "underwhere"):
    underwhere.register()
body, shell, settings = fixtures.setup("closed")
body.name = "Demo_Body"
shell.name = "Demo_Armor"
body.data.clear_geometry()
body.data.from_pydata(
    [(x * .15, y * .15, z * .15) for x, y, z in fixtures.VERTICES] +
    [(x * .1, y * .1, z * .1 + .6) for x, y, z in fixtures.VERTICES], [],
    list(fixtures.POLYGONS) + [tuple(i + 8 for i in p) for p in fixtures.POLYGONS])
body.data.update()
shell.scale = (.3, .3, .3)
settings.preset = 'BALANCED'
body.shape_key_add(name='Basis')
key = body.shape_key_add(name='Expression')
key.data[8].co.x += .02
body.data.uv_layers.new(name='UVMap')
body.vertex_groups.new(name='DemoWeight').add(list(range(16)), 1.0, 'REPLACE')
shell.data.materials[0].diffuse_color = (.08, .3, .55, 1)
body.data.materials.append(fixtures.material("BodySurface"))
body.data.materials[0].diffuse_color = (.65, .3, .15, 1)
text = bpy.data.texts.new("START_HERE")
text.use_fake_user = True
text.write("""UnderWhere demo / 合成サンプル
1. Install the Extension ZIP and open Sidebar > UnderWhere.
2. Body = Demo_Body, occluder = Demo_Armor (Use Selection also works).
3. Preflight > Analyze > Classification > Update Comparison.
4. The lower block is covered; the upper block stays exposed. Select faces
   in Edit Mode; Keep / Hide / Clear.
5. Return to Object Mode. Create Deleted Copy preserves Expression/UV/weights.
6. Export the deleted copy and its Armature, if any, with Apply Modifiers OFF.
Export Shareable Report omits mesh data. Private full diagnostics contain it.
Current pose is always inspected. Add integer frames with Current + Selected Frames.
Intermediate poses remain untested.
See docs/user/QUICKSTART_JA.md for the full workflow.
""")
bpy.context.view_layer.update()
bpy.data.orphans_purge(do_recursive=True)
# Factory startup can inherit the user's file-browser directory from their
# system documents location. Never embed that path in the public demo.
for screen in bpy.data.screens:
    for area in screen.areas:
        for space in area.spaces:
            if space.type == 'FILE_BROWSER' and space.params:
                # RNA writes a terminating NUL but can leave old bytes in the
                # fixed-size DNA buffer. Overwrite its former contents first.
                space.params.directory = b'_' * len(space.params.directory)
                space.params.directory = b'//'
out = ROOT / "dist"
out.mkdir(exist_ok=True)
bpy.context.preferences.filepaths.save_version = 0
demo = out / 'underwhere_demo.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(demo), compress=False)
# An uncompressed file makes this release check inspect the actual DNA bytes,
# including stale fixed-buffer tails, without an extra Python dependency.
payload = demo.read_bytes()
assert payload.startswith(b'BLENDER'), 'Expected an uncompressed demo for privacy inspection'
private_patterns = [rb'/' + rb'home/[^/\x00 ]+/', rb'Users[\\/][^\\/\x00 ]+',
                    rb'home[\\/][^\\/\x00 ]+', rb'OneDrive',
                    rb'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}']
assert not any(re.search(pattern, payload, re.IGNORECASE) for pattern in private_patterns), 'Private path/email in demo'
from underwhere import workflow
report = workflow.run_sync(bpy.context, settings)
assert report["counts"] == {"HIDE_CANDIDATE": 6, "KEEP_EXPOSED": 6}, report["counts"]
assert report["output_plan"]["hidden_polygon_count"] == 6
workflow.export_report(bpy.context, settings, str(ROOT / "outputs/underwhere/sample_report.json"))
print("SAMPLE_CREATED", out / "underwhere_demo.blend")
