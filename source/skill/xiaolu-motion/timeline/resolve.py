"""Storyboard (schema v0.1) -> resolved timeline: every time is absolute seconds.

  python3 -m timeline.resolve storyboard.json [--out storyboard.resolved.json]

Resolution + validation in one pass (timeline/validate.py only prints the report):
  1. JSON Schema (timeline/schema.json)
  2. base clips: src resolved relative to the storyboard, probed with ffprobe; in/out snapped
     to source frames; clips must not overlap on the timeline (gaps render black)
  3. words: words.json mapped onto the timeline through the clips that show its media
  4. anchors -> seconds for shot start/end, transition at, camera keyframe t, sfx at
  5. component contract: component file exists, param names known (specs dumped with Node);
     `invert: true` needs a component that exports `invert = true` and becomes layer 'invert'
  6. sfx flattened to an absolute cue list (the audio side consumes resolved["sfx"])
"""
import argparse
import functools
import json
import math
import subprocess
import sys
from pathlib import Path

from render.common import COMPONENTS, REPO, load_json, load_style, save_json, video_info
from .anchors import AnchorError, Words

SCHEMA = Path(__file__).with_name("schema.json")
EPS = 1e-6


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append({"where": where, "msg": msg})

    def warn(self, where, msg):
        self.warnings.append({"where": where, "msg": msg})

    @property
    def ok(self):
        return not self.errors

    def dump(self):
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


@functools.lru_cache(maxsize=1)
def component_specs():
    """{id: {role, params, ...}} from the JS modules themselves (single source of truth)."""
    try:
        r = subprocess.run(["node", str(REPO / "timeline" / "dump_specs.mjs")], check=True, capture_output=True, text=True)
        return json.loads(r.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as e:  # pragma: no cover
        print("warning: cannot dump component specs:", e, file=sys.stderr)
        return None


def schema_errors(doc):
    try:
        import jsonschema
    except ImportError:  # pragma: no cover
        return ["jsonschema not installed: schema check skipped"]
    v = jsonschema.Draft202012Validator(load_json(SCHEMA))
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message}" for e in sorted(v.iter_errors(doc), key=str)]


def _rel(base_dir, p):
    q = Path(p).expanduser()
    return str(q if q.is_absolute() else (base_dir / q).resolve())


def resolve(sb_path, probe_media=True):
    sb_path = Path(sb_path).resolve()
    sb = load_json(sb_path)
    rep = Report()
    for e in schema_errors(sb):
        rep.err("schema", e)
    if not rep.ok:
        return None, rep
    d = sb_path.parent
    C = sb["canvas"]
    fps, dur = C["fps"], float(sb["duration"])
    frames = round(dur * fps)
    if abs(frames - dur * fps) > 1e-6:
        rep.warn("duration", f"{dur}s x {fps}fps is not a whole number of frames; rendering {frames} frames")
    # ---- style
    try:
        tokens = load_style(sb["style"])
        if sb.get("style_overrides"):
            from render.common import deep_merge
            tokens = deep_merge(tokens, sb["style_overrides"])
    except (OSError, ValueError) as e:
        rep.err("style", f"cannot load style {sb['style']}: {e}")
        return None, rep
    # ---- base clips
    clips = []
    for k, c in enumerate(sb.get("base", [])):
        where = f"base[{k}]"
        cid = c.get("id") or f"b{k + 1}"
        src = _rel(d, c["src"])
        info = None
        if not Path(src).exists():
            rep.err(where, f"src not found: {src}")
            continue
        if probe_media:
            info = video_info(src)
            sf = info["fps"]
            i0, i1 = round(c["in"] * sf), round(c["out"] * sf)
            if abs(i0 / sf - c["in"]) > 1e-3 or abs(i1 / sf - c["out"]) > 1e-3:
                rep.warn(where, f"in/out snapped to source frames: {c['in']}->{i0 / sf:.4f}, {c['out']}->{i1 / sf:.4f}")
            if i1 > info["frames"] + 1:
                rep.err(where, f"out {c['out']}s beyond source ({info['duration']:.3f}s)")
            cin, cout = i0 / sf, i1 / sf
        else:
            cin, cout = float(c["in"]), float(c["out"])
        if cout <= cin:
            rep.err(where, "out must be > in")
            continue
        at = float(c["at"])
        if abs(at * fps - round(at * fps)) > 1e-3:
            rep.warn(where, f"at={at} is not on an output frame boundary (1/{fps}s)")
        matte = _rel(d, c["matte"]) if c.get("matte") else None
        if matte and not Path(matte).exists():
            rep.err(where, f"matte not found: {matte}")
            matte = None
        clips.append({"id": cid, "src": src, "matte": matte, "in": round(cin, 6), "out": round(cout, 6), "at": at, "t0": at,
                      "t1": round(at + cout - cin, 6), "fit": c.get("fit", "cover"), "audio": c.get("audio", True),
                      "camera_in": c.get("camera", []), "src_info": info})
    clips.sort(key=lambda c: c["t0"])
    for a, b in zip(clips, clips[1:]):
        if b["t0"] < a["t1"] - 1e-4:
            rep.err("base", f"clips {a['id']} and {b['id']} overlap on the timeline ({a['t1']:.3f} > {b['t0']:.3f})")
        elif b["t0"] > a["t1"] + 1e-4:
            rep.warn("base", f"gap {a['t1']:.3f}–{b['t0']:.3f}s between {a['id']} and {b['id']} renders black")
    if clips and clips[-1]["t1"] < dur - 1e-4:
        rep.warn("base", f"base ends at {clips[-1]['t1']:.3f}s < duration {dur}s (black tail)")
    if clips and clips[-1]["t1"] > dur + 1e-4:
        rep.warn("base", f"base runs to {clips[-1]['t1']:.3f}s, trimmed at duration {dur}s")
    # ---- words
    words = None
    if sb.get("words"):
        wp = _rel(d, sb["words"])
        try:
            words = Words(load_json(wp), clips)
            if not words.timeline:
                rep.warn("words", f"{wp}: no word falls inside a base clip showing its media")
        except OSError as e:
            rep.err("words", f"cannot read {wp}: {e}")

    def tref(v, where):
        if isinstance(v, (int, float)):
            return float(v), None
        if words is None:
            rep.err(where, "word anchor used but storyboard has no `words`")
            return None, None
        try:
            return words.resolve(v)
        except AnchorError as e:
            rep.err(where, str(e))
            return None, None

    # ---- camera keyframes
    for c in clips:
        keys = []
        for j, kf in enumerate(c.pop("camera_in")):
            t, dbg = tref(kf["t"], f"{c['id']}.camera[{j}].t")
            if t is None:
                continue
            keys.append({"t": t, "zoom": kf.get("zoom", 1.0), "cx": kf.get("cx", 0.5), "cy": kf.get("cy", 0.5), "ease": kf.get("ease", "sineInOut"),
                         **({"anchor": dbg} if dbg else {})})
        keys.sort(key=lambda k: k["t"])
        for k in keys:
            if not (c["t0"] - 1e-3 <= k["t"] <= c["t1"] + 1e-3):
                rep.warn(f"{c['id']}.camera", f"keyframe t={k['t']:.3f} outside clip {c['t0']:.3f}–{c['t1']:.3f} (value still used as hold)")
        c["camera"] = keys or [{"t": c["t0"], "zoom": 1.0, "cx": 0.5, "cy": 0.5, "ease": "lin"}]
    # ---- global camera (L4): shared by every layer (footage depth 1, graphics by their depth)
    gcam = []
    for j, kf in enumerate(sb.get("camera", [])):
        t, dbg = tref(kf["t"], f"camera[{j}].t")
        if t is None:
            continue
        gcam.append({"t": t, "zoom": kf.get("zoom", 1.0), "cx": kf.get("cx", 0.5), "cy": kf.get("cy", 0.5), "ease": kf.get("ease", "sineInOut"), **({"anchor": dbg} if dbg else {})})
    gcam.sort(key=lambda k: k["t"])
    if gcam:
        for c in clips:
            if any(abs(k["zoom"] - 1) > 1e-9 or abs(k["cx"] - 0.5) > 1e-9 or abs(k["cy"] - 0.5) > 1e-9 for k in c["camera"]):
                rep.err(c["id"], "clip camera and global camera both move; use one (global camera = L4)")
    has_matte = any(c.get("matte") for c in clips)
    # ---- components
    specs = component_specs()

    def check_component(cid, where, params, want_role=None):
        if not (COMPONENTS / f"{cid}.js").exists():
            rep.err(where, f"unknown component '{cid}' (components/{cid}.js missing)")
            return
        if specs is None or cid not in specs:
            return
        sp = specs[cid]
        if want_role == "transition" and sp.get("role") != "transition":
            rep.err(where, f"'{cid}' is not a transition component (role {sp.get('role')})")
        if want_role == "shot" and sp.get("role") == "transition":
            rep.err(where, f"'{cid}' is a transition; put it in `transitions`")
        for k, v in (params or {}).items():
            if k not in sp["params"]:
                rep.err(f"{where}.params.{k}", f"unknown param for {cid}; known: {', '.join(sp['params'])}")
                continue
            ps = sp["params"][k]
            t = ps.get("type")
            if t == "number" and v is not None and not isinstance(v, (int, float)):
                rep.err(f"{where}.params.{k}", f"expects a number, got {v!r}")
            if t == "number" and isinstance(v, (int, float)):
                if "min" in ps and v < ps["min"] or "max" in ps and v > ps["max"]:
                    rep.err(f"{where}.params.{k}", f"{v} outside [{ps.get('min')}, {ps.get('max')}]")
            if t == "integer" and not isinstance(v, int):
                rep.err(f"{where}.params.{k}", f"expects an integer, got {v!r}")
            if t == "enum" and v not in ps.get("values", []):
                rep.err(f"{where}.params.{k}", f"{v!r} not in {ps.get('values')}")
            if t == "string" and not isinstance(v, str):
                rep.err(f"{where}.params.{k}", f"expects a string, got {v!r}")
            if t == "color" and isinstance(v, str) and v.startswith("@") and v[1:].replace("colors.", "") not in tokens.get("colors", {}):
                rep.err(f"{where}.params.{k}", f"colour token {v} not defined in style {sb['style']}")

    def sfx_list(item, where, kind):
        out = []
        for j, s in enumerate(item.get("sfx", [])):
            at = s.get("at", "start")
            if at == "start":
                t = item["t0"]
            elif at == "end":
                t = item["t1"]
            elif at == "mid":
                t = (item["t0"] + item["t1"]) / 2
            elif isinstance(at, dict) and "rel" in at:
                t = item["t0"] + at["rel"]
            else:
                t, _ = tref(at, f"{where}.sfx[{j}].at")
            if t is None:
                continue
            if not (0 <= t <= dur):
                rep.warn(f"{where}.sfx[{j}]", f"cue at {t:.3f}s outside the timeline")
            out.append({**{k: v for k, v in s.items() if k != "at"}, "t": round(t, 4), "source": item["id"], "source_kind": kind})
        return out

    shots = []
    for k, s in enumerate(sb.get("shots", [])):
        where = f"shots[{k}]({s['id']})"
        t0, dbg0 = tref(s["start"], where + ".start")
        if t0 is None:
            continue
        if isinstance(s["end"], dict) and "dur" in s["end"]:
            t1, dbg1 = t0 + s["end"]["dur"], None
        else:
            t1, dbg1 = tref(s["end"], where + ".end")
        if t1 is None:
            continue
        if t1 <= t0:
            rep.err(where, f"end {t1:.3f} <= start {t0:.3f}")
            continue
        if t0 < -EPS or t1 > dur + 1e-3:
            rep.err(where, f"{t0:.3f}–{t1:.3f} outside timeline 0–{dur}")
        params = dict(s.get("params") or {})
        if s["component"] == "kinetic_keyword" and not params.get("text") and isinstance(s["start"], dict) and "text" in s["start"]:
            params["text"] = s["start"]["text"]
        check_component(s["component"], where, params, "shot")
        item = {"id": s["id"], "component": s["component"], "t0": round(t0, 4), "t1": round(t1, 4), "params": params, "z": s.get("z", k),
                "layer": s.get("layer", "front"), "depth": float(s.get("depth", 0.0))}
        if s.get("invert"):
            # its own compositing pass (L3i, difference-blended over L3); downstream it is just a layer name
            if item["layer"] == "behind":
                rep.err(where, "invert: true cannot sit behind the person (layer 'behind'); the invert layer is composited over the front layer")
            if specs is None:
                rep.warn(where, f"cannot check that '{s['component']}' supports invert (component specs unavailable)")
            elif s["component"] in specs and not specs[s["component"]].get("invert"):
                rep.err(where, f"'{s['component']}' does not declare invert support (export const invert = true); only white-ink HUD components read correctly under the difference blend")
            item["layer"] = "invert"
        if item["layer"] == "behind" and not has_matte:
            rep.warn(where, "layer 'behind' without a person matte on the base: it renders under nothing (same as front)")
        if dbg0 or dbg1:
            item["anchors"] = {"start": dbg0, "end": dbg1}
        item["sfx"] = sfx_list({**item, "sfx": s.get("sfx", [])}, where, "shot")
        shots.append(item)
    ids = [s["id"] for s in sb.get("shots", [])] + [t["id"] for t in sb.get("transitions", [])]
    for i in {i for i in ids if ids.count(i) > 1}:
        rep.err("ids", f"duplicate id {i}")
    trans = []
    for k, tr in enumerate(sb.get("transitions", [])):
        where = f"transitions[{k}]({tr['id']})"
        at, dbg = tref(tr["at"], where + ".at")
        if at is None:
            continue
        al, dd = tr.get("align", "center"), float(tr["dur"])
        t0 = at - dd / 2 if al == "center" else (at if al == "start" else at - dd)
        t1 = t0 + dd
        if t0 < -EPS or t1 > dur + 1e-3:
            rep.err(where, f"{t0:.3f}–{t1:.3f} outside timeline")
        check_component(tr["type"], where, tr.get("params"), "transition")
        item = {"id": tr["id"], "type": tr["type"], "at": round(at, 4), "t0": round(t0, 4), "t1": round(t1, 4), "dur": dd,
                "params": tr.get("params") or {}, "z": tr.get("z", k)}
        if dbg:
            item["anchor"] = dbg
        item["sfx"] = sfx_list({**item, "sfx": tr.get("sfx", [])}, where, "transition")
        # a transition is meant to hide a base cut: tell when the midpoint misses every clip boundary
        cuts = [c["t0"] for c in clips[1:]]
        if cuts and al == "center" and min(abs(at - x) for x in cuts) > 1.5 / fps:
            rep.warn(where, f"midpoint {at:.3f}s is not on a base clip boundary {['%.3f' % x for x in cuts]}")
        trans.append(item)
    trans.sort(key=lambda t: t["t0"])
    for a, b in zip(trans, trans[1:]):
        if b["t0"] < a["t1"] - 1e-4:
            rep.err("transitions", f"{a['id']} and {b['id']} overlap")
    cues = sorted([c for s in shots for c in s["sfx"]] + [c for t in trans for c in t["sfx"]], key=lambda c: c["t"])
    resolved = {
        "version": sb["version"], "schema": "xiaolu-motion/resolved-0.1", "storyboard": str(sb_path),
        "canvas": C, "duration": dur, "frames": frames, "style": sb["style"], "tokens": tokens,
        "base": clips, "camera": gcam, "finish": sb.get("finish", {}), "shots": shots, "transitions": trans, "sfx": cues,
        "music": sb.get("music", {"mode": "none"}), "qa": sb.get("qa", {}),
        "words": (words.timeline if words else []),
    }
    if resolved["qa"].get("captions", {}).get("srt"):
        resolved["qa"]["captions"]["srt"] = _rel(d, resolved["qa"]["captions"]["srt"])
    if resolved["qa"].get("captions", {}).get("media"):
        resolved["qa"]["captions"]["media"] = _rel(d, resolved["qa"]["captions"]["media"])
    if resolved["qa"].get("face", {}).get("track"):
        resolved["qa"]["face"]["track"] = _rel(d, resolved["qa"]["face"]["track"])
    return resolved, rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--out")
    ap.add_argument("--no-probe", action="store_true")
    a = ap.parse_args()
    res, rep = resolve(a.storyboard, probe_media=not a.no_probe)
    print(json.dumps(rep.dump(), ensure_ascii=False, indent=1))
    if not rep.ok:
        sys.exit(1)
    out = a.out or str(Path(a.storyboard).with_suffix("")) + ".resolved.json"
    save_json(out, res)
    print("wrote", out, f"({res['frames']} frames, {len(res['shots'])} shots, {len(res['transitions'])} transitions, {len(res['sfx'])} sfx cues)")


if __name__ == "__main__":
    main()
