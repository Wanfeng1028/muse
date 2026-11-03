#!/usr/bin/env python3
"""motion-studio command line.

  studio.py new <slug> [--format 4x5|9x16|16x9] [--bpm 120] [--bars 16] [--title "..."]
  studio.py stills <film> [t ...] [--bars] [--out DIR]     one PNG per time, or one per bar
  studio.py sheet <dir> [--out PNG] [--cols 6]             contact sheet of a folder of stills
  studio.py draft <film>                                   half-res, no blur, fast; + per-beat sheet
  studio.py final <film> [--sub 4]                         full-res with motion blur; muxes out/mix.wav if present; verifies
  studio.py verify <film|video.mp4>                        specs, fast start, decode, frame-0 colour, loudness, pops
  studio.py blindpack <film> [--redo]                      packet for a blind reader (stills + on-screen text + prompt)
  studio.py serve <film> [--port 4173] [--launch]          live preview; --launch writes .claude/launch.json (Browser pane: preview_start "motion-studio")
  studio.py notes <film> [--all] [--resolve ID --reply "what changed"]   read / close the notes pinned in the preview
  studio.py search music|sfx <category>                    Mixkit ids + titles for a category page (e.g. music house, sfx footsteps)
  studio.py fetch music|sfx <id> [<id> ...] | fetch kenney [<pack>]   download into the shared library + catalog
  studio.py measure <track-id>                              beat grid + corrected downbeat + bar loudness map (sections)
  studio.py library                                         what the library holds
  studio.py import-sfx <dir> [--roles N]                    add a staged folder (manifest.json, ranking.json) to the library
  studio.py role <sfx-id> <kind> | role <sfx-id> --clear    the clips mix uses for a kind (buzz, ping, pin, thud, whoosh, pop)
  studio.py audition [<kind> ...] [--out DIR]               a page to hear every candidate per kind (publish as a private artifact)
  studio.py mix <film>                                      run the film's sound.py -> out/mix.wav, then report loudness

  studio.py config                                         paths in use (films, library, ledger, house notes); creates the ledger

<film> is a slug under the films root or a path. Paths come from ~/.motion-studio.json
({"root", "library", "ledger", "house"}); defaults live under ~/motion-studio/.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))


def config():
    cfg = {"root": "~/motion-studio/films", "library": "~/motion-studio/library",
           "ledger": "~/motion-studio/ledger.md", "house": "~/motion-studio/house.md"}
    path = Path.home() / ".motion-studio.json"
    if path.exists():
        cfg.update(json.loads(path.read_text()))
    return {k: Path(v).expanduser() for k, v in cfg.items()}


def film_dir(arg):
    p = Path(arg).expanduser()
    if p.suffix == ".mp4":
        return p
    if not (p.exists() or "/" in arg):
        p = config()["root"] / arg
    if not (p / "film.html").exists():
        raise SystemExit(f"no film.html in {p}")
    return p.resolve()


def cmd_config(a):
    cfg = config()
    if not cfg["ledger"].exists():
        cfg["ledger"].parent.mkdir(parents=True, exist_ok=True)
        cfg["ledger"].write_text((SKILL / "assets/templates/ledger.md").read_text())
    for k in ("root", "library", "ledger", "house"):
        state = "" if cfg[k].exists() else "  (not present)"
        print(f"{k:8s} {cfg[k]}{state}")
    if cfg["house"].exists():
        print("house notes exist: read them before starting a film")


def cmd_new(a):
    root = config()["root"]
    dest = root / a.slug
    if (dest / "film.html").exists():
        raise SystemExit(f"{dest} already has a film; pick another slug")
    for sub in ("review", "out", "sources"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "kit.js", dest / "kit.js")      # vendored: films never load from the plugin cache,
    shutil.copy(HERE / "audio.py", dest / "audio.py")  # whose path changes with every version
    title = a.title or a.slug.replace("-", " ").title()
    html = (SKILL / "assets/templates/film.html").read_text()
    for k, v in {"{{TITLE}}": title, "{{FORMAT}}": a.format, "{{BPM}}": str(a.bpm), "{{BARS}}": str(a.bars)}.items():
        html = html.replace(k, v)
    (dest / "film.html").write_text(html)
    for extra in ("storyboard.md", "sound.py"):
        src = SKILL / "assets/templates" / extra
        if src.exists():
            (dest / extra).write_text(src.read_text().replace("{{TITLE}}", title))
    print(dest)


def cmd_stills(a):
    import render
    out = Path(a.out) if a.out else film_dir(a.film) / "review" / time.strftime("stills-%H%M%S")
    out, n, errors = render.stills(film_dir(a.film), a.times, out, bars=a.bars)
    print(f"{n} stills -> {out}" + (f"  ({len(errors)} page errors)" if errors else ""))
    if n > 1:
        print("sheet ->", render.sheet(out, out.with_suffix(".png"), cols=a.cols))


def cmd_sheet(a):
    import render
    print(render.sheet(Path(a.dir), Path(a.out) if a.out else Path(a.dir).with_suffix(".png"), cols=a.cols))


def _studio(film):
    import render
    with render.Film(film) as f:
        return f.studio


def _bg(s):
    """The film's ground colour as RGB (kit films record it; older films are house black)."""
    h = (s or {}).get("bg", "#0b0b0b").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def cmd_draft(a):
    import render, verify
    film = film_dir(a.film)
    dest = render.film(film, film / "out" / "draft.mp4", scale=0.5, sub=1)
    s = _studio(film)
    if s:
        print("per-beat sheet ->", verify.beat_sheet(dest, s["bpm"], film / "review" / "draft-contact.png"))
    print(dest)


def cmd_final(a):
    import render, verify
    film = film_dir(a.film)
    silent = render.film(film, film / "out" / f"{film.name}-silent.mp4", scale=1.0, sub=a.sub)
    mix = film / "out" / "mix.wav"
    final = render.mux(silent, mix, film / "out" / f"{film.name}.mp4") if mix.exists() else silent
    if not mix.exists():
        print("INFO no out/mix.wav yet: final is silent")
    s = _studio(film)
    ok = verify.verify(final, bpm=s["bpm"] if s else None, sheet_dest=film / "review" / "final-contact.png", bg=_bg(s))
    print(final)
    sys.exit(0 if ok else 1)


def cmd_verify(a):
    import verify
    target = Path(a.target).expanduser()
    if target.suffix == ".mp4":
        video, s = target, None
    else:
        film = film_dir(a.target)
        video = next((p for p in [film / "out" / f"{film.name}.mp4", film / "out" / f"{film.name}-silent.mp4"] if p.exists()), None)
        if not video:
            raise SystemExit("no final render in out/; run `final` first")
        s = _studio(film)
    ok = verify.verify(video, bpm=s["bpm"] if s else None, sheet_dest=(video.parent.parent / "review" / "final-contact.png") if s else None, bg=_bg(s))
    sys.exit(0 if ok else 1)


def cmd_blindpack(a):
    import verify
    film = film_dir(a.film)
    s = _studio(film)
    if not s:
        raise SystemExit("blindpack needs window.STUDIO (films built with kit.js); for older films, assemble the packet by hand")
    video = next((p for p in [film / "out" / f"{film.name}.mp4", film / "out" / f"{film.name}-silent.mp4"] if p.exists()), None)
    if not video:
        raise SystemExit("no final render in out/; run `final` first")
    base = film / "review" / "blind-read"
    n = 1 + len([p for p in base.glob("round-*") if p.is_dir()]) if base.exists() else 1
    if a.redo and n > 1:
        n -= 1                              # rebuild the latest round: only while no reader has seen it
        shutil.rmtree(base / f"round-{n}")
    dest = verify.blindpack(film, video, s, base / f"round-{n}")
    print(dest)


def cmd_serve(a):
    import preview
    film = film_dir(a.film)
    if a.launch:
        path = Path.cwd() / ".claude" / "launch.json"
        path.parent.mkdir(exist_ok=True)
        data = json.loads(path.read_text()) if path.exists() else {"version": "0.0.1", "configurations": []}
        data["configurations"] = [c for c in data["configurations"] if c.get("name") != "motion-studio"]
        data["configurations"].append({"name": "motion-studio", "runtimeExecutable": sys.executable,
                                       "runtimeArgs": [str(HERE / "studio.py"), "serve", str(film), "--port", str(a.port)], "port": a.port})
        path.write_text(json.dumps(data, indent=2) + "\n")
        print(f"wrote {path}: in the Browser pane, preview_start name=motion-studio (preview_stop first if another film is open)")
        return
    preview.serve(film, a.port)


def cmd_notes(a):
    import preview
    film = film_dir(a.film)
    if a.resolve is not None:
        n = preview.resolve_note(film, a.resolve, a.reply or "done")
        print(f"#{n['id']} done: {n['reply']}")
    else:
        preview.list_notes(film, show_all=a.all)


def cmd_search(a):
    import audio
    for mid, title in audio.mixkit_search(a.kind, a.query):
        print(f"mixkit-{mid}  {title}")


def cmd_fetch(a):
    import audio
    if a.kind == "kenney":
        print(audio.fetch_kenney(a.ids[0] if a.ids else "impact-sounds"))
        return
    for mid in a.ids:
        key, dest = audio.fetch_mixkit(a.kind, mid.replace("mixkit-", ""))
        print(key, dest)
        if a.kind == "music":
            e = audio.measure(key)
            print(f"  {e['bpm']} bpm, downbeat {e['downbeat']} s (+{e['phase_shift_beats']} beats), spread {e['grid_spread_ms']} ms")


def cmd_measure(a):
    import audio
    e = audio.measure(a.track)
    print(f"{a.track} {e.get('title', '')}: {e['bpm']} bpm, downbeat {e['downbeat']} s (raw {e['raw_downbeat']:.4f}, +{e['phase_shift_beats']} beats), spread {e['grid_spread_ms']} ms")
    print("bar loudness (dB) — sections are where this jumps:")
    for i in range(0, len(e["bar_loudness_db"]), 16):
        print(f"  bars {i:3d}+: " + " ".join(f"{v:4.0f}" for v in e["bar_loudness_db"][i:i + 16]))


def cmd_library(a):
    import audio
    cat = audio.catalog()
    print("library:", audio.library_dir())
    for k, e in cat["tracks"].items():
        if "downbeat" not in e:
            print(f"  music {k:12s} {e.get('title', ''):24s} not measured (studio.py measure {k})")
            continue
        secs = " ".join(f"{a}-{b - 1}:{db:.0f}dB" for a, b, db in audio.sections(e["bar_loudness_db"]))
        print(f"  music {k:12s} {e.get('title', ''):24s} bpm {e['bpm']} (use exactly this in K.setup), {e.get('duration_s', '?')} s")
        print(f"        sections (song bars:loudness): {secs}")
    for k, e in cat["sfx"].items():
        tag = f"role {e['role']}" if e.get("role") else (f"candidate {', '.join(audio.candidate_kinds(e))}" if audio.candidate_kinds(e) else "")
        print(f"  sfx   {k:12s} {e.get('title', '')}" + (f"  [{tag}; {e.get('licence_name', '')}]" if tag else ""))
    for k, e in cat["packs"].items():
        print(f"  pack  {k}  ({e['dir']})")


def cmd_import_sfx(a):
    import audio
    added, refused = audio.import_sfx(a.dir, roles=a.roles)
    cat = audio.catalog()["sfx"]
    print(f"imported {len(added)} clips into {audio.library_dir()}")
    added = list(dict.fromkeys(added))
    for kind in sorted({kd for k in added for kd in audio.candidate_kinds(cat[k])}):
        group = [k for k in added if kind in audio.candidate_kinds(cat[k])]
        picks = [k for k in group if cat[k].get("role") == kind]
        print(f"  {kind}: {len(group)} candidates" + (f", role given to {', '.join(picks)}" if picks else ""))
    for f, lic in refused:
        print(f"  refused {f}: {lic} (only commercial-use licences without NC, ND or SA)")


def cmd_role(a):
    import audio
    if not a.clear and not a.kind:
        raise SystemExit("give a kind, or --clear")
    audio.set_role(a.id, None if a.clear else a.kind)
    print(f"{a.id}: " + ("role cleared" if a.clear else f"role {a.kind}"))


def cmd_audition(a):
    """Every candidate clip per kind on one page, short MP3s beside it (artifacts serve mp3, not m4a), the role picks marked."""
    import html as h, subprocess, audio
    lib, cat = audio.library_dir(), audio.catalog()["sfx"]
    clips = [(k, e) for k, e in cat.items() if audio.candidate_kinds(e) or e.get("role")]
    kinds = a.kinds or sorted({kd for _, e in clips for kd in audio.candidate_kinds(e) + ([e["role"]] if e.get("role") else [])})
    out = Path(a.out).expanduser() if a.out else lib / "audition"
    (out / "a").mkdir(parents=True, exist_ok=True)
    sections, n = [], 0
    for kind in kinds:
        group = [(k, e) for k, e in clips if kind in audio.candidate_kinds(e) or e.get("role") == kind]
        # earshot's order first, then the rest by score
        rk = lambda e: audio.earshot_for(e, kind)
        group.sort(key=lambda x: (rk(x[1]).get("rank") is None, rk(x[1]).get("rank") or 0, -(rk(x[1]).get("z") or -99)))
        cards = []
        for k, e in group:
            dest = out / "a" / f"{k}.mp3"
            if not dest.exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(lib / e["file"]), "-c:a", "libmp3lame", "-b:a", "128k", str(dest)], check=True)
            es = rk(e)
            badges = ("<span class='badge b-role'>in use</span>" if e.get("role") == kind else "") + \
                     (f"<span class='badge b-top'>earshot #{es['rank'] + 1}</span>" if es.get("rank") is not None else "")
            heard = f"earshot: {es.get('verdict', '?')}, z {es.get('z')}; sounds most like {es.get('sounds_most_like')}" if es else "not scored"
            cards.append(f"<div class='c{' role' if e.get('role') == kind else ''}'><div>{badges}</div>"
                         f"<div class='t'>{h.escape(e.get('title') or k)}</div><div class='k'>{h.escape(k)}</div>"
                         f"<audio controls preload='none' src='a/{h.escape(k)}.mp3'></audio>"
                         f"<div class='m'>{h.escape(e.get('licence_name') or e.get('licence', ''))} · {h.escape(e.get('creator') or '')}"
                         f" · {e.get('duration_s') or '?'} s</div><div class='m'>{h.escape(heard)}</div></div>")
            n += 1
        q = next((rk(e).get("query") for _, e in group if rk(e).get("query")), "")
        sections.append(f"<section><h2>{h.escape(kind)}</h2><p class='q'>{h.escape(('Searched for: ' + q) if q else '')}</p>"
                        f"<div class='grid'>{''.join(cards)}</div></section>")
    page = (SKILL / "assets" / "templates" / "audition.html").read_text()
    page = page.replace("{{TITLE}}", "Sound audition").replace("{{SECTIONS}}", "\n".join(sections))
    page = page.replace("{{LEDE}}", "Every candidate per kind, earshot's order first. Clips marked “in use” are the ones mix plays now. "
                        "Listen at a normal level; pick by ear, not by score.")
    page = page.replace("{{FOOT}}", "Licences are recorded per clip in the library catalog. CC BY clips need a credit line in the video "
                        "description (longform.py credits).")
    (out / "index.html").write_text(page)
    print(f"audition -> {out}/index.html + a/ ({n} clips). Publish index.html as a private artifact with every a/*.mp3 under its own name.")


def cmd_mix(a):
    import subprocess, verify
    film = film_dir(a.film)
    if not (film / "sound.py").exists():
        raise SystemExit(f"no sound.py in {film}")
    subprocess.run([sys.executable, str(film / "sound.py")], check=True, cwd=film)
    loud = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(film / "out" / "mix.wav"), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    tail = loud[loud.rfind("Summary:"):]
    print("mix:", " ".join(tail.split("I:")[1].split("LUFS")[0].split()), "LUFS,", "true peak", tail.split("Peak:")[1].split("dBFS")[0].strip(), "dBFS")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("config"); p.set_defaults(fn=cmd_config)
    p = sp.add_parser("new"); p.add_argument("slug"); p.add_argument("--format", default="4x5", choices=["4x5", "9x16", "16x9"])
    p.add_argument("--bpm", type=float, default=120); p.add_argument("--bars", type=int, default=16); p.add_argument("--title"); p.set_defaults(fn=cmd_new)
    p = sp.add_parser("stills"); p.add_argument("film"); p.add_argument("times", nargs="*"); p.add_argument("--bars", action="store_true")
    p.add_argument("--out"); p.add_argument("--cols", type=int, default=6); p.set_defaults(fn=cmd_stills)
    p = sp.add_parser("sheet"); p.add_argument("dir"); p.add_argument("--out"); p.add_argument("--cols", type=int, default=6); p.set_defaults(fn=cmd_sheet)
    p = sp.add_parser("draft"); p.add_argument("film"); p.set_defaults(fn=cmd_draft)
    p = sp.add_parser("final"); p.add_argument("film"); p.add_argument("--sub", type=int, default=4); p.set_defaults(fn=cmd_final)
    p = sp.add_parser("verify"); p.add_argument("target"); p.set_defaults(fn=cmd_verify)
    p = sp.add_parser("blindpack"); p.add_argument("film"); p.add_argument("--redo", action="store_true", help="rebuild the latest round (no reader has seen it)")
    p.set_defaults(fn=cmd_blindpack)
    p = sp.add_parser("serve"); p.add_argument("film"); p.add_argument("--port", type=int, default=4173); p.add_argument("--launch", action="store_true"); p.set_defaults(fn=cmd_serve)
    p = sp.add_parser("notes"); p.add_argument("film"); p.add_argument("--all", action="store_true"); p.add_argument("--resolve", type=int)
    p.add_argument("--reply"); p.set_defaults(fn=cmd_notes)
    p = sp.add_parser("search"); p.add_argument("kind", choices=["music", "sfx"]); p.add_argument("query"); p.set_defaults(fn=cmd_search)
    p = sp.add_parser("fetch"); p.add_argument("kind", choices=["music", "sfx", "kenney"]); p.add_argument("ids", nargs="*"); p.set_defaults(fn=cmd_fetch)
    p = sp.add_parser("measure"); p.add_argument("track"); p.set_defaults(fn=cmd_measure)
    p = sp.add_parser("library"); p.set_defaults(fn=cmd_library)
    p = sp.add_parser("import-sfx"); p.add_argument("dir"); p.add_argument("--roles", type=int, default=0,
                   help="give the role to earshot's top N per kind now (provisional; confirm by ear)"); p.set_defaults(fn=cmd_import_sfx)
    p = sp.add_parser("role"); p.add_argument("id"); p.add_argument("kind", nargs="?"); p.add_argument("--clear", action="store_true")
    p.set_defaults(fn=cmd_role)
    p = sp.add_parser("audition"); p.add_argument("kinds", nargs="*"); p.add_argument("--out"); p.set_defaults(fn=cmd_audition)
    p = sp.add_parser("mix"); p.add_argument("film"); p.set_defaults(fn=cmd_mix)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
