"""Check SKILL.md frontmatter and that every repo path named in the docs exists."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["SKILL.md", "README.md", *[f"references/{p.name}" for p in (ROOT / "references").glob("*.md")]]
TOP = {p.name for p in ROOT.iterdir()}


def frontmatter_errors() -> list[str]:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        return ["SKILL.md has no frontmatter"]
    fields = dict(line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    errors = [f"SKILL.md frontmatter is missing {key}" for key in ("name", "description") if not fields.get(key, "").strip()]
    if fields.get("name", "").strip() != "openvids":
        errors.append("SKILL.md name must be openvids")
    return errors


def path_errors() -> list[str]:
    errors = []
    for doc in DOCS:
        text = (ROOT / doc).read_text(encoding="utf-8")
        for raw in re.findall(r"`([^`\s]+)`", text):
            path = raw.replace("{skillDir}/", "").rstrip("/")
            if "{" in path or "<" in path or path.split("/")[0] not in TOP:
                continue
            if not (ROOT / path).exists():
                errors.append(f"{doc}: {raw} does not exist")
    return errors


errors = frontmatter_errors() + path_errors()
for error in errors:
    print(error)
print(f"checked {len(DOCS)} docs, {len(errors)} errors")
sys.exit(1 if errors else 0)
