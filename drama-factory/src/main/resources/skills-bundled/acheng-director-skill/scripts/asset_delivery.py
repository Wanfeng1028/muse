"""Portable image-prompt inputs, shared by image and H3 asset exports."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from contract_core import content_hash, need
from reference_bindings import inspect_media


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy_image_references(card, missing, source_base, output):
    missing_slots = {item['image'] for item in missing}
    references = []
    for ref in card.get('references', []):
        if ref['image'] in missing_slots:
            continue
        source = (Path(source_base) / ref['file']).resolve()
        label = f"<Picture {ref['image']}>"
        sha = inspect_media(source, label, ref.get('sha256'))
        relative = f"references/{sha}{source.suffix.lower()}"
        destination = Path(output) / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)
        inspect_media(destination, label, sha)
        references.append({**ref, 'source_file': ref['file'], 'file': relative, 'sha256': sha,
                           'binding_status': 'BOUND_LOCAL', 'platform_status': 'NOT_UPLOADED'})
    return references


def missing_details(card, missing):
    originals = {r['image']: r for r in card.get('references', [])}
    return [{**originals.get(m['image'], {}), **m} for m in missing]


def asset_upload_card(entry):
    def cell(value):
        return str(value if value is not None else '未指定').replace('|', '\\|').replace('\n', ' ')
    refs = entry.get('references', [])
    missing = entry.get('missing_reference_details', [])
    lines = [f"### {cell(entry.get('display_name') or entry.get('name') or entry['asset_id'])} · 资产图上传卡", '',
             f"状态：{entry['status']} · NOT_UPLOADED · visual_status=UNVERIFIED", '',
             f"生成模式：{cell(entry.get('mode'))} · 资产类型：{cell(entry.get('asset_kind'))} · 状态版本：{cell(entry.get('state_label'))} / {cell(entry.get('state_version'))}", '',
             f"[完整提示词/草案](<{entry['prompt_file']}>) · SHA-256：{entry['prompt_sha256']}", '',
             '本卡用于生成这一个资产；H3 视频请求的参考图和编号另见对应 Segment 上传卡。', '']
    if not entry.get('reference_count'):
        lines.extend(['本资产无需上传参考图；按完整正文制作，生成后仍需批准。', ''])
    else:
        lines.extend(['逐项上传实际图片；不上传 .image.txt，缺失槽位不重排编号。', '',
                      '| 槽位 | 实际图片/缺项 | 用途/对象 | 版本 | 必须保留 | 禁止继承 |',
                      '|---|---|---|---|---|---|'])
        bound = {r['image']: r for r in refs}
        absent = {r['image']: r for r in missing}
        for number in range(1, entry['reference_count'] + 1):
            row = bound.get(number) or absent.get(number, {})
            media = f"[{cell(Path(row['file']).name)}](<{row['file']}>)" if number in bound else '待提供：' + cell(row.get('asset_id') or row.get('file')) + '；' + cell(row.get('reason') or '生成并批准后重新编译')
            lines.append(f"| {number} | {media} | {cell(row.get('role'))} / {cell(row.get('subject'))} | {cell(row.get('asset_version') or row.get('version'))} | {cell(row.get('preserve'))} | {cell(row.get('exclude'))} |")
        lines.append('')
    if entry.get('render_error'):
        lines.extend(['正文合同阻塞：' + cell(entry['render_error']), ''])
    ready = entry['status'] in {'PROMPT_READY', 'ready-to-submit-not-generated'}
    if not ready:
        next_step = '先补齐缺项或修复正文合同，再重新导出到新目录；当前草案不可提交。'
    elif entry.get('reference_count'):
        next_step = '核对模式和本卡槽位，在实际入口上传图片并复制完整提示词；生成后记录真实文件、版本和人工批准。'
    else:
        next_step = '核对生成模式并复制完整提示词，无需上传参考图；生成后记录真实文件、版本和人工批准。'
    lines.extend(['下一步：' + next_step, ''])
    return '\n'.join(lines)


def finish_asset_entry(entry, card, payload, output, upload_name):
    entry.update(input_revision=content_hash(payload), resolved_card_sha256=content_hash(card),
                 reference_count=len(card.get('references', [])), reference_policy=card.get('reference_policy'),
                 mode=card.get('mode'), asset_kind=card.get('asset_kind'),
                 state_label=card.get('state_label'), state_version=card.get('state_version'),
                 asset_version=card.get('asset_version'),
                 prompt_sha256=file_hash(Path(output) / entry['prompt_file']), upload_card=upload_name,
                 platform_status='NOT_UPLOADED', visual_status='UNVERIFIED')
    upload = Path(output) / upload_name
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_text(asset_upload_card(entry), encoding='utf-8')
    entry['upload_card_sha256'] = file_hash(upload)
    return entry


def validate_asset_entries(root, entries, *, production=None, source_base=None):
    root = Path(root).resolve()
    def local(name):
        path = (root / name).resolve()
        need(root in path.parents, 'asset delivery path escapes bundle')
        return path
    need(len({e['asset_id'] for e in entries}) == len(entries), 'duplicate asset delivery')
    cards = {c['id']: c for c in (production or {}).get('asset_cards', [])}
    if production is not None:
        need({e['asset_id'] for e in entries} == set(cards), 'asset delivery missing or disconnected from source cards')
        if entries and any(e['status'] in {'PROMPT_READY', 'ready-to-submit-not-generated'} for e in entries):
            from post_hooks import check_assets
            check_assets(production, source_base, allow_missing=True)
    results = []
    for entry in entries:
        need(entry.get('platform_status') == 'NOT_UPLOADED' and entry.get('visual_status') == 'UNVERIFIED', 'asset export cannot claim upload or generated quality')
        need(file_hash(local(entry['prompt_file'])) == entry['prompt_sha256'], 'asset prompt changed after compilation')
        need(file_hash(local(entry['upload_card'])) == entry['upload_card_sha256'], 'asset upload card changed')
        need(local(entry['upload_card']).read_text(encoding='utf-8') == asset_upload_card(entry), 'asset upload mapping differs from manifest')
        refs, missing = entry['references'], entry['missing_reference_details']
        numbers = [r['image'] for r in refs + missing]
        need(all(type(n) is int for n in numbers) and sorted(numbers) == list(range(1, entry['reference_count'] + 1)), 'asset reference slots missing or duplicated')
        need(entry['reference_policy'] in {'none', 'required'} and (entry['reference_policy'] == 'required') == bool(numbers), 'asset reference policy differs from slots')
        ready = entry['status'] in {'PROMPT_READY', 'ready-to-submit-not-generated'}
        need(not ready or not missing and not entry.get('render_error'), 'unresolved asset references cannot be ready')
        for ref in refs:
            need(ref.get('binding_status') == 'BOUND_LOCAL' and ref.get('platform_status') == 'NOT_UPLOADED', 'asset reference state inconsistent')
            inspect_media(local(ref['file']), f"<Picture {ref['image']}>", ref['sha256'])
        if production is not None:
            from asset_plan import resolve_card
            need(entry['input_revision'] == content_hash(production), 'asset source revision changed')
            need(entry['asset_id'] in cards, 'asset source card missing')
            card, absent = resolve_card(cards[entry['asset_id']], production, source_base, True)
            need(entry['resolved_card_sha256'] == content_hash(card), 'asset source/version changed')
            if ready:
                from prompt_delivery import render_asset_prompt
                render_card = dict(card)
                if not render_card.get('prompt') and len(cards) == 1:
                    render_card['prompt'] = production.get('asset_prompt', '')
                need(local(entry['prompt_file']).read_text(encoding='utf-8') == render_asset_prompt(render_card, production.get('prompt_bindings'), production.get('style_lock')), 'asset prompt no longer consumes its source/reference contract')
            for key in ('mode', 'asset_kind', 'state_label', 'state_version', 'asset_version', 'reference_policy'):
                need(entry.get(key) == card.get(key), 'asset card metadata differs from source: ' + key)
            need(missing == missing_details(card, absent), 'asset missing-reference mapping changed')
            originals = {r['image']: r for r in card.get('references', [])}
            for ref in refs:
                restored = {k: v for k, v in ref.items() if k not in {'source_file', 'file', 'binding_status', 'platform_status'}}
                restored['file'] = ref['source_file']
                need(restored == originals[ref['image']], 'asset source/reference mapping changed')
        results.append({'asset_id': entry['asset_id'], 'status': 'PASS' if ready else 'DRAFT_NOT_SUBMITTABLE',
                        'prompt_sha256': entry['prompt_sha256'], 'reference_count': entry['reference_count']})
    return {'status': 'PASS' if all(r['status'] == 'PASS' for r in results) else 'DRAFT_NOT_SUBMITTABLE',
            'assets': results, 'visual_status': 'UNVERIFIED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--production', type=Path)
    args = parser.parse_args()
    try:
        index = json.loads((args.package / 'index.json').read_text(encoding='utf-8'))
        need(index.get('asset_reference_contract') == '1.0', 'asset reference contract missing; recompile with current compiler')
        production = json.loads(args.production.read_text(encoding='utf-8')) if args.production else None
        entries = index['assets'] if 'assets' in index else index['asset_prompts']
        result = validate_asset_entries(args.package, entries, production=production,
                                        source_base=args.production.parent if args.production else None)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result = {'status': 'FAIL', 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'PASS' else 2 if result['status'] == 'DRAFT_NOT_SUBMITTABLE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
