#!/usr/bin/env python3
"""Agent 2: phân tích giá và tăng trưởng căn hộ TP.HCM.

Đọc  raw_data/BDS_HCM_raw_latest.xlsx (do Agent 1 tạo)
Ghi  phan_tich/BDS_HCM_phan_tich_<ngày>.xlsx (+ _latest)
     phan_tich/khu_vuc.json  (tóm tắt theo phường / quận cũ cho bản đồ)

  python3 analyze.py            # dùng file latest
  python3 analyze.py --input <file.xlsx>
"""
import argparse, datetime as dt, json, os, shutil

import pandas as pd

ROOT = os.environ.get("BDS_ROOT", "/mnt/project-files/bds")
PRICE = "Giá đơn vị (Triệu VNĐ/ m2)"

# TP Thủ Đức gộp Quận 2, Quận 9, Quận Thủ Đức cũ; các nguồn ghi lẫn lộn nên chuẩn về một khu vực.
AREA_ALIAS = {"Quận 2": "TP Thủ Đức", "Quận 9": "TP Thủ Đức", "Quận Thủ Đức": "TP Thủ Đức",
              "Thành phố Thủ Đức": "TP Thủ Đức"}
ZONE = {  # nhóm khu vực lớn, phục vụ so sánh nhanh
    "Quận 1": "Trung tâm", "Quận 3": "Trung tâm", "Quận 4": "Trung tâm", "Quận 5": "Trung tâm",
    "Quận 10": "Trung tâm", "Quận Phú Nhuận": "Trung tâm", "Quận Bình Thạnh": "Trung tâm",
    "TP Thủ Đức": "Phía Đông", "Quận 7": "Phía Nam", "Huyện Nhà Bè": "Phía Nam", "Quận 8": "Phía Nam",
    "Huyện Bình Chánh": "Phía Tây", "Quận Bình Tân": "Phía Tây", "Quận 6": "Phía Tây", "Quận 11": "Phía Tây",
    "Quận Tân Phú": "Phía Tây", "Quận Tân Bình": "Phía Bắc", "Quận Gò Vấp": "Phía Bắc", "Quận 12": "Phía Bắc",
    "Huyện Hóc Môn": "Phía Bắc", "Huyện Củ Chi": "Phía Bắc", "Huyện Cần Giờ": "Phía Nam",
}

def stats(df, keys, min_n=1):
    g = df.groupby(keys, dropna=True)[PRICE]
    out = pd.DataFrame({
        "Số tin": g.size(),
        "Giá/m² thấp nhất": g.min(), "Giá/m² trung bình": g.mean(), "Giá/m² trung vị": g.median(),
        "Giá/m² cao nhất": g.max(),
        "Giá căn TB (tỷ)": df.groupby(keys)["Giá (tỷ VNĐ)"].mean(),
        "Diện tích TB (m²)": df.groupby(keys)["Diện tích (m2)"].mean(),
    }).round(2).reset_index()
    out = out[out["Số tin"] >= min_n]
    out["Độ tin cậy"] = pd.cut(out["Số tin"], [0, 4, 19, 10**9], labels=["Thấp (<5 tin)", "Vừa", "Cao (≥20 tin)"])
    return out.sort_values("Giá/m² trung vị", ascending=False)

def drop_outliers(df):
    """Bỏ giá/m² ngoài 1,5 IQR trong từng khu vực (nhập sai đơn vị, tin rác)."""
    def keep(s):
        q1, q3 = s.quantile(.25), s.quantile(.75)
        iqr = q3 - q1
        return s.between(q1 - 1.5 * iqr, q3 + 1.5 * iqr) if len(s) >= 8 else pd.Series(True, s.index)
    mask = df.groupby("Khu vực")[PRICE].transform(keep).astype(bool)
    return df[mask], df[~mask]

def growth(hist):
    """% thay đổi giá TB giữa kỳ mới nhất và các mốc trước (theo Cấp + Tên + Nguồn)."""
    hist = hist.dropna(subset=["Giá TB (tr/m2)"]).copy()
    rows = []
    for (level, name, src), g in hist.groupby(["Cấp", "Tên", "Nguồn"]):
        g = g.sort_values("Kỳ")
        last = g.iloc[-1]
        row = {"Cấp": level, "Tên": name, "Nguồn": src, "Kỳ mới nhất": last["Kỳ"],
               "Giá TB mới nhất": last["Giá TB (tr/m2)"], "Số kỳ có dữ liệu": len(g)}
        if len(g) >= 2:
            prev = g.iloc[-2]
            row["Kỳ trước"] = prev["Kỳ"]
            row["% so kỳ trước"] = round((last["Giá TB (tr/m2)"] / prev["Giá TB (tr/m2)"] - 1) * 100, 2)
            first = g.iloc[0]
            row["Kỳ đầu"] = first["Kỳ"]
            row["% so kỳ đầu"] = round((last["Giá TB (tr/m2)"] / first["Giá TB (tr/m2)"] - 1) * 100, 2)
        # mốc theo tuần cho dữ liệu snapshot (Kỳ dạng YYYY-MM-DD)
        try:
            d_last = dt.date.fromisoformat(str(last["Kỳ"]))
            for label, days in [("% 4 tuần", 28), ("% 13 tuần", 91), ("% 52 tuần", 364)]:
                older = g[g["Kỳ"].map(lambda k: _is_date(k) and dt.date.fromisoformat(k) <= d_last - dt.timedelta(days=days))]
                if len(older):
                    row[label] = round((last["Giá TB (tr/m2)"] / older.iloc[-1]["Giá TB (tr/m2)"] - 1) * 100, 2)
        except ValueError:
            pass
        rows.append(row)
    cols = ["Cấp", "Tên", "Nguồn", "Kỳ đầu", "Kỳ trước", "Kỳ mới nhất", "Giá TB mới nhất", "% so kỳ trước",
            "% 4 tuần", "% 13 tuần", "% 52 tuần", "% so kỳ đầu", "Số kỳ có dữ liệu"]
    return pd.DataFrame(rows).reindex(columns=cols)

def _is_date(k):
    try:
        dt.date.fromisoformat(str(k))
        return True
    except ValueError:
        return False

def supply(root):
    """Số tin đang bán theo khu vực ở mỗi snapshot = tăng trưởng nguồn cung chào bán."""
    import glob
    rows = []
    for p in sorted(glob.glob(os.path.join(root, "data", "snapshots", "*.csv"))):
        s = pd.read_csv(p, usecols=["Quận/Huyện cũ", "Mã dự án"])
        s["Khu vực"] = s["Quận/Huyện cũ"].map(lambda x: AREA_ALIAS.get(x, x))
        g = s.groupby("Khu vực").agg(**{"Số tin": ("Mã dự án", "size"), "Số dự án có tin": ("Mã dự án", "nunique")})
        g["Kỳ"] = os.path.basename(p)[:-4]
        rows.append(g.reset_index())
    if not rows:
        return pd.DataFrame()
    df = pd.concat(rows)
    wide = df.pivot_table(index="Khu vực", columns="Kỳ", values="Số tin", aggfunc="sum")
    if wide.shape[1] >= 2:
        wide["% so kỳ trước"] = ((wide.iloc[:, -1] / wide.iloc[:, -2] - 1) * 100).round(1)
    return wide.reset_index()

def projects_by_year(proj):
    p = proj.copy()
    p["Khu vực"] = p["Quận/Huyện cũ"].map(lambda x: AREA_ALIAS.get(x, x))
    if p["Năm mở bán"].notna().sum() == 0:
        return pd.DataFrame({"Ghi chú": ["Chưa có cột Năm mở bán trong Du_an; Agent 1/3 cần bổ sung từ trang dự án hoặc tin tức."]})
    t = p.dropna(subset=["Năm mở bán"]).pivot_table(index="Khu vực", columns="Năm mở bán", values="Mã dự án", aggfunc="count", fill_value=0)
    return t.reset_index()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=os.path.join(ROOT, "raw_data", "BDS_HCM_raw_latest.xlsx"))
    args = ap.parse_args()
    x = pd.read_excel(args.input, sheet_name=None)
    tin, proj, hist = x["Tin_dang"], x["Du_an"], x["Lich_su_gia"]
    date = pd.to_datetime(tin["Ngày thu thập"], dayfirst=True).max().date().isoformat()

    act = tin[(tin["Trạng thái tin"] == "Đang đăng") & tin[PRICE].notna()].copy()
    act["Khu vực"] = act["Quận/Huyện cũ"].map(lambda v: AREA_ALIAS.get(v, v))
    act["Vùng"] = act["Khu vực"].map(ZONE)
    act["Loại căn"] = act["Số phòng ngủ"].map(lambda n: "Studio/1PN" if n <= 1 else f"{int(n)}PN" if n <= 3 else "4PN+" if n == n else None)
    clean, outl = drop_outliers(act)

    city = stats(clean.assign(TP="TP.HCM"), ["TP"])
    by_zone = stats(clean, ["Vùng"])
    by_area = stats(clean, ["Khu vực"])
    by_ward = stats(clean, ["Khu vực", "Phường"])
    by_proj = stats(clean.dropna(subset=["Mã dự án"]), ["Mã dự án", "Tên Chung cư/ Dự án", "Khu vực"], min_n=2)
    by_room = stats(clean, ["Khu vực", "Loại căn"])
    gr = growth(hist)
    sup = supply(ROOT)
    pyear = projects_by_year(proj)
    notes = pd.DataFrame({"Mục": [
        "Ngày dữ liệu", "Tin đang đăng có giá", "Tin bị loại vì giá bất thường", "Cách loại",
        "Khu vực", "Tăng trưởng", "Lưu ý"], "Giá trị": [
        date, len(act), len(outl), "Ngoài 1,5 IQR giá/m² trong từng khu vực (khu có ≥8 tin)",
        "Quận/huyện cũ; Quận 2, 9, Thủ Đức gộp thành TP Thủ Đức",
        "Từ sheet Lich_su_gia: snapshot hằng tuần của Agent 1 + số liệu báo cáo công khai",
        "Giá là giá chào bán trên tin đăng, không phải giá giao dịch thực tế"]})

    out_dir = os.path.join(ROOT, "phan_tich")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"BDS_HCM_phan_tich_{date}.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        for name, df in [("Ghi_chu", notes), ("Toan_TP", city), ("Theo_vung", by_zone), ("Theo_quan_cu", by_area),
                         ("Theo_phuong", by_ward), ("Theo_du_an", by_proj), ("Theo_loai_can", by_room),
                         ("Tang_truong_gia", gr), ("Nguon_cung", sup), ("Du_an_theo_nam", pyear),
                         ("Tin_bi_loai", outl[["ID tin", "Tên Chung cư/ Dự án", "Khu vực", "Giá (tỷ VNĐ)", "Diện tích (m2)", PRICE, "Link bài đăng"]])]:
            df.to_excel(xw, sheet_name=name, index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                w = max(len(str(c.value or "")) for c in list(col)[:60])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 40)
    shutil.copyfile(out, os.path.join(out_dir, "BDS_HCM_phan_tich_latest.xlsx"))

    summary = {"ngay": date, "toan_tp": city.drop(columns=["TP", "Độ tin cậy"]).iloc[0].to_dict(),
               "quan": by_area.astype({"Độ tin cậy": str}).to_dict("records"),
               "phuong": by_ward.astype({"Độ tin cậy": str}).to_dict("records")}
    with open(os.path.join(out_dir, "khu_vuc.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, default=float)
    print(f"Xong: {len(clean)} tin dùng để tính, {len(outl)} tin bị loại -> {out}")
    print(by_area[["Khu vực", "Số tin", "Giá/m² trung vị"]].head(8).to_string(index=False))

if __name__ == "__main__":
    main()
