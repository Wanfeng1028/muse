#!/usr/bin/env python
"""把目录里的图片拼成联络表，便于一次性审阅。

用法: python contact_sheet.py <图片目录> <输出.jpg> [每行张数] [单元格宽]

审图是这个流水线的强制步骤——生成完必须真的看一眼。
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

src = sys.argv[1]
out = sys.argv[2]
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 3
cell_w = int(sys.argv[4]) if len(sys.argv) > 4 else 560

files = sorted(f for f in os.listdir(src) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))
if not files:
    print('目录里没有图片:', src)
    sys.exit(1)

label_h = 32
cell_h = int(cell_w * 9 / 16)
rows = (len(files) + cols - 1) // cols
sheet = Image.new('RGB', (cols * cell_w, rows * (cell_h + label_h)), (24, 25, 27))
draw = ImageDraw.Draw(sheet)

font = None
for fp in ('C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/simhei.ttf'):
    if os.path.exists(fp):
        try:
            font = ImageFont.truetype(fp, 18)
            break
        except Exception:
            pass
if font is None:
    font = ImageFont.load_default()

for i, fn in enumerate(files):
    r, c = divmod(i, cols)
    x, y = c * cell_w, r * (cell_h + label_h)
    try:
        im = Image.open(os.path.join(src, fn)).convert('RGB').resize((cell_w, cell_h), Image.LANCZOS)
        sheet.paste(im, (x, y))
    except Exception as e:
        draw.text((x + 8, y + 8), f'读取失败 {fn}: {e}', fill=(255, 120, 120), font=font)
    draw.text((x + 8, y + cell_h + 5), fn, fill=(235, 235, 235), font=font)

sheet.save(out, quality=92)
print('saved', out, sheet.size, f'({len(files)} 张)')
