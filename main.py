#!/usr/bin/env python3
"""Pi Zero 2 W MAVLink Telemetry HUD."""

import os
import sys
import signal

import pygame

from config import parse_args
from telemetry_state import TelemetryState
from mavlink_reader import MavlinkReader
from hud.renderer import HUDRenderer
from hud import fonts


def main():
    args = parse_args()

    # Allow KMS/DRM framebuffer on Pi OS Lite (no X11)
    if "DISPLAY" not in os.environ and "SDL_VIDEODRIVER" not in os.environ:
        os.environ["SDL_VIDEODRIVER"] = "kmsdrm"

    pygame.init()
    fonts.init()

    flags = 0 if args.windowed else pygame.FULLSCREEN
    screen = pygame.display.set_mode(args.resolution, flags)
    pygame.display.set_caption("MAVLink Telemetry HUD")
    pygame.mouse.set_visible(False)

    state = TelemetryState()
    reader = MavlinkReader(
        args.connections, args.baud, state, rx_only=args.rx_only
    )
    reader.start()

    terrain_sampler = None
    if args.terrain:
        from hud.terrain import TerrainSampler
        terrain_sampler = TerrainSampler(state, db=args.terrain_db)
        terrain_sampler.start()

    map_sampler = None
    if args.map:
        from hud.map_pip import MapPipSampler
        map_sampler = MapPipSampler(
            state,
            zoom=args.map_zoom,
            tile_url_template=args.map_tile_url,
        )
        map_sampler.start()

    renderer = HUDRenderer(
        screen,
        state,
        alt_unit=args.alt_unit,
        terrain_sampler=terrain_sampler,
        map_sampler=map_sampler,
    )
    clock = pygame.time.Clock()

    running = True

    def _shutdown(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False

        renderer.draw()
        pygame.display.flip()
        clock.tick(args.fps)

    reader.stop()
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
