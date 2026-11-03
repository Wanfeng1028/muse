"""Audit what a product video SAYS against what the product actually contains (T05).

The video must be rendered from an HTML page whose visual state is a pure function of
time (the round frame asks for `window.__setTime(t)`; `renderAt(t)` / `render(t)` are
also tried). The tool steps t over the film, collects every visible DOM text string
(text nodes and SVG <text>, visible = displayed, effective opacity > 0.05, inside the
viewport), and checks it against a product corpus (docs, UI string tables, demo data):

  - strings: normalised (NFKC, whitespace squeezed); "found" when the string, or every
    CJK/Latin run of it longer than 1 char, occurs in the corpus
  - numbers: every numeric token with a unit/percent or a value >= 10 must occur as a
    whole number token in the NUMBER corpus (commas stripped). The number corpus is
    `number_globs` (docs + UI string tables) when the spec gives it, else the whole corpus.
    Code and demo logs are full of digits, so matching numbers against them lets almost
    any short number pass (r4-dit: an invented "48" passed). Clock times and dates
    (10:00, 9/28, 2026-06-25, 2026-06-25T10:00:08.000Z) are counted separately as `time_labels`, not checked. Exception: a whole
    string (with words, >= 12 chars) that occurs verbatim in the full corpus, e.g. a raw
    demo-log line shown as is, is a quote and its numbers count as sourced
    (`n_verbatim_quotes`); a bare number never qualifies
  - steady strings: only strings visible in >= 2 samples count, so half-typed words are
    not audited as claims
  - counters: a run of consecutive samples in which a string with the same digit
    skeleton ("你按了 # 次") keeps changing value is a count-up; its final value is
    audited even when no single value stayed for 2 samples
  - scope words (T05 rule 8): strings containing 全程/所有/任何/完全/永遠/一律/always/every/
    all/never/entire... are listed for a reader, with a flag when the whole string is
    verbatim in the corpus (a UI label or a doc sentence)
  - optional features (T05 rule 4): for each feature in `optional_features`, every sample
    where it is mentioned on screen is checked for an optional marker (選配/需自行安裝/
    自帶金鑰/optional...) visible in the SAME sample; unmarked samples are listed

What it can determine: whether on-screen text and numbers exist in the product corpus;
whether an optional feature is mentioned without a marker on the same frame.
What it cannot: whether a sentence OVERSTATES a real feature (scope-word hits are a review
list, not a verdict), text drawn into <canvas> or baked into images (reported as
`canvas_present` / `images`; a real product capture is an image and is not audited
here), numbers the product computes at runtime (they land in `unsourced_numbers` for
review), a marker placed on a different frame than the mention.
Severity: every list is a review list (WARN); no FAIL verdict.

Usage:
    python -X utf8 scripts/fidelity.py <index.html> --corpus <corpus.json> --out <dir> [--dur 48 --step 0.25]
    python -X utf8 scripts/fidelity.py --selftest
corpus.json: {"root": "<dir>", "globs": [...], "number_globs": [...],
              "optional_features": [{"name": "Ollama", "patterns": ["Ollama"]}],
              "optional_markers": [...]}   # markers default to OPTIONAL_MARKERS
"""
import argparse
import glob
import json
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

HOOKS = ["__setTime", "renderAt", "render"]
NUM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|％|x|×|倍|秒|分鐘|分|小時|天|MiB|MB|KB|GB|筆|次|人|個|步|台|種|行|token|tokens)?", re.I)
NUM_TOKEN_RE = re.compile(r"(?<![\d.])\d[\d,]*(?:\.\d+)?(?![\d])")
CLOCK_RE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?Z?)?(?!\d)"
                      r"|(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)|(?<!\d)\d{1,2}/\d{1,2}(?!\d)")
MIN_SAMPLES = 2  # a string must stay on screen >= 2 samples (0.5 s at step 0.25): drops typing frames
COUNTER_GAP = 1  # samples a counter may skip and still be the same run
QUOTE_MIN = 12  # chars: a shorter string matching the corpus verbatim is too weak to source its numbers
RUN_RE = re.compile(r"[㐀-鿿豈-﫿]+|[A-Za-z][A-Za-z0-9'\-\.]*[A-Za-z0-9]|[A-Za-z]")
DIGITS_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
SCOPE_RE = re.compile(r"全程|所有|任何|完全|永遠|一律|全都|百分之百|絕不|always|every|entire|fully|never|\ball\b|\bany\b", re.I)
OPTIONAL_MARKERS = ["選配", "可選", "需自行", "自行安裝", "需安裝", "需要安裝", "另外安裝", "另行安裝", "自帶金鑰",
                    "需要你自己的", "需要自己的", "需另外", "optional", "requires", "bring your own"]

COLLECT_JS = r"""
() => {
  const out = [];
  const W = window.innerWidth, H = window.innerHeight;
  const opacityOf = (el) => { let o = 1; for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
      o *= parseFloat(cs.opacity || '1'); } return o; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = walker.nextNode())) {
    const s = n.nodeValue.replace(/\s+/g, ' ').trim(); if (!s) continue;
    const el = n.parentElement; if (!el || ['SCRIPT','STYLE','NOSCRIPT','TITLE'].includes(el.tagName)) continue;
    if (opacityOf(el) <= 0.05) continue;
    const r = document.createRange(); r.selectNodeContents(n); const b = r.getBoundingClientRect();
    if (b.width < 1 || b.height < 1 || b.right < 0 || b.bottom < 0 || b.left > W || b.top > H) continue;
    out.push(s);
  }
  return {texts: out, canvas: document.querySelectorAll('canvas').length,
          images: Array.from(document.images).filter(i => opacityOf(i) > 0.05).map(i => i.getAttribute('src') || '')};
}
"""


def norm(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip().lower()


def read_globs(root, globs):
    files = []
    for g in globs:
        files += [Path(p) for p in glob.glob(str(root / g), recursive=True)]
    files = sorted(set(p for p in files if p.is_file()))
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in files), [str(p) for p in files]


def load_corpus(spec_path):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    root = Path(spec["root"])
    text, files = read_globs(root, spec["globs"])
    if spec.get("number_globs"):
        ntext, nfiles = read_globs(root, spec["number_globs"])
    else:
        ntext, nfiles = text, files
    numbers = {m.group(0).replace(",", "") for m in NUM_TOKEN_RE.finditer(CLOCK_RE.sub(" ", unicodedata.normalize("NFKC", ntext)))}
    return {"text": norm(text), "files": files, "numbers": numbers, "number_files": nfiles,
            "optional_features": spec.get("optional_features", []),
            "optional_markers": [norm(m) for m in spec.get("optional_markers", OPTIONAL_MARKERS)]}


def string_found(s, corpus):
    n = norm(s)
    if n in corpus:
        return True
    runs = [r for r in RUN_RE.findall(n) if len(r) > 1]
    # a string with no word runs (a bare number, a clock time) is judged by the number check alone
    return all(r in corpus for r in runs)


def verbatim_quote(s, corpus):
    """A whole on-screen string (with words, >= QUOTE_MIN chars) that occurs verbatim in the full
    corpus, e.g. a raw demo-log line: numbers inside it come from the product, even when the
    demo data is outside the number corpus. A bare number never qualifies."""
    n = norm(s)
    return len(n) >= QUOTE_MIN and bool(RUN_RE.findall(n)) and n in corpus


def numbers_in(s):
    out = []
    for m in NUM_RE.finditer(CLOCK_RE.sub(" ", unicodedata.normalize("NFKC", s))):
        raw, unit = m.group(1), m.group(2)
        val = float(raw.replace(",", "")) if raw.replace(",", "").replace(".", "", 1).isdigit() else 0
        if unit or val >= 10:
            out.append(raw.replace(",", ""))
    return out


def skeleton(s):
    return DIGITS_RE.sub("#", s) if DIGITS_RE.search(s) else None


def counters(samples, steady):
    """Runs of samples where one digit skeleton keeps changing value; return the final value of each run."""
    runs, open_runs = [], {}
    for i, (t, texts) in enumerate(samples):
        for s in set(texts):
            k = skeleton(s)
            if k is None:
                continue
            r = open_runs.get(k)
            if r and i - r["last_i"] <= 1 + COUNTER_GAP:
                if s != r["last"]:
                    r["values"].append(s)
                r.update(last=s, last_i=i, last_t=t)
            else:
                if r:
                    runs.append(r)
                open_runs[k] = {"skeleton": k, "first_t": t, "last_t": t, "last_i": i, "last": s, "values": [s]}
    runs += open_runs.values()
    out = []
    for r in runs:
        if len(r["values"]) >= 2 and r["last"] not in steady:
            out.append({"t": r["first_t"], "end_t": r["last_t"], "text": r["last"], "n_values": len(r["values"]),
                        "first_value": r["values"][0]})
    return out


def collect(html, dur, step, viewport=(1280, 720)):
    from playwright.sync_api import sync_playwright
    seen, count, samples = {}, {}, []
    canvas, images, hook = 0, set(), None
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        pg.goto(Path(html).resolve().as_uri())
        pg.wait_for_timeout(800)
        for h in HOOKS:
            if pg.evaluate(f"typeof window.{h} === 'function'"):
                hook = h
                break
        if hook is None:
            b.close()
            return None
        t = 0.0
        while t <= dur + 1e-9:
            pg.evaluate(f"(t) => window.{hook}(t)", t)
            pg.wait_for_timeout(15)
            r = pg.evaluate(COLLECT_JS)
            canvas = max(canvas, r["canvas"])
            images.update(r["images"])
            samples.append((round(t, 2), r["texts"]))
            for s in set(r["texts"]):
                seen.setdefault(s, round(t, 2))
                count[s] = count.get(s, 0) + 1
            t += step
        b.close()
    steady = {s: t for s, t in seen.items() if count[s] >= MIN_SAMPLES}
    return {"hook": hook, "first_seen": steady, "n_transient": len(seen) - len(steady), "samples": samples,
            "counters": counters(samples, steady), "canvas_present": canvas, "images": sorted(images)}


def optional_check(samples, features, markers):
    out = {}
    for f in features:
        pats = [norm(p) for p in f["patterns"]]
        mentioned, marked, unmarked_t = 0, 0, []
        for t, texts in samples:
            joined = [norm(s) for s in texts]
            if not any(p in s for p in pats for s in joined):
                continue
            mentioned += 1
            if any(m in s for m in markers for s in joined):
                marked += 1
            else:
                unmarked_t.append(t)
        out[f["name"]] = {"samples_mentioned": mentioned, "samples_marked": marked,
                          "samples_unmarked": len(unmarked_t), "unmarked_t": unmarked_t[:40]}
    return out


def audit(html, corpus_spec, dur=48.0, step=0.25, viewport=(1280, 720)):
    c = load_corpus(corpus_spec)
    corpus = c["text"]
    got = collect(html, dur, step, viewport)
    if got is None:
        return {"status": "UNDET", "reason": f"no time hook ({', '.join(HOOKS)}) on the page", "corpus_files": c["files"]}
    strings, not_found, unsourced, scope, clocks = [], [], [], [], 0

    def check_numbers(s, t, origin):
        for num in numbers_in(s):
            if num not in c["numbers"]:
                unsourced.append({"t": t, "number": num, "text": s, "origin": origin})

    quoted = 0
    for s, t in sorted(got["first_seen"].items(), key=lambda kv: kv[1]):
        f = string_found(s, corpus)
        strings.append({"t": t, "text": s, "found": f})
        if not f:
            not_found.append({"t": t, "text": s})
        clocks += len(CLOCK_RE.findall(unicodedata.normalize("NFKC", s)))
        if verbatim_quote(s, corpus):
            quoted += 1  # a demo-log line or doc sentence shown as is: its numbers are sourced by the quote
        else:
            check_numbers(s, t, "steady")
        m = SCOPE_RE.search(unicodedata.normalize("NFKC", s))
        if m:
            scope.append({"t": t, "text": s, "word": m.group(0), "verbatim_in_corpus": norm(s) in corpus})
    for k in got["counters"]:
        check_numbers(k["text"], k["t"], "counter-final")
    opt = optional_check(got["samples"], c["optional_features"], c["optional_markers"])
    n = len(strings)
    return {
        "status": "OK", "hook": got["hook"], "n_strings": n,
        "share_found": round(sum(x["found"] for x in strings) / n, 3) if n else None,
        "n_not_found": len(not_found), "n_unsourced_numbers": len(unsourced), "time_labels": clocks,
        "n_transient_strings": got["n_transient"], "n_counters": len(got["counters"]),
        "n_scope_words": len(scope), "n_scope_words_own": sum(not x["verbatim_in_corpus"] for x in scope),
        "n_verbatim_quotes": quoted,
        "n_optional_unmarked_samples": sum(v["samples_unmarked"] for v in opt.values()),
        "not_found": not_found, "unsourced_numbers": unsourced, "counters": got["counters"],
        "scope_words": scope, "optional_features": opt,
        "canvas_present": got["canvas_present"], "images": got["images"],
        "strings": strings, "corpus_files": c["files"], "number_corpus_files": c["number_files"],
        # per sample, the visible text nodes joined in DOM order with no separator: a word animated one span per
        # character ("書" + "角") reads as one string here (r10-c21 A1), at the cost of joining neighbours
        "sample_text": [[t, "".join(texts)] for t, texts in got["samples"]],
        "limits": "canvas/image text not audited; runtime-computed numbers appear as unsourced; "
                  "a phrase recombined from corpus words passes the string check; scope words are a review list; "
                  "an optional marker on a different frame than the mention is not seen; "
                  "semantic overstatement not judged (forward to a reader)",
    }


PAGE = """<!doctype html><html><body style="margin:0;width:1280px;height:720px;font:32px sans-serif">
<div id="a" style="position:absolute;left:40px;top:40px"></div>
<div id="b" style="position:absolute;left:40px;top:200px"></div>
<div id="c" style="position:absolute;left:40px;top:300px"></div>
<div id="d" style="position:absolute;left:40px;top:500px"></div>
<div id="h" style="position:absolute;left:40px;top:400px;opacity:0">hidden text 999%</div>
<script>
window.__setTime = function (t) {
  document.getElementById('a').textContent = t < 1 ? 'LINE_A' : 'LINE_B';
  document.getElementById('b').textContent = t < 1 ? 'NUM_A' : 'NUM_B';
  document.getElementById('c').textContent = t < 0.4 ? String(Math.round(t * 700)) + ' 筆' : '312 筆（10:00）';
  document.getElementById('d').textContent = t < 2 ? '你按了 ' + String(Math.round(12 * (t / 0.5 + 1))) + ' 次' : 'COUNTER_END';
};
</script></body></html>"""


DEMO_LINE = '{"step":"build","ms":4321,"note":"編譯完成"}'


def selftest():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "product.md").write_text("格點 Gridlab 器材日曆：一眼看完 8 台儀器。本月衝突 0 筆，使用率 71%，總預約 312 筆。"
                                       "可接 Ollama 講解（選配）。你按了 次 結束", encoding="utf-8")
        (td / "app.js").write_text("const retries = 48; const width = 95; // 你按了 次", encoding="utf-8")
        (td / "demo.jsonl").write_text(DEMO_LINE + "\n", encoding="utf-8")
        spec = {"root": str(td), "globs": ["product.md", "app.js", "demo.jsonl"], "number_globs": ["product.md"],
                "optional_features": [{"name": "Ollama", "patterns": ["Ollama"]}]}
        (td / "corpus.json").write_text(json.dumps(spec), encoding="utf-8")
        # counter: 12, 24, 36, 48 at t = 0, 0.5, 1, 1.5 (one sample each at step 0.5), then gone
        cases = [
            # name, lines, numbers, counter end text, want: not_found, unsourced, scope, optional_unmarked
            # the ISO date is a time label (T05 rule 3), not an unsourced 2026 / 25
            ("known-true", ["器材日曆 2026-06-25", "一眼看完 8 台儀器"], ["使用率 71%", "312 筆"], "結束", 0, 0, 0, 0),
            ("known-false", ["器材日曆", "AI 自動排程"], ["使用率 95%", "312 筆"], "結束", 1, 2, 0, 0),
            # '全程本地處理' is not in the corpus (1 not found); Ollama shown at t = 1, 1.5, 2 with no marker (3 samples)
            ("scope-and-optional", ["全程本地處理", "可接 Ollama 講解"], ["使用率 71%", "312 筆"], "結束", 1, 1, 1, 3),
            ("optional-marked", ["器材日曆", "可接 Ollama 講解（選配）"], ["使用率 71%", "312 筆"], "結束", 0, 1, 0, 0),
            # a demo-log line shown verbatim sources its 4321; the same number shown bare does not (1 unsourced)
            ("verbatim-demo-quote", ["器材日曆", DEMO_LINE], ["使用率 71%", "4321"], "結束", 0, 1, 0, 0),
        ]
        for name, (la, lb), (na, nb), end, want_nf, want_un, want_sc, want_opt in cases:
            html = PAGE.replace("LINE_A", la).replace("LINE_B", lb).replace("NUM_A", na).replace("NUM_B", nb)
            html = html.replace("COUNTER_END", end)
            if name in ("known-true", "verbatim-demo-quote"):  # no counter on these pages
                html = html.replace("t < 2 ? '你按了 '", "false ? '你按了 '")
            (td / f"{name}.html").write_text(html, encoding="utf-8")
            r = audit(td / f"{name}.html", td / "corpus.json", dur=2.0, step=0.5)
            good = (r["status"] == "OK" and r["n_not_found"] == want_nf and r["n_unsourced_numbers"] == want_un
                    and r["n_scope_words"] == want_sc and r["n_optional_unmarked_samples"] == want_opt
                    and not any("999" in x["text"] for x in r["strings"]))
            print(f"{name}: not found {r['n_not_found']} (want {want_nf}), unsourced "
                  f"{[(x['number'], x['origin']) for x in r['unsourced_numbers']]} (want {want_un}), scope {r['n_scope_words']} "
                  f"(want {want_sc}), optional unmarked samples {r['n_optional_unmarked_samples']} (want {want_opt}) "
                  f"-> {'ok' if good else 'FAIL'}")
            ok &= good
        # number corpus: '95' and '48' exist in app.js (code) but not in product.md -> must still be unsourced
        r = audit(td / "known-false.html", td / "corpus.json", dur=2.0, step=0.5)
        nums = sorted(x["number"] for x in r["unsourced_numbers"])
        good = nums == ["48", "95"] and any(x["origin"] == "counter-final" for x in r["unsourced_numbers"])
        print(f"code-only numbers stay unsourced and the counter final value is audited: {nums} -> {'ok' if good else 'FAIL'}")
        ok &= good
        (td / "nohook.html").write_text("<html><body>器材日曆</body></html>", encoding="utf-8")
        r = audit(td / "nohook.html", td / "corpus.json", dur=1.0, step=0.5)
        good = r["status"] == "UNDET"
        print(f"no time hook -> status {r['status']} (want UNDET, not a verdict) -> {'ok' if good else 'FAIL'}")
        ok &= good
        # viewport (r11 vertical 1080x1920): text at y=1500 is inside a 1080x1920 viewport, outside 1280x720
        (td / "tall.html").write_text('<html><body style="margin:0"><div style="position:absolute;top:1500px">'
                                      '器材日曆</div><script>window.__setTime=function(t){}</script></body></html>',
                                      encoding="utf-8")
        seen_tall = [x["text"] for x in audit(td / "tall.html", td / "corpus.json", 1.0, 0.5, (1080, 1920))["strings"]]
        seen_wide = [x["text"] for x in audit(td / "tall.html", td / "corpus.json", 1.0, 0.5)["strings"]]
        good = seen_tall == ["器材日曆"] and seen_wide == []
        print(f"viewport: y=1500 seen at 1080x1920 {seen_tall}, not at 1280x720 {seen_wide} -> {'ok' if good else 'FAIL'}")
        ok &= good
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", nargs="?")
    ap.add_argument("--corpus")
    ap.add_argument("--out")
    ap.add_argument("--dur", type=float, default=48.0)
    ap.add_argument("--step", type=float, default=0.25)
    ap.add_argument("--viewport", default="1280x720", help="WxH of the page, e.g. 1080x1920 for a vertical video")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    r = audit(a.html, a.corpus, a.dur, a.step, tuple(int(v) for v in a.viewport.lower().split("x")))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "fidelity.json").write_text(json.dumps(r, indent=1, ensure_ascii=False), encoding="utf-8")
    skip = ("strings", "corpus_files", "number_corpus_files", "not_found", "unsourced_numbers", "counters",
            "scope_words", "optional_features")
    print(json.dumps({k: r[k] for k in r if k not in skip}, ensure_ascii=False))


if __name__ == "__main__":
    main()
