import pygame

_cache = {}


def get_font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _cache:
        font = pygame.font.SysFont("dejavusansmono", size, bold=bold)
        _cache[key] = font
    return _cache[key]


def init():
    """Call after pygame.init() to ensure the font system is ready."""
    pygame.font.init()
