from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NAME = "novel-to-ai-short-drama"
REQUIRED_FILES = (
    "README.md",
    "SKILL.md",
    "LICENSE",
    "agents/openai.yaml",
    "references/adaptation-workflow.md",
    "references/deliverable-template.md",
    "references/directing-language.md",
    "references/quality-gates.md",
    "examples/测试结果.md",
)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def read_utf8(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(errors, f"无法读取 UTF-8 文件 {path.relative_to(ROOT)}: {exc}")
        return ""


def load_yaml(path: Path, errors: list[str]) -> dict:
    text = read_utf8(path, errors)
    if not text:
        return {}
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        fail(errors, f"YAML 无法解析 {path.relative_to(ROOT)}: {exc}")
        return {}
    if not isinstance(data, dict):
        fail(errors, f"YAML 顶层必须是对象: {path.relative_to(ROOT)}")
        return {}
    return data


def validate_skill_md(errors: list[str]) -> None:
    path = ROOT / "SKILL.md"
    text = read_utf8(path, errors)
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        fail(errors, "SKILL.md 缺少有效的 YAML frontmatter。")
        return

    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        fail(errors, f"SKILL.md frontmatter 无法解析: {exc}")
        return

    if not isinstance(metadata, dict):
        fail(errors, "SKILL.md frontmatter 必须是对象。")
        return
    if metadata.get("name") != EXPECTED_NAME:
        fail(errors, f"Skill 名称必须为 {EXPECTED_NAME}。")
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        fail(errors, "SKILL.md 必须包含非空 description。")

    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        if "://" in target or target.startswith("#"):
            continue
        target_path = (ROOT / target).resolve()
        try:
            target_path.relative_to(ROOT.resolve())
        except ValueError:
            fail(errors, f"SKILL.md 引用了仓库外路径: {target}")
            continue
        if not target_path.exists():
            fail(errors, f"SKILL.md 引用不存在: {target}")


def validate_openai_yaml(errors: list[str]) -> None:
    data = load_yaml(ROOT / "agents" / "openai.yaml", errors)
    interface = data.get("interface")
    if not isinstance(interface, dict):
        fail(errors, "agents/openai.yaml 缺少 interface。")
        return

    short_description = interface.get("short_description")
    if not isinstance(short_description, str) or not 25 <= len(short_description) <= 64:
        fail(errors, "short_description 长度必须为 25–64 个字符。")
    default_prompt = interface.get("default_prompt")
    if not isinstance(default_prompt, str) or f"${EXPECTED_NAME}" not in default_prompt:
        fail(errors, f"default_prompt 必须显式包含 ${EXPECTED_NAME}。")


def validate_example(errors: list[str]) -> None:
    text = read_utf8(ROOT / "examples" / "测试结果.md", errors)
    top_headings = re.findall(r"^# (.+)$", text, re.MULTILINE)
    expected_headings = ["第一部分：狼人", "第二部分：霸总", "第三部分：校园"]
    if top_headings != expected_headings:
        fail(errors, "测试结果必须且只能包含狼人、霸总、校园三个顶层部分。")

    sections = re.split(r"(?=^# )", text, flags=re.MULTILINE)
    checked = 0
    for section in sections:
        heading = re.match(r"^# (.+)$", section, re.MULTILINE)
        if not heading:
            continue
        durations = [
            int(value)
            for value in re.findall(
                r"^\| [12]-\d{2} \| .*? / (\d+)s \|",
                section,
                re.MULTILINE,
            )
        ]
        if sum(durations) != 60:
            fail(errors, f"{heading.group(1)}的 Skill 分镜合计不是 60 秒。")
        checked += 1
    if checked != 3:
        fail(errors, "未能校验全部三个测试部分。")


def validate_placeholders(errors: list[str]) -> None:
    marker = re.compile(r"\bTO" + r"DO\b|\[TO" + r"DO", re.IGNORECASE)
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() not in {".md", ".yaml", ".yml", ".py", ".txt"}:
            continue
        text = read_utf8(path, errors)
        if marker.search(text):
            fail(errors, f"发现未完成占位符: {path.relative_to(ROOT)}")


def main() -> int:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(errors, f"缺少必需文件: {relative}")

    if not errors:
        validate_skill_md(errors)
        validate_openai_yaml(errors)
        validate_example(errors)
        validate_placeholders(errors)

    if errors:
        print("Skill validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Skill validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
