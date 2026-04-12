import pygame

from hud import colors
from hud import wind
from hud.fonts import get_font

# Wind strip to the left of GPS (direction | arrow | speed)
WIND_STRIP_W = 178
WIND_GPS_GAP = 10

GPS_FIX_NAMES = {0: "No GPS", 1: "No Fix", 2: "2D", 3: "3D",
                 4: "DGPS", 5: "RTK Float", 6: "RTK Fix"}


def draw(surface: pygame.Surface, rect: pygame.Rect, state):
    """Draw the top status bar with mode, arm, GPS, and link status."""
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

    # Waypoint: current/total (MISSION_CURRENT) and distance (NAV_CONTROLLER_OUTPUT)
    _seq = state.wp_seq
    if state.wp_total > 0 and 0 <= _seq < 65530:
        cur = _seq  # MISSION_CURRENT.seq (0-based; same as FC / MAVLink)
        d = state.wp_dist_m
        if 0.0 <= d < 65000.0:
            wp_text = f"WP: {cur}/{state.wp_total} {d:.0f}m"
        else:
            wp_text = f"WP: {cur}/{state.wp_total}"
        wp_surf = font_sm.render(wp_text, True, colors.WHITE)
        surface.blit(wp_surf, (cursor_x, ty + 2))
        cursor_x += wp_surf.get_width() + pad * 3

    # Connection indicator
    if not state.connected:
        conn_surf = font_sm.render("NO LINK", True, colors.RED)
        surface.blit(conn_surf, (cursor_x, ty + 2))
        cursor_x += conn_surf.get_width() + pad * 3

    # Right-aligned: wind (direction / arrow / speed) then GPS
    right_x = x + w - pad

    fix_name = GPS_FIX_NAMES.get(state.gps_fix, f"Fix:{state.gps_fix}")
    gps_color = colors.GPS_GOOD if state.gps_fix >= 3 else colors.GPS_BAD
    gps_text = f"GPS:{fix_name} {state.gps_sats}sat"
    gps_surf = font_sm.render(gps_text, True, gps_color)
    gps_w = gps_surf.get_width()

    right_x -= gps_w
    gps_left = right_x
    right_x -= WIND_GPS_GAP + WIND_STRIP_W
    wind_left = right_x

    wind_rect = pygame.Rect(wind_left, y + 2, WIND_STRIP_W, h - 4)
    wind.draw(
        surface,
        wind_rect,
        state.wind_dir,
        state.wind_speed,
        state.heading,
        state.wind_valid,
    )

    surface.blit(gps_surf, (gps_left, ty + 2))
