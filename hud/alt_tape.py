import pygame

from hud import colors
from hud.fonts import get_font

TICK_SPACING_PX = 3    # pixels per metre
MAJOR_INTERVAL = 10    # major tick every N metres
MINOR_INTERVAL = 5


def draw(surface: pygame.Surface, rect: pygame.Rect, altitude: float,
         label: str = "REL m", color_accent=None):
    """Draw a scrolling altitude tape. label/color_accent let it serve as REL or MSL."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    cx = x + w // 2
    cy = y + h // 2

    clip_prev = surface.get_clip()
    surface.set_clip(rect)

    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    bg.fill((20, 20, 20, 180))
    surface.blit(bg, (x, y))

    font = get_font(14)
    font_sm = get_font(11)

    pixels_per_unit = TICK_SPACING_PX
    alt_range = h // pixels_per_unit + 20
    base = int(altitude)

    for i in range(-alt_range, alt_range + 1):
        val = base + i
        offset = (altitude - val) * pixels_per_unit
        ty = int(cy + offset)

        if ty < y - 10 or ty > y + h + 10:
            continue

        if val % MAJOR_INTERVAL == 0:
            pygame.draw.line(surface, colors.WHITE,
                             (x, ty), (x + 20, ty), 2)
            lbl = font.render(f"{val:4.0f}", True, colors.WHITE)
            surface.blit(lbl, (x + 22, ty - lbl.get_height() // 2))
        elif val % MINOR_INTERVAL == 0:
            pygame.draw.line(surface, colors.GREY,
                             (x, ty), (x + 10, ty), 1)

    # Current value box
    acc = color_accent or colors.GREEN
    box_h = 24
    box_w = w - 4
    box_rect = pygame.Rect(x + 2, cy - box_h // 2, box_w, box_h)
    pygame.draw.rect(surface, colors.BLACK, box_rect)
    pygame.draw.rect(surface, acc, box_rect, 2)

    alt_text = font.render(f"{altitude:6.1f}", True, acc)
    surface.blit(alt_text, (box_rect.x + 4,
                            box_rect.centery - alt_text.get_height() // 2))

    # Label at top
    lbl_surf = font_sm.render(label, True, colors.CYAN)
    surface.blit(lbl_surf, (x + (w - lbl_surf.get_width()) // 2, y + 2))

    surface.set_clip(clip_prev)
