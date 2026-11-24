"""Run with Blender --background --factory-startup --python-exit-code 1."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))
sys.path.insert(0, str(Path(__file__).parent))
import underwhere
from underwhere import blender_adapter as adapter, workflow, ui, i18n
from underwhere.core.contracts import CANDIDATE, KEEP, REVIEW, UNSAFE, UNCERTAIN
import fixtures as fx

OUT = ROOT / "outputs/underwhere"
OUT.mkdir(parents=True, exist_ok=True)


class BlenderIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        underwhere.register()

    @classmethod
    def tearDownClass(cls):
        underwhere.unregister()

    def analyze(self, s):
        return workflow.run_sync(bpy.context, s)

    def test_01_closed_shell_and_actual_output(self):
        body, _, s = fx.setup()
        body.data.materials.append(fx.material("BodyMaterial"))
        before = adapter.snapshot(bpy.context, s)[1]
        report = self.analyze(s)
        self.assertEqual(report["counts"], {CANDIDATE: 6})
        self.assertEqual(report["output_plan"]["hidden_polygon_count"], 6)
        self.assertTrue(report["output_verification"]["verified_with_blender"])
        self.assertEqual(bpy.ops.underwhere.apply(), {'FINISHED'})
        output = workflow.read_report(s)["outputs"][-1]
        self.assertEqual(output["evaluated_remaining_polygons"], 0)
        self.assertEqual(adapter.snapshot(bpy.context, s)[1], before)
        self.assertEqual(len(body.modifiers), 0)

    def test_02_open_tube_exposes(self):
        _, _, s = fx.setup("tube")
        r = self.analyze(s)
        self.assertEqual(r["counts"], {KEEP: 6})
        self.assertEqual(r["output_plan"]["hidden_polygon_count"], 0)

    def test_03_unknown_nearest_does_not_skip_to_opaque(self):
        _, shell, s = fx.setup(alpha=.2)
        outer = fx.cube("FarOpaque", 2, mat=fx.material())
        s.occluders.add().object = outer
        r = self.analyze(s)
        self.assertEqual(r["counts"], {REVIEW: 6})
        self.assertEqual(r["output_plan"]["hidden_polygon_count"], 0)

    def test_04_missing_unknown_and_culling_materials(self):
        for kind in ("missing", "glass", "culling", "linked_alpha"):
            with self.subTest(kind=kind):
                _, shell, s = fx.setup()
                mat = shell.data.materials[0]
                if kind == "missing":
                    shell.data.materials.clear()
                elif kind == "glass":
                    nodes = mat.node_tree.nodes
                    glass = nodes.new("ShaderNodeBsdfGlass")
                    mat.node_tree.links.new(glass.outputs[0], nodes["Material Output"].inputs["Surface"])
                elif kind == "culling":
                    mat.use_backface_culling = True
                else:
                    value = mat.node_tree.nodes.new("ShaderNodeValue")
                    value.outputs[0].default_value = 1
                    mat.node_tree.links.new(value.outputs[0],
                                           mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"])
                self.assertEqual(self.analyze(s)["counts"], {REVIEW: 6})

    def test_05_existing_exposed_and_uncertain(self):
        for kind, alpha, expected in [("tube", 1, UNSAFE), ("closed", .1, UNCERTAIN)]:
            with self.subTest(kind=kind):
                body, _, s = fx.setup(kind, alpha)
                mod = fx.mask(body)
                before = adapter.snapshot(bpy.context, s)[1]
                r = self.analyze(s)
                self.assertEqual(len(r["existing_mask"]["hidden_faces"]), 6)
                self.assertEqual(r["findings"], {expected: 6})
                self.assertEqual(r["output_plan"]["hidden_polygon_count"], 0)
                output = adapter.apply_duplicate(bpy.context, s, r)
                self.assertEqual(output["evaluated_remaining_polygons"], 6)
                self.assertTrue(mod.show_viewport)
                self.assertEqual(adapter.snapshot(bpy.context, s)[1], before)

    def test_06_mask_threshold_invert_and_visibility(self):
        for invert in (False, True):
            for threshold in (0.0, .5, 1.0):
                with self.subTest(invert=invert, threshold=threshold):
                    body, _, s = fx.setup()
                    mod = fx.mask(body, invert, [0, .5, 1, 0, .5, 1, 0, 1], threshold)
                    state, _ = adapter.snapshot(bpy.context, s)
                    self.assertIn("evaluated_remaining_counts", state["existing_mask"])
                    mod.show_viewport = mod.show_render = False
                    state, _ = adapter.snapshot(bpy.context, s)
                    self.assertEqual(state["existing_mask"]["hidden_faces"], [])
                    mod.show_render = True
                    with self.assertRaisesRegex(adapter.InputError, "VISIBILITY_MISMATCH"):
                        adapter.snapshot(bpy.context, s)

    def test_07_modifier_order_and_smooth_rejected(self):
        body, _, s = fx.setup()
        mod = fx.mask(body)
        mod.use_smooth = True
        with self.assertRaisesRegex(adapter.InputError, "SMOOTH_MASK"):
            adapter.snapshot(bpy.context, s)
        mod.use_smooth = False
        body.modifiers.new("AfterMask", 'ARMATURE')
        with self.assertRaisesRegex(adapter.InputError, "MASK_MUST_BE_LAST"):
            adapter.snapshot(bpy.context, s)

    def test_08_topology_modifiers_rejected_even_with_equal_counts(self):
        body, _, s = fx.setup()
        body.modifiers.new("Rebuild", 'NODES')
        with self.assertRaisesRegex(adapter.InputError, "MODIFIER_UNSUPPORTED"):
            adapter.snapshot(bpy.context, s)

    def test_09_ordered_connectivity_not_counts(self):
        body, _, _ = fx.setup()
        wrong = fx.cube("Reordered", .1, tuple(reversed(fx.POLYGONS)))
        class Proxy:
            name = body.name
            data = body.data
            modifiers = body.modifiers
            def evaluated_get(self, depsgraph):
                return wrong.evaluated_get(depsgraph)
        with self.assertRaisesRegex(adapter.InputError, "TOPOLOGY_CORRESPONDENCE_FAILED"):
            adapter.geometry(Proxy(), bpy.context.evaluated_depsgraph_get())

    def test_10_failure_restores_mask_and_scene(self):
        body, _, s = fx.setup()
        mod = fx.mask(body)
        selection = [o.name for o in bpy.context.selected_objects]
        active = bpy.context.active_object
        frame = bpy.context.scene.frame_current
        with patch.object(adapter, "geometry", side_effect=RuntimeError("injected snapshot failure")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                workflow.run_sync(bpy.context, s)
        self.assertTrue(mod.show_viewport and mod.show_render)
        self.assertEqual(selection, [o.name for o in bpy.context.selected_objects])
        self.assertEqual(bpy.context.active_object, active)
        self.assertEqual(bpy.context.scene.frame_current, frame)
        self.assertEqual(bpy.context.mode, 'OBJECT')
        self.assertFalse(workflow.BUSY)

    def test_11_cancel_generator_no_scene_mutation(self):
        body, _, s = fx.setup()
        fx.mask(body)
        before = adapter.snapshot(bpy.context, s)[1]
        counts = (len(bpy.data.objects), len(bpy.data.meshes))
        iterator, _ = workflow.start(bpy.context, s)
        for _ in range(3):
            next(iterator)
        iterator.close()
        workflow.BUSY.discard(workflow.scene_key(bpy.context.scene))
        self.assertEqual(adapter.snapshot(bpy.context, s)[1], before)
        self.assertEqual((len(bpy.data.objects), len(bpy.data.meshes)), counts)
        self.assertEqual(s.result_json, "")

    def test_12_stale_geometry_material_frame_settings_weights(self):
        for kind in ("body", "occluder", "material", "frame", "settings", "weights"):
            with self.subTest(kind=kind):
                body, shell, s = fx.setup()
                self.analyze(s)
                if kind == "body":
                    body.data.vertices[0].co.x += .01
                    body.data.update()
                elif kind == "occluder":
                    shell.location.x += .02
                elif kind == "material":
                    shell.data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = .2
                elif kind == "frame":
                    bpy.context.scene.frame_set(2)
                elif kind == "settings":
                    s.angle = 60
                else:
                    body.vertex_groups.new(name="new").add([0], .8, 'REPLACE')
                bpy.context.view_layer.update()
                with self.assertRaisesRegex(adapter.InputError, "STALE"):
                    workflow.fresh_report(bpy.context, s)

    def test_13_shape_keys_uv_weights_preserved(self):
        body, _, s = fx.setup()
        body.shape_key_add(name="Basis")
        key = body.shape_key_add(name="Expression")
        key.data[0].co.z += .01
        key.value = .5
        body.data.uv_layers.new(name="UVMap")
        body.vertex_groups.new(name="Bone").add([0, 1], .7, 'REPLACE')
        bpy.context.view_layer.update()
        before = adapter.snapshot(bpy.context, s)[1]
        r = self.analyze(s)
        output = adapter.apply_duplicate(bpy.context, s, r)
        dup = bpy.data.objects[output["object"]]
        self.assertIsNot(dup.data, body.data)
        self.assertIsNot(dup.data.shape_keys, body.data.shape_keys)
        self.assertEqual(dup.data.shape_keys.key_blocks["Expression"].value, .5)
        self.assertEqual(len(dup.data.uv_layers), 1)
        self.assertAlmostEqual(dup.vertex_groups["Bone"].weight(0), .7)
        self.assertEqual(adapter.snapshot(bpy.context, s)[1], before)
        key.value = .2
        bpy.context.view_layer.update()
        with self.assertRaisesRegex(adapter.InputError, "STALE"):
            workflow.fresh_report(bpy.context, s)

    def test_14_negative_nonuniform_scale(self):
        body, _, s = fx.setup()
        body.scale = (-1.2, .8, .9)
        bpy.context.view_layer.update()
        self.assertEqual(self.analyze(s)["counts"], {CANDIDATE: 6})

    def test_15_hidden_empty_duplicate_inputs(self):
        body, shell, s = fx.setup()
        shell.hide_set(True)
        with self.assertRaisesRegex(adapter.InputError, "HIDDEN_INPUT"):
            adapter.snapshot(bpy.context, s)
        shell.hide_set(False)
        s.occluders.add().object = body
        with self.assertRaisesRegex(adapter.InputError, "DUPLICATE"):
            adapter.snapshot(bpy.context, s)
        s.occluders.remove(1)
        empty = fx.mesh("Empty", [], [])
        s.body = empty
        with self.assertRaisesRegex(adapter.InputError, "EMPTY"):
            adapter.snapshot(bpy.context, s)

    def test_16_intersection_contact(self):
        body, shell, s = fx.setup()
        body.location.x = 1
        bpy.context.view_layer.update()
        r = self.analyze(s)
        self.assertGreater(r["counts"].get(REVIEW, 0), 0)
        # The wholly interior face may remain a candidate. No actual output
        # may remove a vertex incident to the crossing/exposed faces.
        self.assertEqual(r["output_plan"]["hidden_polygon_count"], 0)
        self.assertTrue(all(f["verdict"] == REVIEW for f in r["faces"]
                            if "SURFACE_INTERSECTION" in f["reason_codes"]))
        body.location.x = .9
        bpy.context.view_layer.update()
        r = self.analyze(s)
        self.assertEqual(r["output_plan"]["hidden_polygon_count"], 0)

    def test_17_manual_keep_hide_evidence_stays(self):
        body, _, s = fx.setup("tube")
        r = self.analyze(s)
        self.assertEqual(bpy.ops.underwhere.override(action='HIDE', selected=False), {'FINISHED'})
        edited = workflow.read_report(s)
        self.assertEqual(edited["faces"], r["faces"])
        self.assertEqual(edited["output_plan"]["manual_risk_faces"], [0])
        self.assertEqual(bpy.ops.underwhere.override(action='RESET', selected=False), {'FINISHED'})
        self.assertFalse(workflow.read_report(s)["overrides"])

    def test_18_preview_cleanup_and_report(self):
        body, _, s = fx.setup()
        before = adapter.snapshot(bpy.context, s)[1]
        r = self.analyze(s)
        for mode in ('CLASSIFY', 'ORIGINAL', 'OUTPUT'):
            obj = adapter.preview(bpy.context, r, mode)
            self.assertEqual(len(obj.data.polygons), 0 if mode == 'OUTPUT' else 6)
        adapter.clear_preview(bpy.context.scene)
        self.assertFalse(any(o.get(adapter.OWNER, "").startswith("PREVIEW:") for o in bpy.data.objects))
        self.assertEqual(adapter.snapshot(bpy.context, s)[1], before)
        path = workflow.export_report(bpy.context, s, str(OUT / "integration_report.json"))
        self.assertEqual(json.loads(path.read_text())["schema_version"], "1.2.0")
        self.assertEqual(json.loads(path.read_text())["report_kind"], "SHAREABLE_SUMMARY")
        with self.assertRaisesRegex(adapter.InputError, "installed Extension"):
            workflow.export_report(bpy.context, s, str(ROOT / "addon/underwhere/forbidden.json"))

    def test_19_input_change_during_analysis_refuses(self):
        body, _, s = fx.setup()
        iterator, elapsed = workflow.start(bpy.context, s)
        try:
            while True:
                next(iterator)
        except StopIteration as done:
            r = done.value
        body.location.z += .01
        bpy.context.view_layer.update()
        try:
            with self.assertRaisesRegex(adapter.InputError, "INPUT_CHANGED"):
                workflow.finish(bpy.context, s, r, elapsed)
        finally:
            workflow.BUSY.discard(workflow.scene_key(bpy.context.scene))
        self.assertEqual(s.result_json, "")

    def test_20_registration_lifecycle(self):
        underwhere.unregister()
        self.assertFalse(hasattr(bpy.types.Scene, "underwhere"))
        underwhere.register()
        self.assertEqual(bpy.app.handlers.load_post.count(ui.on_load), 1)
        self.assertEqual(bpy.app.handlers.depsgraph_update_post.count(ui.on_update), 1)

    def test_21_slit_resolution_and_independent_exposure(self):
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        for width in (.2, .00001):
            with self.subTest(width=width):
                _, shell, s = fx.slit(width)
                # Independent ray at the middle of the opening is a positive
                # control: this geometry really has a visible narrow defect.
                tree = BVHTree.FromPolygons([v.co for v in shell.data.vertices],
                                            [list(p.vertices) for p in shell.data.polygons])
                self.assertIsNone(tree.ray_cast(Vector((0, 0, .1)), Vector((0, 0, 1)))[2])
                r = self.analyze(s)
                self.assertEqual(r["output_plan"]["hidden_polygon_count"], 0)
                if width < .2:
                    self.assertGreater(r["resolution"]["opening_component_probes"], 0)
                    self.assertIn("narrow slits", r["limitations"][0])
                    (OUT / "narrow_slit_diagnostic.json").write_text(json.dumps(r, indent=2))

    def test_22_armature_pose_stale(self):
        body, _, s = fx.setup()
        rigdata = bpy.data.armatures.new("Rig")
        rig = bpy.data.objects.new("Rig", rigdata)
        bpy.context.collection.objects.link(rig)
        body.select_set(False)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        bone = rigdata.edit_bones.new("Bone")
        bone.head = (0, 0, 0)
        bone.tail = (0, 0, 1)
        bpy.ops.object.mode_set(mode='OBJECT')
        group = body.vertex_groups.new(name="Bone")
        group.add(list(range(8)), 1, 'REPLACE')
        mod = body.modifiers.new("Armature", 'ARMATURE')
        mod.object = rig
        bpy.context.view_layer.update()
        self.assertEqual(self.analyze(s)["counts"], {CANDIDATE: 6})
        rig.pose.bones["Bone"].location.x = 2
        bpy.context.view_layer.update()
        with self.assertRaisesRegex(adapter.InputError, "STALE"):
            workflow.fresh_report(bpy.context, s)
        r = self.analyze(s)
        self.assertEqual(r["output_plan"]["hidden_polygon_count"], 0)

    def test_23_output_transaction_rollback(self):
        _, _, s = fx.setup()
        r = self.analyze(s)
        before = (len(bpy.data.objects), len(bpy.data.meshes))
        with patch.object(adapter, "evaluated_counts", return_value=(999, 999)):
            with self.assertRaisesRegex(adapter.InputError, "OUTPUT_EVALUATION_MISMATCH"):
                adapter.apply_duplicate(bpy.context, s, r)
        self.assertEqual((len(bpy.data.objects), len(bpy.data.meshes)), before)

    def test_24_edit_selection_and_manual_override(self):
        body, _, s = fx.setup()
        self.analyze(s)
        s.face_index = 2
        self.assertEqual(bpy.ops.underwhere.face(action='SELECT'), {'FINISHED'})
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertEqual(bpy.ops.underwhere.override(action='KEEP'), {'FINISHED'})
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertEqual(workflow.read_report(s)["overrides"], {"2": "KEEP"})
        bpy.ops.object.mode_set(mode='OBJECT')

    def test_25_save_reload_expires_report(self):
        _, _, s = fx.setup()
        self.analyze(s)
        path = str(OUT / "reload_fixture.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        s = bpy.context.scene.underwhere
        self.assertTrue(s.status.startswith("STALE"))
        with self.assertRaisesRegex(adapter.InputError, "STALE"):
            workflow.fresh_report(bpy.context, s)
        self.assertEqual(self.analyze(s)["counts"], {CANDIDATE: 6})

    def test_26_same_geometry_different_triangulation(self):
        body, _, s = fx.setup()
        quad = self.analyze(s)
        triangles = [(p[0], p[1], p[2]) for p in fx.POLYGONS]
        triangles += [(p[0], p[2], p[3]) for p in fx.POLYGONS]
        body.data.clear_geometry()
        body.data.from_pydata([(x * .1, y * .1, z * .1) for x, y, z in fx.VERTICES],
                              [], triangles)
        body.data.update()
        bpy.context.view_layer.update()
        tri = self.analyze(s)
        self.assertAlmostEqual(quad["areas"][CANDIDATE], tri["areas"][CANDIDATE], places=6)
        self.assertEqual(tri["output_plan"]["hidden_triangle_count"],
                         quad["output_plan"]["hidden_triangle_count"])

    def test_27_linked_input_refused(self):
        _, shell, s = fx.setup()
        library = str(OUT / "linked_fixture.blend")
        bpy.data.libraries.write(library, {shell})
        with bpy.data.libraries.load(library, link=True) as (src, dst):
            dst.objects = [shell.name]
        linked = dst.objects[0]
        bpy.context.collection.objects.link(linked)
        s.occluders[0].object = linked
        with self.assertRaisesRegex(adapter.InputError, "LINKED_OR_READ_ONLY"):
            adapter.snapshot(bpy.context, s)

    def test_28_camera_and_collection_visibility_refused(self):
        _, shell, s = fx.setup()
        shell.visible_camera = False
        with self.assertRaisesRegex(adapter.InputError, "CAMERA_VISIBILITY"):
            adapter.snapshot(bpy.context, s)
        shell.visible_camera = True
        collection = shell.users_collection[0]
        collection.hide_render = True
        try:
            with self.assertRaisesRegex(adapter.InputError, "COLLECTION_VISIBILITY"):
                adapter.snapshot(bpy.context, s)
        finally:
            collection.hide_render = False

    def test_29_unhashed_image_dependency_expires(self):
        from types import SimpleNamespace
        _, _, s = fx.setup()
        self.analyze(s)
        image = bpy.data.images.new("ChangedColorTexture", width=1, height=1)
        try:
            ui.on_update(bpy.context.scene, SimpleNamespace(updates=[SimpleNamespace(id=image)]))
            with self.assertRaisesRegex(adapter.InputError, "STALE"):
                workflow.fresh_report(bpy.context, s)
        finally:
            bpy.data.images.remove(image)

    def test_30_remote_bad_parts_do_not_poison_closed_shell(self):
        _, _, s = fx.setup()
        vertices, polygons = [], []
        for i in range(65):
            offset = len(vertices)
            vertices.extend([(10 + i, 0, 0), (10 + i, 1, 0), (10 + i, 0, 1)])
            polygons.append((offset, offset + 1, offset + 2))
        decoration = fx.mesh('RemoteOpenDecoration', vertices, polygons, fx.material())
        s.occluders.add().object = decoration
        r = self.analyze(s)
        self.assertEqual(r['counts'], {CANDIDATE: 6})
        self.assertIn('RemoteOpenDecoration', [i['object'] for i in r['occluder_issues']])
        # When the malformed object is itself the nearest blocker, it must
        # refuse rather than certify a hide using a farther intact layer.
        body, shell, s = fx.setup()
        malformed = fx.cube('NearNonmanifold', .5, fx.POLYGONS + [fx.POLYGONS[0]], fx.material())
        s.occluders.add().object = malformed
        r = self.analyze(s)
        self.assertEqual(r['counts'], {REVIEW: 6})
        self.assertEqual(r['output_plan']['hidden_polygon_count'], 0)

    def test_31_explicit_opacity_assumption_is_recorded_and_expires(self):
        _, shell, s = fx.setup(alpha=.2)
        self.assertEqual(self.analyze(s)['counts'], {REVIEW: 6})
        material = shell.data.materials[0]
        material.underwhere_assume_opaque = True
        r = self.analyze(s)
        self.assertEqual(r['counts'], {CANDIDATE: 6})
        self.assertEqual(r['assumptions']['dependent_candidate_faces'], 6)
        self.assertEqual(r['assumptions']['opaque_materials'], [material.name])
        self.assertEqual(r['materials'][0]['slots'][0]['automatic_verdict'], 'ALPHA_OR_TRANSMISSION_UNTRUSTED')
        self.assertTrue(r['materials'][0]['slots'][0]['user_assumed_opaque'])
        material.underwhere_assume_opaque = False
        with self.assertRaisesRegex(adapter.InputError, 'STALE'):
            workflow.fresh_report(bpy.context, s)

    def test_32_deleted_copy_preserves_remaining_keys_uv_weights(self):
        body, _, s = fx.setup()
        body.data.clear_geometry()
        vertices = [(x * .1, y * .1, z * .1) for x, y, z in fx.VERTICES]
        vertices += [(x * .1, y * .1, z * .1 + 2) for x, y, z in fx.VERTICES]
        body.data.from_pydata(vertices, [], list(fx.POLYGONS) + [tuple(i + 8 for i in p) for p in fx.POLYGONS])
        body.data.update()
        body.shape_key_add(name='Basis')
        key = body.shape_key_add(name='Expression')
        key.data[8].co.x += .02
        key.value = .3
        body.data.uv_layers.new(name='UVMap')
        for index, loop in enumerate(body.data.uv_layers.active.data):
            loop.uv = (index / 100, index / 200)
        body.vertex_groups.new(name='Bone').add(list(range(8, 16)), .7, 'REPLACE')
        rigdata = bpy.data.armatures.new('ExportRig')
        rig = bpy.data.objects.new('ExportRig', rigdata)
        bpy.context.collection.objects.link(rig)
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        bone = rigdata.edit_bones.new('Bone')
        bone.head = (0, 0, 0)
        bone.tail = (0, 0, .2)
        bpy.ops.object.mode_set(mode='OBJECT')
        rig.select_set(False)
        body.select_set(True)
        bpy.context.view_layer.objects.active = body
        modifier = body.modifiers.new('Armature', 'ARMATURE')
        modifier.object = rig
        bpy.context.view_layer.update()
        before = adapter.snapshot(bpy.context, s)[1]
        r = self.analyze(s)
        self.assertEqual(r['counts'], {CANDIDATE: 6, KEEP: 6})
        output = adapter.apply_duplicate(bpy.context, s, r, deleted=True)
        dup = bpy.data.objects[output['object']]
        self.assertEqual(output['kind'], 'DELETED_COPY')
        self.assertEqual(len(dup.data.vertices), 8)
        self.assertEqual(len(dup.data.polygons), 6)
        self.assertFalse(any(m.type == 'MASK' for m in dup.modifiers))
        self.assertEqual(len(dup.data.shape_keys.key_blocks['Expression'].data), 8)
        for index in range(8):
            self.assertLess((dup.data.shape_keys.key_blocks['Expression'].data[index].co - key.data[index + 8].co).length, 1e-6)
            self.assertAlmostEqual(dup.vertex_groups['Bone'].weight(index), .7)
        self.assertAlmostEqual(dup.data.uv_layers.active.data[0].uv.x,
                               body.data.uv_layers.active.data[24].uv.x)
        self.assertEqual(adapter.snapshot(bpy.context, s)[1], before)
        selection = list(bpy.context.selected_objects)
        active = bpy.context.view_layer.objects.active
        try:
            bpy.ops.object.select_all(action='DESELECT')
            dup.select_set(True)
            rig.select_set(True)
            bpy.context.view_layer.objects.active = dup
            destination = str(OUT / 'shape_key_export.fbx')
            self.assertEqual(bpy.ops.export_scene.fbx(filepath=destination, use_selection=True,
                use_mesh_modifiers=False, bake_anim=False, add_leaf_bones=False), {'FINISHED'})
            objects_before_import = set(bpy.data.objects)
            bpy.ops.import_scene.fbx(filepath=destination)
            imported_objects = set(bpy.data.objects) - objects_before_import
            imported = next(obj for obj in imported_objects if obj.type == 'MESH')
            imported_rig = next(obj for obj in imported_objects if obj.type == 'ARMATURE')
            self.assertEqual(len(imported.data.polygons), 6)
            self.assertEqual(len(imported.data.shape_keys.key_blocks['Expression'].data), 8)
            self.assertEqual(len(imported.data.uv_layers), 1)
            self.assertIn('Bone', imported_rig.data.bones)
            self.assertTrue(any(mod.type == 'ARMATURE' and mod.object == imported_rig for mod in imported.modifiers))
            self.assertGreater(imported.vertex_groups['Bone'].weight(0), 0)
        finally:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in selection:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = active
        s.body = dup
        self.assertTrue(ui.mesh_poll(None, dup))
        self.assertEqual(self.analyze(s)['counts'], {KEEP: 6})

    def test_33_copy_collections_and_link_failure_cleanup(self):
        body, _, s = fx.setup()
        collection = bpy.data.collections.new('BodyCollection')
        bpy.context.scene.collection.children.link(collection)
        collection.objects.link(body)
        r = self.analyze(s)
        output = adapter.apply_duplicate(bpy.context, s, r)
        self.assertEqual(set(bpy.data.objects[output['object']].users_collection), set(body.users_collection))
        before = len(bpy.data.objects), len(bpy.data.meshes)
        with patch.object(adapter, 'link_to_source', side_effect=RuntimeError('link failure')):
            with self.assertRaisesRegex(RuntimeError, 'link failure'):
                adapter.apply_duplicate(bpy.context, s, r)
        self.assertEqual((len(bpy.data.objects), len(bpy.data.meshes)), before)

    def test_34_edit_mode_next_select_and_cached_inspection(self):
        body, _, s = fx.setup('tube')
        self.analyze(s)
        bpy.ops.underwhere.face(action='SELECT')
        bpy.ops.underwhere.face(action='NEXT')
        bpy.ops.underwhere.face(action='SELECT')
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        bpy.ops.object.mode_set(mode='OBJECT')
        workflow.fresh_report(bpy.context, s)
        with patch.object(adapter, 'snapshot', side_effect=AssertionError('unexpected snapshot')):
            workflow.fresh_report(bpy.context, s, verify=False)
            workflow.read_report(s)
            workflow.read_report(s)
            self.assertEqual(ui.freshness_timer(), .75)

    def test_35_default_settings_centimetre_scale_covariance(self):
        results = []
        for scale in (1.0, .01):
            body, shell, s = fx.setup()
            s.preset = 'BALANCED'
            # 0.2m body and 0.4m closed garment, including cm scene coordinates.
            for obj, factor in ((body, 1 / scale), (shell, .2 / scale)):
                for vertex in obj.data.vertices:
                    vertex.co *= factor
                obj.data.update()
            bpy.context.scene.unit_settings.scale_length = scale
            bpy.context.view_layer.update()
            r = self.analyze(s)
            results.append(r)
            self.assertEqual(r['counts'], {CANDIDATE: 6})
            self.assertAlmostEqual(r['input']['settings']['r'] * scale, .05)
        self.assertEqual(results[0]['resolution']['rays'], results[1]['resolution']['rays'])

    def test_36_multiframe_reveal_restoration_and_future_edit_stale(self):
        body, shell, s = fx.setup()
        shell.location.x = 0
        shell.keyframe_insert('location', frame=1)
        shell.location.x = 4
        shell.keyframe_insert('location', frame=10)
        bpy.context.scene.frame_set(1)
        s.scope = 'EXPLICIT_FRAMES'
        s.frames = '1,10'
        r = self.analyze(s)
        self.assertEqual(r['counts'], {KEEP: 6})
        self.assertEqual(r['output_plan']['hidden_polygon_count'], 0)
        self.assertEqual(bpy.context.scene.frame_current, 1)
        # Analyze with both frames closed, then alter only the future pose.
        shell.location.x = 0
        shell.keyframe_insert('location', frame=10)
        bpy.context.scene.frame_set(1)
        r = self.analyze(s)
        self.assertEqual(r['counts'], {CANDIDATE: 6})
        current_before = adapter.snapshot(bpy.context, s)[1]
        shell.location.x = 4
        shell.keyframe_insert('location', frame=10)
        bpy.context.scene.frame_set(1)
        self.assertEqual(adapter.snapshot(bpy.context, s)[1], current_before)
        with self.assertRaisesRegex(adapter.InputError, 'STALE'):
            workflow.fresh_report(bpy.context, s)
        self.assertEqual(bpy.context.scene.frame_current, 1)
        s.frames = 'garbage'
        with self.assertRaisesRegex(adapter.InputError, 'FRAMES_REQUIRED'):
            workflow.start(bpy.context, s)
        self.assertFalse(workflow.BUSY)

    def test_37_solidify_occluder_body_refuses(self):
        body, shell, s = fx.setup()
        shell.modifiers.new('Solidify', 'SOLIDIFY').thickness = .1
        bpy.context.view_layer.update()
        self.assertEqual(self.analyze(s)['counts'], {CANDIDATE: 6})
        body.modifiers.new('Solidify', 'SOLIDIFY')
        with self.assertRaisesRegex(adapter.InputError, 'MODIFIER_UNSUPPORTED'):
            adapter.snapshot(bpy.context, s)

    def test_38_timer_failure_recovers_and_selection_is_not_dirty(self):
        from types import SimpleNamespace
        body, _, s = fx.setup()
        self.analyze(s)
        workflow.DIRTY.clear()
        ui.on_update(bpy.context.scene, SimpleNamespace(updates=[SimpleNamespace(
            id=body, is_updated_geometry=False, is_updated_transform=False, is_updated_shading=False)]))
        self.assertFalse(workflow.DIRTY)
        with patch.object(workflow, 'read_report', side_effect=RuntimeError('injected timer failure')):
            self.assertEqual(ui.freshness_timer(), .75)
        self.assertTrue(s.status.startswith('STALE'))
        with self.assertRaisesRegex(adapter.InputError, 'STALE'):
            workflow.fresh_report(bpy.context, s)
        self.assertEqual(self.analyze(s)['counts'], {CANDIDATE: 6})

    def test_39_large_shape_key_snapshot_profile(self):
        import time
        from array import array
        _, shell, s = fx.setup()
        vertices = [(x / 100, y / 100, 0) for y in range(100) for x in range(100)]
        polygons = [(y * 100 + x, y * 100 + x + 1, (y + 1) * 100 + x + 1,
                     (y + 1) * 100 + x) for y in range(99) for x in range(99)]
        body = fx.mesh('Synthetic10k60keys', vertices, polygons)
        s.body = body
        body.shape_key_add(name='Basis')
        for index in range(60):
            body.shape_key_add(name=f'Expression{index}')
        bpy.context.view_layer.update()
        started = time.perf_counter()
        before = adapter.snapshot(bpy.context, s)[1]
        elapsed = time.perf_counter() - started
        body.data.shape_keys.key_blocks[-1].data[-1].co.x += .01
        self.assertNotEqual(adapter.snapshot(bpy.context, s)[1], before)
        (OUT / 'performance_summary.json').write_text(json.dumps({
            'blender': bpy.app.version_string, 'vertices': len(vertices), 'shape_keys': 61,
            'snapshot_seconds': elapsed, 'source': 'original_synthetic_grid',
            'real_avatar_profile': False,
        }, indent=2))

    def test_40_legacy_settings_migrate_without_legacy_report(self):
        body, shell, s = fx.setup()
        scene = bpy.context.scene
        scene['obma_beta'] = {'body': body, 'spatial_step': .08, 'mode': 0,
                              'result_json': 'private legacy geometry',
                              'occluders': [{'object': shell}]}
        s.body = None
        s.occluders.clear()
        scene.unit_settings.scale_length = .01
        ui.migrate_settings(scene)
        self.assertEqual(s.body, body)
        self.assertEqual(s.occluders[0].object, shell)
        self.assertAlmostEqual(s.spatial_step, .0008)
        self.assertFalse(s.result_json)
        self.assertNotIn('obma_beta', scene)

    def test_41_removed_scene_modal_cleanup(self):
        from types import SimpleNamespace
        scene = bpy.data.scenes.new('TemporaryAnalysis')
        key = workflow.scene_key(scene)
        workflow.BUSY.add(key)
        def empty():
            yield None
        fake = SimpleNamespace(_scene=scene, _key=key, _timer=None,
                               _iterator=empty(), fail=lambda context, exc: {'CANCELLED'})
        fake.cleanup = lambda: ui.UNDERWHERE_OT_analyze.cleanup(fake)
        ui.JOBS.append(fake)
        bpy.data.scenes.remove(scene)
        result = ui.UNDERWHERE_OT_analyze.modal(fake, bpy.context, SimpleNamespace(type='TIMER'))
        self.assertEqual(result, {'CANCELLED'})
        self.assertNotIn(key, workflow.BUSY)
        self.assertNotIn(fake, ui.JOBS)

    def test_42_failed_override_does_not_mutate_cached_evidence(self):
        _, _, s = fx.setup('tube')
        self.analyze(s)
        before = s.result_json
        with patch.object(adapter, 'measure_plan', side_effect=RuntimeError('verification failed')):
            # Blender exposes an operator ERROR report as a Python exception.
            with self.assertRaisesRegex(RuntimeError, 'verification failed'):
                bpy.ops.underwhere.override(action='HIDE', selected=False)
        self.assertEqual(s.result_json, before)
        self.assertEqual(workflow.read_report(s)['overrides'], {})
        self.assertEqual(workflow.read_report(s)['output_plan']['hidden_polygon_count'], 0)

    def test_43_default_human_scale_curved_body_multipart_garment(self):
        fx.reset()
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8)
        body = bpy.context.object
        body.name = 'OriginalSyntheticTorso'
        for vertex in body.data.vertices:
            vertex.co.x *= .3
            vertex.co.y *= .2
            vertex.co.z *= .85
        body.data.update()
        s = bpy.context.scene.underwhere
        s.body = body
        s.preset = 'BALANCED'
        shell_vertices = [(x * .4, y * .3, z) for x, y, z in fx.VERTICES]
        panels = []
        for index, polygon in enumerate(fx.POLYGONS):
            panel = fx.mesh(f'GarmentPanel{index}', shell_vertices, [polygon], fx.material())
            panels.append(panel)
            s.occluders.add().object = panel
        bpy.context.view_layer.update()
        report = self.analyze(s)
        self.assertGreater(len(body.data.polygons), 100)
        self.assertEqual(report['counts'], {CANDIDATE: len(body.data.polygons)})
        self.assertEqual(report['output_plan']['hidden_polygon_count'], len(body.data.polygons))
        # Independent positive control: remove the complete top panel. Finite
        # opening-directed probes must observe the resulting exposure.
        s.occluders.remove(1)
        adapter.remove_owned(panels[1])
        report = self.analyze(s)
        self.assertEqual(report['output_plan']['hidden_polygon_count'], 0)
        self.assertGreater(report['counts'].get(KEEP, 0), 0)

    def test_44_solidify_rim_slits_default_density_and_scene_units(self):
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        for width in (.02, .00001):
            for unit_scale in (1.0, .01):
                with self.subTest(width=width, metres_per_unit=unit_scale):
                    body, shell, s = fx.slit(width)
                    s.preset = 'BALANCED'
                    for obj in (body, shell):
                        for vertex in obj.data.vertices:
                            vertex.co /= unit_scale
                        obj.data.update()
                    bpy.context.scene.unit_settings.scale_length = unit_scale
                    solidify = shell.modifiers.new('Rim', 'SOLIDIFY')
                    solidify.thickness = .01 / unit_scale
                    solidify.use_rim = True
                    bpy.context.view_layer.update()
                    evaluated = shell.evaluated_get(bpy.context.evaluated_depsgraph_get())
                    mesh = evaluated.to_mesh()
                    try:
                        tree = BVHTree.FromPolygons([v.co for v in mesh.vertices],
                                                    [list(p.vertices) for p in mesh.polygons])
                        # Independent control: the rimmed mesh really has an
                        # opening along its centre; this ray must remain clear.
                        self.assertIsNone(tree.ray_cast(Vector((0, 0, .1 / unit_scale)), Vector((0, 0, 1)))[2])
                    finally:
                        evaluated.to_mesh_clear()
                    report = self.analyze(s)
                    # A source-plane target need not pass through both layers
                    # of a thick micro-slit. Such unsampled exposure is REVIEW,
                    # never automatic hiding; the zero-deletion oracle is fixed.
                    self.assertEqual(report['counts'], {KEEP if width == .02 else REVIEW: 6})
                    self.assertEqual(report['output_plan']['hidden_polygon_count'], 0)
                    self.assertGreater(report['resolution']['opening_component_probes'], 0)
                    self.assertTrue(solidify.show_viewport and solidify.show_render)

    def test_45_selected_frames_always_include_visible_current_pose(self):
        body, _, s = fx.setup()
        body.location.x = 0
        body.keyframe_insert('location', frame=1)
        body.location.x = 4
        body.keyframe_insert('location', frame=5)
        bpy.context.scene.frame_set(5)
        s.scope = 'EXPLICIT_FRAMES'
        s.frames = '1'
        report = self.analyze(s)
        self.assertEqual(report['counts'], {KEEP: 6})
        self.assertEqual(report['output_plan']['hidden_polygon_count'], 0)
        self.assertEqual([(state['frame'], state['subframe']) for state in report['sampled_states']], [(5, 0.0), (1, 0.0)])
        self.assertEqual(bpy.context.scene.frame_current, 5)

    def test_46_current_subframe_is_a_distinct_required_state(self):
        body, _, s = fx.setup()
        body.location.x = 0
        body.keyframe_insert('location', frame=5)
        body.location.x = 8
        body.keyframe_insert('location', frame=6)
        bpy.context.scene.frame_set(5, subframe=.5)
        s.scope = 'EXPLICIT_FRAMES'
        s.frames = '5'
        report = self.analyze(s)
        self.assertEqual(report['output_plan']['hidden_polygon_count'], 0)
        self.assertEqual(report['counts'], {KEEP: 6})
        self.assertEqual([(state['frame'], state['subframe']) for state in report['sampled_states']], [(5, .5), (5, 0.0)])
        self.assertEqual(bpy.context.scene.frame_subframe, .5)

    def test_47_opacity_assumption_cannot_override_backface_culling(self):
        _, shell, s = fx.setup()
        material = shell.data.materials[0]
        material.use_backface_culling = True
        material.underwhere_assume_opaque = True
        report = self.analyze(s)
        self.assertEqual(report['counts'], {REVIEW: 6})
        self.assertEqual(report['output_plan']['hidden_polygon_count'], 0)
        self.assertEqual(report['assumptions']['opaque_materials'], [])
        policy = adapter.material_policy(material)
        self.assertEqual(policy['automatic_verdict'], 'BACKFACE_CULLING_UNTRUSTED')
        self.assertTrue(policy['assumption_blocked'])
        self.assertEqual(policy['verdict'], 'BACKFACE_CULLING_UNTRUSTED')

    def test_48_large_report_stays_out_of_saved_scene(self):
        fx.reset()
        count = 72
        vertices = [(x / 100, y / 100, 0) for y in range(count) for x in range(count)]
        polygons = [(y * count + x, y * count + x + 1,
                     (y + 1) * count + x + 1, (y + 1) * count + x)
                    for y in range(count - 1) for x in range(count - 1)]
        body = fx.mesh('Original5kFaceGrid', vertices, polygons)
        shell = fx.cube('RemoteBlocker', 1, mat=fx.material())
        shell.location.x = 4
        s = bpy.context.scene.underwhere
        s.body = body
        s.occluders.add().object = shell
        s.preset = 'BALANCED'
        bpy.context.view_layer.update()
        report = self.analyze(s)
        self.assertGreater(len(json.dumps(report)), 1_000_000)
        self.assertLess(len(s.result_json), 256)
        self.assertNotIn('preview_vertices', s.result_json)
        reference = s.result_json
        s.result_json = ''
        bpy.context.preferences.filepaths.save_version = 0
        without = OUT / 'session_without_report.blend'
        with_report = OUT / 'session_with_reference.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(without), compress=False)
        s.result_json = reference
        bpy.ops.wm.save_as_mainfile(filepath=str(with_report), compress=False)
        self.assertLess(abs(with_report.stat().st_size - without.stat().st_size), 2048)
        self.assertEqual(workflow.read_report(s)['counts'], report['counts'])

    def test_49_preview_revalidates_hidden_inputs_and_removes_old_comparison(self):
        _, shell, s = fx.setup()
        report = self.analyze(s)
        adapter.preview(bpy.context, report, 'CLASSIFY')
        shell.hide_set(True)
        workflow.DIRTY.clear()  # Simulate a missed depsgraph notification.
        with self.assertRaisesRegex(RuntimeError, 'HIDDEN_INPUT'):
            bpy.ops.underwhere.preview()
        self.assertFalse(any(adapter.is_preview(obj) for obj in bpy.data.objects))

    def test_50_solidify_flags_restore_after_opening_snapshot_failure(self):
        _, shell, s = fx.slit(.02)
        modifier = shell.modifiers.new('Rim', 'SOLIDIFY')
        original = adapter.geometry
        def fail_on_shell(obj, *args, **kwargs):
            if obj == shell:
                self.assertFalse(modifier.show_viewport)
                self.assertFalse(modifier.show_render)
                raise RuntimeError('opening snapshot failed')
            return original(obj, *args, **kwargs)
        with patch.object(adapter, 'geometry', side_effect=fail_on_shell):
            with self.assertRaisesRegex(RuntimeError, 'opening snapshot failed'):
                workflow.run_sync(bpy.context, s)
        self.assertTrue(modifier.show_viewport and modifier.show_render)
        self.assertFalse(workflow.BUSY)

    def test_51_session_revisions_preserve_overrides_and_expire_bounded_history(self):
        _, _, s = fx.setup()
        report = self.analyze(s)
        original_reference = s.result_json
        s.face_index = 0
        self.assertEqual(bpy.ops.underwhere.override(action='KEEP', selected=False), {'FINISHED'})
        edited_reference = s.result_json
        self.assertNotEqual(original_reference, edited_reference)
        s.result_json = original_reference
        self.assertEqual(workflow.read_report(s)['overrides'], {})
        s.result_json = edited_reference
        self.assertEqual(workflow.read_report(s)['overrides'], {'0': 'KEEP'})
        self.assertIs(workflow.read_report(s)['preview_vertices'], report['preview_vertices'])
        with patch.object(workflow, 'MAX_REPORT_REVISIONS', 2):
            for _ in range(3):
                workflow.save_report(s, report)
            self.assertLessEqual(len(workflow.REPORT_CACHE), 2)
            s.result_json = original_reference
            with self.assertRaisesRegex(adapter.InputError, 'STALE.*expired'):
                workflow.fresh_report(bpy.context, s)

    def test_52_legacy_embedded_result_is_purged_without_loading_its_geometry(self):
        _, _, s = fx.setup()
        s.result_json = '{"preview_vertices":' + ('0' * 1_000_000) + '}'
        workflow.discard_legacy_report(s)
        self.assertEqual(s.result_json, '')
        self.assertTrue(s.status.startswith('STALE'))

    def test_53_solidify_does_not_bypass_source_mapping_check(self):
        body, _, _ = fx.setup()
        body.modifiers.new('Solidify', 'SOLIDIFY')
        bpy.context.view_layer.update()
        with self.assertRaisesRegex(adapter.InputError, 'TOPOLOGY_CORRESPONDENCE_FAILED'):
            adapter.geometry(body, bpy.context.evaluated_depsgraph_get())

    def test_54_own_comparison_survives_freshness_timer(self):
        _, shell, s = fx.setup()
        self.analyze(s)
        s.preview_mode = 'CLASSIFY'
        bpy.ops.underwhere.preview()
        # The event loop evaluates the depsgraph, then the timer ticks.
        bpy.context.view_layer.update()
        ui.freshness_timer()
        self.assertEqual(sum(adapter.is_preview(o) for o in bpy.data.objects), 1)
        self.assertEqual(s.status, "READY")
        # A real input change still clears the comparison.
        shell.hide_set(True)
        bpy.context.view_layer.update()
        ui.freshness_timer()
        self.assertFalse(any(adapter.is_preview(o) for o in bpy.data.objects))
        self.assertTrue(s.status.startswith("CHECK"))

    def test_55_material_slot_reassignment_is_still_detected(self):
        _, shell, s = fx.setup()
        self.analyze(s)
        bpy.ops.underwhere.preview()
        bpy.context.view_layer.update()
        ui.freshness_timer()
        self.assertEqual(s.status, "READY")
        shell.material_slots[0].material = fx.material("Replacement")
        bpy.context.view_layer.update()
        ui.freshness_timer()
        self.assertFalse(any(adapter.is_preview(o) for o in bpy.data.objects))
        self.assertTrue(s.status.startswith("CHECK"))

    def test_56_audit_repair_policy_keeps_or_restores_undecided_hides(self):
        body, _, s = fx.setup(alpha=.5)  # untrusted shell: every face is Review
        fx.mask(body)                    # existing mask hides everything
        r = self.analyze(s)
        self.assertEqual(r["counts"], {REVIEW: 6})
        self.assertEqual(r["output_plan"]["hidden_polygon_count"], 0)
        bpy.ops.underwhere.repair_policy(policy='RESTORE_EXPOSED_ONLY')
        report = workflow.read_report(s)
        self.assertEqual(report["output_plan"]["hidden_polygon_count"], 6)
        self.assertEqual(len(report["output_plan"]["retained_uncertain_faces"]), 6)
        self.assertEqual(report["output_verification"]["remaining_polygons"], 0)
        bpy.ops.underwhere.repair_policy(policy='RESTORE_EXPOSED_AND_UNRESOLVED')
        self.assertEqual(workflow.read_report(s)["output_plan"]["hidden_polygon_count"], 0)

    def test_57_before_after_preview_colours_existing_versus_output(self):
        body, _, s = fx.setup()
        adapter.preview(bpy.context, self.analyze(s), 'DIFF')
        preview = next(o for o in bpy.data.objects if adapter.is_preview(o))
        names = {preview.data.materials[p.material_index].name.split('.')[0]
                 for p in preview.data.polygons}
        self.assertEqual(len(preview.data.polygons), 6)
        self.assertEqual(names, {"UnderWhere_View_DIFF_NEWLY_HIDDEN"})
        body, _, s = fx.setup(alpha=.5)
        fx.mask(body)
        adapter.preview(bpy.context, self.analyze(s), 'DIFF')
        preview = next(o for o in bpy.data.objects if adapter.is_preview(o))
        names = {preview.data.materials[p.material_index].name.split('.')[0]
                 for p in preview.data.polygons}
        self.assertEqual(names, {"UnderWhere_View_DIFF_RESTORED"})

    def test_58_structured_panels_draw_with_valid_icons_properties_and_operators(self):
        from types import SimpleNamespace
        icons = set(bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys())
        calls = []

        class Layout:
            enabled = active = True
            scale_y = 1.0

            def _icon(self, icon):
                self_test.assertIn(icon, icons | {None, 'NONE'})

            def _child(self, *args, **kwargs):
                return Layout()

            row = column = box = grid_flow = split = _child

            def separator(self, **kwargs):
                pass

            def progress(self, **kwargs):
                self_test.assertGreaterEqual(kwargs.get("factor", 0.0), 0.0)

            def label(self, text="", icon='NONE', **kwargs):
                self._icon(icon)
                calls.append(("label", text))

            def prop(self, data, name, icon='NONE', **kwargs):
                self._icon(icon)
                self_test.assertIn(name, data.bl_rna.properties)

            def prop_enum(self, data, name, value, icon='NONE', **kwargs):
                self._icon(icon)
                self_test.assertIn(name, data.bl_rna.properties)
                self_test.assertIn(value, data.bl_rna.properties[name].enum_items.keys())

            def prop_search(self, data, name, search_data, search_name, icon='NONE', **kwargs):
                self._icon(icon)
                self_test.assertIn(name, data.bl_rna.properties)
                self_test.assertIn(search_name, search_data.bl_rna.properties)

            def template_list(self, list_type, list_id, data, name, active_data, active_name, **kwargs):
                self_test.assertTrue(hasattr(bpy.types, list_type))
                self_test.assertIn(name, data.bl_rna.properties)
                self_test.assertIn(active_name, active_data.bl_rna.properties)

            def operator(self, idname, icon='NONE', **kwargs):
                self._icon(icon)
                category, name = idname.split(".")
                properties = getattr(getattr(bpy.ops, category), name).get_rna_type().properties
                calls.append(("operator", idname))

                class Properties:
                    def __setattr__(self, key, value):
                        self_test.assertIn(key, properties)
                        if properties[key].type == 'ENUM':
                            self_test.assertIn(value, properties[key].enum_items.keys())
                return Properties()

        self_test = self
        panels = [cls for cls in ui.CLASSES if issubclass(cls, bpy.types.Panel)]

        def draw_all():
            drawn = []
            for panel in panels:
                poll = next((base.__dict__["poll"] for base in panel.__mro__
                             if "poll" in base.__dict__ and base.__module__.startswith("underwhere")), None)
                if poll and not poll.__get__(None, panel)(bpy.context):
                    continue
                panel.draw(SimpleNamespace(layout=Layout()), bpy.context)
                drawn.append(panel.bl_idname)
            return drawn

        def draw_steps():
            drawn = []
            for step in ('SETUP', 'REVIEW', 'EXPORT'):
                bpy.context.scene.underwhere.ui_step = step
                drawn += draw_all()
            return drawn

        body, _, s = fx.setup()
        drawn = draw_steps()
        self.assertIn("UNDERWHERE_PT_inputs", drawn)
        self.assertNotIn("UNDERWHERE_PT_results", drawn)  # nothing to show before analysis
        self.analyze(s)
        s.use_extra_bodies = True  # draws the Body part list
        for mode in ('CLASSIFY', 'DIFF', 'OUTPUT', 'ORIGINAL', 'POSES', 'OFF'):
            s.preview_mode = mode
            drawn = draw_steps()
            self.assertIn("UNDERWHERE_PT_results", drawn)
            self.assertIn("UNDERWHERE_PT_output", drawn)
        # Each step shows only its own panels.
        s.ui_step = 'EXPORT'
        self.assertNotIn("UNDERWHERE_PT_inputs", draw_all())
        s.use_extra_bodies = False
        fx.mask(body)
        self.analyze(s)
        draw_steps()
        # While selecting, the panel shows the selected count and a Done button.
        s.preview_mode = 'CLASSIFY'
        s.ui_step = 'REVIEW'
        for target in ('COMPARISON', 'BODY'):
            bpy.ops.underwhere.edit_selection(target=target)
            self.assertIn("UNDERWHERE_PT_faces", draw_all())
            self.assertIn(("operator", "underwhere.finish_selection"), calls)
            bpy.ops.underwhere.finish_selection()
        for idname in ("underwhere.preflight", "underwhere.analyze", "underwhere.go_step",
                       "underwhere.repair_policy", "underwhere.preview",
                       "underwhere.apply", "underwhere.export"):
            self.assertIn(("operator", idname), calls)
        # Untrusted clothing materials are named in the next steps, with an Opaque switch.
        _, shell, s = fx.setup(alpha=.5)
        self.analyze(s)
        draw_steps()
        material = shell.data.materials[0].name
        self.assertTrue(any(kind == "label" and text.startswith(material + " is not confirmed") for kind, text in calls))
        self.assertIn(("label", "Next steps"), calls)
        # An out-of-date result says why and offers the way back.
        s.status = "STALE: inputs changed; Analyze again"
        draw_steps()
        self.assertIn(("label", "Out of date. Use Analyze again at the top."), calls)
        self.assertIn(("label", ui.wrap("The Body, clothing, materials or frames changed.")[0]), calls)
        # The same panels draw in Japanese.
        prefs = bpy.context.preferences.view
        language, translate = prefs.language, prefs.use_translate_interface
        try:
            prefs.language = 'ja_JP'
            prefs.use_translate_interface = True
            s.status = "READY"
            calls.clear()
            draw_steps()
            self.assertIn(("label", "次にやること"), calls)
        finally:
            prefs.language, prefs.use_translate_interface = language, translate

    def test_59_bulk_select_review_faces_then_hide_them_at_once(self):
        body, _, s = fx.setup(alpha=.5)  # every face Review for an untrusted material
        report = self.analyze(s)
        self.assertEqual(report["counts"], {REVIEW: 6})
        self.assertEqual(ui.review_reason_counts(report), [("ALPHA_OR_TRANSMISSION_UNTRUSTED", 6)])
        self.assertIsNotNone(ui.reason_hint("ALPHA_OR_TRANSMISSION_UNTRUSTED"))
        bpy.ops.underwhere.select_group(group='REASON', reason="ALPHA_OR_TRANSMISSION_UNTRUSTED")
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(sum(p.select for p in body.data.polygons), 6)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='HIDE')
        bpy.ops.object.mode_set(mode='OBJECT')
        plan = workflow.read_report(s)["output_plan"]
        self.assertEqual(len(plan["manual_risk_faces"]), 6)
        self.assertEqual(plan["hidden_polygon_count"], 6)
        with self.assertRaisesRegex(RuntimeError, 'No matching faces'):
            bpy.ops.underwhere.select_group(group='EXISTING')

    def test_60_region_selection_on_comparison_maps_to_body_faces(self):
        import bmesh
        _, _, s = fx.setup(alpha=.5)
        self.analyze(s)
        s.preview_mode = 'CLASSIFY'
        bpy.ops.underwhere.preview()
        bpy.ops.underwhere.edit_selection(target='COMPARISON')
        preview = adapter.current_preview(bpy.context.scene)
        self.assertEqual(bpy.context.edit_object, preview)
        mesh = bmesh.from_edit_mesh(preview.data)
        mesh.faces.ensure_lookup_table()
        for index in (1, 3, 4):  # stands in for a box / lasso / paint selection
            mesh.faces[index].select_set(True)
        bmesh.update_edit_mesh(preview.data)
        mapping = list(preview["underwhere_face_map"])
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='HIDE', review_only=True)
        plan = workflow.read_report(s)["output_plan"]
        self.assertEqual(plan["manual_risk_faces"], sorted(mapping[i] for i in (1, 3, 4)))
        # The comparison is redrawn, not left stale or deleted, and selection
        # continues on it so the next region can be dragged right away.
        redrawn = adapter.current_preview(bpy.context.scene)
        self.assertIsNotNone(redrawn)
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        self.assertEqual(bpy.context.edit_object, redrawn)
        self.assertEqual(redrawn.data.total_face_sel, 0)
        bpy.ops.underwhere.finish_selection()
        self.assertEqual(bpy.context.mode, 'OBJECT')
        self.assertTrue(redrawn.hide_select)
        self.assertEqual(bpy.context.view_layer.objects.active, s.body)

    def test_61_review_only_filter_never_overrides_decided_faces(self):
        body, _, s = fx.setup()  # closed opaque shell: every face is a Candidate
        report = self.analyze(s)
        self.assertEqual(ui.review_faces_only(report, list(range(6))), [])
        bpy.ops.underwhere.edit_selection(target='BODY')
        bpy.ops.mesh.select_all(action='SELECT')
        with self.assertRaisesRegex(RuntimeError, 'No unsure faces'):
            bpy.ops.underwhere.override('EXEC_DEFAULT', action='HIDE', review_only=True)
        bpy.ops.object.mode_set(mode='OBJECT')
        self.assertEqual(workflow.read_report(s)["overrides"], {})

    def test_62_switching_selection_tools_keeps_the_current_selection(self):
        import bmesh
        _, _, s = fx.setup(alpha=.5)
        self.analyze(s)
        bpy.ops.underwhere.preview()
        bpy.ops.underwhere.edit_selection(target='COMPARISON', tool='BOX')
        preview = adapter.current_preview(bpy.context.scene)
        mesh = bmesh.from_edit_mesh(preview.data)
        mesh.faces.ensure_lookup_table()
        mesh.faces[2].select_set(True)
        bmesh.update_edit_mesh(preview.data)
        for tool in ('LASSO', 'CIRCLE'):
            bpy.ops.underwhere.edit_selection(target='COMPARISON', tool=tool)
        self.assertEqual(adapter.selected_preview_faces(preview), [list(preview["underwhere_face_map"])[2]])
        bpy.ops.object.mode_set(mode='OBJECT')


    def test_63_previous_name_settings_and_assumptions_migrate(self):
        body, shell, s = fx.setup()
        mask = fx.mask(body)
        scene = bpy.context.scene
        scene['body_occlusion_mask'] = {
            'body': body, 'mode': 1, 'existing_mask': mask.name,
            'spatial_step': .07, 'angle': 30.0, 'scope': 1, 'frames': '1,10',
            'selection_target': 1, 'override_review_only': False,
            'result_json': 'obsolete full report', 'occluders': [{'object': shell}]}
        s.body = None
        s.occluders.clear()
        scene.unit_settings.scale_length = .01
        material = shell.data.materials[0]
        material['obma_assume_opaque'] = True
        old_preview = fx.cube('OldComparison', .1)
        old_preview['body_occlusion_mask_owner'] = f'PREVIEW:{scene.name_full}'
        old_name = old_preview.name
        self.assertFalse(ui.mesh_poll(None, old_preview))
        ui.migrate_settings(scene)
        self.assertEqual(s.body, body)
        self.assertEqual(s.occluders[0].object, shell)
        self.assertEqual(s.mode, 'AUDIT')
        self.assertEqual(s.existing_mask, mask.name)
        self.assertAlmostEqual(s.spatial_step, .07)  # Already stored in metres.
        self.assertEqual(s.scope, 'EXPLICIT_FRAMES')
        self.assertEqual(s.frames, '1,10')
        self.assertEqual(s.selection_target, 'BODY')
        self.assertFalse(s.override_review_only)
        self.assertFalse(s.result_json)
        self.assertNotIn('body_occlusion_mask', scene)
        self.assertNotIn(old_name, bpy.data.objects)
        self.assertTrue(material.underwhere_assume_opaque)
        self.assertNotIn('obma_assume_opaque', material)
        report = self.analyze(s)
        self.assertEqual(report['counts'], {CANDIDATE: 6})


    def test_64_read_only_legacy_material_does_not_block_migration(self):
        _, _, s = fx.setup(alpha=.2)
        material = fx.material('LegacyLinkedMaterial')
        material['obma_assume_opaque'] = True
        library = str(OUT / 'legacy_linked_material.blend')
        bpy.data.libraries.write(library, {material})
        with bpy.data.libraries.load(library, link=True) as (src, dst):
            dst.materials = [material.name]
        linked = dst.materials[0]
        self.assertIsNotNone(linked.library)
        ui.migrate_settings(bpy.context.scene)
        self.assertTrue(linked['obma_assume_opaque'])
        self.assertFalse(adapter.material_policy(linked)['user_assumed_opaque'])
        self.assertEqual(bpy.ops.underwhere.analyze(), {'FINISHED'})
        self.assertEqual(workflow.read_report(s)['counts'], {REVIEW: 6})


    def test_65_linked_scene_is_not_modified_by_name_migration(self):
        body, shell, s = fx.setup()
        previous = bpy.data.scenes.new('LegacyLinkedScene')
        previous['body_occlusion_mask'] = {'spatial_step': .07, 'frames': '1,10'}
        library = str(OUT / 'legacy_linked_scene.blend')
        # Save a complete disposable library copy: the subset writer does not
        # reliably serialize a standalone Scene in the supported Blender build.
        bpy.ops.wm.save_as_mainfile(filepath=library, copy=True, compress=False)
        with bpy.data.libraries.load(library, link=True) as (src, dst):
            dst.scenes = [previous.name]
        linked = dst.scenes[0]
        self.assertIsNotNone(linked.library)
        ui.migrate_settings(linked)
        ui.on_load(None)
        ui.on_undo(None)
        self.assertIn('body_occlusion_mask', linked)
        self.assertEqual(s.body, body)

    def test_66_comparison_selection_starts_without_update_and_survives_refusals(self):
        _, _, s = fx.setup(alpha=.5)  # every face Review for an untrusted material
        self.analyze(s)
        scene = bpy.context.scene
        s.preview_mode = 'OFF'
        # Box / Lasso / Brush show the comparison themselves.
        bpy.ops.underwhere.edit_selection(target='COMPARISON', tool='BOX')
        preview = adapter.current_preview(scene)
        self.assertIsNotNone(preview)
        self.assertEqual(s.preview_mode, 'CLASSIFY')
        self.assertEqual(bpy.context.edit_object, preview)
        # Keep with nothing selected is refused without leaving the selection.
        with self.assertRaisesRegex(RuntimeError, 'No faces selected'):
            bpy.ops.underwhere.override('EXEC_DEFAULT', action='KEEP')
        self.assertEqual(bpy.context.edit_object, preview)
        # Changing the comparison while selecting keeps selecting on the new one.
        s.preview_mode = 'DIFF'
        bpy.ops.underwhere.preview()
        redrawn = adapter.current_preview(scene)
        self.assertTrue(redrawn.name.endswith('DIFF'))
        self.assertEqual(bpy.context.edit_object, redrawn)
        self.assertEqual(sum(adapter.is_preview(obj) for obj in bpy.data.objects), 1)
        # Bulk selection from the comparison moves to the Body instead of failing.
        bpy.ops.underwhere.select_group(group='REVIEW')
        self.assertEqual(bpy.context.edit_object, s.body)
        self.assertEqual(s.body.data.total_face_sel, 6)
        bpy.ops.underwhere.finish_selection()
        self.assertEqual(bpy.context.mode, 'OBJECT')
        # Off removes the comparison even when chosen while selecting on it.
        bpy.ops.underwhere.edit_selection(target='COMPARISON')
        s.preview_mode = 'OFF'
        bpy.ops.underwhere.preview()
        self.assertIsNone(adapter.current_preview(scene))
        self.assertEqual(bpy.context.mode, 'OBJECT')

    def test_67_review_only_refusal_keeps_the_comparison_selection(self):
        import bmesh
        _, _, s = fx.setup()  # closed opaque shell: every face is a Candidate
        self.analyze(s)
        bpy.ops.underwhere.edit_selection(target='COMPARISON')
        preview = adapter.current_preview(bpy.context.scene)
        mesh = bmesh.from_edit_mesh(preview.data)
        for face in mesh.faces:
            face.select_set(True)
        bmesh.update_edit_mesh(preview.data)
        with self.assertRaisesRegex(RuntimeError, 'No unsure faces'):
            bpy.ops.underwhere.override('EXEC_DEFAULT', action='HIDE', review_only=True)
        # The same faces stay selected so the user can untick the filter and retry.
        self.assertEqual(bpy.context.edit_object, preview)
        self.assertEqual(preview.data.total_face_sel, 6)
        self.assertEqual(workflow.read_report(s)["overrides"], {})
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='HIDE', review_only=False)
        self.assertEqual(len(workflow.read_report(s)["overrides"]), 6)
        self.assertEqual(bpy.context.mode, 'EDIT_MESH')
        bpy.ops.underwhere.finish_selection()

    def test_68_other_mesh_in_edit_mode_is_never_left_silently(self):
        _, shell, s = fx.setup(alpha=.5)
        self.analyze(s)
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        shell.select_set(True)
        bpy.context.view_layer.objects.active = shell
        bpy.ops.object.mode_set(mode='EDIT')
        for target in ('COMPARISON', 'BODY'):
            with self.assertRaisesRegex(RuntimeError, 'Leave Edit Mode on FixtureShell'):
                bpy.ops.underwhere.edit_selection(target=target)
            self.assertEqual(bpy.context.edit_object, shell)
        bpy.ops.object.mode_set(mode='OBJECT')


    def preview_labels(self):
        preview = adapter.current_preview(bpy.context.scene)
        names = [preview.data.materials[p.material_index].name for p in preview.data.polygons]
        return [name.removeprefix("UnderWhere_View_").split(".")[0] for name in names]

    def test_69_manual_keep_hide_have_their_own_colors_and_colors_can_be_hidden(self):
        import bmesh
        _, _, s = fx.setup(alpha=.5)  # every face Review for an untrusted material
        self.analyze(s)
        s.preview_mode = 'CLASSIFY'
        bpy.ops.underwhere.preview()
        self.assertEqual(set(self.preview_labels()), {"REVIEW"})
        s.face_index = 0
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='HIDE', selected=False)
        s.face_index = 1
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='KEEP', selected=False)
        # Your Keep / Hide recolor the comparison; the evidence itself is unchanged.
        self.assertEqual(self.preview_labels()[:2], ["MANUAL_HIDE", "MANUAL_KEEP"])
        self.assertEqual(workflow.read_report(s)["faces"][0]["verdict"], REVIEW)
        # Turning colors off redraws the comparison with only the shown faces.
        s.preview_show = {'MANUAL_HIDE'}
        preview = adapter.current_preview(bpy.context.scene)
        self.assertEqual(list(preview["underwhere_face_map"]), [0])
        self.assertEqual(self.preview_labels(), ["MANUAL_HIDE"])
        s.preview_show = {'REVIEW', 'MANUAL_KEEP'}
        self.assertEqual(list(adapter.current_preview(bpy.context.scene)["underwhere_face_map"]),
                         [1, 2, 3, 4, 5])
        # Region selection on a filtered comparison still maps to the Body faces.
        bpy.ops.underwhere.edit_selection(target='COMPARISON')
        preview = adapter.current_preview(bpy.context.scene)
        mesh = bmesh.from_edit_mesh(preview.data)
        for face in mesh.faces:
            face.select_set(True)
        bmesh.update_edit_mesh(preview.data)
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='RESET')
        self.assertEqual(workflow.read_report(s)["overrides"], {"0": "HIDE"})
        bpy.ops.underwhere.finish_selection()

    def test_70_body_split_into_several_objects(self):
        body, shell, s = fx.setup()  # closed opaque shell around the Body
        head = fx.cube("FixtureHead", .05)
        head.location.z = .5
        s.use_extra_bodies = True
        bpy.ops.object.select_all(action='DESELECT')
        head.select_set(True)
        bpy.ops.underwhere.body_part()
        self.assertEqual([item.object for item in s.extra_bodies], [head])
        report = self.analyze(s)
        self.assertEqual(report["counts"], {CANDIDATE: 12})
        self.assertEqual([(p["name"], p["face_offset"], p["face_count"])
                          for p in report["input"]["body_parts"]],
                         [("FixtureBody", 0, 6), ("FixtureHead", 6, 6)])
        self.assertEqual(ui.face_caption(report, 7), "FixtureHead face 1")
        # Selecting on the Body edits every Body object together.
        bpy.ops.underwhere.edit_selection(target='BODY')
        self.assertEqual(set(bpy.context.objects_in_mode), {body, head})
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='KEEP', review_only=False)
        self.assertEqual(len(workflow.read_report(s)["overrides"]), 12)
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='RESET')
        bpy.ops.underwhere.finish_selection()
        s.face_index = 0
        bpy.ops.underwhere.face(action='SELECT')  # face 0 lives on the Body
        self.assertEqual(body.data.total_face_sel, 1)
        self.assertEqual(head.data.total_face_sel, 0)
        bpy.ops.object.mode_set(mode='OBJECT')
        # One output copy per Body object, each with its own share of the plan.
        before = set(bpy.data.objects)
        self.assertEqual(bpy.ops.underwhere.apply(), {'FINISHED'})
        created = {obj.name for obj in set(bpy.data.objects) - before}
        self.assertEqual(created, {"UnderWhere_Result_FixtureBody", "UnderWhere_Result_FixtureHead"})
        for name in created:
            self.assertEqual(adapter.evaluated_counts(bpy.context, bpy.data.objects[name]), (0, 0))
        self.assertEqual(len(body.data.polygons), 6)  # sources untouched
        # The comparison shows both parts beside the Body.
        bpy.ops.underwhere.preview()
        self.assertEqual(len(adapter.current_preview(bpy.context.scene).data.polygons), 12)
        # A Body part cannot also be an occluder, and Audit stays one object at a time.
        s.extra_bodies.add().object = shell
        with self.assertRaisesRegex(adapter.InputError, "DUPLICATE"):
            adapter.snapshot(bpy.context, s)
        s.extra_bodies.remove(len(s.extra_bodies) - 1)
        s.mode = 'AUDIT'
        with self.assertRaisesRegex(adapter.InputError, "MULTI_BODY_AUDIT_UNSUPPORTED"):
            adapter.snapshot(bpy.context, s)

    def test_71_poses_mode_shows_the_share_of_frames_that_hide_each_face(self):
        _, shell, s = fx.setup()
        scene = bpy.context.scene
        shell.keyframe_insert("location", frame=1)
        shell.location.x = 5  # frame 2: the clothing has moved away
        shell.keyframe_insert("location", frame=2)
        scene.frame_set(1)
        s.scope = 'EXPLICIT_FRAMES'
        s.frames = "2"
        report = self.analyze(s)
        self.assertEqual(len(report["sampled_states"]), 2)
        # Exposed in one frame is enough to keep the face (strict union).
        self.assertEqual(report["counts"], {KEEP: 6})
        self.assertEqual({(f["hidden_states"], f["exposed_states"]) for f in report["faces"]}, {(1, 1)})
        s.preview_mode = 'POSES'
        bpy.ops.underwhere.preview()
        self.assertEqual(set(self.preview_labels()), {"POSES_HALF"})
        self.assertEqual(adapter.poses_label(1.0), "POSES_ALL")
        self.assertEqual(adapter.poses_label(.8), "POSES_MOST")
        self.assertEqual(adapter.poses_label(.3), "POSES_FEW")
        self.assertEqual(adapter.poses_label(0.0), "POSES_NONE")


    def test_72_empty_animation_data_does_not_untrust_a_material(self):
        material = fx.material("FbxImported")
        material.animation_data_create()  # FBX imports leave empty containers like these
        material.node_tree.animation_data_create()
        material.node_tree.animation_data.action = bpy.data.actions.new("EmptyAction")
        policy = adapter.material_policy(material)
        self.assertEqual(policy["automatic_verdict"], "CONSTANT_OPAQUE_PRINCIPLED")
        self.assertEqual(policy["animation"], [])
        # Real keyframes or drivers still make it untrusted, with the source named.
        material.node_tree.nodes["Principled BSDF"].inputs["Alpha"].keyframe_insert("default_value", frame=1)
        policy = adapter.material_policy(material)
        self.assertEqual(policy["automatic_verdict"], "ANIMATED_MATERIAL_UNSUPPORTED")
        self.assertEqual(policy["animation"], ["action"])
        driven = fx.material("Driven")
        driven.driver_add("roughness")
        self.assertEqual(adapter.material_policy(driven)["animation"], ["drivers"])

    def test_73_body_imported_100x_too_large_is_sampled_at_human_scale(self):
        body, shell, s = fx.setup()
        for obj in (body, shell):
            for vertex in obj.data.vertices:
                vertex.co *= 100
            obj.data.update()
        report = self.analyze(s)
        self.assertAlmostEqual(report["input"]["body_size_metres"], 20.0, places=4)
        self.assertEqual(report["input"]["settings"]["scale_normalization"], 0.1)
        self.assertEqual(report["counts"], {CANDIDATE: 6})
        # Without the normalization the cover cannot reach the step: all Review (the reported bug).
        with patch.object(adapter, "scale_normalization", return_value=1.0):
            self.assertEqual(self.analyze(s)["counts"], {REVIEW: 6})
        self.assertEqual(adapter.scale_normalization(1.5), 1.0)
        self.assertEqual(adapter.scale_normalization(0.015), 1.0)  # small Bodies already work

    def test_74_tiny_fbx_object_scale_is_accepted_and_real_singularity_explained(self):
        body, _, s = fx.setup()
        for vertex in body.data.vertices:
            vertex.co *= 10000
        body.data.update()
        body.scale = (0.0001, 0.0001, 0.0001)  # determinant 1e-12, world size unchanged
        bpy.context.view_layer.update()
        self.assertEqual(self.analyze(s)["counts"], {CANDIDATE: 6})
        body.scale = (1.0, 0.0, 1.0)
        bpy.context.view_layer.update()
        with self.assertRaises(adapter.InputError) as caught:
            adapter.snapshot(bpy.context, s)
        self.assertEqual(str(caught.exception), "SINGULAR_TRANSFORM: FixtureBody")
        self.assertIn("Ctrl+A", ui.describe_message(str(caught.exception)))

    def test_75_untrusted_materials_are_named_and_opaque_restores_candidates(self):
        _, shell, s = fx.setup(alpha=.5)
        report = self.analyze(s)
        self.assertEqual(report["counts"], {REVIEW: 6})
        material = shell.data.materials[0]
        self.assertEqual(ui.material_blockers(report), [(material.name, 6)])
        material.underwhere_assume_opaque = True  # the switch the Results panel offers
        self.assertEqual(self.analyze(s)["counts"], {CANDIDATE: 6})
        self.assertEqual(ui.stale_explanation("STALE: file loaded; Analyze again")[0],
                         "Results are not saved in .blend files.")


    def test_76_edited_comparison_never_moves_keep_hide_to_another_face(self):
        import bmesh
        _, _, s = fx.setup(alpha=.5)  # every face Review
        self.analyze(s)
        bpy.ops.underwhere.edit_selection(target='COMPARISON', tool='BOX')
        preview = adapter.current_preview(bpy.context.scene)
        # Reordering faces keeps each face's source index.
        bpy.ops.mesh.select_all(action='SELECT')  # sort_elements reorders the selection
        bpy.ops.mesh.sort_elements(type='REVERSE', elements={'FACE'})
        bpy.ops.mesh.select_all(action='DESELECT')
        mesh = bmesh.from_edit_mesh(preview.data)
        mesh.faces.ensure_lookup_table()
        mesh.faces[0].select_set(True)  # after reversing, this face shows source face 5
        bmesh.update_edit_mesh(preview.data)
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='KEEP')
        self.assertEqual(workflow.read_report(s)["overrides"], {"5": "KEEP"})
        # Deleting a face (the reported case) is refused instead of shifting indices.
        preview = adapter.current_preview(bpy.context.scene)
        mesh = bmesh.from_edit_mesh(preview.data)
        mesh.faces.ensure_lookup_table()
        bmesh.ops.delete(mesh, geom=[mesh.faces[0]], context='FACES')
        mesh.faces.ensure_lookup_table()
        mesh.faces[0].select_set(True)
        bmesh.update_edit_mesh(preview.data)
        with self.assertRaisesRegex(RuntimeError, "comparison mesh was edited"):
            bpy.ops.underwhere.override('EXEC_DEFAULT', action='KEEP')
        self.assertEqual(workflow.read_report(s)["overrides"], {"5": "KEEP"})
        self.assertEqual(bpy.context.edit_object, preview)
        bpy.ops.underwhere.finish_selection()


    def test_77_choices_survive_reanalysis_and_reload_while_the_faces_match(self):
        import bmesh
        body, _, s = fx.setup(alpha=.5)  # every face unsure
        self.analyze(s)
        s.face_index = 2
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='HIDE', selected=False)
        self.assertIn('"HIDE":[2]', s.saved_choices)
        # Results live only in the session; the file keeps the choices.
        workflow.REPORT_CACHE.clear()
        report = self.analyze(s)
        self.assertEqual(report["overrides"], {"2": "HIDE"})
        self.assertEqual(report["carried_choices"], 1)
        self.assertEqual(report["output_plan"]["requested_faces"], [2])
        bpy.ops.underwhere.clear_choices('EXEC_DEFAULT')
        self.assertEqual(workflow.read_report(s)["overrides"], {})
        self.assertIn('"HIDE":[]', s.saved_choices)
        # Choices for other faces are never applied.
        s.face_index = 0
        bpy.ops.underwhere.override('EXEC_DEFAULT', action='KEEP', selected=False)
        mesh = bmesh.new()
        mesh.from_mesh(body.data)
        mesh.faces.ensure_lookup_table()
        bmesh.ops.delete(mesh, geom=[mesh.faces[5]], context='FACES_ONLY')
        mesh.to_mesh(body.data)
        mesh.free()
        body.data.update()
        report = self.analyze(s)
        self.assertEqual(report["overrides"], {})
        self.assertEqual(report["carried_choices"], 0)

    def test_78_analyze_opens_review_with_colours_and_next_steps(self):
        _, shell, s = fx.setup(alpha=.5)
        self.assertEqual(bpy.ops.underwhere.analyze(), {'FINISHED'})
        self.assertEqual(s.ui_step, 'REVIEW')
        self.assertIsNotNone(adapter.current_preview(bpy.context.scene))  # colours appear right away
        steps = ui.next_steps(workflow.read_report(s))
        self.assertEqual(steps[0]["level"], 'decide')
        self.assertIn(("opaque", shell.data.materials[0].name), steps[0]["actions"])
        self.assertTrue(any(("review",) in item["actions"] for item in steps))
        # With nothing left to decide, the next step is to export.
        _, _, s = fx.setup()
        bpy.ops.underwhere.analyze()
        self.assertEqual([item["level"] for item in ui.next_steps(workflow.read_report(s))], ['done'])
        # Errors read as sentences that say how to fix them, and keep their code.
        self.assertEqual(ui.describe_message("HIDDEN_INPUT: Shirt; make it visible in this view layer"),
                         "Shirt is hidden. Show it in this view layer. (HIDDEN_INPUT)")
        s.status = "MODIFIER_UNSUPPORTED: Body/Subsurf (SUBSURF)"
        kind, lines = ui.status_view(bpy.context, s, None)
        self.assertEqual(kind, 'error')
        self.assertIn("Body/Subsurf", " ".join(lines))
        s.status = "Choose Body and occluders"
        self.assertEqual(ui.status_view(bpy.context, s, None)[0], 'start')

    def test_79_japanese_interface_uses_the_add_on_wording(self):
        prefs = bpy.context.preferences.view
        language, translate = prefs.language, prefs.use_translate_interface
        try:
            prefs.language = 'ja_JP'
            prefs.use_translate_interface = True
            self.assertEqual(i18n.t("Analyze"), "調べる")
            self.assertEqual(ui.reason_label(REVIEW), "要確認")
            # Blender's own catalogue never replaces the add-on's terms.
            self.assertEqual(i18n.t("Keep"), "残す")
            self.assertEqual(i18n.t("Body"), "素体")
            self.assertEqual(ui.describe_message("HIDDEN_INPUT: Shirt"),
                             "Shirt が非表示です。このビューレイヤーで表示してください。 (HIDDEN_INPUT)")
        finally:
            prefs.language, prefs.use_translate_interface = language, translate
        self.assertEqual(i18n.t("Analyze"), "Analyze")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BlenderIntegration)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    (OUT / "integration_summary.json").write_text(json.dumps({
        "blender": bpy.app.version_string, "tests": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped),
    }, indent=2))
    if not result.wasSuccessful():
        raise RuntimeError("Product integration suite failed")
