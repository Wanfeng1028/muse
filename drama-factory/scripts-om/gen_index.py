import json, os, re

try:
    import yaml
except ImportError:
    import sys
    sys.path.insert(0, os.path.expanduser("~/workspace/toolchains/pylibs"))
    import yaml

DST = "src/main/resources/skills-bundled"
man = json.load(open("scripts-om/manifest.json", encoding="utf-8"))
src_of = {s["id"]: s["src"] for b in man["batches"] for s in b["skills"]}

STOP = {"openmontage", "video", "director", "usage", "gen", "prompting", "the", "a"}
exist_toks = set()
idx = json.load(open(DST + "/_index.json", encoding="utf-8"))
for e in idx["skills"]:
    for t in re.split(r"[-_]", e["id"].lower()):
        if t and t not in STOP:
            exist_toks.add(t)

def overlap(sid):
    toks = [t for t in re.split(r"[-_]", sid.lower()) if t and t not in STOP]
    return any(t in exist_toks for t in toks)

entries = []
for sid in sorted(src_of):
    md = open(os.path.join(DST, sid, "SKILL.md"), encoding="utf-8").read()
    fm = yaml.safe_load(md[3:md.find("\n---\n", 3) + 1])
    desc = str(fm["description"])
    if overlap(sid) and "互补" not in desc:
        desc = desc.rstrip() + "（与现有条目互补的 OpenMontage 视角版本）"
    entries.append({
        "id": sid,
        "name": sid,
        "version": str(fm.get("version", "1.0.0")),
        "description": desc,
        "author": "",
        "license": "AGPL-3.0",
        "source": "calesthio/OpenMontage",
        "sourceUrl": "openmontage/skills/" + src_of[sid],
        "rewritten": True,
    })

out = {"skills": entries}
p = DST + "/_index.openmontage.json"
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
open(p, "a", encoding="utf-8").write("\n")
print(f"wrote {p}: {len(entries)} entries")
ov = [e["id"] for e in entries if "互补" in e["description"]]
print(f"overlap-marked: {len(ov)}")
for x in ov:
    print("  ", x)
