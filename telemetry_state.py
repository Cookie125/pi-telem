import copy
import threading
import time
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class _StateFields:
    # Attitude
    roll: float = 0.0       # radians
    pitch: float = 0.0      # radians
    yaw: float = 0.0        # radians

    # Navigation
    heading: float = 0.0    # degrees 0-360
    altitude: float = 0.0   # metres relative (AGL)
    # Mission / waypoint (MISSION_CURRENT, NAV_CONTROLLER_OUTPUT)
    wp_seq: int = -1        # MISSION_CURRENT.seq (shown as-is; FCs vary), -1 = unknown
    wp_total: int = 0       # mission item count from MISSION_CURRENT.total
    wp_dist_m: float = -1.0  # distance to current WP (m), -1 = unknown
    altitude_msl: float = 0.0  # metres above mean sea level
    airspeed: float = 0.0   # m/s
    groundspeed: float = 0.0
    vspeed: float = 0.0     # m/s climb rate

    # Battery
    bat_voltage: float = 0.0    # volts
    bat_current: float = 0.0    # amps
    bat_remaining: int = -1     # percent, -1 = unknown (battery 1)
    bat2_remaining: int = -1    # percent from BATTERY_STATUS id=1 (e.g. fuel), -1 = unknown

    # GPS
    gps_fix: int = 0        # 0=no, 2=2D, 3=3D
    gps_sats: int = 0
    lat: float = 0.0        # degrees
    lon: float = 0.0        # degrees

    # Home
    home_lat: float = 0.0
    home_lon: float = 0.0
    home_alt: float = 0.0
    home_set: bool = False

    # EFI (EFI_STATUS MAVLink)
    efi_rpm: float = -1.0      # RPM, -1 = unknown / no data

    # Wind
    wind_dir: float = 0.0      # degrees (direction wind is coming FROM)
    wind_speed: float = 0.0    # m/s
    wind_valid: bool = False

    # Status
    flight_mode: str = "UNKNOWN"
    armed: bool = False
    vehicle_type: int = 0   # MAV_TYPE

    # Messages (most recent at end)
    messages: List[Tuple[float, str]] = field(default_factory=list)

    # Timestamps
    last_heartbeat: float = 0.0
    last_attitude: float = 0.0
    last_update: float = 0.0

    # Connection health
    connected: bool = False


MAX_MESSAGES = 50


class TelemetryState:
    """Thread-safe telemetry state container.

    The reader thread calls update() with a callback that mutates fields.
    The render loop calls snapshot() to get a frozen copy for drawing.
    """

    def __init__(self):
        self._state = _StateFields()
        self._lock = threading.Lock()

    def update(self, fn):
        """Call fn(state) while holding the lock. fn should mutate state fields."""
        with self._lock:
            fn(self._state)
            self._state.last_update = time.monotonic()
            if len(self._state.messages) > MAX_MESSAGES:
                self._state.messages = self._state.messages[-MAX_MESSAGES:]

    def snapshot(self) -> _StateFields:
        """Return a shallow copy of the current state for rendering."""
        with self._lock:
            s = copy.copy(self._state)
            s.messages = list(self._state.messages)
            return s
