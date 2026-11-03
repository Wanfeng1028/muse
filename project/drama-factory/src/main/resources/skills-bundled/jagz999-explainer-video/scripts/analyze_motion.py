#!/usr/bin/env python3
"""
Detect camera zooms / scene transitions in a RENDERED explainer video by measuring
per-frame change. Use this to sync music drops + SFX to the *actual* video — essential
when the user has trimmed the render, because crossfade transitions are too smooth for
ffmpeg's `select=gt(scene,...)` scene detector (it finds almost nothing).

How it works: `tblend=all_mode=difference,signalstats` gives the average luma (YAVG) of
the temporal-difference frame per frame — i.e. "how much moved". Camera zooms, crossfades
and scrolls produce sustained YAVG bursts; static holds sit near zero. We threshold into
bursts and classify by peak/duration.

Usage:
  python3 analyze_motion.py <video.mp4> [threshold_fraction]   # default 0.10 of max
Writes motion.json: [{start, peak_t, end, dur, peak}, ...]  and prints a table.
"""
import subprocess, re, json, sys

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    V = sys.argv[1]
    th_frac = float(sys.argv[2]) if len(sys.argv) > 2 else 0.10
    out = subprocess.run(
        ["ffmpeg","-nostdin","-loglevel","error","-i",V,
         "-vf","tblend=all_mode=difference,signalstats,metadata=print:file=-",
         "-an","-f","null","-"], capture_output=True, text=True).stdout
    times, ys, ct = [], [], None
    for line in out.splitlines():
        m = re.search(r"pts_time:([0-9.]+)", line)
        if m: ct = float(m.group(1)); continue
        m = re.search(r"signalstats\.YAVG=([0-9.]+)", line)
        if m and ct is not None: times.append(ct); ys.append(float(m.group(1))); ct = None
    n = len(ys)
    if n == 0: sys.exit("no frames parsed — is the path right?")
    fps = n / (times[-1]-times[0]) if times[-1] > times[0] else 30
    mx = max(ys); TH = max(1.2, mx*th_frac)
    bursts, i = [], 0
    while i < n:
        if ys[i] > TH:
            j, peak, pk_t = i, ys[i], times[i]
            while j < n and ys[j] > TH*0.6:
                if ys[j] > peak: peak, pk_t = ys[j], times[j]
                j += 1
            bursts.append({"start":round(times[i],2),"end":round(times[j-1],2),
                           "peak":round(peak,2),"peak_t":round(pk_t,2),
                           "dur":round(times[j-1]-times[i],2)})
            i = j
        else: i += 1
    merged = []                                   # merge bursts < 0.4s apart
    for b in bursts:
        if merged and b["start"]-merged[-1]["end"] < 0.4:
            merged[-1]["end"]=b["end"]; merged[-1]["dur"]=round(b["end"]-merged[-1]["start"],2)
            if b["peak"]>merged[-1]["peak"]: merged[-1].update(peak=b["peak"], peak_t=b["peak_t"])
        else: merged.append(dict(b))
    big = sorted([b["peak"] for b in merged], reverse=True)[min(2, len(merged)-1)] if merged else 0
    print(f"frames={n} fps~{fps:.1f} dur={times[-1]:.1f} maxYAVG={mx:.2f} TH={TH:.2f} bursts={len(merged)}")
    print("idx  start  peak_t   end    dur   peak  class")
    for k,b in enumerate(merged):
        cls = "TRANSITION" if b["peak"]>=big or b["dur"]>10 else ("zoom" if b["dur"]>=0.5 else "small")
        print(f"{k:>2} {b['start']:>6.2f} {b['peak_t']:>7.2f} {b['end']:>6.2f} {b['dur']:>5.2f} {b['peak']:>6.2f}  {cls}")
    json.dump(merged, open("motion.json","w"))
    print("-> motion.json")

if __name__ == "__main__": main()
