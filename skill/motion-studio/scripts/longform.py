#!/usr/bin/env python3
"""Long-form narrated films (YouTube explainers, 5-20 minutes) on the motion-studio engine.

A film folder holds script.json and narration/<id>.mp3 (one clip per segment, from any TTS or a human read).
script.json: {"title", "palette"?, "captions"?: false, "moods"?: {"<chapter>": "tension"}, "segments": [
  {"id", "chapter", "type", "data", "narration", "source"?, "mood"?}]}.
Anything inside a segment's data with "at": "<word or phrase>" (optionally "nth": 2, "offset": -0.1) is timed to
that word of the segment's narration once `align` has run, so beats land on what is said.

  longform.py init <film>                       copy the engine (film.html, kit.js, figure.js) into the folder
  longform.py lines <film> [--json]             each segment's narration (feed to TTS, one file per id; --json adds speaker, mono)
  longform.py panels <film>                     the unique panel images the film needs -> out/panels.json (prompts for the generator)
  longform.py lint <film | prompts.json>        warn on prompt patterns that break hands, limbs and busy scenes
  longform.py review <film> [--checks c.json]   out/review/index.html: numbered panels to mark by click, regions by drag
  longform.py repair <film> --beat b07 --box x,y,w,h --prompt "..."   redraw one region -> repairs/<image>/rNN/ candidates
  longform.py accept|revert <film> panels/p07/r02 [--seed 2]   put a repair into the panel, or take it back out
  longform.py upscale <film> [--size 2304x1296]   Real-ESRGAN 4x then Lanczos to cover the size -> panels-hd/ (timeline uses it)
  longform.py align <film>                      word timestamps for every clip -> narration/words.json
  longform.py timeline <film> [--pad 0.45]      measure clips, resolve "at" cues -> timeline.js, narration.wav, chapters.txt
  longform.py captions <film> --lang es --text es.json   a caption track in another language -> out/captions.es.vtt
  longform.py stills <film> [--every 20]        one still per segment (or every N s) + contact sheet
  longform.py music <film>                      rank the audio library per chapter mood -> out/music_plan.json
  longform.py mix <film> [--plan | --music a.mp3,b.mp3] [--whoosh id|w.wav | --no-whoosh] [--bed-db -25.5] [--no-sfx]
  longform.py credits <film>                    out/credits.txt: the attribution lines for every sound the mix used
  longform.py render <film> [--workers 4] [--scale 1.0]
  longform.py final <film>                      mux render + mix, verify
  longform.py check <film> [--hold 4]           critic numbers: dead air, text-only stretches, cue landings, flashes
  longform.py share <film>                      out/share/: a page that streams the cut (publish it as a private artifact)

Every file stays in the film folder; nothing is uploaded from here.
"""
import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "templates" / "longform.html"
sys.path.insert(0, str(HERE))
import panelqa  # noqa: E402
FPS = 30
TEXT_ONLY = {"statement", "quote", "list", "chapter", "title"}      # scene types that are words on a background


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


_FILTER_FLAG = None


def filter_file(path):
    """ffmpeg args that read a filtergraph from a file: -filter_complex_script up to ffmpeg 8,
    -/filter_complex on builds that dropped it (9.x). Decided from the help listing, so git builds work too."""
    global _FILTER_FLAG
    if _FILTER_FLAG is None:
        helptext = subprocess.run(["ffmpeg", "-hide_banner", "-h", "long"], capture_output=True, text=True).stdout
        _FILTER_FLAG = "-filter_complex_script" if "-filter_complex_script" in helptext else "-/filter_complex"
    return [_FILTER_FLAG, str(path)]


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def load_script(film):
    return json.loads((film / "script.json").read_text())


def load_timeline(film):
    return json.loads((film / "timeline.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))


def cmd_init(a):
    film = Path(a.film).resolve()
    for d in ("narration", "out", "review", "sources"):
        (film / d).mkdir(parents=True, exist_ok=True)
    shutil.copy(TEMPLATE, film / "film.html")
    for f in ("kit.js", "figure.js"):
        shutil.copy(HERE / f, film / f)
    print(film)


def cmd_lines(a):
    film = Path(a.film).resolve()
    segs = [s for s in load_script(film)["segments"] if s.get("narration")]
    if a.json:      # a drama: one voice per speaker, inner monologue read closer and quieter
        print(json.dumps([{"id": s["id"], "speaker": s.get("speaker", "narrator"), "mono": bool(s.get("mono")), "text": s["narration"]}
                          for s in segs], indent=1, ensure_ascii=False))
        return
    for s in segs:
        print(f"{s['id']}\t{s['narration']}")


def panel_list(film, sc, problems=None):
    """Every panel image the script's panel scenes use, once each and in film order, with what the generator needs: the
    shot, who is in frame, the prompt, reference images and plate. The first beat to give a field sets it."""
    panels = {}
    for s in sc["segments"]:
        if s.get("type") != "panel":
            continue
        d = s.get("data") or {}
        img = d.get("image")
        if not img:
            if problems is not None:
                problems.append(f"{s['id']}: panel scene with no data.image")
            continue
        p = panels.setdefault(img, {"image": img, "beats": [], "shot": d.get("shot"), "char_in_frame": d.get("char_in_frame", []),
                                    "flashback": bool(d.get("flashback")), "prompt": d.get("prompt", ""), "seed": d.get("seed"),
                                    "refs": d.get("refs", []), "plate": d.get("plate"), "size": d.get("size")})
        p["beats"].append(s["id"])
        for k in ("prompt", "refs", "plate", "size"):
            if d.get(k) and not p[k]:
                p[k] = d[k]
    return list(panels.values())


def cmd_panels(a):
    """The unique panel images and their prompts -> out/panels.json for the image runner. Beats that reuse a panel
    (another crop or camera move) list it once."""
    film = Path(a.film).resolve()
    sc = load_script(film)
    problems = []
    panels = panel_list(film, sc, problems)
    for p in panels:
        p["exists"] = (film / p["image"]).exists()
        p["upscaled"] = bool(hd_path(film, p["image"]))
        if not p["prompt"]:
            problems.append(f"{p['image']} (beats {', '.join(p['beats'])}): no prompt")
    for x in problems:
        print("PROBLEM:", x)
    out = film / "out" / "panels.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"panels": panels, "characters": sc.get("characters", {})}, indent=1, ensure_ascii=False) + "\n")
    missing = [p for p in panels if not p["exists"]]
    print(f"{len(panels)} unique panels for {sum(len(p['beats']) for p in panels)} panel beats; {len(missing)} still to generate -> {out}")
    warned = panelqa.lint([dict(p, id=p["image"]) for p in panels])
    if warned:
        print(f"{len(warned)} panel prompts have lint warnings; run `longform.py lint {a.film}`")


def cmd_lint(a):
    """Warn on prompt patterns that break anatomy or blur a scene on small image models. Takes a film folder (its panel
    scenes) or a JSON list of panel records with prompt, shot, refs and plate (an image runner's prompt file)."""
    src = Path(a.source).resolve()
    if src.is_dir():
        items = [dict(p, id=f"{p['image']} ({', '.join(p['beats'])})") for p in panel_list(src, load_script(src))]
    else:
        data = json.loads(src.read_text())
        data = data.get("panels", data) if isinstance(data, dict) else data
        items = [dict(x, id=str(x.get("id") or x.get("beat") or x.get("image") or i + 1)) for i, x in enumerate(data)]
    warned = panelqa.lint(items, a.boiler)
    for pid, ws in warned:
        print(pid)
        for w in ws:
            print("   ", w)
    n = sum(len(w) for _, w in warned)
    print(f"{len(items)} prompts, {len(warned)} with warnings ({n} in all). Warnings are heuristics from the 2026-10-17 anatomy "
          "research; a person decides.")


def cmd_review(a):
    """out/review/index.html: every panel numbered in film order. Click to mark, drag to box a region, type the fix; the
    page keeps marks in this browser, downloads them as marks.json, and prints a `repair` command for each box.
    --checks is a checker's verdicts, {image: {"verdict": "FAIL", "reason", "boxes": [[x, y, w, h] in 0-1]}}."""
    film = Path(a.film).resolve()
    sc = load_script(film)
    checks = json.loads(Path(a.checks).read_text()) if a.checks else {}
    page = panelqa.review_page(film, panel_list(film, sc), checks, sc.get("title", film.name))
    print(f"review sheet -> {page} (open it in a browser; it reads the panels from the film folder)")


def image_for(film, a):
    """The panel image to repair and its panel record. --image works on a bare folder of panels with no script.json."""
    sc = load_script(film) if (film / "script.json").exists() else {"segments": []}
    if a.image:
        return a.image, [p for p in panel_list(film, sc) if p["image"] == a.image][:1]
    for p in panel_list(film, sc):
        if a.beat in p["beats"]:
            return p["image"], [p]
    raise SystemExit(f"no panel beat {a.beat}")


def cmd_repair(a):
    """Redraw one region of a panel (a broken hand, a stray limb): crop a square around --box, redraw it with an mflux edit
    model, and paste back only the box plus --margin, blended inside that edge and colour-matched to the panel around it.
    mflux has no masked inpainting for klein or Qwen-Edit, so the model redraws the whole crop and our mask confines the
    change. Candidates land in repairs/<image>/rNN/; nothing touches the panel until `accept`."""
    film = Path(a.film).resolve()
    img, found = image_for(film, a)
    beats = found[0]["beats"] if found else []
    if a.feather > a.margin:
        print(f"  note: --feather {a.feather} is wider than --margin {a.margin}, so the edge of the box itself keeps some of the old drawing")
    rdir, made, secs, e = panelqa.repair(film, img, a.box, a.prompt, ref=a.ref, model=a.model, seeds=a.seeds, context=a.context,
                                         margin=a.margin, feather=a.feather, color=not a.no_color_match, min_change=a.min_change, gen_size=a.gen_size,
                                         gen_args=a.gen_args.split() if a.gen_args else [], beats=beats)
    rid = e["id"]
    cross = {k: v for k, v in e["crossings"].items() if v}
    if cross:
        print("  lines crossing the paste edge (they stay as drawn outside it; if the redraw moves them, they break there): "
              + ", ".join(f"{k} {v}" for k, v in cross.items()))
    print(f"  crop {e['crop'][2]} px, generated at {e['gen_size']} ({e['enlarged_with'] if e['enlarged_with'] != 'none' else 'native size'})")
    for s, c in e["checks"].items():
        print(f"  seed {s}: {c['change']:.0%} of the box changed, detail ratio {c['sharpness']}"
              + (f"; {'; '.join(c['notes'])}" if c["notes"] else ""))
    print(f"{rid}: {len(made)} candidate(s) in {secs} s -> {rdir.relative_to(film)}/compare_<seed>.png")
    if made:
        print(f"look at the compare images, then: longform.py accept {a.film} {rid}" + (" --seed N" if len(made) > 1 else ""))


def cmd_accept(a):
    film = Path(a.film).resolve()
    src = panelqa.accept(film, a.repair, a.seed)
    print(f"{src.relative_to(film)} replaced (the previous version is in repairs/{a.repair}/); run `upscale` again for this panel")


def cmd_revert(a):
    film = Path(a.film).resolve()
    src = panelqa.revert(film, a.repair)
    print(f"{src.relative_to(film)} restored from before {a.repair}; run `upscale` again for this panel")


def cmd_gemini_draw(a):
    """Draw panels with Gemini (Nano Banana): the prompt plus role-labelled references, 16:9 at 2K, every call fresh.
    Batch by default (half price, results within 24 h; fetch them with `gemini-collect`); --now draws interactively.
    The run is priced first and refused whole past the cap in ~/.motion-studio.json ("gemini": {"cap_usd": 15})."""
    import gemini
    film = Path(a.film).resolve()
    if a.jobs:
        data = json.loads(Path(a.jobs).read_text())
        items = data.get("panels", data) if isinstance(data, dict) else data
    else:
        items = panel_list(film, load_script(film))
    if a.beats:
        items = [p for p in items if set(p.get("beats", [])) & set(a.beats) or p.get("image") in a.beats]
    if not a.redo:
        items = [p for p in items if not (film / p["image"]).exists()]
    if not items:
        raise SystemExit("nothing to draw (every panel exists; --redo draws them again and moves the old ones to history/)")
    jobs = gemini.make_jobs(film, items, model=a.model, size=a.size)
    if a.dry_run:
        cost = sum(gemini.estimate(j, not a.now) for j in jobs)
        for j in jobs:
            print(f"--- {j['image']} ({j['model']}, {len(j['refs'])} refs, ${gemini.estimate(j, not a.now):.4f})\n{gemini.prompt_text(j)}")
        print(f"{len(jobs)} images, about ${cost:.2f} {'interactive' if a.now else 'batch'}; nothing sent")
        return
    run, cost, done, problems = gemini.draw(film, jobs, batch=not a.now)
    for x in problems:
        print("PROBLEM:", x)
    if a.now:
        print(f"run {run}: {len(done)} of {len(jobs)} panels drawn, about ${cost:.2f} committed; sidecars beside each panel")
    else:
        print(f"run {run}: {len(jobs)} panels in {len(done)} batch job(s), about ${cost:.2f} committed; "
              f"`longform.py gemini-collect {a.film}` fetches them once done (target 24 h)")
    print("spend: run ${:.2f}, this month ${:.2f}".format(*gemini.totals(run)))


def cmd_gemini_collect(a):
    import time
    import gemini
    film = Path(a.film).resolve()
    while True:
        written, problems, running = gemini.collect(film)
        for p in written:
            print(f"  {p.relative_to(film)}")
        for x in problems:
            print("PROBLEM:", x)
        if not a.wait or not running:
            break
        time.sleep(a.every)
    print(f"{len(written)} panels written" + (f"; still running: {', '.join(running)}" if running else "; no batch still running"))
    if written:
        print("run `upscale` for the new panels if they are smaller than the frame")


def cmd_gemini_edit(a):
    """Edit a whole panel with one instruction and a keep-list (for Gemini panels this replaces the crop repair):
    "Move him up the bed against the headboard" --keep "the room" --keep "every face and outfit". The result is a
    candidate in repairs/<image>/rNN/; `accept` puts it in the panel and `revert` undoes that."""
    import gemini
    film = Path(a.film).resolve()
    img, found = image_for(film, a)
    refs = [dict(zip(("path", "role"), r.split(":", 1))) if ":" in r else r for r in a.ref or []]
    rdir, e, problem = gemini.edit(film, img, a.instruction, keep=a.keep or [], refs=refs, model=a.model, size=a.size,
                                   beats=found[0]["beats"] if found else [])
    if problem:
        print("PROBLEM:", problem)
    if e["candidates"]:
        print(f"{e['id']}: candidate in {rdir.relative_to(film)}/ (${e['usd']:.3f}, {e['tries']} tr{'y' if e['tries'] == 1 else 'ies'}); "
              f"look at compare_1.png, then: longform.py accept {a.film} {e['id']}")


def cmd_gemini_spend(a):
    import gemini
    rows = gemini.ledger()
    runs = sorted({r["run"] for r in rows if r.get("kind") == "estimate"})
    for run in runs[-a.last:]:
        n = sum(1 for r in rows if r.get("kind") == "estimate" and r["run"] == run)
        print(f"  run {run}: {n} calls, ${gemini.totals(run)[0]:.2f}")
    cfg = gemini.config()
    month_cap = cfg.get("month_cap_usd", gemini.MONTH_CAP_USD)
    print(f"this month ${gemini.totals()[1]:.2f}" + (f" of a ${float(month_cap):.2f} cap" if month_cap is not None else " (no monthly cap)")
          + f"; per-run cap ${float(cfg.get('cap_usd', gemini.CAP_USD)):.2f}; ledger {gemini.ledger_path()}")


PANEL_HD = "panels-hd"      # upscaled copies of the panel images, same relative paths; timeline prefers them


def image_size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


def hd_path(film, img):
    """The upscaled copy of a panel image, if `upscale` made one and it is newer than its source."""
    src, hd = film / img, film / PANEL_HD / Path(img).with_suffix(".png")
    return hd if hd.exists() and (not src.exists() or hd.stat().st_mtime >= src.stat().st_mtime) else None


def cmd_upscale(a):
    """Panels are drawn at the image model's size (1344x768 for klein) and the frame is 1920x1080. Upscale each with
    Real-ESRGAN (realesrgan-ncnn-vulkan, BSD-3; the anime model keeps ink lines clean), then Lanczos down to cover --size
    and centre-crop. The default size is the frame times the deepest camera push (ECU 1.2), so a push-in still shows
    one image pixel per screen pixel. A native large render was tested slower (1,541 s against 7.5 s) and softer."""
    import shutil as sh
    import tempfile
    film = Path(a.film).resolve()
    W, H = (int(x) for x in a.size.lower().split("x"))
    binary = sh.which(a.bin) or (a.bin if Path(a.bin).exists() else None)
    if not binary:
        raise SystemExit(f"{a.bin} not found: install realesrgan-ncnn-vulkan (github.com/xinntao/Real-ESRGAN releases, BSD-3) "
                         "or pass --bin /path/to/realesrgan-ncnn-vulkan")
    imgs = sorted({(s.get("data") or {}).get("image") for s in load_script(film)["segments"] if s.get("type") == "panel"} - {None})
    done = skipped = 0
    for img in imgs:
        src = film / img
        if not src.exists():
            print(f"  missing {img}"); continue
        if hd_path(film, img) and not a.redo:
            skipped += 1; continue
        dest = film / PANEL_HD / Path(img).with_suffix(".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        w, h = image_size(src)
        with tempfile.TemporaryDirectory() as td:
            big = Path(td) / "x4.png"
            if w < W or h < H:
                run([binary, "-i", str(src), "-o", str(big), "-n", a.model, "-s", "4"], capture_output=True)
            else:
                big = src                                   # already large enough: only fit it
            run(["ffmpeg", "-v", "error", "-y", "-i", str(big), "-vf",
                 f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}", str(dest)])
        done += 1
        print(f"  {img}: {w}x{h} -> {dest.relative_to(film)} ({W}x{H})")
    print(f"{done} upscaled, {skipped} already current, {len(imgs)} panels")


def cmd_align(a):
    import align
    film = Path(a.film).resolve()
    out_path = film / "narration" / "words.json"
    words = json.loads(out_path.read_text()) if out_path.exists() and not a.redo else {}
    methods = {}
    for s in load_script(film)["segments"]:
        if not s.get("narration") or (s["id"] in words and words[s["id"]].get("text") == s["narration"]):
            continue
        clip = film / "narration" / f"{s['id']}.mp3"
        if not clip.exists():
            raise SystemExit(f"missing narration clip {clip}")
        ws, method = align.align_clip(clip, s["narration"], work=film / "out")
        words[s["id"]] = {"text": s["narration"], "method": method, "words": ws}
        methods[method] = methods.get(method, 0) + 1
    out_path.write_text(json.dumps(words, indent=1, ensure_ascii=False))
    print(f"words -> {out_path} ({', '.join(f'{v} {k}' for k, v in methods.items()) or 'nothing new'})")


def norm(w):
    return "".join(ch for ch in w.lower().replace("’", "'") if ch.isalnum() or ch == "'")


def find_phrase(words, phrase, nth=1):
    """Start time of the nth occurrence of `phrase` in a segment's word list, or None."""
    target = [norm(x) for x in phrase.split()]
    seq = [norm(w[0]) for w in words]
    hits = 0
    for i in range(len(seq) - len(target) + 1):
        if all(seq[i + k] == target[k] or (k == len(target) - 1 and seq[i + k].startswith(target[k])) for k in range(len(target))):
            hits += 1
            if hits == nth:
                return words[i][1]
    return None


def resolve_cues(node, words, seg, problems, cues):
    """Give every {"at": "..."} inside a segment's data an absolute "t"."""
    if isinstance(node, dict):
        if isinstance(node.get("at"), str):
            t = find_phrase(words, node["at"], node.get("nth", 1)) if words else None
            if t is None:
                problems.append(f"{seg['id']}: cue word \"{node['at']}\" not in its narration" if words else
                                f"{seg['id']}: cue \"{node['at']}\" needs `align` first")
                t = seg["t0"] + 0.5
            node["t"] = round(t + node.get("offset", 0.0), 3)
            cues.append({"seg": seg["id"], "at": node["at"], "t": node["t"]})
        for v in node.values():
            resolve_cues(v, words, seg, problems, cues)
    elif isinstance(node, list):
        for v in node:
            resolve_cues(v, words, seg, problems, cues)


def cmd_timeline(a):
    film = Path(a.film).resolve()
    sc = load_script(film)
    wj = film / "narration" / "words.json"
    allwords = json.loads(wj.read_text()) if wj.exists() else {}
    t, segs, clips, chapters, problems, cues = a.lead, [], [], [], [], []
    moods = sc.get("moods", {})
    for s in sc["segments"]:
        clip = film / "narration" / f"{s['id']}.mp3"
        if s.get("narration"):
            if not clip.exists():
                raise SystemExit(f"missing narration clip {clip}")
            d = duration(clip)
            clips.append((t, clip))
            dur = d + a.pad + s.get("extra", 0.0)
        else:
            dur = s.get("hold", 3.0)
        seg = {k: s[k] for k in ("id", "type", "data", "source", "chapter", "cast", "speaker", "mono", "sfx", "bed") if k in s}
        seg.update(t0=round(t, 3), t1=round(t + dur, 3))
        w = allwords.get(s["id"])
        if w and w.get("text") == s.get("narration"):
            seg["words"] = [[x["w"], round(t + x["t0"], 3), round(t + x["t1"], 3)] for x in w["words"]]
        elif s.get("narration") and allwords:
            problems.append(f"{s['id']}: narration changed since `align`; run align again")
        if seg.get("type") == "panel" and (seg.get("data") or {}).get("image"):
            hd = hd_path(film, seg["data"]["image"])
            if hd:
                seg["data"] = dict(seg["data"], image=str(hd.relative_to(film)))
            elif (film / seg["data"]["image"]).exists() and image_size(film / seg["data"]["image"])[0] < 1920:
                problems.append(f"{s['id']}: panel {seg['data']['image']} is under 1920 wide and has no upscale; run `upscale`")
        resolve_cues(seg.get("data", {}), seg.get("words"), seg, problems, cues)
        if seg.get("sfx"):      # drama foley: "sfx": ["paper slap", {"kind": "low hit", "at": "envelope"}]
            seg["sfx"] = [dict(x, kind=kind_key(x["kind"])) if isinstance(x, dict) else {"kind": kind_key(x)} for x in seg["sfx"]]
            resolve_cues(seg["sfx"], seg.get("words"), seg, problems, cues)
        if seg.get("bed"):      # ambience under the whole segment: "bed": "rain glass" (or a list)
            seg["bed"] = [kind_key(b) for b in ([seg["bed"]] if isinstance(seg["bed"], str) else seg["bed"])]
        segs.append(seg)
        if s.get("chapter") and (not chapters or chapters[-1]["title"] != s["chapter"]):
            if chapters:
                chapters[-1]["t1"] = round(t, 3)
            chapters.append({"title": s["chapter"], "t0": round(t, 3), "mood": s.get("mood") or moods.get(s["chapter"])})
        t += dur
    total = round(t + a.tail, 3)
    if chapters:
        chapters[-1]["t1"] = total
    tl = {"title": sc["title"], "palette": sc.get("palette", {}), "duration": total, "segments": segs,
          "chapters": chapters, "captions": bool(sc.get("captions", False)) and any("words" in s for s in segs),
          "grade": sc.get("grade", {"vignette": 0.35, "grain": 0}), "cues": cues}
    (film / "timeline.js").write_text("window.TIMELINE = " + json.dumps(tl, indent=1, ensure_ascii=False) + ";\n")
    # narration bed: every clip placed at its segment start
    sr = 48000
    inputs, filt = [], []
    for i, (t0, clip) in enumerate(clips):
        inputs += ["-i", str(clip)]
        filt.append(f"[{i}:a]aresample={sr},aformat=channel_layouts=mono,adelay={int(t0 * 1000)}|{int(t0 * 1000)}[n{i}]")
    graph = ";".join(filt) + ";" + "".join(f"[n{i}]" for i in range(len(clips))) + \
        f"amix=inputs={len(clips)}:normalize=0:dropout_transition=0,apad=whole_dur={total}[out]"
    script = film / "out" / "narration.filter"
    if not clips:       # nothing spoken yet (a silent cut or a panel test): a silent bed of the right length
        inputs, graph = ["-f", "lavfi", "-i", f"anullsrc=r={sr}:cl=mono"], "[0:a]anull[out]"
    script.write_text(graph)
    run(["ffmpeg", "-v", "error", "-y", *inputs, *filter_file(script), "-map", "[out]",
         "-t", str(total), "-ar", str(sr), "-ac", "1", str(film / "out" / "narration.wav")])
    # YouTube chapters: first must be 0:00, each at least 10 s
    lines = []
    for k, ch in enumerate(chapters):
        s0 = 0 if k == 0 else int(ch["t0"])
        lines.append(f"{s0 // 60}:{s0 % 60:02d} {ch['title']}")
        if k and ch["t0"] - chapters[k - 1]["t0"] < 10:
            problems.append(f"chapter \"{chapters[k - 1]['title']}\" is under 10 s; YouTube will ignore the chapter list")
    (film / "out" / "chapters.txt").write_text("\n".join(lines) + "\n")
    if any("words" in s for s in segs):
        write_vtt(segs, film / "out" / "captions.vtt")
    print(f"{len(segs)} segments, {len(clips)} narration clips, {len(cues)} word cues, {total:.1f} s ({total / 60:.1f} min)")
    print("\n".join(lines))
    for p in problems:
        print("PROBLEM:", p)


def write_vtt(segs, dest, max_words=9, max_chars=42):
    """A caption track from the aligned words (upload it to YouTube instead of burning captions into 16:9)."""
    cues = []
    for s in segs:
        page, mono = [], s.get("mono")
        for w in s.get("words", []):
            page.append(w)
            text = " ".join(x[0] for x in page)
            if w[0][-1:] in ".!?" or len(page) >= max_words or len(text) > max_chars:
                cues.append((page[0][1], page[-1][2], text, mono)); page = []
        if page:
            cues.append((page[0][1], page[-1][2], " ".join(x[0] for x in page), mono))
    vtt_out(cues, dest)


def vtt_ts(x):
    h, m, sec = int(x // 3600), int(x % 3600 // 60), x % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


def vtt_out(cues, dest):
    """cues: (t0, t1, text, mono). Each cue holds 0.3 s past its last word unless the next one starts; inner
    monologue is italic (<i>, which YouTube shows), and speakers carry no label, as no badge is burned in either."""
    out = ["WEBVTT", ""]
    for i, (a, b, text, mono) in enumerate(cues):
        b = min(b + 0.3, cues[i + 1][0]) if i + 1 < len(cues) else b + 0.3
        out += [f"{vtt_ts(a)} --> {vtt_ts(b)}", f"<i>{text}</i>" if mono else text, ""]
    Path(dest).write_text("\n".join(out))


def pages(text, max_chars=42):
    """Split a line into caption pages of at most max_chars: a page never runs past a sentence end unless the
    next sentence fits whole on it, and a long sentence wraps at spaces."""
    out = []
    for sent in re.findall(r"\S.*?(?:[.!?…]+[\"'»”)]*(?=\s|$)|$)", text):
        cur = out.pop() if out and len(out[-1]) + 1 + len(sent.strip()) <= max_chars and out[-1][-1:] in ".!?…»”\"')" else ""
        for w in sent.split():
            nxt = (cur + " " + w).strip()
            if cur and len(nxt) > max_chars:
                out.append(cur); cur = w
            else:
                cur = nxt
        if cur:
            out.append(cur)
    return out


def cmd_captions(a):
    """A caption track in another language from translated lines, timed to the English read: each segment's
    translation spans that segment's spoken words (first word to last), its pages sharing the time by length."""
    film = Path(a.film).resolve()
    tl = load_timeline(film)
    tr = json.loads(Path(a.text).read_text())
    spoken = [s for s in tl["segments"] if s.get("words")]
    missing = [s["id"] for s in spoken if not str(tr.get(s["id"], "")).strip()]
    if missing:
        raise SystemExit(f"{len(missing)} spoken segments have no {a.lang} line: {', '.join(missing[:12])}")
    extra = sorted(set(tr) - {s["id"] for s in spoken})
    cues = []
    for s in spoken:
        t0, t1 = s["words"][0][1], s["words"][-1][2]
        pg = pages(tr[s["id"]])
        total = sum(len(x) for x in pg)
        t = t0
        for x in pg:
            d = (t1 - t0) * len(x) / total
            cues.append((round(t, 3), round(t + d, 3), x, s.get("mono")))
            t += d
    dest = film / "out" / f"captions.{a.lang}.vtt"
    vtt_out(cues, dest)
    print(f"{len(cues)} cues -> {dest}")
    if extra:
        print(f"ignored {len(extra)} ids not spoken in this film: {', '.join(extra[:12])}")


def cmd_stills(a):
    import render
    film = Path(a.film).resolve()
    tl = load_timeline(film)
    if a.every:
        ts = [round(x, 2) for x in frange(1.0, tl["duration"], a.every)]
    else:
        ts = [round(s["t0"] + (s["t1"] - s["t0"]) * a.at, 2) for s in tl["segments"]]
    out = film / "review" / ("stills-every" if a.every else "stills-segments")
    out, n, errors = render.stills(film, ts, out)
    print(f"{n} stills -> {out}" + (f" ({len(errors)} page errors)" if errors else ""))
    print("sheet ->", render.sheet(out, out.with_suffix(".png"), cols=6))


def frange(a, b, step):
    x = a
    while x < b:
        yield x
        x += step


def _render_chunk(args):
    film, i0, i1, dest, scale = args
    import render
    with render.Film(Path(film)) as f:
        vf = f"scale=trunc(iw*{scale}/2)*2:trunc(ih*{scale}/2)*2:out_color_matrix=bt709:out_range=tv,format=yuv420p"
        ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                               "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                               str(dest)], stdin=subprocess.PIPE)
        for i in range(i0, i1):
            ff.stdin.write(f.shot(i / FPS))
            if (i - i0) % 900 == 0:
                print(f"  chunk {i0}: frame {i - i0}/{i1 - i0}", flush=True)
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError("ffmpeg failed")
        return dest, len(f.errors)


def cmd_render(a):
    film = Path(a.film).resolve()
    tl = load_timeline(film)
    n = math.ceil(tl["duration"] * FPS)
    parts = film / "out" / "parts"
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir(parents=True, exist_ok=True)
    size = math.ceil(n / a.workers)
    jobs = [(str(film), k, min(n, k + size), str(parts / f"p{k:07d}.mp4"), a.scale) for k in range(0, n, size)]
    with ProcessPoolExecutor(a.workers) as ex:
        results = list(ex.map(_render_chunk, jobs))
    lst = parts / "list.txt"
    lst.write_text("".join(f"file '{Path(d).name}'\n" for d, _ in results))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(film / "out" / "silent.mp4")])
    errs = sum(e for _, e in results)
    print(f"{n} frames -> {film / 'out' / 'silent.mp4'}" + (f" ({errs} page errors)" if errs else ""))


# ── music ─────────────────────────────────────────────────
def cmd_music(a):
    """Pick a library track per chapter from its mood; runs of chapters with one mood share one track."""
    import audio
    film = Path(a.film).resolve()
    tl = load_timeline(film)
    chapters = tl["chapters"]
    default = a.default
    runs = []
    for ch in chapters:
        m = ch.get("mood") or default
        if runs and runs[-1]["mood"] == m:
            runs[-1]["t1"] = ch["t1"]; runs[-1]["chapters"].append(ch["title"])
        else:
            runs.append({"mood": m, "t0": ch["t0"], "t1": ch["t1"], "chapters": [ch["title"]]})
    used, misses = [], []
    for r in runs:
        ranked = audio.rank_tracks(r["mood"])
        if not ranked:
            raise SystemExit("the audio library has no tracks: `studio.py fetch music <id>` first")
        # prefer a track not used by the previous run, so a mood change is heard as a change
        pick = next((x for x in ranked if not used or x[1] != used[-1]), ranked[0])
        r.update(track=pick[1], title=pick[2], score=pick[0], alternatives=[[x[0], x[1], x[2]] for x in ranked[:4]])
        used.append(pick[1])
        if pick[0] < a.fit:
            misses.append(r)
        print(f"{r['t0']:7.1f}-{r['t1']:7.1f}s  {r['mood']:<8} {pick[2]} ({pick[1]}, fit {pick[0]:.2f})  [{', '.join(r['chapters'])}]")
    (film / "out" / "music_plan.json").write_text(json.dumps({"runs": runs}, indent=1))
    for r in misses:
        print(f"NO GOOD FIT for {r['mood']} ({', '.join(r['chapters'])}): best is {r['score']:.2f}. "
              f"Search the library source: {', '.join(audio.MOOD_SEARCH.get(r['mood'], [r['mood']]))}")
    print("plan ->", film / "out" / "music_plan.json", "(edit `track` per run to override)")


def build_bed(film, plan, total, sr=48000, xfade=3.0):
    """The music bed from a plan: each run plays its track from the top (looping on a crossfade if the run is longer);
    the last run is back-timed so the track's own ending lands on the film's end."""
    import numpy as np
    import audio
    cat = audio.catalog()["tracks"]
    bed = np.zeros((int(total * sr) + sr, 2))
    runs = plan["runs"]
    for k, r in enumerate(runs):
        x = audio.load(audio.library_dir() / cat[r["track"]]["file"], stereo=True, sr=sr)
        # level-match tracks to one loudness, so a quiet piano run and a loud score sit at the same depth under the voice
        e = (cat[r["track"]].get("mood") or {}).get("energy")
        if e is not None:
            x = x * 10 ** ((-20.0 - e) / 20)
        a0 = max(0.0, r["t0"] - (xfade / 2 if k else 0))
        a1 = min(total, r["t1"] + (xfade / 2 if k < len(runs) - 1 else 0))
        need = int((a1 - a0) * sr)
        last = k == len(runs) - 1
        if last and len(x) >= need:
            # back-time: start late enough that the track ends with the film (trim trailing silence first)
            env = np.abs(x).max(axis=1)
            end = len(env) - np.argmax(env[::-1] > 0.003)
            seg = x[max(0, end - need):end]
        else:
            reps, seg = [], np.zeros((0, 2))
            n_x = int(xfade * sr)
            while len(seg) < need:
                piece = x.copy()
                if len(seg):
                    ramp = np.linspace(0, 1, n_x)[:, None]
                    seg[-n_x:] = seg[-n_x:] * (1 - ramp) + piece[:n_x] * ramp
                    piece = piece[n_x:]
                seg = np.concatenate([seg, piece])
            seg = seg[:need]
        n = len(seg)
        ramp_n = min(int(xfade * sr), n // 2)
        env = np.ones(n)
        if k:
            env[:ramp_n] = np.linspace(0, 1, ramp_n)
        if not last:
            env[-ramp_n:] = np.minimum(env[-ramp_n:], np.linspace(1, 0, ramp_n))
        i0 = int(a0 * sr)
        bed[i0:i0 + n] += seg * env[:, None]
    bed = bed[:int(total * sr)]
    import wave
    dest = film / "out" / "bed.wav"
    pcm = (np.clip(bed, -1, 1) * 32767).astype("<i2")
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())
    return dest


SFX_GAP = {"buzz": 0.6, "ping": 0.35, "pin": 0.12, "thud": 0.5}    # same-kind sounds closer than this are dropped
SFX_MAX = {"buzz": 0.9, "ping": 1.2, "pin": 0.4, "thud": 0.8, "whoosh": 1.0,    # seconds a cue may ring; longer clips are cut
           "gavel": 3.0, "footsteps-marble": 3.0, "monitor-beep": 3.0, "low-hit": 2.5, "glass-break": 2.0, "door": 2.0,
           "pen-roll": 1.5, "paper-slide": 1.5, "pen-scratch": 1.5, "keys-lock": 1.5, "cutlery": 1.5, "dripping-water": 1.5,
           "seal-stamp": 1.0, "paper-slap": 0.8, "slap": 0.8}
BED_GAIN = 0.3        # an ambience bed sits about 10 dB under the foley hits (the whole sfx bus is then --sfx-db)
BED_FADE = 0.8        # seconds a bed fades in and out at the edges of its run of segments


def kind_key(k):
    """One spelling per kind: "paper slap", "Paper_Slap" and "paper-slap" are the same role."""
    return "-".join(str(k).lower().replace("_", " ").split())


def trim_clip(x, kind, sr=48000, fade=0.06):
    """Cut a recording to the time its kind may ring (a 3 s vibration loop is one buzz, not three), fading the cut."""
    import numpy as np
    n = int(SFX_MAX.get(kind, 1.5) * sr)
    if len(x) <= n:
        return x
    x = x[:n].copy()
    f = int(fade * sr)
    x[-f:] *= np.linspace(1, 0, f)
    return x


def recorded_sfx(kind, trim=True):
    """Library clips catalogued with "role": <kind> (studio.py role <id> <kind>); trim=False keeps a bed's full length."""
    import audio
    try:
        lib, cat = audio.library_dir(), audio.catalog()
    except SystemExit:
        return []
    kind = kind_key(kind)
    return [(k, trim_clip(audio.load(lib / v["file"]), kind) if trim else audio.load(lib / v["file"]))
            for k, v in sorted(cat["sfx"].items()) if v.get("role") and kind_key(v["role"]) == kind and (lib / v["file"]).exists()]


def bed_runs(segs):
    """[(kind, t0, t1)]: a bed over each run of back-to-back segments that ask for it, so it doesn't restart at a cut."""
    runs, open_ = [], {}
    for sg in segs:
        here = set(sg.get("bed") or [])
        for k in list(open_):
            if k not in here:
                runs.append((k, *open_.pop(k)))
        for k in here:
            if k in open_:
                open_[k][1] = sg["t1"]
            else:
                open_[k] = [sg["t0"], sg["t1"]]
    return sorted(runs + [(k, a, b) for k, (a, b) in open_.items()], key=lambda r: r[1])


def lay_bed(x, n, sr=48000, xfade=1.0):
    """Loop a clip to n samples with a crossfade at each seam, and fade the ends of the run."""
    import numpy as np
    f = min(int(xfade * sr), len(x) // 3)
    out = x[:n].copy() if len(x) >= n else None
    if out is None:
        out = x.copy()
        ramp = np.linspace(0, 1, f)
        while len(out) < n:
            out[-f:] = out[-f:] * (1 - ramp) + x[:f] * ramp
            out = np.concatenate([out, x[f:]])
        out = out[:n]
    e = min(int(BED_FADE * sr), n // 2)
    out[:e] *= np.linspace(0, 1, e)
    out[n - e:] *= np.linspace(1, 0, e)
    return out


def build_sfx(film, tl, sr=48000, drawn_ok=False):
    """Small UI sounds under the picture, placed from the timeline: a buzz when a phone lights, a soft ping when a
    message lands, a paper tick when a card is pinned, a thud when a stamp hits. Each kind uses recorded clips from
    the library when any carry that role (cycled, gain varied, transient on the cue, as sound.md asks). A kind with no
    recording is left silent, or drawn in code with drawn_ok (a placeholder: the channel owner found them amateur)."""
    import numpy as np
    import wave

    def tt(d):
        return np.arange(int(d * sr)) / sr

    def thump(d, f0, f1, decay):
        t = tt(d)
        f = f1 + (f0 - f1) * np.exp(-t * 25)
        return np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * decay) * np.minimum(1, t / 0.002)

    rng = np.random.default_rng(3)

    def noise(d, lo, hi, decay):
        from scipy.signal import butter, sosfilt
        t = tt(d)
        return sosfilt(butter(2, [lo / (sr / 2), hi / (sr / 2)], "band", output="sos"), rng.standard_normal(len(t))) * np.exp(-t * decay)

    def buzz():
        t = tt(0.42)
        on = ((t % 0.21) < 0.13).astype(float)
        v = np.sign(np.sin(2 * np.pi * 165 * t)) * 0.5 + np.sin(2 * np.pi * 330 * t) * 0.3
        from scipy.signal import butter, sosfilt
        return sosfilt(butter(2, 900 / (sr / 2), output="sos"), v * on) * 0.5

    def ping():
        t = tt(0.5)
        return (np.sin(2 * np.pi * 1318.5 * t) * np.exp(-t * 9) + 0.6 * np.sin(2 * np.pi * 1975.5 * t) * np.exp(-t * 12) * (t > 0.07)) * np.minimum(1, t / 0.003) * 0.35

    def pin():
        return np.concatenate([noise(0.05, 2000, 6000, 80) * 0.5 + thump(0.05, 180, 120, 60)[:int(0.05 * sr)] * 0.4, np.zeros(10)])

    def thud():
        x = thump(0.4, 90, 45, 9) * 0.9
        x[:int(0.08 * sr)] += noise(0.08, 200, 2500, 40) * 0.4
        return x

    drawn = {"buzz": buzz, "ping": ping, "pin": pin, "thud": thud}
    kinds = {k: recorded_sfx(k) or ([(f"drawn-{k}", f())] if drawn_ok else []) for k, f in drawn.items()}
    for sg in tl["segments"]:           # foley a segment asks for by name: recorded clips only, never drawn
        for x in sg.get("sfx", []):
            kinds.setdefault(kind_key(x["kind"]), recorded_sfx(x["kind"]))
    missing = [k for k, c in kinds.items() if not c]
    events = []
    for sg in tl["segments"]:
        d = sg.get("data") or {}
        if sg["type"] == "stage":
            for b in d.get("beats", []):
                if b.get("t") is None:
                    continue
                if b.get("glow"):
                    events.append((b["t"], "buzz"))
                if b.get("notify"):
                    events.append((b["t"] + (0.12 if b.get("glow") else 0.0), "ping"))
        elif sg["type"] == "board":
            events += [(c["t"] - 0.05, "pin") for c in d.get("cards", []) if c.get("t") is not None]
            if d.get("stamp", {}).get("t") is not None:
                events.append((d["stamp"]["t"] - 0.05 + 0.12, "thud"))
        elif sg["type"] == "sms":
            events.append(((d.get("t") or sg["t0"] + 0.55) - 0.2, "ping"))
        events += [(x.get("t", sg["t0"] + 0.1), kind_key(x["kind"])) for x in sg.get("sfx", [])]
    skipped = sum(1 for _, k in events if k in missing)
    events = sorted(e for e in events if e[1] not in missing)
    kept, last = [], {}
    for t, k in events:
        if t - last.get(k, -9) >= SFX_GAP.get(k, 0.3):
            kept.append((t, k)); last[k] = t
    dropped, events = len(events) - len(kept), kept
    total = tl["duration"]
    out = np.zeros(int(total * sr) + sr)
    used = {k: 0 for k in kinds}
    for t, k in events:
        _, x = kinds[k][used[k] % len(kinds[k])]
        if kinds[k][0][0].startswith("drawn"):                 # drawn sounds start on their cue
            gain, peak = 1.0, 0.0
        else:                                                   # recordings: vary the level, land the transient on the cue
            gain, peak = rng.uniform(0.85, 1.15), np.argmax(np.abs(x[:int(0.6 * sr)])) / sr
        i = int((t - peak) * sr)
        if i < 0:
            x, i = x[-i:], 0
        n = min(len(x), len(out) - i)
        out[i:i + n] += gain * x[:n]
        used[k] += 1
    beds, bed_used, bed_silent = {}, {}, set()
    for k, a, b in bed_runs(tl["segments"]):
        clips = beds.setdefault(k, recorded_sfx(k, trim=False))
        if not clips:
            bed_silent.add(k); continue
        done = bed_used.setdefault(k, [])
        key, x = clips[len(done) % len(clips)]
        i, n = int(a * sr), int((b - a) * sr)
        n = min(n, len(out) - i)
        out[i:i + n] += BED_GAIN * lay_bed(x, n, sr)
        bed_used[k].append(key)
        print(f"  bed {k}: {key} under {a:.1f}-{b:.1f} s")
    if bed_silent:
        print(f"  beds silent: no library clip has role {', '.join(repr(k) for k in sorted(bed_silent))}")
    out = np.stack([out, out], 1)[:int(total * sr)]
    dest = film / "out" / "sfx.wav"
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(out, -1, 1) * 32767).astype("<i2").tobytes())
    print(f"sfx: {len(events)} sounds ({', '.join(f'{k} {used[k]}' for k in kinds)})" + (f", {dropped} too close to the last one dropped" if dropped else ""))
    if skipped:
        print(f"  {skipped} cues silent: no library clip has role {', '.join(repr(k) for k in missing)} (sound.md, long-form UI sounds)")
    for k, clips in kinds.items():
        if used[k]:
            print(f"  {k}: " + (", ".join(c for c, _ in clips) if not clips[0][0].startswith("drawn")
                               else "drawn in code (placeholder)"))
    sounds = {k: [c for c, _ in kinds[k][:used[k]]] for k in kinds if used[k] and not kinds[k][0][0].startswith("drawn")}
    for k, keys in bed_used.items():
        sounds.setdefault(k, []).extend(c for c in dict.fromkeys(keys) if c not in sounds.get(k, []))
    return dest, sounds


def library_whoosh():
    """The first library clip catalogued with "role": "whoosh", as (key, path), or None."""
    import audio
    try:
        lib, cat = audio.library_dir(), audio.catalog()
    except SystemExit:
        return None
    hits = [(k, lib / v["file"]) for k, v in sorted(cat["sfx"].items()) if v.get("role") == "whoosh" and (lib / v["file"]).exists()]
    return hits[0] if hits else None


def cmd_mix(a):
    """Narration on top; the music bed ducked under the voice; an optional whoosh at each chapter start."""
    film = Path(a.film).resolve()
    tl = load_timeline(film)
    total = tl["duration"]
    narr = film / "out" / "narration.wav"
    sounds = {}                                          # what the mix used, for `credits`
    inputs = ["-i", str(narr)]
    filt = ["[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[voice][key]"]
    if a.plan:
        plan = json.loads((film / "out" / "music_plan.json").read_text())
        sounds["music"] = list(dict.fromkeys(r["track"] for r in plan["runs"]))
        bed = build_bed(film, plan, total)
        inputs += ["-i", str(bed)]
        filt.append(f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={a.bed_db}dB,afade=t=in:d=1.0[bed]")
        filt.append("[bed][key]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=600[ducked]")
        mix_in = ["[voice]", "[ducked]"]
    elif a.music:
        tracks = [Path(p) for p in a.music.split(",")]
        sounds["music"] = [str(t) for t in tracks]
        seq, k = [], 0
        while sum(duration(t) for t in seq) < total + 5:
            seq.append(tracks[k % len(tracks)]); k += 1
        for t in seq:
            inputs += ["-i", str(t)]
        filt.append("[1:a]aformat=sample_rates=48000:channel_layouts=stereo[m0]")
        for i in range(1, len(seq)):
            filt.append(f"[{i + 1}:a]aformat=sample_rates=48000:channel_layouts=stereo[r{i}]")
            filt.append(f"[m{i - 1}][r{i}]acrossfade=d=4:c1=tri:c2=tri[m{i}]")
        filt.append(f"[m{len(seq) - 1}]atrim=0:{total},volume={a.bed_db}dB,afade=t=in:d=1.5,afade=t=out:st={max(0, total - 4)}:d=4[bed]")
        filt.append("[bed][key]sidechaincompress=threshold=0.02:ratio=6:attack=40:release=600[ducked]")
        mix_in = ["[voice]", "[ducked]"]
    else:
        mix_in = ["[voice]"]
    whoosh = None
    if a.whoosh and Path(a.whoosh).exists():
        whoosh = (a.whoosh, Path(a.whoosh))
    elif a.whoosh:                                       # a catalog id
        import audio
        e = audio.catalog()["sfx"].get(a.whoosh)
        if e is None:
            raise SystemExit(f"--whoosh {a.whoosh}: not a file or a catalogued sfx id")
        whoosh = (a.whoosh, audio.library_dir() / e["file"])
    elif a.whoosh is None:                               # default: the library's whoosh, if one carries the role
        whoosh = library_whoosh()
    if whoosh and len(tl["chapters"]) > 1:
        sounds["whoosh"] = whoosh[0]
        base = len(inputs) // 2
        inputs += ["-i", str(whoosh[1])]
        cuts = [ch["t0"] for ch in tl["chapters"][1:]]
        wmax = SFX_MAX["whoosh"]
        filt.append(f"[{base}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{wmax},afade=t=out:st={wmax - 0.06}:d=0.06,"
                    f"volume=-10dB,asplit={len(cuts)}" +
                    "".join(f"[w{i}]" for i in range(len(cuts))))
        for i, c in enumerate(cuts):
            ms = int(max(0, c - 0.25) * 1000)
            filt.append(f"[w{i}]adelay={ms}|{ms}[wd{i}]")
            mix_in.append(f"[wd{i}]")
    if a.sfx:
        base = len(inputs) // 2
        sfx_wav, sounds["sfx"] = build_sfx(film, tl, drawn_ok=a.sfx_drawn)
        inputs += ["-i", str(sfx_wav)]
        filt.append(f"[{base}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={a.sfx_db}dB[sfx]")
        mix_in.append("[sfx]")
    filt.append("".join(mix_in) + f"amix=inputs={len(mix_in)}:normalize=0:dropout_transition=0,atrim=0:{total}[pre]")
    script = film / "out" / "mix.filter"
    script.write_text(";".join(filt))
    pre = film / "out" / "premix.wav"
    run(["ffmpeg", "-v", "error", "-y", *inputs, *filter_file(script), "-map", "[pre]", "-ar", "48000", str(pre)])
    # two-pass loudness to -14 LUFS; -2.5 dBTP leaves room for the AAC encode's overshoot
    meas = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(pre), "-af", "loudnorm=I=-14:TP=-2.5:LRA=11:print_format=json", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    j = json.loads(meas[meas.rfind("{"):])
    ln = (f"loudnorm=I=-14:TP=-2.5:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}:"
          f"measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(pre), "-af", ln, "-ar", "48000", str(film / "out" / "mix.wav")])
    (film / "out" / "sounds_used.json").write_text(json.dumps(sounds, indent=1) + "\n")
    print("mix ->", film / "out" / "mix.wav", "(sounds used -> out/sounds_used.json; run `credits` for the description)")


def attribution_needed(licence):
    """CC BY needs a credit line; CC0, Mixkit and Kenney do not. NC/ND/SA never enter the library (studio.py import-sfx)."""
    return "CC BY" in licence.upper().replace("-", " ") or "/LICENSES/BY/" in licence.upper()


def cmd_credits(a):
    """The attribution lines for every catalogued sound the last mix used -> out/credits.txt, for the video description.
    A used sound with no licence in the catalog stops here: it doesn't ship (sound.md)."""
    import audio
    film = Path(a.film).resolve()
    used = film / "out" / "sounds_used.json"
    if not used.exists():
        raise SystemExit(f"no {used}: run `mix` first")
    u = json.loads(used.read_text())
    cat = audio.catalog()
    keys = [("tracks", k) for k in u.get("music", [])] + ([("sfx", u["whoosh"])] if u.get("whoosh") else [])
    keys += [("sfx", k) for ks in (u.get("sfx") or {}).values() for k in ks]
    lines, free, unknown = [], [], []
    for table, k in dict.fromkeys(keys):
        e = cat[table].get(k)
        if e is None:
            unknown.append(k)                            # a raw file path given to --music / --whoosh
            continue
        lic = e.get("licence", "")
        if not lic:
            raise SystemExit(f"{k} has no licence in catalog.json: it can't ship (sound.md)")
        if attribution_needed(lic):
            lines.append(e.get("attribution") or
                         f'"{e.get("title") or k}" by {e.get("creator", "unknown")} ({e.get("url", "")}), {e.get("licence_name", lic)}')
        else:
            free.append(k)
    out = film / "out" / "credits.txt"
    out.write_text(("Sound credits:\n" + "\n".join(lines) + "\n") if lines else "")
    print(f"credits -> {out} ({len(lines)} attribution lines; {len(free)} sounds need none: {', '.join(free) or '-'})")
    if unknown:
        print(f"  not in the catalog, check their licence by hand: {', '.join(unknown)}")


def cmd_final(a):
    import verify
    film = Path(a.film).resolve()
    out = film / "out" / f"{film.name}.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(film / "out" / "silent.mp4"), "-i", str(film / "out" / "mix.wav"),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out)])
    # scene wipes and stamps are meant to hit: don't call them pops
    tl = load_timeline(film)
    allow = [(sg["t0"], sg["t0"] + 0.5) for sg in tl["segments"] if sg["type"] in ("stage", "board", "crowd")]
    allow += [(sg["t1"], sg["t1"] + 0.5) for sg in tl["segments"] if sg["type"] in ("stage", "board", "crowd")]
    allow += [(sg["data"]["stamp"]["t"], sg["data"]["stamp"]["t"] + 0.25) for sg in tl["segments"]
              if sg["type"] == "board" and sg.get("data", {}).get("stamp", {}).get("t") is not None]
    ok = verify.verify(out, bpm=None, sheet_dest=None, bg=(11, 11, 11), allow=allow)
    print(out)
    sys.exit(0 if ok else 1)


# ── check: the numbers a critic should start from ─────────
def frame_diffs(video, fps=10, w=192, h=108, local=False):
    """Mean absolute luma change between consecutive frames (0..1), sampled at `fps`. With local=True, also the
    largest change in any 12x12 block above the caption band, so a small reveal (a spoke label) still counts."""
    import numpy as np
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    prev, d, loc = None, [], []
    band = int(h * 0.84) // 12 * 12                      # captions and the source line live below this
    while True:
        b = p.stdout.read(w * h)
        if len(b) < w * h:
            break
        f = np.frombuffer(b, np.uint8).astype(np.int16)
        if prev is not None:
            diff = np.abs(f - prev)
            d.append(float(diff.mean()) / 255)
            if local:
                blocks = diff.reshape(h, w)[:band].reshape(band // 12, 12, w // 12, 12).mean(axis=(1, 3))
                loc.append(float(blocks.max()) / 255)
        prev = f
    p.wait()
    return (np.array(d), np.array(loc)) if local else np.array(d)


def cmd_check(a):
    """Dead air, text-only stretches, cue landings and one-frame flashes, measured from the timeline and the render."""
    import numpy as np
    film = Path(a.film).resolve()
    tl = load_timeline(film)
    segs, total = tl["segments"], tl["duration"]
    report, flags = [], []
    # 1. picture variety from the timeline: how much of the film is words on a background
    text_time = sum(s["t1"] - s["t0"] for s in segs if s["type"] in TEXT_ONLY)
    run_t, run0, worst = 0.0, None, (0.0, None, None)
    for s in segs:
        if s["type"] in TEXT_ONLY:
            run0 = run0 or s; run_t += s["t1"] - s["t0"]
            if run_t > worst[0]:
                worst = (run_t, run0["id"], s["id"])
        else:
            run_t, run0 = 0.0, None
    share = text_time / total
    report.append(f"text-only scenes: {share:.0%} of the film; longest run {worst[0]:.0f} s ({worst[1]}..{worst[2]})")
    if share > a.max_text:
        flags.append(f"{share:.0%} of the film is text on a background (limit {a.max_text:.0%}): turn statements into stage, board or crowd scenes")
    if worst[0] > a.max_text_run:
        flags.append(f"text-only run of {worst[0]:.0f} s from {worst[1]} to {worst[2]} (limit {a.max_text_run:.0f} s)")
    types = [s["type"] for s in segs]
    repeats = [(types[i], segs[i]["id"]) for i in range(2, len(types)) if types[i] == types[i - 1] == types[i - 2]]
    for ty, sid in repeats:
        flags.append(f"three {ty} scenes in a row ending at {sid}")
    video = film / "out" / "silent.mp4"
    if not video.exists():
        report.append("no render yet: run `render` for dead-air, cue and flash checks")
    else:
        fps = 10
        d, loc = frame_diffs(video, fps, local=True)
        ev = d > a.event
        times = np.nonzero(ev)[0] / fps
        # 2. dead air: stretches with no visible event
        gaps = np.diff(np.concatenate([[0.0], times, [total]]))
        starts = np.concatenate([[0.0], times])
        seg_at = lambda t: next((s["id"] for s in segs if s["t0"] <= t < s["t1"]), "end")
        holds = [(starts[i], gaps[i]) for i in range(len(gaps)) if gaps[i] >= a.hold]
        n_ev = int((ev[1:] & ~ev[:-1]).sum() + (1 if len(ev) and ev[0] else 0))     # a run of changing frames is one event
        report.append(f"visible events: {n_ev} ({n_ev / total * 60:.0f}/min); holds over {a.hold:.0f} s: {len(holds)}")
        for t0, g in holds:
            flags.append(f"nothing new on screen for {g:.1f} s from {t0:.1f} s ({seg_at(t0 + 0.1)})")
        # per chapter: events per minute and stillness, so a flat chapter stands out
        for ch in tl["chapters"]:
            k0, k1 = int(ch["t0"] * fps), int(ch["t1"] * fps)
            sl = d[k0:k1]
            if len(sl) < fps:
                continue
            e = sl > a.event
            epm = (e[1:] & ~e[:-1]).sum() / (len(sl) / fps) * 60
            still = float((sl < a.event / 4).mean())
            report.append(f"  {ch['title'][:28]:<28} {epm:4.0f} events/min, {still:.0%} still")
        # 3. cue landings: something visible should change within -0.2..+0.8 s of each cued word
        missed = []
        for c in tl.get("cues", []):
            k0, k1 = int(max(0, c["t"] - 0.2) * fps), int((c["t"] + 0.8) * fps) + 1
            if not ((d[k0:k1] > a.event) | (loc[k0:k1] > a.local)).any():
                missed.append(c)
        report.append(f"word cues: {len(tl.get('cues', []))}, {len(missed)} with no visible change near the word")
        for c in missed:
            flags.append(f"cue \"{c['at']}\" in {c['seg']} at {c['t']:.1f} s: nothing changes on screen")
        # 4. one-frame flashes at full rate: frame n differs from both neighbours while they match each other
        p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        win, n, flashes = [], 0, []
        while True:
            b = p.stdout.read(160 * 90)
            if len(b) < 160 * 90:
                break
            win.append(np.frombuffer(b, np.uint8).astype(np.int16)); n += 1
            if len(win) == 3:
                a0, a1, a2 = win
                d01, d12, d02 = np.abs(a1 - a0).mean(), np.abs(a2 - a1).mean(), np.abs(a2 - a0).mean()
                if min(d01, d12) > 6 and d02 < 0.35 * min(d01, d12):
                    flashes.append((n - 2) / FPS)
                win.pop(0)
        p.wait()
        report.append(f"one-frame flashes: {len(flashes)}")
        for t in flashes:
            flags.append(f"one-frame flash at {t:.2f} s ({seg_at(t)})")
    print("\n".join(report))
    print(f"\n{len(flags)} flag(s)" + (":" if flags else ""))
    for f in flags:
        print("FLAG:", f)
    (film / "review" / "check.txt").write_text("\n".join(report + [""] + ["FLAG: " + f for f in flags]) + "\n")


def cmd_share(a):
    """A page that streams the finished cut, for sending a draft to someone without a download. The artifact host
    serves neither .m3u8 nor .ts and caps each file at 15 MB and each publish at 64 MB, so the cut is split into
    fMP4 HLS segments named .mp4 with the playlist as index.txt, and the page plays them through hls.js."""
    import base64
    import html
    film = Path(a.film).resolve()
    src = film / "out" / f"{film.name}.mp4"
    if not src.exists():
        raise SystemExit(f"{src} is missing: run final first")
    sc, tl = load_script(film), load_timeline(film)
    meta = sc.get("share", {})
    dest = film / "out" / "share"
    shutil.rmtree(dest, ignore_errors=True)
    (dest / "v").mkdir(parents=True)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-c", "copy", "-f", "hls", "-hls_time", str(a.segment),
         "-hls_playlist_type", "vod", "-hls_segment_type", "fmp4", "-hls_fmp4_init_filename", "init.mp4",
         "-hls_segment_filename", str(dest / "v" / "seg%02d.mp4"), str(dest / "v" / "index.m3u8")])
    (dest / "v" / "index.m3u8").rename(dest / "v" / "index.txt")
    sizes = {f.name: f.stat().st_size for f in sorted((dest / "v").iterdir())}
    big = [n for n, b in sizes.items() if b > 14e6]
    if big:
        raise SystemExit(f"segments over 14 MB ({', '.join(big)}): rerun with a smaller --segment")
    poster = dest / "poster.jpg"
    at = meta.get("poster_at", min(tl["duration"] * 0.25, tl["chapters"][1]["t0"] + 3 if len(tl["chapters"]) > 1 else 5))
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=960:-2", "-q:v", "5", str(poster)])
    mins = round(tl["duration"] / 60)
    fill = {
        "TITLE": sc["title"], "HEADLINE": meta.get("headline", sc["title"]), "LEDE": meta.get("lede", "Draft cut, not yet published."),
        "EYEBROW": meta.get("eyebrow", f"Explainer · {mins} min"), "FOOT": meta.get("foot", "Sound on."),
        "ACCENT": (sc.get("palette") or {}).get("ACCENT", "#e8772e"),
    }
    page = (HERE.parent / "assets" / "templates" / "share.html").read_text()
    for k, v in fill.items():
        page = page.replace("{{" + k + "}}", html.escape(v))
    chapters = [[f"{int(c['t0'] if i else 0) // 60}:{int(c['t0'] if i else 0) % 60:02d}", c["title"]] for i, c in enumerate(tl["chapters"])]
    page = page.replace("{{CHAPTERS}}", json.dumps(chapters).replace("</", "<\\/"))
    page = page.replace("{{POSTER}}", "data:image/jpeg;base64," + base64.b64encode(poster.read_bytes()).decode())
    (dest / "index.html").write_text(page)
    total = sum(sizes.values())
    print(f"share -> {dest}/index.html + v/ ({len(sizes)} files, {total / 1e6:.1f} MB)")
    print("publish index.html as a private artifact with every file in v/ under its own name (v/index.txt, v/init.mp4, v/seg00.mp4 ...)")
    if total > 60e6:
        print("over 60 MB: one publish carries at most 64 MB, so publish the page with the first segments, then the rest to the same url")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init"); p.add_argument("film"); p.set_defaults(fn=cmd_init)
    p = sp.add_parser("lines"); p.add_argument("film"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_lines)
    p = sp.add_parser("panels"); p.add_argument("film"); p.set_defaults(fn=cmd_panels)
    p = sp.add_parser("lint"); p.add_argument("source", help="a film folder, or a JSON list of panel prompts")
    p.add_argument("--boiler", help="regex: sentences to leave out of the word count (reference lines and a shared last sentence already are)")
    p.set_defaults(fn=cmd_lint)
    p = sp.add_parser("review"); p.add_argument("film"); p.add_argument("--checks", help="a checker's verdicts per image (JSON)")
    p.set_defaults(fn=cmd_review)
    p = sp.add_parser("repair"); p.add_argument("film"); g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--beat"); g.add_argument("--image")
    p.add_argument("--box", required=True, help="x,y,w,h in panel pixels, or all four in 0-1 (as the review sheet gives them)")
    p.add_argument("--prompt", required=True, help='what to redraw, e.g. "Redraw the right hand in image 1 with five fingers ..."')
    p.add_argument("--ref", help="a second image, e.g. the sleeve and hand cropped from the character sheet")
    p.add_argument("--model", choices=sorted(panelqa.GENERATORS), default="qwen",
                   help="qwen (default) redraws pose and anatomy; klein is about 4x faster but barely changes a large box")
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    p.add_argument("--context", type=float, default=2.25, help="crop side as a multiple of the box's longer side")
    p.add_argument("--margin", type=int, default=32, help="pixels the paste reaches past the box, so a redraw that spills out is kept")
    p.add_argument("--feather", type=float, default=16, help="pixels of blend inside the paste edge (keep it at most --margin)")
    p.add_argument("--gen-size", type=int, help="generate at this size instead of the crop's own (enlarged with Real-ESRGAN when installed)")
    p.add_argument("--no-color-match", action="store_true", help="paste the redraw's colours as they came back")
    p.add_argument("--min-change", type=float, default=0.10,
                   help="drop a seed that changed less than this share of the box by more than 60 levels (0 keeps all)")
    p.add_argument("--gen-args", help='extra mflux arguments, e.g. "-q 8" or "--lora-paths x.safetensors --steps 8"')
    p.set_defaults(fn=cmd_repair)
    p = sp.add_parser("gemini-draw"); p.add_argument("film")
    p.add_argument("--beats", nargs="+", help="only these beats (or panel image paths)")
    p.add_argument("--jobs", help="a JSON list of {image, prompt, refs: [{path, role}], plate, model} instead of script.json")
    p.add_argument("--model", help="flash (Nano Banana 2.1, default) or pro (Nano Banana Pro), or a model id")
    p.add_argument("--size", choices=["1K", "2K", "4K"], help='default 1K (then `upscale`); a panel\'s own "size": "2K" wins')
    p.add_argument("--now", action="store_true", help="interactive, at full price")
    p.add_argument("--redo", action="store_true", help="also panels that exist (moved to history/ first)")
    p.add_argument("--dry-run", action="store_true", help="print each prompt and the price; send nothing"); p.set_defaults(fn=cmd_gemini_draw)
    p = sp.add_parser("gemini-collect"); p.add_argument("film"); p.add_argument("--wait", action="store_true")
    p.add_argument("--every", type=int, default=300, help="seconds between checks with --wait"); p.set_defaults(fn=cmd_gemini_collect)
    p = sp.add_parser("gemini-edit"); p.add_argument("film"); g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--beat"); g.add_argument("--image")
    p.add_argument("--instruction", required=True, help='one change, verb first: "Move the man up the bed against the headboard"')
    p.add_argument("--keep", action="append", help='what must stay exactly the same, e.g. --keep "the room" --keep "every face"')
    p.add_argument("--ref", action="append", help="an extra image, path or path:role (e.g. plates/sickroom.png:the room plate)")
    p.add_argument("--model"); p.add_argument("--size", choices=["1K", "2K", "4K"], help="default 1K"); p.set_defaults(fn=cmd_gemini_edit)
    p = sp.add_parser("gemini-spend"); p.add_argument("--last", type=int, default=10); p.set_defaults(fn=cmd_gemini_spend)
    p = sp.add_parser("accept"); p.add_argument("film"); p.add_argument("repair", help="the repair id, e.g. panels/p07/r02")
    p.add_argument("--seed", type=int); p.set_defaults(fn=cmd_accept)
    p = sp.add_parser("revert"); p.add_argument("film"); p.add_argument("repair"); p.set_defaults(fn=cmd_revert)
    p = sp.add_parser("upscale"); p.add_argument("film"); p.add_argument("--size", default="2304x1296")
    p.add_argument("--model", default="realesrgan-x4plus-anime"); p.add_argument("--bin", default="realesrgan-ncnn-vulkan")
    p.add_argument("--redo", action="store_true"); p.set_defaults(fn=cmd_upscale)
    p = sp.add_parser("align"); p.add_argument("film"); p.add_argument("--redo", action="store_true"); p.set_defaults(fn=cmd_align)
    p = sp.add_parser("timeline"); p.add_argument("film"); p.add_argument("--pad", type=float, default=0.45)
    p.add_argument("--lead", type=float, default=0.3); p.add_argument("--tail", type=float, default=1.5); p.set_defaults(fn=cmd_timeline)
    p = sp.add_parser("captions"); p.add_argument("film"); p.add_argument("--lang", required=True)
    p.add_argument("--text", required=True, help='JSON {"<segment id>": "translated line"}'); p.set_defaults(fn=cmd_captions)
    p = sp.add_parser("stills"); p.add_argument("film"); p.add_argument("--every", type=float); p.add_argument("--at", type=float, default=0.75)
    p.set_defaults(fn=cmd_stills)
    p = sp.add_parser("render"); p.add_argument("film"); p.add_argument("--workers", type=int, default=4); p.add_argument("--scale", type=float, default=1.0)
    p.set_defaults(fn=cmd_render)
    p = sp.add_parser("music"); p.add_argument("film"); p.add_argument("--default", default="serious"); p.add_argument("--fit", type=float, default=0.6)
    p.set_defaults(fn=cmd_music)
    p = sp.add_parser("mix"); p.add_argument("film"); p.add_argument("--plan", action="store_true"); p.add_argument("--music")
    p.add_argument("--whoosh", help="a file or catalog id for the chapter-start whoosh (default: the library clip with role whoosh)")
    p.add_argument("--no-whoosh", dest="whoosh", action="store_const", const="", help="no whoosh at chapter starts")
    p.add_argument("--bed-db", type=float, default=-25.5)
    p.add_argument("--sfx", action=argparse.BooleanOptionalAction, default=True,
                   help="UI sounds from the timeline: phone buzz, message ping, card pin, stamp (on by default; --no-sfx)")
    p.add_argument("--sfx-drawn", action="store_true", help="fill kinds with no recorded clip with code-drawn placeholders")
    p.add_argument("--sfx-db", type=float, default=-12); p.set_defaults(fn=cmd_mix)
    p = sp.add_parser("credits"); p.add_argument("film"); p.set_defaults(fn=cmd_credits)
    p = sp.add_parser("final"); p.add_argument("film"); p.set_defaults(fn=cmd_final)
    p = sp.add_parser("check"); p.add_argument("film"); p.add_argument("--hold", type=float, default=4.0)
    p.add_argument("--event", type=float, default=0.0008, help="mean luma change that counts as something happening")
    p.add_argument("--local", type=float, default=0.02, help="change in one small block that counts as a cue landing (small reveals)")
    p.add_argument("--max-text", type=float, default=0.4); p.add_argument("--max-text-run", type=float, default=25.0)
    p.set_defaults(fn=cmd_check)
    p = sp.add_parser("share"); p.add_argument("film"); p.add_argument("--segment", type=float, default=60, help="seconds per streamed file")
    p.set_defaults(fn=cmd_share)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
