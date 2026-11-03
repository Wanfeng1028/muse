"""Audio for motion-studio films: the shared library, music measurement, and the Mix every sound.py uses.

Library (path from ~/.motion-studio.json "library"):
  catalog.json                 every asset: id, title, file, licence, url; tracks also bpm + corrected downbeat
  mixkit/music/<id>.mp3        Mixkit Free License (music): social, YouTube, ads; not broadcast, games, music-only remixes
  mixkit/sfx/<id>.wav          Mixkit Free License (SFX): any video use, no attribution
  kenney/<pack>/...            Kenney CC0 packs
  sfx/<source>/<kind>/...      clips added by `studio.py import-sfx` (CC0, CC BY, Mixkit), with creator and attribution
Recorded or licensed sound only: no synthesized beeps.
"""
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
HERE = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
LICENCES = {
    "mixkit-music": "Mixkit Free License (music): https://mixkit.co/license/#musicFree",
    "mixkit-sfx": "Mixkit Free License (SFX): https://mixkit.co/license/#sfxFree",
    "kenney-cc0": "Creative Commons Zero (CC0): https://creativecommons.org/publicdomain/zero/1.0/",
}


# ── library + catalog ──────────────────────────────────────
def library_dir():
    cfg = Path.home() / ".motion-studio.json"
    lib = json.loads(cfg.read_text()).get("library") if cfg.exists() else None
    path = Path(lib or "~/motion-studio/library").expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def catalog():
    p = library_dir() / "catalog.json"
    return json.loads(p.read_text()) if p.exists() else {"tracks": {}, "sfx": {}, "packs": {}}


def save_catalog(cat):
    (library_dir() / "catalog.json").write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n")


def _get(url, dest=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if dest:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
    return data


def mixkit_search(kind, query):
    """List (id, title) from a Mixkit category page. kind: 'music' (e.g. 'house', 'downtempo') or 'sfx' (e.g. 'footsteps')."""
    base = "https://mixkit.co/free-stock-music/" if kind == "music" else "https://mixkit.co/free-sound-effects/"
    page = _get(base + query.strip("/") + "/").decode("utf-8", "replace")
    pat = r"/music/(\d+)/" if kind == "music" else r"/active_storage/sfx/(\d+)/"
    ids = list(dict.fromkeys(re.findall(pat, page)))
    titles = [html.unescape(re.sub("<[^>]+>", "", t)).strip() for t in re.findall(r'<h2 class="item-grid-card__title">(.*?)</h2>', page, re.S)]
    found = list(zip(ids, titles))
    cache = library_dir() / ".search-titles.json"   # so `fetch` can record the title the search showed
    seen = json.loads(cache.read_text()) if cache.exists() else {}
    seen.update({f"{kind}-{i}": t for i, t in found})
    cache.write_text(json.dumps(seen, indent=1))
    return found


def fetch_mixkit(kind, mid, title=""):
    lib, cat = library_dir(), catalog()
    key = f"mixkit-{mid}"
    if kind == "music":
        dest = lib / "mixkit" / "music" / f"{mid}.mp3"
        url = f"https://assets.mixkit.co/music/{mid}/{mid}.mp3"
        table, lic = "tracks", "mixkit-music"
    else:
        dest = lib / "mixkit" / "sfx" / f"{mid}.wav"
        url = f"https://assets.mixkit.co/active_storage/sfx/{mid}/{mid}.wav"
        table, lic = "sfx", "mixkit-sfx"
    if not dest.exists():
        _get(url, dest)
    entry = cat[table].get(key, {})
    entry.update({"id": key, "file": str(dest.relative_to(lib)), "url": url, "licence": LICENCES[lic]})
    cache = lib / ".search-titles.json"
    title = title or (json.loads(cache.read_text()).get(f"{kind}-{mid}", "") if cache.exists() else "")
    if title:
        entry["title"] = title
    entry.setdefault("title", "")
    cat[table][key] = entry
    save_catalog(cat)
    return key, dest


def fetch_kenney(pack="impact-sounds"):
    """Download a Kenney CC0 pack (default: impact-sounds) into the library."""
    lib, cat = library_dir(), catalog()
    dest = lib / "kenney" / pack
    if not (dest / "License.txt").exists():
        page = _get(f"https://kenney.nl/assets/{pack}").decode("utf-8", "replace")
        m = re.search(rf"https://kenney\.nl/media/pages/assets/{pack}/[^\"]+\.zip", page)
        if not m:
            raise SystemExit(f"no download link found for Kenney pack {pack}")
        zp = dest.with_suffix(".zip")
        _get(m.group(0), zp)
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run(["unzip", "-oq", str(zp), "-d", str(dest)], check=True)
        zp.unlink()
    cat["packs"][f"kenney-{pack}"] = {"id": f"kenney-{pack}", "dir": str(dest.relative_to(lib)), "licence": LICENCES["kenney-cc0"],
                                      "url": f"https://kenney.nl/assets/{pack}"}
    save_catalog(cat)
    return dest


BANNED_LICENCE = ("NC", "ND", "SA", "NONCOMMERCIAL", "NON-COMMERCIAL", "NODERIVATIVES", "SHAREALIKE")


def licence_ok(name):
    """Commercial use, edits allowed, no share-alike: CC0, CC BY, Mixkit, Kenney. Anything NC, ND or SA stays out."""
    words = name.upper().replace("-", " ").replace("_", " ").split()
    return bool(name.strip()) and not any(w in BANNED_LICENCE for w in words)


def import_sfx(src, roles=0):
    """Add a staged folder of sound effects to the library: src/manifest.json lists each clip (kind, file, source,
    upstream, title, creator, licence, licence_url, source_page, duration_s, attribution); src/ranking.json (optional,
    from earshot) adds each clip's score. Clips are copied to <library>/sfx/<source>/<kind>/ and catalogued with
    "candidates": [<kind>, ...], so mix doesn't use them until they carry "role": <kind>. A file staged under two kinds
    is one entry with both kinds. roles=N gives the role to earshot's
    top N per kind straight away (a provisional pick, to be confirmed by ear). Returns (added, refused)."""
    src = Path(src).expanduser()
    lib, cat = library_dir(), catalog()
    manifest = json.loads((src / "manifest.json").read_text())
    rank = json.loads((src / "ranking.json").read_text()) if (src / "ranking.json").exists() else {"kinds": {}}
    scores = {sc["file"]: sc for k in rank["kinds"].values() for sc in k.get("scores", [])}
    top = {f: i for k in rank["kinds"].values() for i, f in enumerate(k.get("top3", []))}
    added, refused = [], []
    for m in manifest:
        if not licence_ok(m.get("licence") or ""):
            refused.append((m["file"], m.get("licence") or "no licence"))
            continue
        if "generated" in f"{m.get('source', '')} {m.get('licence', '')}".lower():
            refused.append((m["file"], "drawn in code: the library takes recorded (or AI) clips only"))
            continue
        f = src / m["file"]
        key = Path(m["file"]).stem
        dest = lib / "sfx" / m.get("source", "other") / m["kind"] / f.name
        entry = cat["sfx"].get(key, {})
        if not (entry.get("file") and (lib / entry["file"]).exists()):
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(f, dest)
        kinds = list(dict.fromkeys(candidate_kinds(entry) + [m["kind"]]))   # one file staged under two kinds keeps both
        entry.pop("candidate", None); entry.pop("earshot", None)    # older single-kind fields
        keep = entry.get("file") and (lib / entry["file"]).exists()      # a second kind doesn't move the file
        entry.update({"candidates": kinds, "id": key, "title": m.get("title") or "", "file": entry["file"] if keep else str(dest.relative_to(lib)),
                      "url": m.get("source_page") or "", "licence": f"{m['licence']}: {m.get('licence_url') or ''}".rstrip(": "),
                      "licence_name": m["licence"], "creator": m.get("creator") or "", "source": m.get("source") or "",
                      "upstream": m.get("upstream") or "", "duration_s": m.get("duration_s")})
        if m.get("attribution"):
            entry["attribution"] = m["attribution"]
        sc = scores.get(m["file"])
        if sc:
            entry.setdefault("earshot_by_kind", {})[m["kind"]] = {"query": rank["kinds"].get(m["kind"], {}).get("query"), "z": sc.get("z"), "cosine": sc.get("cosine"),
                                "verdict": sc.get("verdict"), "sounds_most_like": sc.get("sounds_most_like"),
                                "rank": top.get(m["file"]), "tool": rank.get("tool"), "commit": rank.get("earshot_commit")}
        if roles and top.get(m["file"], 99) < roles:
            entry["role"] = m["kind"]
        cat["sfx"][key] = entry
        added.append(key)
    save_catalog(cat)
    return added, refused


def candidate_kinds(e):
    """The kinds a catalogued clip is a candidate for (older entries carry one "candidate")."""
    return e.get("candidates") or ([e["candidate"]] if e.get("candidate") else [])


def earshot_for(e, kind):
    """earshot's score for a clip as a candidate for `kind`, or {}."""
    return (e.get("earshot_by_kind") or {}).get(kind) or e.get("earshot") or {}


def set_role(key, kind):
    """Give a catalogued clip a role (mix uses every clip with the role, cycled), or clear it with kind=None."""
    cat = catalog()
    if key not in cat["sfx"]:
        raise SystemExit(f"{key} is not a catalogued sfx")
    if kind:
        cat["sfx"][key]["role"] = kind
    else:
        cat["sfx"][key].pop("role", None)
    save_catalog(cat)


# ── decoding + small DSP ───────────────────────────────────
def load(path, stereo=False, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "2" if stereo else "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).astype(np.float64)
    return x.reshape(-1, 2) if stereo else x


def asset(key, stereo=False):
    """Decode a catalogued asset by id ('mixkit-2541'), or a Kenney file by name ('impactSoft_heavy_003')."""
    lib, cat = library_dir(), catalog()
    for table in ("sfx", "tracks"):
        if key in cat[table]:
            return load(lib / cat[table][key]["file"], stereo)
    for pack in cat["packs"].values():
        hits = list((lib / pack["dir"]).rglob(f"{key}.*"))
        if hits:
            return load(hits[0], stereo)
    raise SystemExit(f"{key} is not in the library: fetch it first (studio.py fetch ...)")


def lowpass(x, hz):
    return sosfilt(butter(2, hz, "lowpass", fs=SR, output="sos"), x)


def fade(x, fin=0.005, fout=0.02):
    x = x.copy()
    a, c = int(fin * SR), min(int(fout * SR), len(x))
    if a: x[:a] *= np.linspace(0, 1, a)
    if c: x[-c:] *= np.linspace(1, 0, c)
    return x


def cut(x, start, dur, fin=0.005, fout=0.02):
    start = max(0.0, start)          # an onset in the first 20 ms would otherwise start the slice before 0
    return fade(x[int(start * SR): int((start + dur) * SR)], fin, fout)


def onsets(x, thr=0.12, gap=0.3):
    env = np.convolve(np.abs(x), np.ones(240) / 240, "same")
    out = []
    for j in np.where(env > thr * env.max())[0]:
        if not out or j - out[-1] > gap * SR:
            out.append(j)
    return [o + int(np.argmax(np.abs(x[o:o + int(0.05 * SR)]))) for o in out]


def single_hits(*keys, length=0.32):
    """Cut individual hits (footsteps, taps) out of longer recordings: vary them by cycling the list."""
    hits = []
    for k in keys:
        x = asset(k)
        hits += [cut(x, o / SR - 0.02, length, 0.002, 0.08) for o in onsets(x) if o + (length + 0.03) * SR < len(x)]
    return hits


# ── music: measure the grid, correct the downbeat ──────────
def sections(loud, jump_db=4.0):
    """Summarise a bar-loudness map as sections: [(from_bar, to_bar, mean_db)], split where loudness jumps."""
    out, start = [], 0
    for i in range(1, len(loud) + 1):
        if i == len(loud) or abs(loud[i] - loud[i - 1]) >= jump_db:
            out.append((start, i, round(sum(loud[start:i]) / (i - start), 1)))
            start = i
    return out


def measure(key):
    """Run product-film's beats.py, then correct the downbeat phase from where the song's sections change.

    beats.py can land the downbeat on the wrong beat of the bar (Cat Walk: 2 beats early). Section changes
    (drops, breakdowns) happen on downbeats, so the beat phase where loudness jumps most is the real one.
    """
    lib, cat = library_dir(), catalog()
    entry = cat["tracks"][key]
    src = lib / entry["file"]
    out = lib / "mixkit" / "music" / f"{key}.beats.json"
    subprocess.run([sys.executable, str(HERE / "beats.py"), "--drums", str(src), "--out", str(out)], check=True, capture_output=True)
    grid = json.loads(out.read_text())
    bpm, beat = grid["bpm"], grid["beatSeconds"]
    x = load(src, sr=22050)
    first = grid["firstBeat"]
    n = int((len(x) / 22050 - first) / beat)
    db = np.array([20 * np.log10(np.sqrt(np.mean(x[int((first + k * beat) * 22050): int((first + (k + 1) * beat) * 22050)] ** 2)) + 1e-9) for k in range(n)])
    jump = np.abs(np.diff(db))
    jump = np.maximum(0, jump - np.median(jump))                      # only real changes count
    raw_k = round((grid["firstDownbeat"] - first) / beat)
    scores = [float(sum(jump[k - 1] for k in range(1, n) if (k - raw_k - p) % 4 == 0)) for p in range(4)]
    p = int(np.argmax(scores))
    downbeat = grid["firstDownbeat"] + p * beat
    bar = 4 * beat
    bars = int((len(x) / 22050 - downbeat) / bar)
    loud = [round(float(20 * np.log10(np.sqrt(np.mean(x[int((downbeat + i * bar) * 22050): int((downbeat + (i + 1) * bar) * 22050)] ** 2)) + 1e-9)), 1) for i in range(bars)]
    entry.update({"duration_s": round(len(x) / 22050, 1), "bpm": round(bpm, 3), "beat": beat, "downbeat": round(downbeat, 4), "raw_downbeat": grid["firstDownbeat"],
                  "phase_shift_beats": p, "grid_spread_ms": grid["gridCheckMs"]["spread"], "bar_loudness_db": loud})
    save_catalog(cat)
    return entry


# ── mood: what a track feels like, measured, so music is chosen for the scene and not by habit ──
# Krumhansl-Kessler key profiles (major, minor), C first
_KK_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# What each mood asks of a track. Each row: feature -> (low, high) where the score is full; it falls off outside.
# energy: mean loudness dBFS; density: onsets per second; bright: spectral centroid Hz; minor: 0 major .. 1 minor;
# dyn: bar-loudness spread in dB (p90 - p10); bpm.
MOODS = {
    "tension":  {"energy": (-30, -17), "density": (0.5, 3.0), "pulse": (0.0, 0.5), "bright": (400, 1600), "minor": (0.55, 1.0), "bpm": (55, 112)},
    "mystery":  {"energy": (-30, -16), "density": (1.0, 3.5), "pulse": (0.2, 0.65), "bright": (500, 1900), "minor": (0.5, 1.0), "bpm": (65, 120)},
    "serious":  {"energy": (-26, -14), "density": (1.5, 4.0), "pulse": (0.3, 0.8), "bright": (700, 2200), "minor": (0.35, 0.9), "bpm": (75, 125)},
    "calm":     {"energy": (-32, -18), "density": (0.2, 2.5), "pulse": (0.0, 0.5), "bright": (400, 1700), "minor": (0.0, 0.5), "bpm": (50, 105)},
    "warm":     {"energy": (-26, -14), "density": (1.0, 3.5), "pulse": (0.2, 0.7), "bright": (700, 2100), "minor": (0.0, 0.45), "bpm": (70, 115)},
    "drive":    {"energy": (-17, -6), "density": (3.5, 9.0), "pulse": (0.55, 1.0), "bright": (1400, 4000), "minor": (0.0, 1.0), "bpm": (110, 140)},
    "uplift":   {"energy": (-19, -8), "density": (2.5, 7.0), "pulse": (0.45, 1.0), "bright": (1300, 3500), "minor": (0.0, 0.4), "bpm": (95, 135)},
}
# Mixkit search words that tend to return each mood (for `studio.py search music ...`)
MOOD_SEARCH = {
    "tension": ["suspense", "tension", "dark ambient", "thriller"], "mystery": ["mystery", "investigation", "detective"],
    "serious": ["documentary", "cinematic", "corporate serious"], "calm": ["ambient", "piano", "calm"],
    "warm": ["acoustic", "inspiring piano", "hopeful"], "drive": ["tech house", "driving", "energetic"],
    "uplift": ["uplifting", "inspiring", "motivational"],
}


def mood(key):
    """Measure a catalogued track's mood features and store them on its catalog entry."""
    lib, cat = library_dir(), catalog()
    entry = cat["tracks"][key]
    sr = 22050
    x = load(lib / entry["file"], sr=sr)
    n, hop = 2048, 1024
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    mag = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(n, 1 / sr)
    rms_db = 20 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    live = rms_db > np.percentile(rms_db, 95) - 35                 # ignore the silent tail and lead-in
    centroid = (mag * freqs).sum(axis=1) / (mag.sum(axis=1) + 1e-9)
    flux = np.maximum(0, np.diff(np.log1p(mag[:, (freqs > 60) & (freqs < 8000)]), axis=0)).sum(axis=1)
    thr = np.median(flux) + 0.5 * flux.std()
    peaks = [i for i in range(1, len(flux) - 1) if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
    # pulse strength: how much of the flux sits on a regular beat (drums) rather than spread out (pads, piano)
    ac = np.correlate(flux - flux.mean(), flux - flux.mean(), "full")[len(flux) - 1:]
    lag_lo, lag_hi = int(0.25 * sr / hop), int(1.0 * sr / hop)
    pulse = float(ac[lag_lo:lag_hi].max() / (ac[0] + 1e-9))
    secs = live.sum() * hop / sr
    # chroma from the spectrum, 80 Hz - 5 kHz
    band = (freqs > 80) & (freqs < 5000)
    pc = np.round(12 * np.log2(freqs[band] / 261.63)).astype(int) % 12
    chroma = np.zeros(12)
    np.add.at(chroma, pc, (mag[live][:, band] ** 2).sum(axis=0))
    chroma /= chroma.sum() + 1e-12
    corr = lambda prof, k: float(np.corrcoef(chroma, np.roll(prof, k))[0, 1])
    best_maj = max(corr(_KK_MAJ, k) for k in range(12)); best_min = max(corr(_KK_MIN, k) for k in range(12))
    minor = float(np.clip(0.5 + (best_min - best_maj) * 2.5, 0, 1))
    bars = np.array([b for b in entry.get("bar_loudness_db", []) if b > -60])
    feats = {"energy": round(float(np.mean(rms_db[live])), 1), "density": round(float(len(peaks) / max(secs, 1)), 2),
             "pulse": round(pulse, 2),
             "bright": round(float(np.mean(centroid[live]))), "minor": round(minor, 2),
             "dyn": round(float(np.percentile(bars, 90) - np.percentile(bars, 10)), 1) if len(bars) > 4 else None,
             "bpm": entry.get("bpm")}
    entry["mood"] = feats
    save_catalog(cat)
    return feats


def mood_score(feats, name):
    """0..1: how well measured features fit a mood. Weighted geometric mean, so one bad miss (a 130 bpm club track
    for "tension") sinks the score instead of being averaged away."""
    want = MOODS[name]
    weights = {"energy": 0.8, "density": 1.0, "bright": 0.7, "minor": 1.2, "bpm": 1.0, "pulse": 1.0}
    soft = {"energy": 5, "density": 1.5, "bright": 700, "minor": 0.25, "bpm": 15, "pulse": 0.15}
    logs, wsum = 0.0, 0.0
    for f, (lo, hi) in want.items():
        v = feats.get(f)
        if v is None:
            continue
        miss = max(lo - v, 0, v - hi) / soft[f]
        logs += weights[f] * np.log(max(0.03, 1 - miss)); wsum += weights[f]
    return round(float(np.exp(logs / wsum)), 3) if wsum else 0.0


def rank_tracks(name, keys=None):
    """Library tracks ranked for a mood: [(score, key, title, feats)]. Measures any track not yet measured."""
    cat = catalog()
    out = []
    for key, e in cat["tracks"].items():
        if keys and key not in keys:
            continue
        feats = e.get("mood") or mood(key)
        out.append((mood_score(feats, name), key, e.get("title", key), feats))
    return sorted(out, reverse=True)


# ── the mix ────────────────────────────────────────────────
def grid_from_film(film_html):
    """bpm and bars from the film's K.setup(...) call, so sound.py always matches the picture."""
    s = Path(film_html).read_text()
    setup = re.search(r"K\.setup\(\{(.*?)\}\)", s, re.S)   # the K.setup call itself, not the first "bpm:" anywhere
    if not setup:
        raise SystemExit(f"{film_html}: no K.setup({{...}}) call found")
    bpm = float(re.search(r"bpm:\s*([\d.]+)", setup.group(1)).group(1))
    bars = int(re.search(r"bars:\s*(\d+)", setup.group(1)).group(1))
    return bpm, bars


class Mix:
    def __init__(self, film_dir):
        self.film = Path(film_dir)
        self.bpm, self.bars = grid_from_film(self.film / "film.html")
        self.beat = 60 / self.bpm
        self.dur = self.bars * 4 * self.beat
        self.buf = np.zeros((int((self.dur + 0.5) * SR), 2))

    def b(self, bar, beat=0):
        return (bar * 4 + beat) * self.beat

    def put(self, sig, at, gain=1.0, pan=0.0, peak=None):
        """Place a mono cue so its transient (peak, seconds into the clip; measured if None) lands on `at`."""
        if peak is None:
            peak = np.argmax(np.abs(sig[: int(0.6 * SR)])) / SR
        i = int(round((at - peak) * SR))
        if i < 0:
            sig, i = sig[-i:], 0
        n = min(len(sig), len(self.buf) - i)
        if n <= 0:
            return
        self.buf[i:i + n, 0] += gain * np.sqrt(0.5 * (1 - pan)) * sig[:n]
        self.buf[i:i + n, 1] += gain * np.sqrt(0.5 * (1 + pan)) * sig[:n]

    def music(self, key, segments, at_bar=0, gain=0.8, fade_out=1.4):
        """Cut a measured track on its bars and lay it on the film's grid.

        segments: [(from_bar, to_bar), ...] in the song's (corrected) bars, to_bar exclusive; they play back to back
        from film bar `at_bar`. The film must run at the song's tempo: set K.setup({bpm}) to the catalog's bpm.
        """
        entry = catalog()["tracks"].get(key)
        if not entry or "downbeat" not in entry:
            raise SystemExit(f"{key}: fetch and measure it first (studio.py fetch music <id>, or studio.py measure {key})")
        if abs(entry["bpm"] - self.bpm) > 0.05:
            print(f"WARNING: film bpm {self.bpm} != track bpm {entry['bpm']}; set K.setup({{bpm: {entry['bpm']}}})", flush=True)
        song = load(library_dir() / entry["file"], stereo=True)
        bar = 4 * 60 / entry["bpm"]
        pieces = []
        for a, c in segments:
            seg = song[int((entry["downbeat"] + a * bar) * SR): int((entry["downbeat"] + c * bar) * SR)].copy()
            f = int(0.005 * SR)
            seg[:f] *= np.linspace(0, 1, f)[:, None]; seg[-f:] *= np.linspace(1, 0, f)[:, None]
            pieces.append(seg)
        edit = np.concatenate(pieces)
        fo = int(fade_out * SR)
        edit[-fo:] *= np.linspace(1, 0, fo)[:, None]
        i = int(self.b(at_bar) * SR)
        n = min(len(edit), len(self.buf) - i)
        self.buf[i:i + n] += gain * edit[:n]

    def bed(self, key, spans, gain=0.5, offset=20.0):
        """An ambience under spans [(from_s, to_s, level), ...], with 0.35 s soft edges."""
        x = asset(key)
        x = x[int(offset * SR): int(offset * SR) + len(self.buf)]
        x = np.pad(x, (0, max(0, len(self.buf) - len(x))))
        env = np.zeros(len(self.buf))
        for a, c, lvl in spans:
            env[int(a * SR): int(c * SR)] = np.maximum(env[int(a * SR): int(c * SR)], lvl)
        k = int(0.35 * SR)
        env = np.convolve(env, np.ones(k) / k, "same")
        self.buf[:, 0] += gain * x * env
        self.buf[:, 1] += gain * np.roll(x, 2400) * env

    def master(self, dest=None, lufs=-14.0, tp=-1.5):
        """Two-pass loudnorm to `lufs` / `tp`, 48 kHz 16-bit; writes out/mix.wav by default."""
        dest = Path(dest or self.film / "out" / "mix.wav")
        dest.parent.mkdir(parents=True, exist_ok=True)
        mix = self.buf[: int(self.dur * SR)].copy()
        tail = int(0.8 * SR)
        mix[-tail:] *= np.linspace(1, 0, tail)[:, None]
        raw = dest.with_suffix(".raw.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f64le", "-ar", str(SR), "-ac", "2", "-i", "-", str(raw)], input=mix.tobytes(), check=True)
        probe = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"],
                               capture_output=True, text=True).stderr
        m = json.loads(probe[probe.rindex("{"): probe.rindex("}") + 1])
        flt = (f"loudnorm=I={lufs}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
               f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", flt, "-ar", str(SR), "-c:a", "pcm_s16le", str(dest)], check=True)
        raw.unlink()
        print(f"{dest}  (input {m['input_i']} LUFS -> {lufs})")
        return dest
