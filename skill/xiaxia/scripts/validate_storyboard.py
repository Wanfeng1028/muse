#!/usr/bin/env python3
# Copyright (c) 2026 栾意
# SPDX-License-Identifier: CC-BY-NC-4.0
"""Validate Xiaxia storyboard timing, compact format, and group delivery rules."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


GROUP_RE = re.compile(
    r"^##\s+生成组\s+([^｜\n]+)｜本组\s+(\d+(?:\.\d+)?)s｜总片\s+([^\n]+)$"
)
SHOT_RE = re.compile(
    r"^\[分镜\s+([^｜\]]+)｜\s*(\d+(?:\.\d+)?)\s*[–—-]\s*(\d+(?:\.\d+)?)s\s*｜\s*(\d+(?:\.\d+)?)s\]\s*[：:]\s*(.*)$"
)
TOTAL_RE = re.compile(r"^总时长：\s*(\d{1,2}):(\d{2})")
RANGE_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?\s*[–—-]\s*"
    r"(\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?\s*$"
)
REQUIRED_GROUP_FIELDS = ("本组任务：", "组尾连续性：")
SOUND_RULE = "声音要求：不要 BGM；不要字幕；只保留剧情对白、环境声和动作音效。"
FORBIDDEN_HEADINGS = re.compile(r"^#{1,6}\s+(分镜圣经|生成组地图)(?:\s|$)", re.M)
EPSILON = 0.06


@dataclass
class Shot:
    number: str
    start: float
    end: float
    declared: float
    header: str
    line: int
    body: list[str] = field(default_factory=list)


@dataclass
class Group:
    label: str
    duration: float
    total_range: str
    line: int
    body: list[str] = field(default_factory=list)
    shots: list[Shot] = field(default_factory=list)


def parse(text: str) -> list[Group]:
    groups: list[Group] = []
    current_group: Group | None = None
    current_shot: Shot | None = None

    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        group_match = GROUP_RE.match(stripped)
        if group_match:
            current_group = Group(
                group_match.group(1).strip(),
                float(group_match.group(2)),
                group_match.group(3).strip(),
                line_no,
            )
            groups.append(current_group)
            current_shot = None
            continue

        shot_match = SHOT_RE.match(stripped)
        if shot_match and current_group:
            current_shot = Shot(
                shot_match.group(1).strip(),
                float(shot_match.group(2)),
                float(shot_match.group(3)),
                float(shot_match.group(4)),
                shot_match.group(5).strip(),
                line_no,
            )
            current_group.shots.append(current_shot)
            continue

        if current_group:
            current_group.body.append(line)
        if current_shot:
            if stripped.startswith(("组尾连续性：", "声音要求：")):
                current_shot = None
            else:
                current_shot.body.append(line)

    return groups


def close(a: float, b: float) -> bool:
    return abs(a - b) <= EPSILON


def parse_range(value: str) -> tuple[float, float] | None:
    match = RANGE_RE.match(value)
    if not match:
        return None

    def stamp(hour: str, minute: str, second: str | None) -> float:
        if second is None:
            return int(hour) * 60 + int(minute)
        return int(hour) * 3600 + int(minute) * 60 + float(second)

    return stamp(match.group(1), match.group(2), match.group(3)), stamp(
        match.group(4), match.group(5), match.group(6)
    )


def meaningful_length(lines: list[str]) -> int:
    return len(re.sub(r"\s+", "", "\n".join(lines)))


def validate(text: str, groups: list[Group]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if FORBIDDEN_HEADINGS.search(text):
        errors.append("正式交付中不得出现“分镜圣经”或“生成组地图”标题。")

    if not groups:
        errors.append("未找到生成组标题；格式应为：## 生成组 01｜本组 27s｜总片 00:00–00:27")
        return errors, warnings

    total_match = next(
        (TOTAL_RE.match(line.strip()) for line in text.splitlines() if TOTAL_RE.match(line.strip())),
        None,
    )
    declared_total = None
    if total_match:
        declared_total = int(total_match.group(1)) * 60 + int(total_match.group(2))

    previous_total_end = 0.0
    shot_numbers: list[int] = []

    for group in groups:
        prefix = f"生成组 {group.label}（第 {group.line} 行）"
        if not 4 <= group.duration <= 30:
            errors.append(f"{prefix}：时长 {group.duration:g}s 超出 4–30s。")

        total_range = parse_range(group.total_range)
        if total_range is None:
            errors.append(f"{prefix}：总片区间“{group.total_range}”无法识别。")
        else:
            total_start, total_end = total_range
            if not close(total_start, previous_total_end):
                errors.append(
                    f"{prefix}：总片起点 {total_start:g}s 未衔接上一组 {previous_total_end:g}s。"
                )
            if not close(total_end - total_start, group.duration):
                errors.append(f"{prefix}：总片区间长度与本组 {group.duration:g}s 不一致。")
            previous_total_end = total_end

        group_text = "\n".join(group.body)
        for required in REQUIRED_GROUP_FIELDS:
            if required not in group_text:
                errors.append(f"{prefix}：缺少“{required}”。")

        nonblank = [line.strip() for line in group.body if line.strip()]
        if not nonblank or nonblank[-1] != SOUND_RULE:
            errors.append(f"{prefix}：组末必须逐字写声音要求，且该行之后不得追加内容。")
        if group_text.count(SOUND_RULE) != 1:
            errors.append(f"{prefix}：声音要求必须且只能出现一次。")

        if not group.shots:
            errors.append(f"{prefix}：没有识别到组内分镜。")
            continue

        if not close(group.shots[0].start, 0):
            errors.append(f"{prefix}：第一镜应从 0s 开始，当前为 {group.shots[0].start:g}s。")

        previous_end = 0.0
        for shot in group.shots:
            shot_prefix = f"{prefix}，分镜 {shot.number}（第 {shot.line} 行）"
            actual = shot.end - shot.start
            if shot.number.isdigit():
                shot_numbers.append(int(shot.number))
            else:
                warnings.append(f"{shot_prefix}：建议使用纯数字镜号。")
            if shot.end <= shot.start:
                errors.append(f"{shot_prefix}：结束时间必须晚于开始时间。")
            if not close(actual, shot.declared):
                errors.append(f"{shot_prefix}：时间段为 {actual:g}s，但声明为 {shot.declared:g}s。")
            if shot.start > previous_end + EPSILON:
                errors.append(f"{shot_prefix}：与上一镜之间有 {shot.start - previous_end:g}s 未覆盖。")
            if shot.start < previous_end - EPSILON:
                errors.append(f"{shot_prefix}：与上一镜重叠 {previous_end - shot.start:g}s。")
            if shot.end > group.duration + EPSILON:
                errors.append(f"{shot_prefix}：结束时间越过本组 {group.duration:g}s。")
            if "mm" not in shot.header or not re.search(r"(?:^|[/+\s])f\d", shot.header, re.I):
                errors.append(f"{shot_prefix}：标题缺少 35mm 等效焦段或光圈。")
            if meaningful_length(shot.body) < 70:
                warnings.append(
                    f"{shot_prefix}：导演段落过短，可能缺少空间、表演、光影、声音或镜尾状态。"
                )

            shot_text = "\n".join(shot.body)
            if not re.search(r"光|阴影|高光|曝光|亮部|暗部", shot_text):
                warnings.append(f"{shot_prefix}：未识别到光影信息。")
            if not re.search(r"声|说|喊|问|答|沉默", shot_text):
                warnings.append(f"{shot_prefix}：未识别到声音或对白处理。")
            previous_end = shot.end

        if not close(previous_end, group.duration):
            errors.append(
                f"{prefix}：最后一镜结束于 {previous_end:g}s，未与本组 {group.duration:g}s 对齐。"
            )

    if declared_total is not None and not close(declared_total, previous_total_end):
        errors.append(f"总时长声明为 {declared_total:g}s，但生成组覆盖到 {previous_total_end:g}s。")

    if shot_numbers:
        expected = list(range(shot_numbers[0], shot_numbers[0] + len(shot_numbers)))
        if shot_numbers != expected:
            errors.append("分镜编号不连续或有重复。")

    return errors, warnings


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：validate_storyboard.py /absolute/path/to/storyboard.md", file=sys.stderr)
        return 2

    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        print(f"错误：文件不存在：{path}", file=sys.stderr)
        return 2

    text = path.read_text(encoding="utf-8")
    groups = parse(text)
    errors, warnings = validate(text, groups)

    for warning in warnings:
        print(f"警告：{warning}")
    for error in errors:
        print(f"错误：{error}")

    if errors:
        print(f"未通过：{len(errors)} 个错误，{len(warnings)} 个警告。")
        return 1

    print(f"通过：{len(groups)} 个生成组，0 个错误，{len(warnings)} 个警告。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
