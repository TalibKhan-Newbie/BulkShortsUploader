"""
ShortUploader — Termux Edition
YouTube URL se shorts banao aur multiple platforms pe upload karo.
Run: python main.py
"""

import os
import sys
import subprocess
import threading
import concurrent.futures
import random
import time
import json

from config import (
    CLIPS_DIR, DOWNLOADS_DIR,
    CHUNK_DURATION, CHUNK_DURATION_MIN, CHUNK_DURATION_MAX,
    SPEED, MUTE_AUDIO,
    TARGET_W, TARGET_H,
    CRF, FPS, MAX_WORKERS,
    UPLOAD_DELAY,
    ENABLE_YOUTUBE, ENABLE_INSTAGRAM, ENABLE_FACEBOOK,
    YOUTUBE_DAILY_LIMIT, INSTAGRAM_DAILY_LIMIT, FACEBOOK_DAILY_LIMIT,
)
from upload import (
    get_youtube_client, upload_clip,
    print_quota_status, platform_remaining,
    already_uploaded,
)

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


def clear():
    os.system("clear")


def ask(prompt, options):
    if prompt:
        print(f"\n  {prompt}")
    for i, o in enumerate(options, 1):
        print(f"    {i}. {o}")
    print()
    while True:
        try:
            c = int(input("  Choice: ").strip())
            if 1 <= c <= len(options):
                return c
        except (ValueError, EOFError):
            pass
        print(f"  1-{len(options)} ke beech number daalo")


# ─── Platform selection ───────────────────────────────────────

def choose_platforms():
    """User se platforms choose karwao. Enabled platforms hi dikhao."""
    enabled = []
    if ENABLE_YOUTUBE:
        enabled.append("youtube")
    if ENABLE_INSTAGRAM:
        enabled.append("instagram")
    if ENABLE_FACEBOOK:
        enabled.append("facebook")

    if len(enabled) == 1:
        return enabled  # sirf ek hai toh seedha wahi

    labels = {
        "youtube":   "YouTube",
        "instagram": "Instagram",
        "facebook":  "Facebook",
    }

    # Options: individual + combo + all
    options = []
    for p in enabled:
        options.append(labels[p] + " only")
    if len(enabled) >= 2:
        options.append(" + ".join(labels[p] for p in enabled) + "  (sab)")

    choice = ask("Kahan upload karna hai?", options)

    if choice <= len(enabled):
        return [enabled[choice - 1]]
    else:
        return enabled


# ─── FFmpeg helpers ───────────────────────────────────────────

def get_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError(f"ffprobe failed for {path}: {r.stderr}")


def process_chunk(task):
    input_path, start, clip_dur, num, total, out_path = task

    # Blurred background: landscape source is letterboxed into 9:16 frame.
    # bg = source scaled+cropped to fill frame then blurred
    # fg = source scaled to fit fully within frame (no crop, full content visible)
    # overlay fg centered on bg
    if not MUTE_AUDIO:
        fc = (
            f"[0:v]split=2[v1][v2];"
            f"[v1]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_W}:{TARGET_H},boxblur=20:5,setpts=PTS/{SPEED}[bg];"
            f"[v2]scale={TARGET_W}:-2,setpts=PTS/{SPEED}[fg];"
            f"[bg][fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2[v];"
            f"[0:a]atempo={SPEED}[a]"
        )
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        fc = (
            f"[0:v]split=2[v1][v2];"
            f"[v1]scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
            f"crop={TARGET_W}:{TARGET_H},boxblur=20:5,setpts=PTS/{SPEED}[bg];"
            f"[v2]scale={TARGET_W}:-2,setpts=PTS/{SPEED}[fg];"
            f"[bg][fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2[v]"
        )
        maps = ["-map", "[v]"]

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(round(start, 3)),
        "-i", input_path,
        "-t", str(round(clip_dur, 3)),
        "-filter_complex", fc,
        *maps,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", str(CRF), "-threads", "2",
        *(("-c:a", "aac") if not MUTE_AUDIO else ()),
        "-r", str(FPS),
        out_path,
    ]

    log(f"  [{num}/{total}] Processing → {os.path.basename(out_path)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {r.stderr[-300:]}")
    log(f"  [{num}/{total}] Done      → {os.path.basename(out_path)}")
    return out_path


def random_starts(duration, n):
    starts = []
    zone = duration / n
    for i in range(n):
        dur = random.uniform(CHUNK_DURATION_MIN, CHUNK_DURATION_MAX)
        zs  = i * zone
        ze  = (i + 1) * zone
        ls  = ze - dur
        s   = random.uniform(zs, ls) if ls > zs else zs
        s   = max(0.0, min(s, duration - dur))
        starts.append((s, dur))
    return starts


def process_video(video_path, n_clips):
    os.makedirs(CLIPS_DIR, exist_ok=True)
    tasks  = []
    points = random_starts(get_duration(video_path), n_clips)

    for i, (s, d) in enumerate(points, 1):
        while True:
            rid = random.randint(10000, 99999)
            out = os.path.join(CLIPS_DIR, f"clip_{rid}.mp4")
            if not os.path.exists(out):
                break
        tasks.append((video_path, s, d, i, n_clips, out))

    print(f"\n  {n_clips} clips ban rahi hain (libx264, workers={MAX_WORKERS})...\n")
    done = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(process_chunk, t): t for t in tasks}
        for f in concurrent.futures.as_completed(futs):
            try:
                done.append(f.result())
            except Exception as e:
                log(f"  FAILED: {e}")

    print(f"\n  {len(done)}/{len(tasks)} clips ready.\n")
    return sorted(done)


# ─── Download ─────────────────────────────────────────────────

def download_youtube(url):
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)
    tmpl = os.path.join(DOWNLOADS_DIR, "%(title).50s.%(ext)s")
    print("\n  Downloading...")
    r = subprocess.run(
        [sys.executable, "-m", "yt_dlp",
         "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
         "--merge-output-format", "mp4",
         "-o", tmpl, "--no-playlist", "--progress", url],
        text=True,
    )
    if r.returncode != 0:
        print("  Download fail ho gaya!")
        return None

    files = sorted(
        [os.path.join(DOWNLOADS_DIR, f) for f in os.listdir(DOWNLOADS_DIR)
         if f.lower().endswith(".mp4")],
        key=os.path.getmtime, reverse=True,
    )
    if files:
        print(f"  Downloaded: {os.path.basename(files[0])}")
        return files[0]
    return None


# ─── Clip count prompt ────────────────────────────────────────

def ask_clip_count(video_path, platforms):
    dur   = get_duration(video_path)
    max_n = int(dur // CHUNK_DURATION)
    mins, secs = int(dur // 60), int(dur % 60)

    # Quota ki sabse choti remaining limit lo
    quota_min = min(platform_remaining(p) for p in platforms)
    max_n = min(max_n, quota_min)

    print(f"\n  Video : {os.path.basename(video_path)}")
    print(f"  Length: {mins}m {secs}s | Max clips: {max_n}")
    print_quota_status()

    if max_n <= 0:
        print("  Quota khatam ya video bahut choti hai!")
        return 0

    while True:
        try:
            n = int(input(f"\n  Kitni clips banana hai? (1-{max_n}): ").strip())
            if 1 <= n <= max_n:
                return n
        except (ValueError, EOFError):
            pass
        print(f"  1-{max_n} ke beech number daalo")


# ─── Handlers ─────────────────────────────────────────────────

def handle_url(yt, platforms):
    url = input("\n  YouTube URL daalo: ").strip()
    if not url:
        print("  URL nahi diya.")
        return

    video_desc = input("  Video topic/description (metadata ke liye): ").strip()

    path = download_youtube(url)
    if not path:
        return

    n = ask_clip_count(path, platforms)
    if n == 0:
        return

    clips = process_video(path, n)
    if not clips:
        print("  Koi clip nahi bani.")
        return

    plat_str = " + ".join(p.upper() for p in platforms)
    print(f"  {len(clips)} clips upload ho rahi hain → {plat_str}")
    for i, clip in enumerate(clips):
        upload_clip(clip, youtube=yt, platforms=platforms, video_desc=video_desc)
        if i < len(clips) - 1:
            print(f"  [{UPLOAD_DELAY}s wait...]")
            time.sleep(UPLOAD_DELAY)


def handle_saved_clips(yt, platforms):
    if not os.path.isdir(CLIPS_DIR):
        print(f"\n  {CLIPS_DIR}/ folder nahi mila.")
        return

    clips = sorted([
        os.path.join(CLIPS_DIR, f)
        for f in os.listdir(CLIPS_DIR)
        if f.lower().endswith(".mp4")
    ])

    if not clips:
        print(f"\n  {CLIPS_DIR}/ mein koi clip nahi mili.")
        return

    quota_min = min(platform_remaining(p) for p in platforms)
    max_n     = min(len(clips), quota_min)

    print(f"\n  {len(clips)} clips mili:\n")
    for i, c in enumerate(clips, 1):
        name = os.path.basename(c)
        tags = [p[0].upper() for p in platforms if already_uploaded(name, p)]
        tag  = f" [{','.join(tags)} done]" if tags else ""
        print(f"    {i}. {name}{tag}")

    print()
    print_quota_status()

    if max_n <= 0:
        print("\n  Quota khatam ho gayi hai!")
        return

    while True:
        try:
            n = int(input(f"\n  Kitni clips upload karni hain? (1-{max_n}): ").strip())
            if 1 <= n <= max_n:
                break
        except (ValueError, EOFError):
            pass
        print(f"  1-{max_n} ke beech daalo")

    video_desc = input("\n  Video topic/description (metadata ke liye, blank=skip): ").strip()

    plat_str = " + ".join(p.upper() for p in platforms)
    print(f"\n  Upload → {plat_str}")
    selected = clips[:n]
    for i, clip in enumerate(selected):
        upload_clip(clip, youtube=yt, platforms=platforms, video_desc=video_desc)
        if i < len(selected) - 1:
            print(f"  [{UPLOAD_DELAY}s wait...]")
            time.sleep(UPLOAD_DELAY)


# ─── Facebook Reels ──────────────────────────────────────────

def handle_facebook_reels(yt, platforms):
    profile_url = input(
        "\n  Facebook profile URL daalo:\n"
        "  (e.g. https://www.facebook.com/username): "
    ).strip()
    if not profile_url:
        print("  URL nahi diya.")
        return

    base = profile_url.rstrip("/")
    reels_url = base if "/reels" in base else base + "/reels/"

    fb_folder = os.path.join(DOWNLOADS_DIR, "fb_reels")
    os.makedirs(fb_folder, exist_ok=True)

    cookies_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fb_cookies.txt")
    auth_args = ["--cookies", cookies_file] if os.path.exists(cookies_file) else []

    print(f"\n  Reels list fetch ho rahi hai...")

    list_cmd = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist", "-j", "--no-warnings",
        *auth_args, reels_url,
    ]
    r = subprocess.run(list_cmd, capture_output=True, text=True)

    urls = []
    for line in r.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            url = data.get("webpage_url") or data.get("url")
            if url:
                urls.append(url)
        except json.JSONDecodeError:
            pass

    if not urls:
        print("  Reels nahi mili ya profile private hai.")
        print()
        print("  Private profile ke liye fb_cookies.txt banao:")
        print("  1. Android Chrome mein facebook.com kholo")
        print("  2. PC pe 'Get cookies.txt LOCALLY' extension use karo")
        print("  3. fb_cookies.txt → project folder mein rakho")
        return

    print(f"  {len(urls)} reels mili!")

    while True:
        try:
            n = int(input(f"  Kitni download karni hain? (1-{len(urls)}, 0=sab): ").strip())
            if 0 <= n <= len(urls):
                break
        except (ValueError, EOFError):
            pass

    selected_urls = urls if n == 0 else urls[:n]
    total = len(selected_urls)
    print(f"\n  {total} reels download ho rahi hain → {fb_folder}\n")

    for i, reel_url in enumerate(selected_urls, 1):
        out_tmpl = os.path.join(fb_folder, f"fb_reel_{i:03d}.%(ext)s")
        dl_cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", out_tmpl, "--no-playlist", "--no-warnings",
            *auth_args, reel_url,
        ]
        log(f"  [{i}/{total}] Downloading...")
        dr = subprocess.run(dl_cmd, capture_output=True, text=True)
        if dr.returncode != 0:
            log(f"  [{i}/{total}] FAIL: {reel_url}")
        else:
            log(f"  [{i}/{total}] Done!")

    downloaded = sorted(
        [os.path.join(fb_folder, f) for f in os.listdir(fb_folder)
         if f.lower().endswith(".mp4")],
        key=os.path.getmtime,
    )

    if not downloaded:
        print("  Koi file download nahi hui.")
        return

    print(f"\n  {len(downloaded)} clips ready.\n")
    print_quota_status()

    quota_min = min(platform_remaining(p) for p in platforms)
    max_n = min(len(downloaded), quota_min)

    if max_n <= 0:
        print("  Quota khatam hai!")
        return

    while True:
        try:
            up_n = int(input(f"  Kitni upload karni hain? (1-{max_n}): ").strip())
            if 1 <= up_n <= max_n:
                break
        except (ValueError, EOFError):
            pass

    video_desc = input("  Video topic/description (metadata ke liye, blank=skip): ").strip()

    plat_str = " + ".join(p.upper() for p in platforms)
    print(f"\n  Upload → {plat_str}")
    for i, clip in enumerate(downloaded[:up_n]):
        upload_clip(clip, youtube=yt, platforms=platforms, video_desc=video_desc)
        if i < up_n - 1:
            print(f"  [{UPLOAD_DELAY}s wait...]")
            time.sleep(UPLOAD_DELAY)


# ─── Main ─────────────────────────────────────────────────────

def main():
    yt = None
    while True:
        clear()
        print()
        print("  ╔══════════════════════════════════════╗")
        print("  ║   ShortUploader  —  Termux Edition   ║")
        print("  ╚══════════════════════════════════════╝")
        print_quota_status()

        choice = ask("Menu:", [
            "URL se download → shorts → upload",
            "Saved clips upload karo",
            "Facebook Reels download → upload",
            "Exit",
        ])

        if choice == 4:
            print("\n  Bye!\n")
            break

        platforms = choose_platforms()

        if "youtube" in platforms and yt is None:
            print("\n  YouTube pe login ho raha hai...")
            try:
                yt = get_youtube_client()
                print("  Login successful!")
            except SystemExit:
                input("\n  Enter dabao...")
                continue
            except Exception as e:
                print(f"  Login fail: {e}")
                input("\n  Enter dabao...")
                continue

        if choice == 1:
            handle_url(yt, platforms)
        elif choice == 2:
            handle_saved_clips(yt, platforms)
        elif choice == 3:
            handle_facebook_reels(yt, platforms)

        print("\n  " + "─" * 38)
        input("  Enter dabao menu ke liye...")


if __name__ == "__main__":
    main()
