# Các bẫy khi chụp Facebook / Threads

Ghi lại từ những lần chụp hỏng thật, kèm cách đã xử lý trong script. Đọc mục tương ứng
khi ảnh chụp ra sai thay vì mò lại từ đầu.

## Chẩn đoán nhanh

| Triệu chứng | Nguyên nhân | Mục |
|---|---|---|
| Ảnh trắng trơn / chỉ có avatar | chữ trắng trên nền bị ghi đè trắng | FB-4 |
| Ảnh ra **đúng kích thước** nhưng **nội dung khối khác** | chọn nhầm bản sao ẩn, hoặc khối nằm ngoài khung nhìn | FB-1, FB-2 |
| `boundingBox()` trả `null`, `0x0` | cả nhánh bị `visibility: hidden` | FB-3 |
| Có cửa sổ chat / banner đè lên ảnh | overlay `position: fixed` | FB-5 |
| Ảnh tối sạm, chữ trắng | lớp phủ popup đăng nhập, hoặc chế độ tối | TH-1, TH-2 |
| Tìm được 0 khối trên Threads | đã ẩn nhầm khung nội dung chính | TH-3 |
| Chữ quá nhỏ khi lên video | chưa phóng layout trước khi chụp | Chung-1 |

## Facebook

### FB-1. Nhiều bản sao của cùng một bình luận trong DOM
Facebook giữ vài bản của cùng nội dung. Bản ẩn **vẫn có `innerText`** nên không lọc được
bằng nội dung, và nếu ép nó hiện thì nó nằm chồng lên vùng khác → ảnh ra khối khác hẳn.

→ Chỉ nhận bản **đang thực sự được vẽ**: `getBoundingClientRect()` có kích thước, và
`document.elementFromPoint()` tại tâm nó trả về chính nó. Đừng ép hiện bản sao ẩn.

### FB-2. Bình luận nằm trong vùng cuộn riêng
`document.scrollHeight` chỉ 1400px nhưng bình luận ở `y = 6537`. Cuộn tới thì danh sách
ảo của Facebook render lại và mọi thứ dịch chỗ → chụp ra khối khác.

→ Đặt khung nhìn **rất cao** (18000px) để mọi khối nằm sẵn trong tầm chụp, và **không**
`scrollIntoView`. Đây là cách duy nhất chạy ổn định.

### FB-3. Cả nhánh bị `visibility: hidden`
Có bản lưu mà toàn bộ nhánh chứa bình luận bị ẩn.

→ Duyệt **hết** tổ tiên (không giới hạn số cấp) ép `visibility: visible`, `display` khác
`none`, bỏ `hidden` / `aria-hidden`; rồi ép tiếp cho các phần tử con bên trong.

### FB-4. Bài đăng nền gradient chữ trắng
Ghi đè `background: #fff` làm chữ trắng tàng hình → ảnh trắng trơn.

→ Đặt `keepBackground: true` cho card đó: giữ nguyên nền gốc, cũng không thêm padding
(padding làm chữ bị cắt ở mép phải).

### FB-5. Cửa sổ chat Messenger che ảnh
→ Ẩn mọi phần tử `position: fixed/sticky` **không chứa và không nằm trong** khối đang chụp.

### FB-6. Lưu trang sai trạng thái
Nếu lúc `Ctrl+S` trang đang ở bài khác (hoặc ở News Feed), dữ liệu bài cũ vẫn còn trong
DOM nhưng **không còn được vẽ** → mọi ảnh chụp đều trống.

→ Kiểm tra trước bằng `fb_list.js`: nếu không liệt kê được bình luận nào có kích thước
thật thì nhờ người dùng lưu lại. Mở bài bằng link trực tiếp `/posts/<id>/`, bung hết
bình luận, cuộn **lên lại đầu bài** rồi mới lưu. `.mhtml` hoạt động tốt.

## Threads

### TH-1. Popup đăng nhập kèm lớp phủ đen mờ
Làm mọi ảnh chụp tối sạm.

→ Gỡ `[role="dialog"]` và các lớp phủ `position: fixed` phủ gần kín màn hình có alpha > 0.05.

### TH-2. Chế độ tối không theo `prefers-color-scheme`
Threads lưu theme riêng nên `page.emulateMediaFeatures()` vô tác dụng.

→ Đổi màu thủ công theo độ sáng từng phần tử: chữ sáng (luminance > 170) → `#0a0a0a`,
chữ xám nhạt (> 110) → `#6b6b6b`, nền → trắng, viền → `#e4e4e4`; **giữ nguyên ảnh đại diện**.

### TH-3. Không được ẩn mọi `position: fixed`
Khác Facebook: khung nội dung chính của Threads **cũng là** `fixed`. Ẩn hết là mất luôn
bài viết, tìm được 0 khối.

### TH-4. Khung nhìn quá cao thì Threads không render
Ngược hẳn Facebook. Threads cần khung nhìn thường (~1600px) rồi `scrollIntoView` tới từng
khối. Đặt 9000px là trắng trang.

### TH-5. Giới hạn của khách chưa đăng nhập
Chỉ xem được ~13 khối dù bài có 424 reply; bấm mọi nút "xem thêm" cũng không ra thêm.

→ Dùng `threads_links.js`: lấy permalink của từng bình luận rồi mở lần lượt, gom reply
con. Một bài 424 reply lấy ra được 53 bình luận thật. Nhớ lọc spam — mở permalink thì
Threads chèn thêm bài quảng cáo không liên quan (`threads_filter.py` lọc theo ngày đăng
của bài gốc).

### TH-6. Chụp ở permalink riêng thì mất số like
Trang chi tiết của một bình luận không hiển thị số lượt thích của chính nó.

→ Card nào có số đáng khoe (9,6K / 6,5K / 1,2K) thì để `url: null` để chụp ở trang gốc;
các card còn lại dùng permalink riêng cho chữ to và đủ nội dung hơn.

## Chung

### Chung-1. Chữ nhỏ khi đưa lên khung dọc
Bài gốc rộng ~528–700px CSS, phóng lên 1000px chỉ được ~1.4×.

→ Đặt `SHOT_ZOOM` (1.6 Threads / 1.9 Facebook) để phóng layout **trước** khi chụp: khung
tăng ít hơn cỡ chữ nên tỉ lệ chữ/khung tăng ~1.5×. Đừng phóng quá tay — card dài sẽ cao
vượt khung; `prep_shots.py` đã chặn ở 1230px nhưng khi chạm trần thì chữ lại co nhỏ.

### Chung-2. Card đứng yên quá lâu
Bình luận dài đọc 60 giây trên một ảnh tĩnh nhìn như treo máy.

→ `build_final.py` cho card trôi lên chậm suốt thời gian hiển thị, biên độ theo độ dài
(tối đa 20px).

### Chung-3. Audio ngắn hơn video
`amix` kết thúc theo track giọng nên nhạc bị cắt, mấy giây cuối câm.

→ `apad` + `atrim` kéo track giọng bằng đúng độ dài video trước khi đưa vào sidechain.

### Chung-4. Nhạc lúc nghe được lúc không
Nhiều bản nhạc có đoạn rất khẽ; cộng thêm sidechain nén mạnh thì gần như mất hẳn.

→ `dynaudnorm` trước `volume`, và nén nhẹ tay (`threshold=0.08:ratio=4:release=280`).
Kiểm chứng bằng cách đo `volumedetect` ở các khoảng **không có giọng**: nên rơi vào
khoảng −24 đến −35 dB.
