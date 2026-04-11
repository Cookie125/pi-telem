import math

import pygame

from hud import colors
from hud.fonts import get_font

# Pixels per degree of pitch on the horizon
PPD = 4.0


def work_surface_diag(w: int, h: int) -> int:
    """Side length of the square work surface drawn before roll rotation.

    Terrain must be rendered at (diag, diag) with the same value so it fills this
    entire square; otherwise centered (w,h) terrain leaves side margins that show
    only the base fill and look empty at the HUD edges when rolled.
    """
    return int(math.hypot(w, h)) + 60


def draw(surface: pygame.Surface, rect: pygame.Rect, roll: float, pitch: float,
         terrain_surface: pygame.Surface = None):
    """Draw artificial horizon with pitch ladder and roll indicator.

    roll / pitch are in radians (from ATTITUDE message).
    terrain_surface: optional pre-rendered SVS surface.  Should be
                     (work_surface_diag(w,h), work_surface_diag(w,h)) so it covers
                     the full prerotation square; horizon aligns it with pitch.
    """
    cx, cy = rect.centerx, rect.centery
    w, h = rect.width, rect.height

    # Work surface (oversized so rotation doesn't clip)
    diag = work_surface_diag(w, h)
    work = pygame.Surface((diag, diag))
    wcx, wcy = diag // 2, diag // 2

    pitch_deg = math.degrees(pitch)
    pitch_px = pitch_deg * PPD

    # Sky and ground split at pitch offset
    split_y = int(wcy + pitch_px)
    work.fill(colors.SKY)

    if terrain_surface is not None:
        # Below-horizon base before blitting SRCALPHA terrain.  Use the same brown
        # as flat ground — not deep green.  Terrain polygons are ~78–96% opaque, so
        # a green underpaint bleeds through at the sides and bottom and reads as
        # solid artificial green; mavproxy uses a tan/brown fallback instead.
        pygame.draw.rect(work, colors.GROUND, (0, split_y, diag, diag - split_y))
        # Full-size (diag x diag) terrain covers the entire work square edge-to-edge.
        # Older (w x h) centered blit left side margins with no SVS under roll.
        ts_w, ts_h = terrain_surface.get_size()
        if ts_w == diag and ts_h == diag:
            work.blit(terrain_surface, (0, int(pitch_px)))
        else:
            ts_rect = terrain_surface.get_rect()
            ts_x = wcx - ts_rect.width // 2
            ts_y = wcy - ts_rect.height // 2 + int(pitch_px)
            work.blit(terrain_surface, (ts_x, ts_y))
    else:
        pygame.draw.rect(work, colors.GROUND, (0, split_y, diag, diag - split_y))

    # Horizon line
    pygame.draw.line(work, colors.WHITE, (0, split_y), (diag, split_y), 2)

    # Pitch ladder
    font = get_font(12)
    for deg in range(-90, 91, 5):
        if deg == 0:
            continue
        y = int(wcy + pitch_px - deg * PPD)
        half_w = 30 if deg % 10 == 0 else 15
        lw = 2 if deg % 10 == 0 else 1
        pygame.draw.line(work, colors.WHITE,
                         (wcx - half_w, y), (wcx + half_w, y), lw)
        if deg % 10 == 0:
            lbl = font.render(f"{deg}", True, colors.WHITE)
            work.blit(lbl, (wcx - half_w - lbl.get_width() - 4,
                            y - lbl.get_height() // 2))
            work.blit(lbl, (wcx + half_w + 4,
                            y - lbl.get_height() // 2))

    # Rotate the work surface by roll
    roll_deg = math.degrees(roll)
    rotated = pygame.transform.rotate(work, roll_deg)
    rr = rotated.get_rect(center=(cx, cy))

    # Clip and blit onto target
    clip_prev = surface.get_clip()
    surface.set_clip(rect)
    surface.blit(rotated, rr)

    # Fixed aircraft symbol (center reference)
    sym_w = 60
    sym_h = 3
    pygame.draw.line(surface, colors.YELLOW,
                     (cx - sym_w, cy), (cx - 15, cy), sym_h)
    pygame.draw.line(surface, colors.YELLOW,
                     (cx + 15, cy), (cx + sym_w, cy), sym_h)
    pygame.draw.line(surface, colors.YELLOW,
                     (cx - 15, cy), (cx - 15, cy + 8), sym_h)
    pygame.draw.line(surface, colors.YELLOW,
                     (cx + 15, cy), (cx + 15, cy + 8), sym_h)
    pygame.draw.circle(surface, colors.YELLOW, (cx, cy), 4, 2)

    # Roll indicator arc (fixed at top)
    arc_r = min(w, h) // 2 - 10
    arc_rect = pygame.Rect(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
    start_angle = math.radians(30)
    end_angle = math.radians(150)
    pygame.draw.arc(surface, colors.WHITE, arc_rect,
                    start_angle, end_angle, 2)

    # Roll tick marks at 0, +-10, +-20, +-30, +-45, +-60
    for tick_deg in [0, 10, -10, 20, -20, 30, -30, 45, -45, 60, -60]:
        angle = math.radians(90 - tick_deg)
        inner = arc_r - 8
        outer = arc_r
        x1 = cx + int(inner * math.cos(angle))
        y1 = cy - int(inner * math.sin(angle))
        x2 = cx + int(outer * math.cos(angle))
        y2 = cy - int(outer * math.sin(angle))
        pygame.draw.line(surface, colors.WHITE, (x1, y1), (x2, y2), 2)

    # Roll triangle pointer (rotates with roll)
    ptr_angle = math.radians(90) - roll
    ptr_r = arc_r + 2
    px = cx + int(ptr_r * math.cos(ptr_angle))
    py = cy - int(ptr_r * math.sin(ptr_angle))
    tri_size = 8
    p1 = (px, py)
    p2_angle = ptr_angle + math.radians(165)
    p3_angle = ptr_angle - math.radians(165)
    p2 = (px + int(tri_size * math.cos(p2_angle)),
          py - int(tri_size * math.sin(p2_angle)))
    p3 = (px + int(tri_size * math.cos(p3_angle)),
          py - int(tri_size * math.sin(p3_angle)))
    pygame.draw.polygon(surface, colors.WHITE, [p1, p2, p3])

    surface.set_clip(clip_prev)
