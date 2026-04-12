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
    if metres >= 1000:
        return f"{metres / 1000:.1f}km"
    return f"{metres:.0f}m"


def draw(surface: pygame.Surface, rect: pygame.Rect, state):
    """Draw HOME distance and bearing in the left strip (width ``rect``); clipped to divider."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    font = get_font(12)
    pad = min(8, max(4, w // 12))

    clip_prev = surface.get_clip()
    surface.set_clip(rect)

    if state.home_set and (state.lat != 0.0 or state.lon != 0.0):
        dist = _haversine(state.lat, state.lon, state.home_lat, state.home_lon)
        brg = _bearing(state.lat, state.lon, state.home_lat, state.home_lon)
        # Two lines: distance and bearing stay inside narrow strip by speed-tape divider
        line1 = f"HOME {_fmt_dist(dist)}"
        line2 = f"{brg:03.0f}\u00b0"
        s1 = font.render(line1, True, colors.WHITE)
        s2 = font.render(line2, True, colors.WHITE)
        gap = 1
        total_h = s1.get_height() + gap + s2.get_height()
        y0 = y + (h - total_h) // 2
        surface.blit(s1, (x + pad, y0))
        surface.blit(s2, (x + pad, y0 + s1.get_height() + gap))
    else:
        surf = font.render("HOME ---", True, colors.GREY)
        surface.blit(surf, (x + pad, y + (h - surf.get_height()) // 2))

    surface.set_clip(clip_prev)
