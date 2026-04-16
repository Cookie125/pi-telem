import os
import threading
import time
from typing import List, Optional

from pymavlink import mavutil


def _latlon_from_mission_item_int(msg) -> Optional[tuple]:
    """Return (lat, lon) in degrees or None if item has no global position."""
    lat = msg.x / 1.0e7
    lon = msg.y / 1.0e7
    if abs(lat) < 1e-7 and abs(lon) < 1e-7:
        return None
    return lat, lon


def _latlon_from_mission_item(msg) -> Optional[tuple]:
    """MISSION_ITEM uses float degrees for x/y."""
    lat = float(msg.x)
    lon = float(msg.y)
    if abs(lat) < 1e-7 and abs(lon) < 1e-7:
        return None
    return lat, lon


# Fallback vehicle types for mode resolution when the reported MAV_TYPE has
# no mode mapping in pymavlink (common with VTOL types 22-28).
_MODE_FALLBACK_TYPES = (1, 2, 10)  # Plane, Copter, Rover


def _resolve_mode(msg) -> str:
    """Resolve flight mode string, with fallback for unmapped vehicle types."""
    mode = mavutil.mode_string_v10(msg)
    if not mode.startswith("Mode("):
        return mode
    # Vehicle type has no mode mapping; try common ArduPilot fallbacks.
    for fallback_type in _MODE_FALLBACK_TYPES:
        mode_map = mavutil.mode_mapping_bynumber(fallback_type)
        if mode_map and msg.custom_mode in mode_map:
            return mode_map[msg.custom_mode]
    return mode


class MavlinkReader(threading.Thread):
    """Background thread that reads MAVLink and updates TelemetryState."""

    def __init__(
        self,
        connections: List[str],
        baud: int,
        state,
        rx_only: bool = False,
    ):
        super().__init__(daemon=True)
        if not connections:
            raise ValueError("connections must be non-empty")
        self.connections = connections
        self.baud = baud
        self.state = state
        self._rx_only = rx_only
        self._stop_event = threading.Event()
        self._conn = None
        self._conn_idx = 0
        # Mission download (MISSION_REQUEST_LIST / ITEM_INT)
        self._mis_busy = False
        self._mis_n: Optional[int] = None
        self._mis_buf: dict = {}
        self._mis_t0 = 0.0
        self._mission_pull_t = 0.0

    # -- lifecycle ------------------------------------------------------------

    def stop(self):
        self._stop_event.set()

    def run(self):
        n = len(self.connections)
        hb_timeout = 5.0 if n > 1 else 30.0
        while not self._stop_event.is_set():
            conn = self.connections[self._conn_idx % n]
            try:
                if conn.startswith("/dev/"):
                    if not os.path.exists(conn):
                        print(f"[mavlink_reader] skip {conn} (not present)")
                        self._conn_idx += 1
                        time.sleep(0.2 if n > 1 else 2.0)
                        continue
                    if not os.access(conn, os.R_OK | os.W_OK):
                        print(f"[mavlink_reader] {conn} not accessible yet, retrying in 5s...")
                        time.sleep(5)
                        continue
                self._connect(conn, heartbeat_timeout=hb_timeout)
                self._loop()
            except Exception as exc:
                print(f"[mavlink_reader] error on {conn}: {exc!r}, next in 2s")
                self.state.update(lambda s: setattr(s, "connected", False))
                self._close_conn()
                self._conn_idx += 1
                time.sleep(2)

    def _close_conn(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.close()
        except Exception:
            pass
        self._conn = None

    # Types that should NOT be treated as the vehicle (GCS, radios, etc.).
    _NON_VEHICLE_TYPES = frozenset((
        mavutil.mavlink.MAV_TYPE_GCS,               # 6
        mavutil.mavlink.MAV_TYPE_ANTENNA_TRACKER,    # 5  (optional, but not a vehicle)
    ))

    # -- connection -----------------------------------------------------------

    def _connect(self, conn_str: str, heartbeat_timeout: float) -> None:
        self._close_conn()
        print(f"[mavlink_reader] connecting to {conn_str} (baud={self.baud})")
        self._conn = mavutil.mavlink_connection(conn_str, baud=self.baud)
        print(f"[mavlink_reader] waiting for vehicle heartbeat (timeout {heartbeat_timeout}s)...")
        # Loop until we get a heartbeat from an actual vehicle, not a GCS or radio.
        deadline = time.monotonic() + heartbeat_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("no vehicle heartbeat received")
            self._conn.wait_heartbeat(timeout=remaining)
            hb_type = self._conn.messages.get("HEARTBEAT")
            if hb_type is not None and hb_type.type not in self._NON_VEHICLE_TYPES:
                break
            print(f"[mavlink_reader] skipping non-vehicle heartbeat (type={hb_type.type if hb_type else '?'})")
        print(f"[mavlink_reader] heartbeat from system {self._conn.target_system} "
              f"component {self._conn.target_component}")
        self.state.update(lambda s: setattr(s, "connected", True))
        if self._rx_only:
            print("[mavlink_reader] receive-only: not sending stream/home/mission requests")
        else:
            self._request_streams()
            self._mission_pull_t = time.monotonic() - 30.0  # mission download soon after connect

    def _request_streams(self):
        """Ask the vehicle to send us the data streams we care about."""
        rate_hz = 4
        streams = [
            mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS,
            mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS,
            mavutil.mavlink.MAV_DATA_STREAM_POSITION,
            mavutil.mavlink.MAV_DATA_STREAM_EXTRA1,
            mavutil.mavlink.MAV_DATA_STREAM_EXTRA2,
            mavutil.mavlink.MAV_DATA_STREAM_EXTRA3,
        ]
        for stream in streams:
            self._conn.mav.request_data_stream_send(
                self._conn.target_system,
                self._conn.target_component,
                stream,
                rate_hz,
                1,  # start
            )

    # -- main read loop -------------------------------------------------------

    def _request_home(self):
        """Ask the vehicle to send HOME_POSITION."""
        if self._rx_only:
            return
        self._conn.mav.command_long_send(
            self._conn.target_system,
            self._conn.target_component,
            mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE,
            0,
            mavutil.mavlink.MAVLINK_MSG_ID_HOME_POSITION,
            0, 0, 0, 0, 0, 0,
        )

    def _loop(self):
        last_home_request = 0.0

        while not self._stop_event.is_set():
            now = time.monotonic()
            if self._mis_busy and (now - self._mis_t0) > 15.0:
                self._mis_busy = False
                self._mis_n = None
                self._mis_buf = {}
            if not self._rx_only:
                if now - self._mission_pull_t >= 25.0:
                    self._mission_pull_t = now
                    self._start_mission_download()

                if now - last_home_request >= 5.0:
                    self._request_home()
                    last_home_request = now

            msg = self._conn.recv_match(blocking=True, timeout=1)
            if msg is None:
                continue
            mtype = msg.get_type()
            if mtype == "BAD_DATA":
                continue

            handler = self._handlers.get(mtype)
            if handler:
                handler(self, msg)

    # -- message handlers -----------------------------------------------------

    def _handle_heartbeat(self, msg):
        if (msg.get_srcSystem() == self._conn.target_system
                and msg.type not in self._NON_VEHICLE_TYPES):
            mode = _resolve_mode(msg)
            armed = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0

            def _up(s):
                s.flight_mode = mode
                s.armed = armed
                s.vehicle_type = msg.type
                s.last_heartbeat = time.monotonic()
                s.connected = True
            self.state.update(_up)

    def _handle_attitude(self, msg):
        def _up(s):
            s.roll = msg.roll
            s.pitch = msg.pitch
            s.yaw = msg.yaw
            s.last_attitude = time.monotonic()
        self.state.update(_up)

    def _handle_vfr_hud(self, msg):
        def _up(s):
            s.airspeed = msg.airspeed
            s.groundspeed = msg.groundspeed
            s.altitude_msl = msg.alt
            s.heading = msg.heading
            s.vspeed = msg.climb
        self.state.update(_up)

    def _handle_gps_raw_int(self, msg):
        def _up(s):
            s.gps_fix = msg.fix_type
            s.gps_sats = msg.satellites_visible
            if msg.fix_type >= 2:
                s.lat = msg.lat / 1e7
                s.lon = msg.lon / 1e7
                s.altitude_msl = msg.alt / 1000.0
        self.state.update(_up)

    def _handle_global_position_int(self, msg):
        def _up(s):
            s.lat = msg.lat / 1e7
            s.lon = msg.lon / 1e7
            s.altitude = msg.relative_alt / 1000.0
            s.altitude_msl = msg.alt / 1000.0
        self.state.update(_up)

    def _handle_sys_status(self, msg):
        def _up(s):
            s.bat_voltage = msg.voltage_battery / 1000.0
            s.bat_current = msg.current_battery / 100.0
            s.bat_remaining = msg.battery_remaining
        self.state.update(_up)

    def _handle_battery_status(self, msg):
        """BATTERY_STATUS id 0 = primary (HUD battery row); id 1 = second pack (Fuel %)."""

        def _up(s):
            bid = msg.id
            if bid == 0:
                if msg.voltages[0] != 65535:
                    s.bat_voltage = msg.voltages[0] / 1000.0
                s.bat_current = msg.current_battery / 100.0
                s.bat_remaining = msg.battery_remaining
            elif bid == 1:
                s.bat2_remaining = msg.battery_remaining
        self.state.update(_up)

    def _handle_home_position(self, msg):
        def _up(s):
            s.home_lat = msg.latitude / 1e7
            s.home_lon = msg.longitude / 1e7
            s.home_alt = msg.altitude / 1000.0
            s.home_set = True
        self.state.update(_up)

    def _handle_efi_status(self, msg):
        def _up(s):
            s.efi_rpm = float(msg.rpm)
        self.state.update(_up)

    def _handle_mission_current(self, msg):
        def _up(s):
            s.wp_seq = int(msg.seq)
            s.wp_total = int(msg.total)
        self.state.update(_up)

    def _handle_nav_controller_output(self, msg):
        def _up(s):
            s.wp_dist_m = float(msg.wp_dist)
        self.state.update(_up)

    def _handle_wind(self, msg):
        def _up(s):
            s.wind_dir = msg.direction
            s.wind_speed = msg.speed
            s.wind_valid = True
        self.state.update(_up)

    def _handle_statustext(self, msg):
        text = msg.text.strip() if isinstance(msg.text, str) else msg.text.decode("utf-8", errors="replace").strip()
        print(f"[statustext] {text}")

        def _up(s):
            s.messages.append((time.time(), text))
        self.state.update(_up)

    def _start_mission_download(self) -> None:
        if self._rx_only or self._conn is None or self._mis_busy:
            return
        self._mis_busy = True
        self._mis_n = None
        self._mis_buf = {}
        self._mis_t0 = time.monotonic()
        try:
            self._conn.mav.mission_request_list_send(
                self._conn.target_system,
                self._conn.target_component,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
        except Exception:
            self._mis_busy = False

    def _request_mission_seq(self, seq: int) -> None:
        if self._rx_only or self._conn is None:
            return
        try:
            self._conn.mav.mission_request_int_send(
                self._conn.target_system,
                self._conn.target_component,
                seq,
                mavutil.mavlink.MAV_MISSION_TYPE_MISSION,
            )
        except Exception:
            pass

    def _mission_missing_seq(self) -> Optional[int]:
        if self._mis_n is None:
            return None
        for i in range(self._mis_n):
            if i not in self._mis_buf:
                return i
        return None

    def _commit_mission(self, wps: list) -> None:
        def _up(s):
            s.mission_wps = wps
            s.mission_version += 1

        self.state.update(_up)

    def _finish_mission_item(self, seq: int, pt: Optional[tuple]) -> None:
        if not self._mis_busy or self._mis_n is None:
            return
        self._mis_buf[seq] = pt
        miss = self._mission_missing_seq()
        if miss is not None:
            if not self._rx_only:
                self._request_mission_seq(miss)
            return
        wps = [self._mis_buf.get(i) for i in range(self._mis_n)]
        self._commit_mission(wps)
        self._mis_busy = False
        self._mis_n = None
        self._mis_buf = {}

    def _handle_mission_count(self, msg):
        if msg.mission_type != mavutil.mavlink.MAV_MISSION_TYPE_MISSION:
            return
        if not self._mis_busy:
            self._mis_busy = True
            self._mis_t0 = time.monotonic()
        self._mis_buf = {}
        n = int(msg.count)
        self._mis_n = n
        if n == 0:
            self._commit_mission([])
            self._mis_busy = False
            self._mis_n = None
            return
        # Receive-only: cannot request items; still accept MISSION_ITEM_* if another GCS
        # (or the FC) causes them to be transmitted on the link.
        if not self._rx_only:
            self._request_mission_seq(0)

    def _handle_mission_item_int(self, msg):
        if msg.mission_type != mavutil.mavlink.MAV_MISSION_TYPE_MISSION:
            return
        seq = int(msg.seq)
        self._finish_mission_item(seq, _latlon_from_mission_item_int(msg))

    def _handle_mission_item(self, msg):
        mt = getattr(msg, "mission_type", mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
        if mt != mavutil.mavlink.MAV_MISSION_TYPE_MISSION:
            return
        seq = int(msg.seq)
        self._finish_mission_item(seq, _latlon_from_mission_item(msg))

    def _handle_mission_ack(self, msg):
        if msg.mission_type != mavutil.mavlink.MAV_MISSION_TYPE_MISSION:
            return
        if not self._mis_busy:
            return
        if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
            return
        self._mis_busy = False
        self._mis_n = None
        self._mis_buf = {}

    _handlers = {
        "HEARTBEAT": _handle_heartbeat,
        "ATTITUDE": _handle_attitude,
        "VFR_HUD": _handle_vfr_hud,
        "GPS_RAW_INT": _handle_gps_raw_int,
        "GLOBAL_POSITION_INT": _handle_global_position_int,
        "SYS_STATUS": _handle_sys_status,
        "BATTERY_STATUS": _handle_battery_status,
        "HOME_POSITION": _handle_home_position,
        "EFI_STATUS": _handle_efi_status,
        "MISSION_CURRENT": _handle_mission_current,
        "MISSION_COUNT": _handle_mission_count,
        "MISSION_ITEM_INT": _handle_mission_item_int,
        "MISSION_ITEM": _handle_mission_item,
        "MISSION_ACK": _handle_mission_ack,
        "NAV_CONTROLLER_OUTPUT": _handle_nav_controller_output,
        "WIND": _handle_wind,
        "STATUSTEXT": _handle_statustext,
    }
