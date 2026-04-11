import argparse


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
        default="/dev/ttyUSB0",
        help="MAVLink connection string (default: /dev/ttyUSB0)",
    )
    p.add_argument(
        "-b", "--baud",
        type=int,
        default=115200,
        help="Serial baud rate, ignored for network connections (default: 115200)",
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

    args = p.parse_args()

    w, h = args.resolution.split("x")
    args.resolution = (int(w), int(h))

    return args
