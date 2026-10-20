"""Acceptance tests for the causal acting and motion-language contract."""
import copy
from pathlib import Path
import unittest

from audit_storyboard_quality import audit, compile_segment
from build_examples import create_drama
from performance_liveliness import check_liveliness


ROOT = Path(__file__).resolve().parents[1]


class LivelinessContract(unittest.TestCase):
    def test_valid_design_is_audited_and_compiled_into_h3(self):
        production = create_drama()
        self.assertEqual(check_liveliness(production)["status"], "PASS")
        self.assertEqual(audit(production, ROOT / "examples")["status"], "PASS")
        text = compile_segment(production, production["segments"][0])
        self.assertIn("Immediate objective", text)
        self.assertIn("Motion language: live_action", text)
        self.assertIn("characters 8 through 11 of spoken line 1", text)
        self.assertIn("<d>[Chinese] 上次是我没听。现在你来。</d>", text)

    def test_design_cannot_hide_the_social_logic(self):
        production = create_drama()
        production["shots"][0]["performance"]["acting_design"]["objective"] = ""
        with self.assertRaisesRegex(ValueError, "objective"):
            check_liveliness(production)

    def test_speech_anchors_must_be_exact_source_substrings(self):
        production = create_drama()
        production["shots"][0]["performance"]["acting_design"]["action_units"][1]["speech_anchor"] = "invented phrase"
        with self.assertRaisesRegex(ValueError, "exact dialogue"):
            check_liveliness(production)

    def test_motion_units_and_cut_times_stay_inside_the_shot(self):
        production = create_drama()
        design = production["shots"][0]["performance"]["acting_design"]
        design["action_units"][1]["end"] = 241
        with self.assertRaisesRegex(ValueError, "timing"):
            check_liveliness(production)
        production = create_drama()
        design = production["shots"][0]["performance"]["acting_design"]
        design["cut_behavior"] = [{"at": 240, "type": "hard_cut", "audio_carries": False, "action_carries": False,
                                    "entry_state": "the first shot ends in a held offer", "exit_state": "the next shot receives the held offer"}]
        self.assertEqual(check_liveliness(production)["status"], "PASS")

    def test_carried_audio_requires_a_real_cross_cut_utterance(self):
        production = create_drama()
        design = production["shots"][0]["performance"]["acting_design"]
        design["cut_behavior"] = [{"at": 240, "type": "hard_cut", "audio_carries": True, "action_carries": True,
                                    "entry_state": "the sentence is in progress", "exit_state": "the sentence continues over the next view"}]
        with self.assertRaisesRegex(ValueError, "cross-cut utterance"):
            check_liveliness(production)


if __name__ == "__main__":
    unittest.main()
