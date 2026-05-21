import os
import json
import time
import random
import requests
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from config import (
    OPENAI_API_KEY, OPENAI_MODEL, CHANNEL_TOPIC,
    ENABLE_YOUTUBE, YOUTUBE_PRIVACY, YOUTUBE_CATEGORY_ID, YOUTUBE_DAILY_LIMIT,
    ENABLE_INSTAGRAM, INSTA_APP_ID, INSTA_APP_SECRET,
    INSTA_ACCESS_TOKEN, INSTA_USER_ID, INSTAGRAM_DAILY_LIMIT,
    ENABLE_FACEBOOK, FB_ACCESS_TOKEN, FB_PAGE_ID, FACEBOOK_DAILY_LIMIT,
)

SCOPES        = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE    = "token.json"
SECRET_FILE   = "client_secret.json"
QUOTA_FILE    = "quota_tracker.json"
HISTORY_FILE  = "upload_history.json"
INSTA_TOKEN_FILE = "insta_token.json"

GRAPH_URL        = "https://graph.facebook.com/v19.0"
GRAPH_IG_URL     = "https://graph.instagram.com"
GRAPH_IG_API_URL = "https://graph.instagram.com/v21.0"

PLATFORM_LIMITS = {
    "youtube":   YOUTUBE_DAILY_LIMIT,
    "instagram": INSTAGRAM_DAILY_LIMIT,
    "facebook":  FACEBOOK_DAILY_LIMIT,
}

_insta_user_id_cache = None


# ─── Quota ───────────────────────────────────────────────────

def load_quota():
    today = str(date.today())
    if os.path.exists(QUOTA_FILE):
        with open(QUOTA_FILE) as f:
            data = json.load(f)
        if data.get("date") == today:
            return data
    return {"date": today, "youtube": 0, "instagram": 0, "facebook": 0}


def save_quota(data):
    with open(QUOTA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def platform_remaining(platform):
    q = load_quota()
    return PLATFORM_LIMITS.get(platform, 0) - q.get(platform, 0)


def increment_quota(platform):
    q = load_quota()
    q[platform] = q.get(platform, 0) + 1
    save_quota(q)


def print_quota_status():
    q = load_quota()
    parts = []
    if ENABLE_YOUTUBE:
        parts.append(f"YT: {q.get('youtube',0)}/{YOUTUBE_DAILY_LIMIT}")
    if ENABLE_INSTAGRAM:
        parts.append(f"IG: {q.get('instagram',0)}/{INSTAGRAM_DAILY_LIMIT}")
    if ENABLE_FACEBOOK:
        parts.append(f"FB: {q.get('facebook',0)}/{FACEBOOK_DAILY_LIMIT}")
    print(f"  [Quota] {' | '.join(parts)}")


# ─── History ─────────────────────────────────────────────────

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}
    with open(HISTORY_FILE) as f:
        return json.load(f)


def save_history(h):
    with open(HISTORY_FILE, "w") as f:
        json.dump(h, f, indent=2)


def mark_uploaded(clip_name, platform):
    h = load_history()
    if clip_name not in h:
        h[clip_name] = []
    if platform not in h[clip_name]:
        h[clip_name].append(platform)
    save_history(h)


def already_uploaded(clip_name, platform="youtube"):
    return platform in load_history().get(clip_name, [])


# ─── OpenAI Metadata ─────────────────────────────────────────

def generate_metadata(clip_name):
    if not OPENAI_API_KEY:
        title = clip_name.replace("_", " ").replace(".mp4", "")[:70]
        return {
            "title":       title,
            "description": f"{title}\n\n#Shorts",
            "caption":     title,
            "tags":        ["shorts", "viral", "bushcraft"],
        }

    from openai import OpenAI

    angles = [
        "focus on a unique DIY hack or trick",
        "highlight a before-and-after transformation",
        "emphasize budget-friendly or cheap materials",
        "show a surprising or unexpected feature",
        "focus on comfort and cozy living",
        "highlight minimalist or off-grid lifestyle",
        "focus on step-by-step build progress",
        "show a time-lapse style quick overview",
    ]

    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"""Viral short-form video strategist.
Channel: {CHANNEL_TOPIC}
Clip: {clip_name}
Creative angle: {random.choice(angles)}
Seed: {random.randint(1000, 9999)}

Return ONLY valid JSON (no markdown):
- title: unique catchy title max 70 chars, no emojis
- description: 2-3 lines + #Shorts + 3-4 hashtags (for YouTube)
- caption: same but for Instagram (hashtags at end, no #Shorts)
- tags: list of 10 relevant strings"""

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=1.1,
        max_tokens=350,
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])
    return json.loads(raw)


# ─── Instagram Token Manager ─────────────────────────────────

def _load_insta_token_meta():
    if os.path.exists(INSTA_TOKEN_FILE):
        with open(INSTA_TOKEN_FILE) as f:
            return json.load(f)
    return {}


def _save_insta_token_meta(token, expires_in_seconds):
    with open(INSTA_TOKEN_FILE, "w") as f:
        json.dump({"token": token, "expires_at": time.time() + expires_in_seconds}, f, indent=2)


def _patch_config_token(new_token):
    import re
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
    with open(config_path, "r") as f:
        content = f.read()
    content = re.sub(r'(INSTA_ACCESS_TOKEN\s*=\s*)"[^"]*"', f'\\1"{new_token}"', content)
    with open(config_path, "w") as f:
        f.write(content)


def get_valid_insta_token():
    token = INSTA_ACCESS_TOKEN
    meta  = _load_insta_token_meta()

    stored_token = meta.get("token")
    expires_at   = meta.get("expires_at", 0)
    days_left    = (expires_at - time.time()) / 86400

    if stored_token and days_left > 7:
        return stored_token

    active_token = stored_token if stored_token else token

    if stored_token and 0 < days_left <= 7:
        print(f"  [Token] Instagram token {days_left:.0f} din mein expire hoga — refresh kar raha hun...")
        resp = requests.get(
            f"{GRAPH_IG_URL}/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": active_token},
        ).json()
        if "access_token" in resp:
            new_token = resp["access_token"]
            _save_insta_token_meta(new_token, resp.get("expires_in", 5184000))
            _patch_config_token(new_token)
            print(f"  [Token] Refreshed! {resp.get('expires_in', 5184000)//86400} din valid.")
            return new_token

    if not stored_token:
        check = requests.get(f"{GRAPH_IG_API_URL}/me", params={"access_token": active_token}).json()
        if "id" in check:
            _save_insta_token_meta(active_token, 5184000)
            return active_token

        resp = requests.get(
            f"{GRAPH_URL}/access_token",
            params={"grant_type": "ig_exchange_token", "client_secret": INSTA_APP_SECRET,
                    "access_token": active_token},
        ).json()
        if "access_token" in resp:
            new_token = resp["access_token"]
            _save_insta_token_meta(new_token, resp.get("expires_in", 5184000))
            _patch_config_token(new_token)
            return new_token

    return active_token


# ─── YouTube Auth ─────────────────────────────────────────────

def get_youtube_client():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(SECRET_FILE):
                print(f"\n  ERROR: {SECRET_FILE} nahi mila!")
                print("  Google Cloud Console se OAuth credentials download karo.")
                raise SystemExit(1)

            flow = InstalledAppFlow.from_client_secrets_file(SECRET_FILE, SCOPES)
            print("\n  ┌─────────────────────────────────────────────┐")
            print("  │  YouTube Login                               │")
            print("  │  Neeche URL copy karo → Chrome mein kholo   │")
            print("  │  Google account se Allow karo               │")
            print("  └─────────────────────────────────────────────┘")
            creds = flow.run_local_server(
                port=8080,
                prompt="consent",
                access_type="offline",
                open_browser=False,
            )

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


# ─── YouTube Upload ───────────────────────────────────────────

def _upload_youtube(clip_path, meta, youtube):
    body = {
        "snippet": {
            "title":       meta["title"],
            "description": meta["description"],
            "tags":        meta["tags"],
            "categoryId":  YOUTUBE_CATEGORY_ID,
        },
        "status": {
            "privacyStatus":           YOUTUBE_PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }
    media   = MediaFileUpload(clip_path, mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    print(f"  [YT] Uploading...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  [YT] {int(status.progress() * 100)}%...", end="\r")

    vid_id = response["id"]
    print(f"  [YT] Done! → https://youtube.com/shorts/{vid_id}    ")
    return vid_id


# ─── Instagram Upload ─────────────────────────────────────────

def _get_insta_user_id(token):
    global _insta_user_id_cache
    if INSTA_USER_ID:
        return INSTA_USER_ID
    if _insta_user_id_cache:
        return _insta_user_id_cache
    resp = requests.get(f"{GRAPH_IG_API_URL}/me", params={"access_token": token}).json()
    if "id" not in resp:
        raise RuntimeError(f"Instagram user ID fetch failed: {resp}")
    _insta_user_id_cache = resp["id"]
    return _insta_user_id_cache


def _upload_to_temp_host(clip_path):
    print(f"  [IG] Temp host pe upload ho raha hai...")
    with open(clip_path, "rb") as f:
        resp = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f}, timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"Temp host failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    if data.get("status") != "success":
        raise RuntimeError(f"Temp host error: {data}")
    return data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")


def _upload_instagram(clip_path, meta, token):
    user_id   = _get_insta_user_id(token)
    video_url = _upload_to_temp_host(clip_path)

    resp = requests.post(
        f"{GRAPH_IG_API_URL}/{user_id}/media",
        data={"media_type": "REELS", "video_url": video_url,
              "caption": meta.get("caption", meta["title"]), "access_token": token},
    ).json()
    if "id" not in resp:
        raise RuntimeError(f"Instagram container failed: {resp}")

    creation_id = resp["id"]
    for _ in range(36):
        s = requests.get(
            f"{GRAPH_IG_API_URL}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
        ).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram processing error: {s}")
        print(f"  [IG] Processing...", end="\r")
        time.sleep(10)
    else:
        raise RuntimeError("Instagram processing timeout (6 min)")

    pub = requests.post(
        f"{GRAPH_IG_API_URL}/{user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
    ).json()
    if "id" not in pub:
        raise RuntimeError(f"Instagram publish failed: {pub}")

    print(f"  [IG] Done! → media_id={pub['id']}    ")
    return pub["id"]


# ─── Facebook Upload ──────────────────────────────────────────

def _upload_facebook(clip_path, meta, token, page_id):
    file_size = os.path.getsize(clip_path)

    start = requests.post(
        f"{GRAPH_URL}/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": token},
    ).json()
    if "video_id" not in start:
        raise RuntimeError(f"Facebook start failed: {start}")

    video_id   = start["video_id"]
    upload_url = start["upload_url"]

    with open(clip_path, "rb") as f:
        up = requests.post(
            upload_url,
            headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(file_size)},
            data=f,
        )
    if up.status_code not in (200, 201):
        raise RuntimeError(f"Facebook upload failed: {up.text}")

    finish = requests.post(
        f"{GRAPH_URL}/{page_id}/video_reels",
        data={"video_id": video_id, "upload_phase": "finish", "video_state": "PUBLISHED",
              "title": meta["title"], "description": meta.get("caption", ""), "access_token": token},
    ).json()
    if not finish.get("success"):
        raise RuntimeError(f"Facebook publish failed: {finish}")

    print(f"  [FB] Done! → video_id={video_id}")
    return video_id


# ─── Multi-Platform Upload ────────────────────────────────────

def upload_clip(clip_path, youtube=None, platforms=None):
    """
    platforms: list jisme "youtube", "instagram", "facebook" ho sakte hain.
    None doge toh config ke ENABLE_* flags se decide hoga.
    """
    clip_name = os.path.basename(clip_path)

    if platforms is None:
        platforms = []
        if ENABLE_YOUTUBE:
            platforms.append("youtube")
        if ENABLE_INSTAGRAM:
            platforms.append("instagram")
        if ENABLE_FACEBOOK:
            platforms.append("facebook")

    print(f"\n  [Meta] Metadata generate ho raha hai...")
    try:
        meta = generate_metadata(clip_name)
        print(f"  [Title] {meta['title']}")
    except Exception as e:
        print(f"  [Meta] Failed ({e}) — default title use ho raha hai")
        title = clip_name.replace("_", " ").replace(".mp4", "")[:70]
        meta  = {"title": title, "description": "#Shorts", "caption": title, "tags": ["shorts"]}

    insta_token = get_valid_insta_token() if "instagram" in platforms else None

    jobs = {}

    if "youtube" in platforms and youtube:
        if already_uploaded(clip_name, "youtube"):
            print(f"  [YT] Skip — pehle se uploaded.")
        elif platform_remaining("youtube") <= 0:
            print(f"  [YT] Skip — daily limit khatam.")
        else:
            jobs["youtube"] = lambda: _upload_youtube(clip_path, meta, youtube)

    if "instagram" in platforms and insta_token:
        if already_uploaded(clip_name, "instagram"):
            print(f"  [IG] Skip — pehle se uploaded.")
        elif platform_remaining("instagram") <= 0:
            print(f"  [IG] Skip — daily limit khatam.")
        else:
            jobs["instagram"] = lambda: _upload_instagram(clip_path, meta, insta_token)

    if "facebook" in platforms and FB_ACCESS_TOKEN and FB_PAGE_ID:
        if already_uploaded(clip_name, "facebook"):
            print(f"  [FB] Skip — pehle se uploaded.")
        elif platform_remaining("facebook") <= 0:
            print(f"  [FB] Skip — daily limit khatam.")
        else:
            jobs["facebook"] = lambda: _upload_facebook(clip_path, meta, FB_ACCESS_TOKEN, FB_PAGE_ID)

    if not jobs:
        print(f"  [Skip] Koi platform nahi bacha upload ke liye.")
        return

    results = {}
    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futures = {ex.submit(fn): name for name, fn in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
                results[name] = "ok"
                increment_quota(name)
                mark_uploaded(clip_name, name)
            except Exception as e:
                results[name] = f"ERROR"
                print(f"  [{name.upper()}] FAILED: {e}")

    all_ok = all(v == "ok" for v in results.values())
    if all_ok and os.path.exists(clip_path):
        os.remove(clip_path)
        print(f"  [Clean] {clip_name} delete ho gaya.")
    elif not all_ok:
        print(f"  [Keep] {clip_name} rakha — kuch platforms fail hue (retry possible).")

    print_quota_status()
