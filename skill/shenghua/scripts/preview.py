#!/usr/bin/env python3
"""Serve a filled work directory with a browser preview shell around the composition.

  preview.py <work-dir> [--port N]   serve until Ctrl+C (run detached on a timed shell)
  preview.py <work-dir> --check      headless self-test: renderAt, word click-seek, screenshots

The shell (_preview.html, regenerated every run) embeds index.html in an iframe and drives it
through window.renderAt(t) from a requestAnimationFrame loop that lives only in the shell —
the composition and the render path are untouched (invariant 1). Transport: play/pause, scrub,
±1 frame steps, and a word panel where clicking a word seeks the playhead to it. voice.wav, when
present, plays in the shell for monitoring only; the real mix is still made by mix-encode.sh.

--check writes _preview_check.js, runs it with node against the repo's playwright-core, saves
_preview_check_1.png / _preview_check_2.png at two seeked times, and exits 0 only if renderAt
answers, a word click seeks exactly, and the two screenshots differ.
"""

import argparse
import functools
import json
import re
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SHELL_NAME = "_preview.html"
CHECK_NAME = "_preview_check.js"
DEFAULT_PORT = 8377
PORT_TRIES = 20

# @TOKENS@, not {{placeholders}}: fill_template.py owns those (invariant 8)
SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><title>preview</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; height:100vh; display:flex; flex-direction:column; overflow:hidden;
         background:#141416; color:#e8e8ea; font:13px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace; }
  #bar { display:flex; align-items:center; gap:8px; padding:8px 12px;
         background:#1d1d20; border-bottom:1px solid #2c2c30; }
  button { background:#2c2c30; color:#e8e8ea; border:1px solid #3a3a40; border-radius:4px;
           padding:4px 12px; font:inherit; cursor:pointer; }
  button:hover { background:#3a3a40; }
  #scrub { flex:1; accent-color:#e8e8ea; }
  #time { min-width:190px; text-align:right; color:#9a9aa2; white-space:pre; }
  #note { padding:4px 12px; background:#3a2b1d; color:#e8c98a; }
  #main { flex:1; display:flex; min-height:0; }
  #stagebox { flex:1; display:flex; align-items:center; justify-content:center; overflow:hidden; }
  #scale { position:relative; }
  #stage { position:absolute; left:0; top:0; border:0; transform-origin:0 0; background:#000; }
  #words { width:250px; margin:0; padding:8px; list-style:none; overflow-y:auto;
           border-left:1px solid #2c2c30; }
  #words li { padding:2px 6px; border-radius:3px; cursor:pointer; color:#9a9aa2; }
  #words li:hover { background:#2c2c30; color:#e8e8ea; }
  #words li.now { background:#e8e8ea; color:#141416; }
  #words li.empty { color:#6a6a72; cursor:default; }
  #words li.empty:hover { background:none; }
</style></head>
<body>
<div id="bar">
  <button id="back" title="previous frame (left arrow)">&#9003;</button>
  <button id="play" title="space">play</button>
  <button id="fwd" title="next frame (right arrow)">&#10140;</button>
  <input id="scrub" type="range" min="0" max="@DURATION@" step="@FRAME@" value="0">
  <span id="time"></span>
</div>
<div id="note" hidden></div>
<div id="main">
  <div id="stagebox"><div id="scale"><iframe id="stage" src="index.html"
      width="@WIDTH@" height="@HEIGHT@"></iframe></div></div>
  <ul id="words"></ul>
</div>
<script>
const W = @WIDTH@, H = @HEIGHT@, D = @DURATION@, FRAME = 1/30;
const WORDS = @WORDS_JSON@;
const HAS_VOICE = @HAS_VOICE@;

const frameEl = document.getElementById('stage');
const scrub = document.getElementById('scrub');
const timeEl = document.getElementById('time');
const playBtn = document.getElementById('play');
const wordsEl = document.getElementById('words');
const noteEl = document.getElementById('note');
const scaleEl = document.getElementById('scale');
const boxEl = document.getElementById('stagebox');

let t = 0, playing = false, lastStamp = null, activeWord = -1, mediaWarned = false;

// voice.wav here is preview monitoring only; mix-encode.sh builds the real mix
const audio = HAS_VOICE ? new Audio('voice.wav') : null;
if (audio) audio.preload = 'auto';

function composition(){
  const w = frameEl.contentWindow;
  return w && typeof w.renderAt === 'function' ? w : null;
}
function note(msg){ noteEl.textContent = msg || ''; noteEl.hidden = !msg; }
function renderCurrent(){
  const c = composition();
  if (!c) return Promise.resolve();
  // renderAt's promise rejects on a clip/presenter frame that was never extracted
  return Promise.resolve(c.renderAt(t)).catch(err => {
    if (!mediaWarned){ mediaWarned = true; note(String(err && err.message || err)); }
  });
}
function paint(){
  if (document.activeElement !== scrub) scrub.value = t;
  timeEl.textContent = t.toFixed(2) + 's / ' + D.toFixed(2) + 's · f' + Math.round(t*30);
  highlight();
}
function seek(v){
  t = Math.max(0, Math.min(D, v));
  if (audio && Math.abs(audio.currentTime - t) > 0.12){
    try { audio.currentTime = Math.min(t, audio.duration || t); } catch(e){}
  }
  paint();
  return renderCurrent();
}
function pause(){ playing = false; lastStamp = null; playBtn.textContent = 'play'; if (audio) audio.pause(); }
function play(){
  if (t >= D) t = 0;
  playing = true; playBtn.textContent = 'pause';
  if (audio && t < (audio.duration || Infinity)){
    try { audio.currentTime = t; } catch(e){}
    audio.play().catch(() => {});
  }
  requestAnimationFrame(tick);
}
function tick(stamp){
  if (!playing) return;
  if (lastStamp != null) t = Math.min(D, t + (stamp - lastStamp)/1000);
  lastStamp = stamp;
  if (audio && !audio.paused && Math.abs(audio.currentTime - t) > 0.25){
    try { audio.currentTime = Math.min(t, audio.duration || t); } catch(e){}
  }
  paint();
  renderCurrent();
  if (t >= D){ pause(); return; }
  requestAnimationFrame(tick);
}

WORDS.forEach((w) => {
  const li = document.createElement('li');
  li.textContent = w.t;
  li.title = w.s.toFixed(2) + 's';
  li.addEventListener('click', () => { pause(); seek(w.s); });
  wordsEl.appendChild(li);
});
if (!WORDS.length){
  const li = document.createElement('li');
  li.className = 'empty';
  li.textContent = 'no words yet — run build_captions.py after transcribe.py';
  wordsEl.appendChild(li);
}
function highlight(){
  let idx = -1;
  for (let i = 0; i < WORDS.length; i++){
    // a zero-length word still lights up: its slot ends where the next word starts
    const end = Math.max(WORDS[i].e, i + 1 < WORDS.length ? WORDS[i + 1].s : WORDS[i].e);
    if (t < WORDS[i].s - 1e-6) break;
    if (t < end){ idx = i; break; }
  }
  if (idx === activeWord) return;
  const kids = wordsEl.children;
  if (activeWord >= 0 && kids[activeWord]) kids[activeWord].classList.remove('now');
  activeWord = idx;
  if (idx >= 0){ kids[idx].classList.add('now'); kids[idx].scrollIntoView({ block: 'nearest' }); }
}

function fit(){
  const s = Math.min(boxEl.clientWidth / W, boxEl.clientHeight / H);
  scaleEl.style.width = (W*s).toFixed(1) + 'px';
  scaleEl.style.height = (H*s).toFixed(1) + 'px';
  frameEl.style.transform = 'scale(' + s + ')';
}
new ResizeObserver(fit).observe(boxEl);

playBtn.addEventListener('click', () => playing ? pause() : play());
document.getElementById('back').addEventListener('click', () => { pause(); seek(t - FRAME); });
document.getElementById('fwd').addEventListener('click', () => { pause(); seek(t + FRAME); });
scrub.addEventListener('input', () => seek(parseFloat(scrub.value)));
addEventListener('keydown', (e) => {
  if (e.code === 'Space'){ e.preventDefault(); playing ? pause() : play(); return; }
  if (e.target === scrub) return;
  if (e.key === 'ArrowLeft'){ pause(); seek(t - FRAME); }
  if (e.key === 'ArrowRight'){ pause(); seek(t + FRAME); }
});

// the iframe may still be loading; the first render waits for its load event
frameEl.addEventListener('load', () => { fit(); paint(); renderCurrent(); });
fit(); paint();

// programmatic handle for preview.py --check
window.pv = { words: WORDS, duration: () => D, time: () => t, play, pause,
              seek: v => { pause(); return seek(v); }, render: renderCurrent };
</script>
</body></html>
"""

CHECK_JS = """// Generated by preview.py --check; regenerated every run, safe to delete.
const fs = require('fs');
const { chromium } = require(@PLAYWRIGHT@);

const fail = (msg, next) => {
  console.error('FAIL ' + msg);
  console.error('Next: ' + next);
  process.exit(1);
};

(async () => {
  const [url, prefix] = process.argv.slice(2);
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1400, height: 950 } });
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(
    () => { const f = document.getElementById('stage');
            return f && f.contentWindow && typeof f.contentWindow.renderAt === 'function'; },
    null, { timeout: 20000 })
    .catch(() => fail('renderAt never appeared in the preview iframe',
                      'make sure ' + url + ' serves a filled index.html'));

  const total = await page.evaluate(() => window.pv.words.length);
  let t1;
  if (total > 0) {
    // a word with real duration: zero-length words never become the active one
    const i = await page.evaluate(() => {
      const ws = window.pv.words;
      const at = ws.findIndex((w, k) => k >= 4 && w.e - w.s > 0.02);
      return at >= 0 ? at : ws.findIndex(w => w.e - w.s > 0.02);
    });
    const r = await page.evaluate(async i => {
      document.querySelectorAll('#words li')[i].click();
      await window.pv.render();
      const lis = [...document.querySelectorAll('#words li')];
      return { t: window.pv.time(), want: window.pv.words[i].s,
               active: lis.findIndex(li => li.classList.contains('now')) };
    }, i);
    if (Math.abs(r.t - r.want) > 0.001)
      fail(`clicking word ${i} seeked to ${r.t.toFixed(3)}s, expected ${r.want.toFixed(3)}s`,
           'open the URL and click a word in the transcript panel');
    if (r.active !== i)
      fail(`word ${i} is not the highlighted word after clicking it (active=${r.active})`,
           'open the URL and check the transcript highlight while scrubbing');
    t1 = r.t;
  } else {
    t1 = await page.evaluate(async () => { await window.pv.seek(0.5); return window.pv.time(); });
    console.log('note: words.js has no words; tested plain seeking instead of a word click');
  }
  await page.screenshot({ path: prefix + '_1.png' });

  const t2 = await page.evaluate(async () => {
    await window.pv.seek(window.pv.duration() * 0.75);
    return window.pv.time();
  });
  await page.screenshot({ path: prefix + '_2.png' });

  const t3 = await page.evaluate(() => { window.pv.play(); return window.pv.time(); });
  await page.waitForTimeout(700);
  const t4 = await page.evaluate(() => { const v = window.pv.time(); window.pv.pause(); return v; });
  await browser.close();
  if (t4 - t3 < 0.3)
    fail(`playback advanced only ${(t4 - t3).toFixed(2)}s in 0.7s — the rAF loop is not driving renderAt`,
         'open the URL and press play; check the browser console');

  const b1 = fs.readFileSync(prefix + '_1.png');
  const b2 = fs.readFileSync(prefix + '_2.png');
  if (b1.equals(b2))
    fail(`screenshots at t=${t1.toFixed(2)}s and t=${t2.toFixed(2)}s are identical — renderAt is not responding`,
         'open the URL and scrub by hand; check the browser console');
  console.log(`PASS renderAt live · seeked ${t1.toFixed(2)}s and ${t2.toFixed(2)}s · screenshots differ · playback ${t3.toFixed(2)}s → ${t4.toFixed(2)}s`);
  console.log(`Next: look at ${prefix}_1.png and ${prefix}_2.png`);
})().catch(err => {
  console.error('FAIL ' + (err && err.message || err));
  console.error('Next: run preview.py without --check and inspect the browser console');
  process.exit(1);
});
"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def fail(problem, fix):
    print(problem, file=sys.stderr)
    print(f"Next: {fix}", file=sys.stderr)
    return 1


def load_work(work):
    """Validate the work dir and return (width, height, duration, words, has_voice)."""
    index = work / "index.html"
    if not index.is_file():
        return None, fail(f"No composition at {index}",
                          f"run fill_template.py {work} <duration> first")
    html = index.read_text(encoding="utf-8")
    match = re.search(r"const D = ([\d.]+)", html)
    if not match:
        return None, fail(f"{index} has no 'const D = …' — it is not a filled composition",
                          f"run fill_template.py {work} <duration>")
    duration = float(match.group(1))

    geometry = None
    render_json = work / "render.json"
    if render_json.is_file():
        try:
            meta = json.loads(render_json.read_text(encoding="utf-8"))
            geometry = int(meta["width"]), int(meta["height"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            geometry = None
    if geometry is None:
        match = re.search(r"const W = (\d+), H = (\d+)", html)
        if not match:
            return None, fail(f"Cannot read the stage size from {render_json} or {index}",
                              f"re-run fill_template.py {work} <duration>")
        geometry = int(match.group(1)), int(match.group(2))

    words_js = work / "words.js"
    if not words_js.is_file():
        return None, fail(f"No words.js in {work}",
                          f"run fill_template.py {work} <duration> (it writes the placeholder)")
    text = words_js.read_text(encoding="utf-8").strip()
    try:
        phrases = json.loads(text[len("window.PHRASES="):].rstrip(";"))
    except (json.JSONDecodeError, ValueError):
        return None, fail(f"{words_js} is not window.PHRASES JSON",
                          f"re-run build_captions.py {work}")
    words = sorted(({"t": w["t"], "s": w["s"], "e": w["e"]}
                    for phrase in phrases for w in phrase), key=lambda w: w["s"])
    return (*geometry, duration, words, (work / "voice.wav").is_file()), 0


def start_server(work, port):
    handler = functools.partial(QuietHandler, directory=str(work))
    for candidate in range(port, port + PORT_TRIES):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
            server.daemon_threads = True
            return server, candidate
        except OSError:
            continue
    return None, None


def write_shell(work, width, height, duration, words, has_voice):
    shell = (SHELL.replace("@WIDTH@", str(width)).replace("@HEIGHT@", str(height))
             .replace("@DURATION@", f"{duration:.4f}").replace("@FRAME@", f"{1/30:.6f}")
             .replace("@WORDS_JSON@", json.dumps(words))
             .replace("@HAS_VOICE@", "true" if has_voice else "false"))
    (work / SHELL_NAME).write_text(shell, encoding="utf-8")


def run_check(work, port):
    node = shutil.which("node")
    playwright = SCRIPTS_DIR / "node_modules" / "playwright-core"
    if node is None:
        return fail("node is not on PATH", "install node, or run the preview by hand without --check")
    if not playwright.is_dir():
        return fail(f"playwright-core is not installed at {playwright}",
                    f"bash {SCRIPTS_DIR / 'setup.sh'} <kit>")
    server, port = start_server(work, port)
    if server is None:
        return fail(f"Ports {port}–{port + PORT_TRIES - 1} are all in use", "pass --port <free port>")
    threading.Thread(target=server.serve_forever, daemon=True).start()

    check_js = (work / CHECK_NAME)
    check_js.write_text(CHECK_JS.replace("@PLAYWRIGHT@", json.dumps(str(playwright))), encoding="utf-8")
    url = f"http://localhost:{port}/{SHELL_NAME}"
    result = subprocess.run([node, str(check_js), url, str(work / "_preview_check")])
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("work", type=Path, help="filled work directory (index.html + words.js)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"first port to try (default {DEFAULT_PORT}; taken ports fall forward)")
    parser.add_argument("--check", action="store_true",
                        help="headless self-test: renderAt, word click-seek, two screenshots; exit 0/1")
    args = parser.parse_args()

    if not args.work.is_dir():
        return fail(f"No work directory at {args.work}",
                    f"run fill_template.py {args.work} <duration> first")
    loaded, status = load_work(args.work)
    if loaded is None:
        return status
    width, height, duration, words, has_voice = loaded
    write_shell(args.work, width, height, duration, words, has_voice)

    if args.check:
        return run_check(args.work, args.port)

    server, port = start_server(args.work, args.port)
    if server is None:
        return fail(f"Ports {args.port}–{args.port + PORT_TRIES - 1} are all in use",
                    "pass --port <free port>")
    url = f"http://localhost:{port}/{SHELL_NAME}"
    voice = "voice.wav" if has_voice else "no voice.wav"
    # flush: detached with nohup the log is block-buffered, and the agent polls that log
    print(f"{url} · {width}x{height} · {duration:.2f}s · {len(words)} words · {voice}", flush=True)
    print("Next: open the URL to review the edit; Ctrl+C to stop "
          "(on a timed shell run detached: nohup python3 "
          f"{Path(__file__).resolve()} {args.work} > {args.work}/preview.log 2>&1 &)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
