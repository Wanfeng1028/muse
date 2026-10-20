"""Loc binh luan that cua bai Threads goc: dung ngay 28-30/07/2026, bo spam."""
import json
import re

SPAM = (
    "s.shopee.vn", "shopee_vn", "sansale", "dung_ecom", "trolythue", "topshoppingvn",
    "shintrasua", "bbi.20.12", "xxkimanhxx", "Nhập mã", "voucher 30%", "Mã:",
    "MBTHREADS", "nhận xây shop", "livestream", "Theo Dõi", "Bấm ", "🔥 SHOP",
    "Tổng hợp mã", "TẶNG SẴN", "lyn.traveller", "_zawncunn", "Hiện xám",
)
BAD_WORDS = ("con L ", "óc c", "đ bt", "câm")


def ok_date(t):
    return bool(re.search(r"(28|29|30)/07/2026", t))


def clean(t):
    # bo dong ten + ngay o dau, bo so luot o cuoi
    parts = [p.strip() for p in t.split("\n") if p.strip()]
    body = []
    for p in parts:
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", p):
            continue
        if re.fullmatch(r"[\d.,]+K?", p):
            continue
        body.append(p)
    return body


rows = json.load(open("shot/threads_all.json", encoding="utf-8"))
keep = []
seen = set()
for r in rows:
    t = r["text"]
    if not ok_date(t):
        continue
    if any(s in t for s in SPAM) or any(b in t for b in BAD_WORDS):
        continue
    body = clean(t)
    if len(body) < 2:
        continue
    name = body[0]
    content = " ".join(body[1:])
    if len(content) < 40 or content in seen:
        continue
    seen.add(content)
    keep.append({"name": name, "len": len(content), "content": content, "raw": t})

keep.sort(key=lambda x: -x["len"])
print(f"{len(keep)} binh luan thuoc bai goc\n")
for k in keep:
    print(f"--- {k['name']} ({k['len']} chu) ---")
    print(k["content"][:400])
    print()

json.dump(keep, open("shot/threads_keep.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
