"""Caption words for a reel: wording from the long form's full context Scribe transcript (what the speaker
said, already checked against the rough cut), timing from a Scribe pass of the reel audio itself.

Usage: python3 caption_words.py <expected_words.json> <reel_scribe.json> <out.json> [fix.json]
expected_words.json: {"words": [{text, start, end}]} on the REEL timeline (long form words mapped)
fix.json (optional): {"replace": [[index_in_expected, "new text", "why"]]}
Writes {"words": [...], "diff": [...]}; prints every place the two transcripts disagree.
"""
import json, re, sys, difflib
exp = json.load(open(sys.argv[1]))["words"]
rs = [w for w in json.load(open(sys.argv[2]))["words"] if w["type"] == "word"]
fix = json.load(open(sys.argv[4])) if len(sys.argv) > 4 else {"replace": []}
n = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
sm = difflib.SequenceMatcher(None, [n(w["text"]) for w in exp], [n(w["text"]) for w in rs], autojunk=False)
out = [dict(text=w["text"], start=w["start"], end=w["end"], timing="long form mapped") for w in exp]
diff = []
for op, i1, i2, j1, j2 in sm.get_opcodes():
    if op == "equal":
        for i, j in zip(range(i1, i2), range(j1, j2)):
            out[i]["start"], out[i]["end"], out[i]["timing"] = rs[j]["start"], rs[j]["end"], "reel scribe"
    else:
        diff.append({"op": op, "long_form": " ".join(w["text"] for w in exp[i1:i2]), "reel_scribe": " ".join(w["text"] for w in rs[j1:j2]),
                     "reel_t": round(exp[i1]["start"] if i1 < len(exp) else rs[j1]["start"], 2)})
for i, txt, why in fix["replace"]:
    out[i]["text_was"] = out[i]["text"]; out[i]["text"] = txt; out[i]["fix"] = why
# an empty replacement merges that word into the one before it (for example "twenty-four" "seven" -> "24/7")
merged = []
for w in out:
    if w["text"] == "" and merged:
        merged[-1]["end"] = max(merged[-1]["end"], w["end"])
        merged[-1].setdefault("merged", []).append(w.get("text_was"))
    else:
        merged.append(w)
out = merged
matched = sum(1 for w in out if w["timing"] == "reel scribe")
json.dump({"words": out, "diff": diff, "matched": matched, "total": len(out)}, open(sys.argv[3], "w"), indent=1)
print(f"{matched} of {len(out)} long form words matched the reel Scribe pass")
for d in diff:
    print(f"  {d['reel_t']:6.2f}s {d['op']:8s} long form: {d['long_form']!r:40s} reel Scribe: {d['reel_scribe']!r}")
