#!/usr/bin/env python3
"""
kol.py — pipeline helper for crypto-KOL explainer videos (Remotion + MiniMax TTS).

  python3 kol.py new       <proj> [--example]      create a video project from the template
  python3 kol.py brand     <handle> [--tagline T] [--avatar FILE]   save the creator brand once (handle, tagline, avatar)
  python3 kol.py avatar    <proj> <twitter_handle|--file PATH>     fetch/import the X avatar into a project (+ brand cache)
  python3 kol.py check     <proj>                  validate video.json, print subtitles as they will appear
  python3 kol.py voicekit  <proj> <out_dir>        write per-scene TTS texts + MiniMax (mmx) scripts
  python3 kol.py timeline  <proj> [voice_dir]      ASR-align voice → timeline.json + build/voice.wav (no dir = estimate)
  python3 kol.py mix       <proj>                  synthesize BGM + SFX, duck, loudness-normalize → build/mix.wav

A project = <proj>/video.json (the spec) + <proj>/video (Remotion app) + <proj>/build (intermediates).
"""
import json, os, re, sys, shutil, difflib, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FPS = 30; SR = 48000
PRE = 0.45          # cover hold at frame 0 (seconds)
TAIL = 0.5          # silence after each scene's voice
OUTRO_HOLD = 3.4    # follow-card time after the last line
BRAND = os.path.expanduser("~/.config/kol-video/brand")   # remembered creator brand: brand.json + avatar.jpg
PUNCT = "，。？！；：、,.?!;:「」“”\"' "


# ----------------------------------------------------------------- spec helpers
def load(proj):
    return json.load(open(os.path.join(proj, "video.json"), encoding="utf-8"))


def disp(spec, t):
    """TTS chunk → subtitle text: replacements (Chinese numerals → digits) + [highlight] marks."""
    for a, b in spec.get("replace", []):
        t = t.replace(a, b)
    for h in sorted(spec.get("highlight", []), key=len, reverse=True):
        i = t.find(h)
        if i < 0:
            continue
        pre = t[:i]
        if pre.count("[") > pre.count("]"):
            continue
        seg = t[i:i + len(h)]
        if "[" in seg or "]" in seg:
            continue
        t = pre + "[" + h + "]" + t[i + len(h):]
    return t


def strip(s):
    return "".join(ch for ch in s if ch not in PUNCT and not ch.isspace())


# ----------------------------------------------------------------- new
def cmd_new(proj, example=False):
    os.makedirs(proj, exist_ok=True)
    dst = os.path.join(proj, "video")
    if os.path.exists(dst):
        sys.exit(f"{dst} already exists")
    shutil.copytree(os.path.join(ROOT, "template"), dst, ignore=shutil.ignore_patterns("node_modules"))
    os.makedirs(os.path.join(proj, "build"), exist_ok=True)
    if os.path.exists(os.path.join(BRAND, "brand.json")):
        shutil.copy(os.path.join(BRAND, "brand.json"), os.path.join(dst, "src", "brand.json"))
        if os.path.exists(os.path.join(BRAND, "avatar.jpg")):
            shutil.copy(os.path.join(BRAND, "avatar.jpg"), os.path.join(dst, "public", "avatar.jpg"))
        print("applied saved brand:", json.load(open(os.path.join(BRAND, "brand.json")))["handle"])
    else:
        print("NOTE: no saved brand yet — run `kol.py brand @handle` (ask the user for their X/Twitter handle first)")
    spec_src = os.path.join(ROOT, "examples", "liq-vs-stoploss", "video.json")
    spec_dst = os.path.join(proj, "video.json")
    if not os.path.exists(spec_dst):
        shutil.copy(spec_src, spec_dst)
    cache = os.path.expanduser("~/.cache/kol-video/node_modules")
    if os.path.isdir(cache):
        os.symlink(cache, os.path.join(dst, "node_modules"))
        print("linked cached node_modules")
    else:
        print("installing npm deps (first run, ~1 min)…")
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=dst, check=True)
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        try:
            shutil.move(os.path.join(dst, "node_modules"), cache)
            os.symlink(cache, os.path.join(dst, "node_modules"))
        except Exception as e:
            print("cache skipped:", e)
    print(f"project ready: {proj}\n  edit {spec_dst} and {dst}/src/scenes.tsx" + ("  (example content kept)" if example else ""))


# ----------------------------------------------------------------- avatar
def cmd_avatar(proj, handle):
    """Best-effort fetch of a public X/Twitter avatar. Prints FAILED when no network path works —
    then ask the user to upload their avatar and run: kol.py avatar <proj> --file <path>."""
    from PIL import Image
    import io, urllib.request
    out = os.path.join(proj, "video", "public", "avatar.jpg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if handle == "--file":
        src = sys.argv[4]
        img = Image.open(src)
    else:
        h = handle.lstrip("@").strip()
        img = None
        tries = []
        # 1) fxtwitter public API → profile image url
        try:
            req = urllib.request.Request(f"https://api.fxtwitter.com/{h}", headers={"User-Agent": "kol-video/1.0"})
            d = json.load(urllib.request.urlopen(req, timeout=15))
            url = d["user"]["avatar_url"].replace("_normal.", "_400x400.")
            img = Image.open(io.BytesIO(urllib.request.urlopen(url, timeout=15).read()))
        except Exception as e:
            tries.append(f"fxtwitter: {e}")
        # 2) unavatar.io
        if img is None:
            try:
                req = urllib.request.Request(f"https://unavatar.io/x/{h}?fallback=false", headers={"User-Agent": "kol-video/1.0"})
                img = Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=20).read()))
            except Exception as e:
                tries.append(f"unavatar: {e}")
        if img is None:
            print("FAILED to fetch avatar:\n  " + "\n  ".join(tries))
            sys.exit(2)
    img = img.convert("RGB")
    w, hgt = img.size
    s = min(w, hgt)
    img = img.crop(((w - s) // 2, (hgt - s) // 2, (w - s) // 2 + s, (hgt - s) // 2 + s)).resize((400, 400), Image.LANCZOS)
    img.save(out, quality=92)
    os.makedirs(BRAND, exist_ok=True); img.save(os.path.join(BRAND, "avatar.jpg"), quality=92)
    print(f"avatar saved: {out}  (source {w}x{hgt}) — show it to the user and confirm it is theirs")


# ----------------------------------------------------------------- brand
def cmd_brand(handle, tagline=None, avatar=None):
    """Remember the creator: handle (+ optional tagline) and avatar (fetched from X, or a local file)."""
    h = "@" + handle.lstrip("@").strip()
    os.makedirs(BRAND, exist_ok=True)
    p = os.path.join(BRAND, "brand.json")
    d = json.load(open(p)) if os.path.exists(p) else {}
    d.update({"handle": h, "avatar": "avatar.jpg"})
    d.setdefault("tagline", "币圈 · AI 交易干货")
    if tagline is not None:
        d["tagline"] = tagline
    json.dump(d, open(p, "w"), ensure_ascii=False, indent=1)
    tmp = os.path.join(BRAND, "_tmp_proj")
    os.makedirs(os.path.join(tmp, "video", "public"), exist_ok=True)
    try:
        if avatar:
            sys.argv[4:] = [avatar]; cmd_avatar(tmp, "--file")
        else:
            cmd_avatar(tmp, h)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"brand saved in {BRAND}: {d}")


# ----------------------------------------------------------------- check
def cmd_check(proj):
    spec = load(proj)
    ok = True
    ids = set()
    for s in spec["scenes"]:
        if s["id"] in ids:
            print("duplicate id", s["id"]); ok = False
        ids.add(s["id"])
        a, b = strip(s["tts"]), strip("".join(s["chunks"]))
        if a != b:
            ok = False
            sm = difflib.SequenceMatcher(None, a, b)
            print(f"[{s['id']}] tts and chunks differ:")
            for op, i1, i2, j1, j2 in sm.get_opcodes():
                if op != "equal":
                    print(f"   {op}: tts='{a[i1:i2]}' chunks='{b[j1:j2]}'")
        for c in s["chunks"]:
            d = disp(spec, c)
            n = len(re.sub(r"[\[\]]", "", d))
            flag = "  <-- long (>16), consider splitting" if n > 16 else ""
            print(f"  {s['id']:<14} {d}{flag}")
    total = sum(len(strip(s["tts"])) for s in spec["scenes"])
    print(f"\n{len(spec['scenes'])} scenes, {total} chars ≈ {total / 5.0:.0f}s at MiniMax 1.15x (incl. pauses)")
    print("OK" if ok else "FIX the issues above")
    return ok


# ----------------------------------------------------------------- voicekit
GEN_FILL = r'''#!/bin/bash
# Generate any missing scene voice files with MiniMax speech-2.8-hd (skips existing ones, retries 3x).
# Override: VOICE=... SPEED=... bash gen_fill.sh
cd "$(dirname "$0")"
if command -v mmx >/dev/null 2>&1; then MMX=(mmx); else MMX=(npx -y mmx-cli); fi
SPEED="${SPEED:-1.15}"
VOICE="${VOICE:-male-qn-jingying}"
PRON=(__PRON__)
d="out/$(echo "$VOICE" | tr ' ()' '___')"; mkdir -p "$d"
total=$(ls text/*.txt | wc -l | tr -d ' ')
for f in text/*.txt; do
  n=$(basename "$f" .txt)
  [ -s "$d/$n.wav" ] && continue
  for try in 1 2 3; do
    echo "[$VOICE] $n (try $try)"
    "${MMX[@]}" speech synthesize --model speech-2.8-hd --non-interactive --quiet --text-file "$f" --voice "$VOICE" --speed "$SPEED" \
      --language Chinese --format wav --sample-rate 32000 "${PRON[@]}" --out "$d/$n.wav" >>log.txt 2>&1 && break
    sleep 3
  done
  [ -s "$d/$n.wav" ] || echo "FAILED: $VOICE $n" | tee -a log.txt
done
echo "done: $(ls "$d" | wc -l | tr -d ' ') / $total files in $d"
'''
COMMAND = '''#!/bin/zsh -l
# Double-click: generate the voice-over with your local MiniMax API (mmx CLI)
cd "$(dirname "$0")"
bash ./gen_fill.sh
echo ""
echo "Press Enter to close"
read
'''


def cmd_voicekit(proj, out):
    spec = load(proj)
    os.makedirs(os.path.join(out, "text"), exist_ok=True)
    for s in spec["scenes"]:
        open(os.path.join(out, "text", s["id"] + ".txt"), "w", encoding="utf-8").write(s["tts"])
    pron = " ".join(f'--pronunciation "{p}"' for p in spec.get("pronunciations", []))
    open(os.path.join(out, "gen_fill.sh"), "w").write(GEN_FILL.replace("__PRON__", pron))
    open(os.path.join(out, "双击生成配音.command"), "w").write(COMMAND)
    for f in ("gen_fill.sh", "双击生成配音.command"):
        os.chmod(os.path.join(out, f), 0o755)
    print(f"voice kit written to {out}: {len(spec['scenes'])} texts. Run gen_fill.sh (or double-click the .command on macOS).")
    print(f"wavs will land in {out}/out/<voice>/<scene_id>.wav")


# ----------------------------------------------------------------- timeline
def _np():
    import numpy as np
    return np


def resample(x, sr, to):
    np = _np()
    if sr == to:
        return x
    n = int(round(len(x) * to / sr)); t = np.linspace(0, len(x) - 1, n)
    return np.interp(t, np.arange(len(x)), x).astype(np.float32)


def trim(x, sr, th_db=-42, pad=0.04):
    np = _np()
    win = int(sr * 0.01)
    e = np.array([np.sqrt(np.mean(x[i:i + win] ** 2) + 1e-12) for i in range(0, len(x) - win, win)])
    db = 20 * np.log10(e / (np.max(e) + 1e-9)); idx = np.where(db > th_db)[0]
    a = max(0, idx[0] * win - int(pad * sr)); b = min(len(x), (idx[-1] + 1) * win + int(pad * sr))
    return x[a:b]


def keys(s):
    from pypinyin import lazy_pinyin
    out = []
    for ch in s:
        if ch.isspace() or ch in PUNCT:
            continue
        out.append(ch.lower() if ch.isascii() else lazy_pinyin(ch)[0])
    return out


_rec = None


def asr(x16):
    global _rec
    import sherpa_onnx
    if _rec is None:
        d = os.environ.get("KOL_ASR_DIR", os.path.expanduser("~/.cache/kol-video/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"))
        _rec = sherpa_onnx.OfflineRecognizer.from_sense_voice(model=f"{d}/model.int8.onnx", tokens=f"{d}/tokens.txt", use_itn=False, language="zh")
    st = _rec.create_stream(); st.accept_waveform(16000, x16); _rec.decode_stream(st)
    r = st.result; chars = []; times = []
    for tok, t in zip(r.tokens, r.timestamps):
        tok = tok.replace("▁", "")
        for i, c in enumerate(tok):
            chars.append(c); times.append(t + 0.02 * i)
    return r.text, chars, times


def align(scene, x, sr):
    """per-chunk (onset, offset) seconds: ASR token timestamps aligned to the script by pinyin."""
    np = _np()
    text, chars, times = asr(resample(x, sr, 16000))
    akeys, atimes = [], []
    for c, t in zip(chars, times):
        k = keys(c)
        if k:
            akeys.append(k[0]); atimes.append(t)
    tk, owner = [], []
    for ci, c in enumerate(scene["chunks"]):
        kk = keys(c); tk += kk; owner += [ci] * len(kk)
    sm = difflib.SequenceMatcher(None, tk, akeys, autojunk=False)
    m = {}
    for a, b, n in sm.get_matching_blocks():
        for i in range(n):
            m[a + i] = atimes[b + i]
    known = sorted(m)
    tt = np.interp(np.arange(len(tk)), known, [m[k] for k in known])
    res = []
    for ci in range(len(scene["chunks"])):
        ix = [i for i, o in enumerate(owner) if o == ci]
        res.append([float(tt[ix[0]]), float(tt[ix[-1]]) + 0.18])
    return res, len(m) / max(1, len(tk)), text


def quietest(x, sr, a, b):
    np = _np()
    a = int(a * sr); b = int(b * sr); w = int(0.03 * sr)
    if b - a <= w:
        return (a + b) / 2 / sr
    best = None
    for i in range(a, b - w, int(0.005 * sr)):
        e = float(np.mean(x[i:i + w] ** 2))
        if best is None or e < best[0]:
            best = (e, i + w // 2)
    return best[1] / sr


def find_wav(vdir, sid):
    for ext in (".wav", ".mp3", ".m4a", ".flac"):
        p = os.path.join(vdir, sid + ext)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"no audio for scene {sid} in {vdir}")


def read_audio(path):
    import soundfile as sf
    np = _np()
    try:
        x, sr = sf.read(path, dtype="float32")
    except Exception:
        tmp = path + ".tmp.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "48000", tmp], check=True)
        x, sr = sf.read(tmp, dtype="float32"); os.remove(tmp)
    if x.ndim > 1:
        x = x.mean(1)
    return x, sr


def cmd_timeline(proj, vdir=None):
    np = _np()
    import soundfile as sf
    spec = load(proj)
    segs = spec["scenes"]
    lead = [0.2] + [0.3] * (len(segs) - 1)
    scenes = []; t = PRE; voice = []; follow_at = 0
    for si, s in enumerate(segs):
        start = t; aud = start + lead[si]
        if vdir:
            x, sr = read_audio(find_wav(vdir, s["id"]))
            x = resample(trim(x, sr), sr, SR); dur = len(x) / SR
            spans, ratio, text = align(s, x, SR)
            warn = "  <-- low match: check the wav really reads this script" if ratio < 0.85 else ""
            print(f"{s['id']}: {dur:.2f}s match={ratio:.2f}{warn}\n   asr: {text}")
            voice.append((aud, x))
        else:
            spans = []; c = 0.0
            for ch in s["chunks"]:
                d = 0.19 * len(strip(ch)) + 0.1; spans.append([c, c + d]); c += d + 0.18
            dur = c
        bounds = []
        for k in range(len(spans) - 1):
            a, b = spans[k][1] - 0.05, spans[k + 1][0]
            if vdir and b > a:
                bounds.append(quietest(x, SR, a, b))
            else:
                bounds.append((spans[k][1] + spans[k + 1][0]) / 2 if b > a else spans[k + 1][0] - 0.03)
        subs = []
        for k, ch in enumerate(s["chunks"]):
            ss = 0 if k == 0 else bounds[k - 1]; ee = dur if k == len(spans) - 1 else bounds[k]
            subs.append({"text": disp(spec, ch), "s": round((aud + ss) * FPS), "e": round((aud + ee) * FPS), "v": round((aud + spans[k][0]) * FPS)})
        last = si == len(segs) - 1
        end = aud + dur + TAIL + (OUTRO_HOLD if last else 0)
        if last:
            follow_at = round((aud + dur + 0.35) * FPS)
        sc = {"id": s["id"], "start": round(start * FPS), "end": round(end * FPS), "subs": subs}
        for k in ("chip", "title", "titleParts"):
            if k in s:
                sc[k] = s[k]
        scenes.append(sc)
        t = end
    total = round(t * FPS)
    out = {"fps": FPS, "total": total, "pre": round(PRE * FPS), "followAt": follow_at, "cover": spec.get("cover", {}), "scenes": scenes}
    json.dump(out, open(os.path.join(proj, "video", "src", "timeline.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if vdir:
        buf = np.zeros(int(t * SR) + SR, np.float32)
        for st_, x in voice:
            i = int(st_ * SR); buf[i:i + len(x)] += x
        os.makedirs(os.path.join(proj, "build"), exist_ok=True)
        sf.write(os.path.join(proj, "build", "voice.wav"), buf, SR)
    print(f"timeline: {t:.1f}s, {total} frames" + ("" if vdir else "  (ESTIMATED — no voice yet)"))


# ----------------------------------------------------------------- mix
def cmd_mix(proj):
    np = _np()
    import soundfile as sf
    import pyloudnorm as pyln
    from scipy.ndimage import maximum_filter1d, minimum_filter1d, uniform_filter1d
    spec = load(proj)
    tl = json.load(open(os.path.join(proj, "video", "src", "timeline.json"), encoding="utf-8"))
    T = tl["total"] / FPS + 0.5
    N = int(T * SR); rng = np.random.default_rng(3)
    voice, _ = sf.read(os.path.join(proj, "build", "voice.wav"), dtype="float32")
    voice = np.pad(voice, (0, max(0, N - len(voice))))[:N]

    def env(n, a=0.005, d=0.2):
        tt = np.arange(n) / SR; return np.minimum(1, tt / a) * np.exp(-tt / d)

    def add(buf, x, t0, g=1.0):
        i = int(t0 * SR)
        if i < 0 or i >= len(buf):
            return
        x = x[:len(buf) - i]; buf[i:i + len(x)] += x * g

    def sine(f, dur):
        tt = np.arange(int(dur * SR)) / SR; return np.sin(2 * np.pi * f * tt)

    def saw(f, dur):
        tt = np.arange(int(dur * SR)) / SR; return sum(np.sin(2 * np.pi * f * k * tt) / k for k in range(1, 8)) * 0.6

    # --- BGM: 100 BPM, Am–F–C–G pad + bass + pluck arp + drums (royalty-free, synthesized)
    bpm = spec.get("bpm", 100); beat = 60 / bpm; bar = 4 * beat
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
    mf = lambda m: 440 * 2 ** ((m - 69) / 12)
    bgm = np.zeros(N, np.float32)
    for b in range(int(T / bar) + 1):
        ch = chords[(b // 2) % 4]; t0 = b * bar
        for m in ch:
            x = (saw(mf(m), bar) + saw(mf(m) * 1.004, bar)) * 0.5
            e = np.minimum(1, np.arange(len(x)) / (0.3 * SR)) * np.minimum(1, (len(x) - np.arange(len(x))) / (0.3 * SR))
            add(bgm, x * e, t0, 0.035)
        for k in range(4):
            add(bgm, sine(mf(ch[0] - 24), beat * 0.9) * env(int(beat * 0.9 * SR), 0.005, 0.25), t0 + k * beat, 0.22)
        arp = [ch[0] + 12, ch[1] + 12, ch[2] + 12, ch[1] + 12]
        for k in range(8):
            m = arp[k % 4]
            add(bgm, (sine(mf(m), 0.4) + 0.3 * sine(mf(m) * 2, 0.4)) * env(int(0.4 * SR), 0.002, 0.12), t0 + k * beat / 2, 0.06)
        for k in range(4):
            n = int(0.35 * SR); tt = np.arange(n) / SR; f = 50 + 90 * np.exp(-tt * 30)
            add(bgm, np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 9), t0 + k * beat, 0.35)
            if k in (1, 3):
                add(bgm, rng.standard_normal(int(0.18 * SR)) * env(int(0.18 * SR), 0.001, 0.05), t0 + k * beat, 0.08)
        for k in range(8):
            add(bgm, np.diff(rng.standard_normal(int(0.05 * SR) + 1)) * env(int(0.05 * SR), 0.001, 0.015), t0 + k * beat / 2, 0.05 if k % 2 else 0.03)
    bgm *= np.minimum(1, np.arange(N) / SR) * np.clip((T - np.arange(N) / SR) / 2.5, 0, 1)
    w = int(0.05 * SR); ve = np.sqrt(np.convolve(voice ** 2, np.ones(w) / w, "same")); ve /= ve.max() + 1e-9
    duck = np.convolve(np.clip(ve * 6, 0, 1), np.ones(int(0.15 * SR)) / int(0.15 * SR), "same"); bgm *= 1 - 0.55 * duck

    # --- SFX
    def whoosh():
        n = int(0.45 * SR); x = rng.standard_normal(n); tt = np.arange(n) / n; y = np.zeros(n); a = 0.0
        for i in range(n):
            c = 0.02 + 0.5 * tt[i] ** 2; a += c * (x[i] - a); y[i] = a
        return y * np.sin(np.pi * tt) ** 2 * 1.5

    def pop():
        n = int(0.12 * SR); tt = np.arange(n) / SR; return np.sin(2 * np.pi * (700 + 900 * np.exp(-tt * 40)) * tt) * np.exp(-tt * 35)

    def thud():
        n = int(0.5 * SR); tt = np.arange(n) / SR
        return np.sin(2 * np.pi * (60 + 120 * np.exp(-tt * 25)) * tt) * np.exp(-tt * 7) + 0.3 * rng.standard_normal(n) * np.exp(-tt * 30)

    def ding():
        return (sine(1318.5, 0.8) + 0.5 * sine(1975.5, 0.8)) * env(int(0.8 * SR), 0.002, 0.25)

    def coin():
        return np.concatenate([sine(1975.5, 0.07) * env(int(0.07 * SR), 0.001, 0.05), sine(2637, 0.4) * env(int(0.4 * SR), 0.001, 0.12)])

    S = {"whoosh": (whoosh(), 0.25), "pop": (pop(), 0.22), "thud": (thud(), 0.33), "ding": (ding(), 0.15), "coin": (coin(), 0.16)}
    sfx = np.zeros(N, np.float32)
    byid = {s["id"]: s for s in tl["scenes"]}
    add(sfx, S["whoosh"][0], (tl["pre"] - 2) / FPS, 0.3)
    add(sfx, S["pop"][0], (tl["pre"] + 2) / FPS, 0.25)
    for i, s in enumerate(spec["scenes"]):
        sc = byid[s["id"]]
        if i > 0:
            add(sfx, S["whoosh"][0], sc["start"] / FPS - 0.1, S["whoosh"][1])
        for ev in s.get("sfx", []):          # [chunk_index, type, frame_offset?]
            k, typ = ev[0], ev[1]; off = ev[2] if len(ev) > 2 else 0
            v = sc["subs"][min(k, len(sc["subs"]) - 1)]["v"] + off
            x, g = S[typ]; add(sfx, x.astype(np.float32), v / FPS, g)
    add(sfx, S["pop"][0], tl["followAt"] / FPS, 0.22)
    add(sfx, S["ding"][0], (tl["followAt"] + 36) / FPS, 0.2)

    meter = pyln.Meter(SR)
    norm = lambda x, l: x * 10 ** ((l - meter.integrated_loudness(x)) / 20)
    mix = norm(voice, -19) + norm(bgm, -32) + norm(sfx, -29)
    lim = 10 ** (-1.6 / 20)

    def limit(x):
        e = maximum_filter1d(np.abs(x), int(0.006 * SR)); g = np.minimum(1, lim / (e + 1e-9))
        g = minimum_filter1d(g, int(0.01 * SR)); g = uniform_filter1d(g, int(0.006 * SR))
        return np.clip(x * g, -lim, lim)

    for _ in range(3):
        mix = limit(norm(mix, -14))
    sf.write(os.path.join(proj, "build", "mix.wav"), np.stack([mix, mix], 1).astype(np.float32), SR)
    print(f"mix: {meter.integrated_loudness(mix):.1f} LUFS, peak {20 * np.log10(np.max(np.abs(mix))):.1f} dBFS")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(0)
    c = a[0]
    if c == "new":
        cmd_new(a[1], "--example" in a)
    elif c == "brand":
        tg = a[a.index("--tagline") + 1] if "--tagline" in a else None
        av = a[a.index("--avatar") + 1] if "--avatar" in a else None
        cmd_brand(a[1], tg, av)
    elif c == "avatar":
        cmd_avatar(a[1], a[2])
    elif c == "check":
        sys.exit(0 if cmd_check(a[1]) else 1)
    elif c == "voicekit":
        cmd_voicekit(a[1], a[2])
    elif c == "timeline":
        cmd_timeline(a[1], a[2] if len(a) > 2 else None)
    elif c == "mix":
        cmd_mix(a[1])
    else:
        print(__doc__); sys.exit(1)
