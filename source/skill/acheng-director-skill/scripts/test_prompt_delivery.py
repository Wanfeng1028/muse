"""Acceptance contracts for standalone prompts and explicit uploaded references."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from audit_storyboard_quality import audit, compile_segment, read_data
from compile_assets import compile_assets
from compile_h3 import compile_package
from director_pipeline import archive, restore
from post_hooks import check_assets
from prompt_delivery import PromptDeliveryError, expand_prompt, render_asset_prompt, require_standalone

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class PromptDeliveryAcceptance(unittest.TestCase):
    def test_image_export_resolves_design_and_copies_declared_reference(self):
        p = read_data(EX / "01-mecha.production.json")
        with tempfile.TemporaryDirectory() as temporary:
            result = compile_assets(EX / "01-mecha.production.json", Path(temporary) / "images")
            out = Path(temporary) / "images"
            self.assertEqual(len(result), 1)
            prompt = (out / result[0]["prompt_file"]).read_text(encoding="utf-8")
            self.assertIn("Reference image 1", prompt)
            names = (out / "ASSET_NAMES.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(names, [result[0]["display_name"]])
            self.assertNotIn("提示词", (out / "ASSET_NAMES.txt").read_text(encoding="utf-8"))
            self.assertEqual((out / result[0]["references"][0]["file"]).read_bytes(), (EX / p["asset_cards"][0]["references"][0]["file"]).read_bytes())
            saved = archive(p, EX, Path(temporary) / "archive")
            recovered = restore(saved, Path(temporary) / "recovered")
            self.assertEqual(len(compile_assets(recovered, Path(temporary) / "recovered-images")), 1)
            delivery_view = (out / "DELIVERY_VIEW.md").read_text(encoding="utf-8")
            self.assertIn("# 资产交付总览", delivery_view)
            self.assertIn("复制：", delivery_view)
            self.assertIn("参考图上传助手", delivery_view)
            self.assertIn("四视图", delivery_view) if p["asset_cards"][0].get("asset_kind") == "character" else None
            self.assertNotIn("<details>", delivery_view)
            self.assertIn((out / result[0]["prompt_file"]).read_text(encoding="utf-8").strip(), delivery_view)
        card = read_data(ROOT / "templates/asset-stage.json")["asset_cards"][0]
        card["prompt"] = "Create a full-body portrait. {{BODY}} {{BEHAVIOR}}"
        card["prompt_bindings"] = {"BODY": "An adult woman with a lean athletic build and grounded feet.",
                                   "BEHAVIOR": "Her shoulders stay lowered, gaze steady, hands loosely open."}
        prompt = render_asset_prompt(card)
        self.assertIn("lean athletic build", prompt)
        self.assertNotIn("{{", prompt)

    def test_missing_image_inputs_block_delivery_before_output_is_created(self):
        original = read_data(ROOT / "templates/asset-stage.json")
        for change in ("missing", "unlisted", "editing"):
            p = copy.deepcopy(original)
            card = p["asset_cards"][0]
            if change == "missing":
                card["reference_policy"] = "required"
                card["references"] = [{"image": 1, "file": "no-such-image.png", "role": "identity", "subject": "the adult woman", "preserve": "her face", "exclude": "the original light"}]
            elif change == "unlisted":
                card["prompt"] += " Use reference image 2 for the face."
            else:
                card["mode"] = "EDIT"
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "assets.json"
                source.write_text(json.dumps(p), encoding="utf-8")
                with self.assertRaises(ValueError):
                    compile_assets(source, Path(temp) / "out")
                self.assertFalse((Path(temp) / "out").exists())

    def test_video_export_adds_human_readable_delivery_view(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "video"
            result = compile_package(EX / "02-drama.production.json", out)
            self.assertEqual(len(result), 2)
            view = (out / "DELIVERY_VIEW.md").read_text(encoding="utf-8")
            self.assertIn("# H3 视频交付总览", view)
            self.assertIn("## 段落地图", view)
            self.assertIn("DRAMA_SEG01.upload.md", view)
            self.assertIn("参考图上传助手：本段无需上传参考图", view)
            self.assertNotIn("<details>", view)
            for entry in result:
                prompt = (out / entry["file"]).read_text(encoding="utf-8").strip()
                self.assertNotIn(prompt, view)
                self.assertTrue((out / entry['upload_card']).is_file())
            ref_out = Path(temp) / "ref-video"
            compile_package(EX / "01-mecha.production.json", ref_out)
            ref_view = (ref_out / "DELIVERY_VIEW.md").read_text(encoding="utf-8")
            self.assertIn("<Picture 1>", ref_view)
            self.assertIn("实际上传文件", ref_view)
            self.assertNotIn("<details>", ref_view)
            for entry in read_data(EX / "01-mecha.production.json")["segments"]:
                prompt = (ref_out / f"{entry['id']}.h3.txt").read_text(encoding="utf-8").strip()
                self.assertNotIn(prompt, ref_view)

    def test_second_video_segment_is_independent_and_preserves_spoken_text(self):
        p = read_data(EX / "02-drama.production.json")
        seg = p["segments"][1]
        text = compile_segment(p, seg)
        for item in p["character_registry"] + p["scene_registry"]:
            self.assertIn(item["prompt_description"], text)
        self.assertIn(p["shots"][1]["state_description"], text)
        self.assertIn("(S1)", text)
        self.assertIn("<d>[Chinese] 那就一起把门打开。</d>", text)
        self.assertEqual(audit(p, EX)["status"], "PASS")
        del p["character_registry"][0]["prompt_description"]
        self.assertEqual(audit(p, EX)["gates"][7]["status"], "FAIL")

    def test_unexpanded_codes_are_blocked_in_both_model_exports(self):
        original = read_data(EX / "02-drama.production.json")
        for shorthand in ("A身材 I性格", "body type A", "M01", "E042", "EX-S01-B01", "运镜052", "CHAR_LU", "同上", "{{MISSING}}"):
            p = copy.deepcopy(original)
            p["asset_cards"][0]["prompt"] += " " + shorthand
            with self.subTest(shorthand=shorthand):
                with self.assertRaises(ValueError):
                    check_assets(p, EX)
                p["shots"][1]["visual"] += " " + shorthand
                self.assertEqual(audit(p, EX)["gates"][7]["status"], "FAIL")
        p = copy.deepcopy(original)
        p["segments"][1]["overall_soundscape"] += " CHAR_LU"
        self.assertEqual(audit(p, EX)["gates"][7]["status"], "FAIL")

    def test_supported_h3_labels_and_literals_are_not_mistaken_for_codes(self):
        p = read_data(EX / "01-mecha.production.json")
        self.assertEqual(audit(p, EX)["gates"][7]["status"], "PASS")
        self.assertIn("<Picture 1>", compile_segment(p, p["segments"][0]))
        p["segments"][0]["subjects"] = [{"label": "<Subject 1>", "definition": "<Subject 1> is Forge's left-side blocking position in <Picture 1>.", "retention": "<Subject 1> (appears in [Shot 1]): weak_reference - retain its left-side position only."}]
        p["shots"][0]["visual"] += " Forge takes the position of <Subject 1>."
        self.assertEqual(audit(p, EX)["gates"][7]["status"], "PASS")
        require_standalone("A body with natural proportions moves gently.")
        literal = '<d>[Chinese] A身材是代号，{{BODY}}不要改。</d>'
        self.assertEqual(expand_prompt(literal, {"BODY": "adult body"}), literal)
        require_standalone(literal, english=True)
        with self.assertRaisesRegex(PromptDeliveryError, "cyclic"):
            expand_prompt("{{BODY}}", {"BODY": "{{BODY}}"})

    def test_at_image_syntax_is_supported_and_not_blocked(self):
        card = {
            'id': 'CHAR_TEST',
            'asset_kind': 'character',
            'mode': 'GENERATE',
            'reference_policy': 'required',
            'references': [
                {'image': 1, 'role': 'style', 'subject': 'the style anchor', 'preserve': 'brushwork', 'exclude': 'characters'}
            ],
            'prompt': 'Create a character turnaround sheet following @图片1 visual style.'
        }
        prompt = render_asset_prompt(card)
        self.assertIn('@图片1', prompt)
        self.assertIn('Reference image 1', prompt)
        require_standalone('参考@图片1的画风，保持线条。')
        require_standalone('参考@图1的画风，保持线条。')


if __name__ == "__main__":
    unittest.main()
