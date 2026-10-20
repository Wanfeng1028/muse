"""Trich bai dang + toan bo binh luan tieng Viet tu HTML Facebook da tai."""
import json
import re

VI = "ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụỳýỷỹỵ"
VI_SET = set(VI + VI.upper())

SKIP = (
    "Shopee người bán - Chia sẻ",
    "Hiển thị bình luận",
    "Có thể là hình vẽ",
    "<title>",
    "</script>",
    "Xem thêm",
    "Đăng nhập",
)


def vi_ratio(s):
    return sum(1 for c in s if c in VI_SET) / len(s) if s else 0


h = open("fb_Googlebot.html", encoding="utf-8", errors="ignore").read()

found = {}
for m in re.finditer(r'"text":"((?:[^"\\]|\\.){40,4000})"', h):
    raw = m.group(1)
    try:
        s = json.loads('"' + raw + '"')
    except Exception:
        continue
    if vi_ratio(s) > 0.04 and not any(k in s for k in SKIP):
        found[s.strip()] = m.start()

# du phong: quet moi chuoi JSON dai neu key "text" khong du
if len(found) < 3:
    for m in re.finditer(r'"((?:[^"\\]|\\.){40,4000})"', h):
        raw = m.group(1)
        try:
            s = json.loads('"' + raw + '"')
        except Exception:
            continue
        if vi_ratio(s) > 0.04 and " " in s and not any(k in s for k in SKIP):
            found.setdefault(s.strip(), m.start())

items = sorted(found.items(), key=lambda kv: kv[1])
print(f"TONG: {len(items)} doan\n")
for i, (s, pos) in enumerate(items, 1):
    print(f"--- [{i}] pos={pos} len={len(s)} ---")
    print(s)
    print()

with open("fb_raw.json", "w", encoding="utf-8") as f:
    json.dump([s for s, _ in items], f, ensure_ascii=False, indent=2)
