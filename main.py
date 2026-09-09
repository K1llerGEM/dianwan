import os
import re
import time
import sqlite3
import ctypes
import urllib3
import requests
from datetime import datetime
from bs4 import BeautifulSoup

urllib3.disable_warnings()

# ---------- 数据目录：系统文档文件夹 / Dao ----------
def get_documents_dir():
    try:
        buf = ctypes.c_wchar_p()
        FOLDERID_Documents = "FDD39AD0-238F-46AF-ADB4-6C85480369C7"
        res = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.c_wchar_p(FOLDERID_Documents), 0, None, ctypes.byref(buf))
        if res == 0:
            path = buf.value
            ctypes.windll.ole32.CoTaskMemFree(buf)
            return path
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Documents")

DATA_DIR = os.path.join(get_documents_dir(), "Dao")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "games.db")

# ---------- 各数据源抓取上限 ----------
MAX_STEAM = 300
MAX_3DM = 40
MAX_GAMERSKY = 120
MAX_PRICE_LOOKUP = 100      # 最多给 100 个第三方游戏补价

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

def http_get(url):
    return requests.get(url, headers=HEADERS, verify=False, timeout=30)

# ---------- 日期格式化 ----------
def normalize_date(s):
    nums = re.findall(r"\d+", s)
    if len(nums) < 3 or len(nums[0]) != 4:
        return ""
    year, month, day = nums[0], nums[1].zfill(2), nums[2].zfill(2)
    try:
        datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{year}-{month}-{day}"

# ---------- Steam 价格 ----------
def get_price(block):
    node = block.select_one(".search_price_discount_combined") or block.select_one(".search_price")
    if node is None:
        return "?"
    final = node.select_one(".discount_final_price")
    if final:
        return final.get_text(strip=True)
    text = node.get_text(" ", strip=True)
    return text if text else "免费"

# ---------- 抓取月份 ----------
def current_next_months():
    today = datetime.now()
    months = [(today.year, today.month)]
    y, m = today.year, today.month + 1
    if m > 12:
        m, y = 1, y + 1
    months.append((y, m))
    return months

# ========== 数据源 1：Steam 热门新游 ==========
def fetch_steam():
    rows = []
    seen = set()
    start = 0
    while len(rows) < MAX_STEAM and start < 6000:
        url = ("https://store.steampowered.com/search/results/?filter=popularnew"
               f"&cc=cn&l=schinese&count=25&format=json&start={start}")
        try:
            resp = http_get(url)
        except Exception:
            break
        if resp.status_code != 200:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        blocks = soup.select("a[data-ds-appid]")
        if not blocks:
            break
        for block in blocks:
            name_node = block.select_one(".title")
            if not name_node:
                continue
            name = name_node.get_text(strip=True)
            if not name or "demo" in name.lower() or name in seen:
                continue
            rel = block.select_one(".search_released")
            date_str = normalize_date(rel.get_text(strip=True)) if rel else ""
            if not date_str:
                continue
            seen.add(name)
            rows.append((name, date_str, get_price(block), block.get("href", "")))
            if len(rows) >= MAX_STEAM:
                break
        start += 25
        time.sleep(0.5)
    return rows

# ========== 数据源 2：3DM 月度发售表 ==========
def fetch_3dm():
    rows = []
    seen = set()
    for y, m in current_next_months():
        for page in range(1, 3):
            suffix = "" if page == 1 else f"_{page}"
            url = f"https://www.3dmgame.com/release/pc{y}{m:02d}{suffix}/"
            try:
                resp = http_get(url)
            except Exception:
                break
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            got = False
            for item in soup.select("div.lis"):
                a = item.select_one(".bt a")
                if not a:
                    continue
                name = a.get_text(strip=True)
                date_str = ""
                for row in item.select(".row"):
                    lab = row.select_one(".label")
                    if lab and "发行时间" in lab.get_text():
                        val = row.select_one(".val")
                        date_str = normalize_date(val.get_text(strip=True)) if val else ""
                        break
                if not name or not date_str or name in seen:
                    continue
                seen.add(name)
                rows.append((name, date_str, "—", a.get("href", "")))
                got = True
            if not got:
                break
            time.sleep(0.5)
    return rows

# ========== 数据源 3：游民星空月度发售表 ==========
def fetch_gamersky():
    rows = []
    seen = set()
    for y, m in current_next_months():
        url = f"https://ku.gamersky.com/release/pc_{y}{m:02d}/"
        try:
            resp = http_get(url)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        soup = BeautifulSoup(resp.text, "html.parser")
        for li in soup.select("ul.PF li.lx1")[:MAX_GAMERSKY]:
            a = li.select_one(".tit a")
            if not a:
                continue
            name = a.get_text(strip=True)
            date_str = ""
            for t in li.select(".txt"):
                m2 = re.match(r"发行日期：\s*(\d{4}-\d{2}-\d{2})", t.get_text(strip=True))
                if m2:
                    date_str = m2.group(1)
                    break
            if not name or not date_str or name in seen:
                continue
            seen.add(name)
            rows.append((name, date_str, "—", a.get("href", "")))
        time.sleep(0.5)
    return rows

# ========== 第三方补价：Steam 商店搜索接口 ==========
PRICE_CACHE = {}

def steam_search_price(name):
    """按游戏名在 Steam 商店搜索，返回 '¥xx.xx'；找不到返回空串"""
    if name in PRICE_CACHE:
        return PRICE_CACHE[name]
    result = ""
    try:
        resp = requests.get(
            "https://store.steampowered.com/api/storesearch/",
            params={"term": name, "cc": "cn", "l": "schinese"},
            headers=HEADERS, verify=False, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("items") or []:
                if item.get("type") == "app":
                    price = (item.get("price") or {}).get("final")
                    if price is not None:
                        result = f"¥{price / 100:.2f}"
                        break
    except Exception:
        pass
    PRICE_CACHE[name] = result
    return result

# ========== 汇总入库 ==========
SOURCES = [
    ("steam",    fetch_steam,    MAX_STEAM),
    ("3dm",      fetch_3dm,      MAX_3DM),
    ("gamersky", fetch_gamersky, MAX_GAMERSKY),
]

def update_data():
    all_rows = []      # [name, date, price, url, rank, week, source]
    rank = 0
    for source, fetcher, _max in SOURCES:
        try:
            rows = fetcher()
        except Exception:
            rows = []
        for name, date_str, price, url in rows:
            rank += 1
            week = datetime.strptime(date_str, "%Y-%m-%d").weekday()
            all_rows.append([name, date_str, price, url, rank, week, source])

    # 给 3DM / 游民 的游戏补价格
    looked = 0
    for row in all_rows:
        if row[6] == "steam":
            continue
        if looked >= MAX_PRICE_LOOKUP:
            break
        if not row[2] or row[2] in ("—", "未定价"):
            p = steam_search_price(row[0])
            if p:
                row[2] = p
            looked += 1
            time.sleep(0.15)

    if not all_rows:
        print("本次未抓到数据，保留原有数据")
        return 0

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("DROP TABLE IF EXISTS games")
    conn.execute("CREATE TABLE games (name TEXT, date TEXT, price TEXT, url TEXT, "
                 "rank INTEGER, week INTEGER, source TEXT)")
    conn.executemany("INSERT INTO games VALUES (?,?,?,?,?,?,?)", all_rows)
    conn.commit()
    conn.close()
    steam_n = sum(1 for r in all_rows if r[6] == "steam")
    d3_n = sum(1 for r in all_rows if r[6] == "3dm")
    gs_n = sum(1 for r in all_rows if r[6] == "gamersky")
    print(f"更新完成，共 {len(all_rows)} 款游戏（Steam {steam_n} / 3DM {d3_n} / 游民 {gs_n}）")
    return len(all_rows)