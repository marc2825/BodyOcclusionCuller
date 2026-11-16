"""Strict Blender boundary; temporary evaluated meshes never escape this module."""
from contextlib import contextmanager
from array import array
import hashlib
import json
import math

import bpy
from mathutils import Vector

from . import VERSION
from .core.contracts import hidden_faces, mask_removed_vertices, output_plan

OWNER = "underwhere_owner"
LEGACY_OWNER = "obma_beta_owner"
OWNER_KEYS = (OWNER, "body_occlusion_mask_owner", LEGACY_OWNER)


def is_preview(obj):
    return any(str(obj.get(key, '')).startswith('PREVIEW:') for key in OWNER_KEYS)


def is_preview_material(material):
    return any(material.get(key) == 'PREVIEW' for key in OWNER_KEYS)


class InputError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode()).hexdigest()


def scalar(value):
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    if isinstance(value, bpy.types.ID):
        return [value.bl_rna.identifier, value.name_full]
    try:
        return [scalar(v) for v in value]
    except TypeError:
        return str(type(value).__name__)


def rna_values(value):
    # Execution timings, user counts and runtime IDs are not inputs.
    # Including those would make a duplicate or even a depsgraph refresh stale.
    return {"rna_type": value.bl_rna.identifier, **{
            p.identifier: scalar(getattr(value, p.identifier))
            for p in value.bl_rna.properties
            if p.identifier != "rna_type" and not p.is_readonly
            and p.type != 'COLLECTION'}}


def material_record(material):
    if material is None:
        return {"name": None, "verdict": "MISSING_MATERIAL"}
    graph = material.node_tree
    record = {
        "name": material.name_full,
        "settings": rna_values(material),
        "nodes": [] if graph is None else [
            {"name": n.name, "type": n.bl_idname, "settings": rna_values(n),
             "inputs": [(s.identifier, scalar(getattr(s, "default_value", None)))
                        for s in n.inputs]}
            for n in graph.nodes],
        "links": [] if graph is None else sorted(
            (l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier)
            for l in graph.links),
    }
    record.update(material_policy(material))
    return record


def material_policy(material):
    """Cheap UI policy, shared with the fingerprinted material record."""
    if material is None:
        return {"automatic_verdict": "MISSING_MATERIAL", "verdict": "MISSING_MATERIAL",
                "user_assumed_opaque": False, "assumption_blocked": False}
    graph = material.node_tree
    culling = any(getattr(material, key, False) for key in (
        "use_backface_culling", "use_backface_culling_shadow", "use_backface_culling_lightprobe"))
    reason = "UNSUPPORTED_SHADER"
    if not material.use_nodes or graph is None:
        reason = "NODE_SURFACE_REQUIRED"
    elif material.animation_data or graph.animation_data:
        reason = "ANIMATED_MATERIAL_UNSUPPORTED"
    elif culling:
        reason = "BACKFACE_CULLING_UNTRUSTED"
    else:
        outputs = [n for n in graph.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output]
        if len(outputs) == 1:
            out = outputs[0]
            surface = out.inputs.get("Surface")
            forbidden = any(out.inputs.get(k) and out.inputs[k].is_linked
                            for k in ("Volume", "Displacement", "Thickness"))
            if surface and len(surface.links) == 1 and not forbidden and out.target == 'ALL':
                node = surface.links[0].from_node
                if node.type == 'BSDF_PRINCIPLED':
                    alpha = node.inputs.get("Alpha")
                    transmission = node.inputs.get("Transmission Weight")
                    weight = node.inputs.get("Weight")
                    if (alpha and transmission and not alpha.is_linked
                            and not transmission.is_linked
                            and alpha.default_value == 1.0
                            and transmission.default_value == 0.0
                            and (weight is None or (
                                not weight.is_linked and weight.default_value == 1.0))):
                        reason = "CONSTANT_OPAQUE_PRINCIPLED"
                    else:
                        reason = "ALPHA_OR_TRANSMISSION_UNTRUSTED"
    requested = bool(getattr(material, "underwhere_assume_opaque", False))
    # Opacity is not two-sidedness. A stored checkbox, including one written
    # through Python, cannot bypass an actual backface-culling setting.
    verdict = "BACKFACE_CULLING_UNTRUSTED" if culling else (
        "USER_ASSUMED_OPAQUE" if requested else reason)
    return {"automatic_verdict": reason, "user_assumed_opaque": requested,
            "assumption_blocked": culling, "verdict": verdict}


def settings_record(settings, scene):
    scale = scene.unit_settings.scale_length
    return {"mode": settings.mode, "preset": settings.preset,
            "r": settings.spatial_step / scale, "epsilon_degrees": settings.angle,
            "spatial_step_metres": settings.spatial_step, "metres_per_world_unit": scale,
            "touch_tolerance": settings.touch_tolerance / scale,
            "scope": settings.scope, "frames": settings.frames,
            "current_pose_always_included": True,
            "material_policy": "DIRECT_CONSTANT_OPAQUE_OR_EXPLICIT_USER_ASSUMPTION_V2",
            "directions": "FULL_SPHERE_GEOMETRIC", "max_subdivision_depth": 4}


def inputs(context, settings):
    if context.mode != 'OBJECT':
        raise InputError("OBJECT_MODE_REQUIRED: switch to Object Mode before analysis/output")
    body = settings.body
    if body is None or body.type != 'MESH':
        raise InputError("BODY_MESH_REQUIRED")
    occluders = [item.object for item in settings.occluders]
    if not occluders or any(o is None for o in occluders):
        raise InputError("OCCLUDER_MESH_REQUIRED: remove empty entries")
    if body in occluders or len(set(occluders)) != len(occluders):
        raise InputError("DUPLICATE_OBJECT: Body cannot also be an occluder")
    for obj in [body] + occluders:
        if obj.type != 'MESH' or not obj.data.polygons:
            raise InputError(f"EMPTY_OR_NON_MESH: {obj.name}")
        if obj.library or obj.data.library or obj.override_library or not obj.is_editable:
            raise InputError(f"LINKED_OR_READ_ONLY: {obj.name}; create a local copy first")
        if obj.name not in context.view_layer.objects or not obj.visible_get():
            raise InputError(f"HIDDEN_INPUT: {obj.name}; make it visible in this view layer")
        if obj.hide_render:
            raise InputError(f"RENDER_HIDDEN_INPUT: {obj.name}")
        if (not getattr(obj, "visible_camera", True) or getattr(obj, "is_holdout", False)
                or getattr(obj, "is_shadow_catcher", False)):
            raise InputError(f"CAMERA_VISIBILITY_UNTRUSTED: {obj.name}")
        layers = [context.view_layer.layer_collection]
        while layers:
            layer = layers.pop()
            layers.extend(layer.children)
            if obj.name in layer.collection.all_objects and (
                    layer.collection.hide_render or layer.holdout or layer.indirect_only):
                raise InputError(f"COLLECTION_VISIBILITY_UNTRUSTED: {obj.name}/{layer.name}")
        if obj.is_instancer:
            raise InputError(f"INSTANCING_UNSUPPORTED: {obj.name}")
        if abs(obj.matrix_world.determinant()) < 1e-12:
            raise InputError(f"SINGULAR_TRANSFORM: {obj.name}")
    target = None
    if settings.mode == 'AUDIT':
        target = body.modifiers.get(settings.existing_mask)
        if target is None or target.type != 'MASK' or target.mode != 'VERTEX_GROUP':
            raise InputError("MASK_REQUIRED: choose a vertex-group Mask Modifier")
        if target.use_smooth:
            raise InputError("SMOOTH_MASK_UNSUPPORTED: disable Smooth on a working copy")
        if not target.vertex_group or body.vertex_groups.get(target.vertex_group) is None:
            raise InputError("MASK_GROUP_MISSING")
        if target.show_viewport != target.show_render:
            raise InputError("MASK_VISIBILITY_MISMATCH: viewport and render flags must agree")
        if list(body.modifiers)[-1] != target:
            raise InputError("MASK_MUST_BE_LAST: preceding Armature deformation is supported")
    for obj in [body] + occluders:
        for modifier in obj.modifiers:
            if obj == body and modifier == target:
                continue
            # Disabled unknown modifiers also refuse: the output must not become
            # silently different when switched on for rendering or later editing.
            if modifier.type != 'ARMATURE' and not (obj != body and modifier.type == 'SOLIDIFY'):
                raise InputError(f"MODIFIER_UNSUPPORTED: {obj.name}/{modifier.name} ({modifier.type})")
            if modifier.show_viewport != modifier.show_render:
                raise InputError(f"MODIFIER_VISIBILITY_MISMATCH: {modifier.name}")
    return body, occluders, target


@contextmanager
def unmasked(context, target):
    if target is None:
        yield
        return
    flags = target.show_viewport, target.show_render
    try:
        target.show_viewport = False
        target.show_render = False
        context.view_layer.update()
        yield
    finally:
        target.show_viewport, target.show_render = flags
        context.view_layer.update()


def geometry(obj, depsgraph, *, require_correspondence=True):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    try:
        if mesh is None or not mesh.polygons:
            raise InputError(f"EMPTY_EVALUATED_MESH: {obj.name}")
        polygons = [list(p.vertices) for p in mesh.polygons]
        source = [list(p.vertices) for p in obj.data.polygons]
        if require_correspondence and (len(mesh.vertices) != len(obj.data.vertices) or polygons != source):
            raise InputError(f"TOPOLOGY_CORRESPONDENCE_FAILED: {obj.name}")
        mesh.calc_loop_triangles()
        vertices = [tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices]
        if any(not math.isfinite(c) for v in vertices for c in v):
            raise InputError(f"NONFINITE_GEOMETRY: {obj.name}")
        triangles = [(t.polygon_index, list(t.vertices)) for t in mesh.loop_triangles]
        materials = [material_record(slot.material) for slot in evaluated.material_slots]
        keys = obj.data.shape_keys
        rigs = []
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE' and mod.object:
                rigs.append({"name": mod.object.name,
                             "pose": [(b.name, [list(row) for row in b.matrix])
                                      for b in mod.object.pose.bones]})
        return {
            "name": obj.name_full, "mesh": obj.data.name_full,
            "vertices": vertices, "polygons": polygons, "triangles": triangles,
            "material_indices": [p.material_index for p in mesh.polygons],
            "materials": materials,
            "source_vertices": [tuple(v.co) for v in obj.data.vertices],
            "groups": [g.name for g in obj.vertex_groups],
            "weights": [[(g.group, g.weight) for g in v.groups] for v in obj.data.vertices],
            "modifiers": [rna_values(m) for m in obj.modifiers],
            "source_polygons_digest": digest(source),
            "shape_keys": [] if keys is None else [
                (k.name, k.value, k.mute, k.relative_key.name, coordinates_digest(k.data))
                for k in keys.key_blocks],
            "rigs": rigs,
        }
    finally:
        evaluated.to_mesh_clear()


@contextmanager
def without_solidify(context, obj):
    modifiers = [(m, m.show_viewport, m.show_render) for m in obj.modifiers if m.type == 'SOLIDIFY']
    try:
        for modifier, _, _ in modifiers:
            modifier.show_viewport = modifier.show_render = False
        context.view_layer.update()
        yield
    finally:
        for modifier, viewport, render in modifiers:
            modifier.show_viewport, modifier.show_render = viewport, render
        context.view_layer.update()


def occluder_geometry(context, obj):
    if not any(mod.type == 'SOLIDIFY' for mod in obj.modifiers):
        return geometry(obj, context.evaluated_depsgraph_get())
    # Verify ordered source correspondence before Solidify. Its rim closes the
    # boundary graph without closing the aperture, so opening probes must be
    # constructed from this separate evaluated surface.
    with without_solidify(context, obj):
        source = geometry(obj, context.evaluated_depsgraph_get())
    # Blocker hits index the final evaluated faces/material slots, never source
    # Body faces. Only this explicit blocker extraction may change topology.
    result = geometry(obj, context.evaluated_depsgraph_get(), require_correspondence=False)
    result["opening_geometry"] = {"vertices": source["vertices"], "polygons": source["polygons"]}
    result["opening_geometry_policy"] = "PRE_SOLIDIFY_EVALUATED"
    return result


def coordinates_digest(points):
    """Hash RNA float buffers in C; avoid millions of Python tuples/JSON floats."""
    coordinates = array('f', [0.0]) * (3 * len(points))
    points.foreach_get("co", coordinates)
    return hashlib.sha256(coordinates.tobytes()).hexdigest()


def evaluated_counts(context, obj):
    evaluated = obj.evaluated_get(context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        mesh.calc_loop_triangles()
        return len(mesh.polygons), len(mesh.loop_triangles)
    finally:
        evaluated.to_mesh_clear()


def snapshot(context, settings):
    body, occluders, target = inputs(context, settings)
    target_record = rna_values(target) if target else None
    with unmasked(context, target):
        depsgraph = context.evaluated_depsgraph_get()
        bdata = geometry(body, depsgraph)
        odata = [occluder_geometry(context, o) for o in occluders]
    # Hash original flags, not the temporary disabled state.
    bdata["modifiers"] = [rna_values(m) for m in body.modifiers]
    existing = {"name": None, "hidden_faces": [], "settings": None}
    if target:
        group = body.vertex_groups[target.vertex_group]
        weights = [next((g.weight for g in v.groups if g.group == group.index), 0.0)
                   for v in body.data.vertices]
        removed = mask_removed_vertices(weights, target.threshold, target.invert_vertex_group)
        hidden = hidden_faces(bdata["polygons"], removed) if target.show_viewport else set()
        counts = evaluated_counts(context, body)
        expected = (len(bdata["polygons"]) - len(hidden),
                    sum(1 for fi, _ in bdata["triangles"] if fi not in hidden))
        if counts != expected:
            raise InputError(f"MASK_EVALUATION_MISMATCH: expected {expected}, evaluated {counts}")
        existing = {"name": target.name, "hidden_faces": sorted(hidden),
                    "settings": target_record, "evaluated_remaining_counts": counts,
                    "enabled": target.show_viewport}
    state = {
        "body": bdata, "occluders": odata, "settings": settings_record(settings, context.scene),
        "existing_mask": existing,
        "frame": context.scene.frame_current, "subframe": context.scene.frame_subframe,
        "blender": bpy.app.version_string, "extension": VERSION,
        "scene": context.scene.name_full,
    }
    return state, digest(state)


def visibility_signature(context, settings):
    """No evaluated meshes; catches visibility switches missed by depsgraph flags."""
    objects = [settings.body] + [item.object for item in settings.occluders]
    flags = []
    for obj in objects:
        flags.append(None if obj is None else (
            obj.as_pointer(), obj.hide_get(), obj.hide_viewport, obj.hide_render,
            obj.visible_get(), getattr(obj, 'visible_camera', True),
            getattr(obj, 'is_holdout', False), getattr(obj, 'is_shadow_catcher', False)))
    layers, collections = [context.view_layer.layer_collection], []
    while layers:
        layer = layers.pop()
        layers.extend(layer.children)
        collections.append((layer.name, layer.exclude, layer.hide_viewport, layer.holdout,
                            layer.indirect_only, layer.collection.hide_render,
                            layer.collection.hide_viewport))
    slots = tuple(None if obj is None else tuple(
        (slot.link, slot.material.as_pointer() if slot.material else 0)
        for slot in obj.material_slots) for obj in objects)
    return (context.view_layer.name, tuple(flags), tuple(collections), slots)


def remove_owned(obj):
    mesh = obj.data if obj.type == 'MESH' else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def link_to_source(duplicate, body):
    for collection in body.users_collection:
        collection.objects.link(duplicate)


def apply_duplicate(context, settings, report, *, deleted=False):
    """Transactional copy. Source, original groups and original masks stay intact."""
    body, _, target = inputs(context, settings)
    plan = output_plan(report)
    duplicate = body.copy()
    try:
        duplicate.data = body.data.copy()
        duplicate.name = f"UnderWhere_{'Export' if deleted else 'Result'}_{body.name}"
        duplicate[OWNER] = "OUTPUT"
        link_to_source(duplicate, body)
        if target:
            duplicate.modifiers.remove(duplicate.modifiers[target.name])
        group = duplicate.vertex_groups.new(name="UnderWhere_Hide")
        if plan["removed_vertices"]:
            group.add(plan["removed_vertices"], 1.0, 'REPLACE')
        mod = duplicate.modifiers.new("UnderWhere_Mask", 'MASK')
        mod.mode = 'VERTEX_GROUP'
        mod.vertex_group = group.name
        mod.threshold = 0.5
        mod.invert_vertex_group = True
        mod.use_smooth = False
        modifier_name = mod.name
        context.view_layer.update()
        counts = evaluated_counts(context, duplicate)
        expected = (len(report["faces"]) - plan["hidden_polygon_count"],
                    sum(f["triangles"] for f in report["faces"]) - plan["hidden_triangle_count"])
        if counts != expected:
            raise InputError(f"OUTPUT_EVALUATION_MISMATCH: expected {expected}, evaluated {counts}")
        if deleted:
            # BMesh preserves shape-key layers, UVs and deform weights while
            # removing the same conservative vertex set as the verified Mask.
            import bmesh
            duplicate.modifiers.remove(mod)
            bm = bmesh.new()
            try:
                bm.from_mesh(duplicate.data)
                bm.verts.ensure_lookup_table()
                bmesh.ops.delete(bm, geom=[bm.verts[i] for i in plan['removed_vertices']],
                                 context='VERTS')
                bm.to_mesh(duplicate.data)
                duplicate.data.update()
            finally:
                bm.free()
            counts = evaluated_counts(context, duplicate)
            if counts != expected:
                raise InputError("DELETED_COPY_EVALUATION_MISMATCH")
        return {"object": duplicate.name, "group": group.name,
                "modifier": None if deleted else modifier_name,
                "kind": "DELETED_COPY" if deleted else "MASK_COPY",
                "evaluated_remaining_polygons": counts[0],
                "evaluated_remaining_triangles": counts[1], "plan": plan}
    except Exception:
        remove_owned(duplicate)
        raise


def measure_plan(context, settings, report):
    """Evaluate the actual proposed Modifier on a disposable copy before Apply."""
    output = apply_duplicate(context, settings, report)
    try:
        return {
            "verified_with_blender": True,
            "plan_digest": digest(output["plan"]),
            "remaining_polygons": output["evaluated_remaining_polygons"],
            "remaining_triangles": output["evaluated_remaining_triangles"],
        }
    finally:
        remove_owned(bpy.data.objects[output["object"]])


COLORS = {
    "KEEP_EXPOSED": (0.1, 0.5, 1.0, 1.0),
    "REVIEW": (1.0, 0.65, 0.04, 1.0),
    "HIDE_CANDIDATE": (0.1, 0.8, 0.3, 1.0),
    "UNSAFE_EXISTING_MASK": (1.0, 0.08, 0.15, 1.0),
    "UNCERTAIN_EXISTING_MASK": (0.8, 0.1, 0.8, 1.0),
    "ORIGINAL": (0.55, 0.55, 0.55, 1.0),
    # Before / After: existing hides versus the planned output.
    "DIFF_STILL_HIDDEN": (0.18, 0.18, 0.18, 1.0),
    "DIFF_RESTORED": (0.1, 0.5, 1.0, 1.0),
    "DIFF_NEWLY_HIDDEN": (0.1, 0.8, 0.3, 1.0),
    "DIFF_VISIBLE": (0.8, 0.8, 0.8, 1.0),
}


def diff_label(face, before, after):
    if face in before:
        return "DIFF_STILL_HIDDEN" if face in after else "DIFF_RESTORED"
    return "DIFF_NEWLY_HIDDEN" if face in after else "DIFF_VISIBLE"


def current_preview(scene):
    return next((obj for obj in bpy.data.objects
                 if obj.get(OWNER) == f"PREVIEW:{scene.name_full}"), None)


def selected_preview_faces(obj):
    """Source face indices of the faces selected on a comparison mesh in Edit Mode."""
    import bmesh
    mapping = list(obj.get("underwhere_face_map", []))
    mesh = bmesh.from_edit_mesh(obj.data)
    return sorted({mapping[f.index] for f in mesh.faces if f.select and f.index < len(mapping)})


def clear_preview(scene):
    for obj in list(bpy.data.objects):
        if any(obj.get(key) == f"PREVIEW:{scene.name_full}" for key in OWNER_KEYS):
            # Never delete an object the user is editing; operators leave Edit
            # Mode first, and a later refresh removes it.
            if obj.mode == 'EDIT':
                continue
            remove_owned(obj)
    for mat in list(bpy.data.materials):
        if any(mat.get(key) == "PREVIEW" for key in OWNER_KEYS) and mat.users == 0:
            bpy.data.materials.remove(mat)


def preview(context, report, mode):
    clear_preview(context.scene)
    if mode == 'OFF':
        return None
    plan = output_plan(report)
    hidden = set(plan["hidden_faces"]) if mode == 'OUTPUT' else set()
    before = set(report["existing_mask"]["hidden_faces"])
    after = set(plan["hidden_faces"])
    vertices = report["preview_vertices"]
    # Compare alongside the source without touching its visibility or transforms.
    offset = report["preview_offset_x"]
    mesh = bpy.data.meshes.new("UnderWhere_Comparison")
    obj = None
    try:
        mesh.from_pydata([(x + offset, y, z) for x, y, z in vertices], [],
                         [p for i, p in enumerate(report["source_polygons"]) if i not in hidden])
        obj = bpy.data.objects.new("UnderWhere_Comparison_" + mode, mesh)
        obj[OWNER] = f"PREVIEW:{context.scene.name_full}"
        # Comparison face i shows source face face_map[i]; region selection on
        # the colored comparison is mapped back to the Body through this.
        obj["underwhere_face_map"] = [f["face"] for f in report["faces"] if f["face"] not in hidden]
        obj.hide_render = True
        obj.hide_select = True
        context.collection.objects.link(obj)
        names = list(COLORS)
        for name, color in COLORS.items():
            mat = bpy.data.materials.new("UnderWhere_View_" + name)
            mat[OWNER] = "PREVIEW"
            mat.diffuse_color = color
            mat.use_nodes = True
            shader = mat.node_tree.nodes.get("Principled BSDF")
            shader.inputs["Base Color"].default_value = color
            mesh.materials.append(mat)
        visible = [f for f in report["faces"] if f["face"] not in hidden]
        for poly, face in zip(mesh.polygons, visible):
            if mode == 'CLASSIFY':
                label = face["finding"] or face["verdict"]
            elif mode == 'DIFF':
                label = diff_label(face["face"], before, after)
            else:
                label = "ORIGINAL"
            poly.material_index = names.index(label)
        return obj
    except Exception:
        if obj:
            remove_owned(obj)
        elif mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        raise
