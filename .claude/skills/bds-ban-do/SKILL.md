---
name: bds-ban-do
description: Dựng và cập nhật trang web bản đồ giá căn hộ TP.HCM (Leaflet + nền Esri Street Map/OSM/vệ tinh Esri, miễn phí): nhãn giá theo dự án, di chuột hiện link tin, bộ lọc, lớp tin quy hoạch.
---

# Agent 4: Bản đồ giá căn hộ

Dựng một lần, sau đó chỉ cần làm mới dữ liệu (Agent 5 gọi `build_map.py`). Trả lời bằng tiếng Việt.

## Thành phần
- `<BDS_ROOT>/agents/ban-do/index.html`: trang mẫu (Leaflet 1.9.4 + markercluster từ unpkg, nền Esri World Street Map (không cần API key; CARTO nay đòi key) + nút chuyển OpenStreetMap, ảnh vệ tinh Esri).
- `<BDS_ROOT>/agents/ban-do/build_map.py`: xuất `web/data/listings.json`, `meta.json`, `news.geojson`; chép `index.html` vào `web/` nếu chưa có.
- Trang chạy tĩnh, không cần máy chủ, không tốn phí bản đồ.

## Chạy
```bash
python3 <BDS_ROOT>/agents/ban-do/build_map.py              # làm mới dữ liệu (mặc định --days 30)
python3 <BDS_ROOT>/agents/ban-do/build_map.py --force-html # ghi đè index.html sau khi sửa template
cd <BDS_ROOT>/web && python3 -m http.server 8000           # xem thử tại http://localhost:8000
```

## Trang hiển thị
- Mỗi dự án: nhãn trắng "tên + giá/m² trung vị" (giống Batdongsan). Tin không thuộc dự án: nhãn đen "x tỷ".
- Di chuột vào nhãn: hộp hiện danh sách tin (giá, diện tích, số PN, giá/m²) kèm link bài đăng.
- Thu nhỏ: gom nhóm thành vòng tròn đếm số tin; zoom ≥ 16 hiện từng nhãn.
- Bộ lọc: tìm tên, giá, giá/m², diện tích, số phòng ngủ, khu vực (quận cũ), phường mới, pháp lý, ngày đăng, nguồn; bật/tắt lớp tin quy hoạch.
- Chỉ dùng tin "Đang đăng" có tọa độ trong khung TP.HCM và **đăng trong 30 ngày** tính đến ngày thu thập
  (tin không có ngày đăng bị bỏ). Danh sách trong hộp xếp mới nhất trước, ghi ngày đăng và nguồn; giá nhãn dự án
  là trung vị của các tin 30 ngày đó. Bộ lọc ngày: 30 / 14 / 7 ngày.

## Độ chính xác vị trí
- Chotot/Homedy thường đặt nhiều tin, nhiều dự án chung một điểm tâm phường (vd Citi Home và Victoria Village cùng
  một điểm). Vì vậy Agent 1 chạy `collect.py geocode`: tra tọa độ từng dự án theo tên (Nominatim/OpenStreetMap,
  chỉ nhận kết quả là tòa nhà/khu dân cư trong TP.HCM cũ) và tra "đường, phường" cho tin không thuộc dự án.
  Tọa độ tra được **thay** tọa độ nguồn.
- Sửa tay (ưu tiên cao nhất): thêm dòng `ma_du_an,lat,lng,ghi_chu` vào `data/toa_do_tay.csv`
  (vd chuột phải vào tòa nhà trên Google Maps, chép tọa độ), rồi chạy lại `collect.py build` và `build_map.py`.
- Trường `acc` của mỗi tin: A = tọa độ dự án đã tra/sửa tay, S = đúng con đường, P = ghim của người đăng,
  X = gần đúng (tâm phường). Nhãn X có viền đứt, màu xám, hộp ghi "Vị trí gần đúng"; ô "Chỉ vị trí chính xác" ẩn chúng.
- Google Geocoding API chính xác hơn nhưng cần API key có bật thanh toán; chưa dùng.

## Đăng lên mạng (miễn phí)
Cần một repo GitHub (người dùng tạo, hoặc cho phép Claude tạo). Đưa nội dung `web/` lên nhánh chính của repo,
bật GitHub Pages (Settings → Pages → Deploy from branch). Agent 5 cập nhật bằng `PUSH=1 WEB_REPO_DIR=<clone> bash weekly.sh`.
Không đẩy lên repo khi người dùng chưa đồng ý.

## Khi sửa giao diện
- Sửa `agents/ban-do/index.html`, chạy `build_map.py --force-html`, kiểm tra bằng trình duyệt (Playwright: `/opt/pw-browsers/chromium-*/chrome-linux/chrome`).
- Giữ thứ tự trường `FIELDS` trong `build_map.py` khớp với cách `index.html` đọc.
