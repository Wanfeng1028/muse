"""Render a human-readable delivery view without changing production truth.

The machine-facing exports remain the source of truth. This module only adds a
director-friendly index so a user can understand status, upload order and copy
zones before opening the raw prompt files.
"""
import argparse
import json
from fractions import Fraction
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def esc(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def fps(production):
    return Fraction(production.get("fps_num", 24), production.get("fps_den", 1))


def seconds(frames, production):
    return f"{float(Fraction(frames, 1) / fps(production)):.3f}s"


def duration(seg, production):
    if seg.get("generation_clip_duration") is not None:
        return f"{float(seg['generation_clip_duration']):.2f}s"
    return seconds(seg["end_frame"] - seg["start_frame"], production)


def asset_name(card, entry=None):
    if entry and entry.get("display_name"):
        return entry["display_name"]
    if card.get("asset_kind") == "character":
        return " · ".join((card.get("character_name") or card.get("name") or card["id"],
                           card.get("state_label") or "neutral_identity", "四视图角色身份基准"))
    return card.get("name") or card["id"]


def _prompt_details(title, prompt_file, prompt_text):
    # Keep the complete model-facing text visible by default. The human view
    # adds context around it but never hides or replaces the prompt body.
    lines = [f"#### 复制：{esc(title)}（完整正文）", "", f"完整文件：[下载/打开 {prompt_file}]({prompt_file})", "", "```text", prompt_text.rstrip(), "```", ""]
    return lines


def _asset_reference_guide(card, entry):
    """Return an ordered, user-facing upload guide for one image asset."""
    originals = {ref.get("image"): ref for ref in card.get("references", [])}
    copied = {ref.get("image"): ref for ref in entry.get("references", [])}
    missing = {ref.get("image"): ref for ref in entry.get("missing_references", [])}
    numbers = sorted(set(originals) | set(copied) | set(missing))
    if not numbers:
        return ["参考图上传助手：无需上传参考图；可直接复制完整提示词生成。", ""]
    lines = ["参考图上传助手：严格按下表顺序上传；文件名不能替代实际文件，说明文字不要粘进图像提示词。", "", "| 槽位 | 实际上传文件 | 用途 | 必须保留 | 禁止继承 |", "|---:|---|---|---|---|"]
    for number in numbers:
        source = originals.get(number, {})
        actual = copied.get(number)
        absent = missing.get(number)
        if actual and actual.get("file"):
            file_text = f"[{actual['file']}]({actual['file']})"
        elif absent:
            file_text = f"待提供：`{absent.get('file', source.get('file', '未指定文件'))}`"
        else:
            file_text = f"待提供：`{source.get('file', '未指定文件')}`"
        lines.append(f"| {number} | {file_text} | {esc(source.get('role', (actual or {}).get('role', '未说明用途')))} | {esc(source.get('preserve', '按完整提示词中的身份/结构描述保持'))} | {esc(source.get('exclude', '不要把参考图中未声明的姿态、光线、文字或背景带入'))} |")
    lines.extend(["", "上传顺序：先上传槽位 1，再按 2、3……递增；上传完成后确认提示词中的 `Reference image N` 与槽位一一对应。"])
    if missing:
        lines.append("当前阻塞：上表带“待提供”的槽位尚未具备真实文件；先生成并批准该依赖资产，再重新导出本资产提示词。")
    else:
        lines.append("提交前检查：所有文件可打开、顺序正确、只继承表中“必须保留”内容，并把姿态/构图/光线按本次正文重建。")
    lines.append("")
    return lines


def _video_reference_guide(production, seg, entry):
    """Return a slot-by-slot H3 reference upload guide."""
    if entry.get("binding_snapshot"):
        from h3_delivery import upload_card
        return upload_card(entry).splitlines()
    originals = {ref.get("label"): ref for ref in seg.get("references", [])}
    refs = entry.get("references", [])
    if not refs:
        if seg.get("mode") == "T2VA" and not originals:
            return ["参考图上传助手：本段无需上传参考图；已明确选择 T2VA。", ""]
        return ["参考图上传助手：待素材，引用模式尚未绑定真实媒体，不能提交；请先完成逐段参考规划。", ""]
    lines = ["参考图上传助手：先上传下表素材，再粘贴本段 H3 正文；槽位标签、顺序和用途不能互换。", "", "| 顺序 | H3 槽位 | 实际上传文件 | 用途 | 必须保留 | 禁止继承 |", "|---:|---|---|---|---|---|"]
    for number, ref in enumerate(refs, 1):
        original = originals.get(ref.get("label"), {})
        preserve = original.get("retention", "正文定义的身份、空间或构图范围")
        exclude = original.get("exclude", "参考图未声明的风格、文字、网格、姿态或光线")
        lines.append(f"| {number} | `{esc(ref.get('label'))}` | [{ref.get('file', '未指定文件')}]({ref.get('file', '')}) | {esc(ref.get('role'))} | {esc(preserve)} | {esc(exclude)} |")
    lines.extend(["", "上传顺序：按 1、2、3……逐槽上传；不要把段落 A 的素材错传到段落 B。上传后检查 H3 正文中的标签与界面槽位一致。", "提交前检查：模式与时长一致；素材已上传；只保留表中指定范围；未上传的素材不能被提示词假定存在。", ""])
    return lines


def _asset_prompt_section(production, output, index, compact=False):
    """Render the actionable image-prompt catalog before video segments."""
    entries = index.get("asset_prompts", [])
    if not entries:
        return ["## 资产目录与提示词", "", "本次生产未登记独立资产图提示词；请以各 Segment 的参考状态为准。", ""]
    lines = ["## 资产目录与提示词", "", "以下是可直接交给画布 Agent 的独立资产图提示词。提示词文件是生成指令，不是已经生成的图片；状态为 PLANNED 时仍需先补齐真实参考素材。", "",
             "| 资产 | 状态 | 用途 | 参考依赖 | 提示词文件 |", "|---|---|---|---|---|"]
    for entry in entries:
        missing = ", ".join(entry.get("missing_references", [])) or (f"{entry.get('reference_count', 0)} 项" if entry.get("reference_count") else "无")
        lines.append(f"| {esc(entry.get('name') or entry['asset_id'])} (`{entry['asset_id']}`) | {esc(entry.get('status'))} | {esc(entry.get('purpose'))} | {esc(missing)} | [{entry['prompt_file']}]({entry['prompt_file']}) |")
    lines.extend(["", "### 可复制资产提示词", ""])
    for entry in entries:
        path = output / entry["prompt_file"]
        lines.extend([f"#### {esc(entry.get('name') or entry['asset_id'])} · {entry.get('status')}", "", f"完整文件：[{entry['prompt_file']}]({entry['prompt_file']})"])
        if entry.get("upload_card"):
            from asset_delivery import asset_upload_card
            lines.extend(["", f"独立上传卡：[{entry['upload_card']}]({entry['upload_card']})", "", asset_upload_card(entry)])
        if path.is_file() and not (compact and index.get("asset_reference_contract")):
            lines.extend(["", "```text", path.read_text(encoding="utf-8").rstrip(), "```"])
        lines.append("")
    return lines


def _creative_summary(production, entries):
    story = production.get("story", {}) or {}
    lines = ["## 创作摘要", ""]
    synopsis = story.get("synopsis") or production.get("creative_summary")
    lines.append(str(synopsis).strip() if synopsis else "本包未登记一句话梗概；请以 Segment 正文与镜头地图为准。")
    arc = story.get("arc_scope")
    if arc:
        lines.extend(["", f"叙事范围：{arc}"])
    summaries = [e.get("summary") for e in entries if e.get("summary")]
    if summaries:
        lines.extend(["", "段落推进："])
        for e in entries:
            if e.get("summary"):
                lines.append(f"- {e['segment_id']}：{e['summary']}")
    lines.append("")
    return lines


def _execution_section(production, entries, index):
    blockers = []
    for asset in index.get("asset_prompts", []):
        if index.get("asset_reference_contract") and asset.get("status") == "PLANNED":
            blockers.append(f"资产 {asset['asset_id']}：先按独立上传卡补齐参考素材或正文合同；不可提交草案")
    for entry in entries:
        blockers.extend(f"{entry['segment_id']}：{item}" for item in entry.get("blockers", []))
        for ref in entry.get("references", []):
            if ref.get("binding_status") != "BOUND_LOCAL":
                blockers.append(f"{entry['segment_id']}：{ref.get('label')} 待真实素材绑定")
    lines = ["## 执行顺序与阻塞项", "", "1. 先按上方资产目录把提示词逐项交给画布 Agent；资产生成完成后记录真实文件、版本和哈希。", "2. 打开每个 Segment 的上传卡，只上传该段表内的真实媒体，并在入口核对模式、时长和槽位编号。", "3. 打开对应 H3 文件，复制完整正文提交；`CHAT_DELIVERY.md` 不替代 H3 正文文件。", "4. 平台上传后另行保存入口回执；本地 `READY_TO_UPLOAD` 不等于平台已上传，`visual_status=UNVERIFIED` 不得升级。", ""]
    if index.get("asset_reference_contract"):
        lines[2] = "1. 待制作资产先按自己的上传卡上传实际参考图、提交完整资产提示词；生成后登记真实文件、版本、哈希并批准，再重新编译下游。已经批准且未变化的资产直接复用。"
    if blockers:
        lines.extend(["当前阻塞：", *[f"- {item}" for item in dict.fromkeys(blockers)], ""])
    else:
        lines.extend(["当前阻塞：无机器识别阻塞；仍需实际平台上传回执和生成后人工画面验收。", ""])
    return lines


def render_assets(production, output, index):
    cards = {card["id"]: card for card in production.get("asset_cards", [])}
    entries = index.get("assets", [])
    ready = sum(entry.get("status") == "ready-to-submit-not-generated" for entry in entries)
    missing = len(entries) - ready
    lines = ["# 资产交付总览", "", "这是给人阅读的导航页；模型只接收各资产 `.image.txt` 或 `.draft.txt` 的完整正文。", "",
             "## 总控台", "", f"资产数量：{len(entries)}", f"可提交提示词：{ready}", f"待参考图草案：{missing}",
             "状态：已编译但未调用图像模型。真实身份一致性、画面质量和文字伪影仍需生图后人工检查。", "", "## 资产目录", "",
             "| 资产 | 类型 | 状态 | 参考图 | 用途 |", "|---|---|---|---|---|"]
    for entry in entries:
        card = cards.get(entry["asset_id"], {})
        refs = entry.get("references", [])
        ref_state = "无需参考图" if not refs and not entry.get("missing_references") else f"{len(refs) + len(entry.get('missing_references', []))} 张"
        lines.append(f"| {esc(asset_name(card, entry))} | {esc(card.get('asset_kind') or 'asset')} | {esc(entry.get('status'))} | {ref_state} | {esc(card.get('purpose') or card.get('transaction', {}).get('change') or '按完整提示词生成')} |")
    lines.extend(["", "## 逐项交付", ""])
    for entry in entries:
        card = cards.get(entry["asset_id"], {})
        title = asset_name(card, entry)
        lines.extend([f"### {title}", "", f"用途：{esc(card.get('purpose') or card.get('transaction', {}).get('change') or '按提示词生成')}" ,
                      f"生成模式：{esc(entry.get('mode') or card.get('mode'))}",
                      f"提交状态：{esc(entry.get('status'))}"])
        if card.get("asset_kind") == "character":
            views = card.get("view_layout", {}).get("views", [])
            lines.append("视图：正面全身、背面全身、侧面全身、正脸头肩近景（四视图角色身份基准）" if views else "视图：角色身份基准")
        if entry.get("missing_references"):
            lines.append("阻塞：" + "; ".join(f"缺少图{item.get('image')}（{item.get('role', '未说明用途')}）" for item in entry["missing_references"]))
        elif entry.get("references"):
            lines.append("上传：" + "; ".join(f"图{ref['image']} {ref.get('label', ref.get('file', '未命名素材'))}（{ref['role']}）" for ref in entry["references"]))
        else:
            if entry.get("status") in {"draft-missing-references", "DRAFT_MISSING_REFERENCES"} or card.get("reference_policy") == "required":
                lines.append("上传：参考策略已声明但真实素材尚未绑定；请先补齐依赖，不能按纯文字图生成。")
            else:
                lines.append("上传：无需参考图；这是单项独立资产，按完整正文生成。")
        lines.append("")
        lines.extend(_asset_reference_guide(card, entry))
        prompt_path = output / entry["prompt_file"]
        if prompt_path.is_file():
            lines.extend(_prompt_details(title, entry["prompt_file"], prompt_path.read_text(encoding="utf-8")))
    lines.extend(["## 使用顺序", "", "1. 先按 `UPLOAD.md` 生成并批准依赖资产。", "2. 角色身份资产默认使用四视图基准板；状态版本单独保留，不覆盖身份基准。", "3. 复制对应 `.image.txt` 全文到 GPT Image 2/2.5；不要把本页说明或 `index.json` 一起提交。", ""])
    return "\n".join(lines) + "\n"


def render_video(production, output, index, compact=False):
    if index.get("version") == "4.3.6":
        from h3_delivery import upload_card
        context = index["display_context"]
        entries = index.get("segments", [])
        view_production = production or {
            "project_id": context.get("project_id"),
            "production_total_duration": context.get("production_total_duration"),
            "fps_num": context.get("fps_num", 24),
            "fps_den": context.get("fps_den", 1),
            "story": {"synopsis": context.get("story_summary"), "arc_scope": context.get("story_arc_scope")},
            "segments": [],
        }
        segment_by_id = {seg.get("id"): seg for seg in view_production.get("segments", [])}
        lines = ["# H3 视频交付总览 · Acheng Director 生产台", "", "## 总控台", "",
                 f"项目：{view_production.get('project_id', '未命名项目')}",
                 f"总时长：{context.get('production_total_duration')} 秒 · {context.get('fps_num')}/{context.get('fps_den')} fps",
                 f"段落数量：{len(entries)} · 模式：{index.get('execution_mode')}",
                 "状态：机器检查不等于平台已上传或影像已生成；缺素材与合同缺项保持草案。", ""]
        lines.extend(_creative_summary(view_production, entries))
        lines.extend(_asset_prompt_section(view_production, output, index, compact=compact))
        lines.extend(["## 段落地图（分段地图）", "", "| 段落 | 时间 | 时长 | H3模式 | 创作事件/意图 | 状态 |", "|---|---|---:|---|---|---|"])
        for entry in entries:
            seg = segment_by_id.get(entry["segment_id"], {})
            start = seconds(seg.get("start_frame", entry.get("start_frame", 0)), view_production)
            end = seconds(seg.get("end_frame", entry.get("end_frame", 0)), view_production)
            event = entry.get("summary") or seg.get("summary") or "见完整 H3 正文"
            lines.append(f"| {entry['segment_id']} | {start}–{end} | {esc(entry.get('generation_clip_duration'))}s | {entry['mode']} | {esc(event)} | {entry['status']} |")
        lines.extend(["", "## 每段上传参考助手", "", "每张卡只覆盖一个 Segment；先看状态与实际文件，再按标签顺序上传。Subject 是内容对象，不是额外上传槽位。", ""])
        for entry in entries:
            if entry.get("summary"):
                lines.extend([f"**本段创作摘要：** {entry['summary']}", ""])
            lines.append(upload_card(entry))
            if not compact and index.get("execution_mode") == "interactive_segment":
                prompt = output / entry["file"]
                if prompt.is_file():
                    lines.extend(_prompt_details(entry["segment_id"], entry["file"], prompt.read_text(encoding="utf-8")))
        lines.extend(["## H3 正文文件", "", "每个文件都是独立请求；请复制对应文件的完整正文，不把本页说明、manifest 或上传卡混入模型输入。", "", "| 段落 | 状态 | 完整 H3/草案 | 独立上传卡 |", "|---|---|---|---|"])
        for entry in entries:
            lines.append(f"| {entry['segment_id']} | {entry['status']} | [{entry['file']}]({entry['file']}) | [{entry['upload_card']}]({entry['upload_card']}) |")
        lines.append("")
        lines.extend(_execution_section(view_production, entries, index))
        if index.get("execution_mode") == "interactive_segment":
            lines.extend(["WAIT_FOR_USER_CONTINUE：当前只交付一个完整 Segment；收到“继续/下一段”后再推进，partial 从游标恢复。", ""])
        else:
            lines.extend(["自动文件模式：长 H3 正文留在独立文件；本页保留创作摘要、资产提示词、分段地图和每段上传助手，不能用总清单链接代替操作卡。", ""])
        return "\n".join(lines) + "\n"
    shots = {shot["id"]: shot for shot in production.get("shots", [])}
    lines = ["# H3 视频交付总览", "", "这是给人阅读的导航页；每个 `.h3.txt` 都是独立请求，复制全文提交，不依赖上一段聊天。", "", "## 总控台", "",
             f"总时长：{production.get('production_total_duration', '未指定')} 秒 · {production.get('fps_num', 24)}/{production.get('fps_den', 1)} fps",
             f"段落数量：{len(index.get('segments', []))}", "状态：已编译但未调用视频模型；真实身份、动作自然度、声音和尾态仍需生成后验收。", "", "## 段落地图", "",
             "| 段落 | 时间 | 时长 | H3模式 | 镜头事件 | 参考素材 | 状态 |", "|---|---:|---:|---|---|---|---|"]
    for entry in index.get("segments", []):
        seg = next((item for item in production.get("segments", []) if item["id"] == entry["segment_id"]), {})
        seg_shots = [shots[sid] for sid in seg.get("shot_ids", []) if sid in shots]
        events = "；".join(shot.get("visual", "") for shot in seg_shots) or "见完整提示词"
        refs = ("无需参考图" if seg.get("mode") == "T2VA" else "待素材/待核验") if not entry.get("references") else "、".join(ref["label"] for ref in entry["references"])
        lines.append(f"| {esc(entry['segment_id'])} | {seconds(seg.get('start_frame', 0), production)}–{seconds(seg.get('end_frame', 0), production)} | {esc(duration(seg, production))} | {esc(entry.get('mode'))} | {esc(events)} | {esc(refs)} | 旧清单需联合复验 |")
    lines.extend(["", "## 逐段提交卡", ""])
    for entry in index.get("segments", []):
        seg = next((item for item in production.get("segments", []) if item["id"] == entry["segment_id"]), {})
        lines.extend([f"### {entry['segment_id']} · {entry.get('mode')} · {duration(seg, production)}", "", f"时间：{seconds(seg.get('start_frame', 0), production)}–{seconds(seg.get('end_frame', 0), production)}"])
        refs = entry.get("references", [])
        lines.append(("参考输入：无需参考图。" if seg.get("mode") == "T2VA" else "参考输入：待素材，不能提交。") if not refs else "参考输入：" + "; ".join(f"{ref['label']} = {ref['role']}" for ref in refs))
        if seg.get("summary"):
            lines.append("导演意图：" + seg["summary"])
        lines.append("提交前：旧清单需重新编译并通过逐段联合验收；入口时长、模式和参考槽位另行核对。")
        lines.append("")
        lines.extend(_video_reference_guide(production, seg, entry))
        prompt_path = output / entry["file"]
        if prompt_path.is_file():
            lines.extend(_prompt_details(entry["segment_id"], entry["file"], prompt_path.read_text(encoding="utf-8")))
    lines.extend(["## 使用顺序", "", "1. 先打开每段 `UPLOAD.md`，按标签上传该段素材。", "2. 在 H3 入口设置相同模式和时长。", "3. 复制对应 `.h3.txt` 全文提交；不要把内部 speaker_map、index.json 或本页说明贴入模型。", ""])
    return "\n".join(lines) + "\n"


def render_project(production, image_dir=None, video_dir=None):
    lines = ["# Acheng 导演交付总览", "", "## 导演总控台", "", f"项目：{production.get('project_id', '未命名项目')}",
             f"交付范围：{production.get('delivery_scope', 'prompt_only')}", f"总时长：{production.get('production_total_duration', '未指定')} 秒",
             f"帧率：{production.get('fps_num', 24)}/{production.get('fps_den', 1)} fps", "状态：机器合同需通过后，提示词才可进入提交阶段；模型生成与人工画面验收另行进行。", ""]
    story = production.get("story", {})
    if story.get("synopsis"):
        lines.extend(["## 创作摘要", "", story["synopsis"], ""])
    lines.extend(["## 一页生产路线", "", "| 阶段 | 结果 | 状态 |", "|---|---|---|",
                  f"| 剧本/叙事 | {esc(story.get('synopsis') or '见 production.json') } | {'已登记' if story else '未提供'} |",
                  f"| 资产 | {len(production.get('asset_cards', []))} 项资产卡 | {'待编译' if image_dir is None else '已编译'} |",
                  f"| 分镜 | {len(production.get('shots', []))} 个镜头 | {'已登记' if production.get('shots') else '未提供'} |",
                  f"| 视频 | {len(production.get('segments', []))} 个生成段 | {'待编译' if video_dir is None else '已编译'} |", ""])
    if image_dir:
        lines.extend(["## 资产入口", "", f"[打开资产交付总览](images/{Path(image_dir).name}/DELIVERY_VIEW.md)", ""])
    if video_dir:
        lines.extend(["## 视频入口", "", f"[打开 H3 交付总览](video/{Path(video_dir).name}/DELIVERY_VIEW.md)", ""])
    lines.extend(["## 验收边界", "", "机器检查只证明字段、时长、引用顺序、代号消解和文件完整性；角色身份稳定、四视图一致、表演自然、碰撞材质、声音连续和最终尾态必须在真实生成后人工验收。", ""])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("production", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--kind", choices=("project", "assets", "video"), default="project")
    args = parser.parse_args()
    production = read_json(args.production)
    if args.kind == "assets":
        text = render_assets(production, args.out.parent, read_json(args.out.parent / "index.json"))
    elif args.kind == "video":
        text = render_video(production, args.out.parent, read_json(args.out.parent / "index.json"))
    else:
        text = render_project(production)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"Rendered human-readable delivery view: {args.out}")


if __name__ == "__main__":
    main()
