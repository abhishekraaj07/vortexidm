import os
import sys
import time
import json
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from vortex_engine import DownloadTask, format_size, format_speed, format_eta

DATA_DIR = os.path.join(os.path.expanduser("~"), ".vortex_idm")
os.makedirs(DATA_DIR, exist_ok=True)
HISTORY_FILE = os.path.join(DATA_DIR, "downloads_history.json")

# THEME PALETTE (Deep OLED Black Mode)
CLR_BG = "#0f1013"          # Pure dark background
CLR_CARD = "#191a1f"        # Card background
CLR_PANEL = "#212229"       # Toolbar & sidebar panel
CLR_BORDER = "#2e303b"      # Subtle border
CLR_TEXT = "#f8fafc"        # Bright text
CLR_TEXT_MUTED = "#94a3b8"  # Secondary text
CLR_ACCENT = "#10b981"      # IDM Emerald Green
CLR_ACCENT_HOVER = "#059669"# Darker green
CLR_CYAN = "#06b6d4"        # Cyan indicator
CLR_DANGER = "#f43f5e"      # Red stop button
CLR_SEL = "#065f46"         # Selection highlight

class IDMProgressDialog(tk.Toplevel):
    """The iconic IDM Download Progress Window in Sleek Black Theme."""
    def __init__(self, parent, task, on_complete_callback=None):
        super().__init__(parent)
        self.task = task
        self.on_complete_callback = on_complete_callback
        
        self.title(f"0.0% of {task.filename} - VORTEX Download Status")
        self.geometry("560x470")
        self.resizable(False, False)
        self.configure(bg=CLR_BG)

        self.lift()
        self.focus_force()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        # 1. Top File Details Frame (Dark Card)
        info_frame = tk.LabelFrame(
            self, text="File Information", bg=CLR_CARD, fg=CLR_TEXT_MUTED,
            font=("Segoe UI", 9, "bold"), padx=14, pady=10,
            highlightbackground=CLR_BORDER, highlightthickness=1
        )
        info_frame.pack(fill=tk.X, padx=14, pady=(12, 6))

        grid_opts = {"sticky": "w", "pady": 3}

        tk.Label(info_frame, text="File Name:", bg=CLR_CARD, fg=CLR_TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, **grid_opts)
        self.lbl_file = tk.Label(info_frame, text=self.task.filename, bg=CLR_CARD, fg=CLR_TEXT, font=("Segoe UI", 9, "bold"))
        self.lbl_file.grid(row=0, column=1, **grid_opts)

        tk.Label(info_frame, text="Status:", bg=CLR_CARD, fg=CLR_TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=1, column=0, **grid_opts)
        self.lbl_status = tk.Label(info_frame, text="Connecting to server...", bg=CLR_CARD, fg=CLR_CYAN, font=("Segoe UI", 9))
        self.lbl_status.grid(row=1, column=1, **grid_opts)

        tk.Label(info_frame, text="File size:", bg=CLR_CARD, fg=CLR_TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=2, column=0, **grid_opts)
        size_str = format_size(self.task.total_size) if self.task.total_size > 0 else "Dynamic / Streaming"
        self.lbl_size = tk.Label(info_frame, text=size_str, bg=CLR_CARD, fg=CLR_TEXT, font=("Segoe UI", 9))
        self.lbl_size.grid(row=2, column=1, **grid_opts)

        tk.Label(info_frame, text="Downloaded:", bg=CLR_CARD, fg=CLR_TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=3, column=0, **grid_opts)
        self.lbl_downloaded = tk.Label(info_frame, text="0 bytes", bg=CLR_CARD, fg=CLR_TEXT, font=("Segoe UI", 9))
        self.lbl_downloaded.grid(row=3, column=1, **grid_opts)

        tk.Label(info_frame, text="Transfer rate:", bg=CLR_CARD, fg=CLR_TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=4, column=0, **grid_opts)
        self.lbl_speed = tk.Label(info_frame, text="0.00 B/s", bg=CLR_CARD, fg=CLR_ACCENT, font=("Segoe UI", 10, "bold"))
        self.lbl_speed.grid(row=4, column=1, **grid_opts)

        tk.Label(info_frame, text="Time left:", bg=CLR_CARD, fg=CLR_TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=5, column=0, **grid_opts)
        self.lbl_time_left = tk.Label(info_frame, text="Calculating...", bg=CLR_CARD, fg=CLR_TEXT, font=("Segoe UI", 9))
        self.lbl_time_left.grid(row=5, column=1, **grid_opts)

        tk.Label(info_frame, text="Resume capability:", bg=CLR_CARD, fg=CLR_TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=6, column=0, **grid_opts)
        resume_text = "Yes" if self.task.supports_ranges else "No"
        resume_color = CLR_ACCENT if self.task.supports_ranges else CLR_DANGER
        tk.Label(info_frame, text=resume_text, bg=CLR_CARD, fg=resume_color, font=("Segoe UI", 9, "bold")).grid(row=6, column=1, **grid_opts)

        # 2. Main Progress Bar Frame (Dark)
        prog_frame = tk.Frame(self, bg=CLR_BG, padx=14, pady=4)
        prog_frame.pack(fill=tk.X)

        self.canvas_prog = tk.Canvas(prog_frame, height=18, bg="#1e1e24", highlightthickness=1, highlightbackground=CLR_BORDER)
        self.canvas_prog.pack(fill=tk.X, pady=(4, 2))
        self.prog_rect = self.canvas_prog.create_rectangle(0, 0, 0, 18, fill=CLR_ACCENT, width=0)

        self.lbl_overall_pct = tk.Label(prog_frame, text="0.0%", bg=CLR_BG, fg=CLR_TEXT, font=("Segoe UI", 10, "bold"))
        self.lbl_overall_pct.pack(anchor="e")

        # 3. Iconic IDM Multi-Connection Chunk Progress Canvas (Dark)
        conn_frame = tk.LabelFrame(
            self,
            text=f"Download Status ({self.task.num_threads} Parallel Connections):",
            bg=CLR_CARD, fg=CLR_TEXT_MUTED,
            font=("Segoe UI", 9, "bold"),
            padx=10, pady=8,
            highlightbackground=CLR_BORDER, highlightthickness=1
        )
        conn_frame.pack(fill=tk.X, padx=14, pady=(2, 12))

        self.chunk_canvas = tk.Canvas(conn_frame, height=48, bg="#121316", highlightthickness=1, highlightbackground=CLR_BORDER)
        self.chunk_canvas.pack(fill=tk.X, pady=2)

        # 4. Bottom Control Buttons (Dark Themed)
        btn_box = tk.Frame(self, bg=CLR_BG)
        btn_box.pack(fill=tk.X, padx=14, pady=(0, 12))

        self.btn_pause = tk.Button(
            btn_box, text="⏸️ Pause", font=("Segoe UI", 9, "bold"),
            bg="#27272a", fg=CLR_TEXT, activebackground="#3f3f46", activeforeground=CLR_TEXT,
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2",
            command=self.toggle_pause
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_cancel = tk.Button(
            btn_box, text="❌ Cancel", font=("Segoe UI", 9),
            bg="#27272a", fg=CLR_DANGER, activebackground="#3f3f46",
            relief=tk.FLAT, padx=14, pady=6, cursor="hand2",
            command=self.cancel_download
        )
        self.btn_cancel.pack(side=tk.LEFT)

        self.btn_open = tk.Button(
            btn_box, text="▶️ Open", font=("Segoe UI", 9, "bold"),
            bg=CLR_ACCENT, fg="#ffffff", activebackground=CLR_ACCENT_HOVER, activeforeground="#ffffff",
            relief=tk.FLAT, padx=16, pady=6, state=tk.DISABLED, cursor="hand2",
            command=self.open_file
        )
        self.btn_open.pack(side=tk.RIGHT)

        self.btn_open_folder = tk.Button(
            btn_box, text="📂 Open Folder", font=("Segoe UI", 9),
            bg="#27272a", fg=CLR_TEXT, activebackground="#3f3f46", activeforeground=CLR_TEXT,
            relief=tk.FLAT, padx=12, pady=6, state=tk.DISABLED, cursor="hand2",
            command=self.open_folder
        )
        self.btn_open_folder.pack(side=tk.RIGHT, padx=8)

    def update_telemetry(self, cur, total, speed, eta, status):
        pct = (cur / total * 100) if (total and total > 0) else (100.0 if status == "Completed" else 0.0)
        self.title(f"{pct:.1f}% of {self.task.filename} - VORTEX")
        
        self.lbl_status.config(text=status)
        self.lbl_downloaded.config(text=f"{format_size(cur)} ({cur:,} bytes)")
        self.lbl_speed.config(text=format_speed(speed))
        self.lbl_time_left.config(text=format_eta(eta))
        
        # Update progress bar
        w = self.canvas_prog.winfo_width()
        if w < 10: w = 530
        fill_w = int((pct / 100.0) * w)
        self.canvas_prog.coords(self.prog_rect, 0, 0, fill_w, 18)
        self.lbl_overall_pct.config(text=f"{pct:.1f}%")

        # Update file size display
        if total > 0:
            self.lbl_size.config(text=f"{format_size(total)} ({total:,} bytes)")
        else:
            self.lbl_size.config(text=f"{format_size(cur)} (Streaming)")

        # Redraw connection chunk blocks
        self._draw_chunk_stripes()

        if status == "Completed":
            self.lbl_status.config(text="Download Complete!", fg=CLR_ACCENT)
            self.canvas_prog.itemconfig(self.prog_rect, fill=CLR_ACCENT)
            self.btn_pause.config(state=tk.DISABLED)
            self.btn_open.config(state=tk.NORMAL)
            self.btn_open_folder.config(state=tk.NORMAL)
            if self.on_complete_callback:
                self.on_complete_callback()
        elif status == "Paused":
            self.lbl_status.config(text="Paused", fg="#f59e0b")
            self.btn_pause.config(text="Resume")

    def _draw_chunk_stripes(self):
        self.chunk_canvas.delete("all")
        w = self.chunk_canvas.winfo_width()
        h = self.chunk_canvas.winfo_height()
        if w < 10: w = 510

        chunks = self.task.chunks
        if not chunks:
            # Single stream block
            pct = (self.task.downloaded_bytes / self.task.total_size) if self.task.total_size else 1.0
            self.chunk_canvas.create_rectangle(0, 0, int(w * pct), h, fill=CLR_ACCENT, width=0)
            return

        total_chunks = len(chunks)
        gap = 2
        chunk_w = (w - (gap * (total_chunks - 1))) / total_chunks

        for i, c in enumerate(chunks):
            x1 = int(i * (chunk_w + gap))
            x2 = int(x1 + chunk_w)
            part_len = c["end"] - c["start"] + 1
            ratio = min(1.0, c["downloaded"] / part_len) if part_len > 0 else 0

            # Background unfilled segment (dark slate)
            self.chunk_canvas.create_rectangle(x1, 0, x2, h, fill="#1e1e24", outline="#2e2e38")
            
            # Filled segment (IDM neon emerald)
            fill_h = int(h * ratio)
            if fill_h > 0:
                self.chunk_canvas.create_rectangle(x1, h - fill_h, x2, h, fill=CLR_ACCENT, outline="")

    def toggle_pause(self):
        if self.task.is_paused:
            self.btn_pause.config(text="⏸️ Pause")
            self.lbl_status.config(text="Resuming...")
            threading.Thread(target=self.task.start, args=(self.update_telemetry,), daemon=True).start()
        else:
            self.task.pause()

    def cancel_download(self):
        self.task.cancel()
        self.destroy()

    def open_file(self):
        if os.path.exists(self.task.filepath):
            os.startfile(self.task.filepath)

    def open_folder(self):
        if os.path.exists(self.task.filepath):
            subprocess.run(["explorer", os.path.dirname(self.task.filepath)])

    def on_close(self):
        self.destroy()

class VortexIDM(tk.Tk):
    """The main Internet Download Manager (IDM) in Full Black Theme."""
    def __init__(self):
        super().__init__()
        self.title("Internet Download Manager (VORTEX Turbo Edition - Dark Mode)")
        self.geometry("1020x620")
        self.minsize(820, 500)
        self.configure(bg=CLR_BG)

        self._setup_dark_ttk_styles()

        self.save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        self.history = self._load_history()
        self.active_tasks = {}

        self._build_menu()
        self._build_toolbar()
        self._build_main_split()
        self._build_statusbar()
        self._populate_table()

    def _setup_dark_ttk_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        # Dark Treeview Styling
        style.configure(
            "Treeview",
            background="#141519",
            foreground=CLR_TEXT,
            fieldbackground="#141519",
            rowheight=26,
            bordercolor=CLR_BORDER,
            font=("Segoe UI", 9)
        )
        style.map("Treeview", background=[('selected', CLR_SEL)], foreground=[('selected', '#ffffff')])

        style.configure(
            "Treeview.Heading",
            background=CLR_PANEL,
            foreground=CLR_TEXT,
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT
        )
        style.map("Treeview.Heading", background=[('active', '#2e303b')])

    def _load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def _save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2)
        except Exception:
            pass

    def _build_menu(self):
        menubar = tk.Menu(self, bg=CLR_PANEL, fg=CLR_TEXT, activebackground=CLR_SEL, activeforeground="#ffffff")
        
        m_tasks = tk.Menu(menubar, tearoff=0, bg=CLR_PANEL, fg=CLR_TEXT)
        m_tasks.add_command(label="Add new download...", accelerator="Ctrl+N", command=self.open_add_url_dialog)
        m_tasks.add_separator()
        m_tasks.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="Tasks", menu=m_tasks)

        m_file = tk.Menu(menubar, tearoff=0, bg=CLR_PANEL, fg=CLR_TEXT)
        m_file.add_command(label="Stop download", command=self.stop_selected)
        m_file.add_command(label="Delete", accelerator="Del", command=self.delete_selected)
        menubar.add_cascade(label="File", menu=m_file)

        m_dl = tk.Menu(menubar, tearoff=0, bg=CLR_PANEL, fg=CLR_TEXT)
        m_dl.add_command(label="Resume Download", command=self.resume_selected)
        m_dl.add_command(label="Pause Download", command=self.stop_selected)
        m_dl.add_separator()
        m_dl.add_command(label="Options", command=self.open_settings)
        menubar.add_cascade(label="Downloads", menu=m_dl)

        m_help = tk.Menu(menubar, tearoff=0, bg=CLR_PANEL, fg=CLR_TEXT)
        m_help.add_command(label="About VORTEX IDM", command=lambda: messagebox.showinfo(
            "About VORTEX IDM",
            "VORTEX Download Accelerator (IDM Dark Edition)\n\n"
            "• Pure Multi-Threaded Engine (16x acceleration)\n"
            "• Built-in YouTube / Video Stream Downloader\n"
            "• 100% Lifetime Free (No 30-day Trial limit)"
        ))
        menubar.add_cascade(label="Help", menu=m_help)

        self.config(menu=menubar)
        self.bind("<Control-n>", lambda e: self.open_add_url_dialog())
        self.bind("<Delete>", lambda e: self.delete_selected())

    def _build_toolbar(self):
        # Dark Modern Toolbar
        toolbar = tk.Frame(self, bg=CLR_PANEL, padx=6, pady=6, highlightbackground=CLR_BORDER, highlightthickness=1)
        toolbar.pack(fill=tk.X)

        def make_tool_btn(text, cmd):
            btn = tk.Button(
                toolbar,
                text=text,
                font=("Segoe UI", 9, "bold"),
                bg="#27272a",
                fg=CLR_TEXT,
                activebackground="#3f3f46",
                activeforeground="#ffffff",
                relief=tk.FLAT,
                padx=10,
                pady=5,
                cursor="hand2",
                command=cmd
            )
            btn.pack(side=tk.LEFT, padx=3)
            return btn

        make_tool_btn("➕ Add URL", self.open_add_url_dialog)
        make_tool_btn("▶️ Resume", self.resume_selected)
        make_tool_btn("⏸️ Stop", self.stop_selected)
        make_tool_btn("⏹️ Stop All", self.stop_all)
        make_tool_btn("🗑️ Delete", self.delete_selected)
        make_tool_btn("⚙️ Options", self.open_settings)

    def _build_main_split(self):
        split = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True)

        # 1. Left Sidebar: Categories Tree (Dark)
        left_frame = tk.Frame(split, bg="#141519", width=190)
        split.add(left_frame, weight=1)

        cat_lbl = tk.Label(left_frame, text="CATEGORIES", font=("Segoe UI", 8, "bold"), bg="#1e1f25", fg=CLR_TEXT_MUTED, anchor="w", padx=10, pady=6)
        cat_lbl.pack(fill=tk.X)

        self.cat_tree = ttk.Treeview(left_frame, show="tree", selectmode="browse")
        self.cat_tree.pack(fill=tk.BOTH, expand=True)

        all_node = self.cat_tree.insert("", "end", text="📁 All Downloads", open=True)
        self.cat_tree.insert(all_node, "end", text="📦 Compressed")
        self.cat_tree.insert(all_node, "end", text="📄 Documents")
        self.cat_tree.insert(all_node, "end", text="🎵 Music")
        self.cat_tree.insert(all_node, "end", text="💻 Programs")
        self.cat_tree.insert(all_node, "end", text="🎬 Video")
        
        status_node = self.cat_tree.insert("", "end", text="📁 By Status", open=True)
        self.cat_tree.insert(status_node, "end", text="⏳ Unfinished")
        self.cat_tree.insert(status_node, "end", text="✅ Finished")

        # 2. Right Main Table: Downloads Grid (Dark Mode)
        right_frame = tk.Frame(split, bg="#141519")
        split.add(right_frame, weight=5)

        cols = ("Name", "Size", "Status", "Time Left", "Transfer Rate", "Date Added")
        self.table = ttk.Treeview(right_frame, columns=cols, show="headings", selectmode="browse")

        self.table.heading("Name", text="File Name")
        self.table.heading("Size", text="Size")
        self.table.heading("Status", text="Status")
        self.table.heading("Time Left", text="Time Left")
        self.table.heading("Transfer Rate", text="Transfer Rate")
        self.table.heading("Date Added", text="Last Try Date")

        self.table.column("Name", width=280)
        self.table.column("Size", width=95, anchor="e")
        self.table.column("Status", width=110, anchor="center")
        self.table.column("Time Left", width=90, anchor="center")
        self.table.column("Transfer Rate", width=110, anchor="e")
        self.table.column("Date Added", width=140, anchor="center")

        sb_y = ttk.Scrollbar(right_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=sb_y.set)

        self.table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_y.pack(side=tk.RIGHT, fill=tk.Y)

        self.table.bind("<Double-1>", self.on_table_double_click)
        self.table.bind("<Button-3>", self.show_context_menu)

        # Context Menu
        self.ctx_menu = tk.Menu(self, tearoff=0, bg=CLR_PANEL, fg=CLR_TEXT)
        self.ctx_menu.add_command(label="Open File", command=self.open_selected_file)
        self.ctx_menu.add_command(label="Open Folder", command=self.open_selected_folder)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Resume", command=self.resume_selected)
        self.ctx_menu.add_command(label="Pause", command=self.stop_selected)
        self.ctx_menu.add_command(label="Delete", command=self.delete_selected)

    def _build_statusbar(self):
        self.statusbar = tk.Label(
            self, text="Ready", bd=1, relief=tk.FLAT, anchor="w",
            font=("Segoe UI", 9), padx=10, pady=4,
            bg=CLR_PANEL, fg=CLR_TEXT_MUTED
        )
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def _populate_table(self):
        for item in self.table.get_children():
            self.table.delete(item)
        for h in self.history:
            self.table.insert("", "end", iid=h["id"], values=(
                h.get("filename", "Unknown"),
                h.get("size_str", "--"),
                h.get("status", "Completed"),
                h.get("time_left", "--"),
                h.get("speed_str", "--"),
                h.get("date", "--")
            ))

    def open_add_url_dialog(self):
        """The iconic IDM 'Enter new address to download' modal pop-up in Dark Mode."""
        dlg = tk.Toplevel(self)
        dlg.title("Enter new address to download")
        dlg.geometry("540x230")
        dlg.resizable(False, False)
        dlg.configure(bg=CLR_BG)
        dlg.lift()
        dlg.focus_force()

        initial_url = ""
        try:
            cb = self.clipboard_get().strip()
            if cb.startswith("http://") or cb.startswith("https://"):
                initial_url = cb
        except Exception:
            pass

        tk.Label(dlg, text="Address (URL):", bg=CLR_BG, fg=CLR_TEXT, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        
        url_entry = tk.Entry(
            dlg, font=("Segoe UI", 10), bg="#1e1e24", fg=CLR_TEXT,
            insertbackground=CLR_TEXT, relief=tk.FLAT,
            highlightbackground=CLR_BORDER, highlightcolor=CLR_ACCENT, highlightthickness=1
        )
        url_entry.pack(fill=tk.X, padx=16, ipady=4)
        url_entry.insert(0, initial_url)
        url_entry.focus()

        # Save to Row
        save_frame = tk.Frame(dlg, bg=CLR_BG)
        save_frame.pack(fill=tk.X, padx=16, pady=12)

        tk.Label(save_frame, text="Save to:", bg=CLR_BG, fg=CLR_TEXT, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        dir_var = tk.StringVar(value=self.save_dir)
        dir_ent = tk.Entry(
            save_frame, textvariable=dir_var, font=("Segoe UI", 9),
            bg="#1e1e24", fg=CLR_TEXT_MUTED, relief=tk.FLAT, state="readonly"
        )
        dir_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8, ipady=3)

        def browse():
            d = filedialog.askdirectory(initialdir=self.save_dir)
            if d:
                self.save_dir = d
                dir_var.set(d)

        tk.Button(
            save_frame, text="Browse...", font=("Segoe UI", 8),
            bg="#27272a", fg=CLR_TEXT, relief=tk.FLAT, cursor="hand2", command=browse
        ).pack(side=tk.RIGHT)

        # Buttons Row
        btn_box = tk.Frame(dlg, bg=CLR_BG)
        btn_box.pack(fill=tk.X, padx=16, pady=(10, 0))

        def start_now():
            u = url_entry.get().strip()
            if not u:
                messagebox.showwarning("Address required", "Please enter a valid download URL.")
                return
            dlg.destroy()
            self.spawn_download(u)

        tk.Button(
            btn_box, text="OK (Start Download)", font=("Segoe UI", 9, "bold"),
            bg=CLR_ACCENT, fg="#ffffff", activebackground=CLR_ACCENT_HOVER,
            relief=tk.FLAT, width=18, pady=6, cursor="hand2", command=start_now
        ).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(
            btn_box, text="Cancel", font=("Segoe UI", 9),
            bg="#27272a", fg=CLR_TEXT, relief=tk.FLAT, width=10, pady=6, cursor="hand2", command=dlg.destroy
        ).pack(side=tk.RIGHT)

    def spawn_download(self, url):
        self.statusbar.config(text=f"Connecting to: {url}...")
        
        def bg_probe():
            try:
                task = DownloadTask(url, self.save_dir, num_threads=16)
                task.inspect()
                self.after(0, lambda: self._on_task_ready(task))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Connection Error", str(e)))

        threading.Thread(target=bg_probe, daemon=True).start()

    def _on_task_ready(self, task):
        task_id = str(int(time.time() * 1000))
        size_display = format_size(task.total_size) if task.total_size > 0 else "Streaming"
        record = {
            "id": task_id,
            "url": task.url,
            "filename": task.filename,
            "filepath": task.filepath,
            "size": task.total_size,
            "size_str": size_display,
            "status": "Downloading",
            "time_left": "--",
            "speed_str": "Connecting...",
            "date": time.strftime("%Y-%m-%d %H:%M")
        }
        self.history.insert(0, record)
        self._save_history()
        self._populate_table()

        # Open IDM Progress Dialog
        prog_dlg = IDMProgressDialog(self, task, on_complete_callback=lambda: self._on_task_completed(task_id, record))
        self.active_tasks[task_id] = (task, prog_dlg)

        def run():
            def cb(cur, total, speed, eta, status):
                self.after(0, lambda: prog_dlg.update_telemetry(cur, total, speed, eta, status))
                tot_str = format_size(total) if total > 0 else format_size(cur)
                self.after(0, lambda: self._update_table_row(task_id, tot_str, status, format_eta(eta), format_speed(speed)))
            task.start(cb)

        threading.Thread(target=run, daemon=True).start()

    def _update_table_row(self, task_id, size_str, status, eta, speed):
        if self.table.exists(task_id):
            item = self.table.item(task_id)
            vals = list(item["values"])
            vals[1] = size_str
            vals[2] = status
            vals[3] = eta
            vals[4] = speed
            self.table.item(task_id, values=vals)

    def _on_task_completed(self, task_id, record):
        actual_size = os.path.getsize(record["filepath"]) if os.path.exists(record["filepath"]) else record["size"]
        record["size"] = actual_size
        record["size_str"] = format_size(actual_size)
        record["status"] = "Completed"
        record["time_left"] = "00:00"
        record["speed_str"] = "Done"
        self._save_history()
        self._update_table_row(task_id, record["size_str"], "Completed", "00:00", "Done")
        self.statusbar.config(text=f"Completed: {record['filename']}")

    def show_context_menu(self, event):
        item = self.table.identify_row(event.y)
        if item:
            self.table.selection_set(item)
            self.ctx_menu.post(event.x_root, event.y_root)

    def on_table_double_click(self, event):
        self.open_selected_file()

    def open_selected_file(self):
        sel = self.table.selection()
        if sel:
            task_id = sel[0]
            rec = next((h for h in self.history if h["id"] == task_id), None)
            if rec and os.path.exists(rec.get("filepath", "")):
                os.startfile(rec["filepath"])
            else:
                messagebox.showinfo("File missing", "The downloaded file could not be found.")

    def open_selected_folder(self):
        sel = self.table.selection()
        if sel:
            task_id = sel[0]
            rec = next((h for h in self.history if h["id"] == task_id), None)
            if rec and os.path.exists(rec.get("filepath", "")):
                subprocess.run(["explorer", os.path.dirname(rec["filepath"])])
            elif os.path.exists(self.save_dir):
                subprocess.run(["explorer", self.save_dir])

    def resume_selected(self):
        sel = self.table.selection()
        if sel:
            task_id = sel[0]
            rec = next((h for h in self.history if h["id"] == task_id), None)
            if rec:
                self.spawn_download(rec["url"])

    def stop_selected(self):
        sel = self.table.selection()
        if sel:
            task_id = sel[0]
            if task_id in self.active_tasks:
                task, dlg = self.active_tasks[task_id]
                task.pause()

    def stop_all(self):
        for task_id, (task, dlg) in self.active_tasks.items():
            task.pause()
        self.statusbar.config(text="All downloads stopped.")

    def delete_selected(self):
        sel = self.table.selection()
        if sel:
            task_id = sel[0]
            self.history = [h for h in self.history if h["id"] != task_id]
            self._save_history()
            self.table.delete(task_id)

    def open_settings(self):
        messagebox.showinfo(
            "VORTEX Options",
            f"Current Configuration:\n\n"
            f"• Default Save Directory:\n  {self.save_dir}\n\n"
            f"• Acceleration Threads: 16 Parallel Streams\n"
            f"• Theme: Deep OLED Black Mode\n"
            f"• Trial Expiration: NEVER (Lifetime Active)"
        )

if __name__ == "__main__":
    app = VortexIDM()
    app.mainloop()
