import time

import pygame

from hud import colors
from hud.fonts import get_font

GPS_FIX_NAMES = {0: "No GPS", 1: "No Fix", 2: "2D", 3: "3D",
                 4: "DGPS", 5: "RTK Float", 6: "RTK Fix"}


def draw(surface: pygame.Surface, rect: pygame.Rect, state):
    """Draw the top status bar with mode, arm, GPS, and UTC time."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height

    pygame.draw.rect(surface, colors.PANEL_BG, rect)
    pygame.draw.line(surface, colors.GREY, (x, y + h - 1), (x + w, y + h - 1), 1)

    font = get_font(16, bold=True)
    font_sm = get_font(13)
    pad = 8
    ty = y + (h - font.get_height()) // 2

    cursor_x = x + pad

    # Flight mode
    mode_surf = font.render(state.flight_mode, True, colors.CYAN)
    surface.blit(mode_surf, (cursor_x, ty))
    cursor_x += mode_surf.get_width() + pad * 3

    # Armed status
    arm_text = "ARMED" if state.armed else "DISARMED"
    arm_color = colors.ARMED_COLOR if state.armed else colors.DISARMED_COLOR
    arm_surf = font.render(arm_text, True, arm_color)
    surface.blit(arm_surf, (cursor_x, ty))
    cursor_x += arm_surf.get_width() + pad * 3

    # Connection indicator
    if not state.connected:
        conn_surf = font_sm.render("NO LINK", True, colors.RED)
        surface.blit(conn_surf, (cursor_x, ty + 2))
        cursor_x += conn_surf.get_width() + pad * 3

    # Right-aligned items
    right_x = x + w - pad

    # UTC time
    utc_str = time.strftime("%H:%M:%S", time.gmtime())
    utc_surf = font_sm.render(f"UTC {utc_str}", True, colors.WHITE)
    right_x -= utc_surf.get_width()
    surface.blit(utc_surf, (right_x, ty + 2))
    right_x -= pad * 3

    # GPS
    fix_name = GPS_FIX_NAMES.get(state.gps_fix, f"Fix:{state.gps_fix}")
    gps_color = colors.GPS_GOOD if state.gps_fix >= 3 else colors.GPS_BAD
    gps_text = f"GPS:{fix_name} {state.gps_sats}sat"
    gps_surf = font_sm.render(gps_text, True, gps_color)
    right_x -= gps_surf.get_width()
    surface.blit(gps_surf, (right_x, ty + 2))
