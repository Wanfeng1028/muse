"""Tao giong doc tieng Viet bang edge-tts (mien phi)."""
import asyncio
import json
import os
import subprocess

import edge_tts

NU = "vi-VN-HoaiMyNeural"
NAM = "vi-VN-NamMinhNeural"
RATE = "+18%"


def voice_for(i, total):
    # nu dan chuyen o card mo dau va card ket, nam cho cac cau tra loi
    return NU if i == 1 or i == total else NAM


async def make(text, voice, out):
    comm = edge_tts.Communicate(text, voice, rate=RATE)
    await comm.save(out)


def dur(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


async def main():
    data = json.load(open("content.json", encoding="utf-8"))
    os.makedirs("voice", exist_ok=True)
    total = len(data["cards"])
    timings = []
    for i, card in enumerate(data["cards"], 1):
        out = f"voice/v{i:02d}.mp3"
        v = voice_for(i, total)
        await make(card["speak"], v, out)
        d = dur(out)
        timings.append({"index": i, "file": out, "voice": v, "dur": round(d, 3)})
        print(f"{out}  {d:6.2f}s  {v}")
    json.dump(timings, open("voice/timings.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"TONG THOI LUONG VOICE: {sum(t['dur'] for t in timings):.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
