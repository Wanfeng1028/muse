#!/usr/bin/env python3
"""
ElevenLabs helpers for Explainer Video.

Reads the API key from $ELEVENLABS_API_KEY or a .env file in the current dir.

Usage:
  # Voiceover, one clip per scene, WITH word timestamps (for syncing 3D lifts):
  #   script.json = [{"id":"intro","text":"..."}, ...]
  python3 elevenlabs.py tts script.json out_dir --voice <voice_id>
  #   -> out_dir/NN_id.mp3, out_dir/durations.json, out_dir/alignments.json
  #   then concatenate the clips into one gap-free track yourself (ffmpeg concat).

  # Background music (one file, full length):
  python3 elevenlabs.py music "ambient minimal tech ..." out.mp3 --ms 161000

  # One sound effect clip (min duration 0.5s):
  python3 elevenlabs.py sfx "soft cinematic whoosh" out.mp3 --seconds 0.9

  # List available voices:
  python3 elevenlabs.py voices
"""
import sys, os, json, base64, urllib.request, urllib.error, subprocess, argparse

API = "https://api.elevenlabs.io/v1"

def key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    if not k and os.path.exists(".env"):
        for line in open(".env"):
            if line.startswith("ELEVENLABS_API_KEY="):
                k = line.split("=", 1)[1].strip()
    if not k:
        sys.exit("ELEVENLABS_API_KEY not set (env or .env)")
    return k

def post(url, body, raw=False):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"xi-api-key": key(), "Content-Type": "application/json"}, method="POST")
    r = urllib.request.urlopen(req, timeout=300)
    return r.read() if raw else json.load(r)

def dur(path):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries",
        "format=duration","-of","default=noprint_wrappers=1:nokey=1", path]).strip())

def cmd_voices(_):
    req = urllib.request.Request(f"{API}/voices", headers={"xi-api-key": key()})
    for v in json.load(urllib.request.urlopen(req)).get("voices", []):
        lbl = v.get("labels", {})
        print(f"{v['voice_id']}  {v['name']:<20} {lbl.get('gender','?'):<7} {lbl.get('accent','')}")

def cmd_tts(a):
    scenes = json.load(open(a.script))
    os.makedirs(a.out, exist_ok=True)
    durs, aligns = {}, {}
    for i, s in enumerate(scenes, 1):
        fn = os.path.join(a.out, f"{i:02d}_{s['id']}.mp3")
        body = {"text": s["text"], "model_id": a.model,
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.8,
                                   "style": 0.0, "use_speaker_boost": True}}
        url = f"{API}/text-to-speech/{a.voice}/with-timestamps?output_format=mp3_44100_128"
        try:
            res = post(url, body)
        except urllib.error.HTTPError as e:
            sys.exit(f"TTS failed for {s['id']}: {e.code} {e.read()[:200]}")
        open(fn, "wb").write(base64.b64decode(res["audio_base64"]))
        al = res["alignment"]
        aligns[s["id"]] = {"chars": al["characters"], "start": al["character_start_times_seconds"]}
        durs[s["id"]] = round(dur(fn), 2)
        print(f"  {fn}  {durs[s['id']]}s")
    json.dump(durs, open(os.path.join(a.out, "durations.json"), "w"))
    json.dump(aligns, open(os.path.join(a.out, "alignments.json"), "w"))
    print("TOTAL", round(sum(durs.values()), 1), "s")
    print("Tip: find a keyword's start time with alignments.json to set CUES.")

def cmd_music(a):
    open(a.out, "wb").write(post(f"{API}/music?output_format=mp3_44100_128",
        {"prompt": a.prompt, "music_length_ms": a.ms}, raw=True))
    print(a.out, round(dur(a.out), 1), "s")

def cmd_sfx(a):
    secs = max(0.5, a.seconds)  # API minimum is 0.5s
    open(a.out, "wb").write(post(f"{API}/sound-generation",
        {"text": a.prompt, "duration_seconds": secs, "prompt_influence": 0.55}, raw=True))
    # warn if silent
    try:
        out = subprocess.run(["ffmpeg","-i",a.out,"-af","volumedetect","-f","null","-"],
                             capture_output=True, text=True).stderr
        mx = [l for l in out.splitlines() if "max_volume" in l]
        print(a.out, mx[0].split("]")[-1].strip() if mx else "")
        if mx and float(mx[0].split("max_volume:")[1].split("dB")[0]) < -30:
            print("  WARNING: near-silent clip — regenerate with a clearer prompt.")
    except Exception:
        print(a.out, "written")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="c", required=True)
    sp = sub.add_parser("tts"); sp.add_argument("script"); sp.add_argument("out")
    sp.add_argument("--voice", required=True); sp.add_argument("--model", default="eleven_multilingual_v2")
    sp.set_defaults(f=cmd_tts)
    sp = sub.add_parser("music"); sp.add_argument("prompt"); sp.add_argument("out")
    sp.add_argument("--ms", type=int, default=160000); sp.set_defaults(f=cmd_music)
    sp = sub.add_parser("sfx"); sp.add_argument("prompt"); sp.add_argument("out")
    sp.add_argument("--seconds", type=float, default=1.0); sp.set_defaults(f=cmd_sfx)
    sp = sub.add_parser("voices"); sp.set_defaults(f=cmd_voices)
    a = p.parse_args(); a.f(a)
