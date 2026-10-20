"""Diff the kept words of a cut (cut_words.json, output timeline) against a fresh Scribe
transcript of the rendered file. Prints every non-equal opcode with output times."""
import json, re, sys, difflib
kept_path, fresh_path = sys.argv[1], sys.argv[2]
norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower().replace("-", ""))
def load(p, key="words"):
    ws = [w for w in json.load(open(p))[key] if w.get("type") == "word"]
    out = []
    for w in ws:
        for part in w["text"].replace("-", " ").split():
            n = norm(part)
            if n: out.append((n, w["start"], w["text"].strip()))
    return out
a, b = load(kept_path), load(fresh_path)
sm = difflib.SequenceMatcher(a=[x[0] for x in a], b=[x[0] for x in b], autojunk=False)
eq = sum(i2 - i1 for t, i1, i2, j1, j2 in sm.get_opcodes() if t == "equal")
print(f"kept words {len(a)}, fresh transcript words {len(b)}, matched {eq} ({100*eq/len(a):.1f}% of kept)")
for t, i1, i2, j1, j2 in sm.get_opcodes():
    if t == "equal": continue
    ta = " ".join(x[2] for x in a[i1:i2]); tb = " ".join(x[2] for x in b[j1:j2])
    at = a[i1][1] if i1 < len(a) else a[-1][1]
    ctx = " ".join(x[2] for x in a[max(0,i1-4):i1]) + " [...] " + " ".join(x[2] for x in a[i2:i2+4])
    print(f"  {t:7} @{at:7.2f}s  kept: '{ta}'  fresh: '{tb}'   ctx: {ctx}")
