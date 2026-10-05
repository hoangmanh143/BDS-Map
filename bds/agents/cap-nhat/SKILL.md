---
name: bds-cap-nhat-hang-tuan
description: Chạy đợt cập nhật hằng tuần cho web bản đồ BĐS TP.HCM - thu thập, phân tích, tin quy hoạch, làm mới dữ liệu bản đồ, đẩy lên trang và báo kết quả.
---

# Agent 5: Cập nhật hằng tuần

Dùng khi người dùng nói "cập nhật tuần này", khi routine hằng tuần chạy, hoặc khi cần làm mới bản đồ. Trả lời bằng tiếng Việt.

## Các bước
1. **Tin quy hoạch trước** (cần Claude): làm theo kỹ năng `bds-tin-quy-hoach` để ghi tin mới vào `tin_quy_hoach/raw/<hôm nay>.jsonl`
   và số liệu báo cáo giá mới (nếu có) vào `data/raw/<hôm nay>/price_history_google.jsonl`.
2. **Chạy chuỗi script**:
   ```bash
   bash <BDS_ROOT>/agents/cap-nhat/weekly.sh
   ```
   Script: kiểm tra mạng → Agent 1 (Chotot, Batdongsan nếu vào được, build, geocode) → Agent 2 → gộp tin Agent 3 → Agent 4.
   Mã thoát 2 = mạng chặn Chotot: báo người dùng, không chạy tiếp.
3. **Kiểm tra trước khi đẩy**: so `raw_data/BDS_HCM_raw_latest.xlsx` sheet Thong_ke với tuần trước. Nếu số tin đang đăng giảm hơn 30%
   hoặc giá trung vị toàn TP đổi hơn 10% trong 1 tuần, dừng và hỏi người dùng (thường do nguồn đổi cấu trúc).
4. **Đẩy lên trang** (chỉ khi đã có repo GitHub Pages và người dùng đồng ý một lần):
   `PUSH=1 WEB_REPO_DIR=<thư mục clone> bash weekly.sh`, hoặc commit thư mục `web/` vào repo đó.
5. **Báo một tin ngắn**: số tin mới / đã gỡ / tổng đang đăng, giá trung vị toàn TP và % so tuần trước,
   2–3 khu vực biến động mạnh nhất (từ `phan_tich/BDS_HCM_phan_tich_latest.xlsx`, sheet Tang_truong_gia), số tin quy hoạch mới, link trang.

## Lịch tự động
Tạo một routine hằng tuần (sáng thứ Hai, giờ Việt Nam) với nội dung: "Chạy kỹ năng bds-cap-nhat-hang-tuan".
Routine chạy trên môi trường đám mây của project, môi trường đó phải cho phép gateway.chotot.com, nominatim.openstreetmap.org,
pypi.org/files.pythonhosted.org, và (nếu đẩy trang) github.com.
