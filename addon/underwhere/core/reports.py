"""Allowlisted diagnostics suitable for public issues; never include source geometry."""
from collections import Counter


def shared_report(report):
    return {
        "schema_version": report["schema_version"], "report_kind": "SHAREABLE_SUMMARY",
        "extension_version": report["extension_version"], "method": report["method"],
        "environment": {"blender": report["environment"]["blender"]},
        "scope": report["input"]["settings"].get("scope", "CURRENT_POSE_ONLY"),
        "sampled_state_count": len(report.get("sampled_states", [None])),
        "sampled_states": [{"frame": state["frame"], "subframe": state["subframe"]}
                           for state in report.get("sampled_states", [])],
        "current_pose_always_included": report["input"]["settings"].get("current_pose_always_included", False),
        "counts": report["counts"], "findings": report["findings"],
        "reason_counts": dict(Counter(code for f in report["faces"] for code in f["reason_codes"])),
        "output": {key: report["output_plan"][key] for key in
                   ("hidden_polygon_count", "hidden_triangle_count")},
        "repair_policy": report["output_plan"].get("repair_policy"),
        "retained_uncertain_count": len(report["output_plan"].get("retained_uncertain_faces", [])),
        "existing_mask_hidden_count": len(report.get("existing_mask", {}).get("hidden_faces", [])),
        "user_assumed_opaque_material_count": len(report.get("assumptions", {}).get("opaque_materials", [])),
        "assumption_dependent_candidate_count": report.get("assumptions", {}).get("dependent_candidate_faces", 0),
        "occluder_issue_counts": dict(Counter(code for issue in report.get("occluder_issues", [])
                                             for code in issue["reason_codes"])),
        "timings_seconds": report["timings_seconds"], "limitations": report["limitations"],
        "warnings": report["warnings"],
    }
