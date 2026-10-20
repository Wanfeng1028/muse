import tempfile
import unittest
from pathlib import Path

from compile_scene_prompt import compile_artifacts
from validate_scene_spec import validate


def make_spec(**overrides):
    value = {
        "schema_version": "scene-art-v1", "scene_id": "SCENE_TEST", "revision": 1,
        "status": "DIRECTION_LOCKED", "purpose": "concept_keyart",
        "source": {"kind": "brief", "refs": [], "assumptions": []},
        "thesis": {"statement": "A working archive protects fragile memory above a storm sea.", "primary_tension": "scholarly restraint versus violent weather"},
        "world_context": {"location": "cliffside archive", "era": "near future", "season": "monsoon", "day_phase": "dawn", "function": "rare-book conservation", "power_or_maintenance": "conservators maintain sealed storage", "recent_event": "a storm damaged the outer walkway", "offscreen_world": "cloud sea and distant service paths"},
        "spatial": {"dominant_grammar": "courtyard sequence", "secondary_grammar": "quiet modern conservation infrastructure", "boundary": "timber archive on a cliff shelf", "entrances": ["wet stone threshold"], "exits": ["service bridge"], "landmarks": ["deep eaves", "conservation hall"], "traversal": ["covered walkway"], "foreground": "wet threshold", "midground": "restoration tables", "background": "cloud sea", "scale_anchors": ["adult conservator", "door", "book cart"]},
        "design": {"materials": ["aged timber", "wet stone", "paper screens"], "aging_behavior": ["darkened grain", "rain sheen"], "cultural_logic": ["threshold cleaning ritual"], "motifs": ["restrained lattice"], "human_use": ["linen-wrapped books", "repair tools"], "iconic_object": "sealed archive drawer", "weather": "steady monsoon rain", "atmosphere": "cool mist"},
        "camera": {"intent": "make the archive function legible", "framing": "wide three-layer view", "height": "eye level", "lens_feel": "moderate wide angle", "target": "the lit conservation hall", "path": "static"},
        "lighting": {"sources": ["cool dawn sky", "warm conservation lamps"], "key_direction": "warm light from the hall", "contrast": "restrained warm-cool separation", "color_roles": ["cool blue exterior", "warm amber interior"], "depth_strategy": "mist and value falloff"},
        "references": [], "constraints": {"preserve": [], "exclude": ["readable text", "logos"], "unknowns": []},
        "generation": {"intent": "GENERATE", "model_family": "model-neutral", "input_mode": "text", "execution_settings": {}},
        "handoff": {"owner": "scene-design", "consumers": ["assets"], "write_paths": [], "frozen_facts": [], "advisory_paths": []},
        "prompt_status": "DRAFT", "visual_status": "UNVERIFIED", "evidence": [], "unresolved": []
    }
    value.update(overrides)
    return value


class SceneContractAcceptance(unittest.TestCase):
    def test_valid_generate_contract(self):
        self.assertEqual(validate(make_spec()), [])

    def test_edit_requires_reference(self):
        errors = validate(make_spec(generation={"intent": "EDIT", "model_family": "gpt-image", "input_mode": "image", "execution_settings": {}}))
        self.assertTrue(any("requires at least one reference" in x for x in errors))

    def test_approved_reference_requires_hash(self):
        reference = {"id": "IMG_1", "file": "ref.png", "role": "scene", "preserve": ["geometry"], "exclude": ["pose"], "status": "approved"}
        errors = validate(make_spec(references=[reference]))
        self.assertTrue(any("needs a SHA-256" in x for x in errors))

    def test_handoff_cannot_write_production(self):
        errors = validate(make_spec(handoff={"owner": "scene-design", "consumers": ["assets"], "write_paths": ["/production.json"], "frozen_facts": [], "advisory_paths": []}))
        self.assertTrue(any("write_paths" in x for x in errors))

    def test_compile_exports_standalone_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = compile_artifacts(make_spec(), Path(directory))
            self.assertEqual(result["visual_status"], "UNVERIFIED")
            self.assertTrue((Path(directory) / "SCENE_TEST.image.txt").is_file())
            text = (Path(directory) / "SCENE_TEST.image.txt").read_text(encoding="utf-8")
            self.assertIn("cliffside archive", text)
            self.assertIn("Exclude:", text)


if __name__ == "__main__":
    unittest.main()
