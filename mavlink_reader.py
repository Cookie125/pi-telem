import threading
import time
from typing import Optional

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


class MavlinkReader(threading.Thread):
    """Background thread that reads MAVLink and updates TelemetryState."""

    def __init__(self, connection_string, baud, state):
        super().__init__(daemon=True)
        self.connection_string = connection_string
        self.baud = baud
        self.state = state
        self._stop_event = threading.Event()
        self._conn = None
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
        while not self._stop_event.is_set():
            try:
                self._connect()
                self._loop()
            except Exception as exc:
                print(f"[mavlink_reader] error: {exc}, reconnecting in 2s")
                self.state.update(lambda s: setattr(s, "connected", False))
                time.sleep(2)

    # -- connection -----------------------------------------------------------

    def _connect(self):
        print(f"[mavlink_reader] connecting to {self.connection_string} "
              f"(baud={self.baud})")
        self._conn = mavutil.mavlink_connection(
            self.connection_string, baud=self.baud
        )
        print("[mavlink_reader] waiting for heartbeat...")
        self._conn.wait_heartbeat(timeout=30)
        print(f"[mavlink_reader] heartbeat from system {self._conn.target_system} "
              f"component {self._conn.target_component}")
        self.state.update(lambda s: setattr(s, "connected", True))
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
        self._conn.mav.command_long_send(
            self._conn.target_system,
            self._conn.target_component,
            mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE,
            0,
            mavutil.mavlink.MAVLINK_MSG_ID_HOME_POSITION,
            0, 0, 0, 0, 0, 0,
        )

    def _loop(self):
        last_heartbeat_sent = 0.0
        last_home_request = 0.0

        while not self._stop_event.is_set():
            now = time.monotonic()
            if self._mis_busy and (now - self._mis_t0) > 15.0:
                self._mis_busy = False
                self._mis_n = None
                self._mis_buf = {}
            if now - self._mission_pull_t >= 25.0:
                self._mission_pull_t = now
                self._start_mission_download()

            if now - last_heartbeat_sent >= 1.0:
                self._send_heartbeat()
                last_heartbeat_sent = now
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

    def _send_heartbeat(self):
        self._conn.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
            0, 0, 0,
        )

    # -- message handlers -----------------------------------------------------

    def _handle_heartbeat(self, msg):
        if msg.get_srcSystem() == self._conn.target_system:
            mode = mavutil.mode_string_v10(msg)
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
        if self._conn is None or self._mis_busy:
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
        if self._conn is None:
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
