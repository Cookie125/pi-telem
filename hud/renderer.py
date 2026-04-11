import pygame

from hud import colors
from hud import horizon
from hud import speed_tape
from hud import alt_tape
from hud import compass
from hud import status_bar
from hud import battery
from hud import messages
from hud import home_info
from hud import wind
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
    def __init__(self, screen: pygame.Surface, state, alt_unit: str = "m"):
        self.screen = screen
        self.state = state
        self.alt_unit = alt_unit
        self._build_layout()

    def _build_layout(self):
        sw, sh = self.screen.get_size()
        spd_w = int(sw * TAPE_WIDTH_FRAC)
        alt_w = int(sw * ALT_TAPE_WIDTH_FRAC)
        right_tapes_w = alt_w * 2  # REL + MSL side by side

        # Top status bar
        self.status_rect = pygame.Rect(0, 0, sw, STATUS_BAR_H)

        # Bottom bar split: battery | messages | VS
        bot_y = sh - BOTTOM_BAR_H
        bat_w = int(sw * 0.28)
        vs_w = int(sw * 0.15)
        msg_w = sw - bat_w - vs_w
        self.battery_rect = pygame.Rect(0, bot_y, bat_w, BOTTOM_BAR_H)
        self.messages_rect = pygame.Rect(bat_w, bot_y, msg_w, BOTTOM_BAR_H)
        self.vspeed_rect = pygame.Rect(sw - vs_w, bot_y, vs_w, BOTTOM_BAR_H)

        # Compass / info bar just above bottom
        info_y = bot_y - COMPASS_BAR_H
        self.compass_rect = pygame.Rect(spd_w, info_y,
                                        sw - spd_w - right_tapes_w, COMPASS_BAR_H)

        # Main area between status bar and compass bar
        main_top = STATUS_BAR_H
        main_bot = info_y
        main_h = main_bot - main_top

        self.speed_rect = pygame.Rect(0, main_top, spd_w, main_h)
        self.alt_rel_rect = pygame.Rect(sw - right_tapes_w, main_top, alt_w, main_h)
        self.alt_msl_rect = pygame.Rect(sw - alt_w, main_top, alt_w, main_h)
        self.horizon_rect = pygame.Rect(spd_w, main_top,
                                        sw - spd_w - right_tapes_w, main_h)

        # Home info bar spanning full width at compass row
        self.home_info_rect = pygame.Rect(0, info_y, sw, COMPASS_BAR_H)

        # Wind indicator overlaid at bottom-left of horizon area
        wind_size = 80
        self.wind_rect = pygame.Rect(
            self.horizon_rect.x + 6,
            self.horizon_rect.bottom - wind_size - 6,
            wind_size, wind_size)

    def draw(self):
        s = self.state.snapshot()
        self.screen.fill(colors.HUD_BG)

        # Horizon first (background for center area)
        horizon.draw(self.screen, self.horizon_rect, s.roll, s.pitch)

        # Tapes overlay on sides
        speed_tape.draw(self.screen, self.speed_rect, s.airspeed, s.groundspeed)
        unit = self.alt_unit
        conv = M_TO_FT if unit == "ft" else 1.0
        alt_tape.draw(self.screen, self.alt_rel_rect, s.altitude * conv,
                      label=f"REL {unit}", color_accent=colors.GREEN)
        alt_tape.draw(self.screen, self.alt_msl_rect, s.altitude_msl * conv,
                      label=f"MSL {unit}", color_accent=colors.CYAN)

        # Wind indicator
        wind.draw(self.screen, self.wind_rect,
                  s.wind_dir, s.wind_speed, s.heading, s.wind_valid)

        # Compass ribbon between tapes, below horizon
        home_brg = None
        if s.home_set and (s.lat != 0.0 or s.lon != 0.0):
            home_brg = _bearing(s.lat, s.lon, s.home_lat, s.home_lon)
        compass.draw(self.screen, self.compass_rect, s.heading,
                     home_bearing=home_brg)

        # Home / vspeed info in the side areas of compass bar row
        home_info.draw(self.screen, self.home_info_rect, s)

        # Top status bar
        status_bar.draw(self.screen, self.status_rect, s)

        # Bottom bar
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
                     s.bat_voltage, s.bat_current, s.bat_remaining)
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
