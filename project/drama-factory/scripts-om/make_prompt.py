import json, os, sys

SRC = os.path.expanduser("~/workspace/openmontage/skills")
SYS = """你是一个严格执行改写任务的中文技术写作者。输出只包含按要求格式化的改写内容，不许寒暄、不许解释、不许输出思考过程。

任务：把下方 N 个 OpenMontage 技能文档逐一改写为剧坊（Playhouse）官方 skill 库的 SKILL.md。

铁律（违反整批拒收、打回重做）：
1. 用自己的话重写，严禁逐字复制原文句子。任何连续 13 个英文单词与原文完全相同即拒收（我会用程序逐批校验）。技术术语、命令名、文件名等专有名词可以出现，但整句不许照搬。
2. 每个 skill 恰好输出一节：节头行 `### FILE: <id>`，随后是完整的 SKILL.md 内容（frontmatter + 正文）。节之间不许加任何说明文字。
3. frontmatter 必须严格如下（YAML，不增多余字段）：
---
name: <id>
version: "1.0.0"
description: <中文一句话：功能是什么 + 适用场景，60-120字>
metadata:
  license: AGPL-3.0
---
4. 正文中文为主，60-120 行 Markdown。保留原文全部实质内容：功能清单、关键流程步骤、重要命令/参数模板、验收要点，用自己的措辞和结构重组。可合并同类项、删去纯宣传语。代码块里的命令允许保留功能等价的形式，但每条必须附一句自己的中文说明。
5. 全篇输出结尾单独一行写 `=== END`，其后不许再有任何内容。
6. id 必须与给定的 id 列表一一对应，不许自创 id。
7. 原文中的示例 prompt、示例文案、示例标题、URL 列表一律用自己的话改写或替换为等效新示例，不许照搬原文示例句子（示例照搬同样触发 13 词拒收）。
"""

def main():
    batch = sys.argv[1]
    man = json.load(open("scripts-om/manifest.json", encoding="utf-8"))
    b = next(x for x in man["batches"] if x["batch"] == batch)
    ids = [s["id"] for s in b["skills"]]
    parts = [SYS, "\n本批 id 列表（必须一一对应）: " + ", ".join(ids) + "\n"]
    for s in b["skills"]:
        src = os.path.join(SRC, s["src"])
        text = open(src, encoding="utf-8").read()
        parts.append(f"\n===== SOURCE: {s['id']}（原文件 {s['src']}）=====\n{text}\n===== END SOURCE: {s['id']} =====\n")
    out = "scripts-om/work/prompt-" + batch + ".txt"
    open(out, "w", encoding="utf-8").write("".join(parts))
    print(f"wrote {out} ({len(''.join(parts))} chars)")

main()
