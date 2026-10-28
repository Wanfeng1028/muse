#!/usr/bin/env python3
"""Read-only comparison of public Skill files and explicit local installations.

Reports differences, not version precedence. Never copies files or reads runtime
secrets. Symlinked Skill roots are supported; nested links are not followed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ALIASES = {
    'yichen-agent-memory': 'agent-memory',
    'yichen-volc-asr': 'volc-asr',
    'yichen-mac-wechat-dual-open': 'mac-wechat-dual-open',
    'yichen-wechat-local-vault': 'wechat-local-vault',
    'yichen-wecom-local-vault': 'wecom-local-vault',
    'yichen-wecom-operations': 'wecom-operations',
    'yichen-x-article-draft-uploader': 'x-article-draft-uploader',
}
EXCLUDED = {'work', '.git', '.venv', '.runtime', '.versions', '__pycache__',
            'node_modules', 'outputs', 'logs', 'private'}

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def safe_file(root: Path, relative: Path) -> Path | None:
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            return None
    return candidate if candidate.is_file() else None

def compare(repo: Path, roots: list[Path], plugin_root: Path | None = None) -> dict:
    raw = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z'])
    tracked = [Path(p) for p in raw.decode().split('\0') if p]
    entries = sorted(p.parent for p in tracked if p.name == 'SKILL.md')
    results = []
    for entry in entries:
        name = entry.name
        names = [name, ALIASES.get(name, name)]
        choices = [base / alias for base in roots for alias in dict.fromkeys(names)]
        if name == 'yichen-grok-consult':
            choices = [plugin_root / 'skills/grok-consult'] if plugin_root else []
        installed = next((p.resolve() for p in choices if (p / 'SKILL.md').is_file()), None)
        item = {'skill': name, 'status': 'not_found', 'identical': [],
                'changed': [], 'missing_locally': [], 'nested_links_skipped': []}
        if installed:
            for file in tracked:
                if entry not in file.parents:
                    continue
                rel = file.relative_to(entry)
                if any(part in EXCLUDED for part in rel.parts):
                    continue
                public = safe_file(repo, file)
                if public is None:
                    continue
                candidate = installed / rel
                local = safe_file(installed, rel)
                if local is None:
                    field = 'nested_links_skipped' if any(
                        (installed / Path(*rel.parts[:i])).is_symlink()
                        for i in range(1, len(rel.parts) + 1)
                    ) else 'missing_locally'
                else:
                    field = 'identical' if digest(public) == digest(local) else 'changed'
                item[field].append(str(rel))
            item['status'] = 'different' if any(item[k] for k in
                ('changed', 'missing_locally', 'nested_links_skipped')) else 'identical'
        results.append(item)
    return {'read_only': True, 'comparison': 'tracked public files versus installed files',
            'version_precedence_inferred': False, 'skills': results}

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--local-root', action='append', type=Path,
                   help='Repeat for installed Skill roots; first matching root wins')
    p.add_argument('--grok-plugin-root', type=Path,
                   help='Explicit installed Grok plugin root; no cache auto-discovery')
    a = p.parse_args()
    roots = a.local_root or [Path.home()/'.agents/skills', Path.home()/'.codex/skills']
    print(json.dumps(compare(a.repo.resolve(), [r.expanduser() for r in roots],
                             a.grok_plugin_root.expanduser() if a.grok_plugin_root else None),
                     ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
