---
name: bds-thu-thap-du-lieu
description: Thu thập tin bán căn hộ và danh sách dự án TP.HCM từ Batdongsan, Chotot, Google vào file raw data xlsx (template v2), chạy lại hằng tuần để có lịch sử giá.
---

# Agent 1: Thu thập dữ liệu BĐS TP.HCM

Dùng khi cần lấy tin bán căn hộ / dự án mới nhất ở TP.HCM, hoặc chạy đợt cập nhật hằng tuần.
Trả lời người dùng bằng tiếng Việt.

## Phạm vi đã chốt
- TP.HCM **cũ** (22 quận/huyện trước 1/7/2025; build tự loại tin Bình Dương, Bà Rịa-Vũng Tàu), căn hộ chung cư + dự án, chỉ tin **bán**.
- Nguồn: Chotot/Nhà Tốt (chính), Muaban, Homedy, Bds123, Mogi, Batdongsan.vn, Google (báo, báo cáo thị trường);
  Batdongsan.com.vn chỉ có mẫu khi lấy được. **Bỏ qua nhóm Facebook.**
- Mỗi tuần 1 lần. Lịch sử giá = các snapshot hằng tuần + giá ban đầu của tin Chotot + số liệu báo cáo công khai.

## Vị trí
- Script: `/mnt/project-files/bds/agents/thu-thap/collect.py` (cần `pandas openpyxl requests beautifulsoup4`).
- Template: `/mnt/project-files/bds/template/Template_raw_data_v2.xlsx` (sheet `Tu_dien` giải thích cột).
- Dữ liệu thô: `/mnt/project-files/bds/data/raw/<YYYY-MM-DD>/*.jsonl`
- Kho tích lũy: `data/master.csv` (mọi tin từng thấy), `data/snapshots/<ngày>.csv`, `data/projects.csv`,
  `data/price_history_external.csv`, `data/geocode_cache.csv`, `data/project_aliases.csv` (sửa tay).
- Kết quả: `/mnt/project-files/bds/raw_data/BDS_HCM_raw_<ngày>.xlsx` và `BDS_HCM_raw_latest.xlsx`
  (sheet Tin_dang, Du_an, Lich_su_gia, Thong_ke). Agent phân tích và agent bản đồ đọc file `latest`.

## Bước 0: kiểm tra mạng
```bash
curl -sS -o /dev/null -w "%{http_code}\n" --max-time 15 "https://gateway.chotot.com/v1/public/ad-listing?region_v2=13000&cg=1010&st=s&limit=1"
```
- `200` → **Chế độ A (script)**.
- Lỗi 403 / `CONNECT tunnel failed` → mạng môi trường chặn. Báo người dùng một lần các tên miền cần mở
  (batdongsan.com.vn, gateway.chotot.com, nominatim.openstreetmap.org) rồi dùng **Chế độ B (WebFetch)**.

## Chế độ A: script (đủ toàn TP, dùng cho chạy hằng tuần)
```bash
cd /mnt/project-files/bds/agents/thu-thap
python3 collect.py chotot                 # ~4.000 tin, API JSON, có tọa độ + phường mới
python3 collect.py batdongsan             # ~13.700 tin, 20 tin/trang, nghỉ 1,5 giây/trang
python3 collect.py batdongsan-projects    # ~700 dự án
python3 collect.py muaban                 # ~1.000 tin, JSON trong trang
python3 collect.py homedy                 # HTML, 18 tin/trang
python3 collect.py bds123                 # HTML, 20 tin/trang (có cả Bình Dương -> build tự loại)
python3 collect.py mogi                   # HTML, 15 tin/trang, bỏ tin cho thuê
python3 collect.py bdsvn                  # batdongsan.vn (KHÁC batdongsan.com.vn)
python3 collect.py build                  # chuẩn hóa, chống trùng, so tuần trước, xuất xlsx
python3 collect.py geocode && python3 collect.py build   # tra tọa độ dự án còn thiếu
```
- Cài thư viện: nếu pip báo "No matching distribution", chạy
  `NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 python3 -m pip install pandas openpyxl requests beautifulsoup4`.
- Chạy thật 05/10/2026: Chotot OK (4.104 tin, ~3 phút). **Batdongsan chặn bằng Cloudflare** (HTTP 403
  "Just a moment", cả với Chromium headless) nên `batdongsan` / `batdongsan-projects` không chạy được từ cloud;
  không cố vượt chặn. Lấy mẫu Batdongsan bằng Chế độ B (WebFetch) — nhưng trên môi trường "BĐS project" WebFetch tới batdongsan.com.vn cũng báo EGRESS_BLOCKED (05/10/2026). Bộ chọn HTML vẫn chưa kiểm chứng.
- Giữ `--delay` ≥ 1,5 giây, không chạy song song nhiều tiến trình vào cùng một trang.

### Nguồn bổ sung (thêm 05/10/2026)
- Các nguồn này có thể chạy song song (mỗi trang một tiến trình). Dừng khi trang rỗng hoặc lặp lại.
- Tin chỉ có phường mới: build suy ra quận cũ từ cặp phường→quận của Chotot; không suy ra được thì loại
  (thường là Bình Dương/BR-VT cũ).
- Cùng một căn có thể được đăng trên nhiều trang; build chưa gộp trùng giữa các nguồn.
- Build loại tin nguồn bổ sung có ngày đăng quá 180 ngày (`STALE_DAYS`): trang sâu của Mogi/Bds123 còn rất nhiều
  tin 2024 với giá cũ. Homedy không ghi ngày ở trang sâu nên không lọc được.
- Geocode: Nominatim hay trả 429 qua proxy chung; script tự dừng, lưu tiến độ, lần sau chạy tiếp.
- Không dùng được: OneHousing (chỉ có hàng Hà Nội), Alonhadat, i-batdongsan (xác minh robot), Nhadat24h,
  Guland, Cafeland (Cloudflare). Không cố vượt các lớp chặn này.

## Chế độ B: WebFetch (khi mạng bị chặn; chỉ lấy được mẫu vài trăm tin)
Gom bằng WebFetch, ghi JSONL vào `data/raw/<hôm nay>/`, rồi chạy `python3 collect.py build`.
Tên file quyết định cách đọc:

| File | Lấy từ | Khóa mỗi dòng |
|---|---|---|
| `chotot_*.jsonl` | `https://gateway.chotot.com/v1/public/ad-listing?region_v2=13000&cg=1010&st=s&limit=20&o=<offset>` | list_id, subject, price, original_price, size, rooms, toilets, floornumber, area_name, ward_name_v3, street_name, pty_project_name, latitude, longitude, list_time, orig_list_time, property_legal_document, furnishing_sell, company_ad |
| `batdongsan_<x>.jsonl` | `https://batdongsan.com.vn/ban-can-ho-chung-cu-tp-hcm/p<n>` | url, product_id, title, project, price_text, area_text, bedrooms, toilets, location_text (vd "Quận 7 (P. Phú Thuận mới)"), posted_text |
| `batdongsan_projects_*.jsonl` | `https://batdongsan.com.vn/du-an-can-ho-chung-cu-tp-hcm/p<n>` | name, url, developer, address, price_text, status, area_scale |
| `price_history_*.jsonl` | báo cáo thị trường tìm bằng WebSearch | Kỳ, Cấp, Tên, Giá TB (tr/m2), Giá thấp nhất (tr/m2), Giá cao nhất (tr/m2), Nguồn, Link nguồn |
| tên khác (vd `google_*.jsonl`) | tin từ web khác | đúng tên cột sheet Tin_dang |

Lưu ý chế độ B:
- Prompt WebFetch: "Output ONLY a JSON array … using exactly these keys copied verbatim … null where missing".
  Mỗi lần thường chỉ trả 10–20 tin; kiểm tra vài giá trị với trang gốc trước khi tin.
- Không bịa số liệu: trường nào trang không có thì để null.
- Báo cáo giá lịch sử: ghi rõ đơn vị gốc (CBRE, Savills, DKRA, Bộ Xây dựng…) trong `Nguồn`, giữ link bài.

## Sau khi build
1. Đọc `Thong_ke` và vài dòng `Tin_dang`; kiểm tra: tỷ lệ thiếu giá, thiếu tọa độ, giá/m² bất thường.
2. Tên dự án lệch giữa nguồn (vd "Green River - Quận 8" vs "Green River"): thêm dòng vào
   `data/project_aliases.csv` (cột `alias,ma_du_an`) rồi build lại.
3. Báo người dùng: số tin mới / đã gỡ / tổng, số dự án, link file `latest`, và điều gì còn thiếu.

## Quy tắc
- Không đổi tên/thứ tự cột template khi chưa được người dùng duyệt (cột nằm trong `LISTING_COLS`,
  `PROJECT_COLS`, `HISTORY_COLS` ở đầu `collect.py`).
- Không xóa `data/master.csv` hay `data/snapshots/`; đó là lịch sử giá.
- Chạy build lại cùng ngày là an toàn (ghi đè snapshot ngày đó).
