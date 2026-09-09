import json
import os
import sqlite3
import threading
import ctypes
import calendar as cal
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk
from main import update_data, DB_PATH, DATA_DIR

# ---------- 配置 ----------
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
PAGE_SIZE = 10
ROW_H = 48
BG_COLOR = "#1E1E2E"
ACTIVE_BG = "#4A4A6A"
CARD_BG = "#26263A"
TEXT_WHITE = "#ECECF4"
TEXT_GRAY = "#9A9AB0"
PRICE_GREEN = "#8FD6AE"
BAR_BG = "#1E1E2E"
SENTINEL = "#010203"
WEEK_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
HAS_GAME_BG = "#2E5E4E"

# ---------- 毛玻璃 ----------
def enable_acrylic(hwnd):
    class ACCENT_POLICY(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_uint), ("AccentFlags", ctypes.c_uint),
                    ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_uint)]
    class WINCOMPATTRDATA(ctypes.Structure):
        _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p),
                    ("SizeOfData", ctypes.c_size_t)]
    accent = ACCENT_POLICY()
    accent.AccentState = 4
    accent.AccentFlags = 2
    accent.GradientColor = 0xCC1E1E2E
    data = WINCOMPATTRDATA()
    data.Attribute = 19
    data.Data = ctypes.addressof(accent)
    data.SizeOfData = ctypes.sizeof(accent)
    return ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))

# ---------- 设置 ----------
def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings():
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)
    except Exception:
        pass

settings = load_settings()

# ---------- 窗口 ----------
root = tk.Tk()
root.overrideredirect(True)
root.title("电玩之道")
WIN_W, WIN_H = 440, 650
root.geometry(f"{WIN_W}x{WIN_H}+{settings.get('x', 100)}+{settings.get('y', 100)}")

pinned = settings.get("pinned", True)
root.attributes("-topmost", pinned)

hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
if enable_acrylic(hwnd):
    BG = SENTINEL
    root.attributes("-transparentcolor", SENTINEL)
else:
    BG = BG_COLOR
    root.attributes("-alpha", 0.94)
root.configure(bg=BG)

# ---------- 顶栏 ----------
bar = tk.Frame(root, bg=BAR_BG, height=36)
bar.pack(fill="x")
bar.pack_propagate(False)

tk.Label(bar, text="电玩之道", bg=BAR_BG, fg=TEXT_WHITE,
         font=("Microsoft YaHei", 11, "bold")).pack(side="left", padx=10)

def toggle_pin():
    global pinned
    pinned = not pinned
    root.attributes("-topmost", pinned)
    pin_btn.config(text="取消固定" if pinned else "固定")
    settings["pinned"] = pinned
    save_settings()

pin_btn = tk.Button(bar, text="取消固定" if pinned else "固定", command=toggle_pin,
                    bg=BAR_BG, fg=TEXT_WHITE, relief="flat", font=("Microsoft YaHei", 9),
                    activebackground="#3A3A55", borderwidth=0, highlightthickness=0)
pin_btn.pack(side="right", padx=4, pady=4)

def close_app():
    settings["x"] = root.winfo_x()
    settings["y"] = root.winfo_y()
    save_settings()
    root.destroy()

close_btn = tk.Button(bar, text="×", command=close_app, bg=BAR_BG, fg="#E06C75",
                      relief="flat", font=("Microsoft YaHei", 12, "bold"),
                      activebackground="#3A3A55", borderwidth=0, highlightthickness=0)
close_btn.pack(side="right", padx=(4, 8), pady=4)

def start_move(e):
    root._dx = e.x_root - root.winfo_x()
    root._dy = e.y_root - root.winfo_y()

def on_move(e):
    if pinned:
        return
    root.geometry(f"+{e.x_root - root._dx}+{e.y_root - root._dy}")

def stop_move(e):
    settings["x"] = root.winfo_x()
    settings["y"] = root.winfo_y()
    save_settings()

bar.bind("<Button-1>", start_move)
bar.bind("<B1-Motion>", on_move)
bar.bind("<ButtonRelease-1>", stop_move)

# ---------- 数据状态 ----------
state = {"date": datetime.now().strftime("%Y-%m-%d"), "page": 0, "total_pages": 1}

today = datetime.now()
week_start = today - timedelta(days=today.weekday())
week_dates = [week_start + timedelta(days=i) for i in range(7)]

# ---------- 周一~周日 + 日历按钮 ----------
week_frame = tk.Frame(root, bg=BG)
week_frame.pack(fill="x", padx=10, pady=(8, 2))

week_btns = []

def select_weekday(i):
    state["date"] = week_dates[i].strftime("%Y-%m-%d")
    state["page"] = 0
    date_label.config(text=f"正在看：{state['date']}")
    load_page()

for i in range(7):
    b = tk.Button(week_frame, text=f"{WEEK_NAMES[i]}\n{week_dates[i].strftime('%m-%d')}",
                  command=lambda idx=i: select_weekday(idx),
                  bg="#26263A", fg=TEXT_WHITE, relief="flat",
                  font=("Microsoft YaHei", 8), activebackground=ACTIVE_BG,
                  borderwidth=0, highlightthickness=0)
    b.pack(side="left", expand=True, fill="x", padx=1)
    week_btns.append(b)

cal_btn = tk.Button(week_frame, text="日\n历", command=lambda: open_calendar(),
                    bg="#26263A", fg=TEXT_WHITE, relief="flat",
                    font=("Microsoft YaHei", 9), activebackground=ACTIVE_BG,
                    borderwidth=0, highlightthickness=0)
cal_btn.pack(side="left", padx=(2, 0))

def refresh_week_btns():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        rows = conn.execute(
            "SELECT DISTINCT date FROM games WHERE date >= ? AND date <= ?",
            (week_start.strftime("%Y-%m-%d"),
             (week_start + timedelta(days=6)).strftime("%Y-%m-%d"))).fetchall()
        conn.close()
        has = set(r[0] for r in rows)
    except Exception:
        has = set()
    sel = state["date"]
    for i, b in enumerate(week_btns):
        ds = week_dates[i].strftime("%Y-%m-%d")
        if ds == sel:
            b.config(bg=ACTIVE_BG)
        elif ds in has:
            b.config(bg=HAS_GAME_BG)
        else:
            b.config(bg="#26263A")

date_label = tk.Label(root, text=f"正在看：{state['date']}", bg=BG, fg=TEXT_GRAY,
                      font=("Microsoft YaHei", 9))
date_label.pack(pady=(2, 2))

# ---------- 游戏列表（Canvas） ----------
list_canvas = tk.Canvas(root, bg="#1A1A2A", highlightthickness=0, bd=0)
list_canvas.pack(fill="both", expand=True, padx=10, pady=6)

row_urls = {}
sel_index = -1
cur_rows = []
cur_base = 0

def draw_list():
    global sel_index
    list_canvas.delete("all")
    row_urls.clear()
    cw = list_canvas.winfo_width()
    if cw <= 1:
        cw = WIN_W - 20
    ch = list_canvas.winfo_height()
    if not cur_rows:
        msg = "（这一天还没有收录的游戏）"
        if state["date"] == "":
            msg = "数据下载中，请稍候…"
        list_canvas.create_text(cw // 2, ch // 2, text=msg,
                                fill=TEXT_GRAY, font=("Microsoft YaHei", 11))
        return
    for i, (name, price, url) in enumerate(cur_rows):
        y0 = i * ROW_H
        y1 = y0 + ROW_H
        if i == sel_index:
            list_canvas.create_rectangle(2, y0 + 2, cw - 2, y1 - 2,
                                         fill="#2A2A40", outline="")
        short = name if len(name) <= 20 else name[:20] + "…"
        list_canvas.create_text(10, y0 + ROW_H // 2, anchor="w",
                                text=f"{cur_base + i + 1}. {short}",
                                fill=TEXT_WHITE, font=("Microsoft YaHei", 11))
        p = str(price).strip()
        p_color = PRICE_GREEN if p and p != "免费" else TEXT_GRAY
        list_canvas.create_text(cw - 10, y0 + ROW_H // 2, anchor="e",
                                text=p, fill=p_color,
                                font=("Microsoft YaHei", 11, "bold"))
        list_canvas.create_line(6, y1 - 1, cw - 6, y1 - 1, fill="#2E2E42")
        row_urls[i] = url

def canvas_click(e):
    global sel_index
    idx = int(e.y // ROW_H)
    if idx in row_urls:
        sel_index = idx
        draw_list()

def canvas_dbl(e):
    idx = int(e.y // ROW_H)
    if idx in row_urls and row_urls[idx]:
        os.startfile(row_urls[idx])

list_canvas.bind("<Button-1>", canvas_click)
list_canvas.bind("<Double-Button-1>", canvas_dbl)
list_canvas.bind("<Configure>", lambda e: draw_list())

# ---------- 翻页 ----------
nav = tk.Frame(root, bg=BG)
nav.pack(fill="x", padx=10, pady=(4, 0))

def load_page():
    global sel_index, cur_rows, cur_base
    sel_index = -1
    cur_rows = []
    d = state["date"]
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        total = conn.execute("SELECT COUNT(*) FROM games WHERE date = ?",
                             (d,)).fetchone()[0]
    except sqlite3.OperationalError:
        list_canvas.delete("all")
        page_label.config(text="…")
        conn.close()
        state["date"] = ""
        draw_list()
        return
    state["total_pages"] = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if state["page"] >= state["total_pages"]:
        state["page"] = state["total_pages"] - 1
    rows = conn.execute(
        "SELECT name, price, url FROM games WHERE date = ? ORDER BY rank LIMIT ? OFFSET ?",
        (d, PAGE_SIZE, state["page"] * PAGE_SIZE)).fetchall()
    conn.close()

    cur_base = state["page"] * PAGE_SIZE
    cur_rows = rows
    page_label.config(text=f"{state['page'] + 1} / {state['total_pages']}"
                          if rows else "0 / 0")
    draw_list()
    refresh_week_btns()

def prev_page():
    if state["page"] > 0:
        state["page"] -= 1
        load_page()

def next_page():
    if state["page"] < state["total_pages"] - 1:
        state["page"] += 1
        load_page()

prev_btn = tk.Button(nav, text="◀ 上一页", command=prev_page, bg="#26263A", fg=TEXT_WHITE,
                     relief="flat", font=("Microsoft YaHei", 9), activebackground=ACTIVE_BG,
                     borderwidth=0, highlightthickness=0)
prev_btn.pack(side="left")

page_label = tk.Label(nav, text="1 / 1", bg=BG, fg=TEXT_GRAY, font=("Microsoft YaHei", 9))
page_label.pack(side="left", expand=True)

next_btn = tk.Button(nav, text="下一页 ▶", command=next_page, bg="#26263A", fg=TEXT_WHITE,
                     relief="flat", font=("Microsoft YaHei", 9), activebackground=ACTIVE_BG,
                     borderwidth=0, highlightthickness=0)
next_btn.pack(side="right")

# ---------- 底部加载条 ----------
status_frame = tk.Frame(root, bg=BG)
status_frame.pack(fill="x", padx=10, pady=(2, 10))

status_label = tk.Label(status_frame, text="正在更新游戏数据…", bg=BG, fg=TEXT_GRAY,
                        font=("Microsoft YaHei", 8))
status_label.pack(side="left")

style = ttk.Style()
style.theme_use("clam")
style.configure("Dark.Horizontal.TProgressbar", troughcolor="#1A1A2A",
                background="#3E8E68", thickness=6)
load_bar = ttk.Progressbar(status_frame, style="Dark.Horizontal.TProgressbar",
                           mode="indeterminate", length=200)
load_bar.pack(side="right", pady=4)
load_bar.start(15)

# ---------- 日历弹窗 ----------
def open_calendar():
    pop = tk.Toplevel(root)
    pop.overrideredirect(True)
    pop.configure(bg="#1E1E2E")
    pop.attributes("-topmost", True)
    pop.grab_set()
    pop.focus_set()
    pop.geometry(f"280x400+{root.winfo_x() + 40}+{root.winfo_y() + 40}")

    today = datetime.now()
    cur = {"y": today.year, "m": today.month}

    bar_p = tk.Frame(pop, bg="#26263A")
    bar_p.pack(fill="x")
    tk.Label(bar_p, text="选择日期", bg="#26263A", fg=TEXT_WHITE,
             font=("Microsoft YaHei", 9)).pack(side="left", padx=8, pady=4)
    tk.Button(bar_p, text="×", command=pop.destroy, bg="#26263A", fg="#E06C75",
              relief="flat", font=("Microsoft YaHei", 10, "bold"),
              borderwidth=0, highlightthickness=0).pack(side="right", padx=4)

    year_p = tk.Frame(pop, bg="#1E1E2E")
    year_p.pack(fill="x", pady=(4, 0))

    def shift_year(delta):
        cur["y"] += delta
        build()

    tk.Button(year_p, text="◀◀", command=lambda: shift_year(-1), bg="#1E1E2E",
              fg=TEXT_WHITE, relief="flat", borderwidth=0, highlightthickness=0,
              font=("Microsoft YaHei", 9)).pack(side="left", padx=12)
    year_label = tk.Label(year_p, text="", bg="#1E1E2E", fg=TEXT_WHITE,
                          font=("Microsoft YaHei", 10, "bold"))
    year_label.pack(side="left", expand=True)
    tk.Button(year_p, text="▶▶", command=lambda: shift_year(1), bg="#1E1E2E",
              fg=TEXT_WHITE, relief="flat", borderwidth=0, highlightthickness=0,
              font=("Microsoft YaHei", 9)).pack(side="right", padx=12)

    month_p = tk.Frame(pop, bg="#1E1E2E")
    month_p.pack(fill="x")

    def shift_month(delta):
        m = cur["m"] + delta
        y = cur["y"]
        if m < 1:
            m, y = 12, y - 1
        elif m > 12:
            m, y = 1, y + 1
        cur["y"], cur["m"] = y, m
        build()

    tk.Button(month_p, text="◀", command=lambda: shift_month(-1), bg="#1E1E2E",
              fg=TEXT_WHITE, relief="flat", borderwidth=0, highlightthickness=0,
              font=("Microsoft YaHei", 9)).pack(side="left", padx=12)
    month_label = tk.Label(month_p, text="", bg="#1E1E2E", fg=TEXT_WHITE,
                           font=("Microsoft YaHei", 10, "bold"))
    month_label.pack(side="left", expand=True)
    tk.Button(month_p, text="▶", command=lambda: shift_month(1), bg="#1E1E2E",
              fg=TEXT_WHITE, relief="flat", borderwidth=0, highlightthickness=0,
              font=("Microsoft YaHei", 9)).pack(side="right", padx=12)

    def go_today():
        cur["y"], cur["m"] = today.year, today.month
        build()

    tk.Button(pop, text="今天", command=go_today, bg="#26263A", fg=TEXT_WHITE,
              relief="flat", font=("Microsoft YaHei", 9), activebackground=ACTIVE_BG,
              borderwidth=0, highlightthickness=0).pack(pady=2)

    days_frame = tk.Frame(pop, bg="#1E1E2E")
    days_frame.pack(padx=10, pady=4)

    tk.Label(pop, text="● 当天有游戏发售", bg="#1E1E2E", fg="#2E5E4E",
             font=("Microsoft YaHei", 8)).pack(pady=(0, 6))

    def pick_date(y, m, d):
        state["date"] = f"{y}-{str(m).zfill(2)}-{str(d).zfill(2)}"
        state["page"] = 0
        date_label.config(text=f"正在看：{state['date']}")
        pop.destroy()
        load_page()

    def build():
        for w in days_frame.winfo_children():
            w.destroy()
        year_label.config(text=f"{cur['y']} 年")
        month_label.config(text=f"{cur['m']} 月")
        conn = sqlite3.connect(DB_PATH, timeout=10)
        try:
            has_games = set(r[0] for r in conn.execute(
                "SELECT DISTINCT date FROM games WHERE date LIKE ?",
                (f"{cur['y']}-{str(cur['m']).zfill(2)}-%",)).fetchall())
        except sqlite3.OperationalError:
            has_games = set()
        conn.close()
        first, days = cal.monthrange(cur["y"], cur["m"])
        for i, n in enumerate(["一", "二", "三", "四", "五", "六", "日"]):
            tk.Label(days_frame, text=n, bg="#1E1E2E", fg=TEXT_GRAY,
                     font=("Microsoft YaHei", 9)).grid(row=0, column=i, padx=1, pady=2)
        r, c = 1, first
        for d in range(1, days + 1):
            dstr = f"{cur['y']}-{str(cur['m']).zfill(2)}-{str(d).zfill(2)}"
            if (cur["y"], cur["m"], d) == (today.year, today.month, today.day):
                bg, fg = ACTIVE_BG, "#FFFFFF"
            elif dstr in has_games:
                bg, fg = "#2E5E4E", "#FFFFFF"
            else:
                bg, fg = "#26263A", TEXT_WHITE
            tk.Button(days_frame, text=str(d),
                      command=lambda dd=d: pick_date(cur["y"], cur["m"], dd),
                      bg=bg, fg=fg, relief="flat", width=3, font=("Microsoft YaHei", 9),
                      activebackground="#5A5A7A", borderwidth=0, highlightthickness=0
                      ).grid(row=r, column=c, padx=1, pady=1)
            c += 1
            if c > 6:
                c = 0
                r += 1

    build()

# ---------- 启动 ----------
load_page()
root.update()

done = threading.Event()
update_failed = [False]

def background_update():
    try:
        update_data()
    except Exception:
        update_failed[0] = True
    finally:
        done.set()

def check_update():
    if done.is_set():
        load_bar.stop()
        load_bar.pack_forget()
        if update_failed[0]:
            status_label.config(text="更新失败（请检查网络），显示的是上次数据")
        else:
            status_label.config(text=f"更新完成 · {datetime.now().strftime('%H:%M')}")
        load_page()
    else:
        root.after(100, check_update)

threading.Thread(target=background_update, daemon=True).start()
root.after(100, check_update)

root.bind_all("<Button-3>", lambda e: close_app())

root.mainloop()
