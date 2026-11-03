"""Word timestamps for narration you already have: forced alignment of known text to its audio.

Most TTS engines (Kokoro included) return audio without word times. Captions that light word by word, and
scene beats keyed to a spoken word, need them. This aligns each segment's script text to its clip with
PocketSphinx (offline, `pip install pocketsphinx`, its English model ships inside the wheel), and falls back to
spreading words by spoken weight between the clip's measured pauses when alignment can't run.

    words = align_clip("narration/s03.mp3", "Behind that one message is a subscription business...")
    # [{"w": "Behind", "t0": 0.0, "t1": 0.64}, ...]   times in seconds from the clip's start

Each result says how it was timed ("align" or "spread"); spread times are good to about 0.15 s.
"""
import re
import subprocess
import wave
from pathlib import Path

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def say_int(n):
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + say_int(n % 100))
    for size, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        if n >= size:
            return say_int(n // size) + " " + name + ("" if n % size == 0 else " " + say_int(n % size))
    return str(n)


def spoken(token):
    """One written token -> the words a narrator says for it ("$4.12" -> four dollars twelve cents)."""
    t = token.lower().strip(".,;:!?\"'()[]“”‘’—–")
    t = t.replace("’", "'")
    if not t:
        return []
    m = re.fullmatch(r"\$([\d,]+)(?:\.(\d\d))?([kmb])?", t)
    if m:
        n = int(m.group(1).replace(",", ""))
        out = say_int(n).split()
        if m.group(3):
            out += [{"k": "thousand", "m": "million", "b": "billion"}[m.group(3)]]
        out += ["dollar" if n == 1 and not m.group(3) else "dollars"]
        if m.group(2) and int(m.group(2)):
            out += say_int(int(m.group(2))).split() + ["cents"]
        return out
    m = re.fullmatch(r"([\d,]+)(?:\.(\d+))?(%|percent)?", t)
    if m and m.group(1).replace(",", "").isdigit():
        raw = m.group(1).replace(",", "")
        n = int(raw)
        if len(raw) == 4 and 1900 <= n <= 2099 and "," not in m.group(1) and not m.group(2):
            out = (say_int(n // 100) + " " + ("hundred" if n % 100 == 0 else ("oh " + ONES[n % 100] if n % 100 < 10 else say_int(n % 100)))).split()
        else:
            out = say_int(n).split()
        if m.group(2):
            out += ["point"] + [ONES[int(d)] for d in m.group(2)]
        if m.group(3):
            out += ["percent"]
        return out
    m = re.fullmatch(r"(\d+)(st|nd|rd|th)", t)
    if m:
        return say_int(int(m.group(1))).split()
    return [w for w in re.split(r"[^a-z0-9']+", t) if w]


def tokens(text):
    """Written tokens as they should appear in a caption, each with its spoken words."""
    out = []
    for tok in text.replace("—", " — ").split():
        words = spoken(tok)
        if tok in ("—", "–"):
            continue
        out.append({"w": tok, "say": words})
    return out


def to_wav16k(src, dest):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", str(dest)], check=True)


def pauses(wav_path, frame=0.02, floor_db=-38.0, min_len=0.12):
    """Silent stretches [(t0, t1)] from a plain energy envelope."""
    import numpy as np
    with wave.open(str(wav_path)) as w:
        sr, x = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    n = int(sr * frame)
    if len(x) < n:
        return [], len(x) / sr
    e = x[: len(x) // n * n].reshape(-1, n)
    db = 20 * np.log10(np.sqrt((e ** 2).mean(axis=1)) + 1e-9)
    ref = np.percentile(db, 95)
    quiet = db < max(floor_db, ref - 30)
    out, start = [], None
    for i, q in enumerate(list(quiet) + [False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * frame >= min_len:
                out.append((start * frame, i * frame))
            start = None
    return out, len(x) / sr


def weight(word):
    return 0.12 + 0.045 * len(re.sub(r"[^a-z0-9]", "", word.lower())) + (0.25 if word[-1:] in ",;:" else 0) + (0.35 if word[-1:] in ".!?" else 0)


def spread(toks, wav_path):
    """Fallback: speech runs between measured pauses, words spread inside by spoken weight."""
    gaps, dur = pauses(wav_path)
    t0 = gaps[0][1] if gaps and gaps[0][0] < 0.05 else 0.0
    t1 = gaps[-1][0] if gaps and gaps[-1][1] > dur - 0.05 else dur
    ws = [weight(" ".join(t["say"]) + t["w"][-1:]) for t in toks]
    total, acc, out = sum(ws) or 1, t0, []
    for t, w in zip(toks, ws):
        d = (t1 - t0) * w / total
        out.append({"w": t["w"], "t0": round(acc, 3), "t1": round(acc + d * 0.92, 3)})
        acc += d
    return out


YEAR = re.compile(r"(19|20)\d\d")


def _onset_error(words, gaps):
    """mean distance from each measured speech onset (end of a pause) to the nearest word start"""
    ons = [b for a, b in gaps if a > 0.05]
    if not ons or not words:
        return 0.0
    return sum(min(abs(w["t0"] - t) for w in words) for t in ons) / len(ons)


def _snap(words, gaps, dur):
    """Pull word edges onto measured silence: a word never starts inside a pause or ends deep into one.
    The aligner hands leading silence to the first word and pause time to the word before it."""
    for a, b in gaps:
        for w in words:
            if a - 0.02 <= w["t0"] < b:          # starts in the pause: move to where speech resumes
                w["t0"] = round(min(b, w["t1"] - 0.05), 3)
            if a < w["t1"] <= b + 0.02 and w["t0"] < a:   # runs into the pause: end where it goes quiet
                w["t1"] = round(a + 0.08, 3)
    return words


def align_clip(clip, text, work=None):
    """Align `text` to `clip`; returns (words, method)."""
    clip = Path(clip)
    work = Path(work or clip.parent)
    wav = work / f".{clip.stem}.16k.wav"
    to_wav16k(clip, wav)
    toks = tokens(text)
    gaps, dur = pauses(wav)
    try:
        words = _sphinx(toks, wav)
        method = "align"
        # a year can be read "twenty twenty-five" or "two thousand twenty-five": try the other reading and keep
        # whichever lands word starts on the measured pauses
        years = [i for i, t in enumerate(toks) if YEAR.fullmatch(t["w"].strip(".,;:!?"))]
        if years:
            alt = [dict(t) for t in toks]
            for i in years:
                alt[i]["say"] = say_int(int(toks[i]["w"].strip(".,;:!?"))).split()
            try:
                w2 = _sphinx(alt, wav)
                if _onset_error(w2, gaps) < _onset_error(words, gaps) - 0.01:
                    words = w2
            except Exception:
                pass
        words = _snap(words, gaps, dur)
    except Exception as e:                                   # no pocketsphinx, or the aligner gave up
        words, method = spread(toks, wav), "spread"
        print(f"  {clip.name}: alignment unavailable ({e}); spread by weight")
    wav.unlink(missing_ok=True)
    return words, method


def _sphinx(toks, wav):
    from pocketsphinx import Decoder
    d = Decoder(samprate=16000, bestpath=False, loglevel="FATAL")
    flat, owner = [], []                                     # spoken words the dictionary knows, and their token
    for i, t in enumerate(toks):
        for w in t["say"]:
            if d.lookup_word(w):
                flat.append(w); owner.append(i)
    if not flat:
        raise RuntimeError("no dictionary words")
    d.set_align_text(" ".join(flat))
    with wave.open(str(wav)) as w:
        data, dur = w.readframes(w.getnframes()), w.getnframes() / 16000
    d.start_utt(); d.process_raw(data, full_utt=True); d.end_utt()
    segs = [s for s in d.seg() if not s.word.startswith("<") and s.word not in ("[NOISE]",)]
    if len(segs) != len(flat):
        raise RuntimeError(f"aligned {len(segs)} of {len(flat)} words")
    span = {}
    for s, i in zip(segs, owner):
        a, b = s.start_frame / 100, (s.end_frame + 1) / 100
        lo, hi = span.get(i, (a, b))
        span[i] = (min(lo, a), max(hi, b))
    # tokens the dictionary didn't know (names, codes): share the gap between their timed neighbours
    out, i = [], 0
    while i < len(toks):
        if i in span:
            out.append({"w": toks[i]["w"], "t0": round(span[i][0], 3), "t1": round(span[i][1], 3)}); i += 1; continue
        j = i
        while j < len(toks) and j not in span:
            j += 1
        a = span[i - 1][1] if i > 0 else 0.0
        b = span[j][0] if j < len(toks) else dur
        step = (b - a) / (j - i) if j > i else 0
        for k in range(i, j):
            out.append({"w": toks[k]["w"], "t0": round(a + (k - i) * step, 3), "t1": round(a + (k - i + 1) * step, 3)})
        i = j
    return out
