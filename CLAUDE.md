# Dự án: Web tìm kiếm bất động sản TP.HCM

Chủ dự án: Mạnh. Luôn trả lời bằng **tiếng Việt**, ngắn gọn, nêu số liệu kèm nguồn.

## Mục tiêu
Trang web bản đồ giá căn hộ TP.HCM (giống bản đồ giá của Batdongsan): mỗi dự án hiện giá/m², di chuột hiện link tin đăng,
có bộ lọc; kèm phân tích giá, tăng trưởng theo khu vực và tin quy hoạch. Cập nhật hằng tuần.

## Phạm vi đã chốt (05/10/2026)
- TP.HCM **cũ**: 22 quận/huyện trước sáp nhập 1/7/2025 (không gồm Bình Dương, Bà Rịa-Vũng Tàu).
- Căn hộ chung cư và dự án, chỉ tin **bán**.
- Nguồn: Chotot/Nhà Tốt, Batdongsan.com.vn, Google (báo, báo cáo thị trường). **Không dùng nhóm Facebook.**
- Lịch sử giá: không có dữ liệu cũ; dùng snapshot hằng tuần + giá ban đầu của tin Chotot + báo cáo công khai.
- Bản đồ miễn phí: Leaflet + OpenStreetMap, trang tĩnh. Chưa có tên miền/hosting; dự kiến GitHub Pages.
- Phường ghi theo đơn vị **mới** sau sáp nhập; kèm cột Quận/Huyện cũ để so với số liệu quá khứ.

## 5 agent (kỹ năng)
| # | Kỹ năng | Script | Đầu ra |
|---|---|---|---|
| 1 | `bds-thu-thap-du-lieu` | `agents/thu-thap/collect.py` | `raw_data/BDS_HCM_raw_latest.xlsx` |
| 2 | `bds-phan-tich-gia` | `agents/phan-tich/analyze.py` | `phan_tich/BDS_HCM_phan_tich_latest.xlsx`, `phan_tich/khu_vuc.json` |
| 3 | `bds-tin-quy-hoach` | `agents/tin-quy-hoach/news.py` | `tin_quy_hoach/tin_quy_hoach.xlsx`, `.geojson` |
| 4 | `bds-ban-do` | `agents/ban-do/build_map.py` + `index.html` | `web/` (trang bản đồ) |
| 5 | `bds-cap-nhat-hang-tuan` | `agents/cap-nhat/weekly.sh` | chạy 1 → 2 → 3 → 4, đẩy trang, báo kết quả |

Thứ tự phụ thuộc: Agent 1 là gốc; 2 và 4 đọc file của 1; 4 đọc thêm file của 2 và 3.

## Thư mục dữ liệu (`BDS_ROOT`)
- Trong project Claude: `BDS_ROOT=/mnt/project-files/bds` (mặc định của mọi script).
- Trên máy khác: `export BDS_ROOT=<đường dẫn>/bds` trước khi chạy script; thay `/mnt/project-files/bds` trong SKILL.md bằng đường dẫn đó.
```
bds/
  agents/        script + SKILL.md của 5 agent
  template/      Template_raw_data_v2.xlsx (sheet Tu_dien giải thích cột)
  data/          raw/<ngày>/*.jsonl, master.csv, snapshots/, projects.csv, geocode_cache.csv, project_aliases.csv
  raw_data/      file xlsx tổng hợp theo ngày + _latest
  phan_tich/     kết quả Agent 2
  tin_quy_hoach/ raw/<ngày>.jsonl + kết quả Agent 3
  web/           trang bản đồ (index.html + data/)
```

## Môi trường
- Python 3 + `pandas openpyxl requests beautifulsoup4` (xem `requirements.txt`).
  Trên môi trường đám mây của Claude, nếu pip báo không tìm thấy gói: thêm `NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1` trước lệnh pip.
- Mạng cần mở: `gateway.chotot.com`, `nominatim.openstreetmap.org`, `pypi.org`, `files.pythonhosted.org`; thêm `github.com` nếu đẩy trang.
- Batdongsan chặn truy cập tự động bằng Cloudflare (403): chỉ lấy mẫu qua WebFetch khi được; **không tìm cách vượt chặn**.

## Quy tắc làm việc
- Template v2 đã được Mạnh duyệt ngày 05/10/2026. Muốn đổi cột phải hỏi lại.
- Không xóa `data/master.csv`, `data/snapshots/`: đó là lịch sử giá.
- Không bịa số liệu; trường không có thì để trống. Ghi rõ "giá chào bán" khi nói về giá tin đăng.
- Việc không hoàn tác được (đẩy trang công khai, xóa dữ liệu hàng loạt) phải hỏi trước.
- Sau mỗi lần chạy: báo số tin, số dự án, file kết quả và điều còn thiếu.
