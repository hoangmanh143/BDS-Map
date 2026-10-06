#!/usr/bin/env python3
"""Agent thu thập tin bán căn hộ / dự án TP.HCM.

Luồng:  thu thập (chotot | batdongsan | file JSONL do Claude gom bằng WebFetch)
        -> data/raw/<ngày>/*.jsonl
        -> build: chuẩn hóa theo template v2, chống trùng, so với tuần trước,
           cập nhật lịch sử giá, xuất xlsx.

Ví dụ:
  python3 collect.py chotot --max-pages 100
  python3 collect.py batdongsan --max-pages 700
  python3 collect.py batdongsan-projects --max-pages 72
  python3 collect.py geocode      # tra tọa độ dự án / đường (thay tọa độ tâm phường)
  python3 collect.py muaban | onehousing | homedy | bds123 | mogi | bdsvn   # nguồn bổ sung
  python3 collect.py build
"""
import argparse, datetime as dt, glob, json, os, re, sys, time, unicodedata

import pandas as pd

ROOT = os.environ.get("BDS_ROOT", "/mnt/project-files/bds")
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
SNAP = os.path.join(DATA, "snapshots")
OUT = os.path.join(ROOT, "raw_data")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# Cột sheet Tin_dang (template v2). Giữ đúng thứ tự.
LISTING_COLS = [
    "ID tin", "Nguồn", "Mã tin gốc", "Tiêu đề tin", "Tên Chung cư/ Dự án", "Mã dự án",
    "Loại hình", "Địa chỉ", "Số nhà", "Đường", "Phường", "Quận/Huyện cũ", "Thành phố",
    "Vĩ độ", "Kinh độ", "Giá (tỷ VNĐ)", "Giá ban đầu (tỷ VNĐ)", "Giá đơn vị (Triệu VNĐ/ m2)",
    "Diện tích (m2)", "Số phòng ngủ", "Số nhà vệ sinh", "Tầng", "Nội thất", "Pháp lý",
    "Người đăng", "Ngày đăng bán", "Ngày thu thập", "Lần đầu thấy", "Lần cuối thấy",
    "Trạng thái tin", "Link bài đăng",
]
PROJECT_COLS = [
    "Mã dự án", "Tên dự án", "Chủ đầu tư", "Địa chỉ", "Phường", "Quận/Huyện cũ", "Vĩ độ",
    "Kinh độ", "Quy mô", "Năm mở bán", "Năm bàn giao", "Giá mở bán (tr/m2)", "Tình trạng",
    "Số tin đang bán", "Giá TB hiện tại (tr/m2)", "Link nguồn",
]
HISTORY_COLS = [
    "Kỳ", "Cấp", "Tên", "Mã dự án", "Giá TB (tr/m2)", "Giá thấp nhất (tr/m2)",
    "Giá cao nhất (tr/m2)", "Số tin", "Nguồn", "Link nguồn",
]

# ---------------------------------------------------------------- helpers

def today():
    return os.environ.get("BDS_DATE") or dt.date.today().isoformat()

def slug(s):
    if s is None or (isinstance(s, float) and pd.isna(s)) or not str(s).strip():
        return None
    s = unicodedata.normalize("NFD", str(s).replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").upper()
    return s or None

def num(text):
    """'86,6 m²' -> 86.6 ; '1.250,5' -> 1250.5"""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = re.search(r"\d[\d.,]*", str(text))
    if not m:
        return None
    t = m.group(0)
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None

def price_ty(text):
    """'6,5 tỷ' -> 6.5 ; '850 triệu' -> 0.85 ; 'Thỏa thuận' -> None ; số VNĐ -> tỷ"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return round(text / 1e9, 4) if text > 1e5 else float(text)
    t = str(text).lower()
    if "thỏa" in t or "thoả" in t or "liên hệ" in t:
        return None
    v = num(t)
    if v is None:
        return None
    if "triệu" in t and "/m" not in t:
        return round(v / 1000, 4)
    return v

def relative_date(text, base):
    """'Đăng hôm nay' / 'hôm qua' / '3 ngày trước' / '05/10/2026' -> dd/mm/yyyy"""
    if not text:
        return None
    t = str(text).lower()
    b = dt.date.fromisoformat(base)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    if "hôm nay" in t or "phút" in t or "giờ" in t:
        d = b
    elif "hôm qua" in t:
        d = b - dt.timedelta(days=1)
    elif (m := re.search(r"(\d+)\s*ngày", t)):
        d = b - dt.timedelta(days=int(m.group(1)))
    elif (m := re.search(r"(\d+)\s*tuần", t)):
        d = b - dt.timedelta(weeks=int(m.group(1)))
    elif (m := re.search(r"(\d+)\s*tháng", t)):
        d = b - dt.timedelta(days=30 * int(m.group(1)))  # xấp xỉ
    else:
        return None
    return d.strftime("%d/%m/%Y")

def ms_date(ms):
    if not ms:
        return None
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone(dt.timedelta(hours=7))).strftime("%d/%m/%Y")

def clean_admin(name, prefixes):
    if not name:
        return None
    n = str(name).strip()
    for p in prefixes:
        if n.lower().startswith(p.lower()):
            n = n[len(p):].strip()
    return n or None

def old_district(name):
    """'Quận 7' giữ nguyên; 'Q. Bình Thạnh' -> 'Quận Bình Thạnh'; 'H. Bình Chánh' -> 'Huyện Bình Chánh'"""
    if not name:
        return None
    n = name.strip()
    n = re.sub(r"^Q\.\s*", "Quận ", n)
    n = re.sub(r"^H\.\s*", "Huyện ", n)
    n = re.sub(r"^TP\.\s*", "Thành phố ", n)
    return n

def parse_bds_location(text):
    """'Quận 7 (P. Phú Thuận mới)' -> ('Quận 7', 'Phú Thuận')"""
    if not text:
        return None, None
    m = re.match(r"\s*(.*?)\s*\((?:P\.|X\.|Phường|Xã|ĐK\.)\s*(.*?)\s*mới\)", str(text))
    if m:
        return old_district(m.group(1)), m.group(2)
    return old_district(str(text).split(",")[-1]), None

def http_get(url, params=None, retries=3):
    import requests
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=30)
            if r.status_code == 200:
                return r
            print(f"  HTTP {r.status_code} {url}", file=sys.stderr)
        except Exception as e:  # mạng chập chờn hoặc bị chặn
            print(f"  lỗi {e.__class__.__name__}: {e}", file=sys.stderr)
        time.sleep(2 ** (i + 1))
    raise SystemExit(f"Không tải được {url}. Nếu bị proxy chặn (403), dùng chế độ WebFetch trong SKILL.md.")

def raw_dir(date):
    d = os.path.join(RAW, date)
    os.makedirs(d, exist_ok=True)
    return d

def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Ghi {len(rows)} dòng -> {path}")

# ---------------------------------------------------------------- collectors

def collect_chotot(args):
    """API công khai của Chợ Tốt / Nhà Tốt. region_v2=13000 (HCM), cg=1010 (căn hộ), st=s (bán)."""
    url = "https://gateway.chotot.com/v1/public/ad-listing"
    rows, page = [], 0
    while page < args.max_pages:
        r = http_get(url, {"region_v2": args.region, "cg": 1010, "st": "s",
                           "limit": 50, "o": page * 50})
        js = r.json()
        ads = js.get("ads", [])
        if not ads:
            break
        rows.extend(ads)
        page += 1
        print(f"  chotot trang {page}: {len(rows)}/{js.get('total')}")
        time.sleep(args.delay)
    write_jsonl(os.path.join(raw_dir(today()), "chotot_api.jsonl"), rows)

def collect_batdongsan(args):
    """Trang danh sách batdongsan.com.vn, 20 tin/trang.
    LƯU Ý: bộ chọn CSS viết theo cấu trúc trang 2025-2026, chưa chạy thử trực tiếp
    (sandbox bị chặn mạng). Nếu số tin = 0, kiểm tra lại class trong HTML."""
    from bs4 import BeautifulSoup
    base = "https://batdongsan.com.vn/ban-can-ho-chung-cu-tp-hcm"
    rows = []
    for p in range(1, args.max_pages + 1):
        html = http_get(base if p == 1 else f"{base}/p{p}").text
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div.js__card, div.re__card-full")
        if not cards:
            break
        for c in cards:
            a = c.select_one("a.js__product-link-for-product-id, a[href*='-pr']")
            href = a.get("href") if a else None
            pid = (c.get("prid") or (a.get("data-product-id") if a else None)
                   or (re.search(r"-pr(\d+)", href or "") or [None, None])[1])
            def txt(sel):
                e = c.select_one(sel)
                return e.get_text(" ", strip=True) if e else None
            rows.append({
                "url": ("https://batdongsan.com.vn" + href) if href and href.startswith("/") else href,
                "product_id": pid,
                "title": txt(".js__card-title, .re__card-title"),
                "project": txt(".re__card-config-project, .re__project-title"),
                "price_text": txt(".re__card-config-price"),
                "area_text": txt(".re__card-config-area"),
                "price_per_m2_text": txt(".re__card-config-price_per_m2"),
                "bedrooms": num(txt(".re__card-config-bedroom")),
                "toilets": num(txt(".re__card-config-toilet")),
                "location_text": txt(".re__card-location"),
                "posted_text": txt(".re__card-published-info-published-at, .re__card-contact-button-info"),
            })
        print(f"  batdongsan trang {p}: {len(rows)}")
        time.sleep(args.delay)
    write_jsonl(os.path.join(raw_dir(today()), "batdongsan_html.jsonl"), rows)

def collect_bds_projects(args):
    from bs4 import BeautifulSoup
    base = "https://batdongsan.com.vn/du-an-can-ho-chung-cu-tp-hcm"
    rows = []
    for p in range(1, args.max_pages + 1):
        soup = BeautifulSoup(http_get(base if p == 1 else f"{base}/p{p}").text, "html.parser")
        cards = soup.select("div.js__project-card, div.re__prj-card-full")
        if not cards:
            break
        for c in cards:
            a = c.select_one("a[href*='-pj']")
            def txt(sel):
                e = c.select_one(sel)
                return e.get_text(" ", strip=True) if e else None
            rows.append({
                "name": txt(".re__prj-card-title, h3"),
                "url": ("https://batdongsan.com.vn" + a["href"]) if a else None,
                "developer": txt(".re__prj-card-contact-name, .re__prj-card-developer"),
                "address": txt(".re__prj-card-location, .re__prj-card-address"),
                "price_text": txt(".re__prj-card-config-value"),
                "status": txt(".re__prj-tag-info, .re__prj-card-status"),
                "area_scale": txt(".re__prj-card-config"),
            })
        print(f"  dự án trang {p}: {len(rows)}")
        time.sleep(args.delay)
    write_jsonl(os.path.join(raw_dir(today()), "batdongsan_projects.jsonl"), rows)

# ---------------------------------------------------------------- nguồn bổ sung (thêm 05/10/2026)
# Các trang dưới đây không chặn truy cập tự động (đã kiểm tra robots.txt cho phép trang danh sách).
# Mỗi bộ thu thập ghi thẳng bản ghi theo tên cột template -> norm_generic trong build.
# Tên file JSONL không được bắt đầu bằng "chotot"/"batdongsan" (sẽ bị đọc nhầm kiểu).

OLD_DISTRICT_NAMES = {
    "Bình Thạnh": "Quận Bình Thạnh", "Gò Vấp": "Quận Gò Vấp", "Phú Nhuận": "Quận Phú Nhuận",
    "Tân Bình": "Quận Tân Bình", "Tân Phú": "Quận Tân Phú", "Bình Tân": "Quận Bình Tân",
    "Bình Chánh": "Huyện Bình Chánh", "Hóc Môn": "Huyện Hóc Môn", "Củ Chi": "Huyện Củ Chi",
    "Nhà Bè": "Huyện Nhà Bè", "Cần Giờ": "Huyện Cần Giờ", "Thủ Đức": "Thành phố Thủ Đức",
}

def vn_price_ty(text):
    """'9 tỷ 200 triệu' -> 9.2 ; '3,35 Tỷ' -> 3.35 ; '850 triệu' -> 0.85 ; tin thuê ('/tháng') -> None"""
    if text is None:
        return None
    t = str(text).lower()
    if "/th" in t or "thỏa" in t or "thoả" in t or "liên hệ" in t:
        return None
    ty = re.search(r"(\d[\d.,]*)\s*tỷ", t)
    tr = re.search(r"(\d[\d.,]*)\s*triệu", t)
    v = (num(ty.group(1)) if ty else 0) + ((num(tr.group(1)) or 0) / 1000 if tr else 0)
    return round(v, 4) if v else None

def split_address(text):
    """Tách (phường, quận cũ) từ chuỗi địa chỉ tự do; quận cũ None nếu không nhận ra."""
    if not text:
        return None, None
    t = str(text)
    ward = re.search(r"(?:Phường|Xã|P\.)\s*([^,\-]+)", t)
    ward = ward.group(1).strip() if ward else None
    dist = None
    m = re.search(r"(?:Quận|Q\.)\s*(\d{1,2})\b", t)
    if m:
        dist = f"Quận {int(m.group(1))}"
    elif re.search(r"Thủ Đức", t):
        dist = "Thành phố Thủ Đức"
    else:
        for k, v in OLD_DISTRICT_NAMES.items():
            if re.search(rf"(?:Quận|Huyện|Q\.|H\.|^|,)\s*{k}\s*(?:,|$)", t):
                dist = v
                break
    return ward, dist

def listing(src, prefix, sid, **kw):
    r = {"ID tin": f"{prefix}-{sid}", "Nguồn": src, "Mã tin gốc": str(sid), "Loại hình": "Căn hộ",
         "Thành phố": "Hồ Chí Minh"}
    r.update({k: v for k, v in kw.items() if v is not None})
    return r

def soup_of(url):
    from bs4 import BeautifulSoup
    return BeautifulSoup(http_get(url).text, "html.parser")

def next_data(url):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', http_get(url).text, re.S)
    return json.loads(m.group(1)) if m else {}

def is_rent(title):
    return bool(title and re.search(r"cho thuê|thuê", title, re.I) and not re.search(r"\bbán\b", title, re.I))

def pages(args, fetch_page, out_name):
    """Gọi fetch_page(p) -> list bản ghi, dừng khi trang rỗng hoặc lặp lại trang trước."""
    rows, seen = [], set()
    for p in range(1, args.max_pages + 1):
        try:
            got = fetch_page(p)
        except SystemExit as e:
            print(f"  dừng ở trang {p}: {e}", file=sys.stderr)
            break
        new = [r for r in got if r["ID tin"] not in seen]
        if not new:
            break
        seen.update(r["ID tin"] for r in new)
        rows += new
        print(f"  {out_name} trang {p}: {len(rows)}")
        time.sleep(args.delay)
    write_jsonl(os.path.join(raw_dir(today()), f"{out_name}.jsonl"), rows)

def collect_muaban(args):
    base = "https://muaban.net/bat-dong-san/ban-can-ho-chung-cu-ho-chi-minh"
    def page(p):
        items = (next_data(base if p == 1 else f"{base}?page={p}").get("props", {}).get("pageProps", {})
                 .get("classified", {}).get("items", []))
        out = []
        for it in items:
            attrs = " ".join(a.get("value", "") for a in it.get("attributes") or [])
            locs = [l.get("name") for l in it.get("locations_display") or []]
            ward, dist = split_address(", ".join(x for x in locs if x))
            pr = it.get("price")
            out.append(listing("Muaban", "MB", it["id"],
                **{"Tiêu đề tin": it.get("title"), "Địa chỉ": it.get("location"),
                   "Phường": ward, "Quận/Huyện cũ": dist,
                   "Giá (tỷ VNĐ)": round(pr / 1e9, 4) if pr else None,
                   "Diện tích (m2)": num(re.search(r"[\d.,]+\s*m²", attrs).group(0)) if "m²" in attrs else None,
                   "Số phòng ngủ": num(re.search(r"(\d+)\s*PN", attrs).group(1)) if re.search(r"\d+\s*PN", attrs) else None,
                   "Số nhà vệ sinh": num(re.search(r"(\d+)\s*WC", attrs).group(1)) if re.search(r"\d+\s*WC", attrs) else None,
                   "Người đăng": "Môi giới" if it.get("is_company") else "Cá nhân",
                   "Ngày đăng bán": dt.date.fromisoformat(it["publish_at"][:10]).strftime("%d/%m/%Y") if it.get("publish_at") else None,
                   "Link bài đăng": "https://muaban.net" + it["url"] if it.get("url") else None}))
        return out
    pages(args, page, "muaban")

def collect_onehousing(args):
    """OneHousing trả căn hộ toàn quốc; chỉ giữ TP.HCM."""
    base = "https://onehousing.vn/mua-ban-can-ho-chung-cu-ho-chi-minh"
    def page(p):
        data = (next_data(base if p == 1 else f"{base}?page={p}").get("props", {}).get("pageProps", {})
                .get("inventory", {}).get("data", []))
        out = []
        for it in data:
            hcm = "hồ chí minh" in (it.get("province") or "").lower()
            geo = it.get("geolocation") or {}
            pr = it.get("min_selling_price")
            wc = it.get("number_of_bathrooms")
            ts = it.get("last_modified_date")
            r = listing("OneHousing", "OH", it.get("inventory_code") or it["id"],
                **{"Tiêu đề tin": " ".join(x for x in [it.get("project_name"), it.get("block_name"), it.get("property_code")] if x),
                   "Tên Chung cư/ Dự án": it.get("project_name"),
                   "Địa chỉ": ", ".join(x for x in [it.get("ward"), it.get("district"), it.get("province")] if x),
                   "Phường": clean_admin(it.get("ward"), ["P. ", "Phường ", "X. ", "Xã "]),
                   "Quận/Huyện cũ": old_district(it.get("district")) if it.get("district") else None,
                   "Vĩ độ": geo.get("lat_cdnt"), "Kinh độ": geo.get("long_cdnt"),
                   "Giá (tỷ VNĐ)": round(pr / 1e9, 4) if pr else None,
                   "Diện tích (m2)": it.get("min_area"), "Số phòng ngủ": it.get("number_of_bedrooms"),
                   "Số nhà vệ sinh": wc[0] if isinstance(wc, list) and wc else wc,
                   "Tầng": it.get("floor_number"), "Nội thất": it.get("furniture_status"),
                   "Người đăng": "Sàn OneHousing",
                   "Ngày đăng bán": ms_date(int(ts)) if ts else None,
                   "Link bài đăng": f"https://onehousing.vn/mua-ban-can-ho-chung-cu-ho-chi-minh?code={it.get('inventory_code')}"})
            r["_hcm"] = hcm
            out.append(r)
        return out
    rows_all = []
    def keep(p):
        got = page(p)
        rows_all.extend(got)
        return got
    pages(args, keep, "onehousing_all")
    rows = [{k: v for k, v in r.items() if k != "_hcm"} for r in rows_all if r["_hcm"]]
    os.remove(os.path.join(raw_dir(today()), "onehousing_all.jsonl"))
    write_jsonl(os.path.join(raw_dir(today()), "onehousing.jsonl"), rows)

def collect_homedy(args):
    base = "https://homedy.com/ban-can-ho-tp-ho-chi-minh"
    def page(p):
        out = []
        for c in soup_of(base if p == 1 else f"{base}/p{p}").select("div.product-item"):
            a = c.select_one("a.title")
            if not a:
                continue
            href = a.get("href", "")
            sid = re.search(r"-es(\d+)", href)
            addr = c.select_one("li.address")
            addr = addr.get("title") or addr.get_text(" ", strip=True) if addr else None
            ward, dist = split_address(addr)
            title = a.get("title") or a.get_text(" ", strip=True)
            proj = re.match(r"/ban-can-ho-([^/]+)/", href)
            t = lambda s: (c.select_one(s).get_text(" ", strip=True) if c.select_one(s) else None)
            out.append(listing("Homedy", "HD", sid.group(1) if sid else href,
                **{"Tiêu đề tin": title, "Địa chỉ": addr, "Phường": ward, "Quận/Huyện cũ": dist,
                   "Tên Chung cư/ Dự án": proj.group(1).replace("-", " ").title() if proj else None,
                   "Giá (tỷ VNĐ)": vn_price_ty(t("span.price")), "Diện tích (m2)": num(t("span.acreage")),
                   "Số phòng ngủ": num(re.search(r"(\d+)\s*PN", title, re.I).group(1)) if re.search(r"\d+\s*PN", title, re.I) else None,
                   "Ngày đăng bán": relative_date(t("div.time"), today()),
                   "Link bài đăng": "https://homedy.com" + href}))
        return out
    pages(args, page, "homedy")

def collect_bds123(args):
    base = "https://bds123.vn/ban-can-ho-chung-cu-ho-chi-minh.html"
    def page(p):
        out = []
        for c in soup_of(base if p == 1 else f"{base}?page={p}").select("article.post-listing"):
            a = c.select_one("h3.post-title a")
            if not a:
                continue
            href = a.get("href", "")
            sid = re.search(r"-pr(\d+)", href)
            loc = c.select_one("span.line-row-1")
            loc = loc.get_text(" ", strip=True) if loc else None
            proj = loc.split(" - ")[0].strip() if loc and " - " in loc else None
            ward, dist = split_address(loc)
            price = c.select_one("span[aria-label^='Giá']")
            area = c.select_one("span[aria-label^='Diện tích']")
            bed = c.select_one("span[aria-label^='Số phòng ngủ']")
            tm = c.select_one("time")
            posted = re.search(r"(\d{2}/\d{2}/\d{4})", tm.get("title", "")) if tm else None
            out.append(listing("Bds123", "B123", sid.group(1) if sid else href,
                **{"Tiêu đề tin": a.get("title"), "Tên Chung cư/ Dự án": proj, "Địa chỉ": loc,
                   "Phường": ward, "Quận/Huyện cũ": dist,
                   "Giá (tỷ VNĐ)": vn_price_ty(price.get("aria-label")) if price else None,
                   "Diện tích (m2)": num(area.get_text()) if area else None,
                   "Số phòng ngủ": num(bed.get_text()) if bed else None,
                   "Ngày đăng bán": posted.group(1) if posted else None,
                   "Link bài đăng": "https://bds123.vn" + href if href.startswith("/") else href}))
        return out
    pages(args, page, "bds123")

def collect_mogi(args):
    base = "https://mogi.vn/ho-chi-minh/mua-can-ho-chung-cu"
    def page(p):
        out = []
        for c in soup_of(base if p == 1 else f"{base}?cp={p}").select("div.prop-info"):
            a = c.select_one("a.link-overlay")
            title = c.select_one(".prop-title").get_text(" ", strip=True) if c.select_one(".prop-title") else None
            if not a or is_rent(title):
                continue
            href = a.get("href", "")
            sid = re.search(r"-id(\d+)", href)
            attrs = [li.get_text(" ", strip=True) for li in c.select("ul.prop-attr li")]
            addr = c.select_one(".prop-addr").get_text(" ", strip=True) if c.select_one(".prop-addr") else None
            ward, dist = split_address(addr)
            li = c.find_parent("li")
            created = li.select_one(".prop-created").get_text(strip=True) if li and li.select_one(".prop-created") else None
            pick = lambda pat: next((num(x) for x in attrs if re.search(pat, x)), None)
            out.append(listing("Mogi", "MG", sid.group(1) if sid else href,
                **{"Tiêu đề tin": title, "Địa chỉ": addr, "Phường": ward, "Quận/Huyện cũ": dist,
                   "Giá (tỷ VNĐ)": vn_price_ty(c.select_one(".price").get_text(" ", strip=True)) if c.select_one(".price") else None,
                   "Diện tích (m2)": pick(r"m"), "Số phòng ngủ": pick(r"PN"), "Số nhà vệ sinh": pick(r"WC"),
                   "Ngày đăng bán": relative_date(created, today()), "Link bài đăng": href}))
        return out
    pages(args, page, "mogi")

def collect_bdsvn(args):
    """batdongsan.vn (trang khác, KHÔNG phải batdongsan.com.vn)."""
    base = "https://batdongsan.vn/ban-can-ho-chung-cu-ho-chi-minh"
    def page(p):
        out = []
        for a in soup_of(f"{base}/" if p == 1 else f"{base}/p{p}").select("a.card-cm"):
            href = a.get("href", "")
            sid = re.search(r"-r(\d+)$", href)
            t = lambda s: (a.select_one(s).get_text(" ", strip=True) if a.select_one(s) else None)
            title = t("h3.title")
            if is_rent(title):
                continue
            addr = re.sub(r"\s+", " ", t("div.description") or "").strip() or None
            ward, dist = split_address(addr)
            tags = [d.get_text(" ", strip=True) for d in a.select("div.description-item")]
            pick = lambda pat: next((num(x) for x in tags if re.search(pat, x)), None)
            out.append(listing("Batdongsan.vn", "BVN", sid.group(1) if sid else href,
                **{"Tiêu đề tin": title, "Địa chỉ": addr, "Phường": ward, "Quận/Huyện cũ": dist,
                   "Giá (tỷ VNĐ)": vn_price_ty(t("div.price")),
                   "Diện tích (m2)": pick(r"m²"), "Số phòng ngủ": pick(r"Phòng ngủ|PN"), "Số nhà vệ sinh": pick(r"WC"),
                   "Ngày đăng bán": relative_date(t("div.time"), today()), "Link bài đăng": href}))
        return out
    pages(args, page, "bdsvn")

EXTRA_SOURCES = {"Muaban", "OneHousing", "Homedy", "Bds123", "Mogi", "Batdongsan.vn"}

def fill_district_from_ward(df):
    """Nguồn bổ sung thường chỉ ghi phường mới: suy ra quận cũ từ cặp phường mới -> quận cũ của Chotot.
    Tin nguồn bổ sung vẫn không rõ quận cũ (thường là Bình Dương / BR-VT nay thuộc TP.HCM) bị loại."""
    ref = df[df["Nguồn"] == "Chotot"].dropna(subset=["Phường", "Quận/Huyện cũ"])
    wmap = ref.groupby(ref["Phường"].map(slug))["Quận/Huyện cũ"].agg(lambda s: s.mode().iloc[0]).to_dict()
    miss = df["Quận/Huyện cũ"].isna()
    df.loc[miss, "Quận/Huyện cũ"] = df.loc[miss, "Phường"].map(slug).map(wmap)
    drop = df["Nguồn"].isin(EXTRA_SOURCES) & df["Quận/Huyện cũ"].isna()
    if drop.any():
        print(f"  loại {drop.sum()} tin nguồn bổ sung không xác định được quận cũ")
    df = df[~drop]
    # Mogi/Homedy... còn giữ tin đăng từ 2024 ở các trang sâu: giá cũ, không phải giá chào bán hiện tại.
    posted = pd.to_datetime(df["Ngày đăng bán"], format="%d/%m/%Y", errors="coerce")
    stale = df["Nguồn"].isin(EXTRA_SOURCES) & (posted < pd.Timestamp(today()) - pd.Timedelta(days=STALE_DAYS))
    if stale.any():
        print(f"  loại {stale.sum()} tin nguồn bổ sung đăng quá {STALE_DAYS} ngày")
    return df[~stale]

STALE_DAYS = 180

# ---------------------------------------------------------------- normalizers

# Mã -> nhãn chỉ dùng khi tin không kèm feature_params (chế độ WebFetch). Mã chưa rõ giữ dạng "Chotot mã n".
CHOTOT_FURNISH = {1: "Nội thất cao cấp"}
CHOTOT_LEGAL = {2: "Đang chờ sổ"}

def code_label(table, v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return table.get(v, f"Chotot mã {v}")

def chotot_feature(ad, key):
    for grp in (ad.get("feature_params") or {}).values():
        for it in grp.get("items", []):
            if it.get("id") == key:
                return it.get("value")
    return None

def norm_chotot(ad, date):
    price = price_ty(ad.get("price"))
    size = num(ad.get("size"))
    proj = ad.get("pty_project_name") or None
    district = ad.get("area_name")
    return {
        "ID tin": f"CT-{ad['list_id']}", "Nguồn": "Chotot", "Mã tin gốc": str(ad["list_id"]),
        "Tiêu đề tin": ad.get("subject"),
        "Tên Chung cư/ Dự án": re.sub(r"\s*-\s*(Quận|Huyện|TP)\b.*$", "", proj) if proj else None,
        "Loại hình": "Căn hộ",
        "Địa chỉ": ", ".join(x for x in [ad.get("street_name"), ad.get("ward_name_v3"), "Hồ Chí Minh"] if x),
        "Số nhà": None, "Đường": clean_admin(ad.get("street_name"), ["Đường "]),
        "Phường": clean_admin(ad.get("ward_name_v3"), ["Phường ", "Xã ", "Đặc khu "]),
        "Quận/Huyện cũ": district, "Thành phố": "Hồ Chí Minh",
        "Vĩ độ": ad.get("latitude"), "Kinh độ": ad.get("longitude"),
        "Giá (tỷ VNĐ)": price, "Giá ban đầu (tỷ VNĐ)": price_ty(ad.get("original_price")),
        "Diện tích (m2)": size, "Số phòng ngủ": ad.get("rooms"), "Số nhà vệ sinh": ad.get("toilets"),
        "Tầng": ad.get("floornumber"),
        "Nội thất": chotot_feature(ad, "furnishing_sell") or code_label(CHOTOT_FURNISH, ad.get("furnishing_sell")),
        "Pháp lý": chotot_feature(ad, "property_legal_document") or code_label(CHOTOT_LEGAL, ad.get("property_legal_document")),
        "Người đăng": "Môi giới" if ad.get("company_ad") else "Cá nhân",
        "Ngày đăng bán": ms_date(ad.get("orig_list_time") or ad.get("list_time")),
        "Link bài đăng": f"https://www.nhatot.com/{ad['list_id']}.htm",
    }

def norm_bds(r, date):
    district, ward = parse_bds_location(r.get("location_text"))
    pid = r.get("product_id") or (re.search(r"-pr(\d+)", r.get("url") or "") or [None, None])[1]
    return {
        "ID tin": f"BDS-{pid}", "Nguồn": "Batdongsan", "Mã tin gốc": str(pid),
        "Tiêu đề tin": r.get("title"), "Tên Chung cư/ Dự án": r.get("project"),
        "Loại hình": "Căn hộ",
        "Địa chỉ": ", ".join(x for x in [ward, district, "Hồ Chí Minh"] if x),
        "Phường": ward, "Quận/Huyện cũ": district, "Thành phố": "Hồ Chí Minh",
        "Giá (tỷ VNĐ)": price_ty(r.get("price_text")), "Diện tích (m2)": num(r.get("area_text")),
        "Số phòng ngủ": num(r.get("bedrooms")), "Số nhà vệ sinh": num(r.get("toilets")),
        "Ngày đăng bán": relative_date(r.get("posted_text"), date),
        "Link bài đăng": r.get("url"),
    }

def norm_generic(r, date):
    """Bản ghi đã theo tên cột template (nguồn Google / web khác / nhập tay)."""
    out = {k: r.get(k) for k in LISTING_COLS if k in r}
    out.setdefault("Nguồn", "Google")
    if not out.get("ID tin"):
        key = out.get("Link bài đăng") or out.get("Tiêu đề tin")
        out["ID tin"] = "WEB-" + str(abs(hash(key)) % 10**10)
    out["Giá (tỷ VNĐ)"] = price_ty(out.get("Giá (tỷ VNĐ)"))
    out["Diện tích (m2)"] = num(out.get("Diện tích (m2)"))
    return out

def load_raw(date):
    rows, projects, history = [], [], []
    for path in sorted(glob.glob(os.path.join(RAW, date, "*.jsonl"))):
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            recs = [json.loads(l) for l in f if l.strip()]
        if name.startswith("chotot"):
            rows += [norm_chotot(r, date) for r in recs if r.get("list_id")]
        elif name.startswith("batdongsan_projects"):
            projects += recs
        elif name.startswith("batdongsan"):
            rows += [norm_bds(r, date) for r in recs if r.get("url") or r.get("product_id")]
        elif name.startswith("price_history"):
            history += recs
        else:
            rows += [norm_generic(r, date) for r in recs]
        print(f"  đọc {len(recs):>5} dòng  {name}")
    return rows, projects, history

# ---------------------------------------------------------------- build

# Phạm vi đã chốt: TP.HCM cũ (22 quận/huyện trước 1/7/2025). Tin của Bình Dương, Bà Rịa-Vũng Tàu bị loại.
OLD_HCM = {slug(x) for x in [
    "Quận 1", "Quận 3", "Quận 4", "Quận 5", "Quận 6", "Quận 7", "Quận 8", "Quận 10", "Quận 11", "Quận 12",
    "Quận 2", "Quận 9", "Thành phố Thủ Đức", "Quận Thủ Đức", "Quận Bình Thạnh", "Quận Gò Vấp",
    "Quận Phú Nhuận", "Quận Tân Bình", "Quận Tân Phú", "Quận Bình Tân", "Huyện Bình Chánh",
    "Huyện Hóc Môn", "Huyện Củ Chi", "Huyện Nhà Bè", "Huyện Cần Giờ"]}

def in_scope(district):
    if district is None or (isinstance(district, float) and pd.isna(district)):
        return True  # chưa rõ quận thì giữ, kiểm tra tay
    return slug(district) in OLD_HCM

def finish_listing(df, date):
    df = df.reindex(columns=LISTING_COLS)
    df["Ngày thu thập"] = pd.to_datetime(date).strftime("%d/%m/%Y")
    df["Mã dự án"] = df["Tên Chung cư/ Dự án"].map(slug)
    alias_path = os.path.join(DATA, "project_aliases.csv")  # cột: alias, ma_du_an (sửa tay khi 2 nguồn ghi tên khác nhau)
    if os.path.exists(alias_path):
        al = pd.read_csv(alias_path)
        amap = dict(zip(al["alias"].map(slug), al["ma_du_an"]))
        df["Mã dự án"] = df["Mã dự án"].map(lambda k: amap.get(k, k))
    ok = df["Giá (tỷ VNĐ)"].notna() & (df["Diện tích (m2)"] > 0)
    df.loc[ok, "Giá đơn vị (Triệu VNĐ/ m2)"] = (
        df.loc[ok, "Giá (tỷ VNĐ)"] * 1000 / df.loc[ok, "Diện tích (m2)"]).round(2)
    # loại giá vô lý (đơn vị nhập sai, giá thuê lẫn vào...)
    bad = (df["Giá đơn vị (Triệu VNĐ/ m2)"] < 10) | (df["Giá đơn vị (Triệu VNĐ/ m2)"] > 1000)
    df.loc[bad, "Giá đơn vị (Triệu VNĐ/ m2)"] = None
    return df.drop_duplicates("ID tin", keep="last")

def fill_from_projects(df):
    """Tin thiếu tọa độ / phường lấy theo trung vị các tin cùng dự án."""
    known = df.dropna(subset=["Mã dự án"])
    agg = known.groupby("Mã dự án").agg(
        lat=("Vĩ độ", "median"), lng=("Kinh độ", "median"),
        ward=("Phường", lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None),
        dist=("Quận/Huyện cũ", lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None))
    for col, src in [("Vĩ độ", "lat"), ("Kinh độ", "lng"), ("Phường", "ward"), ("Quận/Huyện cũ", "dist")]:
        df[col] = df[col].fillna(df["Mã dự án"].map(agg[src]))
    return df

def update_master(snap, date):
    path = os.path.join(DATA, "master.csv")
    if os.path.exists(path):
        master = pd.read_csv(path, dtype={"Mã tin gốc": str})
    else:
        master = pd.DataFrame(columns=LISTING_COLS)
    seen = set(snap["ID tin"])
    d = pd.to_datetime(date).strftime("%d/%m/%Y")
    first = dict(zip(master["ID tin"], master["Lần đầu thấy"]))
    snap = snap.copy()
    snap["Lần đầu thấy"] = snap["ID tin"].map(first).fillna(d)
    snap["Lần cuối thấy"] = d
    snap["Trạng thái tin"] = "Đang đăng"
    gone = master[~master["ID tin"].isin(seen)].copy()
    gone["Trạng thái tin"] = "Đã gỡ"
    sources_now = set(snap["Nguồn"])
    # chỉ đánh dấu "Đã gỡ" cho nguồn có chạy tuần này; nguồn không chạy giữ nguyên trạng thái
    gone.loc[~gone["Nguồn"].isin(sources_now), "Trạng thái tin"] = master.set_index("ID tin").loc[
        gone.loc[~gone["Nguồn"].isin(sources_now), "ID tin"], "Trạng thái tin"].values
    out = pd.concat([snap, gone], ignore_index=True).reindex(columns=LISTING_COLS)
    out.to_csv(path, index=False)
    return out

def build_history(external):
    rows = []
    for path in sorted(glob.glob(os.path.join(SNAP, "*.csv"))):
        period = os.path.basename(path)[:-4]
        s = pd.read_csv(path)
        p = s["Giá đơn vị (Triệu VNĐ/ m2)"]
        s = s[p.notna()]
        for level, col in [("Dự án", "Mã dự án"), ("Phường", "Phường"), ("Quận cũ", "Quận/Huyện cũ")]:
            g = s.dropna(subset=[col]).groupby(col)["Giá đơn vị (Triệu VNĐ/ m2)"]
            names = s.dropna(subset=[col]).groupby(col)["Tên Chung cư/ Dự án"].first() if level == "Dự án" else None
            for key, ser in g:
                rows.append({"Kỳ": period, "Cấp": level,
                             "Tên": names[key] if names is not None else key,
                             "Mã dự án": key if level == "Dự án" else None,
                             "Giá TB (tr/m2)": round(ser.mean(), 2), "Giá thấp nhất (tr/m2)": round(ser.min(), 2),
                             "Giá cao nhất (tr/m2)": round(ser.max(), 2), "Số tin": len(ser),
                             "Nguồn": "Snapshot tin đăng"})
        allp = s["Giá đơn vị (Triệu VNĐ/ m2)"]
        if len(allp):
            rows.append({"Kỳ": period, "Cấp": "Toàn TP", "Tên": "TP.HCM", "Giá TB (tr/m2)": round(allp.mean(), 2),
                         "Giá thấp nhất (tr/m2)": round(allp.min(), 2), "Giá cao nhất (tr/m2)": round(allp.max(), 2),
                         "Số tin": len(allp), "Nguồn": "Snapshot tin đăng"})
    ext_path = os.path.join(DATA, "price_history_external.csv")
    ext = pd.read_csv(ext_path) if os.path.exists(ext_path) else pd.DataFrame(columns=HISTORY_COLS)
    if external:
        ext = pd.concat([ext, pd.DataFrame(external)], ignore_index=True).reindex(columns=HISTORY_COLS)
        ext = ext.drop_duplicates(["Kỳ", "Cấp", "Tên", "Nguồn"], keep="last")
        ext.to_csv(ext_path, index=False)
    hist = pd.concat([pd.DataFrame(rows), ext], ignore_index=True).reindex(columns=HISTORY_COLS)
    return hist.sort_values(["Cấp", "Tên", "Kỳ"])

def build_projects(master, bds_projects):
    path = os.path.join(DATA, "projects.csv")
    proj = pd.read_csv(path) if os.path.exists(path) else pd.DataFrame(columns=PROJECT_COLS)
    new = []
    for p in bds_projects:
        district, ward = None, None
        addr = p.get("address") or ""
        m = re.search(r"(Phường|Xã)\s+([^,]+)", addr)
        if m:
            ward = m.group(2).strip()
        m = re.search(r"(Quận|Huyện)\s+([^,]+)", addr)
        if m:
            district = f"{m.group(1)} {m.group(2).strip()}"
        new.append({"Mã dự án": slug(p.get("name")), "Tên dự án": p.get("name"),
                    "Chủ đầu tư": p.get("developer"), "Địa chỉ": addr, "Phường": ward,
                    "Quận/Huyện cũ": district, "Quy mô": p.get("area_scale"),
                    "Giá mở bán (tr/m2)": num(p.get("price_text")) if p.get("price_text") else None,
                    "Tình trạng": p.get("status"), "Link nguồn": p.get("url")})
    if new:
        proj = pd.concat([proj, pd.DataFrame(new)], ignore_index=True)
    active = master[master["Trạng thái tin"] == "Đang đăng"].dropna(subset=["Mã dự án"])
    g = active.groupby("Mã dự án")
    derived = pd.DataFrame({
        "Tên dự án": g["Tên Chung cư/ Dự án"].first(),
        "Phường": g["Phường"].agg(lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None),
        "Quận/Huyện cũ": g["Quận/Huyện cũ"].agg(lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None),
        "Vĩ độ": g["Vĩ độ"].median(), "Kinh độ": g["Kinh độ"].median(),
        "Số tin đang bán": g.size(),
        "Giá TB hiện tại (tr/m2)": g["Giá đơn vị (Triệu VNĐ/ m2)"].mean().round(2),
    }).reset_index()
    proj = proj.drop_duplicates("Mã dự án", keep="last").set_index("Mã dự án")
    derived = derived.set_index("Mã dự án")
    proj = proj.reindex(proj.index.union(derived.index))
    for c in ["Số tin đang bán", "Giá TB hiện tại (tr/m2)"]:
        proj[c] = derived[c]
    for c in ["Tên dự án", "Phường", "Quận/Huyện cũ", "Vĩ độ", "Kinh độ"]:
        proj[c] = proj[c].fillna(derived[c])
    proj = proj.reset_index().reindex(columns=PROJECT_COLS)
    proj.to_csv(path, index=False)
    return proj

def build(args):
    date = args.date or today()
    print(f"Build ngày {date}")
    rows, bds_projects, external = load_raw(date)
    if not rows:
        raise SystemExit(f"Không có dữ liệu thô trong {os.path.join(RAW, date)}")
    snap = fill_district_from_ward(fill_from_projects(finish_listing(pd.DataFrame(rows), date)))
    keep = snap["Quận/Huyện cũ"].map(in_scope)
    if (~keep).any():
        print(f"  loại {(~keep).sum()} tin ngoài TP.HCM cũ: {sorted(snap.loc[~keep, 'Quận/Huyện cũ'].unique())[:10]}")
    snap = snap[keep]
    os.makedirs(SNAP, exist_ok=True)
    snap.to_csv(os.path.join(SNAP, f"{date}.csv"), index=False)
    master = update_master(snap, date)
    master = apply_geocode_cache(fill_from_projects(master))
    projects = apply_geocode_cache(build_projects(master, bds_projects))
    history = build_history(external)
    stats = (master.groupby(["Nguồn", "Trạng thái tin"]).size().rename("Số tin").reset_index())
    stats.loc[len(stats)] = ["Tổng", "", len(master)]

    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, f"BDS_HCM_raw_{date}.xlsx")
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE  # ký tự điều khiển trong tiêu đề tin làm hỏng xlsx
    clean = lambda d: d.apply(lambda c: c.map(lambda v: ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v))
    master, projects, history = clean(master), clean(projects), clean(history)
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        master.to_excel(xw, sheet_name="Tin_dang", index=False)
        projects.to_excel(xw, sheet_name="Du_an", index=False)
        history.to_excel(xw, sheet_name="Lich_su_gia", index=False)
        stats.to_excel(xw, sheet_name="Thong_ke", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "B2"
            for col in ws.columns:
                w = max(len(str(c.value or "")) for c in list(col)[:50])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, w + 2), 45)
    latest = os.path.join(OUT, "BDS_HCM_raw_latest.xlsx")
    import shutil
    shutil.copyfile(out, latest)
    print(f"Xong: {len(master)} tin ({(master['Trạng thái tin']=='Đang đăng').sum()} đang đăng), "
          f"{len(projects)} dự án, {len(history)} dòng lịch sử giá -> {out}")

# ---------------------------------------------------------------- geocode

HCM_BOX = (10.35, 11.17, 106.35, 107.05)  # khung TP.HCM cũ (lat min, lat max, lng min, lng max)
GEO_COLS = ["ma_du_an", "lat", "lng", "query", "nguon", "loai", "ket_qua"]
MANUAL_GEO = "toa_do_tay.csv"   # sửa tay: ma_du_an,lat,lng,ghi_chu (vd tọa độ lấy từ Google Maps), ưu tiên cao nhất

def street_key(street, ward):
    return f"DUONG|{slug(street)}|{slug(ward)}"

def is_centroid(df):
    """Tọa độ nguồn chỉ là tâm phường/khu: một điểm dùng chung cho >=2 dự án khác nhau
    hoặc >=3 tin không có dự án (Chotot/Homedy đặt mặc định khi người đăng không ghim vị trí)."""
    pt = df["Vĩ độ"].round(4).astype(str) + "," + df["Kinh độ"].round(4).astype(str)
    has = df["Vĩ độ"].notna()
    g = df[has].groupby(pt[has])
    shared = (g["Mã dự án"].nunique() >= 2) | (g["Mã dự án"].agg(lambda s: s.isna().sum()) >= 3)
    return has & pt.map(shared).fillna(False).astype(bool)

def _nominatim(q, ua, want):
    """Trả (lat, lng, mô tả) nếu kết quả nằm trong TP.HCM cũ và đúng loại (want='du_an' | 'duong')."""
    import requests
    r = requests.get("https://nominatim.openstreetmap.org/search", headers=ua, timeout=30,
                     params={"q": q, "format": "jsonv2", "limit": 5, "countrycodes": "vn"})
    if r.status_code == 429:
        raise RuntimeError("429")
    for js in (r.json() if r.status_code == 200 else []):
        lat, lng = float(js["lat"]), float(js["lon"])
        if not (HCM_BOX[0] <= lat <= HCM_BOX[1] and HCM_BOX[2] <= lng <= HCM_BOX[3]):
            continue
        cat, typ = js.get("category", ""), js.get("type", "")
        if want == "duong" and cat == "highway":
            return lat, lng, f"{cat}/{typ}"
        # dự án: chỉ nhận tòa nhà / khu dân cư; bỏ ranh giới phường, đường, quán, trường... trùng tên
        if want == "du_an" and (cat == "building" or (cat == "landuse" and typ in ("residential", "construction"))):
            return lat, lng, f"{cat}/{typ}"
    return None

def geocode(args):
    """Tra tọa độ chính xác hơn tọa độ nguồn (Nominatim/OpenStreetMap, ~1 yêu cầu/giây theo quy định):
    1. Mọi dự án đang có tin (theo tên dự án, rồi "Chung cư <tên>"): tọa độ tìm được sẽ THAY tọa độ nguồn,
       vì Chotot/Homedy hay đặt nhiều dự án chung một điểm tâm phường.
    2. Tin không thuộc dự án: tra "<đường>, <phường>" để đặt ít nhất đúng con đường.
    Kết quả lưu data/geocode_cache.csv (cả lần không tìm thấy, để tuần sau không tra lại)."""
    cache_path = os.path.join(DATA, "geocode_cache.csv")
    cache = pd.read_csv(cache_path) if os.path.exists(cache_path) else pd.DataFrame(columns=GEO_COLS)
    cache = cache.reindex(columns=GEO_COLS)
    cache["loai"] = cache["loai"].fillna("du_an")
    done = set(cache["ma_du_an"]) if not args.retry else set(cache.dropna(subset=["lat"])["ma_du_an"])
    master = pd.read_csv(os.path.join(DATA, "master.csv"), low_memory=False)
    act = master[master["Trạng thái tin"] == "Đang đăng"]
    todo = []
    pr = act.dropna(subset=["Mã dự án"]).groupby("Mã dự án").agg(
        name=("Tên Chung cư/ Dự án", "first"), n=("ID tin", "size"),
        ward=("Phường", lambda s: s.dropna().mode().iloc[0] if s.notna().any() else None))
    for code, p in pr.sort_values("n", ascending=False).iterrows():   # dự án nhiều tin tra trước
        if code not in done and isinstance(p["name"], str):
            name = re.sub(r"^(chung cư|căn hộ|dự án|khu căn hộ)\s+", "", p["name"].strip(), flags=re.I)
            qs = [f"{name}, {p['ward']}, Hồ Chí Minh" if p["ward"] else None, f"{name}, Hồ Chí Minh",
                  f"Chung cư {name}, Hồ Chí Minh"]
            todo.append((code, "du_an", [q for q in qs if q]))
    st = act[act["Mã dự án"].isna() & act["Đường"].notna() & act["Phường"].notna()]
    for (street, ward), _ in st.groupby(["Đường", "Phường"]).size().sort_values(ascending=False).items():
        key = street_key(street, ward)
        if key not in done:
            todo.append((key, "duong", [f"{street}, {ward}, Hồ Chí Minh"]))
    ua = {"User-Agent": "bds-hcm-collector/1.0 (personal research; weekly batch)"}  # Nominatim yêu cầu UA riêng
    new = []
    try:
        for key, kind, qs in todo[:args.limit]:
            hit = None
            for q in qs:
                hit = _nominatim(q, ua, kind)
                time.sleep(1.1)
                if hit:
                    break
            new.append({"ma_du_an": key, "lat": hit[0] if hit else None, "lng": hit[1] if hit else None,
                        "query": q, "nguon": "Nominatim", "loai": kind, "ket_qua": hit[2] if hit else None})
            if len(new) % 50 == 0:
                print(f"  {len(new)}/{min(len(todo), args.limit)}", file=sys.stderr)
    except RuntimeError:
        print("  Nominatim báo quá tải (429), dừng; lần sau chạy tiếp từ chỗ dừng.", file=sys.stderr)
    except Exception as e:  # mất mạng giữa chừng: vẫn lưu phần đã tra
        print(f"  Lỗi mạng ({e}), lưu phần đã tra.", file=sys.stderr)
    if new:
        cache = pd.concat([cache, pd.DataFrame(new)], ignore_index=True).drop_duplicates("ma_du_an", keep="last")
        cache.to_csv(cache_path, index=False)
    hits = sum(n["lat"] is not None for n in new)
    print(f"Tra được {hits}/{len(new)} mục đã thử (còn {len(todo) - len(new)} chưa thử). "
          f"Chạy lại build để áp tọa độ.")

def apply_geocode_cache(df):
    """Áp tọa độ đã tra: sửa tay > dự án (Nominatim) > đường (chỉ cho tin không dự án có tọa độ trống/tâm phường)."""
    path = os.path.join(DATA, "geocode_cache.csv")
    c = pd.read_csv(path).reindex(columns=GEO_COLS) if os.path.exists(path) else pd.DataFrame(columns=GEO_COLS)
    c["loai"] = c["loai"].fillna("du_an")
    c = c.dropna(subset=["lat", "lng"])
    man = os.path.join(DATA, MANUAL_GEO)
    if os.path.exists(man):
        m = pd.read_csv(man).dropna(subset=["ma_du_an", "lat", "lng"])
        c = pd.concat([c, m.assign(loai="du_an", nguon="Sửa tay")], ignore_index=True)
    c = c.drop_duplicates("ma_du_an", keep="last").set_index("ma_du_an")
    c[["lat", "lng"]] = c[["lat", "lng"]].apply(pd.to_numeric, errors="coerce").astype(float)  # concat có thể ra object
    proj = c[c["loai"] == "du_an"]
    hit = df["Mã dự án"].isin(proj.index)
    df.loc[hit, "Vĩ độ"] = df.loc[hit, "Mã dự án"].map(proj["lat"])
    df.loc[hit, "Kinh độ"] = df.loc[hit, "Mã dự án"].map(proj["lng"])
    if "Đường" in df.columns:
        strt = c[c["loai"] == "duong"]
        key = pd.Series([street_key(s, w) if isinstance(s, str) and isinstance(w, str) else None
                         for s, w in zip(df["Đường"], df["Phường"])], index=df.index)
        weak = df["Mã dự án"].isna() & (df["Vĩ độ"].isna() | is_centroid(df)) & key.isin(strt.index)
        df.loc[weak, "Vĩ độ"] = key[weak].map(strt["lat"])
        df.loc[weak, "Kinh độ"] = key[weak].map(strt["lng"])
    return df

# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, pages in [("chotot", collect_chotot, 100), ("batdongsan", collect_batdongsan, 700),
                            ("batdongsan-projects", collect_bds_projects, 72),
                            ("muaban", collect_muaban, 80), ("onehousing", collect_onehousing, 80),
                            ("homedy", collect_homedy, 1000), ("bds123", collect_bds123, 1000),
                            ("mogi", collect_mogi, 1000), ("bdsvn", collect_bdsvn, 300)]:
        p = sub.add_parser(name)
        p.add_argument("--max-pages", type=int, default=pages)
        p.add_argument("--delay", type=float, default=1.5, help="giây nghỉ giữa các trang")
        p.add_argument("--region", default="13000", help="Chotot region_v2 (13000 = HCM)")
        p.set_defaults(fn=fn)
    g = sub.add_parser("geocode")
    g.add_argument("--limit", type=int, default=1500)
    g.add_argument("--retry", action="store_true", help="tra lại cả mục lần trước không tìm thấy")
    g.set_defaults(fn=geocode)
    b = sub.add_parser("build")
    b.add_argument("--date", help="YYYY-MM-DD, mặc định hôm nay")
    b.set_defaults(fn=build)
    args = ap.parse_args()
    args.fn(args)

if __name__ == "__main__":
    main()
