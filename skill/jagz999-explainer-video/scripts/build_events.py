#!/usr/bin/env python3
"""
Turn detected motion (motion.json from analyze_motion.py) into two timelines:
  music_accents.json — risers + impacts/drops on scene-defining motion (the "drops in sync")
  sfx_events.json    — a whoosh on every camera-move start, swishes through long scrolls

Then build the tracks:
  python3 build_sfx.py music_accents.json sfx_clips accents.mp3
  python3 build_sfx.py sfx_events.json   sfx_clips sfx.mp3
  # music.mp3 = generative bed + accents (amix); see AUDIO_SYNC.md

Generative music can't be beat-locked to your timestamps, so the "drops in sync" come from
placed impact/riser accents layered OVER the bed — NOT from the bed itself.

Per-interaction UI sounds (button press, panel reveal, success ding) are content-specific,
so pass them in an optional ui_events.json: [[t,"clip",gain], ...]. They're merged into sfx.

Usage:
  python3 build_events.py motion.json <total_seconds> [ui_events.json]

Clip names referenced (generate them with elevenlabs.py sfx, verify not silent):
  whoosh, swish, impact, riser, drop, clap   (sfx)  +  button, pop, ding  (ui, optional)
Taste notes from real use: use ONE whoosh per camera-move *start*; a separate "zoom-out"
sound on every settle gets annoying fast — omit it. Keep the button SFX quiet/subtle.
"""
import json, sys

def main():
    if len(sys.argv) < 3: sys.exit(__doc__)
    B = json.load(open(sys.argv[1]))
    TOTAL = float(sys.argv[2])
    ui = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else []

    # ---- SFX: whoosh at each motion start; swishes through long scrolls ----
    sfx = []
    for b in B:
        dur = b["end"] - b["start"]
        if dur < 0.3 and b["peak"] < 2.3: continue            # skip jitter
        sfx.append({"t": round(b["start"],2), "clip":"whoosh",
                    "gain": round(0.45 + min(0.18, b["peak"]/55), 2)})
        if dur > 4.0:                                          # long scroll
            t = b["start"] + 2.0
            while t < b["end"] - 1.0:
                sfx.append({"t": round(t,2), "clip":"swish", "gain":0.4}); t += 3.5
    for t, c, g in ui: sfx.append({"t": float(t), "clip": c, "gain": float(g)})
    sfx.sort(key=lambda e: e["t"])
    json.dump({"total": TOTAL, "events": sfx}, open("sfx_events.json","w"))

    # ---- MUSIC accents: impacts on scene-defining motion, risers into big drops ----
    peaks = sorted([b["peak"] for b in B], reverse=True)
    big = peaks[2] if len(peaks) > 2 else (peaks[-1] if peaks else 0)
    acc = [{"t":2.6, "clip":"clap", "gain":3.0}]              # intro build (clap clips run quiet→boost)
    last = -9
    for b in B:
        if b["peak"] < 2.3: continue
        dur = b["end"] - b["start"]
        t = b["start"] if dur > 4 else b["peak_t"]            # scroll→start, transition→peak
        if t - last < 2.6: continue
        last = t
        if b["peak"] >= big or dur > 10:                      # big drop
            acc += [{"t":round(max(0,t-1.6),2),"clip":"riser","gain":0.85},
                    {"t":round(t,2),"clip":"impact","gain":0.95},
                    {"t":round(t+0.05,2),"clip":"drop","gain":0.6}]
        else:
            acc.append({"t":round(t,2),"clip":"impact","gain":0.55})
    acc.sort(key=lambda e: e["t"])
    json.dump({"total": TOTAL, "events": acc}, open("music_accents.json","w"))
    print(f"sfx events: {len(sfx)} | music accents: {len(acc)}")
    print("impacts at:", [e["t"] for e in acc if e["clip"]=="impact"])

if __name__ == "__main__": main()
