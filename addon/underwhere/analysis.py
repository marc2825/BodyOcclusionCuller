"""Incremental finite-sample analysis on immutable geometry snapshots."""
from collections import Counter
import math
import time
import uuid

from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import VERSION
from .core.contracts import CANDIDATE, KEEP, REVIEW, METHOD, aggregate, finding, output_plan
from .vendor.angular_cover import hemisphere_cover, oriented_directions
from .vendor.surface_cover import cover_triangle, triangle_area, geometric_normal

LIMITATIONS = [
    "Finite samples only; narrow slits and sub-resolution exposure may be missed.",
    "Only explicitly sampled frames; intermediate/future poses and outfit changes are untested.",
    "Geometric straight rays only; shadows, AO, reflections, outlines and physics are untested.",
    "No continuous visibility guarantee; penetration is not analysed separately.",
    "Blockers require direct constant opaque Principled or an explicit recorded user assumption.",
    "Vertex Mask may retain candidate faces at shared boundaries.",
    "Destructively deleted source faces cannot be recovered.",
]


def opening_targets(objects, limit=64):
    """Additional counterexample rays, never an occlusion certificate.

    Each boundary component contributes its vertex mean. This also catches tiny
    centered slits missed by the coarse hemisphere grid. Complex/open geometry
    beyond the bounded component budget prevents automatic candidates.
    """
    targets = []
    issues = []
    for obj in objects:
        opening_geometry = obj.get("opening_geometry", obj)
        object_targets = []
        object_reasons = []
        edges = Counter()
        for polygon in opening_geometry["polygons"]:
            for a, b in zip(polygon, polygon[1:] + polygon[:1]):
                edges[tuple(sorted((a, b)))] += 1
        if any(count > 2 for count in edges.values()):
            object_reasons.append("NONMANIFOLD_OCCLUDER")
        adjacency = {}
        for (a, b), count in edges.items():
            if count == 1:
                adjacency.setdefault(a, set()).add(b)
                adjacency.setdefault(b, set()).add(a)
        unseen = set(adjacency)
        while unseen:
            stack = [min(unseen)]
            component = set()
            while stack:
                vertex = stack.pop()
                if vertex in component:
                    continue
                component.add(vertex)
                unseen.discard(vertex)
                stack.extend(adjacency[vertex] - component)
            if len(object_targets) >= limit:
                if "OPENING_BUDGET_EXCEEDED" not in object_reasons:
                    object_reasons.append("OPENING_BUDGET_EXCEEDED")
                continue
            object_targets.append(sum((Vector(opening_geometry["vertices"][i]) for i in sorted(component)),
                               Vector()) / len(component))
        if adjacency and obj.get("opening_geometry_policy") == "PRE_SOLIDIFY_EVALUATED":
            # A ray aimed at the source opening can hit the inner rimmed layer
            # first. For a narrow thick aperture this does not prove occlusion.
            # Preserve actual exposure witnesses; otherwise refuse this blocker.
            object_reasons.append("SOLIDIFY_OPENING_UNRESOLVED")
        targets.extend(object_targets)
        if object_reasons:
            issues.append({"object": obj["name"], "reason_codes": object_reasons})
    return targets, issues


def analyze_steps(state, fingerprint):
    started = time.perf_counter()
    body = state["body"]
    settings = state["settings"]
    tolerance = settings["touch_tolerance"]
    yield {"stage": "Build occluder BVH", "progress": 0.0}
    vertices, triangles, metadata = [], [], []
    openings, topology_issues = opening_targets(state["occluders"])
    ambiguous_objects = {issue["object"] for issue in topology_issues}
    ambiguity_reasons = {issue["object"]: issue["reason_codes"] for issue in topology_issues}
    for obj in state["occluders"]:
        offset = len(vertices)
        vertices.extend(obj["vertices"])
        for face, indices in obj["triangles"]:
            triangles.append([offset + i for i in indices])
            slot = obj["material_indices"][face]
            mat = obj["materials"][slot] if 0 <= slot < len(obj["materials"]) else {
                "name": None, "verdict": "MISSING_MATERIAL"}
            metadata.append({"object": obj["name"], "face": face, "slot": slot,
                             "material": mat["name"], "material_verdict": mat["verdict"]})
    blocker = BVHTree.FromPolygons(vertices, triangles, all_triangles=True)
    body_tree = BVHTree.FromPolygons(body["vertices"], [t[1] for t in body["triangles"]],
                                     all_triangles=True)
    # Overlap is only used as a conservative refusal, never a hide certificate.
    intersections = {body["triangles"][a][0] for a, _ in body_tree.overlap(blocker)}
    built = time.perf_counter()
    cover = hemisphere_cover(math.radians(settings["epsilon_degrees"]), max_level=4)
    if cover.realized_max_edge > math.radians(settings["epsilon_degrees"]) + 1e-12:
        raise ValueError("ANGULAR_COVER_INCOMPLETE")
    by_face = [[] for _ in body["polygons"]]
    for face, tri in body["triangles"]:
        by_face[face].append(tri)
    faces = []
    rays = 0
    maximum_radius = 0.0
    maximum_edge = 0.0
    existing = set(state["existing_mask"]["hidden_faces"])
    for face_index, face_triangles in enumerate(by_face):
        labels, reasons = [], set()
        witness = None
        face_rays = 0
        assumed_materials = set()
        face_radius, face_edge = 0.0, 0.0
        area = sum(triangle_area(*(body["vertices"][i] for i in tri)) for tri in face_triangles)
        if face_index in intersections:
            labels.append(REVIEW)
            reasons.add("SURFACE_INTERSECTION")
        else:
            for tri in face_triangles:
                points = [body["vertices"][i] for i in tri]
                spatial = cover_triangle(*points, settings["r"], max_depth=4)
                face_radius = max(face_radius, spatial.realized_max_probe_radius)
                face_edge = max(face_edge, spatial.realized_max_leaf_edge)
                normal = geometric_normal(*points)
                if not spatial.usable or normal is None:
                    labels.append(REVIEW)
                    reasons.add("SPATIAL_COVER_INCOMPLETE_OR_DEGENERATE")
                    continue
                directions = oriented_directions(cover, normal)
                # Both hemispheres also inspect thin/open or reversed body surfaces.
                directions += [tuple(-x for x in d) for d in directions if sum(
                    a * b for a, b in zip(d, normal)) > 1e-10]
                triangle_labels = []
                for probe in spatial.probes:
                    origin = Vector(probe.position)
                    _, _, near_index, distance = blocker.find_nearest(origin)
                    if near_index is not None and distance <= tolerance:
                        triangle_labels.append(REVIEW)
                        reasons.add("CONTACT_OR_DEPTH_TIE")
                        continue
                    probe_labels = []
                    opening_directions = [(p - origin).normalized() for p in openings
                                          if (p - origin).length > tolerance]
                    for direction in opening_directions + directions:
                        hit, _, index, distance = blocker.ray_cast(origin, Vector(direction))
                        rays += 1
                        face_rays += 1
                        if index is None:
                            probe_labels.append(KEEP)
                            reasons.add("EXPOSURE_WITNESS")
                            witness = {"point": list(probe.position), "direction": list(direction),
                                       "triangle": tri, "frame": state["frame"],
                                       "subframe": state["subframe"],
                                       "material_verdict": "NO_BLOCKER_HIT"}
                            break
                        meta = metadata[index]
                        if distance <= tolerance:
                            probe_labels.append(REVIEW)
                            reasons.add("CONTACT_OR_DEPTH_TIE")
                        elif meta["object"] in ambiguous_objects or meta["material_verdict"] not in (
                                "CONSTANT_OPAQUE_PRINCIPLED", "USER_ASSUMED_OPAQUE"):
                            probe_labels.append(REVIEW)
                            reasons.add("OCCLUDER_TOPOLOGY_AMBIGUITY" if meta["object"] in ambiguous_objects
                                        else meta["material_verdict"])
                            reasons.update(ambiguity_reasons.get(meta["object"], []))
                            if witness is None:
                                witness = {"point": list(probe.position),
                                           "direction": list(direction), "triangle": tri,
                                           "frame": state["frame"], "subframe": state["subframe"],
                                           **meta}
                        else:
                            probe_labels.append(CANDIDATE)
                            if meta["material_verdict"] == "USER_ASSUMED_OPAQUE":
                                assumed_materials.add(meta["material"])
                        if rays % 256 == 0:
                            yield {"stage": f"Sample face {face_index + 1}/{len(by_face)}",
                                   "progress": face_index / len(by_face)}
                    triangle_labels.append(aggregate(probe_labels))
                    if KEEP in triangle_labels:
                        break
                labels.append(aggregate(triangle_labels))
                if KEEP in labels:
                    break
        label = aggregate(labels)
        if label == CANDIDATE:
            reasons.add("ALL_REQUIRED_FINITE_SAMPLES_OCCLUDED")
        elif not reasons:
            reasons.add("NO_COMPLETE_EVIDENCE")
        maximum_radius = max(maximum_radius, face_radius)
        maximum_edge = max(maximum_edge, face_edge)
        faces.append({
            "face": face_index, "verdict": label,
            "finding": finding(label, face_index in existing),
            "reason_codes": sorted(reasons), "evidence_type": "FINITE_SAMPLED",
            "witness": witness, "area": area, "triangles": len(face_triangles),
            "rays": face_rays, "realized_probe_radius": face_radius,
            "realized_max_leaf_edge": face_edge,
            "user_assumed_materials": sorted(assumed_materials),
        })
        yield {"stage": f"Face {face_index + 1}/{len(by_face)}",
               "progress": (face_index + 1) / len(by_face)}
    finished = time.perf_counter()
    report = {
        "schema_version": "1.2.0", "extension_version": VERSION, "core_version": "3",
        "method": METHOD, "run_id": uuid.uuid4().hex,
        "environment": {"blender": state["blender"]},
        "input": {"body": body["name"], "mesh": body["mesh"],
                  "body_parts": body.get("parts", []),
                  "occluders": [o["name"] for o in state["occluders"]],
                  "mode": settings["mode"], "frame": state["frame"],
                  "subframe": state["subframe"], "settings": settings},
        "fingerprint": fingerprint, "evidence_type": "FINITE_SAMPLED",
        "existing_mask": state["existing_mask"],
        "faces": faces, "counts": dict(Counter(f["verdict"] for f in faces)),
        "findings": dict(Counter(f["finding"] for f in faces if f["finding"])),
        "areas": {label: sum(f["area"] for f in faces if f["verdict"] == label)
                  for label in (CANDIDATE, KEEP, REVIEW)},
        "resolution": {"angular_hemisphere_cover": cover.to_dict(),
                       "realized_max_probe_radius": maximum_radius,
                       "realized_max_leaf_edge": maximum_edge,
                       "requested_r": settings["r"], "rays": rays},
        "materials": [{"object": o["name"],
                       "slots": [{"name": m["name"], "verdict": m["verdict"],
                                  "automatic_verdict": m.get("automatic_verdict", m["verdict"]),
                                  "assumption_blocked": m.get("assumption_blocked", False),
                                  "user_assumed_opaque": m.get("user_assumed_opaque", False)}
                                 for m in o["materials"]]} for o in state["occluders"]],
        "source_polygons": body["polygons"], "preview_vertices": body["vertices"],
        "overrides": {}, "outputs": [], "limitations": LIMITATIONS,
        "warnings": ["SAMPLED_STATES_ONLY", "NOT_A_CONTINUOUS_OCCLUSION_CERTIFICATE"],
        "occluder_issues": topology_issues,
        "timings_seconds": {"bvh_and_overlap": built - started,
                            "sampling": finished - built, "analysis": finished - started},
    }
    report["resolution"]["opening_component_probes"] = len(openings)
    report["resolution"]["opening_geometry"] = [
        {"object": obj["name"], "policy": obj.get("opening_geometry_policy", "EVALUATED")}
        for obj in state["occluders"]]
    report["resolution"]["opening_budget_or_nonmanifold_ambiguity"] = bool(topology_issues)
    report["assumptions"] = {
        "opaque_materials": sorted({m["name"] for o in state["occluders"] for m in o["materials"]
                                    if m["verdict"] == "USER_ASSUMED_OPAQUE"}),
        "dependent_candidate_faces": sum(f["verdict"] == CANDIDATE and bool(f["user_assumed_materials"])
                                         for f in faces),
    }
    body_min = min(v[0] for v in body["vertices"])
    body_max = max(v[0] for v in body["vertices"])
    report["preview_offset_x"] = max(body_max, max(v[0] for v in vertices)) - body_min + max(
        (body_max - body_min) * .25, .01)
    report["output_plan"] = output_plan(report)
    return report
