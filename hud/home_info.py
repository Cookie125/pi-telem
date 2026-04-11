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
    """Draw home distance, bearing, and vertical speed in the info bar."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    font = get_font(14)
    pad = 8
    ty = y + (h - font.get_height()) // 2

    # Home distance and bearing
    if state.home_set and (state.lat != 0.0 or state.lon != 0.0):
        dist = _haversine(state.lat, state.lon, state.home_lat, state.home_lon)
        brg = _bearing(state.lat, state.lon, state.home_lat, state.home_lon)
        text = f"HOME {_fmt_dist(dist)} {brg:03.0f}\u00b0"
        color = colors.WHITE
    else:
        text = "HOME ---"
        color = colors.GREY

    surf = font.render(text, True, color)
    surface.blit(surf, (x + pad, ty))
