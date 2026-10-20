#!/usr/bin/env python3
"""Event log -> edit decision list (EDL) -> one ffmpeg filter graph, then optionally render.

USAGE
  edl.py RUN_DIR [--render draft|final|none] [--zoom 1.5 | --no-zoom] [--no-narration]
  edl.py --edit-only INPUT.mp4 --out NEW_DIR [--mode feature-demo|bug-report] [--render draft|final|none]

RUN_DIR comes from record.py (raw.webm, events.json, storyboard.yaml; narration/manifest.json if tts.py ran).
Writes: edl.json (segments, predicted duration, checkpoints, warnings), filter.txt, captions.srt, text/,
and draft.mp4 (480p, fast) or edited.mp4 (full size, high quality). Default --render draft.
The video offset is read from events.json only; change it with calibrate.py --set.
--edit-only speeds up spans where the picture is frozen (and the audio silent) in an existing recording.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import overlay as ov  # noqa: E402
from common import (FPS, die, filter_script_args, link_or_copy, require_filters, load_json, load_storyboard, need, probe_summary,  # noqa: E402
                    run_paths, save_json, snap)

LEAD = 0.5                     # seconds kept before the first visible step
WIN = {"click": (0.6, 1.2), "hover": (0.4, 0.8), "select": (0.5, 1.2), "expect": (0.3, 1.5),
       "step": (0.1, 0.9), "error": (0.3, 1.0), "bug": (1.0, 3.0), "scroll": (0.2, 0.8), "press": (0.3, 0.9)}
MIN_GAP = 0.25                 # idle gaps shorter than this stay at 1x
IDLE_SPEED = {"feature-demo": 6.0, "bug-report": 8.0}
MAX_IDLE_OUT = 0.6             # an idle gap never lasts longer than this after speed-up
TAIL = {"feature-demo": 1.5, "bug-report": 3.0}
BUG_FREEZE = 2.0
MIN_HOLD = 0.2                 # shorter holds read as a stutter; skip them
ZOOM_RAMP = 0.4
INTRO, OUTRO = 2.0, 1.8


# ---------- segment model: [{"a","b","speed"}] ranges and [{"freeze","dur"}] holds, in play order ----------

def newt(segs: list[dict], t: float) -> float:
    """Raw video time -> body time (edited, before intro). Times inside cuts map to the next kept frame."""
    acc = 0.0
    for s in segs:
        if "freeze" in s:
            if t <= s["freeze"]:
                return acc
            acc += s["dur"]
        else:
            if t < s["a"]:
                return acc
            if t <= s["b"]:
                return acc + (t - s["a"]) / s["speed"]
            acc += (s["b"] - s["a"]) / s["speed"]
    return acc


def rawt(segs: list[dict], tb: float) -> float:
    """Body time -> raw video time (inverse of newt)."""
    acc = 0.0
    last = 0.0
    for s in segs:
        d = s["dur"] if "freeze" in s else (s["b"] - s["a"]) / s["speed"]
        if tb <= acc + d:
            return s["freeze"] if "freeze" in s else s["a"] + (tb - acc) * s["speed"]
        acc += d
        last = s.get("b", s.get("freeze", last))
    return last


def body_duration(segs: list[dict]) -> float:
    return newt(segs, float("inf"))


def build_ranges(start: float, stop: float, windows: list[tuple[float, float]],
                 cuts: list[tuple[float, float]], idle_speed: float) -> list[dict]:
    """Classify [start, stop] into keep (1x), idle (fast) and cut; merge; snap to the frame grid."""
    pts = {start, stop}
    for a, b in windows + cuts:
        for x in (a, b):
            if start < x < stop:
                pts.add(x)
    pts = sorted(pts)

    def cls(m):
        if any(a <= m < b for a, b in cuts):
            return "cut"
        if any(a <= m < b for a, b in windows):
            return "keep"
        return "idle"

    spans = []
    for a, b in zip(pts, pts[1:]):
        c = cls((a + b) / 2)
        if spans and spans[-1][2] == c:
            spans[-1][1] = b
        else:
            spans.append([a, b, c])
    for s in spans:                                  # short idle gaps are not worth a speed change
        if s[2] == "idle" and s[1] - s[0] < MIN_GAP:
            s[2] = "keep"
    merged = []
    for s in spans:
        if merged and merged[-1][2] == s[2]:
            merged[-1][1] = s[1]
        else:
            merged.append(list(s))
    segs = []
    for a, b, c in merged:
        a, b = snap(a), snap(b)
        if c == "cut" or b - a < 1.0 / FPS:
            continue
        sp = 1.0 if c == "keep" else max(idle_speed, (b - a) / MAX_IDLE_OUT)
        segs.append({"a": a, "b": b, "speed": round(sp, 3)})
    return segs


def insert_freeze(segs: list[dict], f: float, dur: float) -> list[dict]:
    f = snap(f)
    dur = snap(dur)
    if dur < 1.0 / FPS:
        return segs
    out = []
    done = False
    for s in segs:
        if done or "freeze" in s:
            out.append(s)
            continue
        if s["a"] <= f <= s["b"]:
            if f > s["a"]:
                out.append({**s, "b": f})
            out.append({"freeze": f, "dur": dur})
            if f < s["b"]:
                out.append({**s, "a": f})
            done = True
        elif f < s["a"]:                             # f falls in a cut: hold the next kept frame
            out.append({"freeze": s["a"], "dur": dur})
            out.append(s)
            done = True
        else:
            out.append(s)
    if not done and out:
        last = next(s for s in reversed(out) if "freeze" not in s)
        out.append({"freeze": snap(last["b"] - 1.0 / FPS), "dur": dur})
    return out


# ---------- plan from the event log ----------

def make_plan(doc: dict, sb: dict, raw_dur: float, narration: dict | None, zoom: float) -> dict:
    mode = sb["mode"]
    off = float(doc.get("video_offset") or 0.0)
    W, H = doc["viewport"]
    ev = [dict(e, vt=e["t"] + off) for e in doc["events"]]
    steps = [e for e in ev if e["kind"] == "step"]
    ends = {e["i"]: e["vt"] for e in ev if e["kind"] == "step_end"}
    end_vt = next((e["vt"] for e in ev if e["kind"] == "end"), raw_dur)
    for s in steps:
        s["vt_end"] = ends.get(s["i"], end_vt)
    visible = [s for s in steps if not s["hidden"]]
    if not visible:
        die("no visible steps in the event log")
    hidden = [(s["vt"], s["vt_end"]) for s in steps if s["hidden"]]

    def step_of(e):
        return next((s for s in reversed(steps) if s["vt"] <= e["vt"] + 1e-6), None)

    flash_end = next((e["vt"] for e in ev if e["kind"] == "flash_end"), 0.0)
    start = max([visible[0]["vt"] - LEAD, flash_end + 0.05] +
                [b for a, b in hidden if b <= visible[0]["vt"] + 1e-6])
    first_do = sb["steps"][visible[0]["i"]]["do"]
    first_do = first_do[0] if isinstance(first_do, list) else first_do
    if str(first_do).strip().lower().startswith("goto "):   # do not show the blank page while it loads
        nav = next((e for e in ev if e["kind"] == "nav" and visible[0]["vt"] <= e["vt"] <= visible[0]["vt_end"]), None)
        if nav:
            start = max(start, nav["vt"] + 0.05)
    bug = next((e for e in ev if e["kind"] == "bug"), None)
    stop = (bug["vt"] if (mode == "bug-report" and bug) else end_vt) + TAIL[mode]
    stop = min(stop, raw_dur - 1.0 / FPS)

    windows = []
    for e in ev:
        k = e["kind"]
        st = step_of(e)
        if st is not None and st["hidden"]:
            continue
        if k == "type":
            windows.append((e["t_start"] + off - 0.5, e["vt"] + 0.8))
        elif k in WIN and not (k == "error" and mode != "bug-report"):
            a, b = WIN[k]
            windows.append((e["vt"] - a, e["vt"] + b))
    cuts = [(a, b) for a, b in hidden if b > start and a < stop]
    segs = build_ranges(start, stop, windows, cuts, IDLE_SPEED[mode])
    if not segs:
        die("EDL is empty; check the event log and video_offset")

    if mode == "bug-report" and bug:
        segs = insert_freeze(segs, bug["vt"], BUG_FREEZE)

    clips = {c["i"]: c for c in (narration or {}).get("clips", [])}
    for j, s in enumerate(visible):                 # hold each step long enough to read / hear it
        nxt = visible[j + 1]["vt"] if j + 1 < len(visible) else None
        cap = sb["steps"][s["i"]].get("caption", "")
        need_s = max(1.2, 0.3 * len(cap.split()))
        if s["i"] in clips:
            need_s = max(need_s, clips[s["i"]]["duration"] + 0.35)
        a = newt(segs, s["vt"])
        b = newt(segs, nxt) if nxt is not None else body_duration(segs)
        if need_s - (b - a) >= MIN_HOLD:
            f = min(s["vt_end"], nxt if nxt is not None else stop) - 0.05
            segs = insert_freeze(segs, max(f, s["vt"]), need_s - (b - a))

    total_body = body_duration(segs)
    captions, warnings, zooms, errors = [], [], [], []
    for j, s in enumerate(visible):
        nxt = visible[j + 1]["vt"] if j + 1 < len(visible) else None
        a = newt(segs, s["vt"])
        b = newt(segs, nxt) if nxt is not None else total_body
        st_clicks = [e for e in ev if e["kind"] in ("click", "type", "select") and step_of(e) is s]
        pos = ov.caption_position(st_clicks, H)
        text = sb["steps"][s["i"]].get("caption", "")
        cap = {"i": s["i"], "n": j + 1, "text": text, "a": round(a, 3), "b": round(b, 3), "pos": pos}
        captions.append(cap)
        if mode == "feature-demo" and not sb.get("theme"):   # themed captions sit below the frame
            rect = ov.caption_rect(f"{j + 1}. {text}", pos, W, H)
            for c in st_clicks:
                bb = c.get("bbox")
                if bb and ov.overlaps(rect, (bb["x"], bb["y"], bb["width"], bb["height"])):
                    warnings.append(f"caption {j + 1} may cover the clicked element {c['target']}")
    if zoom > 1.0 and mode == "feature-demo":
        for e in ev:
            st = step_of(e)
            if e["kind"] not in ("click", "type", "select") or (st and st["hidden"]):
                continue
            t1 = newt(segs, e["vt"])
            t0 = newt(segs, e["t_start"] + off) if e["kind"] == "type" else t1
            zooms.append({"a": round(t0 - 0.5, 3), "b": round(t1 + (0.6 if e["kind"] == "type" else 1.3), 3),
                          "cx": round(e["x"] / W, 4), "cy": round(e["y"] / H, 4), "target": e.get("target")})
    for e in ev:
        if e["kind"] == "error" and start <= e["vt"] <= stop:
            errors.append({**{k: e.get(k) for k in ("source", "status", "method", "url", "text")},
                           "t_body": round(newt(segs, e["vt"]), 3)})

    bug_info = None
    if bug:
        tb = newt(segs, bug["vt"])
        bug_info = {"t_body": round(tb, 3), "bbox": bug.get("bbox"), "freeze": BUG_FREEZE,
                    "errors_so_far": bug.get("errors_so_far")}
    return {"mode": mode, "viewport": [W, H], "offset": off, "raw_duration": raw_dur,
            "start": start, "stop": stop, "segments": segs, "body_duration": round(total_body, 3),
            "captions": captions, "zooms": zooms, "errors": errors, "bug": bug_info, "warnings": warnings,
            "clicks": [{"raw_t": round(e["vt"], 3), "t_body": round(newt(segs, e["vt"]), 3), "target": e["target"]}
                       for e in ev if e["kind"] == "click" and not (step_of(e) and step_of(e)["hidden"])]}


# ---------- filter graph ----------

def piecewise(ws: list[dict], key: str, var="it") -> str:
    expr = f"{ws[-1][key]}"
    for k in range(len(ws) - 1, 0, -1):
        prev, cur = ws[k - 1][key], ws[k][key]
        a = ws[k]["a"]
        expr = (f"if(lt({var},{a:.3f}),{prev},if(lt({var},{a + ZOOM_RAMP:.3f}),"
                f"{prev}+({cur}-{prev})*({var}-{a:.3f})/{ZOOM_RAMP},{expr}))")
    return expr


def zoom_filter(zooms: list[dict], W: int, H: int, zmax: float, ss: int, out: tuple[int, int] | None = None) -> str:
    """Click zoom. `out` renders straight at another size (the theme frame) to avoid a second rescale."""
    OW, OH = out or (W, H)
    ws = sorted(zooms, key=lambda z: z["a"])
    env = [f"clip(min((it-{z['a']:.3f})/{ZOOM_RAMP},({z['b']:.3f}-it)/{ZOOM_RAMP}),0,1)" for z in ws]
    m = env[0]
    for e in env[1:]:
        m = f"max({m},{e})"
    zexpr = f"1+{zmax - 1:.3f}*{m}"
    cx, cy = piecewise(ws, "cx"), piecewise(ws, "cy")
    return (f"scale={OW * ss}:{OH * ss}:flags=lanczos,"
            f"zoompan=z='{zexpr}':x='clip(({cx})*iw-iw/zoom/2,0,iw-iw/zoom)'"
            f":y='clip(({cy})*ih-ih/zoom/2,0,ih-ih/zoom)':d=1:s={OW}x{OH}:fps={FPS},setsar=1")


def seg_chain(segs: list[dict], src: str, audio: bool = False) -> list[str]:
    """trim/freeze/concat parts. Frame-exact: boundaries are frame indices on the fps=30 source."""
    n = len(segs)
    parts = [f"[{src}]split={n}" + "".join(f"[p{i}]" for i in range(n))]
    if audio:
        parts.append(f"[0:a]asplit={n}" + "".join(f"[q{i}]" for i in range(n)))
    labels = []
    for i, s in enumerate(segs):
        if "freeze" in s:
            k = round(s["freeze"] * FPS)
            m = max(1, round(s["dur"] * FPS))
            parts.append(f"[p{i}]trim=start_frame={k}:end_frame={k + 1},setpts=PTS-STARTPTS,"
                         f"loop=loop={m - 1}:size=1:start=0,setpts=N/({FPS}*TB)[s{i}]")
            if audio:
                parts.append(f"aevalsrc=0:d={s['dur']:.3f}:s=48000:c=stereo[r{i}]")
        else:
            ka, kb = round(s["a"] * FPS), round(s["b"] * FPS)
            parts.append(f"[p{i}]trim=start_frame={ka}:end_frame={kb},setpts=(PTS-STARTPTS)/{s['speed']}[s{i}]")
            if audio:
                tempo = f",atempo={min(s['speed'], 100)}" if s["speed"] != 1 else ""
                parts.append(f"[q{i}]atrim={s['a']:.3f}:{s['b']:.3f},asetpts=PTS-STARTPTS,"
                             f"aresample=48000,aformat=channel_layouts=stereo{tempo}[r{i}]")
        labels.append(f"[s{i}][r{i}]" if audio else f"[s{i}]")
    if audio:
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=1[catv][cata]")
        parts.append(f"[catv]fps={FPS},setsar=1[cat]")      # fps after concat, or speed-ups do not shorten
    else:
        parts.append("".join(labels) + f"concat=n={n}:v=1:a=0,fps={FPS},setsar=1[cat]")
    return parts


def build_graph(plan: dict, sb: dict, run: pathlib.Path, draft: bool, zmax: float,
                narration: dict | None) -> tuple[str, list[str], float]:
    """Returns (filter graph, extra input files, predicted total duration)."""
    W, H = plan["viewport"]
    mode = plan["mode"]
    T = ov.Texts(run)
    segs = plan["segments"]
    total_body = plan["body_duration"]
    head = f"[0:v]fps={FPS},setpts=PTS-STARTPTS,format=yuv420p,setsar=1"
    if mode == "bug-report":
        head += "," + ov.timestamp_filter()
    parts = [head + "[src]"] + seg_chain(segs, "src")

    if mode == "feature-demo" and sb.get("theme"):
        return themed_graph(plan, sb, run, draft, zmax, narration, parts)
    if plan["zooms"]:
        parts.append(f"[cat]{zoom_filter(plan['zooms'], W, H, zmax, 1 if draft else 2)}[zm]")
    else:
        parts.append("[cat]null[zm]")

    if mode == "feature-demo":
        fl = [ov.caption_filter(T, f"{c['n']}. {c['text']}", c["a"], c["b"], c["pos"]) for c in plan["captions"]]
        fl.append("fade=t=in:d=0.3")
        parts.append("[zm]" + ",".join(fl) + "[body]")
        intro = INTRO
        outro = OUTRO if sb.get("outro") else 0.0
        parts.append(ov.card(T, "intro", sb.get("title", ""), sb.get("subtitle"), W, H, INTRO))
        if outro:
            parts.append(ov.card(T, "outro", sb["outro"], None, W, H, OUTRO))
            parts.append("[intro][body][outro]concat=n=3:v=1:a=0[outv0]")
        else:
            parts.append("[intro][body]concat=n=2:v=1:a=0[outv0]")
    else:
        intro = outro = 0.0
        bug = plan["bug"] or {}
        fl = [f"pad={W + ov.PANEL_W}:{H}:0:0:color={ov.PANEL_BG}"]
        if bug:
            fl += ov.bug_box(bug.get("bbox"), bug["t_body"], bug["t_body"] + bug["freeze"] + 2.0, W, H)
        fl += ov.bug_panel(T, w=W, h=H, title=sb.get("title", "Bug"),
                           steps=[{"text": c["text"], "a": c["a"], "b": c["b"]} for c in plan["captions"]],
                           bug_t=bug.get("t_body"), expected=sb["bug"]["expected"], actual=sb["bug"]["actual"],
                           errors=plan["errors"], total=total_body)
        fl.append("fade=t=in:d=0.3")
        parts.append("[zm]" + ",".join(fl) + "[outv0]")
    tail = "scale=-2:480:flags=bicubic," if draft else ""
    parts.append(f"[outv0]{tail}format=yuv420p[outv]")

    total = intro + total_body + outro
    inputs, audio = narration_mix(plan, narration, intro, total) if mode == "feature-demo" else ([], [])
    return ";\n".join(parts + audio), inputs, total


def narration_mix(plan: dict, narration: dict | None, intro: float, total: float) -> tuple[list[str], list[str]]:
    """Per-step narration clips delayed to their captions and mixed to [outa]."""
    inputs, parts, labels = [], [], []
    caps = {c["i"]: c for c in plan["captions"]}
    for k, c in enumerate((narration or {}).get("clips", []), start=1):
        if c["i"] not in caps:
            continue
        inputs.append(c["file"])
        delay = int((intro + caps[c["i"]]["a"] + 0.15) * 1000)
        d = c["duration"]
        parts.append(f"[{len(inputs)}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"afade=t=in:d=0.03,afade=t=out:st={max(0, d - 0.03):.3f}:d=0.03,"
                     f"adelay={delay}:all=1[n{k}]")
        labels.append(f"[n{k}]")
    if labels:
        parts.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
                     f"apad,atrim=0:{total:.3f}[outa]")
    return inputs, parts


def still(path: str, duration: float, alpha: bool = False) -> str:
    """A PNG layer as a video stream of `duration` seconds (movie source, so no extra -i input)."""
    fmt = "rgba" if alpha else "yuv420p"
    return (f"movie={path},loop=loop=-1:size=1:start=0,fps={FPS},trim=duration={duration:.3f},"
            f"setpts=PTS-STARTPTS,format={fmt},setsar=1")


def resolve_theme(sb: dict, run: pathlib.Path) -> dict:
    """Theme names are built-in; relative paths resolve from the run, then the original storyboard folder."""
    import theme as th
    spec = str(sb["theme"])
    base = run
    if not th.theme_path(spec, run).exists():
        meta = run / "meta.json"
        sb_dir = load_json(meta).get("storyboard_dir") if meta.exists() else None
        base = pathlib.Path(sb_dir) if sb_dir else run
    return th.load_theme(spec, base)


def themed_graph(plan: dict, sb: dict, run: pathlib.Path, draft: bool, zmax: float,
                 narration: dict | None, parts: list[str]) -> tuple[str, list[str], float]:
    """feature-demo on a designed canvas: framed recording, caption band, themed cards (scripts/theme.py)."""
    import theme as th
    W, H = plan["viewport"]
    theme = resolve_theme(sb, run)
    layers = th.render_layers(theme, (W, H), run / "theme", title=sb.get("title", ""), subtitle=sb.get("subtitle"),
                              outro=sb.get("outro"), label=sb.get("theme_label", ""),
                              captions=[(c["n"], c["text"]) for c in plan["captions"]])
    files, lay = layers["files"], layers["layout"]
    fx, fy, fw, fh = lay["frame"]
    total_body = plan["body_duration"]
    if plan["zooms"]:
        parts.append(f"[cat]{zoom_filter(plan['zooms'], W, H, zmax, 1 if draft else 2, (fw, fh))}[rec]")
    else:
        parts.append(f"[cat]scale={fw}:{fh}:flags=lanczos,setsar=1[rec]")
    parts.append(still(files["background"], total_body) + "[bg]")
    parts.append(f"[bg][rec]overlay=x={fx}:y={fy}:shortest=1[b0]")
    k = 0
    for k, c in enumerate(plan["captions"], start=1):
        a, b = c["a"], c["b"]
        fade = (f",fade=t=in:st={a:.3f}:d=0.25:alpha=1"
                f",fade=t=out:st={max(a, b - 0.25):.3f}:d=0.25:alpha=1")
        cap = files["captions"][c["n"]]
        parts.append(still(cap["file"], total_body, alpha=True) + fade + f"[c{k}]")
        parts.append(f"[b{k - 1}][c{k}]overlay={cap['x']}:{cap['y']}:enable='{ov.between(a, b)}'[b{k}]")
    parts.append(f"[b{k}]fade=t=in:d=0.3[body]")
    intro = INTRO
    outro = OUTRO if sb.get("outro") else 0.0
    fades = ",fade=t=in:d=0.3,fade=t=out:st={st:.2f}:d=0.35"
    parts.append(still(files["intro"], INTRO) + fades.format(st=INTRO - 0.35) + "[intro]")
    if outro:
        parts.append(still(files["outro"], OUTRO) + fades.format(st=OUTRO - 0.35) + "[outro]")
        parts.append("[intro][body][outro]concat=n=3:v=1:a=0[outv0]")
    else:
        parts.append("[intro][body]concat=n=2:v=1:a=0[outv0]")
    tail = "scale=-2:480:flags=bicubic," if draft else ""
    parts.append(f"[outv0]{tail}format=yuv420p[outv]")
    total = intro + total_body + outro
    inputs, audio = narration_mix(plan, narration, intro, total)
    return ";\n".join(parts + audio), inputs, total


def checkpoints(plan: dict, intro: float, total: float) -> list[dict]:
    cps = [{"label": "start", "t": 0.4, "raw_t": None}]
    for c in plan["captions"]:
        cps.append({"label": f"step{c['n']}", "t": intro + c["a"] + 0.35, "raw_t": None})
    for k, c in enumerate(plan["clicks"], 1):
        cps.append({"label": f"click{k}+0.3", "t": intro + c["t_body"] + 0.3, "raw_t": c["raw_t"] + 0.3})
    if plan["bug"]:
        cps.append({"label": "bug", "t": intro + plan["bug"]["t_body"] + 0.8, "raw_t": None})
    acc = 0.0
    for s in plan["segments"][:-1]:
        acc += s["dur"] if "freeze" in s else (s["b"] - s["a"]) / s["speed"]
        if "speed" in s and s["speed"] > 1:
            cps.append({"label": "after-fast", "t": intro + acc + 0.1, "raw_t": None})
    cps.append({"label": "end", "t": max(0.0, total - 0.4), "raw_t": None})
    for c in cps:
        if c["raw_t"] is None and intro <= c["t"] <= intro + plan["body_duration"]:
            c["raw_t"] = round(rawt(plan["segments"], c["t"] - intro), 3)
        c["t"] = round(min(max(c["t"], 0), total - 0.05), 3)
    cps.sort(key=lambda c: c["t"])
    return cps[:30]


def render(run: pathlib.Path, src: str, inputs: list[str], has_audio: bool, draft: bool) -> pathlib.Path:
    out = "draft.mp4" if draft else "edited.mp4"
    args = ["-i", src]
    for f in inputs:
        args += ["-i", f]
    args += filter_script_args("filter.txt") + ["-map", "[outv]"]
    if has_audio:
        args += ["-map", "[outa]", "-c:a", "aac", "-b:a", "160k"]
    args += ["-c:v", "libx264", "-preset", "veryfast" if draft else "medium", "-crf", "30" if draft else "20",
             "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart", out]
    t = time.time()
    cmd = ["ffmpeg", "-hide_banner", "-y", "-v", "error"] + args
    r = subprocess.run(cmd, cwd=run, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        die("ffmpeg failed (cwd " + str(run) + "):\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])
    print(f"rendered {out} in {time.time() - t:.1f}s")
    return run / out


# ---------- edit-only (existing recording, no event log) ----------

def detect_spans(path: pathlib.Path, filt: str, key: str) -> list[tuple[float, float]]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path)] + filt.split(" ") +
                       ["-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace")
    starts = [float(x) for x in re.findall(rf"{key}_start: ?([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(rf"{key}_end: ?([\d.]+)", r.stderr)]
    return list(zip(starts, ends + [float("inf")] * (len(starts) - len(ends))))


def edit_only(inp: pathlib.Path, out: pathlib.Path, mode: str, render_kind: str):
    if out.exists() and any(out.iterdir()):
        die(f"{out} is not empty; never overwrite a previous run")
    out.mkdir(parents=True, exist_ok=True)
    pr = probe_summary(inp)
    dur = pr["duration"]
    frozen = [(a, min(b, dur)) for a, b in detect_spans(inp, "-map 0:v -vf freezedetect=n=-60dB:d=0.8",
                                                         "lavfi.freezedetect.freeze")]
    has_audio = bool(pr["audio_codec"])
    if has_audio:
        silent = [(a, min(b, dur)) for a, b in detect_spans(inp, "-map 0:a -af silencedetect=n=-35dB:d=0.8",
                                                            "silence")]
        idle = [(max(a, c), min(b, d)) for a, b in frozen for c, d in silent if max(a, c) < min(b, d)]
    else:
        idle = frozen
    start = idle[0][1] - 0.3 if idle and idle[0][0] <= 0.05 else 0.0
    stop = idle[-1][0] + 0.5 if idle and idle[-1][1] >= dur - 0.05 else dur - 1.0 / FPS
    keep = []
    cur = start
    for a, b in idle:
        if a > cur:
            keep.append((cur, a))
        cur = max(cur, b)
    if cur < stop:
        keep.append((cur, stop))
    segs = build_ranges(max(0.0, start), stop, keep, [], IDLE_SPEED[mode])
    rel = "src" + inp.suffix
    link_or_copy(inp.resolve(), out / rel)
    graph = ";\n".join([f"[0:v]fps={FPS},setpts=PTS-STARTPTS,format=yuv420p,setsar=1[src]"]
                       + seg_chain(segs, "src", audio=has_audio)
                       + [f"[cat]fade=t=in:d=0.3{',scale=-2:480' if render_kind == 'draft' else ''},format=yuv420p[outv]"]
                       + (["[cata]anull[outa]"] if has_audio else []))
    (out / "filter.txt").write_text(graph, encoding="utf-8")
    total = body_duration(segs)
    plan = {"mode": mode, "edit_only": True, "source": str(inp.resolve()), "raw_duration": dur,
            "segments": segs, "body_duration": round(total, 3), "captions": [], "clicks": [], "bug": None,
            "zooms": [], "errors": [], "warnings": [], "idle_spans": idle}
    plan["predicted_duration"] = round(total, 3)
    plan["intro"] = 0.0
    plan["checkpoints"] = checkpoints(plan, 0.0, total)
    save_json(out / "edl.json", plan)
    print(f"edit-only: {dur:.2f}s -> {total:.2f}s predicted; {len(idle)} idle span(s); "
          f"{len(segs)} segment(s)")
    if render_kind != "none":
        render(out, rel, [], has_audio, render_kind == "draft")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", type=pathlib.Path)
    ap.add_argument("--render", choices=["draft", "final", "none"], default="draft")
    ap.add_argument("--zoom", type=float, default=1.5, help="max zoom on clicks (feature-demo), cap 1.5 advised")
    ap.add_argument("--no-zoom", action="store_true")
    ap.add_argument("--no-narration", action="store_true")
    ap.add_argument("--no-theme", action="store_true", help="ignore the storyboard theme (plain captions)")
    ap.add_argument("--edit-only", type=pathlib.Path, metavar="INPUT")
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--mode", choices=["feature-demo", "bug-report"], default="feature-demo")
    a = ap.parse_args()
    need("ffmpeg")
    require_filters()
    if a.edit_only:
        if not a.out:
            die("--edit-only needs --out NEW_DIR")
        return edit_only(a.edit_only, a.out, a.mode, a.render)
    if not a.run:
        ap.error("RUN_DIR is required")
    p = run_paths(a.run)
    for k in ("raw", "events", "storyboard"):
        if not p[k].exists():
            die(f"missing {p[k]}")
    sb = load_storyboard(p["storyboard"])
    if a.no_theme:
        sb = {k: v for k, v in sb.items() if k not in ("theme", "theme_label")}
    doc = load_json(p["events"])
    if doc.get("offset_method", "").startswith("none"):
        print("warning: video_offset unknown (see calibrate.py)", file=sys.stderr)
    raw = probe_summary(p["raw"])
    narration = None if a.no_narration or not p["narration"].exists() else load_json(p["narration"])
    zmax = 1.0 if a.no_zoom else a.zoom
    if zmax > 1.5:
        print("warning: zoom above 1.5 blurs the 1x recording and the DOM cursor", file=sys.stderr)
    plan = make_plan(doc, sb, raw["duration"], narration, zmax)
    graph, inputs, total = build_graph(plan, sb, a.run, a.render == "draft", zmax, narration)
    p["filter"].write_text(graph, encoding="utf-8")
    intro = INTRO if plan["mode"] == "feature-demo" else 0.0
    plan["intro"] = intro
    plan["predicted_duration"] = round(total, 3)
    plan["checkpoints"] = checkpoints(plan, intro, total)
    plan["narration"] = bool(narration and inputs)
    plan["render"] = a.render
    p["srt"].write_text(ov.srt([{"a": intro + c["a"], "b": intro + c["b"], "text": c["text"]}
                                for c in plan["captions"]]), encoding="utf-8")
    save_json(p["edl"], plan)
    fast = [s for s in plan["segments"] if s.get("speed", 1) > 1]
    print(f"EDL: raw {raw['duration']:.2f}s -> {total:.2f}s predicted "
          f"({len(plan['segments'])} segments, {len(fast)} sped up, "
          f"{sum(1 for s in plan['segments'] if 'freeze' in s)} holds, {len(plan['zooms'])} zooms)")
    for w in plan["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    if a.render != "none":
        render(a.run, "raw.webm", inputs, plan["narration"], a.render == "draft")


if __name__ == "__main__":
    main()
