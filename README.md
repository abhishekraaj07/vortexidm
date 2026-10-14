# ⚡ VORTEX — High-Speed Download Accelerator (IDM Dark Edition)

A high-speed multi-threaded download manager inspired by Internet Download Manager (IDM) with pure Black OLED theme, multi-part parallel connections, pause/resume capability, and built-in YouTube/streaming media extractor.

## 🚀 Key Features

- **16x Multi-Threaded Acceleration**: Splits files into parallel chunks and downloads simultaneously.
- **Zero-Merge Pre-Allocation**: Instant download completion without disk merge overhead.
- **Pause & Resume**: Never lose partially downloaded files.
- **YouTube & Video Downloader**: Built-in `yt-dlp` stream extraction for YouTube, Instagram, Twitter/X, and Facebook videos directly into `.mp4`.
- **Iconic IDM UI (Black Mode)**:
  - Categories Tree (Compressed, Documents, Music, Programs, Video).
  - Multi-column download queue table.
  - Live 16-connection chunk progress stripes animation.
  - Right-click context menu (Open File, Open Folder, Resume, Pause, Delete).
- **100% Free & Open-Source**: Zero trial limits, zero licenses, zero ads.

## 📦 Running the App

```bash
# GUI Mode
python vortex.py

# CLI Mode
python vortex.py "https://example.com/file.zip" -t 16
```

## 🛠️ Requirements

- Python 3.10+
- `requests`
- `yt-dlp` (for video downloads)
