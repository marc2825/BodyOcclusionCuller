"""Generated test geometry only; no external models."""
import bpy

VERTICES = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
            (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
POLYGONS = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
            (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def reset():
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    s = bpy.context.scene.underwhere
    s.result_json = ""  # first, so no update below redraws an old result
    s.display_target = 'BESIDE'
    s.preview_mode = 'CLASSIFY'
    s.body = None
    s.occluders.clear()
    s.use_extra_bodies = False
    s.saved_choices = ""
    s.notice = ""
    s.ui_step = 'SETUP'
    s.extra_bodies.clear()
    s.preview_show = {'HIDE_CANDIDATE', 'KEEP_EXPOSED', 'REVIEW', 'UNSAFE_EXISTING_MASK',
                      'UNCERTAIN_EXISTING_MASK', 'MANUAL_HIDE', 'MANUAL_KEEP'}
    s.result_json = ""
    s.mode = 'GENERATE'
    s.existing_mask = ""
    s.spatial_step = 1.0
    s.angle = 90.0
    s.touch_tolerance = 0.00001
    s.scope = 'CURRENT_POSE_ONLY'
    bpy.context.scene.unit_settings.scale_length = 1.0
    bpy.context.scene.frame_set(1)


def material(name="Opaque", alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = alpha
    return mat


def mesh(name, vertices, polygons, mat=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], polygons)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    if mat:
        data.materials.append(mat)
    return obj


def cube(name, scale=1, polygons=POLYGONS, mat=None):
    return mesh(name, [(x * scale, y * scale, z * scale) for x, y, z in VERTICES],
                polygons, mat)


def setup(kind="closed", alpha=1):
    reset()
    body = cube("FixtureBody", .1)
    polys = POLYGONS if kind != "tube" else POLYGONS[2:]
    shell = cube("FixtureShell", 1, polys, material(alpha=alpha))
    bpy.context.scene.underwhere.body = body
    bpy.context.scene.underwhere.occluders.add().object = shell
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.context.view_layer.update()
    return body, shell, bpy.context.scene.underwhere


def mask(body, invert=True, weights=None, threshold=.5):
    group = body.vertex_groups.new(name="Existing")
    weights = weights if weights is not None else [1] * len(body.data.vertices)
    for i, weight in enumerate(weights):
        group.add([i], weight, 'REPLACE')
    mod = body.modifiers.new("ExistingMask", 'MASK')
    mod.vertex_group = group.name
    mod.invert_vertex_group = invert
    mod.threshold = threshold
    bpy.context.scene.underwhere.mode = 'AUDIT'
    bpy.context.scene.underwhere.existing_mask = mod.name
    bpy.context.view_layer.update()
    return mod


def slit(width):
    body, shell, s = setup()
    shell.data.clear_geometry()
    # The top is split into two slabs separated by an open strip.
    vertices = list(VERTICES)
    vertices += [(-width / 2, -1, 1), (-width / 2, 1, 1),
                 (width / 2, -1, 1), (width / 2, 1, 1)]
    polygons = [POLYGONS[0], *POLYGONS[2:], (4, 8, 9, 7), (10, 5, 6, 11)]
    shell.data.from_pydata(vertices, [], polygons)
    shell.data.update()
    bpy.context.view_layer.update()
    return body, shell, s
