"""Acceptance of bounded guidance, provenance and existing prompt consumption."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from director_library import ROOT, load_libraries, select_questions, select_visuals, validate_libraries


class DirectorLibraryAcceptance(unittest.TestCase):
    def test_catalog_routes_sources_and_generated_views(self):
        result = validate_libraries()
        self.assertEqual((result['inquiries'], result['visual_entries'], result['surface_entries']), (36, 31, 7))
        self.assertFalse(result['production_mutated'])
        self.assertEqual(result['artistic_quality'], 'UNVERIFIED')

    def test_questions_are_bounded_and_cli_reports_bad_ids(self):
        self.assertEqual(select_questions(module='performance')['status'], 'INDEX_ONLY')
        selected = select_questions(module='performance', case='P1')
        self.assertEqual([q['id'] for q in selected['cards']], ['Q05', 'Q06'])
        self.assertEqual(selected['remaining_ids'], ['Q07'])
        self.assertEqual(select_questions(module='shots', case='C99')['status'], 'NO_MATCH')
        command = [sys.executable, str(ROOT/'scripts/director_library.py'), 'questions', '--question', 'Q99']
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)['status'], 'ERROR')

    def test_material_adapters_do_not_silently_change_medium(self):
        ink = select_visuals(medium='ink', surface='silk')
        self.assertEqual(ink['cards'][0]['id'], 'MAT05')
        self.assertIn('留白', ink['cards'][0]['appearance'])
        self.assertEqual(ink['reference_media'], [])
        self.assertFalse(ink['production_mutated'])
        cel = select_visuals(medium='anime_3d', surface='silk')['cards'][0]
        self.assertIn('简洁亮带', cel['appearance'])
        self.assertNotEqual(cel['appearance'], ink['cards'][0]['appearance'])
        with self.assertRaisesRegex(ValueError, 'incompatible'):
            select_visuals(ids=['OPT01'], medium='ink')
        self.assertEqual(select_visuals(medium='ink', layer='optics')['status'], 'NO_MATCH')

    def test_source_tampering_is_a_real_failure(self):
        inquiries, visuals = load_libraries()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            files = ['data/director-inquiries.json', 'data/visual-style-materials.json', 'data/module-registry.json',
                     inquiries['source_file'], visuals['source_file']]
            for name in files:
                dst = target/name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/name, dst)
            source = target/inquiries['source_file']
            source.write_bytes(source.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'Library source changed'):
                validate_libraries(target)

    def test_selected_material_reaches_asset_and_h3_files(self):
        from prompt_delivery import render_asset_prompt
        from audit_storyboard_quality import compile_segment
        from reference_bindings import resolve_bindings
        source = ROOT/'examples/02-drama.production.json'
        source_bytes = source.read_bytes()
        payload = json.loads(source_bytes)
        material = select_visuals(medium='live_action', surface='dry_cloth')['cards'][0]
        # Host adoption supplies existing scene facts; the retrieval tool writes no facts.
        statement = ("Lu Chuan's existing gray woven work jacket remains dry under the established east-window light. "
                     + material['appearance'])
        card = payload['asset_cards'][0]
        card['seven_steps'][3]['content'] += ' ' + statement
        card['prompt'] += ' ' + statement
        payload['shots'][0]['visual'] += ' ' + statement
        segment = copy.deepcopy(payload['segments'][0])
        bindings = resolve_bindings(payload, segment, source.parent)
        segment['references'] = [r for r in bindings['references'] if r['label'].startswith('<')]
        segment['subjects'] = bindings['subjects']
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp)/'adoption.image.txt'
            video = Path(tmp)/'adoption.h3.txt'
            image.write_text(render_asset_prompt(card, payload.get('prompt_bindings'), payload.get('style_lock')), encoding='utf-8')
            video.write_text(compile_segment(payload, segment), encoding='utf-8')
            self.assertIn(statement, image.read_text(encoding='utf-8'))
            self.assertIn(statement, video.read_text(encoding='utf-8'))
            self.assertNotIn('MAT04', video.read_text(encoding='utf-8'))
        self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == '__main__':
    unittest.main()
