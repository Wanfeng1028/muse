import json, os, itertools

SRC = os.path.expanduser("~/workspace/openmontage/skills")
OUT = "scripts-om/manifest.json"

def skill_id(rel):
    parts = rel[:-3].split("/")  # drop .md
    if parts[0] == "pipelines":
        return "openmontage-" + parts[1] + "-" + parts[2]
    return "openmontage-" + parts[-1]

files = []
for root, dirs, fs in os.walk(SRC):
    dirs.sort()
    for f in sorted(fs):
        if f == "INDEX.md" or not f.endswith(".md"):
            continue
        full = os.path.join(root, f)
        rel = os.path.relpath(full, SRC)
        files.append((rel, skill_id(rel)))

# check duplicates
ids = [i for _, i in files]
assert len(ids) == len(set(ids)), "duplicate ids!"

# existing ids
import subprocess
exist = set()
idx = json.load(open("src/main/resources/skills-bundled/_index.json"))
for e in idx["skills"]:
    exist.add(e["id"])
conflict = [i for i in ids if i in exist]
assert not conflict, f"id conflict with existing: {conflict}"

# batches: group by (topdir, pipeline) with size limits
groups = {}
for rel, sid in files:
    p = rel.split("/")
    key = (p[0], p[1] if p[0] in ("pipelines", "creative") and len(p) > 2 else "")
    groups.setdefault(key, []).append((rel, sid))

batches = []
for key in sorted(groups):
    items = groups[key]
    n = 4 if len(items) > 8 else 3
    for k in range(0, len(items), n):
        chunk = items[k:k+n]
        bname = f"{key[0]}-{key[1]}-{(k//n)+1}" if key[1] else f"{key[0]}-{(k//n)+1}"
        batches.append({"batch": bname, "skills": [{"id": s, "src": r} for r, s in chunk]})

json.dump({"batches": batches, "total": len(files)}, open(OUT, "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("total skills:", len(files))
print("total batches:", len(batches))
for b in batches:
    print(b["batch"], len(b["skills"]))
