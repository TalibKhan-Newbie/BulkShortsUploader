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

import re as _re
import requests as _requests


def _fb_load_cookies():
    tokens_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "get_tokens.txt")
    if not os.path.exists(tokens_file):
        return "", []
    with open(tokens_file) as f:
        cookie_str = f.read().strip()
    if not cookie_str:
        return "", []
    return cookie_str, ["--add-header", f"Cookie:{cookie_str}"]


def _fb_to_mbasic_url(raw_url):
    """
    Any Facebook URL → mbasic.facebook.com videos tab URL.
    mbasic = plain HTML version, no JS needed, easy to parse.
    """
    id_match = _re.search(r'[?&]id=(\d+)', raw_url)
    if id_match:
        return f"https://mbasic.facebook.com/profile.php?id={id_match.group(1)}&v=videos"

    path_match = _re.search(r'facebook\.com/(.+)', raw_url)
    if path_match:
        path = path_match.group(1).split("?")[0].rstrip("/")
        return f"https://mbasic.facebook.com/{path}/videos/"

    return None


def _fb_fetch(url, headers):
    """
    Fetch URL safely.
    Facebook kabhi kabhi intent:// redirect karta hai (Android app deep link).
    Requests ye handle nahi kar sakta — manually redirect follow karo aur
    intent:// mile toh browser_fallback_url use karo.
    """
    import urllib.parse

    current = url
    for _ in range(10):
        try:
            resp = _requests.get(current, headers=headers, timeout=30, allow_redirects=False)
        except Exception as e:
            err = str(e)
            # requests ne intent:// follow karne ki koshish ki aur InvalidSchema diya
            fb = _re.search(r'browser_fallback_url=([^;&\s"\']+)', err)
            if fb:
                current = urllib.parse.unquote(fb.group(1))
                continue
            log(f"  [fetch] Error: {e}")
            return None

        if resp.status_code == 200:
            return resp.text

        if resp.status_code not in (301, 302, 303, 307, 308):
            log(f"  [fetch] HTTP {resp.status_code}")
            return None

        loc = resp.headers.get("Location", "")
        if not loc:
            return None

        if loc.startswith("intent://"):
            fb = _re.search(r'browser_fallback_url=([^;&\s"\']+)', loc)
            if not fb:
                log("  [fetch] intent:// redirect, no fallback URL.")
                return None
            import urllib.parse as _up
            loc = _up.unquote(fb.group(1))

        elif not loc.startswith("http"):
            base = _re.match(r"https?://[^/]+", current)
            loc = (base.group(0) if base else "https://mbasic.facebook.com") + loc

        if loc == current:
            return None
        current = loc

    return None


def _mbasic_scrape_videos(start_url, cookie_str, max_pages=10):
    """
    mbasic.facebook.com plain-HTML se paginated video ID scraping.
    Public profiles: cookies ke bina bhi kaam karta hai.
    Private profiles: cookies se kaam karta hai (agar follow kiya ho).
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
            "Gecko/20100101 Firefox/126.0"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookie_str:
        headers["Cookie"] = cookie_str

    all_ids = []
    url = start_url

    for page_num in range(1, max_pages + 1):
        html = _fb_fetch(url, headers)
        if not html:
            break

        if "login" in html[:2000].lower() and "password" in html[:2000].lower():
            log("  [mbasic] Login page mili — cookies invalid ya profile private hai.")
            break

        page_ids = []
        for pat in [
            r'href="/video/(\d+)(?:/|\?)',
            r'video_id=(\d+)',
            r'/videos/(\d{10,})(?:/|\?)',
            r'"videoID":"(\d{10,})"',
            r'"video_id":"(\d{10,})"',
            r'story_fbid=(\d{10,})',
        ]:
            for vid in _re.findall(pat, html):
                if vid not in all_ids and vid not in page_ids:
                    page_ids.append(vid)

        all_ids.extend(page_ids)
        log(f"  [mbasic] Page {page_num}: {len(page_ids)} videos (total: {len(all_ids)})")

        if not page_ids:
            break

        next_match = _re.search(
            r'href="(/[^"]*(?:videos|end_cursor|start_index|timeline_cursor)[^"]*)"',
            html, _re.IGNORECASE,
        )
        if not next_match:
            break
        next_path = next_match.group(1)
        next_url = "https://mbasic.facebook.com" + next_path
        if next_url == url:
            break
        url = next_url

    return all_ids


def _ytdlp_fetch_urls(url, cookie_args):
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist", "-j", "--no-warnings", "--ignore-errors",
        *cookie_args, url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    urls = []
    for line in r.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            u = data.get("webpage_url") or data.get("url")
            if u:
                urls.append(u)
        except json.JSONDecodeError:
            pass
    return urls


def _extract_video_ids(html):
    """HTML se Facebook video/reel IDs extract karo (unique, ordered)."""
    seen = {}
    for pat in [
        r'/reel/(\d{8,})',           # reels tab ka main pattern
        r'"video_id"\s*:\s*"(\d{8,})"',
        r'"videoID"\s*:\s*"(\d{8,})"',
        r'story_fbid=(\d{8,})',
        r'/videos/(\d{10,})',
        r'href="/video/(\d{8,})',
    ]:
        for vid in _re.findall(pat, html):
            if vid not in seen:
                seen[vid] = len(seen)
    return list(seen.keys())


def _fb_headers(cookie_str=""):
    h = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) "
            "Gecko/20100101 Firefox/126.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    if cookie_str:
        h["Cookie"] = cookie_str
    return h


def _fetch_all_fb_reels(raw_url, cookie_str, cookie_args):
    id_match = _re.search(r'[?&]id=(\d+)', raw_url)
    numeric_id = id_match.group(1) if id_match else None

    # ── Strategy 1: facebook.com reels tab direct scrape ──────
    print("  Strategy 1: facebook.com/reels_tab HTML scraping...")
    if numeric_id:
        reels_url = f"https://www.facebook.com/profile.php?id={numeric_id}&sk=reels_tab"
    else:
        base = _re.sub(r'[?#].*', '', raw_url).rstrip('/')
        reels_url = base + "?sk=reels_tab"

    html = _fb_fetch(reels_url, _fb_headers(cookie_str))
    if html:
        log(f"  [debug] Page size: {len(html)} bytes")
        ids = _extract_video_ids(html)
        log(f"  [debug] IDs found: {len(ids)}")
        if ids:
            print(f"  {len(ids)} reels mili!")
            return [f"https://www.facebook.com/reel/{vid}/" for vid in ids]

    # ── Strategy 2: mbasic videos tab ─────────────────────────
    print("  Strategy 2: mbasic.facebook.com videos tab...")
    mbasic_url = _fb_to_mbasic_url(raw_url)
    if mbasic_url:
        ids = _mbasic_scrape_videos(mbasic_url, cookie_str)
        if ids:
            return [f"https://www.facebook.com/video/{vid}/" for vid in ids]

    # ── Strategy 3: yt-dlp flat-playlist ──────────────────────
    print("  Strategy 3: yt-dlp playlist try kar raha hai...")
    candidates = []
    if numeric_id:
        candidates += [
            f"https://www.facebook.com/profile.php?id={numeric_id}&sk=videos",
            f"https://www.facebook.com/profile.php?id={numeric_id}",
        ]
    candidates.append(raw_url)

    for candidate in candidates:
        urls = _ytdlp_fetch_urls(candidate, cookie_args)
        if urls:
            return urls

    return []


def handle_facebook_reels(yt, platforms):
    profile_url = input(
        "\n  Facebook profile/page URL daalo:\n"
        "  (e.g. https://www.facebook.com/username\n"
        "   ya  https://www.facebook.com/profile.php?id=xxx): "
    ).strip()
    if not profile_url:
        print("  URL nahi diya.")
        return

    fb_folder = os.path.join(DOWNLOADS_DIR, "fb_reels")
    os.makedirs(fb_folder, exist_ok=True)

    cookie_str, cookie_args = _fb_load_cookies()
    if cookie_str:
        print("  [Auth] get_tokens.txt mili — cookies use ho rahi hain.")
    else:
        print("  [Auth] get_tokens.txt nahi mili — public profile try karega.")

    urls = _fetch_all_fb_reels(profile_url, cookie_str, cookie_args)

    if not urls:
        print("\n  Koi reel nahi mili.")
        print("  Agar private profile hai toh pehle manually follow karo,")
        print("  phir fresh cookies get_tokens.txt mein daalo.")
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

    video_desc = input("  Video topic/description (metadata ke liye, blank=skip): ").strip()

    print(f"\n  {total} reels download ho rahi hain (workers={MAX_WORKERS}) → {fb_folder}\n")

    def _dl_one(args):
        i, reel_url = args
        out_tmpl = os.path.join(fb_folder, f"fb_reel_{i:03d}.%(ext)s")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", out_tmpl, "--no-playlist", "--no-warnings",
            *cookie_args, reel_url,
        ]
        log(f"  [{i}/{total}] Downloading...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log(f"  [{i}/{total}] FAIL")
            return False
        log(f"  [{i}/{total}] Done!")
        return True

    done_count = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_dl_one, t): t for t in enumerate(selected_urls, 1)}
        for f in concurrent.futures.as_completed(futs):
            if f.result():
                done_count += 1

    downloaded = sorted(
        [os.path.join(fb_folder, f) for f in os.listdir(fb_folder)
         if f.lower().endswith(".mp4")],
        key=os.path.getmtime,
    )

    print(f"\n  {done_count}/{total} reels download hui.\n")

    if not downloaded:
        print("  Koi file download nahi hui.")
        return

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
