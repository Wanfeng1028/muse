import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from orchestrator_plan import plan
from post_hooks import check_assets
from style_anchor import style_policy_report


ROOT = Path(__file__).resolve().parents[1]


class StyleAnchorAcceptance(unittest.TestCase):
    def setUp(self):
        self.template = json.loads((ROOT / "templates/style-anchor-stage.json").read_text(encoding="utf-8"))

    def test_new_asset_run_without_policy_is_blocked(self):
        payload = copy.deepcopy(self.template)
        payload.pop("style_policy")
        report = style_policy_report(payload, ROOT / "templates", strict=True)
        self.assertEqual(report["status"], "BLOCKED")

    def test_planned_anchor_blocks_dependent_readiness(self):
        report = check_assets(self.template, ROOT / "templates")
        self.assertEqual(report["status"], "DRAFT")
        self.assertEqual(report["style_policy"]["status"], "STYLE_ANCHOR_PENDING_APPROVAL")

    def test_approved_anchor_requires_matching_file_hash(self):
        payload = copy.deepcopy(self.template)
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            image = base / "style.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\napproved-style-anchor")
            sha = hashlib.sha256(image.read_bytes()).hexdigest()
            payload["style_lock"].update({"status": "approved", "approved_file": "style.png", "approved_sha256": sha})
            payload["asset_plan"][0].update({"status": "approved", "file": "style.png", "sha256": sha})
            report = style_policy_report(payload, base, strict=True)
            self.assertEqual(report["status"], "READY")

    def test_dependent_asset_must_reference_anchor_as_final_slot(self):
        payload = copy.deepcopy(self.template)
        payload["style_lock"]["apply_to_kinds"] = ["character"]
        payload["asset_plan"].append({"id": "CHAR_A", "kind": "character", "version": "v1.0", "purpose": "identity", "depends_on": [], "status": "planned"})
        payload["asset_cards"].append({"id": "CHAR_A", "asset_version": "v1.0", "recipe": "portrait", "references": []})
        with self.assertRaisesRegex(ValueError, "style_lock anchor missing"):
            style_policy_report(payload, ROOT / "templates", strict=True)

    def test_orchestrator_places_style_anchor_before_assets(self):
        production = {"version": "2.0", "project_id": "demo", "shots": [], "segments": []}
        result = plan({"request_id": "REQ_STYLE", "intent": "assets"}, production)
        self.assertEqual([node["id"] for node in result["nodes"]], ["style-anchor", "assets", "continuity", "audit"])
        self.assertEqual(result["style_policy"], "required")


if __name__ == "__main__":
    unittest.main()
