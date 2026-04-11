"""Terrain SVS (Synthetic Vision System) for the HUD.

Two classes:
    TerrainSampler  - background thread (2 Hz) that ray-casts and queries SRTM elevation
    TerrainRenderer - converts angle_grid data into a cached pygame.Surface (numpy surfarray)
"""

import math
import sys
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pygame

# Add project root to sys.path so lib/ can be found as a package
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ------------------------------------------------------------------
# Tunable constants
# ------------------------------------------------------------------
NUM_RAYS = 101         # horizontal rays across the FOV (matches mavproxy)
FOV_DEG = 120.0        # degrees either side of heading (-60 to +60)
NUM_STEPS = 120        # sample points along each ray
MAX_RANGE_M = 1500.0   # maximum ray length in metres
NUM_BANDS = 24         # range bands for color grading (matches mavproxy max)
SAMPLE_HZ = 2.0        # how often the sampler runs
POS_MOVE_THRESH = 30.0 # metres moved before re-querying DEM
HDG_CHANGE_THRESH = 2.0  # degrees heading change before re-querying DEM

# Earth radius for rhumb-line math
EARTH_R = 6_378_100.0

# ------------------------------------------------------------------
# Elevation color ramp (from mavproxy horizon_svs)
# Each entry: (elevation_angle_deg, (r, g, b))  where RGB are 0.0–1.0
# Terrain far below the horizon is green; near/above is brown/grey.
# ------------------------------------------------------------------
_TERRAIN_COLOR_RAMP = [
    (-90.0, (0.06, 0.25, 0.08)),   # deep green (far below)
    (-60.0, (0.12, 0.38, 0.14)),
    (-45.0, (0.18, 0.45, 0.18)),
    (-30.0, (0.28, 0.52, 0.22)),
    (-20.0, (0.38, 0.50, 0.24)),
    (-12.0, (0.45, 0.48, 0.26)),
    ( -8.0, (0.52, 0.46, 0.28)),   # tan transition
    ( -4.0, (0.55, 0.42, 0.26)),
    (  0.0, (0.52, 0.38, 0.24)),
    (  5.0, (0.48, 0.34, 0.22)),
    ( 10.0, (0.42, 0.30, 0.20)),   # brown
    ( 20.0, (0.38, 0.28, 0.22)),
    ( 45.0, (0.35, 0.30, 0.28)),   # grey/rock
]


# ------------------------------------------------------------------
# Pre-computed color LUT for fast vectorized angle -> RGB mapping
# ------------------------------------------------------------------
_LUT_MIN_DEG = -90.0
_LUT_MAX_DEG = 45.0
_LUT_STEP_DEG = 0.25
_LUT_SIZE = int((_LUT_MAX_DEG - _LUT_MIN_DEG) / _LUT_STEP_DEG) + 1


def _build_color_lut():
    """Build a (_LUT_SIZE, 3) float32 array: elevation angle -> (R, G, B) 0-255.

    Distance darkening is NOT baked in so it can be applied per-band at render time.
    """
    ramp_angles = np.array([r[0] for r in _TERRAIN_COLOR_RAMP])
    ramp_r = np.array([r[1][0] for r in _TERRAIN_COLOR_RAMP])
    ramp_g = np.array([r[1][1] for r in _TERRAIN_COLOR_RAMP])
    ramp_b = np.array([r[1][2] for r in _TERRAIN_COLOR_RAMP])

    angles = np.linspace(_LUT_MIN_DEG, _LUT_MAX_DEG, _LUT_SIZE)
    lut = np.empty((_LUT_SIZE, 3), dtype=np.float32)
    lut[:, 0] = np.interp(angles, ramp_angles, ramp_r) * 255.0
    lut[:, 1] = np.interp(angles, ramp_angles, ramp_g) * 255.0
    lut[:, 2] = np.interp(angles, ramp_angles, ramp_b) * 255.0
    return lut


_COLOR_LUT = _build_color_lut()  # built once at import time


def _lut_index(angle_deg_arr: np.ndarray) -> np.ndarray:
    """Convert an array of elevation angles (degrees) to LUT indices."""
    return ((angle_deg_arr - _LUT_MIN_DEG) / _LUT_STEP_DEG).astype(
        np.int32
    ).clip(0, _LUT_SIZE - 1)


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------
@dataclass
class TerrainProfile:
    """Output of TerrainSampler -- everything TerrainRenderer needs."""
    # Azimuth angles in degrees relative to heading, shape (NUM_RAYS,)
    # e.g. -60 ... 0 ... +60
    rel_azimuths: np.ndarray
    # Elevation angles in radians for each (ray, band), shape (NUM_RAYS, NUM_BANDS)
    # Positive = terrain above aircraft, negative = below
    angle_grid: np.ndarray
    # Bands valid mask -- False if no DEM data for that band/ray
    valid_grid: np.ndarray
    # Band distances (centre of each band) in metres, shape (NUM_BANDS,)
    band_dists: np.ndarray


# ------------------------------------------------------------------
# Vectorized rhumb-line position math
# ------------------------------------------------------------------
def _ray_positions(lat_deg: float, lon_deg: float,
                   azimuth_deg_arr: np.ndarray,
                   distances_m: np.ndarray):
    """Compute (lat, lon) for every (azimuth, distance) pair.

    azimuth_deg_arr: shape (R,)
    distances_m:     shape (S,)
    Returns lats, lons each shape (R, S) in degrees.
    """
    lat1 = math.radians(lat_deg)
    lon1 = math.radians(lon_deg)

    # tc shape (R, 1)
    tc = np.radians(-azimuth_deg_arr[:, np.newaxis])  # (R,1)
    # d shape (1, S)
    d = distances_m[np.newaxis, :] / EARTH_R            # (1,S)

    lat1 = np.clip(lat1, -math.pi / 2 + 1e-9, math.pi / 2 - 1e-9)

    lat2 = lat1 + d * np.cos(tc)  # (R, S)
    lat2 = np.clip(lat2, -math.pi / 2 + 1e-9, math.pi / 2 - 1e-9)

    delta_lat = lat2 - lat1
    near_zero = np.abs(delta_lat) < 1e-12
    with np.errstate(divide="ignore", invalid="ignore"):
        log_ratio = np.log(
            np.tan(lat2 / 2 + math.pi / 4) /
            np.tan(lat1 / 2 + math.pi / 4)
        )
    q = np.where(near_zero, np.cos(lat1), delta_lat / np.where(log_ratio == 0, 1e-15, log_ratio))

    dlon = -d * np.sin(tc) / np.where(q == 0, 1e-15, q)
    lon2 = ((lon1 + dlon + math.pi) % (2 * math.pi)) - math.pi

    return np.degrees(lat2), np.degrees(lon2)


# ------------------------------------------------------------------
# TerrainSampler
# ------------------------------------------------------------------
class TerrainSampler(threading.Thread):
    """Background thread: casts rays, queries DEM, produces TerrainProfile."""

    def __init__(self, state, db: str = "SRTM1"):
        super().__init__(name="TerrainSampler", daemon=True)
        self._state = state
        self._db = db
        self._lock = threading.Lock()
        self._profile: Optional[TerrainProfile] = None
        self._profile_seq = 0  # incremented each time a new profile is ready

        # Layer-1 cache: last DEM query results
        self._cached_lat = None
        self._cached_lon = None
        self._cached_hdg = None
        self._cached_elev = None   # shape (NUM_RAYS, NUM_STEPS)
        self._cached_valid = None  # shape (NUM_RAYS, NUM_STEPS)

        # Pre-compute ray geometry (relative azimuths, distances)
        self._rel_az = np.linspace(-FOV_DEG / 2, FOV_DEG / 2, NUM_RAYS)
        step_size = MAX_RANGE_M / NUM_STEPS
        self._distances = np.arange(1, NUM_STEPS + 1) * step_size  # (S,)
        band_size = NUM_STEPS // NUM_BANDS
        self._band_dists = np.array([
            ((i * band_size + (i + 1) * band_size) / 2) * step_size
            for i in range(NUM_BANDS)
        ])

        self._elev_model = None  # lazy init in run()

    # ------------------------------------------------------------------
    def _init_elevation_model(self):
        from lib.mp_elevation import ElevationModel
        self._elev_model = ElevationModel(self._db)

    def run(self):
        self._init_elevation_model()
        interval = 1.0 / SAMPLE_HZ
        while True:
            t0 = time.monotonic()
            try:
                self._sample()
            except Exception:
                pass
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))

    # ------------------------------------------------------------------
    def _sample(self):
        s = self._state.snapshot()
        if not s.connected or s.lat == 0.0 and s.lon == 0.0:
            return

        lat, lon, alt_msl = s.lat, s.lon, s.altitude_msl
        # heading is stored in degrees 0-360 in telemetry_state
        hdg_deg = s.heading % 360.0

        # Absolute azimuths for the rays
        abs_az = (hdg_deg + self._rel_az) % 360.0  # (R,)

        # Layer-1 cache check
        need_dem = True
        if (self._cached_lat is not None and
                self._cached_elev is not None):
            dlat = abs(lat - self._cached_lat) * EARTH_R * math.pi / 180.0
            dlon = abs(lon - self._cached_lon) * EARTH_R * math.pi / 180.0 * math.cos(math.radians(lat))
            dist_moved = math.hypot(dlat, dlon)
            hdg_delta = abs((hdg_deg - self._cached_hdg + 180) % 360 - 180)
            if dist_moved < POS_MOVE_THRESH and hdg_delta < HDG_CHANGE_THRESH:
                need_dem = False

        if need_dem:
            lats, lons = _ray_positions(lat, lon, abs_az, self._distances)
            # lats/lons shape (R, S)
            elev, valid = self._elev_model.GetElevationBulk(lats, lons)
            self._cached_lat = lat
            self._cached_lon = lon
            self._cached_hdg = hdg_deg
            self._cached_elev = elev
            self._cached_valid = valid
        else:
            elev = self._cached_elev
            valid = self._cached_valid

        # Compute elevation angles: shape (R, S)
        dz = elev - alt_msl  # positive when terrain above aircraft
        angle_rad = np.arctan2(dz, self._distances[np.newaxis, :])  # (R, S)

        # Group into NUM_BANDS, take max angle per band per ray
        band_size = NUM_STEPS // NUM_BANDS
        angle_grid = np.full((NUM_RAYS, NUM_BANDS), -math.pi / 2)
        valid_grid = np.zeros((NUM_RAYS, NUM_BANDS), dtype=bool)

        for b in range(NUM_BANDS):
            sl = slice(b * band_size, (b + 1) * band_size)
            band_angles = angle_rad[:, sl]   # (R, band_size)
            band_valid = valid[:, sl]        # (R, band_size)
            # only consider valid samples
            masked = np.where(band_valid, band_angles, -math.pi / 2)
            angle_grid[:, b] = np.max(masked, axis=1)
            valid_grid[:, b] = np.any(band_valid, axis=1)

        profile = TerrainProfile(
            rel_azimuths=self._rel_az.copy(),
            angle_grid=angle_grid,
            valid_grid=valid_grid,
            band_dists=self._band_dists.copy(),
        )

        with self._lock:
            self._profile = profile
            self._profile_seq += 1

    # ------------------------------------------------------------------
    def get_profile(self):
        """Return (seq, profile) atomically. seq increments on new data."""
        with self._lock:
            return self._profile_seq, self._profile


# ------------------------------------------------------------------
# TerrainRenderer
# ------------------------------------------------------------------

# Must match hud/horizon.py PPD so elevation angles land on the
# same pixel rows as the pitch ladder and horizon line.
_PPD = 4.0                           # pixels per degree (from horizon.py)
_PPR = _PPD * 180.0 / math.pi       # pixels per radian


def _terrain_color_for_elevation(max_angle_deg: float, dist_factor: float):
    """Return (R, G, B) 0-255 for a band given its max elevation angle and distance.

    dist_factor: 0 = far, 1 = near.  Nearer bands are slightly darker for depth.
    """
    ramp = _TERRAIN_COLOR_RAMP
    a = max(-90.0, min(45.0, max_angle_deg))
    for i in range(len(ramp) - 1):
        a0, c0 = ramp[i]
        a1, c1 = ramp[i + 1]
        if a <= a1:
            t = (a - a0) / (a1 - a0) if a1 != a0 else 1.0
            r = c0[0] + t * (c1[0] - c0[0])
            g = c0[1] + t * (c1[1] - c0[1])
            b = c0[2] + t * (c1[2] - c0[2])
            break
    else:
        r, g, b = ramp[-1][1]
    darken = 0.85 + 0.15 * (1.0 - dist_factor)
    return (int(min(255, r * darken * 255)),
            int(min(255, g * darken * 255)),
            int(min(255, b * darken * 255)))


class TerrainRenderer:
    """Renders terrain as layered filled polygons matching mavproxy horizon_svs.

    Each range band is a polygon whose top edge follows the per-ray elevation
    profile (mountain silhouette) and whose bottom edge is the previous band's
    top edge.  Bands are drawn far-to-near with increasing alpha, producing a
    stacked depth effect with visible contour edges between layers.
    """

    def __init__(self):
        self._cached_surface: Optional[pygame.Surface] = None
        self._last_seq = -1
        self._last_size = (0, 0)

    # ------------------------------------------------------------------
    def update(self, seq: int, profile: Optional[TerrainProfile],
               surface_size: tuple, pitch_rad: float, roll_rad: float):
        """Rebuild the cached surface when new terrain data arrives."""
        if profile is None:
            return
        if seq == self._last_seq and surface_size == self._last_size:
            return
        self._last_seq = seq
        self._last_size = surface_size
        self._rebuild(profile, surface_size)

    # ------------------------------------------------------------------
    def _rebuild(self, profile: TerrainProfile, size: tuple):
        W, H = size
        if W <= 0 or H <= 0:
            return

        # SRCALPHA surface: sky pixels stay (0,0,0,0) = fully transparent
        surf = pygame.Surface((W, H), pygame.SRCALPHA)

        horizon_row = H / 2.0

        # --- Interpolate rays to pixel columns ----------------------------
        ray_az = profile.rel_azimuths          # (R,)
        col_az = np.linspace(ray_az[0], ray_az[-1], W)

        angle_grid = profile.angle_grid        # (R, B)  radians
        n_bands = angle_grid.shape[1]

        # Interpolate elevation angles from R rays -> W pixel columns per band
        interp_angles = np.empty((W, n_bands))
        for b in range(n_bands):
            interp_angles[:, b] = np.interp(col_az, ray_az, angle_grid[:, b])

        # Convert elevation angles to pixel Y rows
        # Positive angle = above horizon = lower row number
        band_rows = horizon_row - np.degrees(interp_angles) * _PPD
        band_rows = np.clip(band_rows, 0, H).astype(np.int32)

        # --- Build and draw stacked band polygons -------------------------
        # y_prev tracks the bottom edge for the next band (starts at screen bottom)
        y_prev_full = np.full(W, H, dtype=np.int32)

        # Subsample x positions for polygon vertices (every ~4 px keeps detail,
        # reduces vertex count from ~1600 to ~400 per polygon edge)
        step = max(1, W // 200)
        sample_idx = np.arange(0, W, step, dtype=np.int32)
        if sample_idx[-1] != W - 1:
            sample_idx = np.append(sample_idx, W - 1)
        xs_sub = sample_idx  # pixel x coords for sampled points

        for b in range(n_bands):
            y_top_full = band_rows[:, b]  # (W,)

            # Subsample edges
            y_bot = y_prev_full[sample_idx]
            y_top = y_top_full[sample_idx]

            # Per-band color from the elevation-angle ramp
            dist_factor = (b + 1) / max(n_bands, 1)
            max_ang = float(np.degrees(np.max(interp_angles[:, b])))
            color_rgb = _terrain_color_for_elevation(max_ang, dist_factor)

            # Per-band alpha: far = more transparent, near = more opaque
            alpha = int((0.78 + 0.18 * dist_factor) * 255)
            color_rgba = (*color_rgb, alpha)

            # Build polygon: bottom edge L->R, then top edge R->L
            bottom_pts = list(zip(xs_sub.tolist(), y_bot.tolist()))
            top_pts = list(zip(xs_sub[::-1].tolist(), y_top[::-1].tolist()))

            verts = (
                [(-1, int(y_bot[0]))]
                + bottom_pts
                + [(W, int(y_bot[-1]))]
                + [(W, int(y_top[-1]))]
                + top_pts
                + [(-1, int(y_top[0]))]
            )

            pygame.draw.polygon(surf, color_rgba, verts)

            # This band's top becomes the next band's bottom
            y_prev_full = y_top_full.copy()

        self._cached_surface = surf

    # ------------------------------------------------------------------
    def get_surface(self) -> Optional[pygame.Surface]:
        return self._cached_surface
