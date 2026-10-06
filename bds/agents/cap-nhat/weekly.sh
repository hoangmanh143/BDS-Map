#!/usr/bin/env bash
# Agent 5: chạy lại cả chuỗi hằng tuần. Dừng ngay khi một bước lỗi.
#   bash weekly.sh            # thu thập + phân tích + tin quy hoạch + dữ liệu bản đồ
#   PUSH=1 bash weekly.sh     # thêm bước đẩy thư mục web/ lên repo (cần WEB_REPO_DIR là bản clone của repo trang)
set -euo pipefail
ROOT="${BDS_ROOT:-/mnt/project-files/bds}"
A="$ROOT/agents"
export BDS_ROOT="$ROOT"
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "1/6 Kiểm tra mạng"
code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 "https://gateway.chotot.com/v1/public/ad-listing?region_v2=13000&cg=1010&st=s&limit=1" || true)
[ "$code" = "200" ] || { echo "Chotot không truy cập được (HTTP $code). Dừng; xem SKILL bds-thu-thap-du-lieu, Chế độ B."; exit 2; }

log "2/6 Thu thập (Agent 1)"
python3 "$A/thu-thap/collect.py" chotot
bds=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 -A "Mozilla/5.0" https://batdongsan.com.vn/ban-can-ho-chung-cu-tp-hcm || true)
if [ "$bds" = "200" ]; then
  python3 "$A/thu-thap/collect.py" batdongsan || log "Batdongsan lỗi, bỏ qua tuần này"
else
  log "Batdongsan trả HTTP $bds (thường do Cloudflare), bỏ qua"
fi
python3 "$A/thu-thap/collect.py" build
python3 "$A/thu-thap/collect.py" geocode --limit 800 || log "Geocode lỗi, dùng tọa độ cũ"
python3 "$A/thu-thap/collect.py" build

log "3/6 Phân tích (Agent 2)"
python3 "$A/phan-tich/analyze.py"

log "4/6 Tin quy hoạch (Agent 3): gộp các tin Claude đã ghi vào tin_quy_hoach/raw/"
ls "$ROOT"/tin_quy_hoach/raw/*.jsonl >/dev/null 2>&1 && python3 "$A/tin-quy-hoach/news.py" build || log "Chưa có tin mới"

log "5/6 Dữ liệu bản đồ (Agent 4)"
python3 "$A/ban-do/build_map.py"

if [ "${PUSH:-0}" = "1" ]; then
  log "6/6 Đẩy web/ lên repo trang"
  : "${WEB_REPO_DIR:?Đặt WEB_REPO_DIR là thư mục clone của repo GitHub Pages}"
  rsync -a --delete --exclude .git "$ROOT/web/" "$WEB_REPO_DIR/"
  git -C "$WEB_REPO_DIR" add -A
  git -C "$WEB_REPO_DIR" commit -m "Cập nhật dữ liệu $(date +%Y-%m-%d)" || log "Không có thay đổi"
  git -C "$WEB_REPO_DIR" push
else
  log "6/6 Bỏ qua bước đẩy lên repo (PUSH khác 1)"
fi
log "Xong"
