"""land.py <land-110m.json> > assets/land.js
Turns Natural Earth land (world-atlas TopoJSON, public-domain data) into an equal-area grid of
[lat, lon] dots on land, used by the globe scene."""
import json, math, sys

topo = json.load(open(sys.argv[1]))
sx, sy = topo["transform"]["scale"]; tx, ty = topo["transform"]["translate"]
arcs = []
for a in topo["arcs"]:
    x = y = 0; pts = []
    for dx, dy in a:
        x += dx; y += dy
        pts.append((x * sx + tx, y * sy + ty))
    arcs.append(pts)

def ring(idx):
    out = []
    for i in idx:
        seg = arcs[i] if i >= 0 else arcs[~i][::-1]
        out.extend(seg if not out else seg[1:])
    return out

polys = []
for g in topo["objects"]["land"]["geometries"]:
    parts = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
    for p in parts:
        rings = [ring(r) for r in p]
        xs = [q[0] for r in rings for q in r]; ys = [q[1] for r in rings for q in r]
        polys.append((rings, (min(xs), min(ys), max(xs), max(ys))))

def inside(lon, lat):
    for rings, (x0, y0, x1, y1) in polys:
        if lon < x0 or lon > x1 or lat < y0 or lat > y1: continue
        c = False
        for r in rings:
            n = len(r); j = n - 1
            for i in range(n):
                xi, yi = r[i]; xj, yj = r[j]
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi: c = not c
                j = i
        if c: return True
    return False

step = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
out = []
lat = -84 + step / 2
while lat < 84:
    n = max(1, int(round(360 * math.cos(math.radians(lat)) / step)))
    for k in range(n):
        lon = -180 + (k + 0.5 * (int(round(lat / step)) % 2)) * 360.0 / n
        if lon > 180: lon -= 360
        if inside(lon, lat): out.append((round(lat, 1), round(lon, 1)))
    lat += step
flat = ",".join("%g,%g" % p for p in out)
print("// %d land dots, %.1f deg equal-area grid, from Natural Earth 110m land (public domain) via world-atlas" % (len(out), step))
print("window.LAND = [" + flat + "];")
