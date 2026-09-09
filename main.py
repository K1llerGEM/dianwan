import re
import time
import sqlite3
from datetime import datetime
import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = ("https://store.steampowered.com/search/results/?filter=popularnew"
            "&cc=cn&l=schinese&count=25&format=json&start={start}")
MAX_GAMES = 300          # 想抓更多就调大这个数（“无限”的旋钮）
STEP = 25

def fetch_page(start):
    resp = requests.get(BASE_URL.format(start=start), verify=False, timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup.select("a.search_result_row")

def parse_date(text):
    nums = re.findall(r"\d+", text)
    if len(nums) >= 3:
        return f"{nums[0]}-{nums[1].zfill(2)}-{nums[2].zfill(2)}"
    return None

def weekday_of(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").weekday()   # 周一=0 … 周日=6
    except Exception:
        return -1

def update_data():
    conn = sqlite3.connect("games.db", timeout=10)
    conn.execute("DROP TABLE IF EXISTS games")
    conn.execute("CREATE TABLE games (name TEXT, date TEXT, price TEXT, url TEXT, rank INTEGER, week INTEGER)")
    conn.execute("DELETE FROM games")        # 每次全量刷新，热门榜保持最新

    rank = 0
    seen = set()
    start = 0
    while rank < MAX_GAMES and start <= MAX_GAMES:
        rows = fetch_page(start)
        if not rows:
            break
        for g in rows:
            name_el = g.select_one(".title")
            if name_el is None:
                continue
            name_text = name_el.text.strip()
            if "Demo" in name_text or name_text in seen:
                continue
            seen.add(name_text)

            date_text = ""
            date_el = g.select_one(".search_released")
            if date_el:
                d = parse_date(date_el.text.strip())
                date_text = d if d else date_el.text.strip()

            price_el = g.select_one(".search_price, .search_price_discount_combined")
            price_text = "?"
            if price_el:
                final = price_el.select_one(".discount_final_price")
                price_text = final.text.strip() if final else price_el.text.strip().replace("\n", " ").strip()
            url_text = g.get("href") or ""

            rank += 1
            week = weekday_of(date_text)
            conn.execute("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)",
                         (name_text, date_text, price_text, url_text, rank, week))
        start += STEP
        time.sleep(0.5)      # 礼貌抓取，防止被 Steam 限流

    conn.commit()
    conn.close()
    print(f"更新完成，共 {rank} 款游戏（按热门排序）")

if __name__ == "__main__":
    update_data()
