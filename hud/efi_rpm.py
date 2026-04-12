"""EFI RPM readout (EFI_STATUS), bottom bar right."""

import pygame

from hud import colors
from hud.fonts import get_font


def draw(surface: pygame.Surface, rect: pygame.Rect, rpm: float) -> None:
    """Draw RPM in the bottom strip (right of messages)."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    bg.fill((20, 20, 20, 200))
    surface.blit(bg, (x, y))

    font = get_font(14)
    ty = y + (h - font.get_height()) // 2

    if rpm >= 0.0:
        text = f"RPM {rpm:.0f}"
        color = colors.WHITE
    else:
        text = "RPM ---"
        color = colors.GREY

    surf = font.render(text, True, color)
    surface.blit(surf, (x + (w - surf.get_width()) // 2, ty))
