"""Optional PIP map: raster tiles + HOME and ownship heading marker (background thread)."""

from __future__ import annotations

import hashlib
import io
import math
import os
import threading
import time
import urllib.error
import urllib.request
from typing import List, Optional, Tuple

import pygame

from hud import colors
from hud.fonts import get_font
from hud.home_info import _haversine

# Fixed PIP size (keeps tile count and CPU bounded on Pi Zero 2 W)
PIP_W = 184
PIP_H = 136
TILE_SIZE = 256

# Rebuild at most this often, or when moved this far (metres)
SAMPLE_INTERVAL_S = 1.25
MOVE_THRESH_M = 35.0

# Map imagery transparency (0–255; higher = more opaque)
MAP_TILE_ALPHA = 200
# Base fill behind tiles (RGBA) — slightly transparent so horizon shows through
MAP_BASE_RGBA = (26, 28, 32, 210)
# Mission route: dotted line (RGBA)
ROUTE_DOT_RGBA = (220, 235, 255, 115)
ROUTE_DOT_SPACING_PX = 5
ROUTE_DOT_RADIUS = 1

# When HOME is set, fit aircraft + HOME in the PIP (with margin); mission WPs drawn but not used for zoom
FIT_MARGIN_PX = 8
# Rebuild a bit more often while auto-framing so zoom/pan tracks
AUTO_FIT_MOVE_THRESH_M = 12.0
AUTO_FIT_MAX_INTERVAL_S = 2.0
# When within this distance of HOME, rebuild on smaller moves so zoom tracks the approach
HOME_APPROACH_M = 300.0
AUTO_FIT_MOVE_THRESH_NEAR_M = 5.0

# Tile policy: identify; cache on disk; throttle requests
USER_AGENT = "pi-telem/1.0 (+https://github.com/Cookie125/pi-telem; map tiles)"

_DEFAULT_TILE_URL = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)

# Triangle arrow, tip toward -Y (north); rotates with heading — generic map-style marker
_HEADING_ARROW_BASE: Optional[pygame.Surface] = None


def _home_autofit_enabled(s) -> bool:
    return bool(
        s.home_set
        and (abs(s.home_lat) > 1e-12 or abs(s.home_lon) > 1e-12),
    )


def _collect_zoom_frame_points(s, ac_lat: float, ac_lon: float) -> List[Tuple[float, float]]:
    """Only aircraft + HOME — zoom level then tightens as you get closer to HOME (mission WPs not used for scale)."""
    pts: List[Tuple[float, float]] = [(ac_lat, ac_lon)]
    if s.home_set:
        pts.append((s.home_lat, s.home_lon))
    return pts


def _compute_autofit_window(
    points: List[Tuple[float, float]],
    z_ceiling: int,
) -> Optional[Tuple[int, float, float]]:
    """Pick zoom and world-px origin (top-left) so bbox of points fits in PIP."""
    if len(points) < 2:
        return None
    margin = FIT_MARGIN_PX
    inner_w = max(8.0, float(PIP_W - 2 * margin) * 0.92)
    inner_h = max(8.0, float(PIP_H - 2 * margin) * 0.92)

    xs0 = []
    ys0 = []
    for la, lo in points:
        wx, wy = _lat_lon_to_world_px(la, lo, 0)
        xs0.append(wx)
        ys0.append(wy)
    spx = max(max(xs0) - min(xs0), 1e-6)
    spy = max(max(ys0) - min(ys0), 1e-6)
    z_fit = int(math.floor(math.log2(min(inner_w / spx, inner_h / spy))))
    z = max(0, min(z_fit, min(z_ceiling, 19)))

    while z >= 0:
        xs = [_lat_lon_to_world_px(la, lo, z)[0] for la, lo in points]
        ys = [_lat_lon_to_world_px(la, lo, z)[1] for la, lo in points]
        mx, Mx = min(xs), max(xs)
        my, My = min(ys), max(ys)
        if Mx - mx <= inner_w and My - my <= inner_h:
            break
        z -= 1
    if z < 0:
        z = 0
        xs = [_lat_lon_to_world_px(la, lo, z)[0] for la, lo in points]
        ys = [_lat_lon_to_world_px(la, lo, z)[1] for la, lo in points]

    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    x0 = cx - PIP_W / 2.0
    y0 = cy - PIP_H / 2.0
    return z, x0, y0


def _lat_lon_to_world_px(lat: float, lon: float, zoom: int) -> Tuple[float, float]:
    scale = TILE_SIZE * (2**zoom)
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * scale
    return x, y


def _cache_path(cache_root: str, z: int, x: int, y: int) -> str:
    return os.path.join(cache_root, str(z), str(x), f"{y}.png")


def _cache_root_for_tile_url(base_dir: str, tile_url: str) -> str:
    """Separate on-disk tiles per URL so switching OSM ↔ Esri does not reuse wrong imagery."""
    key = hashlib.sha256(tile_url.encode("utf-8")).hexdigest()[:16]
    return os.path.join(base_dir, key)


def _fetch_tile(url: str, cache_path: str) -> Optional[bytes]:
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    if os.path.isfile(cache_path):
        with open(cache_path, "rb") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
        with open(cache_path, "wb") as f:
            f.write(data)
        return data
    except (urllib.error.URLError, OSError, TimeoutError):
        return None


def _get_heading_arrow_base() -> pygame.Surface:
    global _HEADING_ARROW_BASE
    if _HEADING_ARROW_BASE is None:
        s = pygame.Surface((24, 24), pygame.SRCALPHA)
        cx, cy = 12, 12
        pts = [(cx, cy - 9), (cx + 7, cy + 6), (cx - 7, cy + 6)]
        pygame.draw.polygon(s, colors.WHITE, pts)
        pygame.draw.polygon(s, colors.BLACK, pts, 2)
        _HEADING_ARROW_BASE = s
    return _HEADING_ARROW_BASE


def _heading_deg(h: float) -> float:
    try:
        x = float(h) % 360.0
    except (TypeError, ValueError):
        return 0.0
    if x != x:  # NaN
        return 0.0
    return x


def _clip_segment_to_pip(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Clip segment to PIP pixel rect [0, PIP_W) x [0, PIP_H). None if disjoint."""
    xmin, ymin = 0.0, 0.0
    xmax = float(PIP_W - 1)
    ymax = float(PIP_H - 1)
    dx = x1 - x0
    dy = y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0 - xmin, xmax - x0, y0 - ymin, ymax - y0)
    u1, u2 = 0.0, 1.0
    for i in range(4):
        if abs(p[i]) < 1e-18:
            if q[i] < 0:
                return None
            continue
        t = q[i] / p[i]
        if p[i] < 0:
            if t > u2:
                return None
            u1 = max(u1, t)
        else:
            if t < u1:
                return None
            u2 = min(u2, t)
    if u1 > u2 + 1e-12:
        return None
    return (
        (x0 + u1 * dx, y0 + u1 * dy),
        (x0 + u2 * dx, y0 + u2 * dy),
    )


def _draw_dotted_route(
    surf: pygame.Surface,
    p1: Tuple[float, float],
    p2: Tuple[float, float],
) -> None:
    """Light dotted line between two pixel coords (for SRCALPHA surfaces)."""
    x1, y1 = float(p1[0]), float(p1[1])
    x2, y2 = float(p2[0]), float(p2[1])
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy)
    if dist < 0.5:
        return
    ux, uy = dx / dist, dy / dist
    step = ROUTE_DOT_SPACING_PX
    t = 0.0
    while t <= dist:
        px = int(x1 + ux * t + 0.5)
        py = int(y1 + uy * t + 0.5)
        if 0 <= px < PIP_W and 0 <= py < PIP_H:
            pygame.draw.circle(surf, ROUTE_DOT_RGBA, (px, py), ROUTE_DOT_RADIUS)
        t += step


def _draw_wp_marker(
    surf: pygame.Surface,
    sx: int,
    sy: int,
    label: str,
    active: bool,
) -> None:
    r = 6
    fill = colors.YELLOW if active else colors.CYAN
    pygame.draw.circle(surf, fill, (sx, sy), r, 0)
    pygame.draw.circle(surf, colors.BLACK, (sx, sy), r, 1)
    font = get_font(10, bold=True)
    t = font.render(label, True, colors.BLACK)
    surf.blit(t, (sx - t.get_width() // 2, sy - t.get_height() // 2))


def _draw_home_h(surf: pygame.Surface, x: int, y: int) -> None:
    font = get_font(14, bold=True)
    fg = font.render("H", True, colors.WHITE)
    outline = font.render("H", True, colors.BLACK)
    w, h = fg.get_size()
    base_x = x - w // 2
    base_y = y - h // 2
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            surf.blit(outline, (base_x + dx, base_y + dy))
    surf.blit(fg, (base_x, base_y))


def _blit_tile(
    surf: pygame.Surface,
    data: Optional[bytes],
    dest_xy: Tuple[int, int],
) -> None:
    if not data:
        return
    try:
        img = pygame.image.load(io.BytesIO(data)).convert_alpha()
        img.set_alpha(MAP_TILE_ALPHA)
        surf.blit(img, dest_xy)
    except pygame.error:
        pass


class MapPipSampler(threading.Thread):
    """Builds a PIP map surface from XYZ tiles; updates slowly to stay Pi-friendly."""

    def __init__(
        self,
        state,
        zoom: int = 14,
        tile_url_template: Optional[str] = None,
    ):
        super().__init__(name="MapPipSampler", daemon=True)
        self._state = state
        # Upper bound on zoom; also caps auto-frame when HOME is set (fit uses min needed, up to this)
        self._zoom = max(0, min(zoom, 19))
        self._tile_url = tile_url_template or _DEFAULT_TILE_URL
        home = os.path.expanduser("~/.cache/pi-telem/map_tiles")
        self._cache_root = _cache_root_for_tile_url(home, self._tile_url)

        self._lock = threading.Lock()
        self._surf: Optional[pygame.Surface] = None
        self._seq = 0

        self._last_lat = 0.0
        self._last_lon = 0.0
        self._last_build_t = 0.0
        self._last_mission_v = -1

    def get_latest(self) -> Tuple[int, Optional[pygame.Surface]]:
        with self._lock:
            return self._seq, self._surf

    def _should_rebuild(self, lat: float, lon: float, s) -> bool:
        now = time.monotonic()
        if self._seq == 0 or self._last_build_t <= 0:
            return True
        if now - self._last_build_t >= SAMPLE_INTERVAL_S * 5:
            return True
        autofit = _home_autofit_enabled(s)
        if autofit and now - self._last_build_t >= AUTO_FIT_MAX_INTERVAL_S:
            return True
        min_iv = 0.55 if autofit else SAMPLE_INTERVAL_S
        if now - self._last_build_t < min_iv:
            return False
        d = _haversine(self._last_lat, self._last_lon, lat, lon)
        if autofit:
            if s.home_set:
                d_home = _haversine(lat, lon, s.home_lat, s.home_lon)
                move_thresh = (
                    AUTO_FIT_MOVE_THRESH_NEAR_M
                    if d_home < HOME_APPROACH_M
                    else AUTO_FIT_MOVE_THRESH_M
                )
            else:
                move_thresh = AUTO_FIT_MOVE_THRESH_M
        else:
            move_thresh = MOVE_THRESH_M
        return d >= move_thresh

    def _build(self, lat: float, lon: float) -> pygame.Surface:
        s = self._state.snapshot()
        if _home_autofit_enabled(s):
            pts = _collect_zoom_frame_points(s, lat, lon)
            aw = _compute_autofit_window(pts, self._zoom)
            if aw is not None:
                z, x0, y0 = aw
            else:
                z = self._zoom
                px, py = _lat_lon_to_world_px(lat, lon, z)
                x0 = px - PIP_W / 2.0
                y0 = py - PIP_H / 2.0
        else:
            z = self._zoom
            px, py = _lat_lon_to_world_px(lat, lon, z)
            x0 = px - PIP_W / 2.0
            y0 = py - PIP_H / 2.0

        out = pygame.Surface((PIP_W, PIP_H), pygame.SRCALPHA)
        out.fill(MAP_BASE_RGBA)

        tx0 = int(x0 // TILE_SIZE)
        ty0 = int(y0 // TILE_SIZE)
        tx1 = int((x0 + PIP_W) // TILE_SIZE)
        ty1 = int((y0 + PIP_H) // TILE_SIZE)
        n = 2**z

        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                txw = tx % n
                if ty < 0 or ty >= n:
                    continue
                # Templates may use {z}/{x}/{y} (OSM) or {z}/{y}/{x} (Esri, etc.)
                url = self._tile_url.format(z=z, x=txw, y=ty)
                path = _cache_path(self._cache_root, z, txw, ty)
                data = _fetch_tile(url, path)
                wx = tx * TILE_SIZE
                wy = ty * TILE_SIZE
                dx = int(wx - x0)
                dy = int(wy - y0)
                _blit_tile(out, data, (dx, dy))

        heading = _heading_deg(s.heading)

        def _proj_f(llat: float, llon: float) -> Tuple[float, float]:
            wx, wy = _lat_lon_to_world_px(llat, llon, z)
            return (wx - x0, wy - y0)

        def _proj(llat: float, llon: float) -> Optional[Tuple[int, int]]:
            fx, fy = _proj_f(llat, llon)
            sx = int(fx)
            sy = int(fy)
            if 0 <= sx < PIP_W and 0 <= sy < PIP_H:
                return sx, sy
            return None

        # Mission route: clip segments to PIP so paths show through map when WPs are off-screen
        wps = s.mission_wps
        for i in range(len(wps) - 1):
            a, b = wps[i], wps[i + 1]
            if a is None or b is None:
                continue
            ax, ay = _proj_f(a[0], a[1])
            bx, by = _proj_f(b[0], b[1])
            clipped = _clip_segment_to_pip(ax, ay, bx, by)
            if clipped is not None:
                (p0, p1) = clipped
                _draw_dotted_route(out, p0, p1)

        # Mission waypoints (HOME is drawn after so it stacks on top)
        cur = int(s.wp_seq) if s.wp_seq >= 0 else -1
        for seq, pt in enumerate(s.mission_wps):
            if pt is None:
                continue
            wlat, wlon = pt
            wpix = _proj(wlat, wlon)
            if wpix is None:
                continue
            _draw_wp_marker(
                out,
                wpix[0],
                wpix[1],
                str(seq),
                active=(seq == cur),
            )

        # HOME on top of waypoints
        if s.home_set and abs(s.home_lat) + abs(s.home_lon) > 1e-9:
            hp = _proj(s.home_lat, s.home_lon)
            if hp is not None:
                _draw_home_h(out, hp[0], hp[1])

        # Ownship: arrow aligned with heading (deg clockwise from north, north-up map)
        ac = _proj(lat, lon)
        if ac is not None:
            base = _get_heading_arrow_base()
            rot = pygame.transform.rotate(base, -heading)
            r = rot.get_rect(center=ac)
            out.blit(rot, r.topleft)

        return out

    def run(self) -> None:
        while True:
            time.sleep(0.2)
            try:
                s = self._state.snapshot()
                lat, lon = s.lat, s.lon
                if abs(lat) < 1e-8 and abs(lon) < 1e-8:
                    continue
                mv = s.mission_version
                if not self._should_rebuild(lat, lon, s) and mv == self._last_mission_v:
                    continue
                surf = self._build(lat, lon)
                with self._lock:
                    self._surf = surf
                    self._seq += 1
                self._last_lat = lat
                self._last_lon = lon
                self._last_build_t = time.monotonic()
                self._last_mission_v = mv
            except Exception:
                time.sleep(2.0)  # backoff on tile / pygame errors
