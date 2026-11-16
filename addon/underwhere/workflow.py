"""Result lifecycle, live freshness checks and report export."""
import json
from pathlib import Path
import time
from collections import Counter, OrderedDict
from contextlib import contextmanager
import uuid

import bpy

from . import blender_adapter as adapter
from .analysis import analyze_steps
from .core.contracts import output_plan
from .core.contracts import aggregate, finding, CANDIDATE, KEEP, REVIEW
from .core.reports import shared_report

LIVE_RUNS = set()
BUSY = set()
DIRTY = set()
REPORT_CACHE = OrderedDict()
LIVE_GUARDS = {}
MODAL_OWNERS = {}
MAX_REPORT_REVISIONS = 64
REFERENCE_SCHEMA = "UNDERWHERE_SESSION_REPORT_REFERENCE_V1"


def scene_key(scene):
    return scene.as_pointer()


def read_report(settings):
    raw = settings.result_json
    if not raw:
        raise adapter.InputError("ANALYSIS_REQUIRED")
    if len(raw) > 256:
        raise adapter.InputError("STALE: legacy embedded report; Analyze again")
    try:
        reference = json.loads(raw)
        token = reference["token"] if reference["schema"] == REFERENCE_SCHEMA else None
    except (ValueError, KeyError, TypeError) as exc:
        raise adapter.InputError("STALE: invalid report reference; Analyze again") from exc
    if not isinstance(token, str) or token not in REPORT_CACHE:
        raise adapter.InputError("STALE: session report expired; Analyze again")
    REPORT_CACHE.move_to_end(token)
    return REPORT_CACHE[token]


def cache_report(token, report):
    REPORT_CACHE[token] = report
    REPORT_CACHE.move_to_end(token)
    while len(REPORT_CACHE) > MAX_REPORT_REVISIONS:
        REPORT_CACHE.popitem(last=False)
    runs = {value["run_id"] for value in REPORT_CACHE.values()}
    LIVE_RUNS.intersection_update(runs)
    for run_id in list(LIVE_GUARDS):
        if run_id not in runs:
            LIVE_GUARDS.pop(run_id)


def save_report(settings, report):
    # Undo stores only a tiny immutable revision reference. Geometry/evidence
    # stays in bounded session memory; revisions share those immutable arrays.
    stored = report.copy()
    stored["overrides"] = report.get("overrides", {}).copy()
    stored["outputs"] = list(report.get("outputs", []))
    stored["output_plan"] = output_plan(stored)
    token = uuid.uuid4().hex
    cache_report(token, stored)
    settings.result_json = json.dumps({"schema": REFERENCE_SCHEMA, "token": token}, separators=(",", ":"))
    settings.issues.clear()
    for face in report["faces"]:
        if face["finding"] or face["verdict"] == REVIEW:
            item = settings.issues.add()
            item.face = face["face"]
            item.label = face["finding"] or face["verdict"]


def discard_legacy_report(settings):
    if len(settings.result_json) > 256:
        settings.result_json = ""
        settings.issues.clear()
        settings.status = "STALE: legacy embedded report removed; Analyze again"


def guard(context, settings):
    return (context.scene.frame_current, context.scene.frame_subframe,
            adapter.digest(adapter.settings_record(settings, context.scene)),
            settings.body.as_pointer() if settings.body else 0,
            tuple(item.object.as_pointer() if item.object else 0 for item in settings.occluders),
            settings.existing_mask, adapter.visibility_signature(context, settings))


def fresh_report(context, settings, *, verify=True):
    report = read_report(settings)
    if report["run_id"] not in LIVE_RUNS:
        settings.status = "STALE: re-analyze after loading or enabling"
        raise adapter.InputError(settings.status)
    key = scene_key(context.scene)
    if not verify and key not in DIRTY and LIVE_GUARDS.get(report["run_id"]) == guard(context, settings):
        return report
    BUSY.add(key)
    try:
        with object_mode(context, settings):
            _, fingerprint = adapter.snapshot(context, settings)
            validate_states(context, settings, report)
    except Exception:
        settings.status = "STALE: input is no longer supported"
        raise
    finally:
        BUSY.discard(key)
    if fingerprint != report["fingerprint"]:
        settings.status = "STALE: inputs changed; Analyze again"
        raise adapter.InputError(settings.status)
    settings.status = "READY"
    DIRTY.discard(key)
    LIVE_GUARDS[report["run_id"]] = guard(context, settings)
    return report


@contextmanager
def object_mode(context, settings):
    if context.mode == 'EDIT_MESH' and context.edit_object and adapter.is_preview(context.edit_object):
        # Selecting on the comparison mesh is a view-only activity; leave it.
        bpy.ops.object.mode_set(mode='OBJECT')
    was_edit = context.mode == 'EDIT_MESH' and context.edit_object == settings.body
    if context.mode != 'OBJECT' and not was_edit:
        raise adapter.InputError("Edit the configured Body or use Object Mode")
    try:
        if was_edit:
            bpy.ops.object.mode_set(mode='OBJECT')
        yield
    finally:
        if was_edit and context.mode == 'OBJECT' and settings.body:
            bpy.ops.object.mode_set(mode='EDIT')


def selected_frames(settings):
    if settings.scope == 'CURRENT_POSE_ONLY':
        return []
    try:
        frames = sorted({int(value.strip()) for value in settings.frames.split(',')})
    except ValueError as exc:
        raise adapter.InputError("FRAMES_REQUIRED: comma-separated integer frames") from exc
    if not frames or len(frames) > 32 or min(frames) < -1048574 or max(frames) > 1048574:
        raise adapter.InputError("FRAME_LIMIT: choose 1–32 valid frames")
    return frames


def validate_states(context, settings, report):
    """Future sampled-frame animation edits may leave the current pose unchanged."""
    states = [state for state in report.get('sampled_states', []) if 'fingerprint' in state]
    if not states:
        return
    scene = context.scene
    original = scene.frame_current, scene.frame_subframe
    try:
        for state in states:
            scene.frame_set(state['frame'], subframe=state['subframe'])
            if adapter.snapshot(context, settings)[1] != state['fingerprint']:
                raise adapter.InputError('STALE: sampled frame changed; Analyze again')
    finally:
        scene.frame_set(original[0], subframe=original[1])


def required_states(settings, base):
    current = (base["frame"], base["subframe"])
    return [current] + [(frame, 0.0) for frame in selected_frames(settings) if (frame, 0.0) != current]


def state_caption(report):
    return ", ".join(f"{state['frame'] + state['subframe']:g}" for state in report["sampled_states"])


def analyze_states(context, settings, base, fingerprint, states):
    scene = context.scene
    original = scene.frame_current, scene.frame_subframe
    merged = None
    sampled = []
    for number, (frame, subframe) in enumerate(states):
        if number == 0:
            state, state_fingerprint = base, fingerprint
        else:
            try:
                scene.frame_set(frame, subframe=subframe)
                state, state_fingerprint = adapter.snapshot(context, settings)
            finally:
                scene.frame_set(original[0], subframe=original[1])
        if (state["body"]["polygons"] != base["body"]["polygons"] or
                state["existing_mask"]["hidden_faces"] != base["existing_mask"]["hidden_faces"]):
            raise adapter.InputError("STATE_TOPOLOGY_OR_MASK_CHANGED")
        iterator = analyze_steps(state, fingerprint)
        try:
            while True:
                try:
                    step = next(iterator)
                except StopIteration as done:
                    result = done.value
                    break
                yield {"stage": f"Frame {frame + subframe:g}: {step['stage']}",
                       "progress": (number + step['progress']) / len(states)}
        finally:
            iterator.close()
        for issue in result['occluder_issues']:
            issue['frame'] = frame
        sampled.append({"frame": frame, "subframe": subframe, "counts": result["counts"],
                        "is_current_pose": number == 0,
                        "fingerprint": state_fingerprint})
        if merged is None:
            merged = result
        else:
            for face, other in zip(merged["faces"], result["faces"]):
                label = aggregate([face["verdict"], other["verdict"]])
                if other["verdict"] == label and face["verdict"] != label:
                    face["witness"] = other["witness"]
                face["verdict"] = label
                face["finding"] = finding(label, face["face"] in base["existing_mask"]["hidden_faces"])
                face["reason_codes"] = sorted(set(face["reason_codes"] + other["reason_codes"]))
                face["user_assumed_materials"] = sorted(set(face["user_assumed_materials"] + other["user_assumed_materials"]))
                for field in ("realized_probe_radius", "realized_max_leaf_edge"):
                    face[field] = max(face[field], other[field])
                face["rays"] += other["rays"]
            for field in merged["timings_seconds"]:
                merged["timings_seconds"][field] += result["timings_seconds"][field]
            merged["occluder_issues"].extend(result["occluder_issues"])
            merged["assumptions"]["opaque_materials"] = sorted(set(
                merged["assumptions"]["opaque_materials"] + result["assumptions"]["opaque_materials"]))
    merged["sampled_states"] = sampled
    merged['area_reference_state'] = {'frame': base['frame'], 'subframe': base['subframe']}
    merged['input']['frame'] = base['frame']
    merged['input']['subframe'] = base['subframe']
    merged["counts"] = dict(Counter(f["verdict"] for f in merged["faces"]))
    merged["findings"] = dict(Counter(f["finding"] for f in merged["faces"] if f["finding"]))
    merged["areas"] = {label: sum(f["area"] for f in merged["faces"] if f["verdict"] == label)
                       for label in (CANDIDATE, KEEP, REVIEW)}
    merged["resolution"]["rays"] = sum(f["rays"] for f in merged["faces"])
    merged["resolution"]["realized_max_probe_radius"] = max(f["realized_probe_radius"] for f in merged["faces"])
    merged["resolution"]["realized_max_leaf_edge"] = max(f["realized_max_leaf_edge"] for f in merged["faces"])
    merged["assumptions"]["dependent_candidate_faces"] = sum(
        f["verdict"] == CANDIDATE and bool(f["user_assumed_materials"]) for f in merged["faces"])
    # Comparison stays at the original scene state, not the last sampled frame.
    merged["preview_vertices"] = base["body"]["vertices"]
    body_vertices = base['body']['vertices']
    low = min(v[0] for v in body_vertices)
    high = max(v[0] for v in body_vertices)
    merged['preview_offset_x'] = max(
        high, *(v[0] for obj in base['occluders'] for v in obj['vertices'])) - low + max((high - low) * .25, .01)
    return merged


def start(context, settings):
    key = scene_key(context.scene)
    if key in BUSY:
        raise adapter.InputError("ANALYSIS_ALREADY_RUNNING")
    BUSY.add(key)
    began = time.perf_counter()
    try:
        state, fingerprint = adapter.snapshot(context, settings)
        settings.progress = 0.0
        settings.status = "Analyzing"
        states = required_states(settings, state)  # Current frame/subframe is mandatory.
        return analyze_states(context, settings, state, fingerprint, states), time.perf_counter() - began
    except Exception:
        BUSY.discard(key)
        raise


def finish(context, settings, report, snapshot_seconds):
    # Fail closed if a user edits inputs while the modal job is running.
    _, current = adapter.snapshot(context, settings)
    if current != report["fingerprint"]:
        raise adapter.InputError("INPUT_CHANGED_DURING_ANALYSIS")
    validate_states(context, settings, report)
    report["timings_seconds"]["snapshot"] = snapshot_seconds
    report["environment"]["platform"] = __import__("platform").platform()
    report["output_plan"] = output_plan(report)
    began = time.perf_counter()
    report["output_verification"] = adapter.measure_plan(context, settings, report)
    report["timings_seconds"]["output_verification"] = time.perf_counter() - began
    LIVE_RUNS.add(report["run_id"])
    LIVE_GUARDS[report["run_id"]] = guard(context, settings)
    DIRTY.discard(scene_key(context.scene))
    save_report(settings, report)
    settings.status = "READY"
    settings.progress = 1.0
    adapter.clear_preview(context.scene)


def run_sync(context, settings):
    iterator, elapsed = start(context, settings)
    try:
        while True:
            try:
                step = next(iterator)
                settings.progress = step["progress"]
            except StopIteration as done:
                finish(context, settings, done.value, elapsed)
                return done.value
    finally:
        iterator.close()
        BUSY.discard(scene_key(context.scene))


def export_report(context, settings, path, *, private=False):
    report = fresh_report(context, settings)
    destination = Path(bpy.path.abspath(path)).resolve()
    if destination.suffix.lower() != ".json":
        raise adapter.InputError("Choose a .json report filename")
    package = Path(__file__).resolve().parent
    if destination.is_relative_to(package):
        raise adapter.InputError("Do not write reports inside the installed Extension")
    # File browser handles overwrite confirmation; serialize before opening.
    payload = json.dumps(report if private else shared_report(report), ensure_ascii=False, indent=2, allow_nan=False)
    destination.write_text(payload, encoding="utf-8")
    return destination
