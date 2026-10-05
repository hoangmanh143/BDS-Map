#!/usr/bin/env python3
"""Agent 3: kho tin quy hoạch, hạ tầng, giải tỏa, chính sách ảnh hưởng giá BĐS TP.HCM.

Claude tìm tin bằng WebSearch/WebFetch, ghi mỗi tin một dòng JSON vào
  tin_quy_hoach/raw/<YYYY-MM-DD>.jsonl
rồi chạy:
  python3 news.py build
Kết quả: tin_quy_hoach/tin_quy_hoach.xlsx (gộp mọi tuần, chống trùng theo link)
         tin_quy_hoach/tin_quy_hoach.geojson (tin có tọa độ, cho lớp bản đồ)
"""
import argparse, glob, json, os

import pandas as pd

ROOT = os.environ.get("BDS_ROOT", "/mnt/project-files/bds")
DIR = os.path.join(ROOT, "tin_quy_hoach")
COLS = ["Ngày tin", "Tiêu đề", "Loại", "Tóm tắt", "Khu vực ảnh hưởng", "Phường", "Quận/Huyện cũ",
        "Vĩ độ", "Kinh độ", "Tác động dự kiến", "Mức độ", "Mốc thời gian", "Trạng thái dự án",
        "Nguồn", "Link", "Ngày thu thập"]
LOAI = {"Hạ tầng giao thông", "Quy hoạch", "Giải tỏa - tái định cư", "Dự án lớn", "Chính sách", "Thị trường"}
TAC_DONG = {"Tăng", "Giảm", "Trung tính"}

def build(args):
    rows = []
    for p in sorted(glob.glob(os.path.join(DIR, "raw", "*.jsonl"))):
        day = os.path.basename(p)[:-6]
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    r.setdefault("Ngày thu thập", day)
                    rows.append(r)
    if not rows:
        raise SystemExit(f"Chưa có tin trong {DIR}/raw/")
    df = pd.DataFrame(rows).reindex(columns=COLS)
    bad = df[~df["Loại"].isin(LOAI) | ~df["Tác động dự kiến"].isin(TAC_DONG) | df["Link"].isna()]
    if len(bad):
        print(f"Cảnh báo: {len(bad)} tin sai Loại/Tác động hoặc thiếu Link:\n{bad[['Tiêu đề', 'Loại', 'Tác động dự kiến']].to_string()}")
    df = df.drop_duplicates("Link", keep="last")
    df["_d"] = pd.to_datetime(df["Ngày tin"], dayfirst=True, errors="coerce")
    df = df.sort_values("_d", ascending=False).drop(columns="_d")
    os.makedirs(DIR, exist_ok=True)
    out = os.path.join(DIR, "tin_quy_hoach.xlsx")
    summary = (df.assign(**{"Khu vực": df["Quận/Huyện cũ"].fillna(df["Khu vực ảnh hưởng"])})
                 .pivot_table(index="Khu vực", columns="Tác động dự kiến", values="Link", aggfunc="count", fill_value=0)
                 .reset_index())
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="Tin", index=False)
        summary.to_excel(xw, sheet_name="Theo_khu_vuc", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "B2"
            for col in ws.columns:
                w = max(len(str(c.value or "")) for c in list(col)[:60])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 50)
    geo = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r["Kinh độ"]), float(r["Vĩ độ"])]},
         "properties": {k: (None if pd.isna(r[k]) else r[k]) for k in ["Ngày tin", "Tiêu đề", "Loại", "Tóm tắt",
                        "Tác động dự kiến", "Mốc thời gian", "Link"]}}
        for _, r in df.dropna(subset=["Vĩ độ", "Kinh độ"]).iterrows()]}
    with open(os.path.join(DIR, "tin_quy_hoach.geojson"), "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False)
    print(f"Xong: {len(df)} tin ({len(geo['features'])} có tọa độ) -> {out}")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(fn=build)
    a = ap.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()
