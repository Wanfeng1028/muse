"""Line level check: every phrase line of the rough cut (kept words, split on pauses >= 0.35 s)
must be present in the fresh transcript of the render. Prints lines whose words are under
80% matched, plus the totals."""
import json, re, sys, difflib
kept_path, fresh_path = sys.argv[1], sys.argv[2]
norm = lambda s: re.sub(r"[^a-z0-9']", "", s.lower().replace("-", ""))
def load(p):
    out = []
    for w in json.load(open(p))["words"]:
        if w.get("type") != "word": continue
        for part in w["text"].replace("-", " ").split():
            n = norm(part)
            if n: out.append((n, w["start"], w["end"], w["text"].strip()))
    return out
a, b = load(kept_path), load(fresh_path)
sm = difflib.SequenceMatcher(a=[x[0] for x in a], b=[x[0] for x in b], autojunk=False)
ok = [False] * len(a)
for t, i1, i2, j1, j2 in sm.get_opcodes():
    if t == "equal":
        for i in range(i1, i2): ok[i] = True
lines, cur = [], []
for i, x in enumerate(a):
    if cur and x[1] - a[cur[-1]][2] >= 0.35:
        lines.append(cur); cur = []
    cur.append(i)
lines.append(cur)
bad = 0
for L in lines:
    m = sum(ok[i] for i in L) / len(L)
    if m < 0.8:
        bad += 1
        print(f"  LOW {m:.0%} @{a[L[0]][1]:.2f}: {' '.join(a[i][3] for i in L)}")
print(f"{len(lines)} kept lines, {len(lines) - bad} at >= 80% word match, {bad} below; words matched {sum(ok)}/{len(a)}")
