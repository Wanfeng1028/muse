---
name: tabcom-video-thumbnail
description: Tạo thumbnail (ảnh bìa) cho video ngắn dọc 9:16 của Tabcom từ chính source người nói - cắt khung, viền nét đứt trắng quanh người, gradient xanh teal trên dưới, panel trắng bo góc với tiêu đề IN HOA 2 dòng. Dùng khi người dùng nói "tạo thumb", "làm thumbnail", "ảnh bìa video", "cover video", hoặc đổi tiêu đề/khung hình của một thumbnail đã tạo. Skill này chạy TỰ ĐỘNG ngay sau khi dựng xong video bằng skill tabcom-video-edit, không cần đợi người dùng nhắc.
---

# Tabcom video thumbnail

Ảnh bìa dọc **1080×1920 JPG**, dựng bằng `scripts/make_thumb.py` (Pillow + OpenCV + rembg). Mẫu đã duyệt: `mau-thumb-da-duyet.jpg` trong thư mục skill này.

## Chạy tự động sau khi edit video

Dựng xong video là **làm thumbnail luôn**, không hỏi. Người dùng đã chốt: mỗi video ngắn phải có thumbnail đi kèm.

## Công thức đã duyệt

1. **Khung hình**: cắt 1 frame từ **source người nói** (không phải bản đã edit). Dò 5–6 mốc thời gian, xem bằng mắt, chọn frame **mặt hướng máy, miệng khép, tay gọn, mắt mở**.
2. **Viền nét đứt trắng** quanh người: mask bằng `birefnet-portrait` → dilate 26px → `cv2.findContours` → đi dọc contour vẽ nét đứt (nét 38px, cách 26px, dày 8px) + lớp glow mờ phía sau để nổi trên nền tối.
3. **Gradient xanh teal** mép trên 30% chiều cao và mép dưới 26%, blend chế độ **screen**, alpha 0.62. Màu: trên `(18,214,160)`, dưới `(16,190,170)`.
4. **Panel trắng bo góc**: rộng 960, bo 30, nền trắng alpha 246, **padding 72×50**, đặt tâm tại y≈1400, đổ bóng nhẹ.
5. **Tiêu đề 2 dòng, IN HOA toàn bộ** (script tự `.upper()`):
   - Dòng 1: cụm khóa tô **đỏ `#E21A22`**, phần còn lại **navy `#1B2A8C`**.
   - Dòng 2: navy toàn bộ.
   - Markup: `"TRAFFIC *NỘI SÀN VÀ NGOẠI SÀN*"` — phần trong `*...*` là đỏ.
   - Cấu trúc câu theo mẫu: **[nội dung chính] / [đối tượng] phải biết / phải nắm / phải phân biệt**.
6. **Font: đúng bộ font đang dùng để edit video** — `assets/fonts/ps-display/` của skill `tabcom-video-edit`
   (script tự tìm qua `tabcom_paths.py`, không cần cấu hình):
   - `anton` = `PS Anton - Regular V1.0.otf` (mặc định, là font display của video)
   - `shoulders` = `Big Shoulders ExtraBold Viet Hoa.otf` (phương án 2)

## Nơi lưu kết quả

**Trong đúng thư mục chứa file video source** (`yy.mm.dd - Tên video/`), đặt tên:

```
yy.mm.dd - Tên video (thumb).jpg
```

Đây là **ngoại lệ** so với quy ước lưu output hình ảnh (xem `tai-lieu/quy-tac-video-tabcom.md`
trong skill `tabcom-video-edit`): thumbnail video nằm cùng chỗ với file video, không tách ra.

## Cách chạy

```bash
python scripts/make_thumb.py "<source.mp4>" <giây> "<dòng 1, *cụm này màu đỏ*>" "<dòng 2>" [thư-mục-ra]
```

Không truyền tham số thì script lấy video từ `TABCOM_SRC` và ghi ảnh cạnh file video.
Đổi tiêu đề hoặc đổi frame chỉ mất chưa tới 1 phút render.

## Lưu ý đã bị nhắc

- Chữ **không được sát viền panel** — giữ padding 72×50, đừng giảm.
- **In hoa toàn bộ**, không dùng sentence case.
- Dùng font của video, không tự thay font khác.
- Kiểm bằng mắt sau khi render: đọc file ảnh bằng Read, soát chữ tràn, viền nét đứt có ôm đúng người, gradient không nuốt mất mặt.

## Môi trường

`ffmpeg`, `opencv-python` (cv2), `rembg` + `birefnet-portrait`, `pillow>=10`, `numpy`.
