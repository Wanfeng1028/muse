"""Check install metadata, local links, and the public distribution boundary."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SKILL_FOLDERS = ('agents', 'assets', 'references', 'scripts')


class DistributionTests(unittest.TestCase):
    def skill_files(self):
        yield ROOT / 'SKILL.md'
        for folder in SKILL_FOLDERS:
            yield from (
                path for path in (ROOT / folder).rglob('*')
                if path.is_file() and '__pycache__' not in path.parts
            )

    @unittest.skipUnless(importlib.util.find_spec('yaml'), 'Metadata check needs PyYAML')
    def test_skill_and_interface_metadata_load_as_yaml(self):
        import yaml

        content = (ROOT / 'SKILL.md').read_text(encoding='utf-8')
        self.assertTrue(content.startswith('---\n'))
        metadata = yaml.safe_load(content.split('---', 2)[1])
        self.assertEqual(metadata['name'], 'remotion-shotflow')
        self.assertTrue(metadata['description'].strip())
        interface = yaml.safe_load((ROOT / 'agents/openai.yaml').read_text(encoding='utf-8'))
        self.assertIn('$' + metadata['name'], interface['interface']['default_prompt'])

    def test_relative_markdown_links_resolve_within_repository(self):
        documents = [*(ROOT.glob('README*.md')), ROOT / 'SKILL.md', ROOT / 'CONTRIBUTING.md',
                     ROOT / 'THIRD_PARTY_NOTICES.md', *(ROOT / 'references').glob('*.md'),
                     *(ROOT / 'assets').glob('*.md')]
        for document in documents:
            links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', document.read_text(encoding='utf-8'))
            for link in links:
                parsed = urlsplit(link)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                with self.subTest(document=document.name, link=link):
                    target = (document.parent / unquote(parsed.path)).resolve()
                    self.assertTrue(target.is_relative_to(ROOT))
                    self.assertTrue(target.is_file(), f'Missing local reference: {target.name}')

    def test_skill_contains_only_portable_text_and_original_example_data(self):
        for path in self.skill_files():
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertFalse(path.is_symlink())
                self.assertIn(path.suffix, {'.md', '.py', '.yaml', '.json'})
                text = path.read_text(encoding='utf-8')
                self.assertIsNone(re.search(r'/(?:Users|home)/[^\s/]+/', text))
                if path.suffix == '.json':
                    json.loads(text)


if __name__ == '__main__':
    unittest.main()
