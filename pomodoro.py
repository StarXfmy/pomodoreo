# -*- coding: utf-8 -*-
"""桌面番茄钟 —— 基于 Python 标准库 tkinter，零第三方依赖。

双击本文件即可运行（需要 Windows 版 Python）。
"""

import json
import os
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import winsound  # Windows 专用提示音
except ImportError:  # 非 Windows 环境降级处理
    winsound = None

# 运行目录（用于读写配置文件）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "pomodoro_config.json")

# 默认配置（单位：分钟）
DEFAULT_CONFIG = {
    "work": 25,        # 专注时长
    "short_break": 5,  # 短休息时长
    "long_break": 15,  # 长休息时长
    "long_every": 4,   # 每多少个专注后进入长休息
    "on_top": False,   # 窗口置顶
}

# 配色方案
COLORS = {
    "work": {"main": "#e2543e", "dark": "#c73e2a", "label": "专注"},
    "short_break": {"main": "#3e9d6c", "dark": "#2f7f56", "label": "短休息"},
    "long_break": {"main": "#3a7bd5", "dark": "#2b5fa8", "label": "长休息"},
}
BG = "#f7f6f3"
CARD = "#ffffff"
TEXT = "#333333"
MUTED = "#9a9a9a"
RING_BG = "#e8e6e1"


class PomodoroApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = self._load_config()

        self.mode = "work"          # work / short_break / long_break
        self.completed_work = 0     # 已完成的专注次数（累计）
        self.remaining = 0          # 当前剩余秒数
        self.total = 0              # 当前模式总秒数
        self.running = False        # 是否正在计时
        self._after_id = None       # root.after 的句柄

        self._setup_window()
        self._build_ui()
        self._set_mode("work")

    # ---------- 配置读写 ----------
    def _load_config(self) -> dict:
        cfg = dict(DEFAULT_CONFIG)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    for k in DEFAULT_CONFIG:
                        if k in data:
                            cfg[k] = data[k]
        except (OSError, ValueError):
            pass
        return cfg

    def _save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    # ---------- 界面 ----------
    def _setup_window(self):
        self.root.title("番茄钟")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.config.get("on_top"):
            self.root.attributes("-topmost", True)

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG, padx=32, pady=24)
        outer.pack()

        # 模式标签
        self.mode_label = tk.Label(
            outer, text="", font=("Microsoft YaHei UI", 14, "bold"),
            bg=BG, fg=TEXT,
        )
        self.mode_label.pack(pady=(0, 12))

        # 圆形进度环
        self.canvas_size = 260
        self.canvas = tk.Canvas(
            outer, width=self.canvas_size, height=self.canvas_size,
            bg=BG, highlightthickness=0,
        )
        self.canvas.pack()

        # 时间文字（画在 canvas 中央）
        self.time_text = self.canvas.create_text(
            self.canvas_size / 2, self.canvas_size / 2 - 6,
            text="25:00", font=("Consolas", 44, "bold"), fill=TEXT,
        )
        self.mode_text = self.canvas.create_text(
            self.canvas_size / 2, self.canvas_size / 2 + 34,
            text="", font=("Microsoft YaHei UI", 11), fill=MUTED,
        )

        # 专注进度圆点
        self.dots_frame = tk.Frame(outer, bg=BG)
        self.dots_frame.pack(pady=16)
        self.dot_labels = []

        # 按钮行
        btns = tk.Frame(outer, bg=BG)
        btns.pack(pady=(0, 6))

        self.start_btn = tk.Button(
            btns, text="开始", font=("Microsoft YaHei UI", 12, "bold"),
            command=self.toggle, relief="flat", bd=0,
            bg=COLORS["work"]["main"], fg="white", activebackground=COLORS["work"]["dark"],
            activeforeground="white", padx=26, pady=8, cursor="hand2",
        )
        self.start_btn.grid(row=0, column=0, padx=6)

        reset_btn = tk.Button(
            btns, text="重置", font=("Microsoft YaHei UI", 11),
            command=self.reset, relief="flat", bd=0,
            bg=CARD, fg=TEXT, activebackground="#e8e6e1",
            padx=16, pady=8, cursor="hand2",
        )
        reset_btn.grid(row=0, column=1, padx=6)

        skip_btn = tk.Button(
            btns, text="跳过", font=("Microsoft YaHei UI", 11),
            command=self.skip, relief="flat", bd=0,
            bg=CARD, fg=TEXT, activebackground="#e8e6e1",
            padx=16, pady=8, cursor="hand2",
        )
        skip_btn.grid(row=0, column=2, padx=6)

        # 底部：设置 / 置顶
        foot = tk.Frame(outer, bg=BG)
        foot.pack(pady=(10, 0))

        self.top_var = tk.BooleanVar(value=self.config.get("on_top", False))
        top_chk = tk.Checkbutton(
            foot, text="窗口置顶", variable=self.top_var,
            command=self._toggle_top, bg=BG, fg=MUTED,
            activebackground=BG, selectcolor=BG,
            font=("Microsoft YaHei UI", 9), cursor="hand2",
        )
        top_chk.pack(side="left", padx=6)

        set_btn = tk.Button(
            foot, text="设置", font=("Microsoft YaHei UI", 9),
            command=self._open_settings, relief="flat", bd=0,
            bg=BG, fg=MUTED, activebackground="#e8e6e1",
            cursor="hand2",
        )
        set_btn.pack(side="left", padx=6)

    # ---------- 计时核心 ----------
    def _mode_seconds(self, mode: str) -> int:
        if mode == "work":
            return int(self.config["work"]) * 60
        if mode == "short_break":
            return int(self.config["short_break"]) * 60
        return int(self.config["long_break"]) * 60

    def _set_mode(self, mode: str):
        self.mode = mode
        self.total = self._mode_seconds(mode)
        self.remaining = self.total
        self._refresh_ui()
        self._render_ring()

    def _next_mode(self) -> str:
        if self.mode == "work":
            self.completed_work += 1
            if self.completed_work % int(self.config["long_every"]) == 0:
                return "long_break"
            return "short_break"
        # 休息结束后回到专注
        return "work"

    def toggle(self):
        if self.running:
            self._pause()
        else:
            self._start()

    def _start(self):
        self.running = True
        self.start_btn.config(text="暂停")
        self._tick()

    def _pause(self):
        self.running = False
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        self.start_btn.config(text="继续")

    def reset(self):
        self._pause()
        self.start_btn.config(text="开始")
        self._set_mode(self.mode)

    def skip(self):
        self._pause()
        self.start_btn.config(text="开始")
        self._advance()

    def _advance(self):
        """进入下一阶段（用于跳过或自然完成）。"""
        nxt = self._next_mode()
        self._set_mode(nxt)
        self._notify()

    def _tick(self):
        if not self.running:
            return
        if self.remaining <= 0:
            self.running = False
            self._advance()
            return
        self.remaining -= 1
        self._refresh_ui()
        self._render_ring()
        self._after_id = self.root.after(1000, self._tick)

    # ---------- 显示 ----------
    def _refresh_ui(self):
        c = COLORS[self.mode]
        self.mode_label.config(text=c["label"], fg=c["dark"])
        mm, ss = divmod(self.remaining, 60)
        self.canvas.itemconfigure(self.time_text, text=f"{mm:02d}:{ss:02d}")
        self.canvas.itemconfigure(
            self.mode_text,
            text=f"第 {self.completed_work % int(self.config['long_every'])} / "
                 f"{self.config['long_every']} 个专注",
        )
        self.start_btn.config(
            bg=c["main"], activebackground=c["dark"],
        )
        self._render_dots()

    def _render_ring(self):
        c = COLORS[self.mode]
        pad = 10
        x0 = pad
        y0 = pad
        x1 = self.canvas_size - pad
        y1 = self.canvas_size - pad
        self.canvas.delete("ring")
        # 背景环
        self.canvas.create_oval(
            x0, y0, x1, y1, outline=RING_BG, width=10, tags="ring",
        )
        # 进度环（顺时针从顶部开始，随剩余时间减少）
        fraction = self.remaining / self.total if self.total else 0
        extent = -360 * fraction
        self.canvas.create_arc(
            x0, y0, x1, y1, start=90, extent=extent,
            style="arc", outline=c["main"], width=10, tags="ring",
        )

    def _render_dots(self):
        for w in self.dot_labels:
            w.destroy()
        self.dot_labels.clear()
        n = int(self.config["long_every"])
        for i in range(n):
            filled = i < (self.completed_work % n)
            color = COLORS["work"]["main"] if filled else RING_BG
            lbl = tk.Label(
                self.dots_frame, text="●", font=("Arial", 12),
                bg=BG, fg=color,
            )
            lbl.pack(side="left", padx=3)
            self.dot_labels.append(lbl)

    # ---------- 提示音 / 通知 ----------
    def _notify(self):
        # 短暂置顶闪动提醒
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(800, lambda: self.root.attributes(
                "-topmost", self.config.get("on_top", False)))
        except tk.TclError:
            pass
        if winsound:
            for _ in range(3):
                winsound.Beep(880, 180)
                winsound.Beep(660, 180)

    # ---------- 设置 / 杂项 ----------
    def _toggle_top(self):
        self.config["on_top"] = self.top_var.get()
        self.root.attributes("-topmost", self.top_var.get())
        self._save_config()

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.grab_set()

        fields = [
            ("专注时长（分钟）", "work"),
            ("短休息（分钟）", "short_break"),
            ("长休息（分钟）", "long_break"),
            ("几个专注后长休息", "long_every"),
        ]
        entries = {}
        for i, (label, key) in enumerate(fields):
            tk.Label(win, text=label, bg=BG, fg=TEXT,
                     font=("Microsoft YaHei UI", 10)).grid(
                row=i, column=0, sticky="e", padx=10, pady=6)
            var = tk.StringVar(value=str(self.config[key]))
            ent = tk.Entry(win, textvariable=var, width=8, justify="center",
                           font=("Microsoft YaHei UI", 10))
            ent.grid(row=i, column=1, padx=10, pady=6)
            entries[key] = var

        def save():
            try:
                for key, var in entries.items():
                    val = int(var.get())
                    if val <= 0:
                        raise ValueError
                    self.config[key] = val
            except ValueError:
                messagebox.showerror("错误", "请输入正整数", parent=win)
                return
            self._save_config()
            if not self.running:
                self.reset()
            win.destroy()

        btns = tk.Frame(win, bg=BG)
        btns.grid(row=len(fields), column=0, columnspan=2, pady=12)
        tk.Button(btns, text="保存", command=save, bg=COLORS["work"]["main"],
                  fg="white", relief="flat", bd=0, padx=18, pady=4,
                  cursor="hand2").pack(side="left", padx=6)
        tk.Button(btns, text="取消", command=win.destroy, bg=CARD,
                  fg=TEXT, relief="flat", bd=0, padx=18, pady=4,
                  cursor="hand2").pack(side="left", padx=6)

        win.update_idletasks()
        # 居中于主窗口
        x = self.root.winfo_rootx() + 60
        y = self.root.winfo_rooty() + 60
        win.geometry(f"+{x}+{y}")

    def _on_close(self):
        self.running = False
        self._save_config()
        self.root.destroy()


def main():
    root = tk.Tk()
    PomodoroApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
