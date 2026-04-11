import math

import pygame

from hud import colors
from hud.fonts import get_font


def draw(surface: pygame.Surface, rect: pygame.Rect,
         wind_dir: float, wind_speed: float, heading: float,
         wind_valid: bool):
    """Draw a G1000-style wind indicator: arrow showing direction wind is
    coming FROM (relative to aircraft heading) plus speed readout."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    cx = x + w // 2
    cy = y + h // 2

    font = get_font(13)
    font_sm = get_font(11)

    if not wind_valid:
        lbl = font_sm.render("WIND ---", True, colors.GREY)
        surface.blit(lbl, (cx - lbl.get_width() // 2, cy - lbl.get_height() // 2))
        return

    # Arrow radius fits inside the rect with room for text
    text_h = font.get_height() + 4
    arrow_r = min(w, h - text_h * 2) // 2 - 4
    arrow_r = max(arrow_r, 12)

    # Wind direction relative to heading (rotate so top = nose of aircraft)
    # wind_dir is where wind comes FROM in earth frame
    rel_angle_deg = (wind_dir - heading + 180) % 360
    rel_angle = math.radians(rel_angle_deg)

    # Arrow tip (where wind is coming from, relative)
    tip_x = cx + int(arrow_r * math.sin(rel_angle))
    tip_y = cy - int(arrow_r * math.cos(rel_angle))

    # Arrow tail (opposite side)
    tail_x = cx - int(arrow_r * math.sin(rel_angle))
    tail_y = cy + int(arrow_r * math.cos(rel_angle))

    # Draw shaft
    pygame.draw.line(surface, colors.CYAN, (tail_x, tail_y), (tip_x, tip_y), 2)

    # Arrowhead at tip
    head_len = 10
    head_angle = math.radians(25)
    for sign in (-1, 1):
        a = rel_angle + math.pi + sign * head_angle
        hx = tip_x + int(head_len * math.sin(a))
        hy = tip_y - int(head_len * math.cos(a))
        pygame.draw.line(surface, colors.CYAN, (tip_x, tip_y), (hx, hy), 2)

    # Small circle at center representing aircraft
    pygame.draw.circle(surface, colors.WHITE, (cx, cy), 3, 1)

    # Speed text below the arrow area
    spd_text = font.render(f"{wind_speed:.0f}m/s", True, colors.CYAN)
    surface.blit(spd_text, (cx - spd_text.get_width() // 2,
                            y + h - text_h))

    # Direction text above the arrow area
    dir_text = font_sm.render(f"{wind_dir:03.0f}\u00b0", True, colors.CYAN)
    surface.blit(dir_text, (cx - dir_text.get_width() // 2, y + 2))
