"""校验 storyboard.json：时间轴、拍点、阅读时间、重复、音效事件、张力曲线。只用 Python 标准库。

用法：
  python check_storyboard.py src/storyboard.json
  python check_storyboard.py src/storyboard.json --sfx-manifest public/sfx/manifest.json --music-json docs/music.json

退出码：有错误时为 1，只有警告时为 0。
"""
import argparse
import json
import re
import sys
from pathlib import Path

CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
WORD = re.compile(r"[A-Za-z0-9]+(?:[.'’-][A-Za-z0-9]+)*")


def reading_seconds(lines):
    text = "".join(lines)
    cjk = len(CJK.findall(text))
    words = len(WORD.findall(CJK.sub(" ", text)))
    if cjk == 0 and words == 0:
        return 0.0
    return cjk / 5.0 + words / 3.0 + 0.5


def visual_len(line):
    cjk = len(CJK.findall(line))
    return cjk + (len(line) - cjk) * 0.55


def sparkline(values, width=60):
    bars = " .:-=+*#%@"
    if not values:
        return ""
    step = max(1, len(values) // width)
    sampled = values[::step]
    return "".join(bars[min(9, max(0, round(v / 10 * 9)))] for v in sampled)


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="校验分镜数据")
    ap.add_argument("storyboard")
    ap.add_argument("--sfx-manifest", default=None)
    ap.add_argument("--music-json", default=None, help="analyze_music.py 或 synth_music.py 的输出，用于核对时长和拍点")
    ap.add_argument("--beat-tolerance", type=float, default=1.0, help="切点偏离拍点多少帧以内算对齐")
    args = ap.parse_args()

    sb = json.loads(Path(args.storyboard).read_text(encoding="utf-8"))
    errors, warns, infos = [], [], []
    E, W, I = errors.append, warns.append, infos.append

    meta = sb.get("meta", {})
    shots = sb.get("shots", [])
    fps = meta.get("fps")
    width, height = meta.get("width"), meta.get("height")
    total = meta.get("durationInFrames")

    for key in ("fps", "width", "height", "durationInFrames"):
        if not isinstance(meta.get(key), int) or meta.get(key) <= 0:
            E(f"meta.{key} 必须是正整数，当前为 {meta.get(key)!r}")
    if errors:
        report(errors, warns, infos)
        return
    if width % 2 or height % 2:
        E(f"宽高必须是偶数（H.264 要求），当前 {width}x{height}")
    vertical = height > width
    max_line = 14 if vertical else 20

    if not shots:
        E("shots 为空")
        report(errors, warns, infos)
        return

    ids = [s.get("id") for s in shots]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        E(f"镜头 id 重复：{sorted(dup)}")

    manifest = {}
    if args.sfx_manifest:
        manifest = json.loads(Path(args.sfx_manifest).read_text(encoding="utf-8"))

    music = json.loads(Path(args.music_json).read_text(encoding="utf-8")) if args.music_json else None
    bpm = meta.get("bpm") or (music or {}).get("bpm")
    offset = meta.get("beatOffsetFrames", (music or {}).get("beatOffsetFrames", 0)) or 0
    beat_frames = None
    if music and music.get("beats"):
        beat_frames = [b["frame"] for b in music["beats"]]
    elif bpm:
        fpb = fps * 60.0 / bpm
        beat_frames = [round(offset + k * fpb) for k in range(int((total - offset) / fpb) + 2)]

    ordered = sorted(shots, key=lambda s: s.get("from", 0))
    if [s.get("id") for s in ordered] != ids:
        W("shots 的书写顺序和时间顺序不一致，建议按 from 排序书写")

    cursor = 0
    scene_run, last_scene = 0, None
    transitions = set()
    durations = []
    intensity = []
    for s in ordered:
        sid = s.get("id", "?")
        f0, d = s.get("from"), s.get("duration")
        if not isinstance(f0, int) or not isinstance(d, int) or d <= 0:
            E(f"{sid}：from 和 duration 必须是整数且 duration > 0")
            continue
        if not s.get("scene"):
            E(f"{sid}：缺少 scene")
        if f0 > cursor and not s.get("gapOk"):
            E(f"{sid}：和上一个镜头之间有 {f0 - cursor} 帧空档（第 {cursor} 到 {f0} 帧会是空画面）")
        if f0 < cursor and not s.get("overlapOk"):
            E(f"{sid}：和上一个镜头重叠 {cursor - f0} 帧。需要重叠的转场请加 \"overlapOk\": true")
        cursor = max(cursor, f0 + d)
        durations.append(d)

        if d < 8:
            W(f"{sid}：只有 {d} 帧（{d / fps:.2f} 秒），非常短，确认是刻意的闪切")
        if d > 8 * fps and not s.get("longOk"):
            W(f"{sid}：{d / fps:.1f} 秒的长镜头，确认内部有持续的运动或渐进揭示（确认后可加 \"longOk\": true）")

        text = s.get("text") or []
        if isinstance(text, str):
            text = [text]
        need = reading_seconds(text)
        if need and d / fps < need - 0.05:
            W(f"{sid}：文字需要约 {need:.1f} 秒才能读完，镜头只有 {d / fps:.1f} 秒")
        for line in text:
            if visual_len(line) > max_line:
                W(f"{sid}：这一行偏长（约 {visual_len(line):.0f} 字宽，{'竖屏' if vertical else '横屏'}建议不超过 {max_line}）：{line}")

        if beat_frames and f0 > 0:
            nearest = min(beat_frames, key=lambda b: abs(b - f0))
            if abs(nearest - f0) > args.beat_tolerance:
                W(f"{sid}：切点第 {f0} 帧不在拍上（最近的拍在第 {nearest} 帧）")

        scene = s.get("scene")
        scene_run = scene_run + 1 if scene == last_scene else 1
        last_scene = scene
        if scene_run == 4:
            W(f"{sid}：场景 {scene} 已经连续用了 4 次，注意画面是否单调")

        tr = s.get("transitionOut", "cut")
        transitions.add(tr)

        if "intensity" in s:
            intensity.extend([s["intensity"]] * max(1, d // max(1, fps // 2)))

        for ev in s.get("events", []) or []:
            at = ev.get("at")
            if not isinstance(at, int):
                E(f"{sid}：音效事件缺少整数 at：{ev}")
                continue
            if at < 0 or at > d:
                W(f"{sid}：音效事件 at={at} 超出镜头范围 0 到 {d}")
            name = ev.get("sfx")
            if manifest and name not in manifest:
                E(f"{sid}：音效 {name!r} 不在 manifest 里")

    if cursor != total:
        E(f"meta.durationInFrames = {total}，但最后一个镜头结束在第 {cursor} 帧")

    non_cut = transitions - {"cut", None}
    if len(non_cut) > 3:
        W(f"用了 {len(non_cut)} 种非硬切转场：{sorted(non_cut)}。建议不超过 3 种")

    if music:
        mdur = music.get("durationInFrames")
        if mdur and abs(mdur - total) > fps:
            W(f"音乐长 {mdur} 帧，片子长 {total} 帧，相差 {abs(mdur - total) / fps:.1f} 秒")

    if durations:
        avg = sum(durations) / len(durations) / fps
        I(f"{len(durations)} 个镜头，总长 {total / fps:.1f} 秒，平均镜头 {avg:.2f} 秒")
    if intensity:
        peak_pos = intensity.index(max(intensity)) / len(intensity)
        I(f"张力曲线：|{sparkline(intensity)}|")
        I(f"张力最高点在全片 {peak_pos:.0%} 处")
        if not 0.6 <= peak_pos <= 0.9:
            W(f"张力最高点在全片 {peak_pos:.0%} 处，通常放在 70% 到 85% 更好")
        if len(set(intensity)) <= 2:
            W("张力值几乎没有变化，情绪曲线可能太平")
    else:
        I("镜头没有 intensity 字段，跳过张力曲线检查")

    report(errors, warns, infos)


def report(errors, warns, infos):
    for m in infos:
        print(f"[INFO] {m}")
    for m in warns:
        print(f"[WARN] {m}")
    for m in errors:
        print(f"[ERR ] {m}")
    print(f"结果：{len(errors)} 个错误，{len(warns)} 个警告")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
