#!/usr/bin/env python3
"""Lint this skill: frontmatter, length, every referenced path exists, no orphan references, scripts run --help.

USAGE
  lint_skill.py [SKILL_ROOT]     # default: the folder above scripts/
Exit 1 on any failure. Run it after every edit to SKILL.md, references/ or scripts/
(broken paths after install were the top complaint about other video skills).
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

MAX_LINES = 200
PATH_RE = re.compile(r"(?<![\w/.-])((?:scripts|references|assets|tests)/[\w.\-/]+)")


def main():
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else \
        pathlib.Path(__file__).resolve().parent.parent
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    fails, notes = [], []
    skill = root / "SKILL.md"
    if not skill.exists():
        sys.exit(f"FAIL no SKILL.md in {root}")
    text = skill.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        fails.append("SKILL.md has no YAML frontmatter")
    else:
        import yaml
        fm = yaml.safe_load(m.group(1)) or {}
        for k in ("name", "description"):
            if not fm.get(k):
                fails.append(f"frontmatter missing '{k}'")
        if fm.get("name") and fm["name"] != root.name:
            notes.append(f"frontmatter name '{fm['name']}' differs from folder '{root.name}'")
        if len(str(fm.get("description", ""))) > 1024:
            fails.append("description over 1024 characters")
    n = text.count("\n") + 1
    (fails if n > MAX_LINES else notes).append(f"SKILL.md has {n} lines (max {MAX_LINES})")

    docs = [skill] + sorted((root / "references").glob("*.md"))
    for d in docs:
        for ref in sorted(set(PATH_RE.findall(d.read_text(encoding="utf-8")))):
            ref = ref.rstrip(".,:;)`'\"")
            if "*" in ref or "<" in ref:
                continue
            if not (root / ref).exists():
                fails.append(f"{d.relative_to(root)} points to missing {ref}")
    for r in sorted((root / "references").glob("*.md")):
        if f"references/{r.name}" not in text:
            fails.append(f"references/{r.name} is not linked from SKILL.md")

    for s in sorted((root / "scripts").glob("*.py")):
        src = s.read_text(encoding="utf-8")
        doc = re.search(r'^(?:#![^\n]*\n)?"""(.*?)"""', src, re.S)
        if not doc:
            fails.append(f"{s.name}: no module docstring")
            continue
        if "Not a CLI" in doc.group(1):
            continue
        if "USAGE" not in doc.group(1):
            fails.append(f"{s.name}: docstring has no USAGE section")
        r = subprocess.run([sys.executable, str(s), "--help"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode != 0:
            fails.append(f"{s.name} --help exited {r.returncode}: {r.stderr.strip()[-200:]}")
    for s in sorted((root / "scripts").glob("*.sh")):
        if subprocess.run(["bash", "-n", str(s)], capture_output=True).returncode != 0:
            fails.append(f"{s.name}: bash syntax error")
        if "USAGE" not in s.read_text(encoding="utf-8"):
            fails.append(f"{s.name}: no USAGE comment")

    for x in notes:
        print(f"note  {x}")
    for x in fails:
        print(f"FAIL  {x}")
    print("lint: " + ("FAILED" if fails else "OK"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
