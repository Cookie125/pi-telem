import pygame

from hud import colors
from hud import horizon
from hud import speed_tape
from hud import alt_tape
from hud import compass
from hud import efi_rpm
from hud import status_bar
from hud import battery
from hud import messages
from hud import home_info
from hud.home_info import _bearing
from hud.fonts import get_font

# Layout proportions (fractions of total width/height)
STATUS_BAR_H = 28
BOTTOM_BAR_H = 28
COMPASS_BAR_H = 34
TAPE_WIDTH_FRAC = 0.12   # speed tape width
ALT_TAPE_WIDTH_FRAC = 0.10  # each altitude tape


M_TO_FT = 3.28084


class HUDRenderer:
    def __init__(self, screen: pygame.Surface, state, alt_unit: str = "m",
                 terrain_sampler=None, map_sampler=None):
        self.screen = screen
        self.state = state
        self.alt_unit = alt_unit
        self._terrain_sampler = terrain_sampler
        self._map_sampler = map_sampler
        self._terrain_renderer = None
        if terrain_sampler is not None:
            from hud.terrain import TerrainRenderer
            self._terrain_renderer = TerrainRenderer()
        self._last_terrain_seq = -1
        self._build_layout()

    def _build_layout(self):
        sw, sh = self.screen.get_size()
        spd_w = int(sw * TAPE_WIDTH_FRAC)
        alt_w = int(sw * ALT_TAPE_WIDTH_FRAC)
        right_tapes_w = alt_w * 2  # REL + MSL side by side

        # Top status bar
        self.status_rect = pygame.Rect(0, 0, sw, STATUS_BAR_H)

        # Bottom bar: battery width set in draw() from measured text (snug to Fuel %)
        bot_y = sh - BOTTOM_BAR_H
        vs_w = int(sw * 0.15)
        self.battery_rect = pygame.Rect(0, bot_y, 100, BOTTOM_BAR_H)
        self.messages_rect = pygame.Rect(100, bot_y, sw - 100 - vs_w, BOTTOM_BAR_H)
        self.vspeed_rect = pygame.Rect(sw - vs_w, bot_y, vs_w, BOTTOM_BAR_H)

        # Compass row: HOME strip | compass | RPM (same x-span as alt tapes, same row as compass)
        info_y = bot_y - COMPASS_BAR_H
        compass_w = sw - spd_w - right_tapes_w
        self.compass_rect = pygame.Rect(spd_w, info_y, compass_w, COMPASS_BAR_H)
        self.rpm_rect = pygame.Rect(
            sw - right_tapes_w, info_y, right_tapes_w, COMPASS_BAR_H
        )

        # Main area between status bar and compass bar
        main_top = STATUS_BAR_H
        main_bot = info_y
        main_h = main_bot - main_top

        self.speed_rect = pygame.Rect(0, main_top, spd_w, main_h)
        self.alt_rel_rect = pygame.Rect(sw - right_tapes_w, main_top, alt_w, main_h)
        self.alt_msl_rect = pygame.Rect(sw - alt_w, main_top, alt_w, main_h)

        # Horizon spans the full width so terrain renders edge-to-edge;
        # tapes draw on top with semi-transparent backgrounds.
        self.horizon_rect = pygame.Rect(0, main_top, sw, main_h)

        # HOME text only in left strip (same column as speed tape), bounded by divider
        self.home_info_rect = pygame.Rect(0, info_y, spd_w, COMPASS_BAR_H)

        # Wind is drawn in the status bar (top right, left of GPS); see status_bar.py

        # Map PIP bottom-left of main band, right of speed tape (above compass row)
        self.map_pip_rect = None
        if self._map_sampler is not None:
            from hud.map_pip import PIP_H, PIP_W

            margin = 8
            self.map_pip_rect = pygame.Rect(
                spd_w + margin,
                info_y - PIP_H - margin,
                PIP_W,
                PIP_H,
            )

    def draw(self):
        s = self.state.snapshot()
        self.screen.fill(colors.HUD_BG)

        # Update terrain surface if sampler is active
        terrain_surf = None
        if self._terrain_sampler is not None and self._terrain_renderer is not None:
            seq, profile = self._terrain_sampler.get_profile()
            # Same square size as horizon's prerotation work surface so SVS fills
            # edge-to-edge before roll (no empty side margins).
            w, h = self.horizon_rect.width, self.horizon_rect.height
            diag = horizon.work_surface_diag(w, h)
            self._terrain_renderer.update(
                seq, profile,
                (diag, diag),
                s.pitch, s.roll,
            )
            terrain_surf = self._terrain_renderer.get_surface()

        home_xy = None
        if (
            self._terrain_sampler is not None
            and self._terrain_renderer is not None
            and terrain_surf is not None
        ):
            from hud.terrain import home_marker_work_coords

            home_xy = home_marker_work_coords(s, diag, s.pitch)

        # Horizon first (background for center area)
        horizon.draw(
            self.screen,
            self.horizon_rect,
            s.roll,
            s.pitch,
            terrain_surface=terrain_surf,
            home_marker_xy=home_xy,
        )

        # Map PIP (tiles + markers) over horizon, before side tapes
        if self._map_sampler is not None and self.map_pip_rect is not None:
            _, msurf = self._map_sampler.get_latest()
            if msurf is not None:
                self.screen.blit(msurf, self.map_pip_rect.topleft)
                pygame.draw.rect(self.screen, colors.GREY, self.map_pip_rect, 1)

        # Tapes overlay on sides
        speed_tape.draw(self.screen, self.speed_rect, s.airspeed, s.groundspeed)
        unit = self.alt_unit
        conv = M_TO_FT if unit == "ft" else 1.0
        alt_tape.draw(self.screen, self.alt_rel_rect, s.altitude * conv,
                      label=f"REL {unit}", color_accent=colors.GREEN)
        alt_tape.draw(self.screen, self.alt_msl_rect, s.altitude_msl * conv,
                      label=f"MSL {unit}", color_accent=colors.CYAN)

        # Compass ribbon between tapes, below horizon
        home_brg = None
        if s.home_set and (s.lat != 0.0 or s.lon != 0.0):
            home_brg = _bearing(s.lat, s.lon, s.home_lat, s.home_lon)
        compass.draw(self.screen, self.compass_rect, s.heading,
                     home_bearing=home_brg)
        efi_rpm.draw(self.screen, self.rpm_rect, s.efi_rpm)

        # Home text in the left strip; separators after so lines sit on top
        home_info.draw(self.screen, self.home_info_rect, s)
        pygame.draw.line(
            self.screen,
            colors.GREY,
            (self.speed_rect.right, self.compass_rect.top),
            (self.speed_rect.right, self.compass_rect.bottom),
            1,
        )
        pygame.draw.line(
            self.screen,
            colors.GREY,
            (self.compass_rect.right, self.compass_rect.top),
            (self.compass_rect.right, self.compass_rect.bottom),
            1,
        )

        # Top status bar
        status_bar.draw(self.screen, self.status_rect, s)

        # Bottom bar — battery column width fits V / A / % / Fuel: (divider snug to text)
        sw, sh = self.screen.get_size()
        vs_w = int(sw * 0.15)
        bot_y = sh - BOTTOM_BAR_H
        bat_w = battery.content_width(
            s.bat_voltage, s.bat_current, s.bat_remaining, s.bat2_remaining
        )
        min_msg = 80
        bat_w = min(bat_w, max(sw - vs_w - min_msg, 1))
        self.battery_rect = pygame.Rect(0, bot_y, bat_w, BOTTOM_BAR_H)
        self.messages_rect = pygame.Rect(bat_w, bot_y, sw - bat_w - vs_w, BOTTOM_BAR_H)
        self.vspeed_rect = pygame.Rect(sw - vs_w, bot_y, vs_w, BOTTOM_BAR_H)

        pygame.draw.rect(self.screen, colors.PANEL_BG, self.battery_rect)
        pygame.draw.rect(self.screen, colors.PANEL_BG, self.messages_rect)
        pygame.draw.rect(self.screen, colors.PANEL_BG, self.vspeed_rect)
        pygame.draw.line(self.screen, colors.GREY,
                         (self.battery_rect.right, self.battery_rect.top),
                         (self.battery_rect.right, self.battery_rect.bottom), 1)
        pygame.draw.line(self.screen, colors.GREY,
                         (self.vspeed_rect.left, self.vspeed_rect.top),
                         (self.vspeed_rect.left, self.vspeed_rect.bottom), 1)

        battery.draw(self.screen, self.battery_rect,
                     s.bat_voltage, s.bat_current, s.bat_remaining,
                     s.bat2_remaining)
        messages.draw(self.screen, self.messages_rect, s.messages)
        self._draw_vspeed(s.vspeed)

    def _draw_vspeed(self, vspeed: float):
        r = self.vspeed_rect
        font = get_font(14)
        color = colors.GREEN if abs(vspeed) < 2.0 else colors.YELLOW
        label = font.render(f"VS {vspeed:+5.1f}m/s", True, color)
        surface = self.screen
        surface.blit(label, (r.x + (r.width - label.get_width()) // 2,
                             r.y + (r.height - label.get_height()) // 2))
