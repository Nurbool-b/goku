"""Goku lock screen. Runs in the USER session on every club PC (Windows, Python 3 with tkinter).
Locked  : full-screen black window. The client enters the 4-digit code from the website (or the operator unlocks in the admin panel).
Unlocked: window hidden, small timer in the corner. Last 5 minutes: red warning. Time up: locked again, PC shuts down 2 min later."""
import ctypes, json, os, re, threading, time, urllib.request
import tkinter as tk
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "lock_config.json"), encoding="utf-8"))
URL = CFG["url"].rstrip("/") + "/rest/v1/rpc/"
KEY, PC, SECRET = CFG["key"], CFG["pc_id"], CFG["lock_secret"]
WARN, GRACE = 300, 120
BG, GREEN, WHITE, RED = "#0F0F0F", "#5DD62C", "#F8F8F8", "#ff4d5e"

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


def rpc(name, body):
    req = urllib.request.Request(
        URL + name, data=json.dumps(body).encode(), method="POST",
        headers={"apikey": KEY, "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else None


def parse(ts):
    s = ts.replace("Z", "+00:00").replace(" ", "T")
    s = re.sub(r"([+-]\d\d)$", r"\1:00", s)
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s)
    return datetime.fromisoformat(s).timestamp()


state = {"status": "available", "client": None, "end": None, "unlocked": False, "offset": 0.0, "fails": 0, "online": False}


def fetch():
    try:
        r = rpc("agent_status", {"p_pc": PC, "p_secret": SECRET})
        if r:
            r = r[0]
            state.update(status=r["status"], client=r["client"], unlocked=r["unlocked"], fails=r["fails"],
                         end=parse(r["session_end"]) if r["session_end"] else None,
                         offset=parse(r["server_now"]) - time.time(), online=True)
    except Exception:
        state["online"] = False  # keep the last known state


def poll_loop():
    while True:
        fetch()
        time.sleep(2)


def now():
    return time.time() + state["offset"]


root = tk.Tk()
root.title("Goku Lock")
root.configure(bg=BG)
root.overrideredirect(True)
W, H = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry("%dx%d+0+0" % (W, H))
root.attributes("-topmost", True)
root.protocol("WM_DELETE_WINDOW", lambda: None)
root.bind("<Alt-F4>", lambda e: "break")

box = tk.Frame(root, bg=BG)
box.place(relx=.5, rely=.5, anchor="center")
tk.Label(box, text="GOKU eSPORTS", font=("Segoe UI", 46, "bold"), fg=GREEN, bg=BG).pack()
tk.Label(box, text="PC %02d" % PC, font=("Segoe UI", 20), fg=WHITE, bg=BG).pack(pady=(0, 24))
msg = tk.Label(box, font=("Segoe UI", 22), fg=WHITE, bg=BG, wraplength=int(W * .7), justify="center")
msg.pack(pady=(0, 24))
entry = tk.Entry(box, font=("Segoe UI", 40), justify="center", width=6, bg="#202020", fg=WHITE, insertbackground=WHITE, relief="flat")
entry.pack(ipady=8)
err = tk.Label(box, font=("Segoe UI", 16), fg=RED, bg=BG)
err.pack(pady=8)


def unlock_done(ok):
    if ok:
        entry.delete(0, "end")
        err.config(text="")
        threading.Thread(target=fetch, daemon=True).start()
    else:
        err.config(text="Неверный код · Код қате" + ("\nПозовите оператора · Операторды шақырыңыз" if state["fails"] >= 4 else ""))


def do_unlock(event=None):
    code = entry.get().strip()

    def work():
        try:
            ok = bool(rpc("agent_unlock", {"p_pc": PC, "p_secret": SECRET, "p_code": code}))
        except Exception:
            ok = False
        root.after(0, lambda: unlock_done(ok))
        fetch()
    threading.Thread(target=work, daemon=True).start()


entry.bind("<Return>", do_unlock)
tk.Button(box, text="Разблокировать · Ашу", font=("Segoe UI", 18, "bold"), bg=GREEN, fg=BG, relief="flat",
          activebackground=GREEN, command=do_unlock).pack(ipadx=20, ipady=6)

tw = tk.Toplevel(root)
tw.overrideredirect(True)
tw.attributes("-topmost", True)
tw.configure(bg=BG)
tw.geometry("300x56+%d+8" % (W - 310))
tl = tk.Label(tw, font=("Segoe UI", 20, "bold"), fg=GREEN, bg=BG)
tl.pack(expand=True, fill="both")
tw.withdraw()


def hms(s):
    s = max(0, int(s))
    return "%d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def tick():
    st = state
    running = st["status"] == "occupied" and st["unlocked"] and st["end"]
    if running and now() < st["end"]:
        rem = st["end"] - now()
        root.withdraw()
        tl.config(text=("⚠ Осталось " if rem < WARN else "⏱ ") + hms(rem), fg=RED if rem < WARN else GREEN)
        tw.deiconify()
        tw.lift()
    else:
        tw.withdraw()
        if running:
            left = GRACE - (now() - st["end"])
            text = "Время вышло. ПК выключится через %d сек.\nУақыт бітті. Компьютер %d секундтан кейін өшеді." % (max(0, left), max(0, left))
        elif st["status"] == "occupied":
            text = "Забронировано: %s\nВведите код со страницы заявки\nБрондалған. Өтініш бетіндегі кодты енгізіңіз" % (st["client"] or "")
        elif not st["online"]:
            text = "Нет связи с сервером. Позовите оператора.\nСервермен байланыс жоқ. Операторды шақырыңыз."
        else:
            text = "Компьютер свободен. Забронируйте на сайте или подойдите к оператору.\nКомпьютер бос. Сайттан брондаңыз немесе операторға барыңыз."
        msg.config(text=text)
        if root.state() == "withdrawn":
            root.deiconify()
            entry.focus_set()
        root.lift()
        root.attributes("-topmost", True)
    root.after(500, tick)


threading.Thread(target=poll_loop, daemon=True).start()
root.after(300, tick)
root.mainloop()
