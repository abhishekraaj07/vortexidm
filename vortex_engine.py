import os
import sys
import time
import json
import threading
import urllib.parse
import re
import requests

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

VIDEO_DOMAINS = [
    "youtube.com", "youtu.be", "instagram.com", "twitter.com",
    "x.com", "tiktok.com", "facebook.com", "fb.watch", "vimeo.com"
]

def is_video_site(url):
    u = url.lower()
    return any(domain in u for domain in VIDEO_DOMAINS)

def format_size(bytes_num):
    if bytes_num is None or bytes_num <= 0:
        return "0.00 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_num < 1024.0:
            return f"{bytes_num:.2f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.2f} PB"

def format_speed(bps):
    return f"{format_size(bps)}/s"

def format_eta(seconds):
    if seconds is None or seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class DownloadTask:
    def __init__(self, url, save_dir, filename=None, num_threads=16):
        self.url = url.strip()
        self.save_dir = save_dir
        self.custom_filename = filename
        self.num_threads = max(1, min(num_threads, 32))
        
        self.filename = None
        self.filepath = None
        self.meta_path = None
        self.total_size = 0
        self.supports_ranges = False
        self.is_video_stream = is_video_site(self.url)
        
        self.downloaded_bytes = 0
        self.speed = 0
        self.eta = None
        
        self.is_paused = False
        self.is_cancelled = False
        self.is_completed = False
        self.error_message = None
        
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.chunks = []

    def inspect(self):
        """Probe URL or fetch video metadata."""
        if self.is_video_stream:
            self._inspect_video()
            return self

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        try:
            r = requests.head(self.url, headers=headers, allow_redirects=True, timeout=12)
            if r.status_code >= 400 or "content-length" not in r.headers:
                r = requests.get(self.url, headers=headers, stream=True, timeout=12)
                r.close()
        except Exception as e:
            raise RuntimeError(f"Connection failed: {e}")

        # Total size
        self.total_size = int(r.headers.get("content-length", 0))
        accept_ranges = r.headers.get("accept-ranges", "").lower()
        self.supports_ranges = (accept_ranges == "bytes") or (self.total_size > 0 and r.status_code == 206)

        # Detect filename
        if self.custom_filename:
            self.filename = self.custom_filename
        else:
            cd = r.headers.get("content-disposition", "")
            if "filename=" in cd:
                match = re.findall(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)["\']?', cd)
                if match:
                    self.filename = urllib.parse.unquote(match[0].strip())
            
            if not self.filename:
                parsed = urllib.parse.urlparse(r.url)
                path = urllib.parse.unquote(parsed.path)
                basename = os.path.basename(path)
                if basename and "." in basename and not basename.endswith((".html", ".htm", ".php", ".jsp")):
                    self.filename = basename
                else:
                    # Guess by content-type
                    ct = r.headers.get("content-type", "").lower()
                    ext = ".bin"
                    if "video/mp4" in ct: ext = ".mp4"
                    elif "audio/mpeg" in ct: ext = ".mp3"
                    elif "application/zip" in ct: ext = ".zip"
                    elif "application/pdf" in ct: ext = ".pdf"
                    self.filename = f"download_{int(time.time())}{ext}"

        self.filename = re.sub(r'[\\/*?:"<>|]', "_", self.filename)
        self.filepath = os.path.join(self.save_dir, self.filename)
        self.meta_path = self.filepath + ".vortex.json"
        return self

    def _inspect_video(self):
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
                title = info.get('title', f"video_{int(time.time())}")
                self.filename = re.sub(r'[\\/*?:"<>|]', "_", title) + ".mp4"
                self.filepath = os.path.join(self.save_dir, self.filename)
                self.total_size = info.get('filesize') or info.get('filesize_approx') or 0
                self.supports_ranges = True
        except Exception as e:
            # Fallback
            self.filename = f"video_{int(time.time())}.mp4"
            self.filepath = os.path.join(self.save_dir, self.filename)
            self.total_size = 0

    def start(self, progress_callback=None):
        self.is_paused = False
        self.is_cancelled = False
        self.is_completed = False
        self._stop_event.clear()

        os.makedirs(self.save_dir, exist_ok=True)

        if self.is_video_stream:
            self._download_video_stream(progress_callback)
            return

        if not self.supports_ranges or self.total_size <= 0:
            self._download_single_stream(progress_callback)
            return

        # Prepare chunks for multi-threaded download
        part_size = self.total_size // self.num_threads
        self.chunks = []
        for i in range(self.num_threads):
            start = i * part_size
            end = self.total_size - 1 if i == self.num_threads - 1 else (start + part_size - 1)
            self.chunks.append({
                "id": i,
                "start": start,
                "end": end,
                "downloaded": 0
            })

        if not os.path.exists(self.filepath) or os.path.getsize(self.filepath) != self.total_size:
            with open(self.filepath, "wb") as f:
                f.truncate(self.total_size)

        threads = []
        for chunk in self.chunks:
            t = threading.Thread(target=self._download_chunk, args=(chunk,))
            t.daemon = True
            threads.append(t)
            t.start()

        last_bytes = 0
        last_time = time.time()

        while any(t.is_alive() for t in threads):
            time.sleep(0.2)
            now = time.time()
            dt = now - last_time
            if dt >= 0.4:
                cur_bytes = self.downloaded_bytes
                delta = cur_bytes - last_bytes
                self.speed = max(0, delta / dt)
                remaining = self.total_size - cur_bytes
                self.eta = (remaining / self.speed) if self.speed > 0 else None
                last_bytes = cur_bytes
                last_time = now

                if progress_callback:
                    progress_callback(cur_bytes, self.total_size, self.speed, self.eta, "Downloading")

            if self._stop_event.is_set():
                break

        for t in threads:
            t.join(timeout=1.0)

        if not self.is_cancelled and not self.is_paused and self.downloaded_bytes >= self.total_size:
            self.is_completed = True
            if progress_callback:
                progress_callback(self.total_size, self.total_size, 0, 0, "Completed")

    def _download_chunk(self, chunk):
        cur_start = chunk["start"] + chunk["downloaded"]
        end = chunk["end"]
        if cur_start > end:
            return

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Range": f"bytes={cur_start}-{end}"
        }

        try:
            with requests.get(self.url, headers=headers, stream=True, timeout=15) as r:
                if r.status_code not in (200, 206):
                    return

                with open(self.filepath, "r+b") as f:
                    f.seek(cur_start)
                    for block in r.iter_content(chunk_size=65536):
                        if self._stop_event.is_set():
                            break
                        if block:
                            f.write(block)
                            with self._lock:
                                chunk["downloaded"] += len(block)
                                self.downloaded_bytes += len(block)
        except Exception as e:
            self.error_message = str(e)

    def _download_single_stream(self, progress_callback):
        headers = {"User-Agent": DEFAULT_USER_AGENT}
        with requests.get(self.url, headers=headers, stream=True, timeout=15) as r:
            last_time = time.time()
            last_bytes = 0
            with open(self.filepath, "wb") as f:
                for block in r.iter_content(chunk_size=65536):
                    if self._stop_event.is_set():
                        break
                    if block:
                        f.write(block)
                        self.downloaded_bytes += len(block)
                        now = time.time()
                        if now - last_time >= 0.4:
                            dt = now - last_time
                            self.speed = (self.downloaded_bytes - last_bytes) / dt
                            last_time = now
                            last_bytes = self.downloaded_bytes
                            tot = self.total_size if self.total_size > 0 else self.downloaded_bytes
                            if progress_callback:
                                progress_callback(self.downloaded_bytes, tot, self.speed, None, "Downloading")

        if not self._stop_event.is_set():
            self.total_size = self.downloaded_bytes
            self.is_completed = True
            if progress_callback:
                progress_callback(self.downloaded_bytes, self.total_size, 0, 0, "Completed")

    def _download_video_stream(self, progress_callback):
        import yt_dlp
        task = self

        def hook(d):
            if d['status'] == 'downloading':
                tot = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                cur = d.get('downloaded_bytes', 0)
                spd = d.get('speed') or 0
                eta = d.get('eta') or 0
                task.downloaded_bytes = cur
                task.total_size = tot if tot > 0 else cur
                task.speed = spd
                task.eta = eta
                if progress_callback:
                    progress_callback(cur, task.total_size, spd, eta, "Downloading")
            elif d['status'] == 'finished':
                task.filepath = d.get('filename', task.filepath)
                task.filename = os.path.basename(task.filepath)
                task.is_completed = True
                if progress_callback:
                    progress_callback(task.total_size, task.total_size, 0, 0, "Completed")

        out_template = os.path.join(self.save_dir, "%(title)s.%(ext)s")
        ydl_opts = {
            'outtmpl': out_template,
            'progress_hooks': [hook],
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.url])
        except Exception as e:
            self.error_message = str(e)
            if progress_callback:
                progress_callback(self.downloaded_bytes, self.total_size, 0, 0, f"Error: {e}")

    def pause(self):
        self.is_paused = True
        self._stop_event.set()

    def cancel(self):
        self.is_cancelled = True
        self._stop_event.set()
