#!/data/data/com.termux/files/usr/bin/bash
# BulkShortsUploader — Termux Setup
# Run: bash setup.sh

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   BulkShortsUploader — Termux Setup  ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ─── Helpers ──────────────────────────────────────────────────
ok()   { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; }
info() { echo "  → $1"; }

pip_install() {
    # pehle normal try karo, fail ho toh --no-build-isolation
    pip install "$@" --quiet 2>/dev/null \
        || pip install "$@" --no-build-isolation --quiet 2>/dev/null \
        || pip install "$@" --no-build-isolation
}

pip3_install() {
    pip3 install "$@" --quiet 2>/dev/null \
        || pip3 install "$@" --no-build-isolation --quiet 2>/dev/null \
        || pip3 install "$@" --no-build-isolation
}

# ─── Detect environment ───────────────────────────────────────
if [ -d "/data/data/com.termux" ]; then
    ENV="termux"
elif command -v apt &>/dev/null; then
    ENV="proot"
else
    ENV="unknown"
fi

echo "  Environment: $ENV"
echo ""

# ══════════════════════════════════════════════════════════════
# TERMUX (native)
# ══════════════════════════════════════════════════════════════
if [ "$ENV" = "termux" ]; then

    echo "[1/3] System packages..."
    pkg update -y -q && pkg install -y python ffmpeg
    ok "python + ffmpeg"

    echo ""
    echo "[2/3] cryptography (pkg se — Rust compile se bachne ke liye)..."
    # pip se install karo toh Rust compiler chahiye — ghanton hang ho jaata hai
    # pkg wala pre-built binary hai — seconds mein install
    pkg install -y python-cryptography
    ok "python-cryptography"

    echo ""
    echo "[3/3] Python packages..."
    pip install --upgrade pip --quiet
    pip_install \
        yt-dlp \
        google-api-python-client \
        google-auth \
        google-auth-oauthlib \
        google-auth-httplib2 \
        requests \
        openai

    # ─── Verify ───────────────────────────────────────────────
    echo ""
    echo "  Verifying..."
    PYTHON_BIN="python"

    verify() {
        if $PYTHON_BIN -c "import $1" 2>/dev/null; then
            ok "$1"
        else
            fail "$1 — fix: $2"
            FAILED=1
        fi
    }

    FAILED=0
    verify "googleapiclient"  "pip install google-api-python-client --no-build-isolation"
    verify "google.auth"      "pip install google-auth --no-build-isolation"
    verify "yt_dlp"           "pip install yt-dlp"
    verify "requests"         "pip install requests"

    if [ "$FAILED" = "1" ]; then
        echo ""
        echo "  Kuch packages fail hue. Neeche troubleshoot section dekho."
        echo "  Ya yeh run karo:"
        echo ""
        echo "    python -m pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 yt-dlp requests openai --no-build-isolation"
        echo ""
    fi

# ══════════════════════════════════════════════════════════════
# proot-distro (Ubuntu/Debian inside Termux)
# ══════════════════════════════════════════════════════════════
elif [ "$ENV" = "proot" ]; then

    echo "[1/3] System packages..."
    apt update -y -q
    apt install -y -q python3 python3-pip ffmpeg python3-cryptography
    ok "python3 + ffmpeg + python3-cryptography"

    echo ""
    echo "[2/3] pip upgrade..."
    pip3 install --upgrade pip --quiet
    ok "pip upgraded"

    echo ""
    echo "[3/3] Python packages..."
    pip3_install \
        yt-dlp \
        google-api-python-client \
        google-auth \
        google-auth-oauthlib \
        google-auth-httplib2 \
        requests \
        openai

    # ─── Verify ───────────────────────────────────────────────
    echo ""
    echo "  Verifying..."
    PYTHON_BIN="python3"

    verify() {
        if $PYTHON_BIN -c "import $1" 2>/dev/null; then
            ok "$1"
        else
            fail "$1 — fix: $2"
            FAILED=1
        fi
    }

    FAILED=0
    verify "googleapiclient"  "pip3 install google-api-python-client --no-build-isolation"
    verify "google.auth"      "pip3 install google-auth --no-build-isolation"
    verify "yt_dlp"           "pip3 install yt-dlp"
    verify "requests"         "pip3 install requests"

    if [ "$FAILED" = "1" ]; then
        echo ""
        echo "  Kuch packages fail hue. Yeh run karo:"
        echo ""
        echo "    python3 -m pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 yt-dlp requests openai --no-build-isolation"
        echo ""
    fi

else
    echo "Unknown environment."
    echo "Manually install: ffmpeg, python, then:"
    echo "  pip install -r requirements.txt --no-build-isolation"
    exit 1
fi

# ─── Final ────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║         Setup complete!              ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo "  1. config.py mein apni API keys daalo"
echo "  2. client_secret.json is folder mein rakho"
if [ "$ENV" = "proot" ]; then
    echo "  3. python3 main.py"
else
    echo "  3. python main.py"
fi
echo ""
