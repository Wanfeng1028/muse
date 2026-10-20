---
name: social-qa-video
description: Biến một bài hỏi-đáp trên Threads hoặc Facebook thành video dọc 9:16 kiểu TikTok — ảnh chụp thật của bài đăng và bình luận trôi trên nền phong cảnh, có giọng đọc tiếng Việt và nhạc nền. Dùng khi người dùng gửi link threads.com hoặc facebook.com kèm ý muốn "làm video", "dựng video từ bài này", "cap màn hình bình luận làm video", "làm video hỏi đáp", "biến bài này thành TikTok/Reels", hoặc chỉ dán link mà ngữ cảnh đang làm video ngắn. Cũng dùng khi muốn sửa nội dung, đổi giọng, đổi nhạc hay render lại một video đã dựng bằng skill này.
---

# Video hỏi–đáp từ Threads / Facebook

Dựng video dọc 1080×1920: **ảnh chụp thật** của bài đăng và bình luận (giữ nguyên avatar,
tên, icon like, số lượt thích) đặt giữa khung, trôi lên rất chậm trên nền phong cảnh làm
tối; giọng đọc tiếng Việt đọc **nguyên văn**; nhạc nền tự hạ xuống khi có giọng.

Toàn bộ miễn phí: ảnh chụp bằng Chrome, giọng bằng edge-tts, nền và nhạc từ Mixkit.

## Quy trình

Đặt `SK=${CLAUDE_SKILL_DIR}` (thư mục của skill này; cài thủ công thì là `~/.claude/skills/social-qa-video`). Mỗi video là một thư mục project riêng.

### 1. Lấy nội dung

**Threads** (bài công khai — chụp thẳng từ web, không cần đăng nhập):
```bash
node $SK/scripts/threads_dump.js "<url>" shot/threads.json       # ~13 khối đầu
node $SK/scripts/threads_links.js "<url>" shot/threads_all.json  # sâu hơn: mở permalink từng reply
python $SK/scripts/threads_filter.py                              # lọc bỏ spam, giữ reply đúng bài
```
`threads_dump` nhanh nhưng Threads chỉ cho khách xem ~13 khối. `threads_links` mở permalink
của từng bình luận nên gom được nhiều hơn hẳn (một bài 424 reply lấy ra được 53 cái thật).

**Facebook** (phải đăng nhập → nhờ người dùng lưu trang):
> Mở bài bằng **link trực tiếp** dạng `/posts/<id>/` (đừng lưu từ News Feed), bung hết
> "Xem thêm bình luận" / "Xem thêm", cuộn **lên lại đầu bài**, rồi `Ctrl+S` →
> "Trang web, hoàn chỉnh" hoặc `.mhtml`.

```bash
node $SK/scripts/fb_list.js "<file đã lưu>"   # liệt kê bình luận ĐANG hiển thị thật
```

### 2. Chọn bình luận & viết targets

Chọn bình luận **dài, có góc nhìn riêng, lượt like cao**; giữ ít nhất một góc phản biện.
Viết `shot/targets.json`:

```json
[{"key": "card01", "needle": "đoạn text đặc trưng", "blurName": false,
  "hideMedia": true, "url": null}]
```
- `needle` — mẩu chữ đủ đặc trưng để tìm đúng khối
- `url` — Threads: `null` = chụp ở trang gốc (**giữ được số like**), hoặc permalink riêng
  (chữ to hơn nhưng mất số like). Cho các card có số ấn tượng thì để `null`.
- `blurName` — làm mờ tên; xem mục Riêng tư
- `hideMedia` — ẩn ảnh đính kèm cho card khỏi quá cao
- Facebook thêm `kind`: `"post"` cho bài đăng, `"comment"` cho bình luận;
  `keepBackground: true` nếu bài đăng là nền gradient chữ trắng

### 3. Chụp và chuẩn bị card

```bash
SHOT_ZOOM=1.6 node $SK/scripts/threads_shot.js "<url>" shot/targets.json shot/raw
# Facebook:
SHOT_ZOOM=1.9 node $SK/scripts/fb_shoot.js "<file đã lưu>" shot/targets.json shot/raw

python $SK/scripts/prep_shots.py shot/raw <proj>/cards   # bo góc, đổ bóng, giới hạn cao
```
`SHOT_ZOOM` phóng layout trước khi chụp để chữ to hơn khi thu vào khung dọc: 1.6 cho
Threads, 1.9 cho Facebook. **Luôn xem lại ảnh** (`Read` file PNG) trước khi render.

### 4. Viết content.json rồi render

```bash
python $SK/scripts/new_project.py <proj> 8     # tạo khung content.json
cd <proj>
python $SK/scripts/phien_am.py content.json   # phiên âm từ tiếng Anh
python $SK/scripts/tts.py
python $SK/scripts/build_bg.py
python $SK/scripts/build_final.py              # -> output/video-hoan-chinh.mp4
```

`content.json`: mỗi card có `speak` = lời đọc. Số card phải **khớp** số ảnh trong `cards/`.

Biến môi trường: `BG_DIR` (bộ nền: `assets/bg/nature` hoặc `assets/bg/city`),
`MUSIC` (file nhạc), `PAD` (đệm sau mỗi câu, mặc định 0.9s).

## Quy tắc nội dung

- **Đọc nguyên văn.** Không thêm câu dẫn kiểu "Một người khác nói rằng…". Chỉ mở rộng
  viết tắt để máy đọc đúng: `sx`→sản xuất, `15tr`→mười lăm triệu, `b`→bạn, `ko`→không,
  `đc`→được, `cmt`→comment, `frs`→freeship.
- **Phiên âm từ tiếng Anh** — bắt buộc, chạy trước khi thu giọng. edge-tts đọc từ tiếng
  Anh theo kiểu đánh vần tiếng Việt nghe rất sai (KOC, KOL, follower…):
  ```bash
  python $SK/scripts/phien_am.py <proj>/content.json          # sửa tại chỗ
  python $SK/scripts/phien_am.py <proj>/content.json --check  # chỉ xem
  ```
  KOC→"cây âu xi", KOL→"cây âu eo", follower→"pho lâu ơ", TikTok→"Tích Tóc",
  Shopee→"Sô pi", brand→"bờ ren", data→"đây ta"… Gặp từ mới chưa có thì thêm vào
  `PHIEN_AM` trong script. Chỉ áp cho `speak`; **ảnh chụp giữ nguyên chữ gốc**.
- **Không bịa.** Không thêm số like giả, không thêm bình luận không có thật.
- Mở đầu bằng bình luận đắt nhất (like cao hoặc câu chuyện mạnh), kết bằng câu để lại
  dư âm hoặc một góc nhìn ngược.
- Một bình luận dài bị nền tảng cắt làm nhiều mảnh thì ghép lại cho liền mạch.

## Riêng tư

Làm mờ **tên thật** (Sơn Ngọc Trần, Truong Chi Cong…). Giữ nguyên **nickname tự sinh**
(ProductivePersimmon7745, hdtshop.vn, sontap88…) vì vốn đã ẩn danh. Đặt `blurName: true`
cho card cần mờ — script làm mờ cả tên lẫn avatar.

## Độ dài

Khoảng **1 phút 30 – 2 phút** là vừa. Ước lượng: ~14 chữ tiếng Việt ≈ 1 giây đọc
(tốc độ +18%). Dài quá thì bớt card, đừng đọc chậm lại.

## Nhạc

Mặc định lấy nhạc Mixkit trong `assets/music` (không lời, dùng thương mại được, không
cần ghi công). Muốn dùng nhạc trending của TikTok thì đặt `MUSIC=<file>` — nhưng đó là
nhạc có bản quyền: đăng TikTok thường không sao vì TikTok có license, còn YouTube/Facebook
thì nên đăng bản không nhạc rồi thêm nhạc trong app.

## Lần đầu chạy trên máy mới

```bash
python $SK/scripts/fetch_assets.py    # tải clip nền + nhạc Mixkit
```
Cần sẵn: `ffmpeg`, `yt-dlp`, `node` + `puppeteer-core`, Chrome, Python có `Pillow`,
`edge-tts`. Giọng: `vi-VN-HoaiMyNeural` (nữ, câu mở và câu kết) và `vi-VN-NamMinhNeural`
(nam, các bình luận) — sửa trong `scripts/tts.py`.

## Khi ảnh chụp ra sai

Đọc `references/troubleshooting.md` — chép lại đầy đủ các bẫy của Facebook và Threads
(bản sao DOM ẩn, vùng cuộn riêng, popup che, chế độ tối) kèm cách đã xử lý.
