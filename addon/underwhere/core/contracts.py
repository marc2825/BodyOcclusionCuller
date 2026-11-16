"""Pure face evidence and conservative vertex-mask contracts."""
KEEP = "KEEP_EXPOSED"
REVIEW = "REVIEW"
CANDIDATE = "HIDE_CANDIDATE"
UNSAFE = "UNSAFE_EXISTING_MASK"
UNCERTAIN = "UNCERTAIN_EXISTING_MASK"
METHOD = "UNDERWHERE_FINITE_SAMPLED_V1"

# Audit repair policies. Both restore every face with an exposure witness.
#   RESTORE_UNRESOLVED (default): also restore faces that could not be decided,
#     so only confirmed candidates stay hidden.
#   RESTORE_EXPOSED: keep the author's existing hides wherever exposure was not
#     observed; undecided faces stay hidden and are reported, never claimed safe.
RESTORE_UNRESOLVED = "RESTORE_EXPOSED_AND_UNRESOLVED"
RESTORE_EXPOSED = "RESTORE_EXPOSED_ONLY"
REPAIR_POLICIES = (RESTORE_UNRESOLVED, RESTORE_EXPOSED)


def aggregate(labels):
    labels = list(labels)
    if KEEP in labels:
        return KEEP
    if labels and all(label == CANDIDATE for label in labels):
        return CANDIDATE
    return REVIEW


def conservative_vertices(polygons, candidates):
    """A removed vertex removes every incident face, not only all-hidden faces."""
    incident = {}
    for face, vertices in enumerate(polygons):
        for vertex in vertices:
            incident.setdefault(vertex, set()).add(face)
    return {vertex for vertex, faces in incident.items() if faces <= candidates}


def hidden_faces(polygons, removed_vertices):
    return {i for i, poly in enumerate(polygons) if any(v in removed_vertices for v in poly)}


def mask_removed_vertices(weights, threshold, invert):
    # Blender Mask keeps weights > threshold, with a Boolean inversion afterward.
    return {i for i, weight in enumerate(weights) if (weight > threshold) == invert}


def finding(label, is_hidden):
    if is_hidden and label == KEEP:
        return UNSAFE
    if is_hidden and label == REVIEW:
        return UNCERTAIN
    return ""


def existing_mask_warning(mode, existing, face_count):
    """Audit inputs that are valid but almost certainly not what the user meant."""
    if mode != "AUDIT":
        return None
    if not existing.get("enabled", True):
        return "EXISTING_MASK_DISABLED"
    hidden = len(existing["hidden_faces"])
    if hidden == 0:
        return "EXISTING_MASK_HIDES_NOTHING"
    if hidden == face_count:
        return "EXISTING_MASK_HIDES_EVERYTHING"
    return None


def output_plan(report):
    faces = report["faces"]
    verdict = {f["face"]: f["verdict"] for f in faces}
    candidates = {face for face, label in verdict.items() if label == CANDIDATE}
    audit = report["input"]["mode"] == "AUDIT"
    # Unknown values fall back to the stricter policy.
    policy = report.get("repair_policy", RESTORE_UNRESOLVED)
    if policy not in REPAIR_POLICIES:
        policy = RESTORE_UNRESOLVED
    if audit:
        existing_hidden = set(report["existing_mask"]["hidden_faces"])
        if policy == RESTORE_EXPOSED:
            candidates = {face for face in existing_hidden if verdict[face] != KEEP}
        else:
            candidates &= existing_hidden
    overrides = report.get("overrides", {})
    for index, value in overrides.items():
        if value == "HIDE":
            candidates.add(int(index))
        elif value == "KEEP":
            candidates.discard(int(index))
    polygons = report["source_polygons"]
    vertices = conservative_vertices(polygons, candidates)
    hidden = hidden_faces(polygons, vertices)
    existing = set(report["existing_mask"]["hidden_faces"])
    return {
        "requested_faces": sorted(candidates),
        "removed_vertices": sorted(vertices),
        "hidden_faces": sorted(hidden),
        "hidden_polygon_count": len(hidden),
        "hidden_triangle_count": sum(f["triangles"] for f in faces if f["face"] in hidden),
        "candidate_area": sum(f["area"] for f in faces if f["verdict"] == CANDIDATE),
        "output_hidden_area": sum(f["area"] for f in faces if f["face"] in hidden),
        "unrealized_requested_area": sum(
            f["area"] for f in faces if f["face"] in candidates - hidden),
        "restored_existing_faces": sorted(existing - hidden),
        "newly_hidden_faces": sorted(hidden - existing),
        "manual_risk_faces": sorted(
            int(i) for i, value in overrides.items()
            if value == "HIDE" and faces[int(i)]["verdict"] != CANDIDATE),
        "repair_policy": policy if audit else None,
        # Undecided faces left hidden by RESTORE_EXPOSED (manual Hide is counted
        # separately above).
        "retained_uncertain_faces": sorted(
            face for face in hidden
            if verdict[face] == REVIEW and overrides.get(str(face)) != "HIDE"),
        "kept_at_shared_vertices": sorted(candidates - hidden),
    }
