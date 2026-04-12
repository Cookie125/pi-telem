# pi-telem

MAVLink telemetry HUD for Raspberry Pi Zero 2 W. Reads telemetry from an RFD900 radio (via FTDI/serial) or from an ArduPilot SITL instance over the network, and renders a Yaapu-style heads-up display with an artificial horizon to an HDMI screen using pygame.

**Repository:** [github.com/Cookie125/pi-telem](https://github.com/Cookie125/pi-telem) (default branch: `main`)

## Features

- Artificial horizon with pitch ladder and roll indicator
- Optional **synthetic vision (SVS) terrain** on the horizon (`--terrain`) — layered terrain bands styled like MAVProxy’s `horizon_svs`, using SRTM/Copernicus elevation data
- Scrolling **IAS** (indicated airspeed) tape and dual **REL / MSL** altitude tapes (narrow columns tuned for **800×480** class panels); altitude readouts are **whole units** (no decimals); tape titles sit in a **label band** above each scrolling area
- Compass heading ribbon with home bearing marker
- **Wind**: direction arrow plus speed in the **top status bar** (to the left of GPS), same strip as mode / arm / waypoint
- **Vertical speed** in the **compass row** (right column, aligned with the alt tapes); **EFI RPM** on the **bottom bar** (right of messages)
- Flight mode, arm status, and current waypoint (when the FC sends `MISSION_CURRENT` / `NAV_CONTROLLER_OUTPUT`)
- GPS fix type and satellite count
- Battery voltage, current, remaining %, and optional second-pack “Fuel %” when present
- **HOME** distance and bearing in the left strip below the compass (compact **H …** label; scales down if the column is narrow)
- Optional **PIP map** (`--map`): satellite **Esri World Imagery** by default (or any XYZ tile URL), with **HOME**, **mission waypoints** (MAVLink mission download), dotted route (including segments that cross off the PIP), and ownship heading arrow; with **HOME** set, zoom/pan **auto-frames aircraft + HOME** (cap `--map-zoom`); tiles cache under `~/.cache/pi-telem/map_tiles/` per tile URL
- STATUSTEXT message log
- Auto-start on boot via systemd (`install.sh`)

## Quick Start

```bash
git clone https://github.com/Cookie125/pi-telem.git && cd pi-telem
git checkout main
./install.sh

# Run against a SITL instance (desktop / dev machine)
.venv/bin/python main.py --connection udpin:0.0.0.0:14550 --windowed

# Run against RFD900 hardware on the Pi
.venv/bin/python main.py --connection /dev/ttyUSB0 --baud 115200

# Optional: synthetic vision terrain (needs network once to download DEM tiles)
.venv/bin/python main.py --connection /dev/ttyUSB0 --terrain --terrain-db SRTM1

# Optional: PIP map (needs network once per area unless tiles already cached)
.venv/bin/python main.py --connection /dev/ttyUSB0 --map
```

## Updating an existing clone (e.g. on a Raspberry Pi)

If your local branch diverged from GitHub (for example after a history rewrite on `main`), reset to match the remote, then refresh dependencies:

```bash
cd ~/pi-telem
git fetch origin
git checkout main
git reset --hard origin/main
./.venv/bin/pip install -r requirements.txt --upgrade
```

Restart the service if you use it: `sudo systemctl restart pitelem`

## Connection Strings

The `--connection` flag accepts any `pymavlink` connection string:

| String | Use |
|--------|-----|
| `/dev/ttyUSB0` | Serial (RFD900 via FTDI) |
| `udpin:0.0.0.0:14550` | UDP listen (SITL default output) |
| `udpout:192.168.1.100:14550` | UDP connect to remote |
| `tcp:192.168.1.100:5762` | TCP connect to SITL |

## CLI Options

| Option | Description |
|--------|-------------|
| `-c`, `--connection` | MAVLink connection string (default: `/dev/ttyUSB0`) |
| `-b`, `--baud` | Serial baud rate, ignored for UDP/TCP (default: `115200`) |
| `--rx-only` | **Receive-only:** do not send MAVLink (no stream requests, `HOME_POSITION` pull, or mission download). For a **listen-only** UART (e.g. RFD TX → Pi RX with no Pi TX → RFD RX). HUD works from whatever the vehicle already broadcasts; map **waypoints/route** need mission data from another path or FC broadcast |
| `-r`, `--resolution` | Display size `WxH` (default: `800x480`) |
| `--fps` | Target render frame rate (default: `10`) |
| `--alt-unit` | Altitude tapes: `m` or `ft` (default: `m`) |
| `--windowed` | Windowed mode instead of fullscreen (useful on a dev PC) |
| `--terrain` | Enable SVS terrain on the artificial horizon |
| `--terrain-db` | Elevation source: `SRTM1`, `SRTM3`, or `COP30` (default: `SRTM1`) |
| `--map` | Enable bottom-left PIP map (tiles + HOME / waypoints / ownship) |
| `--map-zoom` | Tile zoom **0–19** (default: **14**). With `--map` and HOME set, auto-fit uses the **minimum** zoom needed to show aircraft + HOME, **capped** by this value |
| `--map-tile-url` | XYZ template with `{z}`, `{x}`, `{y}` (default: Esri World Imagery `{z}/{y}/{x}`). Example OSM: `https://tile.openstreetmap.org/{z}/{x}/{y}.png` |

Equivalent short help:

```
-c, --connection   MAVLink connection string
-b, --baud           Serial baud rate (default: 115200)
    --rx-only         Do not transmit MAVLink (listen-only link)
-r, --resolution     WxH (default: 800x480)
    --fps             Target frame rate (default: 10)
    --alt-unit        m or ft (default: m)
    --windowed        Run in a window instead of fullscreen
    --terrain         SVS terrain on the horizon
    --terrain-db      SRTM1, SRTM3, or COP30 (default: SRTM1)
    --map             PIP map (optional)
    --map-zoom        0–19 (default: 14)
    --map-tile-url    XYZ tile URL template
```

## Synthetic vision terrain (`--terrain`)

- Elevation comes from **ArduPilot terrain mirrors** (same family as MAVProxy): default **`SRTM1`** (~30 m posts), or `SRTM3` / **Copernicus GLO-30** (`COP30`).
- Tiles download on first use and cache under **`~/.cache/MAVProxy/terrain/`** — allow internet once, or pre-cache tiles for your flying area.
- Implementation uses vendored helpers in **`lib/`** (`mp_elevation`, `srtm`, etc.) and a background sampler thread; terrain is drawn as **stacked polygons** similar to MAVProxy `horizon_svs`.
- Requires **NumPy** (listed in `requirements.txt`).
- If terrain data is missing or SVS is off, the horizon still shows the **standard blue/brown artificial horizon** (pitch ladder and roll). Link loss is separate: telemetry drives the HUD whenever MAVLink is connected.

## PIP map (`--map`)

- **Default imagery** is **Esri World Imagery** (satellite). Override **`--map-tile-url`** for other XYZ providers; obey each provider’s terms.
- Tiles are cached on disk under **`~/.cache/pi-telem/map_tiles/<url-hash>/…`** so changing providers does not mix cached files.
- **Offline:** previously downloaded tiles still load; new areas need connectivity (or pre-cache by panning while online).
- The FC must allow **mission download** (same as any GCS) for waypoint positions; the HUD requests the mission periodically over MAVLink.
- Waypoint labels use **MAVLink mission sequence** (0-based), matching `MISSION_CURRENT.seq` and the status **WP:** line.
- **Auto-fit zoom** (when HOME is set) uses **aircraft + HOME only** — mission waypoints are drawn and routed, but they do **not** change the zoom level (so a distant WP does not shrink the map).

## Testing with SITL

Spin up an ArduPilot SITL instance and point it at the HUD:

```bash
# Terminal 1 — start SITL (ArduCopter example)
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550

# Terminal 2 — start the HUD (from the project venv)
cd ~/pi-telem
.venv/bin/python main.py --connection udpin:127.0.0.1:14550 --windowed --alt-unit ft

# With terrain (downloads DEM for current SITL location)
.venv/bin/python main.py --connection udpin:127.0.0.1:14550 --windowed --terrain

# With PIP map (downloads tiles for current area)
.venv/bin/python main.py --connection udpin:127.0.0.1:14550 --windowed --map
```

SITL on another machine:

```bash
# On the SITL machine
sim_vehicle.py -v ArduCopter --out=udp:<PI_IP>:14550

# On the Pi
.venv/bin/python main.py --connection udpin:0.0.0.0:14550
```

If you use another virtualenv for ArduPilot tools only:

```bash
~/venv-ardupilot/bin/python main.py --connection udpin:127.0.0.1:14550 --windowed
```

Install project dependencies in that env first (`pip install -r requirements.txt`), or always use **`.venv/bin/python`** from this repo.

## Running as a Service

After `install.sh`, the systemd service is installed but not started:

```bash
sudo systemctl start pitelem       # start now
sudo systemctl status pitelem      # check status
journalctl -u pitelem -f           # tail logs
```

Edit the connection string or add flags such as `--terrain` or `--map`:

```bash
sudo systemctl edit pitelem
```

Example override:

```ini
[Service]
ExecStart=
ExecStart=/home/pi/pi-telem/.venv/bin/python /home/pi/pi-telem/main.py --connection /dev/ttyUSB0 --baud 115200 --terrain --map
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart pitelem
```

The stock **`install.sh`** service runs **`main.py` without `--terrain` or `--map`**. Add any desired flags in **`systemctl edit`**, as above. Running **`python main.py --terrain`** manually while the service omits the flag explains “works on PC, not on Pi.”

### If terrain works locally but not on the Pi

| Symptom | What to check |
|--------|----------------|
| No SVS, flat brown ground only | **`--terrain` not in the command** (service or script). |
| Still nothing after adding `--terrain` | **GPS lat/lon** are often `0,0` until lock. The HUD falls back to **home** if **`HOME_POSITION`** is set; otherwise terrain waits for a valid position. |
| DEM never loads | **Network** once so tiles can download to **`~/.cache/MAVProxy/terrain/`**; then offline use is fine. |
| Silent failure | Check **`journalctl -u pitelem -e`** — the terrain thread logs errors to stderr at most every 30s, e.g. missing **`numpy`**, missing **`lib/`**, or elevation init failure. Run **`./.venv/bin/pip install -r requirements.txt`** from the repo root. |

## Hardware Setup

- **Pi Zero 2 W** running Raspberry Pi OS Lite (no desktop needed)
- **RFD900** radio modem connected via **FTDI USB-to-serial** adapter
- Any **HDMI display** (mini-HDMI adapter required for the Pi Zero 2 W)

## Dependencies

- Python 3
- **pygame** (SDL2), **pymavlink**, **numpy** (terrain)
- Vendored terrain code under **`lib/`** (SRTM/Copernicus tile access)
- System packages (via `install.sh`): `libsdl2-dev`, `libsdl2-image-dev`, `libsdl2-ttf-dev`, `fonts-dejavu-core`, etc.

`install.sh` creates **`.venv`** and runs `pip install -r requirements.txt`.
