import pygame

from hud import colors
from hud.fonts import get_font

TICK_SPACING_PX = 20   # pixels per m/s
MAJOR_INTERVAL = 10    # major tick every N m/s
MINOR_INTERVAL = 5


def draw(surface: pygame.Surface, rect: pygame.Rect,
         airspeed: float, groundspeed: float):
    """Draw a scrolling speed tape on the left side of the HUD."""
    speed = airspeed
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    cx = x + w // 2
    cy = y + h // 2

    clip_prev = surface.get_clip()
    surface.set_clip(rect)

    # Background
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    bg.fill((20, 20, 20, 180))
    surface.blit(bg, (x, y))

    font = get_font(14)
    font_sm = get_font(11)

    # Scrolling ticks
    pixels_per_unit = TICK_SPACING_PX
    speed_range = h // pixels_per_unit + 4
    base = int(speed)

    for i in range(-speed_range, speed_range + 1):
        val = base + i
        if val < 0:
            continue
        offset = (speed - val) * pixels_per_unit
        ty = int(cy + offset)

        if ty < y - 10 or ty > y + h + 10:
            continue

        if val % MAJOR_INTERVAL == 0:
            pygame.draw.line(surface, colors.WHITE,
                             (x + w - 20, ty), (x + w, ty), 2)
            lbl = font.render(f"{val:3.0f}", True, colors.WHITE)
            surface.blit(lbl, (x + w - 22 - lbl.get_width(), ty - lbl.get_height() // 2))
        elif val % MINOR_INTERVAL == 0:
            pygame.draw.line(surface, colors.GREY,
                             (x + w - 10, ty), (x + w, ty), 1)

    # Current value box
    box_h = 24
    box_w = w - 4
    box_rect = pygame.Rect(x + 2, cy - box_h // 2, box_w, box_h)
    pygame.draw.rect(surface, colors.BLACK, box_rect)
    pygame.draw.rect(surface, colors.GREEN, box_rect, 2)

    spd_text = font.render(f"{speed:5.1f}", True, colors.GREEN)
    surface.blit(spd_text, (box_rect.x + box_rect.width - spd_text.get_width() - 4,
                            box_rect.centery - spd_text.get_height() // 2))

    # Label at top
    label = font_sm.render("IAS m/s", True, colors.CYAN)
    surface.blit(label, (x + (w - label.get_width()) // 2, y + 2))

    surface.set_clip(clip_prev)
