---
name: bds-tin-quy-hoach
description: Tìm và lưu tin quy hoạch, hạ tầng, giải tỏa, dự án lớn, chính sách có thể ảnh hưởng giá căn hộ theo khu vực TP.HCM; xuất xlsx và lớp điểm cho bản đồ.
---

# Agent 3: Tin quy hoạch, đầu tư, giải tỏa, chính sách

Dùng khi người dùng hỏi yếu tố nào đang/ sẽ tác động giá một khu vực, hoặc trong đợt cập nhật hằng tuần.
Trả lời bằng tiếng Việt.

## Quy trình
1. Đọc `<BDS_ROOT>/tin_quy_hoach/tin_quy_hoach.xlsx` (nếu có) để biết tin đã lưu; chỉ tìm tin mới hơn tin mới nhất trong đó (lần đầu: 24 tháng gần nhất).
2. Tìm bằng WebSearch (gửi nhiều truy vấn cùng lúc), theo các nhóm:
   - Hạ tầng giao thông: metro (tuyến 1, 2, 6…), vành đai 2/3/4, cầu (Cần Giờ, Thủ Thiêm 4…), cao tốc, sân bay Long Thành kết nối.
   - Quy hoạch: quy hoạch chung, phân khu 1/2000, TOD, khu đô thị mới.
   - Giải tỏa - tái định cư, thu hồi đất.
   - Dự án lớn khởi công / tạm dừng / được gỡ vướng pháp lý.
   - Chính sách: bảng giá đất, tín dụng, thuế, luật Đất đai/Nhà ở/Kinh doanh BĐS, sáp nhập hành chính.
   - Thị trường: báo cáo giá quý (CBRE, Savills, DKRA, Avison Young, Bộ Xây dựng) → ghi thêm vào
     `<BDS_ROOT>/data/raw/<hôm nay>/price_history_google.jsonl` theo định dạng của Agent 1.
   Ưu tiên: cổng TP.HCM (hochiminhcity.gov.vn), Sở Xây dựng, Sở Quy hoạch Kiến trúc, VnExpress, Tuổi Trẻ, Thanh Niên, Người Lao Động, VietnamFinance, Thư viện Pháp luật, CafeLand.
3. Mở bài bằng WebFetch trước khi ghi (đoạn trích tìm kiếm không phải nguồn). Không bịa ngày, số liệu, tọa độ.
4. Ghi mỗi tin 1 dòng JSON vào `<BDS_ROOT>/tin_quy_hoach/raw/<YYYY-MM-DD>.jsonl` với các khóa:
   `Ngày tin` (dd/mm/yyyy), `Tiêu đề`, `Loại` (Hạ tầng giao thông | Quy hoạch | Giải tỏa - tái định cư | Dự án lớn | Chính sách | Thị trường),
   `Tóm tắt` (1–2 câu, có số liệu), `Khu vực ảnh hưởng`, `Phường` (mới), `Quận/Huyện cũ`, `Vĩ độ`, `Kinh độ`
   (chỉ khi bài nêu vị trí cụ thể: ga, nút giao, dự án; tra bằng Nominatim nếu cần), `Tác động dự kiến` (Tăng | Giảm | Trung tính),
   `Mức độ` (Cao | Vừa | Thấp), `Mốc thời gian`, `Trạng thái dự án`, `Nguồn`, `Link`.
   Một bài nói nhiều dự án → nhiều dòng; thêm `#ten` vào cuối Link để không bị gộp trùng.
5. Chạy `python3 <BDS_ROOT>/agents/tin-quy-hoach/news.py build` → `tin_quy_hoach.xlsx` (sheet Tin, Theo_khu_vuc) và `tin_quy_hoach.geojson`.
6. Báo người dùng: số tin mới, 3–5 tin đáng chú ý nhất theo khu vực, link file.

## Đánh giá tác động
- "Tăng": hạ tầng mới gần khu dân cư, quy hoạch nâng cấp, pháp lý dự án được gỡ.
- "Giảm": giải tỏa kéo dài, dự án treo, siết tín dụng, nguồn cung lớn đổ vào cùng khu.
- Đây là nhận định của agent, ghi rõ là "dự kiến"; không đưa lời khuyên đầu tư.
