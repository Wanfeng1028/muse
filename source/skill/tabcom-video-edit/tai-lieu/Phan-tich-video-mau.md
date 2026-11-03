# Phân tích video mẫu: "26.08.06 - ChatGPT và Shopee (SFX v2).mp4"

Phân tích ngày 07/08/2026, dùng làm chuẩn khi edit các video mới của Tabcom.

## Thông số

- Khổ dọc 1080x1920 (9:16), 30fps, dài ~63 giây, tiếng AAC stereo, có SFX và nhạc nền.
- Source người nói của video mới: 1080x1920, 25fps, ~122 giây (sẽ cắt còn ~60-75 giây).

## Hệ layout (5 kiểu cảnh)

1. **Talking head full-frame**: người nói tại bàn làm việc, nền văn phòng thật (kệ cúp, bảng TABCOM GROUP). Caption đặt ngang ngực, khoảng 55-60% chiều cao khung hình.
2. **Cut-in minh họa full màn**: nền giấy trắng (asset `Nền.png` có sẵn logo Tabcom trên giữa, hotline trái dưới, website phải dưới), ở giữa là illustration dạng editorial collage (ảnh người đen trắng cắt nền + mảng navy/đỏ + nét vẽ xanh lá + mũi tên đen). Caption đè giữa. Dùng cho hook và các đoạn chuyển ý.
3. **Split trên/dưới**: nửa trên là screenshot (đặt trên nền giấy trắng có logo), nửa dưới là người nói đã remove background, đặt trước card gradient xanh lá sang cyan bo góc (asset `Nền nhỏ đặt sau người khi đã remove bg.png`). Caption nằm giữa hai vùng, ngay trên đầu người.
4. **Asset full màn trên gradient**: nền gradient xanh (phóng to từ `Nền nhỏ`) hoặc nền giấy, screenshot/screen-record thả nổi ở giữa, caption bên dưới. Trong mẫu, phần screenshot là screen-record có chuột di chuyển; với asset tĩnh thì thay bằng zoom/pan chậm.
5. **Màn text động**: nền giấy trắng + logo. Gồm: (a) câu hỏi/gạch ý dạng capsule teal bo góc, chữ trắng, hiện lần lượt kèm hiệu ứng gõ chữ; (b) màn PROMPT: nhãn "PROMPT", nội dung prompt màu navy/teal gõ từng dòng; (c) màn công thức: tiêu đề + các dòng [thành phần] + dấu cộng, build từng dòng.

## Caption

- Font: **Nếp gấp** (CapCut), viết IN HOA toàn bộ, màu trắng, có bóng nhẹ.
- Mỗi câu 1 dòng ngắn (4-7 chữ), 1-2 từ khóa được tô nền **teal bo góc** (kiểu highlight capsule). Từ khóa tô là danh từ/số quan trọng: "SHOPEE", "CHATGPT", "1 TỶ", "30 NGÀY"...
- Caption chạy theo lời thoại, đổi liên tục theo nhịp cắt, không dồn nhiều dòng.

## Nhịp dựng

- Hard cut là chính, không transition cầu kỳ. Đổi layout mỗi 2-6 giây.
- Mở bài: 1 câu talking head → cut-in illustration hook full màn (~2-3 giây) → quay lại người nói.
- Thân bài: luân phiên talking head ↔ split screenshot ↔ màn text động; mỗi ý một asset.
- Các đoạn liệt kê dùng capsule teal hiện lần lượt trên nền người nói làm mờ (blur).
- Kết: recap trên nền giấy (logo/từ khóa lớn + 1 dòng đỏ) → talking head CTA "Tabcom gửi shop ngay..." (CTA comment/inbox).
- SFX pop/whoosh khi asset xuất hiện, nhạc nền nhẹ xuyên suốt.

## Màu

- Teal/green gradient (#0?: xanh lá → cyan, lấy đúng từ asset), navy, đỏ đô cho dòng nhấn, nền giấy trắng. Đồng bộ với hệ carousel Tabcom.

## Asset cố định (folder "Các asset cố định")

- `Nền.png`: nền giấy 9:16 có logo + footer, dùng cho mọi cảnh asset/text.
- `Nền nhỏ đặt sau người khi đã remove bg.png`: gradient card sau người đã tách nền (cảnh split) và có thể phóng to làm nền asset.
- `logo nền sáng.jpg`: logo dự phòng.

> Pipeline dựng và checklist đầy đủ: xem `pipeline/README-quy-trinh-edit-video.md` (chốt sau bản v6 video Hóa đơn điện tử).

## Quy ước bổ sung (07/08/2026)

- Không dùng caption chạy theo lời thoại khi dựng bản nháp; người dùng tự chèn caption trong CapCut (font Nếp gấp).
- Cảnh split: người phải được remove background thật (AI cutout, phương án nhanh: rembg isnet-general-use + cắt alpha ngưỡng ~140 để loại bóng ghế), đặt lên card gradient, đầu nhô lên trên mép card; tuyệt đối không để khung chữ nhật cắt vào người.
- Đoạn nào nhắc đến sàn/nền tảng/app/thương hiệu cụ thể: tìm logo thật, remove background rồi chèn (xem quy ước trong `AGENTS.md`).
- Màn liệt kê dạng list: có checkbox/tick đầu dòng; capsule nhắc thương hiệu dùng màu nhận diện của thương hiệu đó (Shopee cam #EE4D2D, TikTok đen).

## Áp cho video mới "Hóa đơn điện tử" (26.08.07)

- Source người nói: áo polo navy Tabcom, cùng bối cảnh văn phòng, 122s cần cắt gọn còn ~60-75s theo 5 lưu ý của kịch bản.
- Asset thay cho screen-record: bộ ảnh pháp lý trong `Tabcom Content/Tabcom content video/video-assets/26.08.07 - Video hóa đơn điện tử shop sàn/` (trích Nghị định 70/2025 bản ký số, infographic ngành Thuế, mẫu 01/ĐKTĐ-HĐĐT, cổng hoadondientu, bài bảng kê). Ảnh tĩnh nên dùng zoom/pan chậm + khoanh đỏ/highlight vùng cần chú ý khi nói tới.
- Các mốc pháp lý (1 tỷ, 30 ngày, thời điểm giao hàng, bảng kê) hợp với màn text động dạng capsule/công thức như mẫu.
