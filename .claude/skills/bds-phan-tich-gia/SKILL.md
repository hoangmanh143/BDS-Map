---
name: bds-phan-tich-gia
description: Phân tích giá căn hộ TP.HCM (thấp nhất, cao nhất, trung bình, trung vị) theo vùng, quận cũ, phường, dự án, loại căn; % tăng trưởng giá theo giai đoạn và nguồn cung theo khu vực.
---

# Agent 2: Phân tích giá và tăng trưởng

Dùng khi người dùng hỏi giá căn hộ theo khu vực, mức tăng giá, so sánh quận/phường/dự án, hoặc sau mỗi lần Agent 1 cập nhật dữ liệu.
Trả lời bằng tiếng Việt.

## Đầu vào / đầu ra
- Đọc: `<BDS_ROOT>/raw_data/BDS_HCM_raw_latest.xlsx` (Agent 1, kỹ năng `bds-thu-thap-du-lieu`) và `<BDS_ROOT>/data/snapshots/*.csv`.
- Ghi: `<BDS_ROOT>/phan_tich/BDS_HCM_phan_tich_<ngày>.xlsx` + `_latest.xlsx`, và `phan_tich/khu_vuc.json` (Agent 4 dùng cho bản đồ).
- `BDS_ROOT` mặc định `/mnt/project-files/bds`.

## Chạy
```bash
python3 <BDS_ROOT>/agents/phan-tich/analyze.py
```
Nếu file latest chưa có hoặc cũ hơn 7 ngày, chạy Agent 1 trước.

## Sheet kết quả
| Sheet | Nội dung |
|---|---|
| Ghi_chu | ngày dữ liệu, số tin dùng, số tin bị loại, cách tính |
| Toan_TP, Theo_vung, Theo_quan_cu, Theo_phuong, Theo_du_an, Theo_loai_can | số tin, giá/m² thấp nhất, TB, trung vị, cao nhất, giá căn TB, diện tích TB, độ tin cậy |
| Tang_truong_gia | % so kỳ trước, 4/13/52 tuần, so kỳ đầu, theo từng Cấp + Tên + Nguồn |
| Nguon_cung | số tin chào bán theo khu vực ở mỗi snapshot |
| Du_an_theo_nam | số dự án mở bán theo năm và khu vực (cần cột Năm mở bán) |
| Tin_bi_loai | tin bị loại vì giá/m² bất thường, để kiểm tra tay |

## Quy tắc diễn giải
- Giá là **giá chào bán** trên tin đăng, không phải giá giao dịch. Chotot nghiêng về căn thứ cấp, giá thấp hơn báo cáo sơ cấp (VD báo cáo Q1/2026: 112–122 tr/m², tin đăng toàn TP: trung vị khoảng 54 tr/m²). Luôn nói rõ nguồn khi so sánh.
- Dùng **trung vị** khi nói về "giá khu vực"; nêu số tin. Khu vực "Độ tin cậy: Thấp" (<5 tin) chỉ nhắc kèm cảnh báo.
- Quận 2, Quận 9, Quận Thủ Đức cũ gộp thành "TP Thủ Đức".
- Tăng trưởng nhiều năm khi chưa đủ snapshot: dùng dòng báo cáo trong Lich_su_gia (Nguồn ≠ "Snapshot tin đăng"), ghi tên đơn vị báo cáo. Không tự suy ra % từ hai nguồn khác nhau.
- Khi trả lời, dẫn file kết quả và nêu 3–5 điểm chính (khu đắt nhất/rẻ nhất, khu tăng/giảm mạnh nhất, nguồn cung tăng ở đâu).
