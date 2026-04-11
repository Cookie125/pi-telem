# pi-telem

MAVLink telemetry HUD for Raspberry Pi Zero 2 W. Reads telemetry from an RFD900 radio (via FTDI/serial) or from an ArduPilot SITL instance over the network, and renders a Yaapu-style heads-up display with an artificial horizon to an HDMI screen using pygame.

## Features

- Artificial horizon with pitch ladder and roll indicator
- Scrolling IAS (indicated airspeed) tape
- Dual scrolling altitude tapes — relative (AGL) and MSL, switchable between metres and feet
- Compass heading ribbon with home bearing marker
- G1000-style wind direction arrow and speed readout
- Flight mode and arm status
- GPS fix type and satellite count
- Battery voltage, current, and remaining %
- Home distance and bearing
- Vertical speed readout
- STATUSTEXT message log
- Auto-start on boot via systemd

## Quick Start

```bash
git clone https://github.com/Cookie125/pi-telem.git && cd pi-telem
./install.sh

# Run against a SITL instance
.venv/bin/python main.py --connection udpin:0.0.0.0:14550 --windowed

# Run against RFD900 hardware
.venv/bin/python main.py --connection /dev/ttyUSB0 --baud 115200
```

## Connection Strings

The `--connection` flag accepts any `pymavlink` connection string:

| String | Use |
|---|---|
| `/dev/ttyUSB0` | Serial (RFD900 via FTDI) |
| `udpin:0.0.0.0:14550` | UDP listen (SITL default output) |
| `udpout:192.168.1.100:14550` | UDP connect to remote |
| `tcp:192.168.1.100:5762` | TCP connect to SITL |

## CLI Options

```
-c, --connection   MAVLink connection string (default: /dev/ttyUSB0)
-b, --baud         Serial baud rate (default: 115200)
-r, --resolution   Display resolution WxH (default: 800x480)
    --fps          Target frame rate (default: 10)
    --alt-unit     Altitude display unit: m or ft (default: m)
    --windowed     Run in a window instead of fullscreen
```

## Testing with SITL

Spin up an ArduPilot SITL instance and point it at the HUD:

```bash
# Terminal 1 — start SITL (ArduCopter example)
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550

# Terminal 2 — start the HUD
python main.py --connection udpin:127.0.0.1:14550 --windowed
```

SITL on another machine:

```bash
# On the SITL machine
sim_vehicle.py -v ArduCopter --out=udp:<PI_IP>:14550

# On the Pi
python main.py --connection udpin:0.0.0.0:14550
```

If pymavlink is installed in a virtualenv (e.g. the ArduPilot dev env):

```bash
~/venv-ardupilot/bin/python main.py --connection udpin:127.0.0.1:14550 --windowed
```

## Running as a Service

After `install.sh`, the systemd service is installed but not started:

```bash
sudo systemctl start pitelem      # start now
sudo systemctl status pitelem     # check status
journalctl -u pitelem -f          # tail logs
```

Edit the connection string in the service:

```bash
sudo systemctl edit pitelem
# Add under [Service]:
# ExecStart=
# ExecStart=/path/to/.venv/bin/python /path/to/main.py --connection udpin:0.0.0.0:14550
```

## Hardware Setup

- **Pi Zero 2 W** running Raspberry Pi OS Lite (no desktop needed)
- **RFD900** radio modem connected via **FTDI USB-to-serial** adapter
- Any **HDMI display** (mini-HDMI adapter required for the Pi Zero 2 W)

## Dependencies

- Python 3
- pygame (SDL2)
- pymavlink
- System: `libsdl2-dev`, `libsdl2-image-dev`, `libsdl2-ttf-dev`, `fonts-dejavu-core`

All installed automatically by `install.sh`.
