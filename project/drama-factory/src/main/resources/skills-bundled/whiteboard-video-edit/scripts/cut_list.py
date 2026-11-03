"""cut-list.md from the RENDERED spans: every stretch of source that is not in the rough cut
(head, every gap between consecutive rendered segments, tail), with its reason taken from the
removed tokens inside it. Covers 100% of the removed time by construction.

Usage (from the edit dir): python3 cut_list.py <title> <source_transcript.json> [notes.md]
  <source_transcript.json>: the Scribe transcript of the SOURCE the rough cut was planned on
  (rough-cut/transcripts/<name>.json). notes.md (optional) is appended under "Notes" (kept on
  purpose, judgement calls); hand edits recorded in edl.json flags are listed automatically.
Reads rough-cut/edl.json, rough-cut/render_report.json, segments.json. Writes cut-list.md.
"""
import json, sys
from fractions import Fraction
from pathlib import Path
title, tr = sys.argv[1], sys.argv[2]
notes = ""
if len(sys.argv) > 3:
    if Path(sys.argv[3]).exists():
        notes = Path(sys.argv[3]).read_text()
    else:
        print(f"note: {sys.argv[3]} does not exist yet, the cut list has no Notes section (write it, then rerun)")
fps = Fraction(24000, 1001)
e = json.load(open('rough-cut/edl.json')); rep = json.load(open('rough-cut/render_report.json'))
segs = json.load(open('segments.json'))['segments']
src_dur = rep['source_duration_s']
spans, prev_end = [], 0.0
for g in segs:
    if g['src_start'] - prev_end > 0.0005:
        spans.append((prev_end, g['src_start']))
    prev_end = g['src_start'] + float(Fraction(g['frames']) / fps)
if src_dur - prev_end > 0.0005:
    spans.append((prev_end, src_dur))
toks = json.load(open(tr))['words']
wordtoks = [t for t in toks if t.get('type') == 'word']
removed = e['removed']
rows, tot, tot_j = [], 0.0, 0.0
for i, (a, b) in enumerate(spans):
    inside = [r for r in removed if a - 0.001 <= (r['start'] + r['end']) / 2 <= b + 0.001 and not r['why'].startswith('dead air')]
    words = [t for t in toks if t.get('type') in ('word', 'audio_event') and a < (t['start'] + t['end']) / 2 < b]
    if inside:
        reasons = []
        for r in inside:
            w = r['why'].replace('drop: ', '')
            if w not in reasons: reasons.append(w)
        why = "; ".join(reasons) + " (with the pause around it)"
        tot_j += b - a
    elif i == 0 and a == 0:
        first = wordtoks[0]
        why = f"head: before the first kept word (\"{first['text'].strip()}\" at {first['start']:.2f})" if not words else "head"
    elif i == len(spans) - 1 and abs(b - src_dur) < 0.001:
        last = wordtoks[-1]
        why = f"tail: after the last word (\"{last['text'].strip()}\" at {last['end']:.2f})" if not words else "tail"
    else:
        why = "dead air (a pause of 0.4 s or more between words, cut down to the edge padding)"
    said = " ".join(t['text'].strip() for t in words)
    if said and not inside:
        why += f" [contains: {said}]"
    rows.append((a, b, said if inside else "", why)); tot += b - a
L = [f"# Cut list, {title} rough cut", "",
     f"Source: `{', '.join(Path(v).name for v in e['sources'].values()) if isinstance(e.get('sources'), dict) else 'source'}` ({src_dur:.3f} s). Rough cut: `rough-cut/rough_cut.mp4`, {rep['streams']['video']['duration']:.3f} s, {rep['cuts']} cuts, {rep['expected_frames']} frames at 24000/1001 fps, A/V difference {rep['av_diff_ms']} ms.", "",
     f"Every stretch of the source that is not in the cut is listed below: {len(rows)} spans (the head, one per cut, the tail), {tot:.3f} s in total, which is exactly source minus cut ({src_dur:.3f} - {rep['streams']['video']['duration']:.3f} = {src_dur - rep['streams']['video']['duration']:.3f} s). Times are SOURCE seconds and are the rendered edges (each sits on a word boundary, padded 30 to 200 ms, with a 30 ms audio fade).", "",
     f"Judgement spans (retakes, false starts, stutters, fillers; everything else is silence): {sum(1 for r in rows if r[2])}, {tot_j:.3f} s.", "",
     "| # | Source span | Length (s) | Words removed | Reason |", "| --- | --- | --- | --- | --- |"]
for k, (a, b, said, why) in enumerate(rows, 1):
    L.append(f"| {k} | {a:.3f} to {b:.3f} | {b - a:.3f} | {said} | {why} |")
hand = [f"- {r['start']:.3f} to {r['end']:.3f} ({r.get('quote', '')}): {f}" for r in e['ranges'] for f in r.get('flags', []) if f.startswith('hand edit')]
if notes.strip():
    L += ["", "## Notes", "", notes.strip()]
L += ["", "## Hand edits to the plan", ""] + (hand or ["- none"])
open('cut-list.md', 'w').write("\n".join(L) + "\n")
print(len(rows), "spans,", round(tot, 3), "s; judgement spans", sum(1 for r in rows if r[2]), round(tot_j, 3), "s")
