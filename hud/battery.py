import pygame

from hud import colors
from hud.fonts import get_font


def _bat_color(remaining: int) -> tuple:
    if remaining < 0:
        return colors.GREY
    if remaining <= 15:
        return colors.BAT_CRIT
    if remaining <= 30:
        return colors.BAT_WARN
    return colors.BAT_GOOD


def draw(surface: pygame.Surface, rect: pygame.Rect,
         voltage: float, current: float, remaining: int):
    """Draw battery voltage, current, and remaining % in the bottom bar."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    font = get_font(14)
    pad = 6
    ty = y + (h - font.get_height()) // 2

    color = _bat_color(remaining)
    cursor_x = x + pad

    # Voltage
    v_surf = font.render(f"{voltage:5.1f}V", True, color)
    surface.blit(v_surf, (cursor_x, ty))
    cursor_x += v_surf.get_width() + pad * 2

    # Current
    c_surf = font.render(f"{current:5.1f}A", True, color)
    surface.blit(c_surf, (cursor_x, ty))
    cursor_x += c_surf.get_width() + pad * 2

    # Remaining
    if remaining >= 0:
        pct_text = f"{remaining}%"
    else:
        pct_text = "--%"
    p_surf = font.render(pct_text, True, color)
    surface.blit(p_surf, (cursor_x, ty))
