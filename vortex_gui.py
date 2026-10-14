import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess

from vortex_engine import DownloadTask, format_size, format_speed, format_eta

class VortexGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VORTEX — High-Speed Download Accelerator")
        self.root.geometry("740x580")
        self.root.minsize(700, 540)
        
        # Modern Dark Color Palette
        self.bg = "#0f172a"          # Slate 900
        self.card_bg = "#1e293b"     # Slate 800
        self.card_border = "#334155" # Slate 700
        self.accent = "#06b6d4"      # Cyan 500
        self.accent_glow = "#22d3ee" # Cyan 400
        self.success = "#10b981"     # Emerald 500
        self.warning = "#f59e0b"     # Amber 500
        self.danger = "#ef4444"      # Red 500
        self.text_main = "#f8fafc"   # Slate 50
        self.text_dim = "#94a3b8"    # Slate 400

        self.root.configure(bg=self.bg)

        # Default save directory (Downloads folder)
        self.save_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        self.current_task = None
        self.download_thread = None

        self._build_ui()
        self._check_clipboard_for_url()

    def _build_ui(self):
        # 1. Header Frame
        header = tk.Frame(self.root, bg=self.bg, pady=16, padx=24)
        header.pack(fill=tk.X)

        title_lbl = tk.Label(
            header,
            text="⚡ VORTEX ACCELERATOR",
            font=("Segoe UI", 18, "bold"),
            fg=self.text_main,
            bg=self.bg
        )
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(
            header,
            text="16x Multi-Threaded Engine • No Trial • No Speed Caps • Lifetime Free",
            font=("Segoe UI", 10),
            fg=self.accent,
            bg=self.bg
        )
        sub_lbl.pack(anchor="w")

        # 2. Input Container Card
        input_card = tk.Frame(self.root, bg=self.card_bg, highlightbackground=self.card_border, highlightthickness=1, padx=20, pady=18)
        input_card.pack(fill=tk.X, padx=24, pady=6)

        # URL row
        url_lbl = tk.Label(input_card, text="Download Link (URL):", font=("Segoe UI", 10, "bold"), fg=self.text_main, bg=self.card_bg)
        url_lbl.pack(anchor="w")

        url_row = tk.Frame(input_card, bg=self.card_bg)
        url_row.pack(fill=tk.X, pady=(4, 12))

        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(
            url_row,
            textvariable=self.url_var,
            font=("Consolas", 11),
            bg="#0b0f19",
            fg="#e2e8f0",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            highlightbackground=self.card_border,
            highlightcolor=self.accent,
            highlightthickness=1
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 8))

        btn_paste = tk.Button(
            url_row,
            text="📋 Paste",
            font=("Segoe UI", 9, "bold"),
            bg="#334155",
            fg=self.text_main,
            activebackground="#475569",
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=12,
            cursor="hand2",
            command=self._paste_clipboard
        )
        btn_paste.pack(side=tk.RIGHT)

        # Options Row: Save Directory + Threads
        opts_row = tk.Frame(input_card, bg=self.card_bg)
        opts_row.pack(fill=tk.X)

        # Save Directory
        dir_frame = tk.Frame(opts_row, bg=self.card_bg)
        dir_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 16))

        dir_lbl = tk.Label(dir_frame, text="Save Location:", font=("Segoe UI", 10, "bold"), fg=self.text_main, bg=self.card_bg)
        dir_lbl.pack(anchor="w")

        dir_sub = tk.Frame(dir_frame, bg=self.card_bg)
        dir_sub.pack(fill=tk.X, pady=(4, 0))

        self.dir_var = tk.StringVar(value=self.save_dir)
        self.dir_entry = tk.Entry(
            dir_sub,
            textvariable=self.dir_var,
            font=("Segoe UI", 10),
            bg="#0b0f19",
            fg="#cbd5e1",
            relief=tk.FLAT,
            highlightbackground=self.card_border,
            highlightthickness=1
        )
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))

        btn_browse = tk.Button(
            dir_sub,
            text="Browse",
            font=("Segoe UI", 9),
            bg="#334155",
            fg=self.text_main,
            relief=tk.FLAT,
            padx=8,
            cursor="hand2",
            command=self._browse_dir
        )
        btn_browse.pack(side=tk.RIGHT)

        # Threads selector
        thread_frame = tk.Frame(opts_row, bg=self.card_bg)
        thread_frame.pack(side=tk.RIGHT)

        thread_lbl = tk.Label(thread_frame, text="Connections (Threads):", font=("Segoe UI", 10, "bold"), fg=self.text_main, bg=self.card_bg)
        thread_lbl.pack(anchor="w")

        self.threads_var = tk.StringVar(value="16")
        thread_cb = ttk.Combobox(
            thread_frame,
            textvariable=self.threads_var,
            values=["4", "8", "16", "24", "32"],
            state="readonly",
            width=6,
            font=("Segoe UI", 10)
        )
        thread_cb.pack(anchor="w", pady=(4, 0), ipady=2)

        # 3. Telemetry & Progress Card
        self.progress_card = tk.Frame(self.root, bg=self.card_bg, highlightbackground=self.card_border, highlightthickness=1, padx=20, pady=18)
        self.progress_card.pack(fill=tk.X, padx=24, pady=12)

        # Status & Filename Row
        status_row = tk.Frame(self.progress_card, bg=self.card_bg)
        status_row.pack(fill=tk.X, pady=(0, 10))

        self.lbl_filename = tk.Label(
            status_row,
            text="Ready — Paste a link to begin",
            font=("Segoe UI", 11, "bold"),
            fg=self.text_main,
            bg=self.card_bg
        )
        self.lbl_filename.pack(side=tk.LEFT)

        self.lbl_percent = tk.Label(
            status_row,
            text="0%",
            font=("Consolas", 12, "bold"),
            fg=self.accent,
            bg=self.card_bg
        )
        self.lbl_percent.pack(side=tk.RIGHT)

        # Custom Canvas Progress Bar
        self.canvas_w = 650
        self.canvas_h = 14
        self.progress_canvas = tk.Canvas(
            self.progress_card,
            width=self.canvas_w,
            height=self.canvas_h,
            bg="#0b0f19",
            highlightthickness=0
        )
        self.progress_canvas.pack(fill=tk.X, pady=(0, 12))
        self.bar_rect = self.progress_canvas.create_rectangle(0, 0, 0, self.canvas_h, fill=self.accent, width=0)

        # Metrics Grid (Speed, Downloaded, ETA)
        metrics_row = tk.Frame(self.progress_card, bg=self.card_bg)
        metrics_row.pack(fill=tk.X)

        self.lbl_speed = tk.Label(
            metrics_row,
            text="Speed: 0.00 B/s",
            font=("Segoe UI", 10),
            fg=self.text_dim,
            bg=self.card_bg
        )
        self.lbl_speed.pack(side=tk.LEFT)

        self.lbl_downloaded = tk.Label(
            metrics_row,
            text="Size: --",
            font=("Segoe UI", 10),
            fg=self.text_dim,
            bg=self.card_bg
        )
        self.lbl_downloaded.pack(side=tk.LEFT, padx=30)

        self.lbl_eta = tk.Label(
            metrics_row,
            text="ETA: --:--",
            font=("Segoe UI", 10),
            fg=self.text_dim,
            bg=self.card_bg
        )
        self.lbl_eta.pack(side=tk.RIGHT)

        # 4. Action Buttons Frame
        btn_bar = tk.Frame(self.root, bg=self.bg)
        btn_bar.pack(fill=tk.X, padx=24, pady=4)

        self.btn_start = tk.Button(
            btn_bar,
            text="⚡ Start Download",
            font=("Segoe UI", 11, "bold"),
            bg=self.accent,
            fg="#042f2e",
            activebackground=self.accent_glow,
            relief=tk.FLAT,
            padx=20,
            pady=8,
            cursor="hand2",
            command=self.start_download
        )
        self.btn_start.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_pause = tk.Button(
            btn_bar,
            text="⏸️ Pause",
            font=("Segoe UI", 10),
            bg="#334155",
            fg=self.text_main,
            relief=tk.FLAT,
            padx=14,
            pady=8,
            state=tk.DISABLED,
            command=self.pause_download
        )
        self.btn_pause.pack(side=tk.LEFT, padx=(0, 10))

        self.btn_cancel = tk.Button(
            btn_bar,
            text="❌ Cancel",
            font=("Segoe UI", 10),
            bg="#334155",
            fg=self.danger,
            relief=tk.FLAT,
            padx=14,
            pady=8,
            state=tk.DISABLED,
            command=self.cancel_download
        )
        self.btn_cancel.pack(side=tk.LEFT)

        self.btn_open_file = tk.Button(
            btn_bar,
            text="▶️ Open File",
            font=("Segoe UI", 10, "bold"),
            bg="#065f46",
            fg="#a7f3d0",
            relief=tk.FLAT,
            padx=12,
            pady=8,
            state=tk.DISABLED,
            command=self.open_file
        )
        self.btn_open_file.pack(side=tk.RIGHT)

        self.btn_open_folder = tk.Button(
            btn_bar,
            text="📂 Open Folder",
            font=("Segoe UI", 10),
            bg="#334155",
            fg=self.text_main,
            relief=tk.FLAT,
            padx=12,
            pady=8,
            state=tk.DISABLED,
            command=self.open_folder
        )
        self.btn_open_folder.pack(side=tk.RIGHT, padx=10)

        # 5. Footer info
        footer = tk.Label(
            self.root,
            text="VORTEX Engine v1.0.0 • Open Source • Pure Speed",
            font=("Segoe UI", 9),
            fg="#475569",
            bg=self.bg
        )
        footer.pack(side=tk.BOTTOM, pady=10)

    def _paste_clipboard(self):
        try:
            cb = self.root.clipboard_get().strip()
            if cb.startswith("http://") or cb.startswith("https://"):
                self.url_var.set(cb)
        except Exception:
            pass

    def _check_clipboard_for_url(self):
        try:
            cb = self.root.clipboard_get().strip()
            if cb.startswith("http://") or cb.startswith("https://"):
                self.url_var.set(cb)
        except Exception:
            pass

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.save_dir, title="Select Download Folder")
        if d:
            self.save_dir = d
            self.dir_var.set(d)

    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("URL Required", "Please enter or paste a valid download link.")
            return

        threads = int(self.threads_var.get())
        save_path = self.dir_var.get().strip()

        self.btn_start.config(state=tk.DISABLED)
        self.btn_pause.config(state=tk.NORMAL)
        self.btn_cancel.config(state=tk.NORMAL)
        self.btn_open_file.config(state=tk.DISABLED)
        self.btn_open_folder.config(state=tk.DISABLED)

        self.lbl_filename.config(text="Connecting and probing server...")
        self.lbl_speed.config(text="Speed: Connecting...")

        def run_thread():
            try:
                task = DownloadTask(url, save_path, num_threads=threads)
                task.inspect()
                self.current_task = task

                self.root.after(0, lambda: self.lbl_filename.config(
                    text=f"{task.filename} ({format_size(task.total_size)})"
                ))

                task.start(self._progress_callback)

                self.root.after(0, self._on_download_finished)
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Download Error", str(e)))
                self.root.after(0, self._reset_controls)

        self.download_thread = threading.Thread(target=run_thread, daemon=True)
        self.download_thread.start()

    def _progress_callback(self, cur, total, speed, eta, status):
        pct = (cur / total * 100) if total > 0 else 0
        def update():
            # Update canvas bar
            w = self.progress_canvas.winfo_width()
            fill_w = int((pct / 100) * w)
            self.progress_canvas.coords(self.bar_rect, 0, 0, fill_w, self.canvas_h)
            
            self.lbl_percent.config(text=f"{pct:.1f}%")
            self.lbl_speed.config(text=f"⚡ {format_speed(speed)}")
            self.lbl_downloaded.config(text=f"📥 {format_size(cur)} / {format_size(total)}")
            self.lbl_eta.config(text=f"⏱️ ETA: {format_eta(eta)}")

            if status == "Paused":
                self.progress_canvas.itemconfig(self.bar_rect, fill=self.warning)
                self.lbl_filename.config(text="PAUSED — Click Start to Resume")
            elif status == "Completed":
                self.progress_canvas.itemconfig(self.bar_rect, fill=self.success)
                self.lbl_filename.config(text="✅ COMPLETED!")
            else:
                self.progress_canvas.itemconfig(self.bar_rect, fill=self.accent)

        self.root.after(0, update)

    def _on_download_finished(self):
        if self.current_task and self.current_task.is_completed:
            self.btn_open_file.config(state=tk.NORMAL)
            self.btn_open_folder.config(state=tk.NORMAL)
            messagebox.showinfo("Download Complete", f"Successfully downloaded:\n{self.current_task.filename}")
        self._reset_controls()

    def _reset_controls(self):
        self.btn_start.config(state=tk.NORMAL)
        self.btn_pause.config(state=tk.DISABLED)
        self.btn_cancel.config(state=tk.DISABLED)

    def pause_download(self):
        if self.current_task:
            self.current_task.pause()
            self._reset_controls()

    def cancel_download(self):
        if self.current_task:
            self.current_task.cancel()
            self.lbl_filename.config(text="Download Cancelled")
            self._reset_controls()

    def open_file(self):
        if self.current_task and os.path.exists(self.current_task.filepath):
            os.startfile(self.current_task.filepath)

    def open_folder(self):
        if self.current_task and os.path.exists(self.current_task.filepath):
            folder = os.path.dirname(self.current_task.filepath)
            subprocess.run(["explorer", folder])
        elif os.path.exists(self.save_dir):
            subprocess.run(["explorer", self.save_dir])

if __name__ == "__main__":
    root = tk.Tk()
    app = VortexGUI(root)
    root.mainloop()
