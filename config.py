# ─── Folders ─────────────────────────────────────────────────
CLIPS_DIR     = "clips"
DOWNLOADS_DIR = "downloads"

# ─── Clip Settings ───────────────────────────────────────────
CHUNK_DURATION     = 30    # max clips calculate karne ke liye
CHUNK_DURATION_MIN = 15    # minimum clip duration (seconds)
CHUNK_DURATION_MAX = 30    # maximum clip duration (seconds)

# ─── Speed ───────────────────────────────────────────────────
SPEED      = 1.5           # 1.0 = normal, 1.5 = 50% faster
MUTE_AUDIO = False         # True = audio mute kar do

# ─── Output Resolution (vertical 9:16) ───────────────────────
TARGET_W = 1080
TARGET_H = 1920

# ─── Encoding (libx264 — CPU, Termux compatible) ─────────────
CRF         = 28           # quality: lower = better (18-35)
FPS         = 30
MAX_WORKERS = 2            # mobile CPU ke liye 2 kaafi hai

# ─── OpenAI (optional) ───────────────────────────────────────
# Blank chhodo toh clip name se simple title banega
OPENAI_API_KEY = ""        # apna OpenAI key yahan daalo
OPENAI_MODEL   = "gpt-4o-mini"
CHANNEL_TOPIC  = "Survival & Bushcraft"

# ─── YouTube ─────────────────────────────────────────────────
ENABLE_YOUTUBE       = True
YOUTUBE_DAILY_LIMIT  = 6   # unverified account ~6/day
YOUTUBE_PRIVACY      = "public"
YOUTUBE_CATEGORY_ID  = "19"   # Travel & Events

# ─── Instagram ───────────────────────────────────────────────
ENABLE_INSTAGRAM      = True
INSTA_APP_ID          = ""     # Meta Developer Console se lo
INSTA_APP_SECRET      = ""     # Meta Developer Console se lo
INSTA_ACCESS_TOKEN    = ""     # Instagram long-lived access token
INSTA_USER_ID         = ""     # blank rakhoge toh auto-fetch hoga
INSTAGRAM_DAILY_LIMIT = 50

# ─── Facebook ────────────────────────────────────────────────
ENABLE_FACEBOOK      = False   # True karo jab FB Page token ho
FB_ACCESS_TOKEN      = ""      # Facebook Page access token
FB_PAGE_ID           = ""      # Facebook Page ID
FACEBOOK_DAILY_LIMIT = 50

# ─── General ─────────────────────────────────────────────────
UPLOAD_DELAY = 10  # seconds between each upload
