#!/usr/bin/env python3
"""Compile H3 and per-Segment upload cards from one verified binding snapshot."""
import argparse
import copy
import json
from pathlib import Path
import re
import hashlib
import shutil
import sys

from audit_storyboard_quality import ContractError, audit, compile_segment, read_data
from contract_core import content_hash
from h3_contract import detail_policy, english_word_count, speech_map
from render_delivery_view import render_video
from h3_final_format import file_contract, validate_h3_file
from reference_bindings import resolve_bindings
from h3_delivery import upload_card, validate_package
from prompt_delivery import render_asset_prompt
from asset_plan import resolve_card
from style_anchor import style_policy_report
from asset_delivery import copy_image_references, finish_asset_entry, missing_details


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_asset_name(asset_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(asset_id or "")):
        raise ContractError("asset id must be a safe filename")
    return str(asset_id)


def export_asset_prompt_bundle(production, source_base, output):
    """Export copy-ready image prompts without treating them as generated media."""
    cards = production.get("asset_cards", [])
    if not cards:
        return []
    style_report = style_policy_report(production, source_base, strict=True)
    if style_report.get("status") == "BLOCKED":
        raise ContractError(style_report["reason"])
    from post_hooks import check_assets
    asset_contract_error = None
    try:
        check_assets(production, source_base, allow_missing=True)
    except (ValueError, KeyError, TypeError) as exc:
        asset_contract_error = str(exc)
    prompt_dir = output / "asset_prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for authored_card in cards:
        # Resolve asset_id dependencies exactly like compile_assets.py. The H3
        # package must not export a second, reference-free version of a prompt.
        card, unresolved = resolve_card(authored_card, production, source_base, True)
        asset_id = _safe_asset_name(card.get("id"))
        refs = card.get("references", [])
        missing = list(unresolved)
        prompt = card.get("prompt")
        if not prompt and len(cards) == 1:
            prompt = production.get("asset_prompt")
        prompt = prompt or ""
        render_error = asset_contract_error
        if prompt:
            try:
                prompt = render_asset_prompt({**card, "prompt": prompt}, production.get("prompt_bindings"), production.get("style_lock"))
            except (ValueError, KeyError) as exc:
                # Keep authored text for recovery, but make the failed consumer
                # contract explicit instead of exporting a reference-free prompt.
                render_error = str(exc)
                prompt = "DRAFT — asset prompt reference contract failed: " + render_error + "\n\n" + str(prompt).rstrip() + "\n"
        else:
            prompt = "DRAFT — this asset has no standalone prompt field in the production source.\n"
        status = "PLANNED" if missing or render_error or not (card.get("prompt") or len(cards) == 1 and production.get("asset_prompt")) else "PROMPT_READY"
        filename = asset_id + (".draft.txt" if status == "PLANNED" else ".image.txt")
        if status == "PLANNED" and not prompt.startswith("DRAFT"):
            prompt = "DRAFT — required references or standalone prompt contract is unresolved.\n\n" + prompt
        (prompt_dir / filename).write_text(prompt, encoding="utf-8")
        entry = {
            "asset_id": asset_id,
            "name": " · ".join(str(v) for v in (card.get("character_name") or card.get("name") or asset_id,
                                                   card.get("state_label"), card.get("state_version"), card.get("asset_version")) if v),
            "prompt_file": "asset_prompts/" + filename,
            "status": status,
            "reference_count": len(refs),
            "references": copy_image_references(card, missing, source_base, output),
            "missing_reference_details": missing_details(card, missing),
            "missing_references": [
                f"Reference image {ref.get('image', '?')}: {ref.get('asset_id') or ref.get('file') or '未指定文件'}"
                for ref in missing
            ],
            "render_error": render_error,
            "purpose": card.get("purpose") or card.get("transaction", {}).get("change") or "按完整提示词生成",
        }
        entries.append(finish_asset_entry(entry, card, production, output, asset_id + ".asset-upload.md"))
    return entries


def compile_package(source, output, *, draft=False, execution_mode="autonomous_file_batch", segment_id=None):
    source, output = Path(source), Path(output)
    production = read_data(source)
    style_report = style_policy_report(production, source.parent, strict=True)
    if style_report.get("status") == "BLOCKED" and production.get("asset_cards"):
        raise ContractError(style_report["reason"])
    revision = content_hash(production)
    if execution_mode not in {"autonomous_file_batch", "interactive_segment"}:
        raise ContractError("invalid execution_mode")
    if execution_mode == "interactive_segment" and not segment_id:
        raise ContractError("interactive_segment requires --segment; one complete Segment per turn")
    selected = [s for s in production["segments"] if not segment_id or s["id"] == segment_id]
    if not selected:
        raise ContractError("unknown Segment")
    if output.exists():
        raise ContractError(f"Output already exists; choose a new revision directory: {output}")
    report = audit(production, source.parent)
    package_failed = [g for g in report["gates"] if g["status"] == "FAIL"]
    prepared = []
    for seg in selected:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", seg["id"]):
            raise ContractError("segment id must be a safe filename")
        snapshot = resolve_bindings(production, seg, source.parent)
        segment_report = audit(production, source.parent, h3_segment_ids={seg['id']}) if any(g['gate'] == 'h3_schema' for g in package_failed) else report
        failed = [g for g in segment_report['gates'] if g['status'] == 'FAIL']
        if failed and not draft and not (snapshot["issues"] and all(g["gate"] == "h3_schema" for g in failed)):
            raise ContractError(json.dumps(report, ensure_ascii=False))
        blockers = list(snapshot["issues"])
        blockers.extend(g["gate"] + ": " + "; ".join(g["errors"]) for g in failed)
        resolved_seg = copy.deepcopy(seg)
        resolved_seg["references"] = [copy.deepcopy(r) for r in snapshot["references"] if r["label"].startswith("<")]
        resolved_seg["subjects"] = snapshot["subjects"]
        try:
            text = compile_segment(production, resolved_seg, draft=bool(blockers))
        except ValueError as exc:
            if not draft:
                raise
            blockers.append(str(exc))
            text = compile_segment(production, resolved_seg, draft=True)
        prepared.append((seg, resolved_seg, snapshot, text, blockers))
    output.mkdir(parents=True)
    asset_prompts = export_asset_prompt_bundle(production, source.parent, output)
    index = []
    for seg, resolved_seg, snapshot, text, blockers in prepared:
        for ref in snapshot["references"]:
            if ref.get("binding_status") != "BOUND_LOCAL":
                continue
            original = (source.parent / ref["file"]).resolve()
            relative = "references/" + ref["sha256"] + original.suffix.lower()
            destination = output / relative
            destination.parent.mkdir(exist_ok=True)
            if not destination.exists():
                shutil.copyfile(original, destination)
            ref["source_file"], ref["file"] = ref["file"], relative
        snapshot.pop("binding_sha256")
        snapshot["binding_sha256"] = content_hash(snapshot)
        name = seg["id"] + (".h3.draft.txt" if blockers else ".h3.txt")
        if blockers:
            text = "DRAFT — planned references/contract unresolved; do not submit. Creative content retained below.\n\n" + text
        (output / name).write_text(text, encoding="utf-8")
        sha = hashlib.sha256((output / name).read_bytes()).hexdigest()
        policy = detail_policy(production, seg)
        body_name = "detailed_description" if seg["mode"] == "Ref2VA" else "integrated_multimodal_description"
        body = text.split(body_name + ":\n", 1)[1].split("\n\noverall_soundscape:", 1)[0]
        entry = {"segment_id": seg["id"], "mode": seg["mode"], "file": name,
                 "generation_clip_duration": seg["generation_clip_duration"],
                 "start_frame": seg["start_frame"], "end_frame": seg["end_frame"],
                 "summary": seg.get("summary", ""),
                 "speaker_map": speech_map(production, seg), "input_revision": revision,
                 "reference_labels": [r["label"] for r in snapshot["references"]] + [s["label"] for s in snapshot["subjects"]],
                 "format_pass": "NOT_ACCEPTED" if blockers else "PASSED", "sha256": sha,
                 "status": "DRAFT_MISSING_REFERENCES" if snapshot["issues"] else ("DRAFT_CONTRACT_FAILED" if blockers else "READY_TO_UPLOAD"),
                 "accepted": not bool(blockers), "blockers": list(dict.fromkeys(blockers)),
                 "platform_status": "NOT_UPLOADED", "binding_snapshot": snapshot,
                 "h3_detail_policy": policy, "detailed_description_english_words": english_word_count(body) if seg["mode"] == "Ref2VA" else None,
                 "execution_capabilities": "UNVERIFIED: confirm actual platform mode, duration and slots",
                 "visual_status": "UNVERIFIED", "references": snapshot["references"],
                 "upload_card": seg["id"] + ".upload.md", "delivery_manifest": name + ".delivery.json"}
        if not blockers:
            contract = file_contract(production, resolved_seg, snapshot["references"])
            contract.update(input_revision=revision, binding_sha256=snapshot["binding_sha256"], expected_prompt_sha256=sha)
            entry["format_contract"] = name + ".check.json"
            entry["format_receipt"] = name + ".acceptance.json"
            write_json(output / entry["format_contract"], contract)
            receipt = validate_h3_file(output / name, contract, output, allow_legacy_fixture=snapshot["legacy_fixture"])
            write_json(output / entry["format_receipt"], receipt)
        (output / entry["upload_card"]).write_text(upload_card(entry), encoding="utf-8")
        entry["upload_card_sha256"] = hashlib.sha256((output / entry["upload_card"]).read_bytes()).hexdigest()
        write_json(output / entry["delivery_manifest"], entry)
        index.append(entry)
    payload = {"version": "4.3.6", "status": "draft-dependencies-pending" if any(not e["accepted"] for e in index) else "compiled-not-generated",
               "production_sha256": revision, "execution_mode": execution_mode, "asset_reference_contract": "1.0",
               "display_context": {
                   **{k: production.get(k) for k in ("project_id", "production_total_duration", "fps_num", "fps_den")},
                   "story_summary": (production.get("story") or {}).get("synopsis") or production.get("creative_summary"),
                   "story_arc_scope": (production.get("story") or {}).get("arc_scope"),
               },
               "asset_prompts": asset_prompts, "segments": index}
    write_json(output / "index.json", payload)
    write_json(output / "audit.json", report)
    (output / "UPLOAD.md").write_text("# H3 逐段上传操作卡\n\n" + "\n".join(upload_card(e) for e in index), encoding="utf-8")
    (output / "DELIVERY_VIEW.md").write_text(render_video(production, output, payload), encoding="utf-8")
    (output / "CHAT_DELIVERY.md").write_text(render_video(production, output, payload, compact=True), encoding="utf-8")
    write_json(output / "delivery.acceptance.json", validate_package(output, production, source.parent))
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--execution-mode", choices=("autonomous_file_batch", "interactive_segment"), default="autonomous_file_batch")
    parser.add_argument("--segment")
    args = parser.parse_args()
    try:
        index = compile_package(args.production, args.out, draft=args.draft, execution_mode=args.execution_mode, segment_id=args.segment)
        print(f"Wrote {len(index)} Segment bundles to {args.out}; {sum(e['accepted'] for e in index)} ready to upload; no model calls made.")
        return 0 if all(e["accepted"] for e in index) else 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
