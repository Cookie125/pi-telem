import pygame

from hud import colors
from hud.fonts import get_font

TICK_SPACING_PX = 3    # pixels per metre
MAJOR_INTERVAL = 10    # major tick every N metres
MINOR_INTERVAL = 5

# 800x480 / ~7": title strip above scrolling tape
LABEL_BAND_H = 20


def draw(surface: pygame.Surface, rect: pygame.Rect, altitude: float,
         label: str = "REL m", color_accent=None):
    """Draw a scrolling altitude tape. label/color_accent let it serve as REL or MSL."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    acc = color_accent or colors.GREEN

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
        title = font_sm.render(label, True, acc)
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

    tick_major = max(5, min(10, w // 4))
    tick_minor = max(3, min(6, w // 7))

    pixels_per_unit = TICK_SPACING_PX
    alt_range = body_h // pixels_per_unit + 20
    base = int(altitude)

    for i in range(-alt_range, alt_range + 1):
        val = base + i
        offset = (altitude - val) * pixels_per_unit
        ty = int(cy + offset)

        if ty < body_y - 10 or ty > body_y + body_h + 10:
            continue

        if val % MAJOR_INTERVAL == 0:
            pygame.draw.line(surface, acc, (x, ty), (x + tick_major, ty), 2)
            lbl = font.render(f"{val:.0f}", True, acc)
            surface.blit(lbl, (x + tick_major + 1, ty - lbl.get_height() // 2))
        elif val % MINOR_INTERVAL == 0:
            pygame.draw.line(
                surface, colors.GREY, (x, ty), (x + tick_minor, ty), 1,
            )

    box_h = 20
    box_w = w - 4
    box_rect = pygame.Rect(x + 2, cy - box_h // 2, box_w, box_h)
    pygame.draw.rect(surface, colors.BLACK, box_rect)
    pygame.draw.rect(surface, acc, box_rect, 2)

    alt_text = font.render(str(int(round(altitude))), True, acc)
    surface.blit(
        alt_text,
        (box_rect.x + 3, box_rect.centery - alt_text.get_height() // 2),
    )

    surface.set_clip(clip_prev)
