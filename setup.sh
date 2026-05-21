#!/data/data/com.termux/files/usr/bin/bash
# BulkShortsUploader — Termux Setup
# Run: bash setup.sh

set -e

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   BulkShortsUploader — Termux Setup  ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ─── Detect environment ───────────────────────────────────────
if [ -d "/data/data/com.termux" ]; then
    ENV="termux"
elif command -v apt &>/dev/null; then
    ENV="proot"
else
    ENV="unknown"
fi

echo "Environment detected: $ENV"
echo ""

# ─── Termux (native) ──────────────────────────────────────────
if [ "$ENV" = "termux" ]; then
    echo "[1/3] System packages install ho rahi hain..."
    pkg update -y
    pkg install -y python ffmpeg

    echo ""
    echo "[2/3] cryptography pkg se install ho rahi hai (compile se bachne ke liye)..."
    # cryptography ko pkg se install karo — pip se install karo toh
    # Rust compiler ki zaroorat padti hai aur ghanton lag jaate hain
    pkg install -y python-cryptography

    echo ""
    echo "[3/3] Python packages install ho rahi hain..."
    pip install --upgrade pip --quiet
    # --no-build-isolation: already installed cryptography use karo
    pip install \
        yt-dlp \
        google-api-python-client \
        google-auth \
        google-auth-oauthlib \
        google-auth-httplib2 \
        requests \
        openai \
        --no-build-isolation \
        --quiet

# ─── proot-distro (Ubuntu/Debian inside Termux) ───────────────
elif [ "$ENV" = "proot" ]; then
    echo "[1/3] System packages install ho rahi hain..."
    apt update -y -q
    apt install -y -q python3 python3-pip ffmpeg python3-cryptography

    echo ""
    echo "[2/3] pip upgrade..."
    pip3 install --upgrade pip --quiet

    echo ""
    echo "[3/3] Python packages install ho rahi hain..."
    pip3 install \
        yt-dlp \
        google-api-python-client \
        google-auth \
        google-auth-oauthlib \
        google-auth-httplib2 \
        requests \
        openai \
        --no-build-isolation \
        --quiet

else
    echo "Unknown environment. Manually install:"
    echo "  ffmpeg, python, then: pip install -r requirements.txt"
    exit 1
fi

# ─── Done ─────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║         Setup complete!              ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. config.py mein apni API keys daalo"
echo "  2. client_secret.json is folder mein rakho"
echo "  3. python main.py"
echo ""
