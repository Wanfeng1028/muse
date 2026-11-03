"""Five acceptance tests for the public production, compiler and recovery contracts."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from audit_storyboard_quality import BASE_FIELDS, REF_FIELDS, ContractError, audit, compile_segment, digest, read_data
from director_pipeline import archive, optimize, pack, restore
from compile_h3 import compile_package
from post_hooks import check_script, check_assets

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples"


class ProductionAcceptance(unittest.TestCase):
    def setUp(self):
        self.mecha = read_data(EX / "01-mecha.production.json")

    def test_complete_examples_and_five_h3_modes(self):
        for path in sorted(EX.glob("*.production.json")):
            with self.subTest(example=path.name):
                production = read_data(path)
                report = audit(production, EX)
                if production.get('example_delivery_expectation') == 'DRAFT_MISSING_REFERENCES':
                    failed = [g for g in report['gates'] if g['status'] == 'FAIL']
                    self.assertEqual([g['gate'] for g in failed], ['h3_schema'])
                    self.assertTrue(all('missing reference file:' in e for e in failed[0]['errors']))
                else:
                    self.assertEqual(report['status'], 'PASS')
                self.assertEqual(pack(production)["shots"], production["shots"])
                for seg in production["segments"]:
                    text = compile_segment(production, seg)
                    fields = REF_FIELDS if seg["mode"] == "Ref2VA" else BASE_FIELDS
                    locations = [text.index(field + ":\n") for field in fields]
                    self.assertEqual(locations, sorted(locations))
                    self.assertNotRegex(text, r"\[Shot 1\] At \d{2}:\d{2}")
                    self.assertNotIn("Negative constraints:", text)
                    for shot in production['shots']:
                        if shot['id'] not in seg['shot_ids']: continue
                        self.assertIn(shot['camera']['sensor_basis'], text)
                        self.assertIn(str(shot['camera']['shutter_angle'])+'-degree', text)
                        for character in shot['characters']:
                            self.assertIn('x='+str(character['position'][0]), text)
                            self.assertIn(character['weapon_hand'], text)
                        if shot['audio']['low_frequency_hz'] is not None:
                            self.assertIn(shot['audio']['source'], text)
                        if shot['features']['supernatural_vfx']:
                            self.assertIn(shot['vfx']['origin'], text)
                        for proof in shot.get('scale_proofs', []):
                            self.assertIn(proof['frame_location'], text)
                            self.assertIn(proof['depth_relation'], text)
                    if path.name.startswith(('07-', '08-')):
                        self.assertNotRegex(text, r"\bLu\b|\bCen\b|key ring|injured right wrist|bandaged")
                        self.assertEqual(production['ledger']['events'], [])
                        self.assertTrue(all(c['trauma_phase'] is None for c in production['ledger']['initial']['characters'].values()))
        for mode in ("T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"):
            with self.subTest(mode=mode):
                p = copy.deepcopy(self.mecha)
                seg = p["segments"][0]
                seg["mode"] = mode
                if mode != "Ref2VA":
                    seg.pop("panels")
                    seg["references"] = []
                    count = 2 if mode == "FL2VA" else 0 if mode == "T2VA" else 1
                    for i in range(count):
                        seg["references"].append({"label": f"<Picture {i + 1}>", "file": "media/mecha-contact.png", "role": "test-only frame anchor"})
                    if mode in ("I2VA", "FL2VA"):
                        p["shots"][0]["visual"] = "The shot begins from <Picture 1>. " + p["shots"][0]["visual"]
                    if mode in ("FL2VA", "L2VA"):
                        p["shots"][-1]["visual"] += " The final pose and composition converge to <Picture " + ("2" if mode == "FL2VA" else "1") + "> at the end."
                self.assertEqual(audit(p, EX)["status"], "PASS")
                text = compile_segment(p, seg)
                if mode in ("FL2VA", "L2VA"):
                    self.assertIn("14.00-second mark", text.splitlines()[0])
                    self.assertIn("Shot 2", text.splitlines()[0])

    def test_timeline_scope_and_scene_registry_are_hard_gates(self):
        script = read_data(ROOT / "templates/script-stage.json")
        self.assertEqual(check_script(script)["status"], "PASS")
        script["script_scenes"][0]["scene_id"] = "UNKNOWN"
        with self.assertRaisesRegex(ContractError, "unregistered scene"):
            check_script(script)
        variants = []
        p = copy.deepcopy(self.mecha); p["shots"][1]["start_frame"] += 1; variants.append(p)
        p = copy.deepcopy(self.mecha); p["production_total_duration"] = 10; variants.append(p)
        p = copy.deepcopy(self.mecha); p["shots"][0]["scene_id"] = "UNREGISTERED"; variants.append(p)
        p = copy.deepcopy(self.mecha); p["segments"][0]["shot_ids"].reverse(); variants.append(p)
        p = copy.deepcopy(self.mecha); p["shots"] = []; variants.append(p)
        for p in variants:
            report = audit(p, EX)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["gates"][0]["status"], "FAIL")
        p = copy.deepcopy(self.mecha)
        p["generation_clip_limit"] = 6
        with self.assertRaisesRegex(ContractError, "cannot fit"):
            pack(p)

    def test_ref2va_detail_density_and_legacy_fixture_boundary(self):
        strict = copy.deepcopy(self.mecha)
        strict["prompt_detail_policy"] = {"ref2va_min_words": 2000, "ref2va_target_words": 2400}
        report = audit(strict, EX)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["gates"][7]["status"], "FAIL")
        legacy = copy.deepcopy(self.mecha)
        legacy["prompt_detail_policy"] = {"profile": "legacy_fixture"}
        self.assertEqual(audit(legacy, EX)["status"], "PASS")
        locked = copy.deepcopy(self.mecha)
        locked["segments"][0]["mode_lock"] = "T2VA"
        locked["segments"][0]["mode_selection_reason"] = "historical mode lock"
        self.assertEqual(audit(locked, EX)["status"], "FAIL")

    def test_optimize_freezes_time_action_camera_and_impact(self):
        replacement = copy.deepcopy(self.mecha["shots"][1]["vfx"])
        replacement["lighting"] = "A thin amber contact line reveals the steel bevel; matte armor stays dark under the fixed east lamp."
        patch = {"base_sha256": digest(self.mecha), "mode": "OPTIMIZE", "updates": [{"shot_id": self.mecha["shots"][1]["id"], "vfx": replacement}]}
        updated = optimize(self.mecha, patch, EX)
        check = copy.deepcopy(updated)
        check["shots"][1]["vfx"] = self.mecha["shots"][1]["vfx"]
        self.assertEqual(check, self.mecha)
        stale = copy.deepcopy(patch); stale["base_sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "stale_revision"):
            optimize(self.mecha, stale, EX)
        illegal = copy.deepcopy(patch); illegal["updates"][0]["camera"] = {}
        with self.assertRaisesRegex(ContractError, "only replace vfx"):
            optimize(self.mecha, illegal, EX)
        illegal = copy.deepcopy(patch); illegal["updates"][0]["vfx"]["phases"][0]["end"] += 1
        with self.assertRaisesRegex(ContractError, "freezes"):
            optimize(self.mecha, illegal, EX)

    def test_state_replay_and_archive_idempotency_recovery(self):
        p = copy.deepcopy(self.mecha)
        p["ledger"]["events"][0]["after"] = -1
        self.assertEqual(audit(p, EX)["gates"][9]["status"], "FAIL")
        p = copy.deepcopy(self.mecha)
        p["shots"][1]["state_in"]["characters"]["CHAR_FORGE"]["ammo"] = 9
        self.assertEqual(audit(p, EX)["gates"][9]["status"], "FAIL")
        p = copy.deepcopy(self.mecha)
        p["ledger"]["events"].append({"id": "EV_FALSE_HEAL", "frame": 250, "shot_id": p["shots"][1]["id"], "domain": "trauma", "target": "CHAR_FORGE", "before": None, "after": 2, "reason": "unsupported recovery"})
        p["shots"][1]["outcome_events"].append("EV_FALSE_HEAL")
        self.assertEqual(audit(p, EX)["gates"][9]["status"], "FAIL")
        with tempfile.TemporaryDirectory() as temp:
            saved = archive(self.mecha, EX, temp)
            before = {f.name: f.stat().st_mtime_ns for f in saved.iterdir() if f.is_file()}
            self.assertEqual(saved, archive(self.mecha, EX, temp))
            self.assertEqual(before, {f.name: f.stat().st_mtime_ns for f in saved.iterdir() if f.is_file()})
            manifest = read_data(saved / "manifest.json")
            self.assertEqual(digest(read_data(saved / "production.json")), digest(self.mecha))
            for ref in manifest["reference_resolver"].values():
                self.assertTrue((saved / ref).is_file())
            recovered = restore(saved, Path(temp) / "recovered")
            self.assertEqual(read_data(recovered)["ledger"], self.mecha["ledger"])
            self.assertEqual(len(compile_package(recovered, Path(temp) / "recompiled")), 1)
            (saved / "ledger.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "corrupt"):
                archive(self.mecha, EX, temp)

    def test_required_quality_evidence_cannot_be_empty_or_invalid(self):
        asset = read_data(ROOT / "templates/asset-stage.json")
        self.assertEqual(check_assets(asset, ROOT / "templates")["status"], "PASS")
        asset["asset_cards"][0]["seven_steps"].pop()
        with self.assertRaisesRegex(ContractError, "seven-step"):
            check_assets(asset, ROOT / "templates")
        cases = []
        p = copy.deepcopy(self.mecha); p["shots"][0]["camera"]["previs_id"] = "133"; cases.append((p, 1))
        p = copy.deepcopy(self.mecha); p["shots"][0]["visual"] += " 神作"; cases.append((p, 2))
        p = read_data(EX / "02-drama.production.json"); p["shots"][0]["performance"]["source_beat_id"] = "EX-WRONG"; cases.append((p, 3))
        p = copy.deepcopy(self.mecha); p["shots"][1]["combat"]["recoil"] = ""; cases.append((p, 4))
        p = copy.deepcopy(self.mecha); p["shots"][1]["vfx"]["phases"][1]["start"] += 1; cases.append((p, 5))
        p = read_data(EX / "03-colossal.production.json"); p["shots"][0]["scale_proofs"] = [p["shots"][0]["scale_proofs"][0]]; cases.append((p, 6))
        p = copy.deepcopy(self.mecha); p["segments"][0]["references"][0]["file"] = "missing.png"; cases.append((p, 7))
        p = copy.deepcopy(self.mecha); p["segments"][0]["panels"][0]["frame"] = 1000; cases.append((p, 7))
        p = copy.deepcopy(self.mecha); p["shots"][0]["audio"]["classification"] = "infrasound"; cases.append((p, 8))
        for p, gate in cases:
            with self.subTest(gate=gate):
                report = audit(p, EX)
                self.assertEqual(report["status"], "FAIL")
                self.assertEqual(report["gates"][gate]["status"], "FAIL")


    def test_ref2va_2900_word_ceiling_contract(self):
        from h3_contract import detail_policy, REF2VA_MAX_WORDS
        p = copy.deepcopy(self.mecha)
        policy = detail_policy(p, p["segments"][0])
        self.assertEqual(policy["profile"], "legacy_fixture")
        p["prompt_detail_policy"] = {"profile": "strict"}
        strict_policy = detail_policy(p, p["segments"][0])
        self.assertEqual(strict_policy["maximum_words"], REF2VA_MAX_WORDS)
        self.assertEqual(strict_policy["maximum_words"], 2900)
        self.assertLessEqual(strict_policy["minimum_words"], 2900)
        self.assertLessEqual(strict_policy["target_words"], 2900)


if __name__ == "__main__":
    unittest.main()
