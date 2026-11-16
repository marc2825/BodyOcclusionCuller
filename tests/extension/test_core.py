"""Pure contract tests (no Blender required)."""
import itertools
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addon"))
from underwhere.core.contracts import (
    KEEP, REVIEW, CANDIDATE, UNSAFE, UNCERTAIN, aggregate,
    conservative_vertices, hidden_faces, finding, mask_removed_vertices, output_plan,
)
from underwhere.core.reports import shared_report


class Contracts(unittest.TestCase):
    def test_empty_is_review(self):
        self.assertEqual(aggregate([]), REVIEW)

    def test_unknown_is_review(self):
        self.assertEqual(aggregate([CANDIDATE, "NEW_UNSUPPORTED"]), REVIEW)

    def test_all_required_states(self):
        self.assertEqual(aggregate([CANDIDATE] * 3), CANDIDATE)
        self.assertEqual(aggregate([CANDIDATE, REVIEW]), REVIEW)
        self.assertEqual(aggregate([REVIEW, KEEP]), KEEP)

    def test_findings_separate(self):
        self.assertEqual(finding(KEEP, True), UNSAFE)
        self.assertEqual(finding(REVIEW, True), UNCERTAIN)
        self.assertEqual(finding(KEEP, False), "")

    def test_mask_threshold_and_inversion(self):
        self.assertEqual(mask_removed_vertices([0, .5, .75, 1], .5, True), {2, 3})
        self.assertEqual(mask_removed_vertices([0, .5, .75, 1], .5, False), {0, 1})

    def test_partial_vertex_removal_deletes_face(self):
        self.assertEqual(hidden_faces([[0, 1, 2], [2, 3, 4]], {0}), {0})

    def test_adapter_never_removes_unrequested_face(self):
        polygons = [[0, 1, 2], [2, 1, 3], [3, 1, 4], [4, 1, 5], [6, 7, 8]]
        for bits in itertools.product([False, True], repeat=len(polygons)):
            requested = {i for i, chosen in enumerate(bits) if chosen}
            removed = conservative_vertices(polygons, requested)
            self.assertLessEqual(hidden_faces(polygons, removed), requested)

    def test_low_poly_candidate_can_disappear(self):
        # Interior triangle has no vertex exclusive to the candidate.
        polygons = [[0, 1, 2], [0, 3, 1], [1, 4, 2], [2, 5, 0]]
        self.assertFalse(conservative_vertices(polygons, {0}))

    def test_loose_vertices_are_not_selected(self):
        self.assertEqual(conservative_vertices([[0, 1, 2]], {0}), {0, 1, 2})

    def test_repair_intersects_existing_mask(self):
        report = {"faces": [
            {"face": 0, "verdict": CANDIDATE, "area": 1, "triangles": 1},
            {"face": 1, "verdict": KEEP, "area": 2, "triangles": 1}],
            "input": {"mode": "AUDIT"}, "existing_mask": {"hidden_faces": [1]},
            "source_polygons": [[0, 1, 2], [3, 4, 5]]}
        self.assertEqual(output_plan(report)["hidden_faces"], [])
        self.assertEqual(output_plan(report)["restored_existing_faces"], [1])
        report["overrides"] = {"1": "HIDE"}
        self.assertEqual(output_plan(report)["manual_risk_faces"], [1])
        self.assertEqual(output_plan(report)["hidden_faces"], [1])

    def test_repair_policy_keeps_or_restores_undecided_hides(self):
        from underwhere.core.contracts import RESTORE_EXPOSED, existing_mask_warning
        report = {"faces": [
            {"face": 0, "verdict": CANDIDATE, "area": 1, "triangles": 1},
            {"face": 1, "verdict": KEEP, "area": 1, "triangles": 1},
            {"face": 2, "verdict": REVIEW, "area": 1, "triangles": 1}],
            "input": {"mode": "AUDIT"}, "existing_mask": {"hidden_faces": [0, 1, 2]},
            "source_polygons": [[0, 1, 2], [3, 4, 5], [6, 7, 8]]}
        strict = output_plan(report)
        self.assertEqual(strict["hidden_faces"], [0])
        self.assertEqual(strict["retained_uncertain_faces"], [])
        report["repair_policy"] = RESTORE_EXPOSED
        kept = output_plan(report)
        # Exposed face 1 is always restored; undecided face 2 keeps the author's hide.
        self.assertEqual(kept["hidden_faces"], [0, 2])
        self.assertEqual(kept["retained_uncertain_faces"], [2])
        self.assertEqual(kept["restored_existing_faces"], [1])
        report["repair_policy"] = "SOMETHING_ELSE"
        self.assertEqual(output_plan(report)["hidden_faces"], [0])  # unknown -> strict
        report["input"]["mode"] = "GENERATE"
        report["repair_policy"] = RESTORE_EXPOSED
        self.assertIsNone(output_plan(report)["repair_policy"])
        self.assertEqual(output_plan(report)["hidden_faces"], [0])

    def test_existing_mask_warnings(self):
        from underwhere.core.contracts import existing_mask_warning
        self.assertIsNone(existing_mask_warning("GENERATE", {"hidden_faces": []}, 4))
        self.assertEqual(existing_mask_warning("AUDIT", {"hidden_faces": [1], "enabled": False}, 4),
                         "EXISTING_MASK_DISABLED")
        self.assertEqual(existing_mask_warning("AUDIT", {"hidden_faces": []}, 4),
                         "EXISTING_MASK_HIDES_NOTHING")
        self.assertEqual(existing_mask_warning("AUDIT", {"hidden_faces": [0, 1, 2, 3]}, 4),
                         "EXISTING_MASK_HIDES_EVERYTHING")
        self.assertIsNone(existing_mask_warning("AUDIT", {"hidden_faces": [0]}, 4))

    def test_vendor_covers_byte_identical(self):
        # Pinned so the sampling code cannot change without a deliberate update.
        expected = {
            "surface_cover.py": "13ae6a0d0d820333a8b6786a4421a404c9215bcb31b974cc9a09bcb7e70442f1",
            "angular_cover.py": "cbf8791983fecab3f3c203bf68c52f9d200680082da5e67b5b53e0c9745f7c9b",
        }
        for name, checksum in expected.items():
            self.assertEqual(hashlib.sha256((ROOT / "addon/underwhere/vendor" / name).read_bytes()).hexdigest(),
                             checksum)

    def test_shared_report_does_not_redistribute_source_or_names(self):
        import json
        report = {
            'schema_version': '1.1.0', 'extension_version': '0.2.0', 'method': 'FINITE',
            'environment': {'blender': '5.2.3', 'platform': 'PRIVATE_PATH'},
            'input': {'body': 'PRIVATE_AVATAR', 'settings': {'scope': 'EXPLICIT_FRAMES'}},
            'faces': [{'reason_codes': ['EXPOSURE_WITNESS'], 'witness': {'point': [12345, 67890, 99999]}}],
            'source_polygons': [[12345, 67890, 99999]], 'preview_vertices': [[12345, 67890, 99999]],
            'fingerprint': 'PRIVATE_HASH', 'counts': {}, 'findings': {},
            'output_plan': {'hidden_polygon_count': 0, 'hidden_triangle_count': 0},
            'assumptions': {'opaque_materials': ['PRIVATE_MATERIAL'], 'dependent_candidate_faces': 0},
            'occluder_issues': [{'object': 'PRIVATE_CLOTHING', 'reason_codes': ['NONMANIFOLD_OCCLUDER']}],
            'timings_seconds': {}, 'limitations': [], 'warnings': [],
        }
        payload = json.dumps(shared_report(report))
        self.assertNotIn('PRIVATE', payload)
        for value in ('12345', '67890', '99999', 'witness', 'source_polygons', 'preview_vertices', 'fingerprint'):
            self.assertNotIn(value, payload)
        self.assertIn('NONMANIFOLD_OCCLUDER', payload)


if __name__ == "__main__":
    unittest.main()
