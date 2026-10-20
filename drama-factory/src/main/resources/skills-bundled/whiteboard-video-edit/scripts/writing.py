"""When is the speaker writing at (or pointing into) which board item? Wrist joint inside an item rect
(plus a margin) with the arm reaching screen-left of the speaker's shoulders, from frames/pose_4fps.jsonl.
Usage: python3 writing.py <edit_dir>; prints intervals and writes frames/writing_intervals.json.
Use it to time item focus events (tools/focus_<label>.json)."""
import json, sys
E = sys.argv[1]
board = json.load(open(f"{E}/tools/board.json"))
items = [k for k in board if not k.startswith("_") and k != "board"]  # every measured item except the whole board
rows = [json.loads(l) for l in open(f"{E}/frames/pose_4fps.jsonl")]
rows.sort(key=lambda r: r["path"])
M = 90  # margin px
hits = []
for k, r in enumerate(rows):
    t = k / 4.0
    j = r.get("joints", {})
    found = None
    for wr, el in (("rWr", "rEl"), ("lWr", "lEl")):
        if wr not in j or j[wr][2] < 0.3: continue
        x, y = j[wr][0] * 3840, j[wr][1] * 2160
        sh = [j[n][0] * 3840 for n in ("lSh", "rSh") if n in j and j[n][2] > 0.3]
        if not sh: continue
        reach = x < min(sh) - 220  # arm extended screen-left of the speaker's shoulders, toward the board
        raised = el in j and j[el][1] * 2160 > y - 40 and reach
        for it in items:
            x0, y0, x1, y1 = board[it]
            if x0 - M <= x <= x1 + M and y0 - M <= y <= y1 + M and raised:
                found = it; break
        if found: break
    hits.append((t, found))
# merge into intervals (allow 0.5 s gaps), keep >= 0.75 s
iv = []
for t, it in hits:
    if not it: continue
    if iv and iv[-1][2] == it and t - iv[-1][1] <= 0.75:
        iv[-1][1] = t
    else:
        iv.append([t, t, it])
iv = [v for v in iv if v[1] - v[0] >= 0.5]
for a, b, it in iv: print(f"{a:7.2f}-{b+0.25:7.2f} {it}")
json.dump([{"start": a, "end": b + 0.25, "item": it} for a, b, it in iv], open(f"{E}/frames/writing_intervals.json", "w"), indent=1)
