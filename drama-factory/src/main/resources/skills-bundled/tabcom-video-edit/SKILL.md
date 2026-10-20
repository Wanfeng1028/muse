---
name: tabcom-video-edit
description: Edit video dọc (9:16) cho Tabcom từ source người nói + asset minh họa, bằng pipeline ffmpeg + Pillow. Dùng khi người dùng gửi video source vào folder "Tabcom edit video" và muốn "edit video", "dựng video", "làm video mới", "cắt video", "edit vid", hoặc yêu cầu chỉnh sửa/render lại một bản draft video Tabcom. Bao gồm bóc timestamp lời thoại, tách nền người bằng AI, dựng cảnh chữ có animation, chèn ảnh minh họa liên tục, logo thật, zoom punch, flash chuyển cảnh và sound effect.
---

# Tabcom video edit — pipeline dựng video dọc

Dựng video bằng **code (ffmpeg + Pillow render từng frame)**, không dùng CapCut để dựng. Người dùng chỉ chèn nhạc nền trong CapCut sau khi nhận file — **caption do pipeline dựng luôn** (chốt 18/08/2026).

Thông số chuẩn: **1080×1920, 25fps, H.264 crf 19, giữ nguyên trọn lời thoại của source**. Nối `OUTRO TABCOM` vào cuối (convert 30fps→25fps rồi concat).

## Bước 0 — Đọc trước khi làm

1. `tai-lieu/Phan-tich-video-mau.md` (trong skill này) — phân tích video mẫu, 5 kiểu cảnh chuẩn.
2. `tai-lieu/quy-tac-video-tabcom.md` (trong skill này) — quy ước logo thương hiệu, quy ước lưu
   output, quy ước thu thập ảnh minh họa. Bắt buộc đọc trước khi gom asset.

Nội dung pháp lý/chính sách: asset phải trích từ **văn bản gốc hoặc nguồn chính thức**, ghi tên văn bản dưới ảnh.

## Chuẩn bị (chỉ làm 1 lần trên mỗi máy)

Asset cố định (font, nền, card gradient, OUTRO, logo sàn, sticker mẫu) nằm sẵn trong
`assets/` của skill này — không cần tải gì thêm. Kiểm tra bằng:

```bash
python scripts/tabcom_paths.py     # in ra bảng OK/THIẾU cho từng asset
```

Môi trường cần có: xem `cai-dat/README-cai-dat.md` trong gói (ffmpeg, python + rembg, faster-whisper,
Playwright). Thiếu thư viện thì báo người dùng cài trước, đừng tự chế đường vòng.

## Đầu vào

Mỗi video là một thư mục `yy.mm.dd - Tên video/` chứa file source người nói. Chỉ định qua biến
môi trường, **không hardcode đường dẫn vào script**:

```bash
# PowerShell
$env:TABCOM_SRC    = "D:\Video\26.08.20 - Ten video\source.mp4"     # file source người nói
$env:TABCOM_OUT    = "D:\Video\26.08.20 - Ten video\26.08.20 - Ten video (draft v1).mp4"
$env:TABCOM_ASSETS = "D:\Video\26.08.20 - Ten video\assets"          # ảnh minh họa riêng video này
```

Mọi script đọc đường dẫn từ `scripts/tabcom_paths.py`:

| Biến | Trỏ tới | Ghi chú |
|---|---|---|
| `P.FIX` | `assets/co-dinh/` | Nền, card gradient cảnh split, OUTRO, logo nền sáng |
| `P.LOGO` | `assets/logo/` | Logo Shopee, TikTok, Facebook, Zalo đã tách nền — thêm mới thì lưu vào đây |
| `P.FONTS` | `assets/fonts/ps-display/` | `PS Anton - Regular V1.0.otf` (chữ lớn), `Big Shoulders ExtraBold Viet Hoa.otf` (dòng phụ). **Cỡ chữ nhân 1.22** vì font condensed |
| `P.STICKERS` | `assets/stickers/` | Sticker, badge sàn, PNG flash mẫu |
| `P.src()` / `P.out_file()` | `TABCOM_SRC` / `TABCOM_OUT` | Báo lỗi rõ nếu chưa set |
| `P.assets()` | `TABCOM_ASSETS` | Ảnh minh họa riêng của video đang dựng |
| `P.work()` | `./build` hoặc `TABCOM_WORK` | Nơi ghi frame, clip, mask trung gian |

## Bước 1 — Bóc timestamp lời thoại (bắt buộc)

```bash
ffmpeg -i "source....mp4" -ac 1 -ar 16000 audio.wav
```
faster-whisper model `small`, `language='vi'`, `word_timestamps=True`, `vad_filter=True`.

Whisper nhận sai tên riêng ("shop"→"SOAP", "Tabcom"→"TAPCOM", "Shopee"→"Soppy") — bỏ qua, chỉ cần mốc thời gian. Lập bảng: mốc → ý đang nói → cảnh dự kiến.

## Bước 2 — Gom ảnh (BẮT BUỘC, quyết định chất lượng video)

Yêu cầu cứng của người dùng: **ảnh phải liên tục, mọi màn đều có hình**, không màn nào chỉ có chữ trơn. Một video ~115 giây cần **25–30 hình**.

Nguồn theo thứ tự:
1. Asset session gom sẵn trong thư mục `TABCOM_ASSETS` của video (`P.assets()`) — **dùng cho hết**, đừng bỏ phí.
2. Ảnh giao diện sàn/app: `scripts/17_collect_platform_images.py` — xem SOP bên dưới.
3. Ảnh stock miễn phí: chạy `scripts/16_get_stock_photos.mjs` (Playwright + Chrome).
   - **Pexels bị Cloudflare chặn** ("Just a moment...") — đừng mất thời gian.
   - **Unsplash và Pixabay scrape được**. Wikimedia chỉ hợp để lấy **logo**, không hợp ảnh stock.
4. Illustration người bán / ảnh generated (tùy chọn): đặt trong `<VIDEO_ROOT>/tai-nguyen/carousel-hook-video-ban-hang/`
   và `<VIDEO_ROOT>/tai-nguyen/generated-carousel/`, gọi bằng `P.extra("...")`. Không có cũng dựng được.

**Kiểm ảnh trước khi dùng — người dùng bắt lỗi này:** mở xem ảnh thật sự vẽ gì. Ví dụ đã mắc: ảnh biểu đồ nến chứng khoán bị dùng cho "dashboard ads" (sai), ảnh cổng sạc điện thoại dùng cho CTA comment (không liên quan). Ảnh sai ngữ cảnh thì bỏ, không chèn cho đủ số lượng.

### SOP tìm ảnh giao diện sàn (Shopee, TikTok Shop, Zalo, Facebook)

Nội dung nhắc tính năng nào của sàn thì phải có ảnh giao diện thật của đúng tính năng đó. Bốn nguồn, chạy bằng `scripts/17_collect_platform_images.py`:

| Cần gì | Lệnh | Ghi chú |
|---|---|---|
| Giao diện app (người mua và người bán) | `play <package>` | Nguồn chính thức, tiếng Việt, tự crop khung điện thoại |
| Giao diện không mở được bằng bot (Shopee Live, TikTok LIVE) | `page <url-bài-hướng-dẫn> <slug>` | Tìm bài trước bằng WebSearch |
| Trang web công khai (fanpage, group, Zalo OA, Academy, website) | `shot <url> <tên>` | Playwright + Chrome hệ thống |
| Ảnh minh họa chung | `bing "<query>" <slug>` | Query phải cụ thể |

Package Play đã dùng được: `com.shopee.vn` · `com.shopee.shopeeseller` (có màn **Hiệu quả bán hàng** với khung 7/30 ngày — ảnh chuẩn cho mọi câu "mở phần phân tích, xem 30 ngày") · `com.tiktokshop.seller` · `com.zing.zalo` · `com.facebook.katana`.

Đã thử và **chặn**, đừng mất thời gian: `shopee.vn` (trả "Trang không khả dụng"), `tiktok.com/shop` và trang cá nhân TikTok (captcha), API `banhang.shopee.vn` và Shopee Uni/TikTok Academy dạng SPA (WebFetch/curl chỉ ra khung rỗng, API cần token đăng nhập), Google Images (HTML không còn URL ảnh gốc — dùng Bing).

Bài tiếng Việt có screenshot thật dùng lại được: `shopee.vn/blog` (chính thức, ưu tiên), `misaeshop.vn`, `cellphones.com.vn/sforum`, `ghn.vn`. **Không lấy ảnh của đối thủ** (`tukigroup.vn`).

Sau khi gom: chạy `sheet out/<slug>` rồi Read contact sheet để chọn — không chọn theo tên file.

### Bàn giao asset kèm README (bắt buộc)

Trong thư mục asset của video (`TABCOM_ASSETS`) phải có `README.md` gồm: ảnh nào cho đoạn nào của kịch bản · URL ảnh + URL trang + ngày lấy · những gì chưa lấy được · lưu ý khi dựng. Kèm `_preview-all.png` (contact sheet) để người dùng duyệt nhanh.

Ba điều luôn phải ghi và làm:
- Số liệu trong ảnh app là **số mẫu của nhà phát hành** — không đọc thành số liệu, không dùng như bằng chứng kết quả.
- Ảnh có **tên tài khoản, tên shop, tên người bình luận** → crop bỏ hoặc làm mờ trước khi lên video.
- Số liệu shop tụt/biểu đồ nguồn traffic: **không đi tìm ảnh dashboard để giả làm dữ liệu thật**, cũng
  **không dán nhãn "minh họa"** lên màn (xem mục "Không dùng nhãn minh họa").

## Bước 3 — Tách nền người cho cảnh split

**Bài học quan trọng:** phương án gate (birefnet trên frame mẫu + isnet từng frame) **không đủ sạch** — union mask qua nhiều frame vẫn nuốt vật thể nền cạnh đầu (ngôi sao cúp, lá cây, mép ghế), và bước "làm tối vùng sáng" chỉ biến chúng thành khối đen xấu hơn.

Cách đúng:
- **Giữ cửa sổ split ngắn (≤ 4 giây)**. Đoạn dài hơn thì chuyển thành **màn asset full màn** (ảnh còn to, dễ đọc hơn).
- Chạy `scripts/15_cutout_birefnet.py`: `birefnet-portrait` **từng frame** (~17 s/frame; 90 frame ≈ 25 phút). Đây là cách duy nhất cho viền tóc sạch tuyệt đối.
- Cắt frame: `crop=940:1040:70:340` (kiểm lại bằng `drawgrid` cho từng source).

Bố cục cảnh split đã duyệt:
- Card gradient **800×690 đặt tại (140, 1226)** — tâm khung.
- Người `scale=760:842`, `overlay=160:1074` — **đúng tâm**, chân chạm mép dưới.
- **Chừa trống nửa trên khung** cho caption. Chỉ đặt nhãn nhỏ góc trái + 1 ảnh + 1 capsule.
- **Dùng bố cục này nhiều lần trong video, không chỉ ở CTA cuối** — người dùng yêu cầu đa dạng
  (18/08/2026). Khi lên kế hoạch phải tính trước chi phí cutout: `birefnet-portrait` chạy
  **~50 giây/frame** trên máy này, tức mỗi giây split tốn ~21 phút. 3–4 cửa sổ × 2,5–3 giây là
  khoảng 4 tiếng — chạy nền và làm việc khác trong lúc chờ, đừng để dồn vào phút cuối.

## Bước 4 — Dựng cảnh

`scripts/10_scene_helpers.py` (Layer, capsule, textimg, icon, render) + `11_scenes_images.py` (ảnh trong mọi màn) + `12_layout_archetypes.py` (bố cục đa dạng).

### Hiệu ứng chữ — phải đa dạng, đánh trúng nhịp nói
`pop` (ease-out-back), `slide`, `wipe`, `slideL`/`slideR` (xen kẽ tạo nhịp zig-zag), `blurin` (cho ảnh), `flip` (co giãn ngang), `shakein` (capsule cảnh báo), `none` (hiện sẵn, không animation), `float` (lơ lửng rung nhẹ), `fly` (bay từ A tới B), `TypeLayer` (gõ chữ cho hook/CTA), `CountLayer` (đếm số, ví dụ 0→50%, kèm boom khi số dừng), `MarkerLayer` (bút highlight quét nền sau chữ).

### Biên độ hiệu ứng — người dùng bắt lỗi "rối mắt, đau đầu" (09/08/2026)
Sinh động không đồng nghĩa nảy mạnh. Thông số đã duyệt: `pop` phóng từ **74%** (không phải 60%), `flip` bóp còn **48%** bề ngang (không phải 15%), `shakein` thu 84% + rung **≤4px ở 7 nhịp/giây trong ≤0,45s**. Nhân toàn bộ thời gian vào thêm ~18%.

Đoạn mở đầu phải giãn hơn phần thân: các item cách nhau **≥0,4 giây**, `TypeLayer` **≤16 ký tự/giây**.

**Ảnh đã xuất hiện ở cảnh trước thì cảnh sau vào là có sẵn** (`anim="none"`, `t0=0`), không cho hiện lại — nếu không, chữ trong cảnh đó bị dồn hiệu ứng và người xem thấy gấp.

### Không dùng nhãn minh họa (chốt 20/08/2026)

**Không dập chữ "MINH HỌA" lên bất cứ đâu** — không lên đạo cụ đồ họa (tờ tiền, icon), **cũng không lên
biểu đồ tự dựng, và không có nhãn "ảnh minh hoạ giao diện…" dưới ảnh chụp app.** Người dùng thấy vướng
và làm màn rối. Cách giữ đúng giới hạn claim mà không cần nhãn:

- Cột/biểu đồ tự dựng thì **để trần, không gắn số nào** — chỉ so sánh cao–thấp trực quan (ví dụ cột
  "TREO LIVE" thấp · cột "LIVE AI" cao). Không có số thì không thành cam kết kết quả.
- Ảnh chụp app/sàn: chọn ảnh **không lộ số liệu** (crop bỏ băng doanh thu, tên shop, tên người bình luận)
  ngay từ khâu gom asset, thay vì để nguyên rồi dán nhãn.

### Lớp phủ đè lên người nói — một kiểu dựng bắt buộc, dùng rải khắp video (20/08/2026)
Thay vì cắt sang màn đồ họa full khung, render **PNG sequence RGBA đè lên chính hình người nói**: chữ `float` lơ lửng rung nhẹ ở khoảng trống phía trên đầu (tránh vùng mặt, đo bằng `drawgrid` trước), ảnh minh họa xếp thành **dải ngang phía dưới người**, ngang bàn làm việc. Ghép bằng cùng cơ chế với cảnh split: `-framerate 25 -start_number 1 -i seq_XXX/%04d.png` rồi `overlay=0:0:enable='between(...)'`.

**Không chỉ dùng ở đoạn mở đầu.** Người dùng yêu cầu (20/08/2026) coi lớp phủ là **một kiểu dựng
ngang hàng** với màn đồ họa full khung và cảnh split, và **luân phiên cả ba kiểu** trong suốt video:

| Kiểu | Khi nào dùng | Chi phí |
|---|---|---|
| Màn đồ họa full khung | Câu có nhiều ý cần liệt kê, số liệu, lưới, checklist | Rẻ, render Pillow |
| **Lớp phủ đè lên người nói** | Câu chỉ có 1–2 ý; muốn giữ mạch mặt người, giữ nhịp nói | Rẻ, render Pillow |
| Cảnh split (người tách nền) | Điểm nhấn, chốt ý, CTA | Đắt, ~50 s/frame cutout |

Mục tiêu nhịp: **cứ 2–3 màn full khung thì chèn 1 đoạn lớp phủ**, mỗi video ≥ 3–4 cửa sổ lớp phủ,
mỗi cửa sổ 2,5–5 giây. Lớp phủ là cách rẻ nhất để "ảnh liên tục" mà không cắt rời người nói.

Quy tắc dựng lớp phủ:

- **Đo vùng trống trước bằng `drawgrid`** trên đúng frame của cửa sổ đó. Người nói ngồi lệch/đưa
  tay theo từng đoạn — không dùng lại tọa độ của cửa sổ trước mà không kiểm.
- **Không che mặt và không che tay đang diễn.** Chữ đặt ở khoảng trống trên đầu hoặc bên vai
  trống; ảnh minh họa xếp dải ngang ngang bàn, hoặc cột dọc ở bên vai còn trống.
- **Nền lớp phủ phải bán trong suốt, không phải khối đặc**: panel trắng `alpha 200–225` bo góc 28,
  hoặc scrim gradient navy `alpha 0→150` ở mép trên/dưới. Đặc 100% thì thành màn full khung, mất
  ý nghĩa của lớp phủ.
- **Chữ phải có viền/bóng đậm** vì nền phía sau là hình quay thật, sáng tối thay đổi liên tục.
- Hiệu ứng ưu tiên `float`, `blurin`, `slideL`/`slideR` biên độ nhỏ — lớp phủ nằm trên hình động
  nên hiệu ứng mạnh sẽ rối. Không dùng `shakein` trên lớp phủ.
- Vẫn giữ **vùng an toàn Reels**: chữ trên y ≈ 1500, tránh cột phải x > 900.
- Caption lời thoại **vẫn bật** trong cửa sổ lớp phủ (khung này thoáng), trừ khi lớp phủ đã là
  một checklist nhiều dòng.

### Bố cục — đừng để 2 màn liền nhau giống nhau
Các archetype đã duyệt: ảnh phủ khổ + chữ đè (có scrim sáng để chữ navy đọc được) · lưới 2×2 ô có nhãn · cột ảnh trái + checklist phải · ảnh nửa trên + panel trắng nổi dưới · dải 3 ảnh ngang · ảnh cắt tròn viền màu · ảnh trái + capsule trượt phải · khối đôi có ảnh bên trong · số lớn + ảnh phụ · flow mũi tên dọc.

### Thuật ngữ phải gọi đúng

**"treo live"** — không phải "chèo live". Đây là cách người bán gọi việc phát lại video quay sẵn thành
phiên live. Whisper luôn nghe thành "chèo live"/"TeoLive"; sửa tay ở caption và chữ trên màn.

### Lề an toàn trên và dưới khung (chốt 20/08/2026)

Nền Tabcom có **logo ở y 48–122** và **hotline/website ở y 1829–1872**. Người dùng bắt lỗi "chữ sát logo,
ảnh sát mép dưới":

- Capsule tiêu đề màn FULL đặt tâm **y ≥ 240** (mép trên cách logo ≥ 90px).
- Mép dưới của mọi ảnh **≤ 1820**. Dải ảnh của lớp phủ đặt tâm **y ≈ 1670** (cao ~300) thay vì 1770.
- Vẫn giữ trần cũ cho chữ: chữ và số kết thúc **trên y ≈ 1500**.

### Màu cam Shopee là màu nhấn thứ ba

`ORANGE = (238, 77, 45)` — cam Shopee `#EE4D2D`, dùng xen với teal và navy cho capsule nhấn liên quan
Shopee, mũi tên, viền số lớn, và nền từ khóa "SHOPEE"/"SHOP" trong caption
(`caption(..., hi_col=ORANGE)` — chữ trên nền cam là **trắng**, trên nền teal là navy).
Liều lượng: khoảng 8–12 điểm cam trong một video ~100 giây, không thay thế teal/navy làm màu chính.

### Ảnh Live AI của Tabcom phải để full khung, không crop (chốt 20/08/2026)

Bộ `avatar-*` trong `TABCOM_ASSETS/avatar-ai/` là **941×1672 = tỉ lệ 9:16 (0,563)** — đây là ảnh sản phẩm
dịch vụ, crop vào là mất set quay, mất sản phẩm hai bên. Người dùng yêu cầu **thấy hết khung**:

- Mọi ô chứa ảnh này phải đặt **đúng tỉ lệ 0,563**: `170×302 · 200×355 · 240×426 · 300×533`.
- Không bỏ ảnh này vào `circle_photo()` (crop tròn) hay ô ngang — dùng ảnh reuse khác cho khung tròn.
- Lưới nhiều ảnh Live AI thì xếp **hàng ngang** (4 ảnh 230×408) hoặc **3×2**, không xếp 2×2 vì ảnh hẹp
  sẽ để lại hai khoảng trống lớn giữa màn.

### Lề an toàn (người dùng bắt lỗi bị crop)
Cột phải: `cx ≤ 806` và `maxw ≤ 490` (shadow cộng thêm 30px mỗi bên). Kiểm mọi capsule: `cx + maxw/2 + 30 ≤ 1080`.

### Khối có ảnh bên trong
Tính chiều cao chữ (`font.getmetrics()`) rồi mới đặt ảnh phía dưới, nếu không **ảnh sẽ đè lấp chữ phụ**.

### Vùng an toàn thật khi phát trên Reels (18/08/2026)

Khung 1080×1920 chỉ là khung file. Khi phát trên **Facebook Reels / TikTok**, phần dưới bị thanh
tên page + caption + nút che, mép phải bị cột nút tương tác che. Vì vậy:

- **Chữ và số liệu phải nằm trên y ≈ 1500**, tránh cột phải **x > 900**.
- Ảnh nền, card gradient và người tách nền được phép xuống thấp hơn — bị che một phần cũng không
  mất thông tin.
- Hàm `balance()` căn khối vào giữa vùng an toàn của nền; với phần chữ thì siết trần dưới còn
  **1500** thay vì 1810.

### Bố cục phải có logic

Thấy khoảng trống thì **không** mặc nhiên nhét ảnh vào cho đầy — mỗi khối phải gắn với một ý của
câu đang nói. Người dùng nhận ra ngay kiểu "trống đâu bạ đấy" và thấy khó chịu. Trống có chủ đích
còn hơn lấp bừa.

### Nhãn phân đoạn
Khi người nói full hình mà đang nói về một nhánh chủ đề (ví dụ NỘI SÀN / NGOẠI SÀN), thêm capsule nhãn trượt vào góc trái trong suốt đoạn đó để người xem phân biệt.

## Bước 4b — Caption chạy theo lời thoại (từ 18/08/2026)

Trước đây người dùng tự chèn caption trong CapCut; nay **pipeline dựng luôn**.

**Chọn khung nào có caption:** không bật đều toàn video. Khung đã kín chữ (công thức, lưới 6 ô,
checklist) thì **bỏ caption ở khung đó**; khung thoáng (ảnh phủ khổ, talking head, lớp phủ, cảnh
người ngồi nửa dưới) thì có. Quyết theo từng khung khi lên `ke-hoach-canh.md`, ghi rõ cột "caption".

**Chữ lấy từ đâu:** dùng `word_timestamps` của faster-whisper để chia cụm và lấy mốc, nhưng
**nội dung chữ phải chép từ kịch bản gốc**, không dùng thẳng text whisper — whisper nhận sai tên
riêng (shop→"sóp", ROAS→"doát", Shopee→"Soppy", Tabcom→"tapcom"), lên caption là lộ ngay.

**Kiểu chữ:** font Nếp gấp là font của CapCut, **không có trên máy** — đừng đi tìm. Dùng
`PS Anton - Regular V1.0.otf` trong `assets/fonts/ps-display/` của skill (`P.F_BLACK`) cho đồng bộ với chữ trong video.
IN HOA toàn bộ, 4–7 chữ một dòng, tối đa 2 dòng. Chữ trắng thì **bắt buộc có viền/bóng đậm**
để nổi trên mọi nền (bài học "chữ trắng chìm vào nền teal", 18/08/2026); 1–2 từ khóa mỗi câu tô
nền teal bo góc — chữ trên nền teal phải là navy.

**Đặt ở đâu:** ngang ngực người nói, khoảng **y 1150–1350** — nằm dưới khối nội dung (kết ở ~1500)
và trên vùng bị thanh info của Reels che. Không đặt caption đè lên chữ của cảnh.

## Bước 5 — Ghép + hiệu ứng + SFX

`scripts/13_assemble.py`.

- Base: `zoompan` zoom punch **12% trong 0.35 s** tại mỗi điểm cắt về người nói.
- Thứ tự overlay: nhãn phân đoạn → clip cảnh → cảnh split (bg + người) → sticker/PiP → flash.
- **PiP**: ảnh nhỏ trượt vào từ mép phải trong các đoạn talking head còn trống, để ảnh không bị đứt quãng.
- Flash chuyển cảnh: 2 lớp PNG radial trắng ấm (strong 0.85 → weak 0.38) tại **mọi** điểm chuyển.
- SFX (`ffmpeg lavfi`, trộn `amix`): whoosh 2 lớp vào cảnh · pop+click cho punch/badge · ding cho capsule · beep alert cho màn cảnh báo · boom cho số lớn và outro.
- **Liều lượng ding — người dùng bắt lỗi "ting ting nhức đầu" (09/08/2026):** ding chỉ đánh vào **nhịp chính của mỗi màn**, không đánh từng dòng trong list. Video ~100 giây thì **~68 điểm SFX là vừa, 119 điểm là quá nhiều**; volume ding ≤ 0.20.

## Chống hết RAM (đã gặp 2 lần)

- **Không** chạy rembg và render Pillow song song → `MemoryError`/segfault. Chạy tuần tự, hoặc chain bằng `until grep -q "DONE" log; do sleep 10; done`.
- Load lần lượt từng model rembg, `del` + `gc.collect()` giữa các phase.
- Pillow 9.5 segfault trên Python 3.12 → cần `pillow>=10`.
- Mọi script render phải có **skip-if-exists** để resume sau khi crash.

## Checklist bắt buộc trước khi bàn giao

- [ ] Không đoạn talking head nào tĩnh quá **~3 giây**.
- [ ] **Ảnh liên tục** — mọi màn có hình, đã dùng hết asset được gom.
- [ ] Mỗi ảnh đúng ngữ cảnh câu đang nói (đã mở xem, không đoán theo tên file).
- [ ] **Có** caption chạy theo lời thoại, nhưng **bỏ ở những khung đã ít khoảng trống** — quyết
      định theo từng khung, không bật đều toàn video.
- [ ] Chữ và số liệu nằm **trên y ≈ 1500** và tránh cột phải **x > 900**: khi phát trên Facebook
      Reels / TikTok, phần dưới bị thanh tên page + caption che, mép phải bị cột nút che.
- [ ] Bố cục có logic — mỗi khối gắn với một ý của câu đang nói, không nhét ảnh cho đầy chỗ trống.
- [ ] Có dùng bố cục "người ngồi nửa dưới, nội dung nửa trên" ở nhiều đoạn, không chỉ CTA cuối.
- [ ] Có **≥ 3 cửa sổ lớp phủ** đè lên hình người nói, rải đều video (không dồn ở mở đầu);
      nền lớp phủ bán trong suốt, không che mặt/tay.
- [ ] Người tách nền sạch tuyệt đối, đặt đúng tâm, chừa trống nửa trên khung.
- [ ] Không capsule/ảnh nào chạm mép phải (kiểm lề an toàn).
- [ ] Không ảnh đè lấp chữ.
- [ ] Bố cục đa dạng, 2 màn liền nhau không cùng kiểu; capsule nhấn căn giữa khung.
- [ ] Hiệu ứng chữ đa dạng, khớp nhịp nói; list có checkbox.
- [ ] Biên độ hiệu ứng vừa phải, đoạn mở đầu giãn nhịp; ảnh vào cảnh là có sẵn, không hiện lại.
- [ ] Ding chỉ đánh nhịp chính, không đánh từng dòng list.
- [ ] **Không có chữ "minh họa"** ở bất cứ đâu trên màn (đạo cụ, biểu đồ, nhãn dưới ảnh app).
- [ ] Nội dung nhắc sàn/app → logo thật đã tách nền (Wikimedia API), lưu vào `assets/logo/` của skill.
- [ ] Có zoom punch, flash chuyển cảnh, SFX đa dạng, OUTRO ở cuối.
- [ ] Đã tạo thumbnail bằng skill `tabcom-video-thumbnail`, lưu trong thư mục video.

## Bước 6 — Thumbnail (bắt buộc, làm luôn không cần hỏi)

Gọi skill **`tabcom-video-thumbnail`** ngay sau khi render xong video. Kết quả lưu **trong chính thư mục của video** với tên `yy.mm.dd - Tên video (thumb).jpg`.

## QC bằng mắt (không bỏ qua)

```bash
ffmpeg -i out.mp4 -vf "fps=1/5,scale=300:533,tile=4x3" -frames:v 1 qc.png   # toàn timeline
ffmpeg -ss <t> -i out.mp4 -frames:v 1 -vf "crop=700:460:190:820,scale=335:220" head.png  # viền tách nền
```
Đọc từng ảnh QC bằng Read. **QC cutout trước khi ghép**, đừng chờ render xong mới phát hiện lỗi.

## Bàn giao

`yy.mm.dd - Tên video (draft vN).mp4` cùng folder source. Nêu rõ đã làm gì, còn gì người dùng tự làm (nhạc nền), điểm nào chưa hoàn hảo.

## Môi trường

`ffmpeg`/`ffprobe`, `faster-whisper`, `rembg`+`onnxruntime` (`isnet-general-use`, `birefnet-portrait` đã tải), `pillow>=10`, `scipy`, `numpy`, Playwright + Chrome hệ thống.
