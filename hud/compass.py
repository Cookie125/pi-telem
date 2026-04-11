import pygame

from hud import colors
from hud.fonts import get_font

CARDINAL = {0: "N", 45: "NE", 90: "E", 135: "SE",
            180: "S", 225: "SW", 270: "W", 315: "NW", 360: "N"}

PIXELS_PER_DEG = 3


def draw(surface: pygame.Surface, rect: pygame.Rect, heading: float,
         home_bearing: float = None):
    """Draw a horizontal compass ribbon with heading indicator and optional home marker."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    cx = x + w // 2
    cy = y + h // 2

    clip_prev = surface.get_clip()
    surface.set_clip(rect)

    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    bg.fill((20, 20, 20, 200))
    surface.blit(bg, (x, y))

    font = get_font(14)
    font_sm = get_font(11)
    font_lg = get_font(16, bold=True)

    # Scrolling ribbon
    visible_range = w // PIXELS_PER_DEG + 20
    for deg_offset in range(-visible_range // 2, visible_range // 2 + 1):
        deg = (int(heading) + deg_offset) % 360
        px = cx + int((deg_offset - (heading - int(heading))) * PIXELS_PER_DEG)

        if px < x - 20 or px > x + w + 20:
            continue

        if deg % 10 == 0:
            tick_h = 8 if deg % 30 == 0 else 4
            pygame.draw.line(surface, colors.WHITE,
                             (px, y + h - tick_h), (px, y + h), 2)

        if deg % 30 == 0:
            lbl_text = CARDINAL.get(deg, f"{deg}")
            color = colors.CYAN if deg in CARDINAL else colors.WHITE
            lbl = font_sm.render(lbl_text, True, color)
            surface.blit(lbl, (px - lbl.get_width() // 2, y + h - 10 - lbl.get_height()))

    # Home bearing marker
    if home_bearing is not None:
        delta = (home_bearing - heading + 180) % 360 - 180
        hpx = cx + int(delta * PIXELS_PER_DEG)
        if x - 5 <= hpx <= x + w + 5:
            # Draw a house icon: triangle roof + rectangle body
            size = 9
            hm_y = y + h - size * 4
            pygame.draw.polygon(surface, colors.ORANGE,
                                [(hpx, hm_y),
                                 (hpx - size, hm_y + size),
                                 (hpx + size, hm_y + size)])
            pygame.draw.rect(surface, colors.ORANGE,
                             (hpx - size + 2, hm_y + size, size * 2 - 4, size + 2))
            lbl = font.render("H", True, colors.BLACK)
            surface.blit(lbl, (hpx - lbl.get_width() // 2, hm_y + size - 1))

    # Center pointer triangle
    tri_y = y + h
    tri_size = 6
    pygame.draw.polygon(surface, colors.GREEN,
                        [(cx, tri_y - tri_size * 2),
                         (cx - tri_size, tri_y),
                         (cx + tri_size, tri_y)])

    # Heading readout
    hdg_text = font_lg.render(f"{heading:03.0f}\u00b0", True, colors.GREEN)
    surface.blit(hdg_text, (cx - hdg_text.get_width() // 2, y + 2))

    surface.set_clip(clip_prev)
