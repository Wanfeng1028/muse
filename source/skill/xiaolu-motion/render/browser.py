"""Headless Chrome session for the engine page (Playwright, async).

Uses the installed Google Chrome (channel="chrome") in headless mode: the Playwright 1.55
cache ships a mismatched browser build on this machine (same workaround as the original
renderer). Nothing is shown on screen.
"""
import sys

CHROME_ARGS = [
    "--enable-gpu", "--ignore-gpu-blocklist", "--use-angle=metal",
    "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
    "--force-color-profile=srgb", "--js-flags=--expose-gc --max-old-space-size=4096",
]


def page_config(resolved, tokens, faces, mode="overlay", overrides=None, layer=None):
    """the object handed to XM.boot(cfg); layer = 'behind' | 'front' | 'invert' | None (all)"""
    return {
        "canvas": resolved["canvas"], "fps": resolved["canvas"]["fps"], "mode": mode, "tokens": tokens,
        "camera": resolved.get("camera") or None, "layer": layer,
        "fonts": [{"key": f["key"], "family": f["family"], "weight": f["weight"], "style": f["style"], "url": f"/font/{f['key']}"} for f in faces],
        "shots": [{"id": s["id"], "component": s["component"], "t0": s["t0"], "t1": s["t1"], "params": s.get("params", {}), "z": s.get("z"),
                   "layer": s.get("layer", "front"), "depth": s.get("depth", 0.0)}
                  for s in resolved["shots"]],
        "transitions": [{"id": t["id"], "type": t["type"], "t0": t["t0"], "t1": t["t1"], "params": t.get("params", {}), "z": t.get("z")}
                        for t in resolved["transitions"]],
        "overrides": overrides or None,
    }


async def launch(p):
    return await p.chromium.launch(channel="chrome", headless=True, args=CHROME_ARGS)


async def open_engine(browser, sink, cfg, verbose=True):
    W, H = cfg["canvas"]["w"], cfg["canvas"]["h"]
    page = await browser.new_page(viewport={"width": min(W, 1280), "height": min(H, 1280)}, device_scale_factor=1)
    if verbose:
        page.on("console", lambda m: print("[page]", m.text, file=sys.stderr) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: print("[pageerror]", e, file=sys.stderr))
    await page.goto(f"{sink.base}/engine/index.html")
    await page.wait_for_function("window.XM_LOADED === true || !!window.XM_ERROR", timeout=60000)
    err = await page.evaluate("window.XM_ERROR || null")
    if err:
        raise RuntimeError("engine load error: " + err)
    info = await page.evaluate("cfg => window.XM.boot(cfg)", cfg)
    return page, info
