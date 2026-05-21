# BulkShortsUploader

YouTube video se automatically shorts banao aur YouTube, Instagram, Facebook pe upload karo.

**Termux (Android) pe chal sakta hai.**

---

## Setup (Termux)

```bash
# 1. Repo clone karo
git clone https://github.com/TalibKhan-Newbie/BulkShortsUploader.git
cd BulkShortsUploader

# 2. Dependencies install karo
bash setup.sh

# 3. Config fill karo
nano config.py

# 4. Google OAuth credentials rakho
# client_secret.json → project folder mein copy karo
# (Google Cloud Console → APIs → YouTube Data API v3 → OAuth 2.0 Client)

# 5. Run karo
python main.py
```

---

## Config

`config.py` mein apni details fill karo:

| Variable | Kya hai |
|---|---|
| `OPENAI_API_KEY` | OpenAI key (blank = simple title use hoga) |
| `CHANNEL_TOPIC` | Tumhara channel kis cheez ke baare mein hai |
| `YOUTUBE_DAILY_LIMIT` | Roz kitni videos upload karni hain |
| `INSTA_APP_ID` / `INSTA_APP_SECRET` | Meta Developer Console se |
| `INSTA_ACCESS_TOKEN` | Instagram long-lived token |
| `FB_ACCESS_TOKEN` / `FB_PAGE_ID` | Facebook Page ke liye |
| `ENABLE_FACEBOOK` | `True` karo jab FB setup ho |
| `SPEED` | Video speed (1.5 = 50% fast) |
| `MUTE_AUDIO` | `True` = audio off |

---

## Google OAuth Setup

1. [Google Cloud Console](https://console.cloud.google.com) pe jao
2. New project banao → **YouTube Data API v3** enable karo
3. **OAuth 2.0 Client ID** banao (Desktop app type)
4. JSON download karo → `client_secret.json` naam se project folder mein rakho
5. `python main.py` chalao → URL print hoga → phone ke Chrome mein kholo → allow karo

---

## Menu

```
╔══════════════════════════════════════╗
║   ShortUploader  —  Termux Edition   ║
╚══════════════════════════════════════╝
[Quota] YT: 0/6 | IG: 0/50

  1. URL se download → shorts → upload
  2. Saved clips upload karo
  3. Exit
```

**Flow:**
1. YouTube URL dalo
2. Video download hogi (yt-dlp)
3. Kitni clips? puchega
4. FFmpeg se 9:16 vertical shorts banega
5. YouTube + Instagram + Facebook pe simultaneously upload

---

## Requirements

- Python 3.9+
- FFmpeg (`pkg install ffmpeg` on Termux)
- `client_secret.json` (Google OAuth)

---

## Files jo commit nahi hoti (gitignored)

```
token.json          # YouTube OAuth token (auto-banta hai)
client_secret.json  # Google credentials (khud daalo)
insta_token.json    # Instagram token cache
quota_tracker.json  # Daily upload count
upload_history.json # Kya upload ho chuka
clips/              # Generated shorts
downloads/          # Downloaded videos
```
