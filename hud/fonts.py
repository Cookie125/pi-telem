import os

import pygame

# Avoid pygame.sysfont / fc-list on boot (slow SD cards; systemd has minimal env).
_DEJAVU_DIR = "/usr/share/fonts/truetype/dejavu"
_DEJAVU = os.path.join(_DEJAVU_DIR, "DejaVuSansMono.ttf")
_DEJAVU_BOLD = os.path.join(_DEJAVU_DIR, "DejaVuSansMono-Bold.ttf")

_cache = {}


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _cache:
        path = _DEJAVU_BOLD if bold else _DEJAVU
        if os.path.isfile(path):
            font = pygame.font.Font(path, size)
        else:
            font = pygame.font.SysFont("dejavusansmono", size, bold=bold)
        _cache[key] = font
    return _cache[key]


def init():
    """Call after pygame.init() to ensure the font system is ready."""
    pygame.font.init()
