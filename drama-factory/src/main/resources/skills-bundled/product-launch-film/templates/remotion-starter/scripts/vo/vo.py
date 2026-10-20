#!/usr/bin/env python3
"""Narration generator (ElevenLabs TTS + optional STT check). Stdlib only; needs ffmpeg/ffprobe on PATH.

Needs ELEVENLABS_API_KEY in the environment. It is read from the environment only: never printed, logged,
written to a file, or passed on the command line.

  python3 scripts/vo/vo.py --voice <voice_id> --name <voice name> --model eleven_v4 --stitch --stt \
      --out vo-takes/take1 [--ids 01-s1,03-x] [--stability 0.4]

Reads src/vo-script.json ({"lines": [{"id", "start", "slot", "text"}]}; start/slot are absolute frames,
slot = the frame by which speech must end). Writes OUT/<id>.mp3 and OUT/manifest.json with durations,
speech onset/offset (ffmpeg silencedetect), whether each line fits its slot, and, with --stt, the
speech-to-text transcript (scribe_v1). Compare the transcript with the script: if the product name is
misheard, rewrite the line rather than respelling the name.
Square-bracket audio tags ([casual], [warm, confident]) are kept for eleven_v3/eleven_v4 and stripped for other models.
Characters are billed per request: audition on 1-2 lines, not the whole script.
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request, urllib.error, uuid

API = "https://api.elevenlabs.io/v1"
TAG_MODELS = ("eleven_v3", "eleven_v4")


def key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k:
        sys.exit("ELEVENLABS_API_KEY is not set")
    return k


def post(url, body, accept="audio/mpeg"):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"xi-api-key": key(), "Content-Type": "application/json", "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:600]}")


def stt(path):
    boundary = uuid.uuid4().hex
    data = open(path, "rb").read()
    parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"model_id\"\r\n\r\nscribe_v1\r\n".encode(),
             f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.mp3\"\r\nContent-Type: audio/mpeg\r\n\r\n".encode() + data + b"\r\n",
             f"--{boundary}--\r\n".encode()]
    req = urllib.request.Request(f"{API}/speech-to-text", data=b"".join(parts), method="POST",
                                 headers={"xi-api-key": key(), "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r).get("text", "")


def measure(path):
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                               capture_output=True, text=True).stdout.strip())
    log = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "silencedetect=noise=-42dB:d=0.12", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    onset = ends[0] if starts and starts[0] < 0.01 and ends else 0.0
    offset = starts[-1] if starts and (not ends or starts[-1] > ends[-1]) else dur
    pauses = sum(1 for s, e in zip(starts, ends) if s > onset + 0.01 and e < offset - 0.01)
    return dur, onset, offset, pauses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "vo-script.json"))
    ap.add_argument("--voice", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--model", default="eleven_v4")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="")
    ap.add_argument("--stability", type=float, default=0.4)
    ap.add_argument("--similarity", type=float, default=0.75)
    ap.add_argument("--style", type=float, default=None)
    ap.add_argument("--speed", type=float, default=None)
    ap.add_argument("--stitch", action="store_true", help="send previous_text/next_text (if the model supports it)")
    ap.add_argument("--stt", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args()
    lines = json.load(open(a.script))["lines"]
    want = [x for x in a.ids.split(",") if x]
    os.makedirs(a.out, exist_ok=True)
    tags_ok = a.model in TAG_MODELS
    clean = lambda t: t if tags_ok else re.sub(r"\[[^\]]*\]\s*", "", t)
    vs = {"stability": a.stability, "similarity_boost": a.similarity, "use_speaker_boost": True}
    if a.style is not None:
        vs["style"] = a.style
    if a.speed is not None:
        vs["speed"] = a.speed
    out, chars = [], 0
    for i, l in enumerate(lines):
        if want and l["id"] not in want:
            continue
        body = {"text": clean(l["text"]), "model_id": a.model, "voice_settings": vs}
        if a.seed is not None:
            body["seed"] = a.seed
        if a.stitch:
            if i > 0: body["previous_text"] = re.sub(r"\[[^\]]*\]\s*", "", lines[i - 1]["text"])
            if i + 1 < len(lines): body["next_text"] = re.sub(r"\[[^\]]*\]\s*", "", lines[i + 1]["text"])
        audio, hdr = post(f"{API}/text-to-speech/{a.voice}?output_format=mp3_44100_128", body)
        path = os.path.join(a.out, f"{l['id']}.mp3")
        open(path, "wb").write(audio)
        chars += len(body["text"])
        dur, on, off, pauses = measure(path)
        slot = (l["slot"] - l["start"]) / 60
        rec = {**l, "text_sent": body["text"], "file": f"audio/vo/{l['id']}.mp3", "seconds": round(dur, 3),
               "onset": round(on, 3), "offset": round(off, 3), "pauses": pauses, "fits": off <= slot}
        if a.stt:
            rec["stt"] = stt(path)
        out.append(rec)
        print(f"{l['id']:11s} {dur:5.2f}s speech {on:.2f}-{off:.2f} (slot {slot:.2f}s {'OK' if off <= slot else 'LONG'}) pauses {pauses}"
              + (f" | STT: {rec['stt']}" if a.stt else ""), flush=True)
    man = {"engine": "elevenlabs", "model": a.model, "voice_id": a.voice, "voice_name": a.name, "settings": vs,
           "stitch": a.stitch, "chars_sent": chars, "lines": out}
    json.dump(man, open(os.path.join(a.out, "manifest.json"), "w"), indent=2, ensure_ascii=False)
    print(f"chars sent: {chars}")


if __name__ == "__main__":
    main()
