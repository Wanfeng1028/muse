"""Read back every caption chip and the headline from the RENDERED reel with Vision OCR.
Usage: python3 chip_readback.py <reel.mp4> <overlay_dir> <work_dir> [variant]
For each chip: decode its middle frame, crop the chip's ink box (plus 20 px), OCR, compare.
Only the needed frames are decoded, fresh from <reel.mp4> on every run (a cache keyed on the work
dir once read back a different render). Exit 0 when every chip matches (Futura's capital I read as
l counts as a match, it is an OCR confusion), 3 when any chip does not."""
import json, re, shutil, subprocess, sys
from pathlib import Path
from PIL import Image
reel, od, wd = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
wd.mkdir(parents=True, exist_ok=True)
chips = json.load(open(od / "chips.json"))
audit = json.load(open(od / "audit.json"))
fr = audit["frames"]
hf = 40
mids = [(c["f0"] + c["f1"] - 1) // 2 for c in chips]
need = sorted(set(mids + [hf]))
alld = wd / "frames"
shutil.rmtree(alld, ignore_errors=True)
alld.mkdir()
expr = "+".join(f"eq(n\\,{f})" for f in need)
subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", reel, "-map", "0:v:0", "-vf", f"select={expr}", "-fps_mode", "passthrough",
                "-frames:v", str(len(need)), str(alld / "s_%05d.png")], check=True)
got = sorted(alld.glob("s_*.png"))
assert len(got) == len(need), (len(got), len(need))
for f, g in zip(need, got):
    g.rename(alld / f"f_{f:05d}.png")
crops = []
for k, c in enumerate(chips):
    f = mids[k]
    b = fr[f]["chip_box"]
    im = Image.open(alld / f"f_{f:05d}.png").convert("RGB")
    cr = im.crop((int(b[0]) - 20, int(b[1]) - 20, int(b[2]) + 20, int(b[3]) + 20))
    cr = cr.resize((cr.width * 2, cr.height * 2))
    p = wd / f"chip_{k:03d}.png"; cr.save(p); crops.append((k, f, p))
V = int(sys.argv[4]) if len(sys.argv) > 4 else 1  # which headline variant this reel carries (H1 = 1)
hb = fr[hf]["headline_boxes"][V - 1] if "headline_boxes" in fr[hf] else fr[hf]["headline_box"]
im = Image.open(alld / f"f_{hf:05d}.png").convert("RGB")
hp = wd / "headline.png"; im.crop(tuple(int(v) for v in hb)).save(hp)
out = subprocess.run([str(Path(__file__).parent / "ocr")] + [str(p) for _, _, p in crops] + [str(hp)], capture_output=True, text=True, check=True).stdout
read = {}
for line in out.splitlines():
    path, _, txt = line.partition("\t")
    read[Path(path).name] = txt
n = lambda s: re.sub(r"[^A-Z0-9/$%']", "", s.upper().replace("’", "'"))
bad, il = [], []
for k, f, p in crops:
    got = read.get(p.name, "")
    if n(got) != n(chips[k]["text"]):
        (il if n(got).replace("L", "I") == n(chips[k]["text"]).replace("L", "I") else bad).append((k, f, chips[k]["text"], got))
print(f"chips read back: {len(crops) - len(bad) - len(il)} of {len(crops)} exact (normalised: letters, digits, / $ % '), "
      f"{len(il)} more exact up to the Futura I/l OCR confusion, {len(bad)} mismatched")
for k, f, want, got in il + bad:
    print(f"  chip {k} frame {f}: rendered {want!r}  OCR {got!r}")
print(f"headline OCR at frame {hf}: {read.get('headline.png')!r}")
sys.exit(3 if bad else 0)
