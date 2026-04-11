#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="pitelem"
VENV_DIR="$SCRIPT_DIR/.venv"
USER="$(whoami)"

echo "=== Pi Telemetry HUD installer ==="

# ---- system deps ----
echo "[1/5] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev \
    libsdl2-dev libsdl2-image-dev libsdl2-ttf-dev libsdl2-mixer-dev \
    fonts-dejavu-core

# ---- serial access ----
echo "[2/5] Adding $USER to dialout group..."
sudo usermod -aG dialout "$USER" 2>/dev/null || true

# ---- python venv ----
echo "[3/5] Creating Python venv and installing packages..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q

# ---- systemd service ----
echo "[4/5] Installing systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=MAVLink Telemetry HUD
After=multi-user.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment=SDL_VIDEODRIVER=kmsdrm
ExecStart=$VENV_DIR/bin/python $SCRIPT_DIR/main.py --connection /dev/ttyUSB0 --baud 115200
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service

echo "[5/5] Done."
echo ""
echo "The service is installed but NOT started."
echo ""
echo "  Edit the connection in the service file if needed:"
echo "    sudo systemctl edit ${SERVICE_NAME}"
echo ""
echo "  Start now:   sudo systemctl start ${SERVICE_NAME}"
echo "  View logs:   journalctl -u ${SERVICE_NAME} -f"
echo "  Run manually: $VENV_DIR/bin/python $SCRIPT_DIR/main.py --connection udpin:0.0.0.0:14550 --windowed"
echo ""
echo "You may need to log out and back in for the dialout group to take effect."
