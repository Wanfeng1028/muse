"""Word anchors -> timeline seconds.

Words live in the clock of the media they were transcribed from (words.json `media`).
Every storyboard base clip whose `src` is that media exposes the words it contains on the
timeline:  t_timeline = clip.at + (t_media - clip.in).  Anchors address those words:

  {"word": i}                       word #i of words.json (0-based `i`), must be inside a clip
  {"text": "剪映", "occurrence": 2}  2nd occurrence (1-based, default 1) of the text among the
                                    words visible on the timeline, in timeline order
  optional on both: "edge": "start"|"end" (default start), "offset": seconds

Text matching is done on a normalised character stream (NFKC, lower-case, whitespace and
punctuation removed), so "剪映 Skill" matches the ASR words 剪 / 映 / sk / ill. A word's
duration is split evenly over its characters, so a match that starts inside a multi-char
word gets an interpolated time.
"""
import os
import re
import unicodedata

_PUNCT = re.compile(r"[\s　-〿！-／：-＠［-｀｛-･"
                    r"!-/:-@\[-`{-~‐-‧·]")


def norm(s):
    return _PUNCT.sub("", unicodedata.normalize("NFKC", s).lower())


def _same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


class AnchorError(ValueError):
    pass


class Words:
    def __init__(self, doc, clips):
        """doc: words.json dict; clips: resolved base clips [{src, in, out, at, id}] (src absolute)"""
        self.doc = doc
        media = doc.get("media")
        tl = []
        if doc.get("clock", "media") == "timeline" or not media:
            for w in doc["words"]:
                tl.append({"i": w["i"], "w": w["w"], "t0": w["s"], "t1": w["e"], "clip": None})
        else:
            for c in clips:
                if not _same(c["src"], media):
                    continue
                for w in doc["words"]:
                    if c["in"] - 1e-6 <= w["s"] < c["out"]:
                        tl.append({"i": w["i"], "w": w["w"], "t0": round(c["at"] + w["s"] - c["in"], 4),
                                   "t1": round(c["at"] + min(w["e"], c["out"]) - c["in"], 4), "clip": c.get("id")})
        tl.sort(key=lambda w: (w["t0"], w["i"]))
        self.timeline = tl
        self.by_i = {w["i"]: w for w in tl}
        chars = []
        for w in tl:
            n = norm(w["w"])
            if not n:
                continue
            d = (w["t1"] - w["t0"]) / len(n)
            for k, ch in enumerate(n):
                chars.append((ch, w["t0"] + k * d, w["t0"] + (k + 1) * d, w["i"]))
        self.chars = chars
        self.text = "".join(c[0] for c in chars)

    def find_text(self, q, occurrence=1):
        nq = norm(q)
        if not nq:
            raise AnchorError(f"empty text anchor {q!r}")
        pos, hits = 0, []
        while True:
            k = self.text.find(nq, pos)
            if k < 0:
                break
            hits.append(k)
            pos = k + len(nq)
        if len(hits) < occurrence:
            raise AnchorError(f"text {q!r} occurrence {occurrence} not found on the timeline (found {len(hits)}); "
                              f"timeline text: {self.text[:120]}…")
        k = hits[occurrence - 1]
        a, b = self.chars[k], self.chars[k + len(nq) - 1]
        return {"start": a[1], "end": b[2], "words": sorted({a[3], b[3]}), "hits": len(hits)}

    def resolve(self, ref):
        """anchor dict -> (seconds, debug)"""
        edge = ref.get("edge", "start")
        off = float(ref.get("offset", 0.0))
        if "word" in ref:
            w = self.by_i.get(int(ref["word"]))
            if not w:
                raise AnchorError(f"word #{ref['word']} is not inside any base clip on the timeline")
            t = w["t0"] if edge == "start" else w["t1"]
            return round(t + off, 4), {"word": w["i"], "w": w["w"]}
        if "text" in ref:
            h = self.find_text(ref["text"], int(ref.get("occurrence", 1)))
            t = h["start"] if edge == "start" else h["end"]
            return round(t + off, 4), {"text": ref["text"], "occurrence": int(ref.get("occurrence", 1)), "of": h["hits"], "words": h["words"]}
        raise AnchorError(f"not an anchor: {ref}")
