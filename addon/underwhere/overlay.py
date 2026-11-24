"""Verdict colours drawn on the Body itself, as a viewport overlay.

Nothing is added to the scene and the Body is never changed: the colours are
drawn by a 3D View draw handler from the analysed (world-space) surface. With
"Show through clothing" the coloured Body is rendered into its own offscreen
buffer, so it keeps its own depth order and stays visible under the clothing,
then laid over the view with the chosen opacity."""
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from . import blender_adapter as adapter
from .core.contracts import output_plan

#: Scene pointer -> {"positions", "colors", "faces", "batches"}.
OVERLAYS = {}
HANDLERS = []
OFFSCREEN = {}
#: For tests and diagnostics: draws made, and the last drawing error (if any).
STATS = {"draws": 0, "last_error": None}


def overlay_label(face, report, mode, before, after, show, hidden):
    """Label to paint on the Body for this face, or None to leave it unpainted."""
    if mode == 'ORIGINAL':
        return None  # The Body itself already is the unmasked view.
    if mode == 'OUTPUT':
        return "HIDE_CANDIDATE" if face["face"] in hidden else None
    label = adapter.face_label(face, report, mode, before, after)
    if mode == 'DIFF' and label == "DIFF_VISIBLE":
        return None
    if mode == 'CLASSIFY' and show is not None and label not in show:
        return None
    return label


def surface(report, mode, show):
    """Triangle positions and colours (one colour per vertex) for the overlay."""
    plan = output_plan(report)
    before = set(report["existing_mask"]["hidden_faces"])
    after = set(plan["hidden_faces"])
    vertices = report["preview_vertices"]
    polygons = report["source_polygons"]
    size = max(max(v[axis] for v in vertices) - min(v[axis] for v in vertices) for axis in range(3))
    normals = vertex_normals(vertices, polygons)
    # Lift the paint just off the surface so it does not flicker against it.
    lift = max(size * 0.0015, 1e-5)
    lifted = [(x + n[0] * lift, y + n[1] * lift, z + n[2] * lift)
              for (x, y, z), n in zip(vertices, normals)]
    positions, colors, faces = [], [], 0
    for face in report["faces"]:
        label = overlay_label(face, report, mode, before, after, show, after)
        if label is None:
            continue
        color = adapter.COLORS[label]
        polygon = polygons[face["face"]]
        for i in range(1, len(polygon) - 1):  # fan: avatars are triangles and quads
            for index in (polygon[0], polygon[i], polygon[i + 1]):
                positions.append(lifted[index])
                colors.append(color)
        faces += 1
    return positions, colors, faces


def vertex_normals(vertices, polygons):
    sums = [[0.0, 0.0, 0.0] for _ in vertices]
    for polygon in polygons:
        for i in range(1, len(polygon) - 1):
            a, b, c = (vertices[polygon[0]], vertices[polygon[i]], vertices[polygon[i + 1]])
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            for index in polygon:
                total = sums[index]
                total[0] += n[0]
                total[1] += n[1]
                total[2] += n[2]
    normals = []
    for x, y, z in sums:
        length = (x * x + y * y + z * z) ** 0.5
        normals.append((x / length, y / length, z / length) if length > 0 else (0.0, 0.0, 0.0))
    return normals


def show(scene, report, mode, show_filter):
    positions, colors, faces = surface(report, mode, show_filter)
    OVERLAYS[scene.as_pointer()] = {"positions": positions, "colors": colors, "faces": faces, "batches": {}}
    redraw()


def clear(scene):
    if OVERLAYS.pop(scene.as_pointer(), None) is not None:
        redraw()


def is_shown(scene):
    """Shown while the paint exists and the result it was made from is still there."""
    return scene.as_pointer() in OVERLAYS and bool(getattr(scene.underwhere, "result_json", ""))


def painted_faces(scene):
    entry = OVERLAYS.get(scene.as_pointer())
    return 0 if entry is None else entry["faces"]


def redraw():
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def opacity(context, settings):
    value = settings.overlay_opacity
    edit = context.edit_object
    if context.mode == 'EDIT_MESH' and edit is not None and edit in adapter.body_objects(settings):
        value *= 0.5  # Let Blender's selection highlight show through while choosing faces.
    return value


def batch(entry, key, alpha):
    """GPU batch for this entry, built on first use inside a draw (needs a GPU context)."""
    cached = entry["batches"].get(key)
    if cached is None:
        shader = gpu.shader.from_builtin('FLAT_COLOR')
        colors = [(r, g, b, alpha) for r, g, b, _ in entry["colors"]]
        cached = (shader, batch_for_shader(shader, 'TRIS', {"pos": entry["positions"], "color": colors}))
        entry["batches"] = {key: cached}  # one batch at a time; opacity changes are rare
    return cached


def active(context):
    scene = getattr(context, "scene", None)
    if scene is None or not hasattr(scene, "underwhere"):
        return None, None
    entry = OVERLAYS.get(scene.as_pointer())
    if entry is None or not entry["positions"] or not is_shown(scene):
        return None, None
    return entry, scene.underwhere


def draw_in_view():
    """Depth-tested paint: clothing in front hides it, like the real Body."""
    try:
        context = bpy.context
        entry, settings = active(context)
        if entry is None or settings.overlay_xray:
            return
        alpha = round(opacity(context, settings), 3)
        shader, tris = batch(entry, ("view", alpha), alpha)
        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.blend_set('ALPHA')
        shader.bind()
        tris.draw(shader)
        gpu.state.blend_set('NONE')
        gpu.state.depth_test_set('NONE')
        STATS["draws"] += 1
    except Exception as exc:  # Never break the viewport; keep the reason for diagnostics.
        STATS["last_error"] = f"{type(exc).__name__}: {exc}"


def draw_through():
    """Paint rendered with its own depth, then laid over the view: visible under clothing."""
    try:
        context = bpy.context
        entry, settings = active(context)
        region, view = context.region, context.region_data
        if entry is None or not settings.overlay_xray or view is None:
            return
        width, height = region.width, region.height
        buffer = OFFSCREEN.get("buffer")
        if buffer is None or buffer.width != width or buffer.height != height:
            if buffer is not None:
                buffer.free()
            buffer = gpu.types.GPUOffScreen(width, height)
            OFFSCREEN["buffer"] = buffer
        shader, tris = batch(entry, ("through", 1.0), 1.0)
        with buffer.bind():
            framebuffer = gpu.state.active_framebuffer_get()
            framebuffer.clear(color=(0.0, 0.0, 0.0, 0.0), depth=1.0)
            gpu.state.depth_test_set('LESS_EQUAL')
            gpu.state.depth_mask_set(True)
            with gpu.matrix.push_pop():
                gpu.matrix.load_matrix(view.view_matrix)
                with gpu.matrix.push_pop_projection():
                    gpu.matrix.load_projection_matrix(view.window_matrix)
                    shader.bind()
                    tris.draw(shader)
            gpu.state.depth_mask_set(False)
            gpu.state.depth_test_set('NONE')
        image = gpu.shader.from_builtin('IMAGE_COLOR')
        quad = batch_for_shader(image, 'TRI_FAN', {
            "pos": ((0, 0), (width, 0), (width, height), (0, height)),
            "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
        })
        gpu.state.blend_set('ALPHA')
        image.bind()
        image.uniform_sampler("image", buffer.texture_color)
        image.uniform_float("color", (1.0, 1.0, 1.0, opacity(context, settings)))
        quad.draw(image)
        gpu.state.blend_set('NONE')
        STATS["draws"] += 1
    except Exception as exc:
        STATS["last_error"] = f"{type(exc).__name__}: {exc}"


def register():
    HANDLERS.append(bpy.types.SpaceView3D.draw_handler_add(draw_in_view, (), 'WINDOW', 'POST_VIEW'))
    HANDLERS.append(bpy.types.SpaceView3D.draw_handler_add(draw_through, (), 'WINDOW', 'POST_PIXEL'))
    adapter.CLEAR_HOOKS.append(clear)


def unregister():
    for handler in HANDLERS:
        bpy.types.SpaceView3D.draw_handler_remove(handler, 'WINDOW')
    HANDLERS.clear()
    if clear in adapter.CLEAR_HOOKS:
        adapter.CLEAR_HOOKS.remove(clear)
    OVERLAYS.clear()
    buffer = OFFSCREEN.pop("buffer", None)
    if buffer is not None:
        try:
            buffer.free()
        except Exception:
            pass
