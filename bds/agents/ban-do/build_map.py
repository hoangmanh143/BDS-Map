#!/usr/bin/env python3
"""Agent 4: xuất dữ liệu cho trang bản đồ tĩnh (Leaflet + OpenStreetMap).

Đọc  raw_data/BDS_HCM_raw_latest.xlsx, phan_tich/khu_vuc.json, tin_quy_hoach/tin_quy_hoach.geojson
Ghi  web/index.html (chép từ template cạnh script, chỉ khi chưa có hoặc --force-html)
     web/data/listings.json, web/data/meta.json, web/data/news.geojson

  python3 build_map.py
  python3 build_map.py --force-html     # ghi đè index.html bằng bản template mới
Xem thử: cd <BDS_ROOT>/web && python3 -m http.server 8000  -> http://localhost:8000
"""
import argparse, json, os, shutil

import pandas as pd

ROOT = os.environ.get("BDS_ROOT", "/mnt/project-files/bds")
HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
PRICE = "Giá đơn vị (Triệu VNĐ/ m2)"
AREA_ALIAS = {"Quận 2": "TP Thủ Đức", "Quận 9": "TP Thủ Đức", "Quận Thủ Đức": "TP Thủ Đức",
              "Thành phố Thủ Đức": "TP Thủ Đức"}

# Thứ tự trường trong mỗi tin (mảng gọn để file nhẹ). index.html đọc theo đúng thứ tự này.
FIELDS = ["id", "src", "title", "proj", "projName", "ward", "area", "lat", "lng", "price", "ppm2",
          "size", "beds", "legal", "date", "url"]

def clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float):
        return round(v, 6) if abs(v) < 1000 and v != int(v) else (int(v) if v == int(v) else round(v, 2))
    return v

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-html", action="store_true")
    args = ap.parse_args()
    os.makedirs(os.path.join(WEB, "data"), exist_ok=True)

    tin = pd.read_excel(os.path.join(ROOT, "raw_data", "BDS_HCM_raw_latest.xlsx"), sheet_name="Tin_dang")
    t = tin[(tin["Trạng thái tin"] == "Đang đăng") & tin["Vĩ độ"].notna() & tin["Giá (tỷ VNĐ)"].notna()].copy()
    t = t[t["Vĩ độ"].between(10.3, 11.2) & t["Kinh độ"].between(106.3, 107.1)]  # bỏ tọa độ ngoài HCM
    t["area"] = t["Quận/Huyện cũ"].map(lambda v: AREA_ALIAS.get(v, v))
    t["date"] = pd.to_datetime(t["Ngày đăng bán"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
    rows = []
    for _, r in t.iterrows():
        rows.append([clean(x) for x in [
            r["ID tin"], r["Nguồn"], r["Tiêu đề tin"], r["Mã dự án"], r["Tên Chung cư/ Dự án"], r["Phường"],
            r["area"], r["Vĩ độ"], r["Kinh độ"], r["Giá (tỷ VNĐ)"], r[PRICE], r["Diện tích (m2)"],
            r["Số phòng ngủ"], r["Pháp lý"], r["date"], r["Link bài đăng"]]])
    with open(os.path.join(WEB, "data", "listings.json"), "w", encoding="utf-8") as f:
        json.dump({"fields": FIELDS, "rows": rows}, f, ensure_ascii=False, separators=(",", ":"))

    meta = {"updated": pd.to_datetime(tin["Ngày thu thập"], dayfirst=True).max().strftime("%d/%m/%Y"),
            "count": len(rows), "areas": sorted(t["area"].dropna().unique().tolist()),
            "sources": sorted(t["Nguồn"].dropna().unique().tolist()),
            "legal": sorted(t["Pháp lý"].dropna().unique().tolist())}
    kv = os.path.join(ROOT, "phan_tich", "khu_vuc.json")
    if os.path.exists(kv):
        with open(kv, encoding="utf-8") as f:
            meta["khu_vuc"] = json.load(f)
    with open(os.path.join(WEB, "data", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, default=float)

    news = os.path.join(ROOT, "tin_quy_hoach", "tin_quy_hoach.geojson")
    shutil.copyfile(news, os.path.join(WEB, "data", "news.geojson")) if os.path.exists(news) else \
        json.dump({"type": "FeatureCollection", "features": []}, open(os.path.join(WEB, "data", "news.geojson"), "w"))

    html = os.path.join(WEB, "index.html")
    if args.force_html or not os.path.exists(html):
        shutil.copyfile(os.path.join(HERE, "index.html"), html)
    print(f"Xong: {len(rows)} tin có tọa độ, {t['Mã dự án'].nunique()} dự án -> {WEB}")

if __name__ == "__main__":
    main()
