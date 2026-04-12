import pygame

from hud import colors
from hud.fonts import get_font

TICK_SPACING_PX = 20   # pixels per m/s
MAJOR_INTERVAL = 10    # major tick every N m/s
MINOR_INTERVAL = 5

# 800x480 / ~7": compact title strip (matches alt_tape rhythm)
LABEL_BAND_H = 20


def draw(surface: pygame.Surface, rect: pygame.Rect,
         airspeed: float, groundspeed: float):
    """Draw a scrolling speed tape on the left side of the HUD."""
    speed = airspeed
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    acc = colors.GREEN

    font = get_font(11)
    font_sm = get_font(9)

    label_h = LABEL_BAND_H if h > LABEL_BAND_H + 48 else 0
    body_y = y + label_h
    body_h = h - label_h
    if body_h < 40:
        label_h = 0
        body_y = y
        body_h = h

    cy = body_y + body_h // 2

    clip_prev = surface.get_clip()

    if label_h > 0:
        band = pygame.Rect(x, y, w, label_h)
        pygame.draw.rect(surface, colors.PANEL_BG, band)
        pygame.draw.rect(surface, acc, band, 2)
        title = font_sm.render("IAS m/s", True, acc)
        surface.blit(
            title,
            (x + (w - title.get_width()) // 2,
             y + (label_h - title.get_height()) // 2),
        )

    body = pygame.Rect(x, body_y, w, body_h)
    surface.set_clip(body)

    bg = pygame.Surface((w, body_h), pygame.SRCALPHA)
    bg.fill((20, 20, 20, 180))
    surface.blit(bg, (body.x, body.y))

    # Major tick length scales down with narrow tapes
    tick_major = max(6, min(12, w // 4))
    tick_minor = max(4, min(8, w // 6))

    pixels_per_unit = TICK_SPACING_PX
    speed_range = body_h // pixels_per_unit + 4
    base = int(speed)

    for i in range(-speed_range, speed_range + 1):
        val = base + i
        if val < 0:
            continue
        offset = (speed - val) * pixels_per_unit
        ty = int(cy + offset)

        if ty < body_y - 10 or ty > body_y + body_h + 10:
            continue

        if val % MAJOR_INTERVAL == 0:
            x0 = x + w - tick_major
            pygame.draw.line(surface, colors.WHITE, (x0, ty), (x + w, ty), 2)
            lbl = font.render(f"{val:.0f}", True, colors.WHITE)
            lx = x0 - 2 - lbl.get_width()
            surface.blit(lbl, (lx, ty - lbl.get_height() // 2))
        elif val % MINOR_INTERVAL == 0:
            x0 = x + w - tick_minor
            pygame.draw.line(surface, colors.GREY, (x0, ty), (x + w, ty), 1)

    box_h = 20
    box_w = w - 4
    box_rect = pygame.Rect(x + 2, cy - box_h // 2, box_w, box_h)
    pygame.draw.rect(surface, colors.BLACK, box_rect)
    pygame.draw.rect(surface, acc, box_rect, 2)

    spd_text = font.render(f"{speed:4.1f}", True, acc)
    surface.blit(
        spd_text,
        (box_rect.x + box_rect.width - spd_text.get_width() - 3,
         box_rect.centery - spd_text.get_height() // 2),
    )

    surface.set_clip(clip_prev)
