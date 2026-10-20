#!/usr/bin/env python3
"""Inline the brand fonts into the scene so a render never depends on the network.

fonts.json: [{"family": "Geist", "weight": 500, "file": "fonts/Geist-Medium.woff2"}, ...]
Usage: build.py [scene.html] [fonts.json] [scene.built.html]
"""
import base64, json, pathlib, sys

src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "scene.html")
fonts = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "fonts.json")
out = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else src.with_suffix(".built.html"))

MIME = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}
css = []
for f in json.loads(fonts.read_text()) if fonts.exists() else []:
    p = fonts.parent / f["file"]
    fmt = MIME.get(p.suffix.lower())
    if not fmt:
        sys.exit(f"unsupported font file: {p}")
    data = base64.b64encode(p.read_bytes()).decode()
    css.append(f"@font-face{{font-family:'{f['family']}';font-weight:{f.get('weight', 400)};"
               f"font-style:{f.get('style', 'normal')};font-display:block;"
               f"src:url(data:font/{fmt};base64,{data}) format('{fmt}')}}")

html = src.read_text()
if "/*FONTS*/" not in html:
    sys.exit("scene has no /*FONTS*/ slot in its <style>")
out.write_text(html.replace("/*FONTS*/", "\n".join(css)))
print(f"{out} ({len(css)} font faces)")
