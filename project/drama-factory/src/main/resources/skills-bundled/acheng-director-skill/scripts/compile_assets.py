#!/usr/bin/env python3
"""Export standalone GPT Image prompts, copied references and upload instructions."""
import argparse
import json
from pathlib import Path
import re
import sys

from audit_storyboard_quality import ContractError, read_data
from post_hooks import check_assets
from prompt_delivery import render_asset_prompt
from asset_plan import resolve_card
from render_delivery_view import render_assets
from asset_delivery import copy_image_references, finish_asset_entry, missing_details, validate_asset_entries


def asset_display_name(card):
    """Return the only user-facing label used by the names-only asset index."""
    if card.get("asset_kind") == "character":
        base = " · ".join([str(card.get("character_name") or card.get("name") or card["id"]).strip(),
                           str(card.get("state_label") or "neutral_identity").strip(),
                           "四视图角色身份基准"])
    else:
        base = str(card.get("name") or card["id"]).strip()
    versions = []
    for key in ("state_version", "asset_version"):
        value = card.get(key)
        if value is not None and str(value).strip():
            versions.append(str(value).strip())
    return " · ".join([base, *versions])


def compile_assets(source, output, allow_missing=False):
    source, output = Path(source), Path(output)
    payload = read_data(source)
    report = check_assets(payload, source.parent, allow_missing)
    if output.exists():
        raise ContractError(f"Output already exists; choose a new revision directory: {output}")
    prepared = []
    cards = {c["id"]: c for c in payload["asset_cards"]}
    order = report["asset_plan"]["production_order"] if report.get("asset_plan") else list(cards)
    for aid in order:
        if aid not in cards:
            continue
        card, missing = resolve_card(cards[aid], payload, source.parent, allow_missing)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", card["id"]):
            raise ContractError("asset id must be a safe filename")
        prepared.append((card, render_asset_prompt(card, payload.get("prompt_bindings"), payload.get("style_lock")), missing))
    output.mkdir(parents=True)
    index, guide = [], ["# 资产图上传与使用清单", "", "默认展示请打开 ASSET_NAMES.txt；它只包含资产名称和可选状态/版本。完整提示词、参考图上传顺序和缺图处理仍记录在本清单与 index.json。", ""]
    for card, prompt, missing in prepared:
        name = card["id"] + (".draft.txt" if missing else ".image.txt")
        prefix = "DRAFT — required reference images are not yet supplied. Do not submit until the upload manifest is resolved.\n\n" if missing else ""
        (output / name).write_text(prefix + prompt, encoding="utf-8")
        refs = copy_image_references(card, missing, source.parent, output)
        display_name = asset_display_name(card)
        entry = {"asset_id": card["id"], "display_name": display_name, "prompt_file": name, "mode": card["mode"],
                      "asset_kind": card.get("asset_kind"), "character_name": card.get("character_name"),
                      "state_label": card.get("state_label"), "view_layout": card.get("view_layout"),
                      "status": "draft-missing-references" if missing else "ready-to-submit-not-generated", "missing_references": missing,
                      "reference_policy": card["reference_policy"], "references": refs,
                      "missing_reference_details": missing_details(card, missing),
                      "target": "GPT Image 2 / 2.5 natural-language prompt; select the actual available model in your entry point"}
        index.append(finish_asset_entry(entry, card, payload, output, card["id"] + ".upload.md"))
        guide.extend([f"## {display_name}", "", f"完整提示词文件：[{name}]({name})", "", f"逐槽位上传卡：[{entry['upload_card']}]({entry['upload_card']})", "",
                      "提交状态：草案；按下面缺图清单先制作并批准依赖资产，然后重新导出。" if missing else "参考图：不需要，可纯文字生成。" if not refs else "参考图：必须上传以下全部文件，顺序与正文 Reference image 编号一致。", ""])
        for item in missing:
            guide.extend([f"- 缺少 Reference image {item['image']}：{item.get('asset_id', item.get('file'))}；版本 {item.get('version', '由输入确定')}；用途 {item['role']}。", ""])
        for ref in refs:
            guide.extend([f"{ref['image']}. [参考图 {ref['image']}]({ref['file']}) — {ref['role']}；{ref['subject']}；保留：{ref['preserve']}；不继承：{ref['exclude']}", ""])
    style_pending = report.get("style_policy", {}).get("status") == "STYLE_ANCHOR_PENDING_APPROVAL"
    package_status = "style-anchor-pending-approval" if style_pending else "draft-dependencies-pending" if report["missing_references"] else "ready-to-submit-not-generated"
    (output / "index.json").write_text(json.dumps({"asset_reference_contract": "1.0", "status": package_status, "input_sha256": report["input_sha256"], "assets": index, "asset_plan": report.get("asset_plan"), "style_policy": report.get("style_policy"), "style_lock": report.get("style_lock")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "UPLOAD.md").write_text("\n".join(guide), encoding="utf-8")
    (output / "ASSET_NAMES.txt").write_text("\n".join(item["display_name"] for item in index) + "\n", encoding="utf-8")
    (output / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "DELIVERY_VIEW.md").write_text(render_assets(payload, output, {"assets": index}), encoding="utf-8")
    acceptance = validate_asset_entries(output, index, production=payload, source_base=source.parent)
    (output / "delivery.acceptance.json").write_text(json.dumps(acceptance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assets", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--draft", action="store_true", help="Export clearly marked drafts for planned references; never claims they are ready")
    args = parser.parse_args()
    try:
        result = compile_assets(args.assets, args.out, args.draft)
        print(f"Compiled {len(result)} standalone image prompts to {args.out}; no model calls made.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
