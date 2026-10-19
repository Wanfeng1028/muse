import json, os, re, sys

try:
    import yaml
except ImportError:
    sys.path.insert(0, os.path.expanduser("~/workspace/toolchains/pylibs"))
    import yaml

SRC = os.path.expanduser("~/workspace/openmontage/skills")
DST = "src/main/resources/skills-bundled"

def eng_words(t):
    return re.findall(r"[A-Za-z0-9_]+(?:['-][A-Za-z0-9_]+)*", t)

def strip_code(t):
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"`[^`\n]+`", " ", t)
    return t

def prose_alpha_count(gram):
    return sum(1 for w in gram if re.fullmatch(r"[A-Za-z]{3,}", w))

def copy13_check(source_text, out_text):
    # 只查正文散文抄袭：剔除代码块/行内代码，且 13-gram 至少含 8 个纯字母词
    sw = eng_words(strip_code(source_text).lower())
    ow = eng_words(strip_code(out_text).lower())
    sgrams = set()
    for i in range(len(sw) - 12):
        g = tuple(sw[i:i+13])
        if prose_alpha_count(g) >= 8:
            sgrams.add(g)
    hits = []
    for i in range(len(ow) - 12):
        g = tuple(ow[i:i+13])
        if prose_alpha_count(g) >= 8 and g in sgrams:
            hits.append(" ".join(g))
            if len(hits) >= 3:
                break
    return hits

def clean(text):
    lines = []
    for ln in text.split("\n"):
        s = ln.strip()
        if s in ("=== END", "--- END", "===END", "```END```"):
            continue
        lines.append(ln)
    return "\n".join(lines).strip() + "\n"

def main():
    batch = sys.argv[1]
    man = json.load(open("scripts-om/manifest.json", encoding="utf-8"))
    b = next(x for x in man["batches"] if x["batch"] == batch)
    expected = {s["id"]: s["src"] for s in b["skills"]}
    raw = open(f"scripts-om/work/out-{batch}.txt", encoding="utf-8").read()
    parts = re.split(r"(?m)^### FILE:\s*(\S+)\s*$", raw)
    # parts[0] is preamble, then (id, body, id, body, ...)
    found = {}
    for i in range(1, len(parts), 2):
        sid = parts[i].strip()
        body = parts[i+1] if i+1 < len(parts) else ""
        found[sid] = body
    errors = []
    missing = [s for s in expected if s not in found]
    extra = [s for s in found if s not in expected]
    if missing:
        errors.append(f"MISSING ids: {missing}")
    if extra:
        errors.append(f"EXTRA ids: {extra}")
    ok_ids = []
    for sid in expected:
        if sid not in found:
            continue
        body = clean(found[sid])
        if not body.startswith("---\n"):
            errors.append(f"{sid}: no frontmatter start"); continue
        end = body.find("\n---\n", 3)
        if end < 0:
            errors.append(f"{sid}: no frontmatter end"); continue
        fm = body[3:end+1]
        try:
            meta = yaml.safe_load(fm)
        except Exception as e:
            errors.append(f"{sid}: yaml fail {e}"); continue
        if not isinstance(meta, dict):
            errors.append(f"{sid}: frontmatter not map"); continue
        if str(meta.get("name")) != sid:
            errors.append(f"{sid}: name mismatch -> {meta.get('name')}"); continue
        desc = str(meta.get("description", ""))
        if len(desc) < 20:
            errors.append(f"{sid}: description too short ({len(desc)})"); continue
        lic = (meta.get("metadata") or {}).get("license") if isinstance(meta.get("metadata"), dict) else None
        if lic != "AGPL-3.0":
            errors.append(f"{sid}: license not AGPL-3.0 -> {lic}"); continue
        src_text = open(os.path.join(SRC, expected[sid]), encoding="utf-8").read()
        hits = copy13_check(src_text, body)
        if hits:
            errors.append(f"{sid}: COPY13 violation: {hits[0][:80]}..."); continue
        ok_ids.append(sid)
    if errors:
        print(f"BATCH {batch} FAILED:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    for sid in ok_ids:
        d = os.path.join(DST, sid)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8").write(clean(found[sid]))
    print(f"BATCH {batch} OK: wrote {len(ok_ids)} skills")

main()
