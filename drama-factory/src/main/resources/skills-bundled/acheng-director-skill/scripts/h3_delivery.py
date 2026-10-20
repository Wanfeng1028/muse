"""One binding snapshot feeds standalone upload cards, manifest and joint gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from contract_core import content_hash, need
from reference_bindings import inspect_media


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cell(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return str(value if value is not None else "未绑定").replace("|", "\\|").replace("\n", " ")


def status(entry):
    return entry.get("status", "UNVERIFIED")


def upload_card(entry):
    """This exact render is checked on disk, not merely mentioned by a host."""
    snapshot = entry["binding_snapshot"]
    rows = snapshot["references"]
    ready = status(entry) == "READY_TO_UPLOAD"
    lines = [f"### {entry['segment_id']} · {entry['mode']} · {entry['generation_clip_duration']} 秒", "",
             f"提交状态：{status(entry)} · 本地绑定不等于平台已上传 · visual_status=UNVERIFIED", "",
             f"[完整正文/草案]({entry['file']}) · [独立上传卡]({entry['upload_card']})", "",
             f"绑定版本：`{snapshot['binding_sha256']}` · 正文 SHA-256：`{entry['sha256']}`", ""]
    if not rows and entry["mode"] == "T2VA" and not snapshot["issues"]:
        lines.extend(["参考图上传助手：本段无需上传参考图；已明确选择 T2VA。跨段身份效果仍需生成后检查。", ""])
    elif not rows:
        lines.extend(["待素材与参考策略：本段不是纯文字免参考。先根据角色、场景、道具、状态与关键帧需求确定真实素材及版本；当前不能提交。", ""])
    else:
        lines.extend(["参考图上传助手：每段是独立请求；按顺序上传实际媒体，不上传 `.image.txt` 或本卡。", "",
                      "| 顺序/标签 | 实际上传文件/状态 | 资产与版本 | 内容对象/说话人 | 用途与生效范围 | 必须保留 | 禁止继承 |",
                      "|---|---|---|---|---|---|---|"])
        for row in rows:
            bound = row.get("binding_status") == "BOUND_LOCAL"
            media = f"[{cell(Path(row.get('source_file') or row['file']).name)}](<{row['file']}>)" if bound else "待生成/待绑定：" + cell(row.get("file") or row.get("asset_id"))
            objects = [s for s in snapshot["subjects"] if row["label"] in s.get("source_labels", [])]
            names = "; ".join(s["label"] + " = " + cell(s.get("entity_id")) + " (" + (s.get('speaker_id') or "非说话人") + ")" for s in objects)
            if not names:
                names = cell(row.get("entity_id"))
            ranges = '; '.join(f"{r['shot_id']} · 全局帧 {r['start_frame']}–{r['end_frame']}（末帧不含）" for r in row.get('active_ranges', [])) or ', '.join(row.get('shot_ids', []))
            if row.get('anchor_shot_ids'):
                ranges += '；构图锚点仅 ' + ', '.join(row['anchor_shot_ids'])
            lines.append(f"| {row.get('upload_order', '待定')} / `{cell(row['label'])}` | {media}; {cell(row.get('binding_status'))}; {cell(row.get('platform_status'))} | {cell(row.get('asset_id') or row.get('entity_id'))} / {cell(row.get('asset_version'))} | {cell(names)} | {cell(row.get('role'))}; {cell(ranges)} | {cell(row.get('preserve'))} | {cell(row.get('exclude'))} |")
        kinds = {row["label"].split()[0].lstrip("<") for row in rows if row.get("label", "").startswith("<")}
        lines.extend(["", "视频参考：" + ("见表" if "Video" in kinds else "未声明；不虚构 Video 标签") + "。音频参考：" + ("见表" if "Audio" in kinds else "未声明；不虚构 Audio 标签") + "。", ""])
    if snapshot["subjects"]:
        lines.append("Subject 是内容对象，不是新增上传槽位；一份素材可承载多个对象，同一对象可用多个来源。")
    for issue in entry.get("blockers", []):
        lines.append("- 阻塞：" + cell(issue))
    lines.extend(["", "下一步：" + ("依次上传本卡真实媒体，在实际入口核对模式、时长、分类编号和素材版本，再粘贴完整正文。未完成入口核对前不宣称可直接提交。" if ready else "补齐上述素材、版本或合同缺项后重新编译到新目录；保留创作全文，不改名冒充正式稿，不切换 T2VA。"),
                  "平台上传：当前卡不证明云端已有素材。上传确认必须另附绑定本段、正文与素材哈希的入口回执。", ""])
    return "\n".join(lines)


def validate_segment_bundle(root, entry, *, production=None, source_base=None):
    from h3_final_format import validate_h3_file
    root = Path(root).resolve()

    def local(name):
        path = (root / name).resolve()
        need(root in path.parents, "delivery path escapes bundle")
        return path

    snapshot = entry["binding_snapshot"]
    claimed = snapshot["binding_sha256"]
    need(content_hash({k: v for k, v in snapshot.items() if k != "binding_sha256"}) == claimed, "binding snapshot changed")
    need(entry["segment_id"] == snapshot["segment_id"] and entry["mode"] == snapshot["mode"], "manifest/binding identity mismatch")
    need(entry["input_revision"] == snapshot["input_revision"], "manifest/binding revision mismatch")
    need(entry.get('platform_status') == 'NOT_UPLOADED' and all(r.get('platform_status') == 'NOT_UPLOADED' for r in snapshot['references']), 'local binding cannot claim platform upload; use a separate evidence receipt')
    need(entry.get("references") == snapshot["references"], "manifest references diverged from binding snapshot")
    need(file_hash(local(entry["file"])) == entry["sha256"], "H3 changed after compilation")
    need(local(entry["upload_card"]).read_text(encoding="utf-8") == upload_card(entry), "upload card differs from binding snapshot")
    need(file_hash(local(entry["upload_card"])) == entry["upload_card_sha256"], "upload card hash changed")
    if production is not None:
        from reference_bindings import resolve_bindings
        need(content_hash(production) == snapshot["input_revision"], "stale production revision")
        segment = next(s for s in production["segments"] if s["id"] == entry["segment_id"])
        current = resolve_bindings(production, segment, source_base)
        # Export paths are content-addressed; compare the declared source paths.
        actual = json.loads(json.dumps(snapshot))
        actual.pop("binding_sha256")
        for row in actual["references"]:
            if "source_file" in row:
                row["file"] = row.pop("source_file")
        need(actual == {k: v for k, v in current.items() if k != "binding_sha256"}, "source binding/version/object changed")
        if status(entry) == "READY_TO_UPLOAD":
            from audit_storyboard_quality import compile_segment
            resolved_segment = {**segment, "references": [r for r in current["references"] if r["label"].startswith("<")], "subjects": current["subjects"]}
            need(local(entry["file"]).read_text(encoding="utf-8") == compile_segment(production, resolved_segment), "H3 body no longer consumes its source/reference contract")
    ready = status(entry) == "READY_TO_UPLOAD"
    if ready:
        need(entry.get('accepted') is True and entry.get('format_pass') == 'PASSED', 'ready state inconsistent')
        need(not snapshot["issues"] and not entry.get("blockers"), "blocked binding cannot be ready")
        contract = json.loads(local(entry["format_contract"]).read_text(encoding="utf-8"))
        need(contract.get("binding_sha256") == claimed, "format contract uses another binding")
        need(contract.get("references") == snapshot["references"], "format references differ from manifest")
        need(contract.get("input_revision") == snapshot["input_revision"], "stale format contract revision")
        need(contract.get("expected_prompt_sha256") == entry["sha256"], "format contract body hash mismatch")
        need(contract.get('mode') == entry['mode'] and contract.get('duration_seconds') == float(entry['generation_clip_duration']), 'format mode/duration differs from upload card')
        receipt = validate_h3_file(local(entry["file"]), contract, root, allow_legacy_fixture=snapshot["legacy_fixture"])
        stored = json.loads(local(entry["format_receipt"]).read_text(encoding="utf-8"))
        need(receipt == stored, "format receipt stale")
        for row in snapshot["references"]:
            need(row["binding_status"] == "BOUND_LOCAL", "planned media cannot be ready")
            inspect_media(local(row["file"]), row["label"], row["sha256"])
    else:
        need(entry["format_pass"] != "PASSED" and entry.get("accepted") is False, "draft must not be accepted")
    return {"joint_status": "PASSED" if ready else "DRAFT_VERIFIED_NOT_SUBMITTABLE",
            "segment_id": entry["segment_id"], "input_revision": entry["input_revision"],
            "sha256": entry["sha256"], "binding_sha256": claimed,
            "upload_card_sha256": entry["upload_card_sha256"], "visual_status": "UNVERIFIED"}


def validate_package(root, production=None, source_base=None):
    root = Path(root)
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    entries = index["segments"]
    need(len({e["segment_id"] for e in entries}) == len(entries), "duplicate Segment in index")
    for entry in entries:
        need(entry["input_revision"] == index["production_sha256"], "index revision mismatch")
        sidecar = json.loads((root / entry["delivery_manifest"]).read_text(encoding="utf-8"))
        need(sidecar == entry, "per-Segment manifest differs from index")
    results = [validate_segment_bundle(root, e, production=production, source_base=source_base) for e in entries]
    expected = "# H3 逐段上传操作卡\n\n" + "\n".join(upload_card(e) for e in entries)
    need((root / "UPLOAD.md").read_text(encoding="utf-8") == expected, "aggregate upload view differs from cards")
    from render_delivery_view import render_video
    need((root / "DELIVERY_VIEW.md").read_text(encoding="utf-8") == render_video(production or {}, root, index), "delivery view differs from accepted bindings")
    need((root / "CHAT_DELIVERY.md").read_text(encoding="utf-8") == render_video(production or {}, root, index, compact=True), "chat delivery missing or divergent")
    result = {"status": "PASS" if all(x["joint_status"] == "PASSED" for x in results) else "DRAFT_NOT_SUBMITTABLE", "segments": results, "visual_status": "UNVERIFIED"}
    if index.get("asset_reference_contract") == "1.0":
        from asset_delivery import validate_asset_entries
        result["asset_prompt_delivery"] = validate_asset_entries(root, index.get("asset_prompts", []), production=production, source_base=source_base)
    return result


def validate_upload_receipt(root, entry, receipt):
    """Verify recorded evidence; does not log in to a platform or infer upload."""
    validate_segment_bundle(root, entry)
    need(status(entry) == "READY_TO_UPLOAD", "draft cannot be uploaded as accepted H3")
    for key, expected in (("segment_id", entry["segment_id"]), ("input_revision", entry["input_revision"]), ("prompt_sha256", entry["sha256"]), ("binding_sha256", entry["binding_snapshot"]["binding_sha256"])):
        need(receipt.get(key) == expected, "upload receipt stale: " + key)
    need(receipt.get("platform") and receipt.get("request_id") and receipt.get("confirmed_by"), "platform/request/confirmer evidence required")
    expected = [{"label": r["label"], "sha256": r["sha256"]} for r in entry["references"]]
    need(receipt.get("uploads") == expected, "platform slot/hash mapping differs")
    evidence = receipt.get("evidence", {})
    need(evidence.get("file") and evidence.get("sha256") and file_hash(Path(root) / evidence["file"]) == evidence["sha256"], "upload evidence file/hash missing")
    return {"platform_status": "UPLOAD_CONFIRMED_BY_RECORDED_EVIDENCE", "platform": receipt["platform"], "request_id": receipt["request_id"], "confirmed_by": receipt["confirmed_by"], "visual_status": "UNVERIFIED", "scope": "recorded receipt consistency; no live platform inspection"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--production", type=Path)
    parser.add_argument("--upload-receipt", type=Path)
    args = parser.parse_args()
    try:
        production = json.loads(args.production.read_text(encoding="utf-8")) if args.production else None
        result = validate_package(args.package, production, args.production.parent if args.production else None)
        if args.upload_receipt:
            receipt = json.loads(args.upload_receipt.read_text(encoding="utf-8"))
            index = json.loads((args.package / "index.json").read_text(encoding="utf-8"))
            entry = next(e for e in index["segments"] if e["segment_id"] == receipt["segment_id"])
            result["upload"] = validate_upload_receipt(args.package, entry, receipt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "PASS" else 2
    except (ValueError, OSError, KeyError, TypeError, StopIteration) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
