"""Tai clip nen + nhac nen mien phi tu Mixkit vao assets/ cua skill.

Mixkit Free License: dung duoc ca thuong mai, khong can ghi cong.
Chay mot lan; lan sau tu bo qua file da co.

  python fetch_assets.py            # bo mac dinh (thien nhien + thanh pho)
  python fetch_assets.py city       # chi tai bo thanh pho
  python fetch_assets.py nature
"""
import os
import subprocess
import sys

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG_DIR = os.path.join(SKILL_DIR, "assets", "bg")
MUSIC_DIR = os.path.join(SKILL_DIR, "assets", "music")

# id video tren assets.mixkit.co/videos/<id>/<id>-1080.mp4
BG_SETS = {
    "nature": [3317, 22729, 50847, 4633, 18312],   # rung tuyet, rung mua, nui
    "city": [4451, 4308, 51502, 51445, 4332, 3428],  # tokyo dem, bien, hoang hon
}
MUSIC_IDS = [322, 148, 272]  # nhac khong loi, da kiem tra bang whisper


def get(url, out):
    if os.path.exists(out) and os.path.getsize(out) > 10000:
        print(f"  co san: {os.path.basename(out)}")
        return True
    r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-o", out, url],
                       capture_output=True, text=True)
    ok = os.path.exists(out) and os.path.getsize(out) > 10000
    print(f"  {'OK  ' if ok else 'LOI '} {os.path.basename(out)}")
    return ok


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else None
    sets = [which] if which in BG_SETS else list(BG_SETS)

    os.makedirs(BG_DIR, exist_ok=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)

    print("Tai clip nen (Mixkit, free ca thuong mai):")
    for name in sets:
        for vid in BG_SETS[name]:
            sub = os.path.join(BG_DIR, name)
            os.makedirs(sub, exist_ok=True)
            out = os.path.join(sub, f"{vid}.mp4")
            if not get(f"https://assets.mixkit.co/videos/{vid}/{vid}-1080.mp4", out):
                get(f"https://assets.mixkit.co/videos/{vid}/{vid}-720.mp4", out)

    print("\nTai nhac nen (Mixkit, khong loi):")
    for mid in MUSIC_IDS:
        get(f"https://assets.mixkit.co/music/{mid}/{mid}.mp3",
            os.path.join(MUSIC_DIR, f"mixkit_{mid}.mp3"))

    print(f"\nXong. Clip nen: {BG_DIR}\n      Nhac:     {MUSIC_DIR}")
    print("Muon chia bo nen theo chu de: dat BG_DIR=<thu muc> khi chay build_bg.py")


if __name__ == "__main__":
    main()
