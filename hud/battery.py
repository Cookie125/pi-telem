import pygame

from hud import colors
from hud.fonts import get_font


def content_width(
    voltage: float,
    current: float,
    remaining: int,
    fuel_remaining: int = -1,
) -> int:
    """Total pixel width for the battery row (matches ``draw`` spacing), including padding."""
    font = get_font(14)
    pad = 6
    pad_v_to_a = 2
    w = pad
    w += font.size(f"{voltage:5.1f}V")[0] + pad_v_to_a
    w += font.size(f"{current:5.1f}A")[0] + pad * 2
    if remaining >= 0:
        pct_text = f"{remaining}%"
    else:
        pct_text = "--%"
    w += font.size(pct_text)[0] + pad * 2
    w += font.size("Fuel: ")[0]
    if fuel_remaining >= 0:
        fuel_text = f"{fuel_remaining}%"
    else:
        fuel_text = "--%"
    w += font.size(fuel_text)[0]
    w += pad
    return w


def _bat_color(remaining: int) -> tuple:
    if remaining < 0:
        return colors.GREY
    if remaining <= 15:
        return colors.BAT_CRIT
    if remaining <= 30:
        return colors.BAT_WARN
    return colors.BAT_GOOD


def draw(surface: pygame.Surface, rect: pygame.Rect,
         voltage: float, current: float, remaining: int,
         fuel_remaining: int = -1):
    """Draw battery 1 (V, A, %), then Fuel: from battery 2 %, in the bottom bar."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    font = get_font(14)
    pad = 6
    pad_v_to_a = 2  # keep amps snug to volts to leave room for Fuel:
    ty = y + (h - font.get_height()) // 2

    color = _bat_color(remaining)
    cursor_x = x + pad

    # Voltage
    v_surf = font.render(f"{voltage:5.1f}V", True, color)
    surface.blit(v_surf, (cursor_x, ty))
    cursor_x += v_surf.get_width() + pad_v_to_a

    # Current
    c_surf = font.render(f"{current:5.1f}A", True, color)
    surface.blit(c_surf, (cursor_x, ty))
    cursor_x += c_surf.get_width() + pad * 2

    # Remaining (battery 1)
    if remaining >= 0:
        pct_text = f"{remaining}%"
    else:
        pct_text = "--%"
    p_surf = font.render(pct_text, True, color)
    surface.blit(p_surf, (cursor_x, ty))
    cursor_x += p_surf.get_width() + pad * 2

    # Fuel: battery 2 % (red — distinct from batt 1; saves horizontal vs colored ramp)
    fuel_red = colors.RED
    label_surf = font.render("Fuel: ", True, fuel_red)
    surface.blit(label_surf, (cursor_x, ty))
    cursor_x += label_surf.get_width()
    if fuel_remaining >= 0:
        fuel_text = f"{fuel_remaining}%"
    else:
        fuel_text = "--%"
    fuel_surf = font.render(fuel_text, True, fuel_red)
    surface.blit(fuel_surf, (cursor_x, ty))
