import time
from typing import List, Tuple

import pygame

from hud import colors
from hud.fonts import get_font

MESSAGE_DISPLAY_SEC = 30


def draw(surface: pygame.Surface, rect: pygame.Rect,
         messages: List[Tuple[float, str]]):
    """Draw the most recent STATUSTEXT messages in the bottom panel."""
    x, y, w, h = rect.x, rect.y, rect.width, rect.height
    font = get_font(13)
    pad = 6

    now = time.time()
    recent = [m for m in messages if now - m[0] < MESSAGE_DISPLAY_SEC]

    line_h = font.get_height() + 2
    max_lines = max(1, h // line_h)
    shown = recent[-max_lines:]

    ty = y + pad
    for ts, text in shown:
        age = now - ts
        if age < 5:
            color = colors.GREEN
        elif age < 15:
            color = colors.WHITE
        else:
            color = colors.GREY

        # Truncate to fit width
        rendered = font.render(text, True, color)
        if rendered.get_width() > w - pad * 2:
            while len(text) > 3 and font.size(text + "...")[0] > w - pad * 2:
                text = text[:-1]
            rendered = font.render(text + "...", True, color)

        surface.blit(rendered, (x + pad, ty))
        ty += line_h
