import argparse

# Tried in order when --connection is omitted (Pi: UDP + common USB / UART devices).
DEFAULT_CONNECTIONS = (
    "udpin:0.0.0.0:14550",
    "/dev/ttyUSB0",
    "/dev/ttyACM0",
    "/dev/serial0",
)


def parse_args():
    p = argparse.ArgumentParser(
        description="Pi Zero 2 W MAVLink Telemetry HUD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
connection string examples:
  /dev/ttyUSB0                 Serial (RFD900 via FTDI)
  udpin:0.0.0.0:14550          UDP listen (SITL default)
  udpout:192.168.1.100:14550   UDP connect to remote
  tcp:192.168.1.100:5762       TCP connect to SITL
""",
    )
    p.add_argument(
        "-c", "--connection",
        action="append",
        dest="connections",
        metavar="CONN",
        default=None,
        help=(
            "MAVLink connection string; repeat for round-robin until one connects. "
            "If omitted: UDP listen 0.0.0.0:14550, then "
            "/dev/ttyUSB0, /dev/ttyACM0, /dev/serial0"
        ),
    )
    p.add_argument(
        "-b", "--baud",
        type=int,
        default=115200,
        help="Serial baud rate, ignored for network connections (default: 115200)",
    )
    p.add_argument(
        "--rx-only",
        action="store_true",
        help=(
            "Receive-only: do not transmit MAVLink (no data-stream requests, "
            "HOME_POSITION pull, or mission download). For listen-only serial "
            "(e.g. Pi RX tied to radio TX without a return wire)."
        ),
    )
    p.add_argument(
        "-r", "--resolution",
        default="800x480",
        help="Display resolution WxH (default: 800x480)",
    )
    p.add_argument(
        "--fps",
        type=int,
        default=10,
        help="Target render frame rate (default: 10)",
    )
    p.add_argument(
        "--windowed",
        action="store_true",
        help="Run in a window instead of fullscreen",
    )
    p.add_argument(
        "--alt-unit",
        choices=["m", "ft"],
        default="m",
        help="Altitude display unit (default: m)",
    )
    p.add_argument(
        "--terrain",
        action="store_true",
        help="Enable SVS terrain rendering on the artificial horizon",
    )
    p.add_argument(
        "--terrain-db",
        choices=["SRTM1", "SRTM3", "COP30"],
        default="SRTM1",
        help="Terrain elevation source (default: SRTM1)",
    )
    p.add_argument(
        "--map",
        action="store_true",
        help="Enable PIP map (satellite tiles + HOME / ownship; uses ~/.cache/pi-telem/map_tiles)",
    )
    p.add_argument(
        "--map-zoom",
        type=int,
        default=14,
        help=(
            "Map tile zoom 0–19 (default: 14). With --map and HOME set, zoom/pan "
            "auto-fits aircraft + HOME on the PIP (mission WPs are drawn but not used "
            "for scale); this value caps max zoom-in."
        ),
    )
    p.add_argument(
        "--map-tile-url",
        default=(
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        help=(
            "XYZ tile URL template with {z} {x} {y} (order may vary; Esri uses {z}/{y}/{x}) "
            "(default: Esri World Imagery satellite; obey provider terms)"
        ),
    )

    args = p.parse_args()

    if not args.connections:
        args.connections = list(DEFAULT_CONNECTIONS)
    else:
        args.connections = list(args.connections)

    w, h = args.resolution.split("x")
    args.resolution = (int(w), int(h))

    return args
