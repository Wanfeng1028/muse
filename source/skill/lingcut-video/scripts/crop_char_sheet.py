"""把「角色定板图」裁成两张可做视频参考的图：大头照 + 全身照。

为什么需要这一步：
  官方视频模型指南明确——**不要用多角度定板图做视频参考**，
  模型会把不同角度当成多个主体，反而加剧角色漂移。
  正确做法是从定板图上裁出「大头照（定义身份）」和「全身照（定义比例/服装）」分开上传。

用法:
  python crop_char_sheet.py <定板图> <输出目录> [前缀]
产物:
  <前缀>_大头照.png   从中间的正脸特写裁
  <前缀>_全身照.png   从左侧的正面全身裁
  <前缀>_联络图.jpg   三图并排，方便肉眼核对裁得对不对
"""
import sys, os
from PIL import Image, ImageDraw

# 定板图的标准排版（比例，可通过 --debug 出来的联络图微调）
REGIONS = {
    "大头照": (0.360, 0.00, 0.660, 0.92),   # 中间：正脸特写
    "全身照": (0.010, 0.00, 0.172, 0.97),   # 左侧：正面全身（A字站姿），右边界留出余量避免切到背面视图
}


def crop(src, outdir, prefix):
    im = Image.open(src).convert("RGB")
    W, H = im.size
    os.makedirs(outdir, exist_ok=True)
    made = {}
    for name, (x0, y0, x1, y1) in REGIONS.items():
        box = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))
        part = im.crop(box)
        # 长边统一到 1024，方便当参考图
        scale = 1024 / max(part.size)
        if scale < 1:
            part = part.resize((int(part.width * scale), int(part.height * scale)), Image.LANCZOS)
        p = os.path.join(outdir, f"{prefix}_{name}.png")
        part.save(p)
        made[name] = p
        print(f"OK  {name}  {part.size[0]}x{part.size[1]}  {p}")

    # 联络图：原图 + 两张裁图并排，肉眼核对
    thumbs = [im] + [Image.open(p) for p in made.values()]
    th = 360
    thumbs = [t.resize((int(t.width * th / t.height), th), Image.LANCZOS) for t in thumbs]
    total_w = sum(t.width for t in thumbs) + 20 * (len(thumbs) + 1)
    sheet = Image.new("RGB", (total_w, th + 40), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    x = 20
    for label, t in zip(["定板图(原)", *made.keys()], thumbs):
        sheet.paste(t, (x, 20))
        d.text((x, 6), label, fill=(230, 230, 230))
        x += t.width + 20
    sp = os.path.join(outdir, f"{prefix}_联络图.jpg")
    sheet.save(sp, quality=88)
    print(f"OK  联络图 -> {sp}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    crop(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "角色")
