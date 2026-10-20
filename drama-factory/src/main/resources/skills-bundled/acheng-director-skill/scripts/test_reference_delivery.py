"""Five public acceptance scenarios for the 4.3.6 reference-delivery slice."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from audit_storyboard_quality import compile_segment, read_data
from compile_h3 import compile_package
from contract_core import content_hash
from director_dispatch import plan_dispatch
from director_pipeline import archive, restore
from h3_delivery import validate_package, validate_segment_bundle, validate_upload_receipt
from orchestrator_commit import commit_artifact
from orchestrator_plan import plan_and_state
from reference_bindings import resolve_bindings
from workflow_state import save_state

ROOT = Path(__file__).resolve().parents[1]

# Authored visible blocking, not repeated filler; the diagram only proves layout.
EXTRA_DETAIL = (
    "Before either machine closes distance, the view holds both support triangles against the same floor seams. "
    "The left machine's rear heel remains inside the nearer rectangle, while the right machine's shield edge overlaps its own chest silhouette without hiding the opponent's fist. "
    "A narrow dark interval between the two forearms remains visible until the existing contact event; this negative space makes the approach and actual collision distinguishable. "
    "The floor reflection follows the planted soles rather than anticipating their movement. The overhead beams remain parallel in perspective as the camera travels along its authored path, so the background cannot imply an unplanned reverse angle. "
    "Small loose fragments remain below the ankle silhouettes and never become a second attack or a screen-filling flash. Their visible drift follows the already described local airflow, then the pieces settle against the same floor seams. "
    "The nearer shoulder plate casts a short shadow over its own upper arm; that shadow travels with the joint and does not jump onto the opponent before contact. "
    "The camera keeps the established screen axis readable through the gap between the torsos. Any change in their relative size comes from the authored depth and camera motion, not an unexplained scale change. "
    "Neither machine acquires a new weapon, a face, a logo or a speaking voice from the gray diagram. Its panel captions and grid borders remain planning information outside the target image. "
    "The existing recovery remains the final action: the hands stop at their established limits, the body weight settles through the support leg, and the trailing material completes its lag without restarting the strike. "
    "The last held composition leaves both the nearest ground contact and the open continuation route readable, with the same motivated key light on the armor edges and the described mechanical sound decaying into room tone."
)


def fixture(base, kind="ref"):
    production = read_data(ROOT / ("examples/01-mecha.production.json" if kind == "ref" else "examples/02-drama.production.json"))
    # Keep all original design facts. Rebase test inputs without mutating examples.
    for group in production["segments"] + production.get("asset_cards", []):
        for ref in group.get("references", []):
            original = ROOT / "examples" / ref["file"]
            target = base / ref["file"]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(original, target)
    if kind == "ref":
        production["prompt_detail_policy"] = {"profile": "strict", "ref2va_max_words": 4000}
        segment = production["segments"][0]
        segment.update(mode_lock="Ref2VA", mode_selection_reason="The real blocking diagram supplies composition and event ordering only.")
        production["shots"][0]["visual"] += " " + EXTRA_DETAIL
        ref = segment["references"][0]
        sha = hashlib.sha256((base / ref["file"]).read_bytes()).hexdigest()
        ref.update(asset_version="blocking-v1", entity_id="blocking-board", sha256=sha,
                   approval={"status": "approved", "sha256": sha, "evidence": "Bundled authored 16-panel gray diagram reviewed for layout only; not identity or generated film."},
                   preserve="relative screen sides and ordered blocking", exclude="grid, captions, schematic appearance and materials", shot_ids=segment["shot_ids"])
        for shot in production['shots']:
            shot['reference_requirements'] = [{'entity_id': 'blocking-board', 'asset_version': 'blocking-v1', 'purpose': 'storyboard blocking and ordering only'}]
    path = base / "production.json"
    path.write_text(json.dumps(production, ensure_ascii=False), encoding="utf-8")
    return production, path


class ReferenceDeliveryAcceptance(unittest.TestCase):
    def test_real_bound_ref2va_one_source_bundle_and_upload_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            p, source = fixture(base)
            before = content_hash(p)
            entry = compile_package(source, base / "out")[0]
            self.assertEqual(content_hash(read_data(source)), before)
            self.assertEqual(entry["status"], "READY_TO_UPLOAD")
            self.assertEqual(entry["platform_status"], "NOT_UPLOADED")
            self.assertEqual(validate_package(base / "out", p, base)["status"], "PASS")
            text = (base / "out" / entry["file"]).read_text(encoding="utf-8")
            for detail in (EXTRA_DETAIL, "Direction facts:", "Speed profile:", "35 Hz", p["shots"][0]["state_description"]):
                self.assertIn(detail, text)
            proof = base / "out" / "platform-observation.txt"
            proof.write_text("TEST RECEIPT ONLY: not an actual cloud upload", encoding="utf-8")
            receipt = {"segment_id": entry["segment_id"], "input_revision": entry["input_revision"], "prompt_sha256": entry["sha256"],
                       "binding_sha256": entry["binding_snapshot"]["binding_sha256"], "platform": "test-platform", "request_id": "test-request", "confirmed_by": "test-fixture",
                       "uploads": [{"label": r["label"], "sha256": r["sha256"]} for r in entry["references"]],
                       "evidence": {"file": proof.name, "sha256": hashlib.sha256(proof.read_bytes()).hexdigest()}}
            self.assertEqual(validate_upload_receipt(base / "out", entry, receipt)["platform_status"], "UPLOAD_CONFIRMED_BY_RECORDED_EVIDENCE")
            receipt["uploads"][0]["label"] = "<Picture 2>"
            with self.assertRaisesRegex(ValueError, "slot/hash"):
                validate_upload_receipt(base / "out", entry, receipt)

    def test_missing_and_prompt_only_media_keep_full_draft_and_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            original, source = fixture(base)
            for name in ("empty", "missing", "prompt"):
                with self.subTest(name=name):
                    p = copy.deepcopy(original)
                    if name == "empty":
                        p["segments"][0]["references"] = []
                    else:
                        p["segments"][0]["references"][0]["file"] = "missing.png" if name == "missing" else "asset.image.txt"
                        if name == "prompt":
                            (base / "asset.image.txt").write_text("Create the image later.", encoding="utf-8")
                    source.write_text(json.dumps(p), encoding="utf-8")
                    entry = compile_package(source, base / name)[0]
                    self.assertEqual(entry["mode"], "Ref2VA")
                    self.assertFalse(entry["accepted"])
                    self.assertEqual(entry["status"], "DRAFT_MISSING_REFERENCES")
                    text = (base / name / entry["file"]).read_text(encoding="utf-8")
                    self.assertIn(EXTRA_DETAIL, text)
                    card = (base / name / entry["upload_card"]).read_text(encoding="utf-8")
                    self.assertNotIn("无需上传", card)
                    self.assertNotIn("PASSED", card)
                    self.assertTrue(entry["binding_snapshot"]["references"])
                    self.assertEqual(validate_package(base / name)["status"], "DRAFT_NOT_SUBMITTABLE")
            for example in ('06-animated-phone', '08-suspense-whisper'):
                entry = compile_package(ROOT / 'examples' / (example + '.production.json'), base / example)[0]
                self.assertFalse(entry['accepted'])
                self.assertEqual(entry['status'], 'DRAFT_MISSING_REFERENCES')
                self.assertNotIn('ink-opening.png', json.dumps(entry['references']))
                if example == '06-animated-phone':
                    body = (base / example / entry['file']).read_text(encoding='utf-8')
                    self.assertIn('<Subject 1> (S1)', body)
                    self.assertNotIn('first-frame pose', body.split('\n[Shot 2]', 1)[1])
                    self.assertEqual(entry['binding_snapshot']['subjects'][0]['speaker_id'], 'S1')

    def test_t2va_and_both_delivery_modes_preserve_full_independent_text(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            p, source = fixture(base, "text")
            entries = compile_package(source, base / "batch")
            chat = (base / "batch/CHAT_DELIVERY.md").read_text(encoding="utf-8")
            for entry in entries:
                self.assertIn(entry["upload_card"], chat)
                self.assertIn("无需上传参考图", (base / "batch" / entry["upload_card"]).read_text(encoding="utf-8"))
                self.assertNotIn((base / "batch" / entry["file"]).read_text(encoding="utf-8").strip(), chat)
            with self.assertRaisesRegex(ValueError, "requires --segment"):
                compile_package(source, base / "bad-interactive", execution_mode="interactive_segment")
            one = compile_package(source, base / "interactive", execution_mode="interactive_segment", segment_id=p["segments"][1]["id"])
            self.assertEqual(len(one), 1)
            view = (base / "interactive/DELIVERY_VIEW.md").read_text(encoding="utf-8")
            self.assertIn(compile_segment(p, p["segments"][1]).strip(), view)
            self.assertIn("WAIT_FOR_USER_CONTINUE", view)

    def test_conflicts_scope_tamper_and_stale_revision_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            p, source = fixture(base)
            seg = p["segments"][0]
            seg["subjects"] = [{"label": "<Subject 1>", "entity_id": "left-blocking", "definition": "<Subject 1> is the left-side blocking figure in <Picture 1>, used only for position, not identity.", "retention": "<Subject 1> (appears in [Shot 2]): weak_reference - preserve left-side placement only.", "shot_ids": [seg["shot_ids"][1]]}]
            source.write_text(json.dumps(p), encoding="utf-8")
            entry = compile_package(source, base / "out")[0]
            text = (base / "out" / entry["file"]).read_text(encoding="utf-8")
            self.assertNotIn("<Subject 1>", text.split("\n[Shot 1] ", 1)[1].split("\n[Shot 2]", 1)[0])
            self.assertIn("<Subject 1>", text.split("\n[Shot 2]", 1)[1])
            for key in ("file", "upload_card"):
                target = base / "out" / entry[key]
                saved = target.read_bytes()
                target.write_bytes(saved + b"changed")
                with self.assertRaises(ValueError):
                    validate_segment_bundle(base / "out", entry)
                target.write_bytes(saved)
            stale = copy.deepcopy(p)
            stale["segments"][0]["subjects"][0]["entity_id"] = "another-object"
            with self.assertRaisesRegex(ValueError, "stale production"):
                validate_package(base / "out", stale, base)
            conflict = copy.deepcopy(p)
            ref = conflict["segments"][0]["references"][0]
            ref.update(asset_id="BOARD", asset_version="v2")
            conflict["asset_plan"] = [{"id": "BOARD", "status": "approved", "version": "v1", "file": ref["file"], "sha256": ref["sha256"]}]
            self.assertTrue(any("version conflict" in s for s in resolve_bindings(conflict, conflict["segments"][0], base)["issues"]))
            seg["references"][0]["state_guards"] = [{"domain": "scenes", "target": p["shots"][0]["scene_id"], "equals": 999}]
            self.assertTrue(any("state conflicts" in s for s in resolve_bindings(p, seg, base)["issues"]))
            # A source-only identity image must respect its temporal scope too.
            from reference_bindings import shot_reference_text
            scoped = copy.deepcopy(seg)
            scoped['references'][0].update(source_only=True, shot_ids=[seg['shot_ids'][1]], start_frame=200, end_frame=250)
            self.assertEqual(shot_reference_text(scoped, p['shots'][0], p), '')
            self.assertIn('From 8.333 to 10.417 seconds', shot_reference_text(scoped, p['shots'][1], p))
            middle = copy.deepcopy(p)
            midref = middle['segments'][0]['references'][0]
            midref.update(shot_ids=[seg['shot_ids'][1]], start_frame=228, end_frame=336,
                          state_guards=[{'domain': 'scenes', 'target': p['shots'][0]['scene_id'], 'equals': 1}])
            self.assertFalse(any('state conflicts' in e for e in resolve_bindings(middle, middle['segments'][0], base)['issues']))
            midref['start_frame'] = 168
            self.assertTrue(any('state conflicts' in e for e in resolve_bindings(middle, middle['segments'][0], base)['issues']))

    def test_routing_commit_partial_and_archive_remain_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            p, source = fixture(base)
            plan, state = plan_and_state({"request_id": "ACCEPT436", "intent": "h3-compile", "execution_mode": "1"}, p)
            self.assertNotIn("style-anchor", [n["id"] for n in plan["nodes"]])
            node = next(n for n in plan["nodes"] if n["phase"] == "model")
            self.assertEqual(node["depends_on"], ["reference-binding:" + p["segments"][0]["id"]])
            # Isolate the compiled bundle submission after asserting its production route.
            node['depends_on'] = []
            state['nodes'] = [node]
            dispatch = plan_dispatch(p, {"request_id": "ROUTE436", "stage": "h3-compile"})
            self.assertIn("continuity", [n["module"] for n in dispatch["steps"][0]["neighbor_checks"]])
            entry = compile_package(source, base / "out")[0]
            state_path = base / "state.json"
            save_state(state_path, state)
            prompt = base / "out" / entry["file"]
            partial = commit_artifact(state, state_path, node, prompt, content_hash(p), status="partial", artifact_id="partial", cursor={"segment_id": entry["segment_id"], "field": "detailed_description"})
            self.assertFalse(partial["artifact"]["accepted"])
            self.assertTrue(state["continuation_required"])
            card = base / "out" / entry["upload_card"]
            saved = card.read_bytes()
            card.unlink()
            with self.assertRaises(OSError):
                commit_artifact(state, state_path, node, prompt, content_hash(p), artifact_id="complete")
            card.write_bytes(saved)
            complete = commit_artifact(state, state_path, node, prompt, content_hash(p), artifact_id="complete")
            self.assertTrue(complete["artifact"]["accepted"])
            committed = Path(complete["artifact"]["path"])
            self.assertEqual(validate_segment_bundle(committed.parent, entry)["joint_status"], "PASSED")
            self.assertEqual(commit_artifact(state, state_path, node, prompt, content_hash(p), artifact_id="complete")["status"], "IDEMPOTENT")
            saved_archive = archive(p, base, base / "archive")
            restored = restore(saved_archive, base / "restored")
            self.assertEqual(compile_package(restored, base / "restored-output")[0]["status"], "READY_TO_UPLOAD")


if __name__ == "__main__":
    unittest.main()
