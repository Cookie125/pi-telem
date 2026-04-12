import math

import pygame

from hud import colors
from hud.fonts import get_font


def draw(surface: pygame.Surface, rect: pygame.Rect,
         wind_dir: float, wind_speed: float, heading: float,
         wind_valid: bool):
    """Wind strip: wind FROM (deg) left, relative arrow center, speed right."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    pad = 3

    font = get_font(12)
    font_sm = get_font(11)

    if not wind_valid:
        lbl = font_sm.render("WIND —", True, colors.GREY)
        surface.blit(
            lbl,
            (x + (w - lbl.get_width()) // 2, y + (h - lbl.get_height()) // 2),
        )
        return

    dir_surf = font_sm.render(f"{wind_dir:03.0f}°", True, colors.CYAN)
    spd_surf = font.render(f"{wind_speed:.0f}m/s", True, colors.CYAN)

    left_x = x + pad
    spd_w = spd_surf.get_width()
    right_x = x + w - pad - spd_w

    ty_dir = y + (h - dir_surf.get_height()) // 2
    ty_spd = y + (h - spd_surf.get_height()) // 2
    surface.blit(dir_surf, (left_x, ty_dir))
    surface.blit(spd_surf, (right_x, ty_spd))

    mid_left = left_x + dir_surf.get_width() + 4
    mid_right = right_x - 4
    cx = (mid_left + mid_right) // 2
    cy = y + h // 2

    avail = max(0, (mid_right - mid_left) // 2)
    arrow_r = max(5, min(avail - 1, h // 2 - 4))

    rel_angle_deg = (wind_dir - heading + 180) % 360
    rel_angle = math.radians(rel_angle_deg)

    tip_x = cx + int(arrow_r * math.sin(rel_angle))
    tip_y = cy - int(arrow_r * math.cos(rel_angle))
    tail_x = cx - int(arrow_r * math.sin(rel_angle))
    tail_y = cy + int(arrow_r * math.cos(rel_angle))

    pygame.draw.line(surface, colors.CYAN, (tail_x, tail_y), (tip_x, tip_y), 2)

    head_len = min(8, arrow_r)
    head_angle = math.radians(25)
    for sign in (-1, 1):
        a = rel_angle + math.pi + sign * head_angle
        hx = tip_x + int(head_len * math.sin(a))
        hy = tip_y - int(head_len * math.cos(a))
        pygame.draw.line(surface, colors.CYAN, (tip_x, tip_y), (hx, hy), 2)

    pygame.draw.circle(surface, colors.WHITE, (cx, cy), 2, 1)
