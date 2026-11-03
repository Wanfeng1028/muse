"""Gom ảnh minh họa thật cho video Tabcom.

4 nguồn, chạy độc lập hoặc gọi hàm từ script khác:

  python 17_collect_platform_images.py play com.shopee.shopeeseller
  python 17_collect_platform_images.py page https://... slug-bai-viet
  python 17_collect_platform_images.py shot https://... ten-file
  python 17_collect_platform_images.py bing "màn hình shopee live" slug
  python 17_collect_platform_images.py sheet out/ten-thu-muc

Kết quả vào ./out/<slug>/ kèm _meta.json (URL ảnh + URL trang, để ghi nguồn trong README).
LUÔN chạy `sheet` rồi Read ảnh contact sheet trước khi chọn — không đoán theo tên file.
"""
import io, json, math, os, re, sys, time, urllib.parse, urllib.request
import html as H
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}
OUT = "out"


def fetch(url, timeout=40):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def _save(data, slug, idx, meta, extra):
    im = Image.open(io.BytesIO(data))
    ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(im.format, ".jpg")
    p = f"{OUT}/{slug}/{idx:02d}{ext}"
    open(p, "wb").write(data)
    meta.append(dict(file=p, size=list(im.size), **extra))
    return im


# ---------------------------------------------------------------- Google Play
def play_screens(package, crop=True):
    """Ảnh giới thiệu app trên Google Play. Nguồn chính thức, tiếng Việt, không cần login.

    Package đã dùng được: com.shopee.vn, com.shopee.shopeeseller (có màn "Hiệu quả bán
    hàng" với khung 7/30 ngày), com.tiktokshop.seller, com.zing.zalo, com.facebook.katana,
    com.zhiliaoapp.musically (TikTok, chỉ có bản tiếng Anh).
    Tìm package khác: https://play.google.com/store/search?q=<tên>&c=apps&hl=vi&gl=VN
    """
    slug = package
    os.makedirs(f"{OUT}/{slug}", exist_ok=True)
    url = f"https://play.google.com/store/apps/details?id={package}&hl=vi&gl=VN"
    html = fetch(url).decode("utf-8", "ignore")
    pat = re.compile(r"https://play-lh\.googleusercontent\.com/[\w\-]+=w(\d+)-h(\d+)[\w\-]*")
    bases, meta = [], []
    for m in pat.finditer(html):
        if int(m.group(1)) < 800:          # bỏ icon và logo nhà phát hành
            continue
        b = m.group(0).split("=")[0]
        if b not in bases:
            bases.append(b)
    for i, b in enumerate(bases, 1):
        try:
            im = _save(fetch(b + "=w2560"), slug, i, meta,
                       dict(img_url=b + "=w2560", page=url))
            if crop:
                crop_phone(f"{OUT}/{slug}/{i:02d}.png" if im.format == "PNG"
                           else f"{OUT}/{slug}/{i:02d}.jpg")
        except Exception:
            continue
    json.dump(meta, open(f"{OUT}/{slug}/_meta.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(slug, "->", len(meta), "ảnh")


def crop_phone(path, pad=8):
    """Cắt lấy khung điện thoại trong ảnh marketing Play (mockup sáng trên nền màu).

    Lấy vùng liên thông sáng lớn nhất: pixel sáng (max>200) và ít bão hòa (max-min<45).
    Ghi đè file gốc; ảnh nào cắt hỏng thì tải lại từ _meta.json.
    """
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(int)
    mx, mn = a.max(axis=2), a.min(axis=2)
    mask = ndimage.binary_closing((mx > 200) & ((mx - mn) < 45), structure=np.ones((9, 9)))
    lab, n = ndimage.label(mask)
    if not n:
        return
    idx = int(np.argmax(ndimage.sum(mask, lab, range(1, n + 1)))) + 1
    ys, xs = np.where(lab == idx)
    box = (max(0, xs.min() - pad), max(0, ys.min() - pad),
           min(a.shape[1], xs.max() + pad), min(a.shape[0], ys.max() + pad))
    im.crop(box).save(path)


# ------------------------------------------------------- ảnh trong bài viết web
def page_images(page_url, slug, minside=420, want=25):
    """Tải ảnh trong một bài hướng dẫn. Cách duy nhất lấy được giao diện Shopee Live,
    TikTok LIVE... vì shopee.vn trả 'Trang không khả dụng' và tiktok.com bắt captcha.

    Bài tiếng Việt có screenshot thật: shopee.vn/blog (chính thức, ưu tiên), misaeshop.vn,
    cellphones.com.vn/sforum, ghn.vn. KHÔNG lấy ảnh của đối thủ (tukigroup.vn).
    """
    os.makedirs(f"{OUT}/{slug}", exist_ok=True)
    html = fetch(page_url).decode("utf-8", "ignore")
    srcs = re.findall(r'(?:src|data-src|data-lazy-src|content)="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                      html, re.I)
    srcs += re.findall(r"(?:src|data-src)='([^']+\.(?:jpg|jpeg|png|webp)[^']*)'", html, re.I)
    seen, meta, got = set(), [], 0
    for s in srcs:
        u = urllib.parse.urljoin(page_url, s)
        if u in seen or got >= want:
            continue
        seen.add(u)
        try:
            data = fetch(u, 25)
            if min(Image.open(io.BytesIO(data)).size) < minside:
                continue
            got += 1
            _save(data, slug, got, meta, dict(img_url=u, page=page_url))
        except Exception:
            continue
    json.dump(meta, open(f"{OUT}/{slug}/_meta.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(slug, "->", got, "ảnh")


# ------------------------------------------------------------- chụp trang thật
def web_shot(url, name, mobile=True, wait=6):
    """Chụp trang công khai bằng Playwright + Chrome hệ thống.

    Chụp được: fanpage/group Facebook (popup đăng nhập tự tắt bằng Escape), oa.zalo.me,
    seller-vn.tiktok.com/university, website khách hàng.
    KHÔNG chụp được: shopee.vn, tiktok.com/shop, trang cần đăng nhập.
    """
    from playwright.sync_api import sync_playwright
    os.makedirs(f"{OUT}/shots", exist_ok=True)
    with sync_playwright() as p:
        # ms-playwright chưa cài browser riêng -> phải dùng Chrome hệ thống
        b = p.chromium.launch(headless=True, channel="chrome")
        ctx = b.new_context(
            viewport={"width": 430, "height": 932} if mobile else {"width": 1440, "height": 1600},
            device_scale_factor=2, locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh",
            is_mobile=mobile, has_touch=mobile,
            user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
                        "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1") if mobile
                       else UA["User-Agent"])
        pg = ctx.new_page()
        pg.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(wait)
        for sel in ('div[role="dialog"] div[aria-label="Đóng"]', '[aria-label="Close"]'):
            try:
                el = pg.query_selector(sel)
                if el:
                    el.click(); time.sleep(1.5); break
            except Exception:
                pass
        pg.keyboard.press("Escape"); time.sleep(1)
        pg.screenshot(path=f"{OUT}/shots/{name}.png")
        print(name, "OK |", pg.title()[:60], "|", pg.url[:90])
        b.close()


# ------------------------------------------------------------------ Bing image
def bing_images(query, slug, want=10, minside=500):
    """Tìm ảnh trên Bing (Google Images không lộ URL gốc trong HTML nữa).

    Bing hiểu kém query tiếng Việt trừu tượng ("biểu đồ doanh thu giảm" ra ảnh thể thao) —
    query phải cụ thể, hoặc dùng page_images() với bài hướng dẫn tìm bằng WebSearch.
    """
    os.makedirs(f"{OUT}/{slug}", exist_ok=True)
    meta, got = [], 0
    for first in (1, 36):
        url = "https://www.bing.com/images/search?q=" + urllib.parse.quote(query) + f"&first={first}"
        html = fetch(url).decode("utf-8", "ignore")
        for m in re.findall(r'm="(\{[^"]*?\})"', html):
            if got >= want:
                break
            try:
                d = json.loads(H.unescape(m))
                u = d.get("murl", "")
                if not u.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue
                data = fetch(u, 25)
                if min(Image.open(io.BytesIO(data)).size) < minside:
                    continue
                got += 1
                _save(data, slug, got, meta, dict(img_url=u, page=d.get("purl", ""), query=query))
            except Exception:
                continue
        if got >= want:
            break
    json.dump(meta, open(f"{OUT}/{slug}/_meta.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(slug, "->", got, "ảnh")


# ------------------------------------------------------------- soát bằng mắt
def contact_sheet(folder, out=None, cols=5, tw=300):
    """Ghép mọi ảnh trong folder thành 1 sheet có nhãn tên file để Read một lần."""
    files = [os.path.join(folder, f) for f in sorted(os.listdir(folder))
             if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
    th = []
    for f in files:
        try:
            im = Image.open(f).convert("RGB"); im.thumbnail((tw, tw * 2)); th.append((f, im))
        except Exception:
            pass
    if not th:
        print("không có ảnh trong", folder); return
    rh = max(t.height for _, t in th) + 20
    sh = Image.new("RGB", (cols * tw, math.ceil(len(th) / cols) * rh), "white")
    d = ImageDraw.Draw(sh)
    for i, (f, t) in enumerate(th):
        x, y = (i % cols) * tw, (i // cols) * rh
        sh.paste(t, (x, y + 16)); d.text((x + 2, y + 3), os.path.basename(f)[:44], fill="black")
    out = out or os.path.join(folder, "_contact.png")
    sh.save(out); print(out, sh.size, len(th), "ảnh")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"play": play_screens, "page": page_images, "shot": web_shot,
     "bing": bing_images, "sheet": contact_sheet}[cmd](*args)
