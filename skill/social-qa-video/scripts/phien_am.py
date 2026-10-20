"""Phien am tu tieng Anh trong truong `speak` de edge-tts doc dung giong Viet.

  python phien_am.py content.json            # sua tai cho, in ra thay doi
  python phien_am.py content.json --check    # chi xem, khong ghi

Chi dung tren `speak` (loi doc). KHONG dung tren text hien thi, va khong
dung cho anh chup — anh giu nguyen chu goc.
"""
import json
import re
import sys

# Khong phan biet hoa thuong. Tu dai duoc thay truoc tu ngan (sap xep o duoi),
# nen "Shopee" khong bi "shop" an mat, "livestream" khong bi "live" an mat.
PHIEN_AM = {
    "KOC": "cây âu xi",
    "KOCs": "cây âu xi",
    "KOL": "cây âu eo",
    "KOLs": "cây âu eo",
    "influencer": "in phờ lu en sờ",
    "followers": "pho lâu ơ",
    "follower": "pho lâu ơ",
    "follow": "pho lâu",
    "booking": "búc king",
    "book": "búc",
    "TikToker": "Tích Tóc cờ",
    "TikTok Shop": "Tích Tóc Sốp",
    "TikTok": "Tích Tóc",
    "brand": "bờ ren",
    "agency": "ây giừn xi",
    "labels": "lây bồ",
    "label": "lây bồ",
    "data": "đây ta",
    "ads": "át",
    "views": "viu",
    "view": "viu",
    "flop": "phờ lóp",
    "check": "chếch",
    "food": "phút",
    "buff": "bấp",
    "bro": "brô",
    "freeship": "phri síp",
    "voucher": "vao chờ",
    "livestream": "lai sờ trim",
    "live": "lai",
    "Shopee": "Sô pi",
    "shop": "sốp",
    "Lazada": "La da da",
    "mall": "mon",
    "website": "quép sai",
    "email": "i meo",
    "mail": "meo",
    "marketing": "ma két ting",
    "content": "con tần",
    "traffic": "tráp phích",
    "seller": "sen lơ",
    "seeding": "si đing",
    "budget": "bát giệt",
    "engagement": "en gây giừ mừn",
}


def doi(s):
    thay = []
    # tu dai truoc: tranh "shop" an mat "Shopee", "live" an mat "livestream"
    for tu in sorted(PHIEN_AM, key=len, reverse=True):
        am = PHIEN_AM[tu]
        # bien tu nguyen ven, khong phan biet hoa thuong
        pat = r"(?<![0-9A-Za-zÀ-ỹ])" + re.escape(tu) + r"(?![0-9A-Za-zÀ-ỹ])"
        s2, n = re.subn(pat, am, s, flags=re.IGNORECASE)
        if n:
            thay.append(f"{tu}->{am} x{n}")
            s = s2
    return s, thay


def main():
    path = sys.argv[1]
    chi_xem = "--check" in sys.argv
    data = json.load(open(path, encoding="utf-8"))

    tong = 0
    for i, c in enumerate(data.get("cards", []), 1):
        goc = c.get("speak", "")
        moi, thay = doi(goc)
        if thay:
            tong += len(thay)
            print(f"card{i:02d}: {', '.join(thay)}")
            c["speak"] = moi

    if not tong:
        print("Khong co tu nao can phien am.")
        return
    if chi_xem:
        print("\n(--check: khong ghi file)")
        return
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nDa sua {tong} cho trong {path}. Chay lai tts.py roi build_final.py.")


if __name__ == "__main__":
    main()
