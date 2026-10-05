# Hướng dẫn cài đặt bộ agent BĐS TP.HCM

## Có gì trong file nén
- `CLAUDE.md`: bối cảnh dự án, Claude đọc tự động khi làm việc trong thư mục này.
- `.claude/skills/`: 5 kỹ năng (agent) - thu thập, phân tích, tin quy hoạch, bản đồ, cập nhật hằng tuần.
- `bds/agents/`: script Python + trang bản đồ mẫu. `bds/template/`: template raw data v2.
- `requirements.txt`: thư viện Python cần cài.

## Cách 1: dùng trong project Claude này (đang dùng)
Không cần cài: script và dữ liệu đã ở `/mnt/project-files/bds/`. Chỉ cần lưu 5 kỹ năng từ các thẻ "Lưu kỹ năng" trong thread,
hoặc vào claude.ai → Settings → Capabilities → Skills → tải lên từng thư mục trong `.claude/skills/` (nén mỗi thư mục thành .zip).

## Cách 2: dùng Claude Code trên máy của bạn hoặc trong repo GitHub
1. Giải nén vào một thư mục, ví dụ `bds-web/`.
2. Cài Python 3.10+ rồi chạy: `pip install -r requirements.txt`
3. Đặt biến: `export BDS_ROOT=$(pwd)/bds` (Windows PowerShell: `$env:BDS_ROOT="$PWD\bds"`).
4. Mở Claude Code trong thư mục đó (`claude`). Claude tự đọc `CLAUDE.md` và thấy 5 kỹ năng trong `.claude/skills/`.
5. Thử: "chạy kỹ năng bds-thu-thap-du-lieu", rồi "chạy bds-phan-tich-gia", "dựng bản đồ bds-ban-do".
6. Xem bản đồ: `cd bds/web && python -m http.server 8000` rồi mở http://localhost:8000

## Đăng bản đồ lên mạng miễn phí (GitHub Pages)
1. Tạo repo GitHub (ví dụ `bds-hcm-map`), đẩy nội dung thư mục `bds/web/` lên nhánh `main`.
2. Repo → Settings → Pages → Source: Deploy from branch → `main` / root.
3. Trang có địa chỉ dạng `https://<tên-github>.github.io/bds-hcm-map/`.
4. Cập nhật hằng tuần: `PUSH=1 WEB_REPO_DIR=<thư mục clone repo> bash bds/agents/cap-nhat/weekly.sh`

## Cập nhật tự động hằng tuần
Trong project Claude: nhắn "tạo lịch chạy bds-cap-nhat-hang-tuan mỗi sáng thứ Hai". Môi trường đám mây cần mở các tên miền ghi trong `CLAUDE.md`.
