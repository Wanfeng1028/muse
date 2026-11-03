import unittest
from pathlib import Path

from build_examples import create_mecha
from build_v3_examples import create_serial
from asset_plan import resolve_card
from compile_assets import asset_display_name
from director_dispatch import integration_registry, plan_dispatch, registry, select_integrations


ROOT = Path(__file__).resolve().parents[1]


class RedMonkeyIntegrationContract(unittest.TestCase):
    def test_catalog_has_required_records_and_no_production_writes(self):
        records = integration_registry(ROOT)
        required = {
            "h3-prompt-writing", "im2-clean-image", "cinematic-vfx-prompt-engine",
            "colossal-scale-visual-director", "camera-moves-whitebox", "prompt-library",
            "red-monkey-reasoning-kit", "lobster-asset-manager", "lobster-security-baseline",
            "lobster-self-reflection", "lobster-hot-memory-system", "skill-audit", "skill-foundry",
            "lobster-anti-omission-gate"
        }
        self.assertTrue(required <= set(records))
        self.assertTrue(all(record["write_paths"] == [] for record in records.values()))
        self.assertEqual(records["red-monkey-reasoning-kit"]["owner"], "director")

    def test_stage_dispatch_adds_only_compatible_internalized_steps(self):
        selected = ["shots", "assets", "effects", "model"]
        steps = select_integrations({"stage": "full", "features": ["colossal", "external_upload"]}, selected, create_mecha(), ROOT)
        ids = {step["id"] for step in steps}
        self.assertTrue({"camera-moves-whitebox", "im2-clean-image", "cinematic-vfx-prompt-engine", "h3-prompt-writing"} <= ids)
        self.assertTrue({"colossal-scale-visual-director", "lobster-security-baseline", "lobster-self-reflection"} <= ids)
        self.assertIn("lobster-anti-omission-gate", ids)
        self.assertFalse({"lobster-ai-video-workflow", "cinematic-director-engine", "lobster-task-layer-executor"} & ids)

    def test_explicit_analysis_routes_are_advisory_and_do_not_write(self):
        steps = select_integrations({"stage": "audit", "features": ["prompt-audit", "reasoning-review"]}, ["continuity"], {}, ROOT)
        by_id = {step["id"]: step for step in steps}
        self.assertEqual(by_id["prompt-library"]["owner"], "director")
        self.assertEqual(by_id["red-monkey-reasoning-kit"]["owner"], "director")
        self.assertEqual(by_id["prompt-library"]["write_paths"], [])
        self.assertEqual(by_id["red-monkey-reasoning-kit"]["write_paths"], [])

    def test_plan_exposes_integration_receipts_without_changing_module_owners(self):
        production = create_mecha()
        request = {"request_id": "REQ_INTEGRATION", "stage": "h3-compile", "features": ["external_upload"]}
        plan = plan_dispatch(production, request, ROOT, Path("C:/Users/dcf/.codex/skills"))
        self.assertEqual(plan["status"], "READY")
        self.assertEqual(plan["integration_contract_version"], "1.0")
        self.assertEqual([step["id"] for step in plan["integration_steps"]], ["lobster-anti-omission-gate", "h3-prompt-writing", "lobster-security-baseline"])
        self.assertTrue(all(step["write_paths"] == [] for step in plan["integration_steps"]))
        self.assertEqual(len(registry(ROOT)), 7)

    def test_anti_omission_gate_is_non_writing_and_not_the_legacy_scheduler(self):
        record = integration_registry(ROOT)["lobster-anti-omission-gate"]
        self.assertEqual(record["status"], "guardrail")
        self.assertEqual(record["owner"], "director")
        self.assertEqual(record["write_paths"], [])
        self.assertIn("references/94-delivery-integrity.md", record["required_reads"])
        self.assertNotIn("L1", " ".join(record["output"]))

    def test_character_identity_assets_default_to_four_views_and_labeled_state(self):
        production = create_serial()
        raw = next(card for card in production["asset_cards"] if card["id"] == "ART_MEI")
        card, missing = resolve_card(raw, production, ROOT / "examples", True)
        self.assertEqual(missing, [])
        self.assertEqual(card["asset_kind"], "character")
        self.assertEqual(card["character_name"], "Meilin")
        self.assertEqual(card["state_label"], "neutral_identity")
        self.assertEqual(card["view_layout"]["views"], ["front_full_body", "back_full_body", "side_profile_full_body", "front_face_close_up"])
        self.assertIn("four-view character turnaround", card["prompt"].lower())
        self.assertIn("Meilin", asset_display_name(card))
        self.assertIn("neutral_identity", asset_display_name(card))


if __name__ == "__main__":
    unittest.main()
