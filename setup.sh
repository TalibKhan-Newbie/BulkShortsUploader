#!/data/data/com.termux/files/usr/bin/bash
# ShortUploader — Termux Setup
# Run: bash setup.sh

echo ""
echo "=== ShortUploader Termux Setup ==="
echo ""

# System packages
pkg update -y
pkg install -y python ffmpeg

# Python packages
pip install --upgrade pip
pip install yt-dlp google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2 requests openai

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Run karo: python main.py"
echo ""
echo "Pehle client_secret.json copy karo is folder mein:"
echo "  (Google Cloud Console → OAuth 2.0 Client → Download JSON)"
echo ""
