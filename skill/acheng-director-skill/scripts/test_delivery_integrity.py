"""Acceptance tests for the non-invasive delivery integrity gate."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from build_examples import create_mecha
from delivery_integrity import check_delivery_integrity, check_production


class DeliveryIntegrityAcceptance(unittest.TestCase):
    def test_h3_gate_passes_without_mutating_production(self):
        payload = create_mecha()
        before = copy.deepcopy(payload)
        receipt = check_delivery_integrity(payload, "h3-compile", Path(__file__).parents[1] / "examples")
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(payload, before)
        self.assertIn("segments:1", receipt["evidence"])

    def test_full_stage_rejects_prompt_only_overclaim(self):
        payload = create_mecha()
        receipt = check_delivery_integrity(payload, "full")
        self.assertEqual(receipt["status"], "EXECUTION_BLOCKED")
        self.assertIn("full stage requires delivery_scope=full_production", receipt["blocked"])

    def test_model_facing_omission_shorthand_is_blocked(self):
        payload = create_mecha()
        payload["segments"][0]["summary"] = "Same as above; continue from the previous shot."
        receipt = check_delivery_integrity(payload, "h3-compile")
        self.assertEqual(receipt["status"], "EXECUTION_BLOCKED")
        self.assertTrue(any("omission shorthand" in item for item in receipt["blocked"]))

    def test_missing_reference_is_disclosed_and_ready_mode_blocks(self):
        payload = create_mecha()
        payload["asset_cards"] = [{"id": "ART_A", "prompt": "A clean prop.",
                                   "references": [{"file": "missing.png"}]}]
        receipt = check_delivery_integrity(payload, "assets", Path(__file__).parents[1] / "examples")
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(any("missing reference" in item for item in receipt["unresolved"]))
        ready = check_delivery_integrity(payload, "assets", Path(__file__).parents[1] / "examples", require_ready=True)
        self.assertEqual(ready["status"], "NEEDS_DIRECTOR_REVISION")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'production.json'
            source.write_text(json.dumps(payload), encoding='utf-8')
            self.assertEqual(check_production(source, 'assets')['status'], 'NEEDS_DIRECTOR_REVISION')
            source.write_text(json.dumps({}), encoding='utf-8')
            self.assertEqual(check_production(source, 'script')['status'], 'NEEDS_DIRECTOR_REVISION')


if __name__ == "__main__":
    unittest.main()
