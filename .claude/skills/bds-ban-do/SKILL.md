---
name: bds-ban-do
description: Dựng và cập nhật trang web bản đồ giá căn hộ TP.HCM (Leaflet + OpenStreetMap, miễn phí): nhãn giá theo dự án, di chuột hiện link tin, bộ lọc, lớp tin quy hoạch.
---

# Agent 4: Bản đồ giá căn hộ

Dựng một lần, sau đó chỉ cần làm mới dữ liệu (Agent 5 gọi `build_map.py`). Trả lời bằng tiếng Việt.

## Thành phần
- `<BDS_ROOT>/agents/ban-do/index.html`: trang mẫu (Leaflet 1.9.4 + markercluster từ unpkg, nền OpenStreetMap).
- `<BDS_ROOT>/agents/ban-do/build_map.py`: xuất `web/data/listings.json`, `meta.json`, `news.geojson`; chép `index.html` vào `web/` nếu chưa có.
- Trang chạy tĩnh, không cần máy chủ, không tốn phí bản đồ.

## Chạy
```bash
python3 <BDS_ROOT>/agents/ban-do/build_map.py              # làm mới dữ liệu
python3 <BDS_ROOT>/agents/ban-do/build_map.py --force-html # ghi đè index.html sau khi sửa template
cd <BDS_ROOT>/web && python3 -m http.server 8000           # xem thử tại http://localhost:8000
```

## Trang hiển thị
- Mỗi dự án: nhãn trắng "tên + giá/m² trung vị" (giống Batdongsan). Tin không thuộc dự án: nhãn đen "x tỷ".
- Di chuột vào nhãn: hộp hiện danh sách tin (giá, diện tích, số PN, giá/m²) kèm link bài đăng.
- Thu nhỏ: gom nhóm thành vòng tròn đếm số tin; zoom ≥ 16 hiện từng nhãn.
- Bộ lọc: tìm tên, giá, giá/m², diện tích, số phòng ngủ, khu vực (quận cũ), phường mới, pháp lý, ngày đăng, nguồn; bật/tắt lớp tin quy hoạch.
- Chỉ dùng tin "Đang đăng" có tọa độ trong khung TP.HCM.

## Đăng lên mạng (miễn phí)
Cần một repo GitHub (người dùng tạo, hoặc cho phép Claude tạo). Đưa nội dung `web/` lên nhánh chính của repo,
bật GitHub Pages (Settings → Pages → Deploy from branch). Agent 5 cập nhật bằng `PUSH=1 WEB_REPO_DIR=<clone> bash weekly.sh`.
Không đẩy lên repo khi người dùng chưa đồng ý.

## Khi sửa giao diện
- Sửa `agents/ban-do/index.html`, chạy `build_map.py --force-html`, kiểm tra bằng trình duyệt (Playwright: `/opt/pw-browsers/chromium-*/chrome-linux/chrome`).
- Giữ thứ tự trường `FIELDS` trong `build_map.py` khớp với cách `index.html` đọc.
