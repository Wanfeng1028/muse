#!/usr/bin/env python3
"""screen_quad.py <photo> [keyed-out.webp|png] [x0,y0,...,x3,y3]

For a photo of a phone whose screen is flat green: prints the screen corners (TL, TR, BR, BL,
image pixels) to paste into index.html, and writes the photo with the screen keyed out.
THR=100,35 loosens the green test for screens that came out darker; the optional last
argument seeds the corners by hand when the automatic guess fails."""
import sys, numpy as np
from PIL import Image
f = sys.argv[1]; out = sys.argv[2] if len(sys.argv) > 2 else None
init = np.array(list(map(float, sys.argv[3].split(','))), np.float64).reshape(4, 2) if len(sys.argv) > 3 else None
im = np.asarray(Image.open(f).convert('RGB')).astype(np.float32)
r, g, b = im[..., 0], im[..., 1], im[..., 2]
gm = g - np.maximum(r, b)
import os
T1, T2 = map(float, os.environ.get('THR', '130,70').split(','))
mask = (g > T1) & (gm > T2)
# keep the biggest blob: flood from the densest row/col centre
ys, xs = np.nonzero(mask)
cy, cx = int(np.median(ys)), int(np.median(xs))
from collections import deque
H, W = mask.shape; seen = np.zeros_like(mask); q = deque([(cy, cx)]); seen[cy, cx] = True
while q:
    y, x = q.popleft()
    for yy, xx in ((y+1,x),(y-1,x),(y,x+1),(y,x-1)):
        if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not seen[yy, xx]:
            seen[yy, xx] = True; q.append((yy, xx))
mask = seen
ys, xs = np.nonzero(mask)
pts = np.stack([xs, ys], 1).astype(np.float64)
# convex hull (monotone chain)
P = sorted(set(map(tuple, pts.astype(int).tolist())))
def cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
lo = []; up = []
for p in P:
    while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
    lo.append(p)
for p in reversed(P):
    while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
    up.append(p)
hull = np.array(lo[:-1] + up[:-1], np.float64)
# corners: extreme hull points along the diagonals of the principal axes
m0 = pts.mean(0); _, _, vt = np.linalg.svd((pts[::17] - m0), full_matrices=False); u, v = vt[0], vt[1]
dirs = [(-u - v), (u - v), (u + v), (-u + v)]
poly = np.array([hull[np.argmax(hull @ (d / np.linalg.norm(d)))] for d in dirs])
if init is not None: poly = init
# keep them in polygon order around the centre
c1 = poly.mean(0); poly = poly[np.argsort(np.arctan2(poly[:, 1]-c1[1], poly[:, 0]-c1[0]))]
# refine every side with a line fit through hull-boundary points near its middle
bnd = []
for y in range(H):
    row = np.nonzero(mask[y])[0]
    if len(row): bnd += [(row[0], y), (row[-1], y)]
for x in range(W):
    col = np.nonzero(mask[:, x])[0]
    if len(col): bnd += [(x, col[0]), (x, col[-1])]
bnd = np.array(bnd, np.float64)
lines = []
for i in range(4):
    a, c = poly[i], poly[(i+1) % 4]; d = c - a; L = np.linalg.norm(d); u = d / L; nrm = np.array([-u[1], u[0]])
    rel = bnd - a; s = rel @ u / L; dist = np.abs(rel @ nrm)
    band = 0.09 * min(np.linalg.norm(poly[1]-poly[0]), np.linalg.norm(poly[2]-poly[1]))
    sel = bnd[(s > 0.25) & (s < 0.75) & (dist < band)]
    m = sel.mean(0); _, _, vt = np.linalg.svd(sel - m); dirv = vt[0]
    lines.append((m, dirv))
def inter(l1, l2):
    (p, d), (q, e) = l1, l2
    A = np.array([d, -e]).T; t = np.linalg.solve(A, q - p); return p + t[0]*d
corners = np.array([inter(lines[i-1], lines[i]) for i in range(4)])
# order TL, TR, BR, BL by angle around the centre, starting top-left
c0 = corners.mean(0); ang = np.arctan2(corners[:, 1]-c0[1], corners[:, 0]-c0[0]); corners = corners[np.argsort(ang)]
k = int(np.argmin(corners.sum(1))); corners = np.roll(corners, -k, 0)
print(f, 'size', W, H, 'pixels', int(mask.sum()))
print('quad', [[round(float(v), 1) for v in p] for p in corners])
sides = [np.linalg.norm(corners[(i+1) % 4]-corners[i]) for i in range(4)]
print('sides', [round(float(s), 1) for s in sides], 'aspect h/w', round(float((sides[1]+sides[3])/(sides[0]+sides[2])), 3))
if out:
    # alpha: fully transparent inside the screen, soft on the anti-aliased rim, with despill
    soft = np.clip((gm - 25) / 60, 0, 1)
    grow = np.zeros_like(mask)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            grow |= np.roll(np.roll(mask, dy, 0), dx, 1)
    alpha = 1 - np.where(grow, np.maximum(soft, mask.astype(np.float32)), 0)
    rgb = im.copy(); spill = grow & (gm > 0); rgb[..., 1] = np.where(spill, np.maximum(r, b), g)
    rgba = np.dstack([rgb, alpha * 255]).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(rgba, 'RGBA')
    img.save(out, quality=90, method=6) if out.endswith('.webp') else img.save(out, optimize=True)
    print('keyed ->', out)
