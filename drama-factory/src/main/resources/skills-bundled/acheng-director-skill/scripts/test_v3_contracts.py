"""Five acceptance cases for the v3 public production contracts."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from asset_plan import check_asset_plan
from audit_storyboard_quality import audit, compile_segment, digest
from build_examples import create_drama, create_mecha
from build_v3_examples import add_handoff, create_serial
from compile_assets import compile_assets
from director_dispatch import accept_response, plan_dispatch
from director_pipeline import archive, optimize, pack, restore
from production_extensions import check_performance
from post_hooks import check_style_lock
from story_contract import check_story

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class V3Acceptance(unittest.TestCase):
    def test_narrative_tracks_knowledge_setups_and_screenplay_coverage(self):
        p = create_serial()
        self.assertEqual(check_story(p)["threads"], 8)
        self.assertEqual(check_story(p)["beats"], 12)
        renamed = copy.deepcopy(p); original_id = renamed["story"]["threads"][0]["id"]
        renamed["story"]["threads"][0]["id"] = "D"
        for beat in renamed["story"]["beats"]:
            if beat["primary_thread"] == original_id: beat["primary_thread"] = "D"
        self.assertEqual(check_story(renamed)["threads"], 8)
        for mutation in ("knowledge", "payoff", "coverage", "dialogue"):
            q = copy.deepcopy(p)
            if mutation == "knowledge":
                q["story"]["beats"][0]["requires_knowledge"] = [{"holder": "CHAR_MEI", "fact_id": "FACT_COPY", "state": "knows"}]
            elif mutation == "payoff":
                q["story"]["setups"][0]["payoff_beat"] = "BEAT_01"
            elif mutation == "coverage":
                q["script_scenes"].pop()
            else:
                q["script_scenes"][6]["text"] = "人物改口，删去了已确认的原台词。"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                check_story(q)

    def test_performance_provenance_and_module_write_authority(self):
        p = create_drama(); add_handoff(p)
        self.assertEqual(check_performance(p)["mapped_beats"], 2)
        self.assertIn(p["shots"][0]["performance"]["events"][0]["cue"], compile_segment(p, p["segments"][0]))
        p["expression_handoff"]["source_locked"] = False
        with self.assertRaises(ValueError): check_performance(p)
        p = create_serial()
        with self.assertRaises(ValueError):
            plan_dispatch({}, {"request_id": "REQ_MISSING", "stage": "full", "completed_modules": ["story"]})
        dispatch = plan_dispatch(p, {"request_id": "REQ_STORY", "stage": "script"})
        response = {"request_id": "REQ_STORY", "input_revision": digest(p), "module": "story", "status": "READY", "attempt": 1,
                    "patch": [{"path": "/story/character_arcs/0/voice", "value": "措辞精确，先限定证据再给结论，保留原对白。"}], "evidence": ["Only the internal character voice note changes; locked dialogue is preserved."], "unresolved": []}
        updated, receipt = accept_response(p, dispatch, response)
        self.assertEqual(receipt["status"], "MERGED_CONTRACT_CHECKED")
        self.assertEqual(updated["shots"], p["shots"])
        self.assertEqual(receipt['validation_scope'], 'phase_contract_only')
        self.assertFalse(receipt['final_delivery_accepted'])
        pending = copy.deepcopy(p)
        pending['segments'][0]['summary'] = '[unsupported-task] This later model field is unfinished.'
        pending_dispatch = plan_dispatch(pending, {"request_id": "REQ_STORY", "stage": "script"})
        pending_response = {**response, 'input_revision': digest(pending)}
        self.assertEqual(accept_response(pending, pending_dispatch, pending_response)[1]['status'], 'MERGED_CONTRACT_CHECKED')
        with self.assertRaisesRegex(ValueError, "stale"): accept_response(updated, dispatch, response)
        response["patch"][0]["path"] = "/shots/0/camera"
        with self.assertRaisesRegex(ValueError, "unauthorized"): accept_response(p, dispatch, response)

    def test_clip_bounds_h3_prefix_and_independent_cross_cut_dialogue(self):
        p = {"fps_num": 24, "fps_den": 1, "generation_clip_limit": 15, "production_total_duration": 17, "segments": [],
             "shots": [{"id": "SHOT_A", "start_frame": 0, "end_frame": 336}, {"id": "SHOT_B", "start_frame": 336, "end_frame": 408}]}
        with self.assertRaisesRegex(ValueError, "No legal"): pack(p)
        p["shots"] = [{"id": f"SHOT_{i}", "start_frame": a, "end_frame": b} for i, (a,b) in enumerate(((0,168),(168,336),(336,408)))]
        self.assertEqual([s["generation_clip_duration"] for s in pack(p)["segments"]], [7,10])
        p = create_mecha(); p["segments"][0]["summary"] = "[unsupported-task] Follow the reference."
        self.assertEqual(audit(p, EX)["gates"][7]["status"], "FAIL")
        p = create_drama()
        self.assertIn("(S1)", compile_segment(p, p["segments"][1]))
        p = create_mecha()
        for i, (s, part) in enumerate(zip(p["shots"], ("Hold ", "the line."))):
            s["dialogues"] = [{"speaker_id": "S1", "speaker_name": "Forge", "language": "English", "text": part, "delivery": "in a low mechanical voice", "start": 0 if i else 72, "end": 72 if i else 168, "utterance_id": "SPEECH_HOLD", "source_text": "Hold the line."}]
        self.assertEqual(audit(p, EX)["status"], "PASS")
        self.assertEqual(compile_segment(p, p["segments"][0]).count("<scenetrans>"), 2)

    def test_nonfluid_effect_family_and_frozen_optimization(self):
        p = create_drama(); s = p["shots"][0]; s["features"]["supernatural_vfx"] = True
        s["vfx"] = {"family": "optical", "origin": "A thin transparent panel stands beyond the east window.", "scope": "Only the background seen through the window is affected.",
                    "process": "A narrow refractive distortion travels across the distant rain while both faces remain clear.", "end_state": "The distortion ends and the background returns to its original alignment.",
                    "lighting": "The existing window light remains stable.", "continuity": "The room, people and key remain unchanged by this background effect.",
                    "events": [{"start": 24, "end": 100, "cue": "The distant rain bends briefly through the transparent panel."}]}
        self.assertEqual(audit(p, EX)["status"], "PASS")
        self.assertNotIn("fluid", compile_segment(p, p["segments"][0]).lower())
        negative = copy.deepcopy(p); negative["shots"][0]["vfx"]["events"][0]["start"] = -1
        self.assertEqual(audit(negative, EX)["gates"][5]["status"], "FAIL")
        replacement = copy.deepcopy(s["vfx"]); replacement["lighting"] = "A faint existing window reflection stays below the cheek highlights."
        patch = {"base_sha256": digest(p), "mode": "OPTIMIZE", "updates": [{"shot_id": s["id"], "vfx": replacement}]}
        self.assertEqual(optimize(p, patch, EX)["shots"][0]["vfx"]["lighting"], replacement["lighting"])
        replacement["process"] = "The effect teleports the key outside the room."
        with self.assertRaisesRegex(ValueError, "freezes"): optimize(p, patch, EX)

    def test_asset_coverage_dependencies_draft_readiness_and_recovery(self):
        p = create_serial()
        report = check_asset_plan(p, EX)
        self.assertEqual(len(report["production_order"]), 12)
        q = copy.deepcopy(p); q["shots"][0]["required_assets"].remove("ART_MEI")
        with self.assertRaisesRegex(ValueError, "character asset missing"): check_asset_plan(q, EX)
        q = copy.deepcopy(p); q["asset_plan"][0]["depends_on"] = ["ART_KEYFRAME_01"]
        with self.assertRaisesRegex(ValueError, "cyclic"): check_asset_plan(q, EX)
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp); source = temp / "production.json"
            source.write_text(json.dumps(p,ensure_ascii=False),encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing approved"): compile_assets(source,temp/"blocked")
            self.assertFalse((temp/"blocked").exists())
            entries = compile_assets(source,temp/"draft",True)
            self.assertEqual(sum(e["status"]=="draft-missing-references" for e in entries),3)
            approved = temp/"approved.png"
            approved.write_bytes((EX/"media/mecha-contact.png").read_bytes())
            sha=hashlib.sha256(approved.read_bytes()).hexdigest()
            # A test fixture only: verifies file/version binding, not identity approval.
            for node in p["asset_plan"]:
                if node["kind"] != "keyframe": node.update(status="approved",file="approved.png",sha256=sha)
            source.write_text(json.dumps(p,ensure_ascii=False),encoding="utf-8")
            self.assertTrue(all(e["status"]=="ready-to-submit-not-generated" for e in compile_assets(source,temp/"ready")))
            saved=archive(p,temp,temp/"archive"); recovered=restore(saved,temp/"recovered")
            self.assertEqual(len(compile_assets(recovered,temp/"recovered-images")),12)

    def test_combat_timing_and_opt_in_style_mother_contracts(self):
        p = create_mecha()
        self.assertEqual(audit(p, EX)["status"], "PASS")
        q = copy.deepcopy(p)
        q["shots"][1]["combat"].pop("timing")
        self.assertEqual(audit(q, EX)["gates"][4]["status"], "FAIL")
        q = copy.deepcopy(p)
        timing = q["shots"][1]["combat"]["timing"]
        timing["slow_motion"]["start"], timing["slow_motion"]["end"] = 0, 12
        self.assertEqual(audit(q, EX)["gates"][4]["status"], "FAIL")
        q = copy.deepcopy(p)
        q["shots"][1]["combat"]["timing"]["direction_facts"].pop("origin")
        self.assertEqual(audit(q, EX)["gates"][4]["status"], "FAIL")
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            style = temp / "style.png"
            style.write_bytes((EX / "media/mecha-contact.png").read_bytes())
            sha = hashlib.sha256(style.read_bytes()).hexdigest()
            payload = {
                "style_lock": {"anchor_asset_id": "STYLE_MOTHER", "anchor_version": "v1", "status": "approved", "medium": "2d_cel",
                               "preserve_scope": ["line weight", "cel shadow hierarchy"], "exclude_scope": ["identity", "scene geometry"],
                               "apply_to_kinds": ["character"]},
                "asset_plan": [
                    {"id": "STYLE_MOTHER", "kind": "style", "version": "v1", "purpose": "approved rendering test frame", "depends_on": [], "status": "approved", "file": "style.png", "sha256": sha},
                    {"id": "CHAR_A", "kind": "character", "version": "v1", "purpose": "identity", "depends_on": ["STYLE_MOTHER"], "status": "planned"}],
                "asset_cards": [{"id": "STYLE_MOTHER", "recipe": "style"},
                                {"id": "CHAR_A", "references": [{"asset_id": "STYLE_MOTHER", "asset_version": "v1", "role": "style"}]}]
            }
            self.assertEqual(check_style_lock(payload, temp)["anchor_asset_id"], "STYLE_MOTHER")
            payload["asset_cards"][1]["references"].append({"asset_id": "CHAR_A", "asset_version": "v1", "role": "identity"})
            with self.assertRaisesRegex(ValueError, "final uploaded reference"):
                check_style_lock(payload, temp)
            payload["asset_cards"][1]["references"].pop()
            payload["asset_cards"][1]["references"] = []
            with self.assertRaisesRegex(ValueError, "style reference"):
                check_style_lock(payload, temp)


if __name__ == "__main__": unittest.main()
