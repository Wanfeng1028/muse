#!/usr/bin/env python3
"""Run a storyboard with Playwright: discover selectors, rehearse, or record a take with an event log.

USAGE
  record.py STORYBOARD.yaml --discover               # dump visible interactive elements before each step (no video)
  record.py STORYBOARD.yaml --rehearse               # run every step, fail loudly, no video
  record.py STORYBOARD.yaml --slug NAME [--root video-out]   # real take into video-out/NAME/v<N>/
  record.py STORYBOARD.yaml --out DIR                # real take into an explicit, empty DIR

Options: --headed, --timeout MS (default 10000), --no-flash
  --profile NAME|PATH   run in a persistent browser profile (signed-in user; see browser_profile.py)
  --channel chrome|msedge|chromium   browser build for --profile (default: installed Chrome)
Step actions ('do' is one string or a list): see references/storyboard.md
  goto PATH|URL   click SEL   hover SEL   check SEL   type SEL | TEXT   fill SEL | TEXT
  press KEY   select SEL | VALUE   scroll PX|SEL   wait MS   expect SEL   expect_text SEL | TEXT   wait_url GLOB
Outputs of a take: raw.webm events.json console.json net.har trace.zip meta.json storyboard.yaml
Exit codes: 0 ok, 1 bad input, 2 a step failed, 3 no usable video produced
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import shutil
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from common import (DEFAULT_VIEWPORT, die, load_storyboard, next_run_dir, probe_summary,  # noqa: E402
                    run_paths, save_json, slugify)

ARITY = {"goto": 1, "click": 1, "hover": 1, "check": 1, "type": 2, "fill": 2, "press": 1, "select": 2,
         "scroll": 1, "wait": 1, "expect": 1, "expect_text": 2, "wait_url": 1}
SECRET_FIELDS = ("password", "pass", "secret", "token", "otp", "cvv", "card")

CURSOR_JS = r"""
(() => {
  if (window.__wvCursor) return; window.__wvCursor = true;
  const css = `#__wv_cur{position:fixed;z-index:2147483647;pointer-events:none;width:24px;height:24px;left:0;top:0;
     display:none;transform:translate(-3px,-2px)}
   .__wv_rip{position:fixed;z-index:2147483646;pointer-events:none;width:16px;height:16px;border-radius:50%;
     border:3px solid #ff3b30;background:rgba(255,59,48,.25);transform:translate(-50%,-50%) scale(1);
     animation:__wv_rip .6s ease-out forwards}
   @keyframes __wv_rip{to{transform:translate(-50%,-50%) scale(4.5);opacity:0}}`;
  const mk = () => {
    const st = document.createElement('style'); st.textContent = css; document.documentElement.appendChild(st);
    const c = document.createElement('div'); c.id = '__wv_cur';
    c.innerHTML = '<svg width="24" height="24" viewBox="0 0 22 22"><path d="M3 2 L3 17 L7 13 L10 20 L13 19 L10 12 L16 12 Z" fill="#111" stroke="#fff" stroke-width="1.5"/></svg>';
    document.documentElement.appendChild(c);
    addEventListener('mousemove', e => { c.style.display='block'; c.style.left=e.clientX+'px'; c.style.top=e.clientY+'px'; }, true);
    addEventListener('mousedown', e => { const r = document.createElement('div'); r.className='__wv_rip';
      r.style.left=e.clientX+'px'; r.style.top=e.clientY+'px'; document.documentElement.appendChild(r);
      setTimeout(() => r.remove(), 700); }, true);
  };
  document.readyState === 'loading' ? addEventListener('DOMContentLoaded', mk) : mk();
})();
"""

DISCOVER_JS = r"""
() => {
  const q = 'a,button,input,select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem],[role=checkbox],[role=option],[contenteditable=true],[data-testid]';
  const out = [];
  for (const el of document.querySelectorAll(q)) {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.width < 2 || r.height < 2 || cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (el.closest('#__wv_cur')) continue;
    const text = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    const o = {tag: el.tagName.toLowerCase(), type: el.getAttribute('type'), id: el.id || null,
      name: el.getAttribute('name'), testid: el.getAttribute('data-testid'), placeholder: el.getAttribute('placeholder'),
      aria: el.getAttribute('aria-label'), role: el.getAttribute('role'), text,
      in_view: r.top >= 0 && r.bottom <= innerHeight};
    if (el.tagName === 'SELECT') o.options = [...el.options].slice(0, 10).map(x => x.value + '=' + x.text.trim());
    o.selector = o.testid ? `[data-testid="${o.testid}"]` : o.id ? `#${CSS.escape(o.id)}`
      : o.name ? `${o.tag}[name="${o.name}"]` : o.aria ? `[aria-label="${o.aria}"]`
      : (text && ['button','a','summary'].includes(o.tag)) ? `${o.tag}:has-text("${text.replace(/"/g, '\\"')}")`
      : o.placeholder ? `[placeholder="${o.placeholder}"]` : null;
    out.push(o);
  }
  return out;
}
"""


class StepError(Exception):
    def __init__(self, msg, elements=None):
        super().__init__(msg)
        self.elements = elements or []


def parse_action(s: str) -> tuple[str, list[str]]:
    s = str(s).strip()
    verb, _, rest = s.partition(" ")
    verb = verb.lower()
    if verb not in ARITY:
        raise ValueError(f"unknown action '{verb}' in '{s}'. Known: {', '.join(sorted(ARITY))}")
    args = [a.strip() for a in rest.split(" | ", 1)] if rest.strip() else []
    if not args and ARITY[verb]:
        raise ValueError(f"'{s}' has no arguments. If the selector starts with '#', quote the whole line in YAML "
                         f"('#' starts a comment): - '{verb} #id'")
    if len(args) != ARITY[verb]:
        sep = " (use 'SEL | VALUE')" if ARITY[verb] == 2 else ""
        raise ValueError(f"'{verb}' needs {ARITY[verb]} argument(s){sep}: '{s}'")
    return verb, args


def step_actions(step: dict) -> list[tuple[str, list[str]]]:
    do = step["do"]
    return [parse_action(x) for x in (do if isinstance(do, list) else [do])]


def is_secret(selector: str, input_type: str | None) -> bool:
    return input_type == "password" or any(k in selector.lower() for k in SECRET_FIELDS)


class Runner:
    def __init__(self, page, base_url: str, viewport, mode: str, timeout: int):
        self.page, self.base, self.mode, self.timeout = page, base_url, mode, timeout
        self.w, self.h = viewport
        self.events: list[dict] = []
        self.console: list[dict] = []
        self.discovered: list[dict] = []
        self.secret_selectors: set[str] = set()     # selectors typed into as secrets (values never logged)
        self.t0 = time.monotonic()
        self.mouse = (self.w / 2, self.h / 2)
        self.hidden = False
        self.live = mode == "record"

    # ---- clock and log ----
    def now(self) -> float:
        return round(time.monotonic() - self.t0, 3)

    def ev(self, kind: str, **kw):
        e = {"t": self.now(), "kind": kind, **kw}
        self.events.append(e)
        return e

    def attach_listeners(self):
        p = self.page

        def on_console(m):
            self.console.append({"t": self.now(), "type": m.type, "text": m.text})
            if m.type == "error":
                self.ev("error", source="console", text=m.text[:500])
        p.on("console", on_console)
        p.on("pageerror", lambda e: (self.console.append({"t": self.now(), "type": "pageerror", "text": str(e)}),
                                     self.ev("error", source="pageerror", text=str(e)[:500])))
        p.on("response", lambda r: r.status >= 400 and self.ev(
            "error", source="http", status=r.status, method=r.request.method, url=r.url[:300]))
        p.on("requestfailed", lambda r: "ERR_ABORTED" not in (r.failure or "") and self.ev(
            "error", source="network", method=r.method, url=r.url[:300], text=r.failure))

    # ---- helpers ----
    def visible_elements(self):
        try:
            return self.page.evaluate(DISCOVER_JS)
        except Exception as e:
            print(f"warning: element dump failed: {str(e).splitlines()[0]}", file=sys.stderr)
            return []

    def nav(self):
        last = next((e for e in reversed(self.events) if e["kind"] == "nav"), None)
        if not last or last["url"] != self.page.url or self.now() - last["t"] > 1.0:
            self.ev("nav", url=self.page.url)

    def wait(self, ms: int):
        self.page.wait_for_timeout(ms if self.live else min(ms, 150))

    def locate(self, sel: str, label: str):
        loc = self.page.locator(sel)
        try:
            loc.first.wait_for(state="visible", timeout=self.timeout)
        except Exception:
            raise StepError(f"{label}: '{sel}' not visible within {self.timeout} ms", self.visible_elements())
        n = loc.count()
        if n > 1:
            raise StepError(f"{label}: '{sel}' matches {n} elements; make the selector specific",
                            self.visible_elements())
        return loc

    def point(self, loc, sel: str, label: str):
        loc.scroll_into_view_if_needed(timeout=self.timeout)
        box = loc.bounding_box()
        if not box:
            raise StepError(f"{label}: '{sel}' has no box", self.visible_elements())
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        if not (0 <= x < self.w and 0 <= y < self.h):
            raise StepError(f"{label}: '{sel}' centre ({x:.0f},{y:.0f}) is outside the viewport")
        hit = loc.evaluate("(el, [x, y]) => { const h = document.elementFromPoint(x, y);"
                           " return (!h || el === h || el.contains(h) || h.contains(el)) ? null"
                           " : h.outerHTML.slice(0, 160); }", [x, y])
        if hit:
            raise StepError(f"{label}: '{sel}' is covered by another element: {hit}")
        return x, y, {k: round(v, 1) for k, v in box.items()}

    def glide(self, x: float, y: float):
        if self.live and not self.hidden:
            dist = math.dist(self.mouse, (x, y))
            self.page.mouse.move(x, y, steps=max(12, min(45, int(dist / 12))))
        else:
            self.page.mouse.move(x, y, steps=2)
        self.mouse = (x, y)

    def restore_cursor(self):
        x, y = self.mouse
        self.page.mouse.move(x + 1, y)
        self.page.mouse.move(x, y)

    def after_maybe_nav(self, before_url: str):
        self.page.wait_for_timeout(150)
        if self.page.url != before_url:
            try:
                self.page.wait_for_load_state("load", timeout=self.timeout)
            except Exception:
                pass
            self.nav()
            self.restore_cursor()

    # ---- actions ----
    def act(self, verb: str, args: list[str], label: str):
        p = self.page
        if verb == "goto":
            url = urllib.parse.urljoin(self.base, args[0])
            p.goto(url, wait_until="load", timeout=self.timeout * 3)
            self.nav()
            self.restore_cursor()
        elif verb in ("click", "check", "hover"):
            loc = self.locate(args[0], label)
            x, y, box = self.point(loc, args[0], label)
            self.glide(x, y)
            if verb == "hover":
                self.ev("hover", x=x, y=y, w=self.w, h=self.h, target=args[0], bbox=box)
                return
            self.wait(250)
            before = p.url
            self.ev("click", x=x, y=y, w=self.w, h=self.h, target=args[0], bbox=box)
            p.mouse.click(x, y)
            self.after_maybe_nav(before)
        elif verb in ("type", "fill"):
            loc = self.locate(args[0], label)
            itype = loc.evaluate("el => el.getAttribute('type')")
            shown = "•" * min(len(args[1]), 8) if is_secret(args[0], itype) else args[1]
            if is_secret(args[0], itype):
                self.secret_selectors.add(args[0])
            if verb == "fill" or self.hidden or not self.live:
                loc.fill(args[1])
                self.ev("fill", target=args[0], text=shown)
                return
            x, y, box = self.point(loc, args[0], label)
            self.glide(x, y)
            self.wait(200)
            p.mouse.click(x, y)
            t_start = self.now()
            loc.press_sequentially(args[1], delay=55)
            self.ev("type", x=x, y=y, w=self.w, h=self.h, target=args[0], bbox=box, text=shown, t_start=t_start)
        elif verb == "press":
            before = p.url
            self.ev("press", key=args[0])
            p.keyboard.press(args[0])
            self.after_maybe_nav(before)
        elif verb == "select":
            loc = self.locate(args[0], label)
            x, y, box = self.point(loc, args[0], label)
            self.glide(x, y)
            self.wait(200)
            try:
                loc.select_option(value=args[1], timeout=self.timeout)
            except Exception:
                loc.select_option(label=args[1], timeout=self.timeout)
            self.ev("select", x=x, y=y, w=self.w, h=self.h, target=args[0], bbox=box, value=args[1],
                    note="native dropdown list is not visible in the recording")
        elif verb == "scroll":
            if args[0].lstrip("-").isdigit():
                dy = int(args[0])
            else:
                loc = self.locate(args[0], label)
                box = loc.bounding_box()
                dy = int(box["y"] - self.h / 3) if box else 0
            stepsz = 80 if dy > 0 else -80
            for _ in range(abs(dy) // 80):
                p.mouse.wheel(0, stepsz)
                p.wait_for_timeout(25 if self.live else 0)
            p.mouse.wheel(0, dy % 80 if dy > 0 else -(abs(dy) % 80))
            self.ev("scroll", dy=dy)
        elif verb == "wait":
            self.wait(int(args[0]))
        elif verb in ("expect", "expect_text"):
            loc = self.locate(args[0], label)
            if verb == "expect_text":
                from playwright.sync_api import expect
                try:
                    expect(loc).to_contain_text(args[1], timeout=self.timeout)
                except AssertionError:
                    raise StepError(f"{label}: '{args[0]}' does not contain '{args[1]}'", self.visible_elements())
            box = loc.bounding_box()
            self.ev("expect", target=args[0], bbox=box and {k: round(v, 1) for k, v in box.items()})
        elif verb == "wait_url":
            p.wait_for_url(args[0], timeout=self.timeout)
            self.nav()

    def flash(self):
        """Sync flash: dark frames first, then magenta. calibrate.py finds the switch in the video."""
        self.page.set_content('<html><body style="margin:0;background:#101010"></body></html>')
        self.page.wait_for_timeout(700)
        t_before = self.now()
        self.page.evaluate("() => new Promise(r => { document.body.style.background = '#ff00ff';"
                           " requestAnimationFrame(() => requestAnimationFrame(r)); })")
        t_after = self.now()
        self.ev("flash", t_before=t_before)["t"] = round((t_before + t_after) / 2, 3)
        self.page.wait_for_timeout(500)
        self.page.set_content('<html><body style="margin:0;background:#ffffff"></body></html>')
        self.ev("flash_end")

    def run_steps(self, steps: list[dict]) -> int | None:
        """Return the index of the failing step, or None."""
        for i, step in enumerate(steps):
            self.hidden = bool(step.get("hidden"))
            label = f"step {i + 1} ({step.get('caption') or 'hidden'})"
            if self.mode == "discover":
                self.discovered.append({"step": i + 1, "url": self.page.url, "elements": self.visible_elements()})
            self.ev("step", i=i, caption=step.get("caption", ""), hidden=self.hidden, bug=bool(step.get("bug")))
            try:
                for verb, args in step_actions(step):
                    self.act(verb, args, label)
                self.wait(int(step.get("wait", 0 if self.hidden else 700)))
                if step.get("bug"):
                    box = None
                    if step.get("bug_target"):
                        try:
                            box = self.page.locator(step["bug_target"]).first.bounding_box(timeout=2000)
                        except Exception:
                            box = None
                    if not box:
                        last = next((e for e in reversed(self.events)
                                     if e["kind"] in ("click", "type", "select") and e.get("bbox")), None)
                        box = last and last["bbox"]
                    errs = sum(1 for e in self.events if e["kind"] == "error")
                    self.ev("bug", i=i, bbox=box and {k: round(v, 1) for k, v in box.items()}, errors_so_far=errs)
            except StepError as e:
                self.ev("fail", i=i, reason=str(e))
                print(f"FAIL {label}: {e}", file=sys.stderr)
                if e.elements:
                    print("Visible interactive elements (use these selectors):", file=sys.stderr)
                    for el in e.elements[:40]:
                        print(f"  {el.get('selector') or '-':45} {el['tag']:8} {el.get('text') or el.get('placeholder') or ''}",
                              file=sys.stderr)
                return i
            except Exception as e:  # Playwright timeouts and the like
                self.ev("fail", i=i, reason=f"{type(e).__name__}: {e}")
                print(f"FAIL {label}: {type(e).__name__}: {str(e).splitlines()[0]}", file=sys.stderr)
                return i
            self.ev("step_end", i=i)
            if self.mode != "record":
                print(f"ok   {label}")
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("storyboard", type=pathlib.Path)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--discover", action="store_true")
    g.add_argument("--rehearse", action="store_true")
    ap.add_argument("--slug")
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path("video-out"))
    ap.add_argument("--out", type=pathlib.Path)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--timeout", type=int, default=10000)
    ap.add_argument("--no-flash", action="store_true")
    ap.add_argument("--profile", help="persistent profile name or user-data dir (overrides storyboard 'profile')")
    ap.add_argument("--channel", choices=("chrome", "chrome-beta", "msedge", "chromium"),
                    help="browser build for --profile (overrides storyboard 'channel')")
    a = ap.parse_args()

    sb = load_storyboard(a.storyboard)
    try:
        for s in sb["steps"]:
            step_actions(s)
    except ValueError as e:
        die(str(e))
    mode = "discover" if a.discover else "rehearse" if a.rehearse else "record"
    vw, vh = sb.get("viewport", list(DEFAULT_VIEWPORT))
    sb_dir = a.storyboard.resolve().parent
    storage = sb.get("storage_state")
    storage = str((sb_dir / storage).resolve()) if storage else None
    profile = a.profile or sb.get("profile")
    if not a.profile and profile and ("/" in profile or "\\" in profile) and not os.path.isabs(os.path.expanduser(profile)):
        profile = str((sb_dir / profile).resolve())          # storyboard paths are relative to the storyboard
    channel = a.channel or sb.get("channel")
    if profile and storage:
        die("use either a profile or storage_state, not both")

    run = None
    if mode == "record":
        if a.out:
            run = a.out
            if run.exists() and any(run.iterdir()):
                die(f"{run} is not empty; never overwrite a previous run (Hard rule 9)")
            run.mkdir(parents=True, exist_ok=True)
        else:
            run = next_run_dir(a.root, a.slug or slugify(sb.get("title", "video")))
        shutil.copy(a.storyboard, run / "storyboard.yaml")
        paths = run_paths(run)

    from importlib.metadata import version
    from playwright.sync_api import sync_playwright
    pw_version = version("playwright")
    failed = None
    started = dt.datetime.now().isoformat(timespec="seconds")
    with sync_playwright() as pw:
        ctx_kw = dict(viewport={"width": vw, "height": vh})
        if mode == "record":
            ctx_kw.update(record_video_dir=str(run / "_video"), record_video_size={"width": vw, "height": vh},
                          record_har_path=str(paths["har"]),
                          record_har_content="embed" if sb["mode"] == "bug-report" else "omit")
        if profile:
            import browser_profile
            browser = None
            ctx = browser_profile.open_context(pw, profile, channel, headless=not a.headed, **ctx_kw)
        else:
            browser = pw.chromium.launch(headless=not a.headed)
            ctx = browser.new_context(storage_state=storage, **ctx_kw)
        if mode == "record":
            ctx.add_init_script(CURSOR_JS)
            ctx.tracing.start(screenshots=True, snapshots=True, sources=False)
        restored = list(ctx.pages)  # a persistent profile opens with a blank or restored tab
        page = ctx.new_page()
        for old in restored:
            old.close()
        r = Runner(page, sb["url"], (vw, vh), mode, a.timeout)
        r.attach_listeners()
        video_src = None
        browser_version = browser.version if browser else page.evaluate("navigator.userAgent")
        try:
            if mode == "record" and not a.no_flash:
                r.flash()
            page.mouse.move(vw / 2, vh / 2)
            failed = r.run_steps(sb["steps"])
            r.ev("end")
        finally:
            if mode == "record":
                try:
                    ctx.tracing.stop(path=str(paths["trace"]))
                except Exception as e:
                    print(f"warning: trace not saved: {e}", file=sys.stderr)
                video_src = page.video.path() if page.video else None
            ctx.close()  # flushes video and HAR (Hard rule 5)
            if browser:
                browser.close()

    errors = [e for e in r.events if e["kind"] == "error"]
    if mode == "discover":
        out = pathlib.Path("discover.json")
        out.write_text(json.dumps(r.discovered, indent=1, ensure_ascii=False))
        for d in r.discovered:
            print(f"\n== before step {d['step']}  {d['url']}")
            for el in d["elements"]:
                extra = f" options={el['options']}" if el.get("options") else ""
                print(f"  {el.get('selector') or '-':45} {el['tag']:8} {(el.get('text') or el.get('placeholder') or '')[:40]}{extra}")
        print(f"\nwrote {out.resolve()}")
    if mode in ("discover", "rehearse"):
        if errors:
            print(f"\n{len(errors)} error event(s) during the run:")
            for e in errors[:15]:
                print(f"  {e['t']:7.2f}s {e['source']:9} {e.get('status', '')} {e.get('text') or e.get('url')}")
        if sb["mode"] == "bug-report":
            bug = next((e for e in r.events if e["kind"] == "bug"), None)
            print("bug step reached" + (f"; {bug['errors_so_far']} error(s) logged by then" if bug else ": NO"))
        sys.exit(2 if failed is not None else 0)

    # ---- record: verify the raw video, calibrate, write logs ----
    if not video_src or not pathlib.Path(video_src).exists():
        print("error: no video file produced (Hard rule 5)", file=sys.stderr)
        sys.exit(3)
    shutil.move(video_src, paths["raw"])
    shutil.rmtree(run / "_video", ignore_errors=True)
    probe = probe_summary(paths["raw"])
    if probe["duration"] <= 0.5 or probe["size_bytes"] == 0:
        print(f"error: raw video unusable: {probe}", file=sys.stderr)
        sys.exit(3)
    save_json(paths["events"], {"version": 1, "mode": sb["mode"], "viewport": [vw, vh], "video_offset": 0.0,
                                "offset_method": "pending", "secret_selectors": sorted(r.secret_selectors),
                                "events": r.events})
    save_json(paths["console"], r.console)
    import calibrate
    off, method = calibrate.measure(run)
    calibrate.write(run, off, method)
    save_json(paths["meta"], {"status": "aborted" if failed is not None else "ok",
                              "failed_step": None if failed is None else failed + 1,
                              "started_at": started, "url": sb["url"], "playwright": pw_version,
                              "storyboard_dir": str(sb_dir),
                              "browser": browser_version, "storage_state": storage,
                              "profile": pathlib.Path(profile).name if profile else None, "raw_probe": probe,
                              "video_offset": off, "offset_method": method, "errors": len(errors)})
    print(f"run dir: {run}")
    print(f"raw.webm {probe['duration']:.2f}s {probe['width']}x{probe['height']} ~{probe['fps']} fps; "
          f"offset {off}s ({method}); {len(r.events)} events, {len(errors)} errors")
    if failed is not None:
        print(f"take aborted at step {failed + 1}; artifacts kept for debugging", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
