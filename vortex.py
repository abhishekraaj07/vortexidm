#!/usr/bin/env python3
"""
VORTEX Download Accelerator
High-speed multi-threaded file downloader with resume support.
Can be used via GUI or CLI.
"""
import sys
import os
import argparse

# Enable UTF-8 for Windows console if possible
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from vortex_engine import DownloadTask, format_size, format_speed, format_eta
from vortex_idm_ui import VortexIDM

def run_cli(url, output_dir, filename, threads):
    print("=" * 60)
    print(">> VORTEX DOWNLOAD ACCELERATOR (CLI MODE)")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Threads: {threads}")
    print("Connecting...")

    task = DownloadTask(url, output_dir, filename=filename, num_threads=threads)
    try:
        task.inspect()
    except Exception as e:
        print(f"Error inspecting URL: {e}")
        sys.exit(1)

    print(f"Target Filename: {task.filename}")
    print(f"File Size      : {format_size(task.total_size)}")
    print(f"Range Support  : {'Yes (Multi-threaded Acceleration)' if task.supports_ranges else 'No (Single Stream)'}")
    print("-" * 60)

    def progress_callback(cur, total, speed, eta, status):
        pct = (cur / total * 100) if total > 0 else 0
        bar_len = 25
        filled = int((pct / 100) * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write(
            f"\r[{status}] [{bar}] {pct:5.1f}% | {format_size(cur)}/{format_size(total)} | {format_speed(speed):>11} | ETA: {format_eta(eta)}"
        )
        sys.stdout.flush()

    try:
        task.start(progress_callback)
        print("\n" + "=" * 60)
        if task.is_completed:
            print("Download complete! Saved to:")
            print(f"   {task.filepath}")
        elif task.is_paused:
            print("Download paused.")
        elif task.is_cancelled:
            print("Download cancelled.")
    except KeyboardInterrupt:
        print("\nPausing download...")
        task.pause()
        print("Progress saved. Run the same command to resume.")

def run_gui():
    from vortex_idm_ui import VortexIDM
    app = VortexIDM()
    app.mainloop()

def main():
    parser = argparse.ArgumentParser(description="VORTEX High-Speed Multi-Threaded Download Accelerator")
    parser.add_argument("url", nargs="?", help="URL of the file to download")
    parser.add_argument("-o", "--output", default=os.path.join(os.path.expanduser("~"), "Downloads"), help="Output directory")
    parser.add_argument("-f", "--filename", default=None, help="Custom output filename")
    parser.add_argument("-t", "--threads", type=int, default=16, help="Number of parallel download threads (default: 16)")
    parser.add_argument("--cli", action="store_true", help="Force CLI mode even without arguments")

    args = parser.parse_args()

    if args.url or args.cli:
        if not args.url:
            print("Error: URL is required in CLI mode.")
            sys.exit(1)
        run_cli(args.url, args.output, args.filename, args.threads)
    else:
        run_gui()

if __name__ == "__main__":
    main()
