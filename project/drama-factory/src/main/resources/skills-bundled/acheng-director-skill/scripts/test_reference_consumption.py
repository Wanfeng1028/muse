import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from compile_h3 import export_asset_prompt_bundle
from audit_storyboard_quality import audit, read_data
from post_hooks import check_assets
from style_anchor import style_policy_report


class ReferenceConsumptionAcceptance(unittest.TestCase):
    def _payload(self, approved=True):
        lock = {
            "anchor_asset_id": "STYLE_MOTHER", "anchor_version": "v1", "status": "approved" if approved else "planned",
            "medium": "2d", "preserve_scope": ["line weight"], "exclude_scope": ["identity"],
            "apply_to_kinds": ["character"],
        }
        plan = [{"id": "STYLE_MOTHER", "kind": "style", "version": "v1", "purpose": "style anchor", "depends_on": [], "status": "approved" if approved else "planned"},
                {"id": "CHAR_A", "kind": "character", "version": "v1", "purpose": "identity", "depends_on": ["STYLE_MOTHER"], "status": "planned"}]
        cards = [{"id": "STYLE_MOTHER", "asset_version": "v1", "asset_kind": "style", "recipe": "style", "mode": "GENERATE", "reference_policy": "none", "references": [], "prompt": "Create a neutral style sample."},
                 {"id": "CHAR_A", "asset_version": "v1", "asset_kind": "character", "character_name": "Ari", "state_label": "neutral_identity", "recipe": "portrait", "mode": "GENERATE", "reference_policy": "required", "references": [{"image": 1, "asset_id": "STYLE_MOTHER", "asset_version": "v1", "role": "style", "subject": "the rendering language", "preserve": "line weight", "exclude": "identity"}], "prompt": "Create the named character identity."}]
        for card in cards:
            card.update(target_skill="im2-clean-image", source_repository="im2-image-skills", generation_status="planned",
                        transaction={"change": "Compose the declared asset.", "preserve": "Preserve the declared reference scope.", "rebuild": "Rebuild the current framing."},
                        seven_steps=[{"step": i, "content": text} for i, text in enumerate([
                            "Show the declared subject only.", "Use the approved line language.", "Keep the framing readable.",
                            "Keep the lighting direction consistent.", "Leave the background uncluttered.", "Preserve surface response.", "Exclude labels and extra figures."], 1)])
        return {"style_policy": "required", "style_lock": lock, "asset_plan": plan, "asset_cards": cards}

    def test_h3_asset_export_expands_asset_id_to_real_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            base, out = Path(directory), Path(directory) / "out"
            image = base / "style.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nreal-style")
            payload = self._payload()
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            payload["style_lock"].update({"approved_file": "style.png", "approved_sha256": digest})
            payload["asset_plan"][0].update({"file": "style.png", "sha256": digest})
            entries = export_asset_prompt_bundle(payload, base, out)
            char = next(item for item in entries if item["asset_id"] == "CHAR_A")
            text = (out / char["prompt_file"]).read_text(encoding="utf-8")
            self.assertEqual(char["status"], "PROMPT_READY")
            self.assertIn("Reference image 1 supplies style guidance", text)
            self.assertNotIn("DRAFT — asset prompt reference contract failed", text)

    def test_unapproved_dependency_is_visible_draft_not_reference_free_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            base, out = Path(directory), Path(directory) / "out"
            payload = self._payload(approved=False)
            entries = export_asset_prompt_bundle(payload, base, out)
            char = next(item for item in entries if item["asset_id"] == "CHAR_A")
            text = (out / char["prompt_file"]).read_text(encoding="utf-8")
            self.assertEqual(char["status"], "PLANNED")
            self.assertTrue(char["missing_references"])
            self.assertTrue(text.startswith("DRAFT —"))
            self.assertIn("Reference image 1 supplies style guidance", text)

    def test_multi_asset_missing_style_policy_is_blocked(self):
        payload = self._payload()
        payload.pop("style_policy")
        report = style_policy_report(payload, Path("."), strict=True)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(style_policy_report(payload, Path("."), strict=True)["status"], "BLOCKED")
        pending = self._payload(False)
        pending.pop('style_policy')
        with self.assertRaisesRegex(ValueError, 'must declare style_policy'):
            check_assets(pending, Path('.'), allow_missing=True)

    def test_animation_term_selection_requires_evidence_and_reaches_h3(self):
        production = read_data(Path(__file__).resolve().parents[1] / "examples/02-drama.production.json")
        segment = production["segments"][0]
        segment["animation_term_ids"] = ["acting.eye_trace"]
        segment["animation_term_evidence"] = [{
            "term_id": "acting.eye_trace", "term": "eye trace", "time_window": "0.50-2.00 seconds",
            "observable_fact": "the eyes travel from the key to the partner's eyes and pause before the reply",
            "camera_or_layout": "the medium close frame keeps both eye lines and the key visible",
            "sound_or_qa": "verify the pause lands before the spoken response and the eyeline does not jump",
        }]
        self.assertEqual(audit(production, Path(__file__).resolve().parents[1])["status"], "PASS")
        segment["animation_term_evidence"] = []
        self.assertEqual(audit(production, Path(__file__).resolve().parents[1])["gates"][7]["status"], "FAIL")

    def test_style_scope_and_approved_source_cannot_diverge(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            image = base / 'style.png'
            image.write_bytes(b'\x89PNG\r\n\x1a\nstyle-test-only')
            sha = hashlib.sha256(image.read_bytes()).hexdigest()
            p = self._payload()
            p['style_lock'].update(approved_file='style.png', approved_sha256=sha)
            p['asset_plan'][0].update(file='style.png', sha256=sha)
            self.assertEqual(style_policy_report(p, base)['status'], 'READY')
            for field, value, message in [('apply_to_kinds', ['scene'], 'omits'), ('status', 'planned', 'status mismatch')]:
                q = copy.deepcopy(p); q['style_lock'][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                    style_policy_report(q, base)
            other = base / 'other.png'; other.write_bytes(image.read_bytes())
            p['asset_plan'][0]['file'] = 'other.png'
            with self.assertRaisesRegex(ValueError, 'same file'):
                style_policy_report(p, base)

    def test_keyframe_must_consume_target_scene_character_and_prop_assets(self):
        from asset_plan import check_asset_plan
        root = Path(__file__).resolve().parents[1]
        p = read_data(root / 'examples/04-serial.production.json')
        report = check_asset_plan(p, root / 'examples')
        self.assertIn('ART_KEYFRAME_01', report['keyframe_coverage'])
        for missing in ('ART_MEI', 'ART_ARCHIVE', 'ART_STATIONERY'):
            q = copy.deepcopy(p)
            node = next(n for n in q['asset_plan'] if n['id'] == 'ART_KEYFRAME_01')
            card = next(c for c in q['asset_cards'] if c['id'] == node['id'])
            node['depends_on'].remove(missing)
            card['references'] = [r for r in card['references'] if r['asset_id'] != missing]
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'keyframe missing target-shot'):
                check_asset_plan(q, root / 'examples')

    def test_asset_source_file_hash_kind_and_state_conflicts_are_rejected(self):
        from asset_plan import resolve_card
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'style.png').write_bytes(b'\x89PNG\r\n\x1a\nstyle-test-only')
            p = self._payload()
            p['asset_plan'][0].update(file='style.png', sha256=hashlib.sha256((base / 'style.png').read_bytes()).hexdigest(), state_version='neutral-v1')
            for field, value, message in [('file', 'other.png', 'file conflicts'), ('sha256', '0'*64, 'SHA-256 conflicts'), ('state_version', 'wrong-v2', 'state_version conflict')]:
                card = copy.deepcopy(p['asset_cards'][1]); card['references'][0][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                    resolve_card(card, p, base, True)
            p['asset_cards'][1]['asset_kind'] = 'scene'
            with self.assertRaisesRegex(ValueError, 'kind conflict'):
                resolve_card(p['asset_cards'][1], p, base)

    def test_audio_cannot_supply_visual_subject_and_riff_types_are_distinct(self):
        from reference_bindings import inspect_media, resolve_bindings
        from test_reference_delivery import fixture
        from compile_h3 import compile_package
        from h3_delivery import validate_package
        import shutil
        import wave
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            p, source = fixture(base)
            segment = p['segments'][0]
            audio = base / 'voice.wav'
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, 8000, 8000, 'NONE', 'not compressed'))
                stream.writeframes(b'\0\0' * 8000)
            root = Path(__file__).resolve().parents[1]
            shutil.copyfile(root / 'camera-moves-whitebox-132/01_dolly_in.mp4', base / 'camera.mp4')
            for label, filename, entity, role, definition, retention, exclude in [
                ('<Audio 1>', 'voice.wav', 'silence-source', 'room-tone floor reference', '<Audio 1> is a silent test recording used only to specify the noise floor; it provides no speaker identity.', '<Audio 1>: reference - reference its silence level only.', 'speech, music and speaker identity'),
                ('<Video 1>', 'camera.mp4', 'camera-source', 'camera-motion reference', '<Video 1> is a whitebox camera-move example, used only for a forward travel direction.', '<Video 1>: attribute_transfer - transfer forward camera travel only.', 'whitebox geometry, people, materials and scene identity')]:
                digest = inspect_media(base / filename, label)
                segment['references'].append({'label': label, 'file': filename, 'entity_id': entity, 'asset_version': 'test-v1',
                    'sha256': digest, 'approval': {'status': 'approved', 'sha256': digest, 'evidence': 'Offline test media; no film-quality approval.'},
                    'role': role, 'definition': definition, 'retention': retention, 'preserve': role, 'exclude': exclude, 'shot_ids': segment['shot_ids']})
                for shot in p['shots']:
                    shot['reference_requirements'].append({'entity_id': entity, 'asset_version': 'test-v1', 'purpose': role})
            segment['summary'] = segment['summary'].replace('[reference generation]', '[reference generation + audio reference]')
            source.write_text(json.dumps(p), encoding='utf-8')
            entry = compile_package(source, base / 'multimodal')[0]
            self.assertEqual([r['label'] for r in entry['references']], ['<Picture 1>', '<Audio 1>', '<Video 1>'])
            self.assertEqual(validate_package(base / 'multimodal', p, base)['status'], 'PASS')
            for ref in entry['references']:
                self.assertEqual(hashlib.sha256((base / 'multimodal' / ref['file']).read_bytes()).hexdigest(), ref['sha256'])
                self.assertIn(ref['label'], (base / 'multimodal' / entry['file']).read_text(encoding='utf-8'))
            sha = inspect_media(audio, '<Audio 1>')
            segment['references'] = segment['references'][:1]
            ref = segment['references'][0]
            ref.update(label='<Audio 1>', file='voice.wav', sha256=sha, approval={'status': 'approved', 'sha256': sha, 'evidence': 'test metadata only'})
            segment['subjects'] = [{'label': '<Subject 1>', 'entity_id': 'blocking-board', 'definition': '<Subject 1> is a visible robot sourced from <Audio 1>.', 'shot_ids': segment['shot_ids'], 'retention': '<Subject 1> appears in [Shot 1] and [Shot 2]: fully_preserved.'}]
            self.assertTrue(any('visual Subject' in e for e in resolve_bindings(p, segment, base)['issues']))
            (base / 'wrong.avi').write_bytes(audio.read_bytes())
            with self.assertRaisesRegex(ValueError, 'signature invalid'):
                inspect_media(base / 'wrong.avi', '<Video 1>')

    def test_rehashed_asset_body_cannot_drop_the_source_reference_instructions(self):
        from asset_delivery import asset_upload_card, file_hash, validate_asset_entries
        from test_guided_reference_delivery import fixture
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); p = fixture(base); out = base / 'out'
            entries = export_asset_prompt_bundle(p, base, out)
            entry = entries[0]
            (out / entry['prompt_file']).write_text('Create a generic person in an arbitrary room.\n', encoding='utf-8')
            entry['prompt_sha256'] = file_hash(out / entry['prompt_file'])
            (out / entry['upload_card']).write_text(asset_upload_card(entry), encoding='utf-8')
            entry['upload_card_sha256'] = file_hash(out / entry['upload_card'])
            with self.assertRaisesRegex(ValueError, 'no longer consumes'):
                validate_asset_entries(out, entries, production=p, source_base=base)


if __name__ == "__main__":
    unittest.main()
