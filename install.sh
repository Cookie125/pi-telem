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
After=display-manager.service
Wants=display-manager.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/${USER}/.Xauthority
ExecStart=$VENV_DIR/bin/python $SCRIPT_DIR/main.py --baud 115200 --map --terrain
Restart=always
RestartSec=5
StartLimitIntervalSec=0

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service

echo "[5/5] Done."
echo ""
echo "The service is installed but NOT started."
echo ""
echo "  Configured for Raspberry Pi OS (desktop): DISPLAY=:0 + XAUTHORITY so pygame uses X11."
echo ""
echo "  Default MAVLink: UDP listen 0.0.0.0:14550, then /dev/ttyUSB0, ttyACM0, serial0."
echo "  Override connections if needed:"
echo "    sudo systemctl edit ${SERVICE_NAME}"
echo ""
echo "  Start now:   sudo systemctl start ${SERVICE_NAME}"
echo "  View logs:   journalctl -u ${SERVICE_NAME} -f"
echo "  Run manually (desktop / SITL uplink): $VENV_DIR/bin/python $SCRIPT_DIR/main.py --windowed -c udpin:127.0.0.1:14550 --tx"
echo ""
echo "  Default service flags: --map --terrain (receive-only MAVLink unless you add --tx)."
echo ""
echo "You may need to log out and back in for the dialout group to take effect."
