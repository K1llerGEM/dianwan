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
    """获取 Windows 真正的"文档"文件夹（自动适配中文系统/重定向）"""
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

MAX_GAMES = 300      # 想抓更多就调大
STEP = 25

# ---------- 日期格式化：各种写法统一成 2026-09-09 ----------
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

# ---------- 价格 ----------
def get_price(block):
    node = block.select_one(".search_price_discount_combined") or block.select_one(".search_price")
    if node is None:
        return "?"
    final = node.select_one(".discount_final_price")
    if final:
        return final.get_text(strip=True)
    text = node.get_text(" ", strip=True)
    return text if text else "免费"

# ---------- 抓取并入库 ----------
def update_data():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("DROP TABLE IF EXISTS games")
    conn.execute("CREATE TABLE games (name TEXT, date TEXT, price TEXT, url TEXT, rank INTEGER, week INTEGER)")

    seen = set()
    rank = 0
    count = 0
    start = 0

    while count < MAX_GAMES and start < 6000:
        url = ("https://store.steampowered.com/search/results/?filter=popularnew"
               f"&cc=cn&l=schinese&count={STEP}&format=json&start={start}")
        try:
            resp = requests.get(url, verify=False, timeout=15)
        except Exception:
            time.sleep(2)
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
            if not name or "demo" in name.lower():
                continue
            if name in seen:
                continue
            seen.add(name)

            rel = block.select_one(".search_released")
            date_str = normalize_date(rel.get_text(strip=True)) if rel else ""
            if not date_str:
                continue

            rank += 1
            price = get_price(block)
            href = block.get("href", "")
            week = datetime.strptime(date_str, "%Y-%m-%d").weekday()
            conn.execute(
                "INSERT INTO games (name, date, price, url, rank, week) VALUES (?,?,?,?,?,?)",
                (name, date_str, price, href, rank, week))
            count += 1
            if count >= MAX_GAMES:
                break
        start += STEP
        time.sleep(0.5)

    conn.commit()
    conn.close()
    print(f"更新完成，共 {count} 款游戏")
