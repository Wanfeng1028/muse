"""Acceptance for portable image inputs and bounded professional guidance."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from asset_plan import resolve_card
from compile_assets import compile_assets
from compile_h3 import export_asset_prompt_bundle
from director_dispatch import plan_dispatch, registry
from orchestrator_plan import plan

ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aY9sAAAAASUVORK5CYII=")


def fixture(base):
    # Test pixels only; no claim of generated identity or visual acceptance.
    for name in ('identity.png', 'scene.png'):
        (base / name).write_bytes(PNG)
    card = {
        'id': 'KEYFRAME_OPENING', 'name': 'Opening frame', 'asset_kind': 'keyframe',
        'target_skill': 'im2-clean-image', 'source_repository': 'im2-image-skills',
        'recipe': 'portrait', 'mode': 'GENERATE', 'generation_status': 'planned',
        'reference_policy': 'required',
        'transaction': {'change': 'Compose the opening view.', 'preserve': 'Preserve approved identity and room layout.', 'rebuild': 'Rebuild the current framing and contact shadows.'},
        'seven_steps': [{'step': i, 'content': text} for i, text in enumerate([
            'A woman stands by the room doorway.', 'Use the approved ink medium.',
            'A medium view shows her open right hand.', 'Window light falls on the matte sleeve.',
            'Keep the doorway readable behind her.', 'Show the visible sleeve folds only.',
            'Avoid extra hands and panel borders.'], 1)],
        'prompt': 'Create a single opening frame showing a woman beside the room doorway, with her open right hand visible.',
        'references': [
            {'image': 1, 'file': 'identity.png', 'role': 'identity', 'subject': 'the woman', 'preserve': 'face and costume', 'exclude': 'source pose and background'},
            {'image': 2, 'file': 'scene.png', 'role': 'scene', 'subject': 'the room', 'preserve': 'doorway and wall layout', 'exclude': 'source people and camera position'}],
    }
    return {'asset_cards': [card]}


class GuidedReferenceAcceptance(unittest.TestCase):
    def test_h3_embedded_asset_prompts_include_portable_inputs_and_detect_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = fixture(base)
            out = base / 'h3-assets'
            entries = export_asset_prompt_bundle(payload, base, out)
            entry = entries[0]
            self.assertIn('references', entry)
            self.assertEqual([r['image'] for r in entry['references']], [1, 2])
            self.assertEqual(entry['status'], 'PROMPT_READY')
            self.assertTrue((out / entry['upload_card']).is_file())
            from asset_delivery import validate_asset_entries
            self.assertEqual(validate_asset_entries(out, entries, production=payload, source_base=base)['status'], 'PASS')
            with self.assertRaisesRegex(ValueError, 'missing or disconnected'):
                validate_asset_entries(out, [], production=payload, source_base=base)
            ref = out / entry['references'][0]['file']
            self.assertEqual(ref.read_bytes(), PNG)
            ref.write_bytes(PNG + b'changed')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                validate_asset_entries(out, entries)

    def test_image_compiler_uses_same_numbered_reference_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = fixture(base)
            source = base / 'production.json'
            source.write_text(json.dumps(payload), encoding='utf-8')
            out = base / 'images'
            entry = compile_assets(source, out)[0]
            text = (out / entry['prompt_file']).read_text(encoding='utf-8')
            upload = (out / entry['upload_card']).read_text(encoding='utf-8')
            self.assertIn('Reference image 1 supplies identity', text)
            self.assertIn('Reference image 2 supplies scene', text)
            for ref in entry['references']:
                self.assertIn(ref['file'], upload)
                self.assertIn(ref['preserve'], upload)
                self.assertIn(ref['exclude'], upload)
            from asset_delivery import validate_asset_entries
            self.assertEqual(validate_asset_entries(out, [entry], production=payload, source_base=base)['status'], 'PASS')
            card = payload['asset_cards'][0]
            card['reference_policy'], card['references'] = 'none', []
            card['transaction']['preserve'] = 'Maintain the original character description and room layout.'
            card['seven_steps'][1]['content'] = 'Use black ink on warm paper.'
            source.write_text(json.dumps(payload), encoding='utf-8')
            no_ref_dir = base / 'text-only'
            no_ref = compile_assets(source, no_ref_dir)[0]
            instructions = (no_ref_dir / no_ref['upload_card']).read_text(encoding='utf-8')
            self.assertIn('无需上传参考图', instructions)
            self.assertNotIn('在实际入口上传图片', instructions)

    def test_missing_dependency_keeps_full_draft_and_original_slot_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = fixture(base)
            (base / 'identity.png').unlink()
            out = base / 'draft'
            entry = export_asset_prompt_bundle(payload, base, out)[0]
            self.assertEqual(entry['status'], 'PLANNED')
            self.assertEqual([r['image'] for r in entry['references']], [2])
            self.assertEqual(entry['missing_reference_details'][0]['image'], 1)
            body = (out / entry['prompt_file']).read_text(encoding='utf-8')
            self.assertTrue(body.startswith('DRAFT'))
            self.assertIn(payload['asset_cards'][0]['prompt'], body)
            upload = (out / entry['upload_card']).read_text(encoding='utf-8')
            self.assertIn('待提供', upload)
            self.assertNotIn('无需上传', upload)
            from asset_delivery import validate_asset_entries
            self.assertEqual(validate_asset_entries(out, [entry])['status'], 'DRAFT_NOT_SUBMITTABLE')

    def test_prompt_file_and_changed_approved_bytes_cannot_be_image_references(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            payload = fixture(base)
            card = payload['asset_cards'][0]
            prompt = base / 'identity.image.txt'
            prompt.write_text('Generate the real identity image later.', encoding='utf-8')
            card['references'][0]['file'] = prompt.name
            with self.assertRaisesRegex(ValueError, 'media'):
                resolve_card(card, payload, base)
            resolved, missing = resolve_card(card, payload, base, True)
            self.assertEqual(missing[0]['image'], 1)
            self.assertIn('media', missing[0]['reason'])
            card['references'][0].update(file='identity.png', asset_id='IDENTITY', asset_version='v1')
            payload['asset_plan'] = [{'id': 'IDENTITY', 'status': 'approved', 'version': 'v1', 'file': 'identity.png', 'sha256': hashlib.sha256(PNG).hexdigest()}]
            (base / 'identity.png').write_bytes(PNG + b'changed')
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                resolve_card(card, payload, base)

    def test_dispatch_routes_current_module_guides_without_new_production_owners(self):
        modules = registry()
        self.assertEqual(set(modules), {'story', 'shots', 'performance', 'assets', 'effects', 'model', 'continuity'})
        for mid, module in modules.items():
            self.assertIn(f'references/decisions/{mid}.md', module['reads'])
        dispatch = plan_dispatch({}, {'request_id': 'assets-guidance', 'stage': 'assets'})
        self.assertEqual([s['module'] for s in dispatch['steps']], ['assets'])
        reads = dispatch['steps'][0]['required_reads']
        self.assertIn('references/decisions/assets.md', reads)
        self.assertNotIn('references/decisions/story.md', reads)
        workflow = plan({'request_id': 'assets-workflow', 'intent': 'assets', 'execution_mode': '1'}, {})
        for node in workflow['nodes']:
            self.assertIn(f"references/decisions/{node['owner']}.md", node['required_reads'])


if __name__ == '__main__':
    unittest.main()
