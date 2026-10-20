import copy
import sys
import unittest
import json
import hashlib
import tempfile

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_storyboard_quality import compile_segment, read_data
from h3_final_format import H3FormatError, finalize_h3_prompt, normalize_h3_prompt, validate_h3_file, file_contract


class H3FinalFormatAcceptance(unittest.TestCase):
    def ref_fixture(self):
        production = read_data(ROOT / "examples/01-mecha.production.json")
        segment = production["segments"][0]
        return compile_segment(production, segment), dict(mode="Ref2VA", shot_count=2, reference_labels=["<Picture 1>"], duration_seconds=14)

    def test_actual_bad_retention_and_internal_ids_cannot_pass(self):
        text, options = self.ref_fixture()
        for broken in (text.replace("weak_reference -", "weak_reference for"),
                       text.replace("the two figures", "CHAR_ACTOR_01 and the two figures")):
            with self.subTest(broken=broken[:40]), self.assertRaises(H3FormatError):
                finalize_h3_prompt(broken, **options)

    def test_subject_only_fake_reference_and_bad_cut_and_audio_fail(self):
        text, options = self.ref_fixture()
        cases = [text.replace("<Picture 1>", "<Subject 1>"),
                 text.replace("At 00:07.000,", "At 00:14.000,"),
                 text.replace("overall_soundscape:\n", "overall_soundscape:\nA hum is audible.\n\n"),
                 text.replace("[reference generation]", "[Task: Ref2VA]")]
        for broken in cases:
            with self.subTest(broken=broken[:40]), self.assertRaises(H3FormatError):
                finalize_h3_prompt(broken, **options)

    def test_unregistered_extra_dialogue_and_nonlocal_speaker_fail(self):
        production = read_data(ROOT / "examples/02-drama.production.json")
        text = compile_segment(production, production["segments"][0])
        options = dict(mode="T2VA", shot_count=2, speech_expectations=[("S1", "Chinese", "上次是我没听。现在你来。")])
        for broken in (text.replace("(S1)", "(S2)"), text.replace("</d>", "</d> (S1) says: <d>[Chinese] 新增台词。</d>")):
            with self.subTest(broken=broken[:40]), self.assertRaises(H3FormatError):
                finalize_h3_prompt(broken, **options)

    def test_final_file_uses_real_reference_hash_and_preserves_bytes(self):
        production = read_data(ROOT / "examples/01-mecha.production.json")
        segment = production["segments"][0]
        refs = []
        for ref in segment["references"]:
            source = (ROOT / "examples" / ref["file"]).resolve()
            refs.append(dict(label=ref["label"], file=str(source), role=ref["role"], sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
        contract = file_contract(production, segment, refs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "segment.h3.txt"
            path.write_text(compile_segment(production, segment), encoding="utf-8")
            before = path.read_bytes()
            receipt = validate_h3_file(path, contract, allow_legacy_fixture=True)
            self.assertEqual(receipt["sha256"], hashlib.sha256(before).hexdigest())
            self.assertEqual(path.read_bytes(), before)
            contract["references"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(H3FormatError, "SHA-256"):
                validate_h3_file(path, contract, allow_legacy_fixture=True)

    def test_final_file_accepts_json_list_dialogue_manifest(self):
        production = read_data(ROOT / "examples/06-animated-phone.production.json")
        segment = production["segments"][0]
        # This test checks JSON speech-list structure only, not source semantics.
        # The production example itself remains a blocked missing-media draft.
        refs = []
        for ref in segment["references"]:
            source = ROOT / 'examples/media/mecha-contact.png'
            refs.append(dict(label=ref["label"], file=str(source), role=ref["role"], sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
        contract = file_contract(production, segment, refs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dialogue.h3.txt"
            path.write_text(compile_segment(production, segment), encoding="utf-8")
            receipt = validate_h3_file(path, json.loads(json.dumps(contract)), allow_legacy_fixture=True)
            self.assertEqual(receipt["dialogue_count"], len(contract["speech_expectations"]))

    def test_commit_reads_final_bytes_rejects_forged_pass_and_preserves_partial(self):
        from orchestrator_plan import plan_and_state
        from orchestrator_commit import commit_artifact
        from workflow_state import save_state
        from contract_core import content_hash
        production = {"version": "2.0", "shots": [], "segments": [{"id": "SEG", "mode": "T2VA", "shot_ids": []}]}
        _, state = plan_and_state({"request_id": "CHECK", "intent": "h3-compile"}, production)
        node = next(n for n in state['nodes'] if n['phase'] == 'model')
        # This test isolates final-file acceptance; graph dependencies are tested separately.
        node['depends_on'] = []
        state['nodes'] = [node]
        revision = content_hash(production)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "SEG.h3.txt"
            path.write_text("integrated_multimodal_description:\n[Shot 1] A camera moves north at 2 m/s.\n\noverall_soundscape:\nWind blows.\n\nnon_diegetic_music:\nN/A\n", encoding="utf-8")
            sp = root / "state.json"
            save_state(sp, state)
            with self.assertRaisesRegex(ValueError, "manifest missing"):
                commit_artifact(state, sp, node, path, revision)
            contract = dict(mode="T2VA", duration_seconds=10, shot_count=1, references=[], speech_expectations=[], input_revision=revision, format_pass="PASSED")
            Path(str(path) + ".check.json").write_text(json.dumps(contract), encoding="utf-8")
            good = path.read_text(encoding="utf-8")
            path.write_text(good.replace("[Shot 1]", "[Shot 1: 00:00.000]"), encoding="utf-8")
            with self.assertRaises(H3FormatError):
                commit_artifact(state, sp, node, path, revision)
            partial = commit_artifact(state, sp, node, path, revision, status="partial", artifact_id="part", cursor={"segment_id": "SEG", "field": "timeline"})
            self.assertFalse(partial["artifact"]["accepted"])
            self.assertTrue(state["continuation_required"])
            path.write_text(good, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, 'binding manifest missing'):
                commit_artifact(state, sp, node, path, revision, artifact_id="final")
            from compile_h3 import compile_package
            production = read_data(ROOT / 'examples/02-drama.production.json')
            revision = content_hash(production)
            _, state = plan_and_state({'request_id': 'JOINT', 'intent': 'h3-compile'}, production)
            node = next(n for n in state['nodes'] if n['phase'] == 'model')
            node['depends_on'] = []
            state['nodes'] = [node]
            exported = compile_package(ROOT / 'examples/02-drama.production.json', root / 'bundle')
            path = root / 'bundle' / exported[0]['file']
            result = commit_artifact(state, sp, node, path, revision, artifact_id="final")
            self.assertTrue(result["artifact"]["accepted"])
            self.assertTrue(result["artifact"]["evidence"])
            self.assertEqual(commit_artifact(state, sp, node, path, revision, artifact_id="final")["status"], "IDEMPOTENT")

    def test_compiled_ref2va_passes_without_losing_engineering_detail(self):
        production = read_data(ROOT / "examples/01-mecha.production.json")
        segment = production["segments"][0]
        text = compile_segment(production, segment)
        self.assertIn("35 Hz", text)
        self.assertIn("Direction facts:", text)
        self.assertIn("Speed profile:", text)
        self.assertIn("<Picture 1>", text)
        self.assertIn("[Shot 1]", text)

    def test_format_pass_rejects_malformed_shot_and_dialogue_structure(self):
        production = read_data(ROOT / "examples/02-drama.production.json")
        segment = production["segments"][0]
        text = compile_segment(production, segment)
        broken = text.replace("[Shot 1]", "[Shot 1: 00:00.000 – 00:03.000]", 1)
        broken = broken.replace("<d>[Chinese]", "[Chinese]", 1)
        with self.assertRaises(H3FormatError):
            finalize_h3_prompt(
                broken,
                mode=segment["mode"],
                shot_count=len(segment["shot_ids"]),
                speech_expectations=[("S1", "Chinese", "上次是我没听。现在你来。")],
            )

    def test_format_pass_rejects_ref2va_below_minimum_without_compressing(self):
        production = read_data(ROOT / "examples/01-mecha.production.json")
        segment = copy.deepcopy(production["segments"][0])
        text = compile_segment(production, segment)
        body = text.split("detailed_description:\n", 1)[1].split("\n\noverall_soundscape:", 1)[0]
        shortened = text.replace(body, "[Shot 1] Short.\n[Shot 2] At 00:07.000, short.")
        with self.assertRaisesRegex(H3FormatError, "minimum"):
            finalize_h3_prompt(
                shortened,
                mode="Ref2VA",
                shot_count=2,
                reference_labels=["<Picture 1>"],
                minimum_words=2000,
            )

    def test_format_pass_rejects_speaker_without_local_speech_binding(self):
        production = read_data(ROOT / "examples/02-drama.production.json")
        segment = production["segments"][0]
        text = compile_segment(production, segment)
        broken = text.replace("says", "describes", 1)
        with self.assertRaisesRegex(H3FormatError, "locally bound"):
            finalize_h3_prompt(
                broken,
                mode=segment["mode"],
                shot_count=len(segment["shot_ids"]),
                speech_expectations=[("S1", "Chinese", "上次是我没听。现在你来。")],
            )

    def test_normalization_only_changes_line_endings_and_trailing_space(self):
        source = "integrated_multimodal_description:\r\n[Shot 1] detail.  \r\n\r\noverall_soundscape:\r\nN/A\r\n\r\nnon_diegetic_music:\r\nN/A\r\n"
        normalized = normalize_h3_prompt(source)
        self.assertEqual(normalized, "integrated_multimodal_description:\n[Shot 1] detail.\n\noverall_soundscape:\nN/A\n\nnon_diegetic_music:\nN/A\n")


if __name__ == "__main__":
    unittest.main()
