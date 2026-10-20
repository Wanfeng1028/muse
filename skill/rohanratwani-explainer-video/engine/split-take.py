"""Split one continuous voiceover take into per-beat clips, keeping the last try of any line.

    python engine/split-take.py <take.(m4a|wav)> <lines.json> <out_vo_dir>

You read the whole read-aloud.md in one go and re-say any sentence you fumble. This finds each
beat's words in the take, in order, prefers a later retake over an earlier fumble, and writes
<out_vo_dir>/<id>.wav + durations.json + words.json: the same files tts.py + align.py write, so
`node build.mjs --voice <name>` and mix.py work unchanged.

The take can be quiet: loudnorm.py sets the level on the mixed master afterwards.
"""
import difflib, json, os, re, subprocess, sys
from faster_whisper import WhisperModel

take, lines_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(out, exist_ok=True)
lines = json.load(open(lines_path, encoding="utf8"))
norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())

wav = os.path.join(out, "_take.wav")
subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", take, "-vn", "-ac", "1", "-ar", "48000", wav], check=True)
model = WhisperModel("small.en", device="cpu", compute_type="int8")
segs, info = model.transcribe(wav, word_timestamps=True, language="en", beam_size=5)
T = [{"w": w.word.strip(), "n": norm(w.word), "s": w.start, "e": w.end} for s in segs for w in s.words]
T = [t for t in T if t["n"]]
toks = [t["n"] for t in T]
print(f"take: {info.duration:.1f}s, {len(T)} words heard")

def score(beat, i, j):
    # letters, not words: whisper splits and merges words ("ChatGPT" -> "chat GPT", "4,000" -> "4" ",000")
    return difflib.SequenceMatcher(None, "".join(beat), "".join(toks[i:j]), autojunk=False).ratio()

cursor, picks = 0, []
for ln in lines:
    beat = [norm(w) for w in (ln.get("text") or ln["say"]).split() if norm(w)]
    n = len(beat)
    cands = []
    for i in range(cursor, min(len(toks), cursor + 3 * n + 25)):
        for L in range(max(1, n - 3), n + 4):
            if i + L <= len(toks):
                cands.append((score(beat, i, i + L), i, i + L))
    if not cands:
        sys.exit(f"ran out of take at {ln['id']}")
    best = max(cands)
    # a retake of the same line scores about as well and starts later: keep the later one
    near = [c for c in cands if c[0] >= best[0] - 0.08 and c[1] >= best[2]]
    pick = max(near, key=lambda c: (c[1], c[0])) if near else best
    if pick[0] < 0.6:
        print(f"  WARNING {ln['id']}: weak match {pick[0]:.2f}, check this line by ear")
    if pick is not best:
        print(f"  {ln['id']}: kept the retake at {T[pick[1]]['s']:.1f}s (fumble at {T[best[1]]['s']:.1f}s)")
    sc, i, j = pick
    # a misheard first word scores as noise, so the window can start one word late: pull back any
    # words spoken right before it (no real pause) that the previous beat didn't claim
    while i > cursor and T[i]["s"] - T[i - 1]["e"] < 0.45:
        i -= 1
    picks.append((ln["id"], (sc, i, j)))
    cursor = j

durs, words = {}, {}
for k, (bid, (sc, i, j)) in enumerate(picks):
    s0 = max(0.0, T[i]["s"] - 0.08)
    nxt = T[picks[k + 1][1][1]]["s"] if k + 1 < len(picks) else T[j - 1]["e"] + 0.3
    e0 = min(T[j - 1]["e"] + 0.15, nxt - 0.03)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", wav, "-af", f"atrim={s0:.3f}:{e0:.3f},asetpts=PTS-STARTPTS",
                    os.path.join(out, bid + ".wav")], check=True)
    durs[bid] = round(e0 - s0, 3)
    words[bid] = [{"w": t["w"], "s": round(t["s"] - s0, 3), "e": round(t["e"] - s0, 3)} for t in T[i:j]]
    print(f"{bid} {durs[bid]:6.2f}s  match {sc:.2f}  {' '.join(t['w'] for t in T[i:j])[:70]}")
json.dump(durs, open(os.path.join(out, "durations.json"), "w"), indent=1)
json.dump(words, open(os.path.join(out, "words.json"), "w"), indent=0)
os.remove(wav)
print(f"done: {len(picks)} beats, {sum(durs.values()):.1f}s of speech kept")
