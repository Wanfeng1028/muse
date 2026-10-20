# Quy tắc bắt buộc cho mọi video Tabcom

Áp dụng cho tất cả video dựng bằng skill `tabcom-video-edit`. Đọc trước khi gom asset và trước khi dựng.

## 1. Thông số kỹ thuật chuẩn

| Mục | Giá trị |
|---|---|
| Khung hình | 1080×1920 (9:16 dọc) |
| Tốc độ khung | 25 fps |
| Mã hóa | H.264, crf 19 |
| Lời thoại | Giữ nguyên trọn vẹn của source, không cắt ý |
| Kết video | Nối `OUTRO TABCOM` (convert 30fps → 25fps rồi concat) |
| Nhạc nền | Người dùng tự chèn trong CapCut sau khi nhận file |
| Caption | Pipeline dựng luôn, không để người dùng làm tay |

## 2. Bảng màu thương hiệu

| Tên | RGB | Dùng cho |
|---|---|---|
| TEAL | `(23, 217, 179)` | Màu chính: capsule, highlight từ khóa, viền |
| NAVY | `(27, 37, 134)` | Chữ chính, nền khối đậm |
| ORANGE | `(238, 77, 45)` | Màu nhấn thứ ba (cam Shopee `#EE4D2D`) — 8–12 điểm/video ~100 giây |
| RED | `(198, 0, 1)` | Cảnh báo, cụm từ khóa trên thumbnail |
| INK | `(23, 23, 23)` | Chữ phụ |

Chữ trên nền teal phải là **navy**; chữ trên nền cam phải là **trắng**.

## 3. Font

Chỉ dùng bộ font trong `assets/fonts/ps-display/` của skill:

- `PS Anton - Regular V1.0.otf` — chữ lớn, tiêu đề, caption.
- `Big Shoulders ExtraBold Viet Hoa.otf` — dòng phụ.
- `PS Big Shoulders Bold Viet Hoa.otf` — chữ nhỏ.

Font condensed nên **cỡ chữ nhân 1.22**. Không tự thay font khác. Font "Nếp gấp" là font riêng của
CapCut, không có trên máy — đừng đi tìm.

## 4. Quy ước logo thương hiệu

- Nội dung nhắc tới sàn/nền tảng/app/thương hiệu cụ thể (Shopee, TikTok, Lazada, ChatGPT...) thì
  visual **phải dùng logo thật** của thương hiệu đó: lấy từ press kit, Wikimedia hoặc nguồn kiểm
  chứng được, remove background rồi mới chèn.
- **Không tự vẽ lại logo**, không dùng icon chung chung thay cho logo khi thương hiệu được nêu đích danh.
- Logo đã tách nền lưu vào `assets/logo/` của skill để tái dùng, đặt tên rõ:
  `logo-<thương hiệu>-<màu nền phù hợp>.png`.
- Chỉ dùng logo ở vai trò minh họa nội dung nói về nền tảng đó. Không đặt logo thương hiệu cạnh
  claim so sánh hoặc phê phán nếu chưa được duyệt.

## 5. Quy ước thu thập ảnh minh họa

- **Ảnh phải liên tục, mọi màn đều có hình.** Không dựng màn chữ trơn. Video ~115 giây cần 25–30 hình.
- Thứ tự nguồn: ảnh giới thiệu app chính thức trên Google Play → trang chính thức của sàn và kênh
  của chính Tabcom → ảnh chụp màn hình trong bài hướng dẫn tiếng Việt → ảnh stock.
  **Không dùng ảnh của đối thủ.**
- Mỗi thư mục asset video phải có `README.md` ghi: ảnh nào cho đoạn nào, URL ảnh, URL trang, ngày lấy,
  phần chưa lấy được, lưu ý khi dựng. Kèm contact sheet `_preview-all.png`.
- Ảnh có **tên tài khoản, tên shop, tên người bình luận** → crop bỏ hoặc làm mờ trước khi lên video.
- Số liệu hiển thị trong ảnh app là **số mẫu của nhà phát hành** — không đọc thành số liệu, không
  dùng làm bằng chứng kết quả.
- **Mở xem ảnh thật sự vẽ gì trước khi dùng**, không chọn theo tên file. Ảnh sai ngữ cảnh thì bỏ,
  không chèn cho đủ số lượng.

## 6. Giới hạn nội dung — không phóng đại, không giả dữ liệu

- **Không dán nhãn "MINH HỌA"** lên bất cứ đâu trên màn (đạo cụ, biểu đồ tự dựng, nhãn dưới ảnh app).
  Cách giữ đúng giới hạn claim mà không cần nhãn:
  - Biểu đồ tự dựng thì **để trần, không gắn số nào** — chỉ so sánh cao–thấp trực quan.
  - Ảnh chụp app/sàn: chọn ảnh **không lộ số liệu** ngay từ khâu gom asset.
- **Không đi tìm ảnh dashboard để giả làm dữ liệu thật.**
- Nội dung pháp lý/chính sách: asset phải trích từ **văn bản gốc hoặc nguồn chính thức**, ghi tên
  văn bản dưới ảnh.
- Không dùng ảnh chụp tiền thật (Nghị định 87/2023) — vẽ tờ tiền cách điệu bằng `banknote()`.

## 7. Vùng an toàn khi phát trên Reels / TikTok

Khung 1080×1920 chỉ là khung file. Khi phát, phần dưới bị thanh tên page + caption + nút che, mép
phải bị cột nút tương tác che.

- **Chữ và số liệu nằm trên y ≈ 1500**, tránh cột phải **x > 900**.
- Nền Tabcom có logo ở **y 48–122** và hotline/website ở **y 1829–1872**:
  capsule tiêu đề màn full đặt tâm **y ≥ 240**; mép dưới mọi ảnh **≤ 1820**.
- Cột phải: `cx ≤ 806` và `maxw ≤ 490` (shadow cộng thêm 30px mỗi bên).
- Caption đặt ngang ngực người nói, khoảng **y 1150–1350**.

## 8. Quy ước lưu output

- Video bàn giao: `yy.mm.dd - Tên video (draft vN).mp4`, đặt **cùng thư mục với file source**.
- Thumbnail: `yy.mm.dd - Tên video (thumb).jpg`, cũng **cùng thư mục với video** — đây là ngoại lệ
  so với quy ước gom hình vào thư mục output chung.
- Ảnh nguồn dùng cho video (ảnh chèn, cutout, screenshot) lưu trong thư mục asset riêng của video.
- File trung gian (frame, mask, clip) để trong thư mục `build/` tạm, không lẫn vào thư mục bàn giao.

## 9. Thuật ngữ phải gọi đúng

- **"treo live"** — không phải "chèo live". Whisper luôn nghe sai; sửa tay ở caption và chữ trên màn.
- Tên riêng whisper hay nhận sai: shop → "sóp", ROAS → "doát", Shopee → "Soppy", Tabcom → "tapcom".
  **Nội dung caption phải chép từ kịch bản gốc**, chỉ lấy mốc thời gian từ whisper.

## 10. Bàn giao

Nêu rõ: đã làm gì, còn gì người dùng tự làm (nhạc nền), điểm nào chưa hoàn hảo. Kèm thumbnail.
Checklist đầy đủ nằm cuối `SKILL.md`.
