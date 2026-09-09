import sqlite3

conn = sqlite3.connect("games.db")

rows = conn.execute("SELECT name, date, price, url FROM games ORDER BY date DESC").fetchall()

for row in rows:
    print(row[0], "——", row[1], "——", row[2])
