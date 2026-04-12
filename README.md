# pi-telem

MAVLink telemetry HUD for Raspberry Pi Zero 2 W. Reads telemetry from an RFD900 radio (via FTDI/serial) or from an ArduPilot SITL instance over the network, and renders a Yaapu-style heads-up display with an artificial horizon to an HDMI screen using pygame.

**Repository:** [github.com/Cookie125/pi-telem](https://github.com/Cookie125/pi-telem) (default branch: `main`)

## Features

- Artificial horizon with pitch ladder and roll indicator
- **Synthetic vision (SVS) terrain** on the horizon (**on by default**; `--no-terrain` to disable) — layered terrain bands styled like MAVProxy’s `horizon_svs`, using SRTM/Copernicus elevation data
- Scrolling **IAS** (indicated airspeed) tape and dual **REL / MSL** altitude tapes (narrow columns tuned for **800×480** class panels); altitude readouts are **whole units** (no decimals); tape titles sit in a **label band** above each scrolling area
- Compass heading ribbon with home bearing marker
- **Wind**: direction arrow plus speed in the **top status bar** (to the left of GPS), same strip as mode / arm / waypoint
- **Vertical speed** in the **compass row** (right column, aligned with the alt tapes); **EFI RPM** on the **bottom bar** (right of messages)
- Flight mode, arm status, and current waypoint (when the FC sends `MISSION_CURRENT` / `NAV_CONTROLLER_OUTPUT`)
- GPS fix type and satellite count
- Battery voltage, current, remaining %, and optional second-pack “Fuel %” when present
- **HOME** distance and bearing in the left strip below the compass (compact **H …** label; scales down if the column is narrow)
- **PIP map** (**on by default**; `--no-map` to disable): satellite **Esri World Imagery** by default (or any XYZ tile URL), with **HOME**, **mission waypoints** on the route when **`MISSION_ITEM_*`** messages are available (**`--tx`** pulls the mission from the FC; **receive-only** can still show waypoints if **another GCS** downloads the mission on the **same MAVLink stream**), dotted route (including segments that cross off the PIP), and ownship heading arrow; with **HOME** set, zoom/pan **auto-frames aircraft + HOME** (cap `--map-zoom`); tiles cache under `~/.cache/pi-telem/map_tiles/` per tile URL
- STATUSTEXT message log
- Auto-start on boot via systemd (`install.sh`)

## Quick Start

```bash
git clone https://github.com/Cookie125/pi-telem.git && cd pi-telem
git checkout main
./install.sh   # run as the Pi desktop user (not `sudo ./install.sh`), so systemd User= and XAUTHORITY match

# Run against a SITL instance (desktop / dev machine). Use --tx so the HUD can
# request streams/mission; add --no-terrain / --no-map to lighten dev runs.
.venv/bin/python main.py -c udpin:127.0.0.1:14550 --windowed --tx

# On the Pi: no -c uses UDP :14550 then USB serial (see "Connection strings").
# Map and terrain are on by default; MAVLink is receive-only unless you add --tx.
.venv/bin/python main.py --baud 115200

# Only a specific serial device
.venv/bin/python main.py -c /dev/ttyUSB0 --baud 115200

# Disable SVS / PIP if you want minimal CPU or no tile/DEM fetch
.venv/bin/python main.py -c /dev/ttyUSB0 --no-terrain --no-map
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

## Connection strings

Use **`-c` / `--connection`** with any `pymavlink` string. **Repeat `-c`** to try several links in **round-robin** until a heartbeat is received (missing `/dev/...` nodes are skipped quickly). **If you omit `-c`**, the default order is:

1. `udpin:0.0.0.0:14550` — listen for UDP (e.g. forwarded MAVLink or another machine on the LAN)  
2. `/dev/ttyUSB0` — common USB–serial (e.g. FTDI)  
3. `/dev/ttyACM0` — many CDC-ACM USB devices  
4. `/dev/serial0` — typical name for the Pi GPIO UART when enabled  

With **multiple** `-c` values, the first-heartbeat timeout is **5 s** per attempt; with **one** `-c`, it is **30 s**.

| String | Use |
|--------|-----|
| `/dev/ttyUSB0` | Serial (RFD900 via FTDI) |
| `udpin:0.0.0.0:14550` | UDP listen on all interfaces, port 14550 |
| `udpout:192.168.1.100:14550` | UDP connect to remote |
| `tcp:192.168.1.100:5762` | TCP connect to SITL |

## CLI Options

| Option | Description |
|--------|-------------|
| `-c`, `--connection` | MAVLink connection; **repeat** for fallback order. **Default** (if omitted): UDP `0.0.0.0:14550`, then `/dev/ttyUSB0`, `/dev/ttyACM0`, `/dev/serial0` |
| `-b`, `--baud` | Serial baud rate, ignored for UDP/TCP (default: `115200`) |
| `--tx` | **Default: off** (receive-only). When set, send MAVLink (stream requests, `HOME_POSITION` pull, mission download). Use for **SITL** or **full-duplex serial** |
| `-r`, `--resolution` | Display size `WxH` (default: `800x480`) |
| `--fps` | Target render frame rate (default: `10`) |
| `--alt-unit` | Altitude tapes: `m` or `ft` (default: `m`) |
| `--windowed` | Windowed mode instead of fullscreen (useful on a dev PC) |
| `--terrain` / `--no-terrain` | **Default: on.** SVS terrain on the horizon; **`--no-terrain`** to disable |
| `--terrain-db` | Elevation source: `SRTM1`, `SRTM3`, or `COP30` (default: `SRTM1`) |
| `--map` / `--no-map` | **Default: on.** Bottom-left PIP map; **`--no-map`** to disable |
| `--map-zoom` | Tile zoom **0–19** (default: **14**). With map enabled and HOME set, auto-fit uses the **minimum** zoom needed to show aircraft + HOME, **capped** by this value |
| `--map-tile-url` | XYZ template with `{z}`, `{x}`, `{y}` (default: Esri World Imagery `{z}/{y}/{x}`). Example OSM: `https://tile.openstreetmap.org/{z}/{x}/{y}.png` |

Equivalent short help:

```
-c, --connection   CONN (repeat for fallback; see README default list)
-b, --baud           Serial baud rate (default: 115200)
    --tx              Allow MAVLink uplink (default: receive-only)
-r, --resolution     WxH (default: 800x480)
    --fps             Target frame rate (default: 10)
    --alt-unit        m or ft (default: m)
    --windowed        Run in a window instead of fullscreen
    --terrain | --no-terrain   Default terrain on
    --terrain-db      SRTM1, SRTM3, or COP30 (default: SRTM1)
    --map | --no-map  Default map on
    --map-zoom        0–19 (default: 14)
    --map-tile-url    XYZ tile URL template
```

## Synthetic vision terrain (`--terrain`, default **on**)

- Elevation comes from **ArduPilot terrain mirrors** (same family as MAVProxy): default **`SRTM1`** (~30 m posts), or `SRTM3` / **Copernicus GLO-30** (`COP30`).
- Tiles download on first use and cache under **`~/.cache/MAVProxy/terrain/`** — allow internet once, or pre-cache tiles for your flying area.
- Implementation uses vendored helpers in **`lib/`** (`mp_elevation`, `srtm`, etc.) and a background sampler thread; terrain is drawn as **stacked polygons** similar to MAVProxy `horizon_svs`.
- Requires **NumPy** (listed in `requirements.txt`).
- If terrain data is missing or SVS is off, the horizon still shows the **standard blue/brown artificial horizon** (pitch ladder and roll). Link loss is separate: telemetry drives the HUD whenever MAVLink is connected.

## PIP map (`--map`, default **on**)

- **Default imagery** is **Esri World Imagery** (satellite). Override **`--map-tile-url`** for other XYZ providers; obey each provider’s terms.
- Tiles are cached on disk under **`~/.cache/pi-telem/map_tiles/<url-hash>/…`** so changing providers does not mix cached files.
- **Offline:** previously downloaded tiles still load; new areas need connectivity (or pre-cache by panning while online).
- Waypoint positions on the map require **`MISSION_ITEM_*`** data in the telemetry stream. With **`--tx`**, the HUD requests the mission from the autopilot. In **receive-only** mode it does **not** send requests, but it **still ingests** `MISSION_COUNT` / `MISSION_ITEM_INT` if they appear on the wire (e.g. **Mission Planner** or another device on the same radio link requested the mission first). If nothing on the link triggers a mission download, the route stays empty.
- Waypoint labels use **MAVLink mission sequence** (0-based), matching `MISSION_CURRENT.seq` and the status **WP:** line.
- **Auto-fit zoom** (when HOME is set) uses **aircraft + HOME only** — mission waypoints are drawn and routed, but they do **not** change the zoom level (so a distant WP does not shrink the map).

## Testing with SITL

Spin up an ArduPilot SITL instance and point it at the HUD:

```bash
# Terminal 1 — start SITL (ArduCopter example)
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550

# Terminal 2 — start the HUD (from the project venv)
cd ~/pi-telem
.venv/bin/python main.py -c udpin:127.0.0.1:14550 --windowed --tx --alt-unit ft

# Defaults already include terrain + map; disable either for a lighter run:
.venv/bin/python main.py -c udpin:127.0.0.1:14550 --windowed --tx --no-terrain
.venv/bin/python main.py -c udpin:127.0.0.1:14550 --windowed --tx --no-map
```

SITL on another machine:

```bash
# On the SITL machine
sim_vehicle.py -v ArduCopter --out=udp:<PI_IP>:14550

# On the Pi
.venv/bin/python main.py -c udpin:0.0.0.0:14550
```

If you use another virtualenv for ArduPilot tools only:

```bash
~/venv-ardupilot/bin/python main.py -c udpin:127.0.0.1:14550 --windowed --tx
```

Install project dependencies in that env first (`pip install -r requirements.txt`), or always use **`.venv/bin/python`** from this repo.

## Running as a Service

### What `install.sh` does

1. Installs system packages (Python, SDL2 dev libs, fonts).  
2. Adds your user to the **`dialout`** group (serial ports). Log out and back in (or reboot) for that to apply.  
3. Creates **`.venv`** and installs **`requirements.txt`**.  
4. Writes **`/etc/systemd/system/pitelem.service`** and runs **`systemctl enable pitelem`** (it does **not** start the service). After updating the unit file, run **`sudo systemctl daemon-reload && sudo systemctl enable pitelem`** (or re-run **`./install.sh`**) so systemd picks up changes.

### Raspberry Pi OS with desktop

The generated unit targets **Raspberry Pi OS with desktop** and a graphical login (including autologin):

| Unit setting | Purpose |
|----------------|--------|
| **`WantedBy=multi-user.target`** | Hook into the normal boot target so the unit actually starts on every boot (unlike relying only on **`graphical.target`**, which may not pull in services if the default target differs). |
| **`After=display-manager.service systemd-user-sessions.service`** | Start after the display manager **and** user session / logind (helps with **`/run/user/<uid>`**). |
| **`Wants=display-manager.service`** | Pull in the display manager if needed. |
| **`ExecStartPre=…bash…`** | Waits (up to **90 s**) for **`/tmp/.X11-unix/X0`**, **`~/.Xauthority`**, and **`/run/user/<uid>`** so the HUD does not start before **autologin / X11** is ready (fixes “blank screen until **`systemctl restart pitelem`**”). |
| **`TimeoutStartSec=120`** | Allows the wait loop plus Python startup before systemd times out. |
| **`User=`** *your login user* | Runs the HUD as the same user that owns the X session (see below). |
| **`Environment=DISPLAY=:0`** | Draw on the usual X11 display (adjust if your `DISPLAY` is not `:0`). |
| **`Environment=XAUTHORITY=/home/<user>/.Xauthority`** | Lets SDL/pygame authenticate to the X server (path matches the user passed to **`User=`**). |
| **`Environment=XDG_RUNTIME_DIR=/run/user/<uid>`** | User runtime dir (set from **`id -u`** at install time). Avoids **`XDG_RUNTIME_DIR is invalid or not set`** for fontconfig / SDL when the app is not launched from a desktop session. |
| **`Environment=PYTHONUNBUFFERED=1`** | Unbuffered stdout/stderr so **`print`** and Python logs show up in **`journalctl`** immediately (otherwise output can be held until the buffer fills). |
| **`WorkingDirectory=`** *repo path* | Ensures imports and relative paths behave. |
| **`ExecStart=.../main.py --baud 115200 --map --terrain`** | Default flags; **no `-c`** so the [connection list](#connection-strings) default applies. |
| **`Restart=always`** / **`RestartSec=5`** | Retry if X11 was not ready yet (e.g. **`.Xauthority`** missing before autologin finishes). |

**Do not** set **`SDL_VIDEODRIVER=kmsdrm`** in the unit: the desktop session owns the display.

Run **`./install.sh` as your normal desktop user** (e.g. `pi`), **not** `sudo ./install.sh` from root, so **`User=`** and **`XAUTHORITY=/home/<user>/.Xauthority`** match the account that logs into the desktop.

After install:

```bash
sudo systemctl start pitelem       # start now
sudo systemctl status pitelem      # check status
journalctl -u pitelem -f           # tail logs
```

**MAVLink** is **receive-only** unless you add **`--tx`** to **`ExecStart`**. The process **keeps trying** the default [connection list](#connection-strings) if nothing is plugged in yet.

### Changing flags or connections

```bash
sudo systemctl edit pitelem
```

**Full uplink** (mission download, stream requests — still default map + terrain):

```ini
[Service]
ExecStart=
ExecStart=/home/pi/pi-telem/.venv/bin/python /home/pi/pi-telem/main.py --baud 115200 --map --terrain --tx
```

**Only** a fixed serial device (no UDP in the rotation):

```ini
[Service]
ExecStart=
ExecStart=/home/pi/pi-telem/.venv/bin/python /home/pi/pi-telem/main.py -c /dev/ttyUSB0 --baud 115200 --map --terrain
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart pitelem
```

### If the service does not start on boot

- **`systemctl is-enabled pitelem`** should print **`enabled`**. If not: **`sudo systemctl enable pitelem`**.  
- **`systemctl status pitelem`** — look for **failed** / **inactive** and the last log lines.  
- Re-run **`./install.sh`** after pulling a newer unit, then **`sudo systemctl daemon-reload && sudo systemctl enable pitelem && sudo systemctl restart pitelem`**.  
- **`journalctl -b -u pitelem`** — errors opening the display, missing **`.Xauthority`**, or Python tracebacks.  
- If the journal only shows **`Started pitelem.service`** and no Python lines, ensure the unit sets **`PYTHONUNBUFFERED=1`** (current **`install.sh`** does); then **`sudo systemctl daemon-reload && sudo systemctl restart pitelem`**.

### If the window does not appear (desktop)

- **HUD only after `sudo systemctl restart pitelem`:** at cold boot the service used to start **before** X11 and your **`.Xauthority`** existed. The installed unit **waits** for the X socket and cookies (see **`ExecStartPre`** in the table above). Re-run **`./install.sh`** to refresh the unit, then **`daemon-reload`** + **`restart`**.  
- Confirm **`echo $DISPLAY`** on the Pi desktop (often **`:0`**); change the unit if yours differs.  
- Enable **autologin** or log in once after boot so **`~/.Xauthority`** exists; **`Restart=always`** retries until the HUD can connect to X11.  
- **`journalctl -u pitelem -e`** for Python/SDL errors (permissions, missing display).  
- If you see **`XDG_RUNTIME_DIR is invalid or not set`**, re-run **`./install.sh`** (the unit sets **`XDG_RUNTIME_DIR=/run/user/<uid>`**). That path is created when you log in; **`Restart=always`** usually clears the error after **`/run/user/<uid>`** exists.  
- A one-time **`fc-list` timed out** warning from pygame/fontconfig on slow SD cards is usually harmless.

### If terrain works locally but not on the Pi

| Symptom | What to check |
|--------|----------------|
| No SVS, flat brown ground only | **`--no-terrain`** in the command, or terrain thread failed — see logs. |
| Still nothing with terrain on | **GPS lat/lon** are often `0,0` until lock. The HUD falls back to **home** if **`HOME_POSITION`** is set; otherwise terrain waits for a valid position. |
| DEM never loads | **Network** once so tiles can download to **`~/.cache/MAVProxy/terrain/`**; then offline use is fine. |
| Silent failure | Check **`journalctl -u pitelem -e`** — the terrain thread logs errors to stderr at most every 30s, e.g. missing **`numpy`**, missing **`lib/`**, or elevation init failure. Run **`./.venv/bin/pip install -r requirements.txt`** from the repo root. |

## Hardware Setup

- **Pi Zero 2 W** (or similar) running **Raspberry Pi OS with desktop** (what **`install.sh`** targets)
- **RFD900** radio modem connected via **FTDI USB-to-serial** adapter
- Any **HDMI display** (mini-HDMI adapter required for the Pi Zero 2 W)

## Dependencies

- Python 3
- **pygame** (SDL2), **pymavlink**, **numpy** (terrain)
- Vendored terrain code under **`lib/`** (SRTM/Copernicus tile access)
- System packages (via `install.sh`): `libsdl2-dev`, `libsdl2-image-dev`, `libsdl2-ttf-dev`, `fonts-dejavu-core`, etc.

`install.sh` creates **`.venv`** and runs `pip install -r requirements.txt`.
