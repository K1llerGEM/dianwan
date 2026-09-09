import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://store.steampowered.com/search/results/?filter=newreleases&sort_by=Released_DESC&cc=cn&l=schinese&count=10&format=json"
resp = requests.get(url, verify=False)

# 把整个网页交给 BeautifulSoup，整理成"可以查的结构"
soup = BeautifulSoup(resp.text, "html.parser")

# 找到所有游戏卡片（search_result_row = 一张游戏卡片）
games = soup.select("a.search_result_row")

for g in games:
    name = g.select_one(".title")
    date = g.select_one(".search_released")

    # 价格部分（上一轮新改的）：
    # 找价格格子时，老名字和新名字都试
    price = g.select_one(".search_price, .search_price_discount_combined")

    if price:
        # 优先取"最终价"，没有就整块文字（比如"免费"）
        final = price.select_one(".discount_final_price")
        price_text = final.text.strip() if final else price.text.strip()
    else:
        price_text = "?"

    print("游戏名:", name.text.strip() if name else "?")
    print("日期:", date.text.strip() if date else "?")
    print("价格:", price_text)
    print("链接:", g.get("href"))
    print("-" * 40)
