import math

import pygame

from hud import colors
from hud.fonts import get_font

EARTH_R = 6371000.0  # metres


def _haversine(lat1, lon1, lat2, lon2):
    """Return distance in metres between two lat/lon points (degrees)."""
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1, lon1, lat2, lon2):
    """Return bearing in degrees from point 1 to point 2."""
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _fmt_dist(metres):
    """Compact for narrow strip: "k" not "km", integer metres when sensible."""
    if metres >= 1000:
        return f"{metres / 1000:.1f}k"
    return f"{int(round(metres))}m"


def _render_fit_width(text: str, color, max_w: int, sizes: tuple = (10, 9, 8, 7)):
    """Pick largest font that fits ``max_w`` px (Dejavu mono widths)."""
    for sz in sizes:
        font = get_font(sz)
        surf = font.render(text, True, color)
        if surf.get_width() <= max_w:
            return surf, font
    font = get_font(sizes[-1])
    return font.render(text, True, color), font


def draw(surface: pygame.Surface, rect: pygame.Rect, state):
    """Draw HOME distance and bearing in the left strip (width ``rect``); clipped to divider."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    pad = max(2, min(4, w // 16))
    max_w = max(8, w - 2 * pad)

    clip_prev = surface.get_clip()
    surface.set_clip(rect)

    if state.home_set and (state.lat != 0.0 or state.lon != 0.0):
        dist = _haversine(state.lat, state.lon, state.home_lat, state.home_lon)
        brg = _bearing(state.lat, state.lon, state.home_lat, state.home_lon)
        # Short label + compact dist; "H" prefix saves width vs "HOME"
        line1 = f"H {_fmt_dist(dist)}"
        line2 = f"{brg:03.0f}\u00b0"
        s1, _ = _render_fit_width(line1, colors.WHITE, max_w)
        s2, _ = _render_fit_width(line2, colors.WHITE, max_w)
        gap = 1
        total_h = s1.get_height() + gap + s2.get_height()
        y0 = y + (h - total_h) // 2
        surface.blit(s1, (x + pad, y0))
        surface.blit(s2, (x + pad, y0 + s1.get_height() + gap))
    else:
        surf, _ = _render_fit_width("H ---", colors.GREY, max_w)
        surface.blit(surf, (x + pad, y + (h - surf.get_height()) // 2))

    surface.set_clip(clip_prev)
