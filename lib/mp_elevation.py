#!/usr/bin/env python3
'''
Wrapper for the SRTM module (srtm.py)
It will grab the altitude of a long,lat pair from the SRTM database
Created by Stephen Dade (stephen_dade@hotmail.com)
'''

import os
import sys
import time

import numpy

from lib import srtm

# SRTM1 = 1 arc-second resolution data (~30m, ~7-9m vertical accuracy)
# SRTM3 = 3 arc-second resolution data (~90m, ~7-9m vertical accuracy)
# COP30 = Copernicus GLO-30 DSM, 1 arc-second (~30m, ~2-4m vertical accuracy)
# 3DEP13 = USGS 3DEP 1/3 arc-second (~10m, ~1-2m vertical accuracy, US only)
TERRAIN_SERVICES = {
    "SRTM1"      : ("terrain.ardupilot.org", "SRTM1"),
    "SRTM3"      : ("terrain.ardupilot.org", "SRTM3"),
    "COP30"      : ("copernicus-dem-30m.s3.amazonaws.com", "COP30"),
    "3DEP13"     : ("prd-tnm.s3.amazonaws.com", "3DEP13"),
}

class ElevationModel():
    '''Elevation Model. Supports SRTM1/3, Copernicus GLO-30, and USGS 3DEP'''

    # all tile-based sources that use SRTMTile internally
    _TILE_SOURCES = ['SRTM1', 'SRTM3', 'COP30', '3DEP13']

    def __init__(self, database='SRTM3', offline=0, debug=False, cachedir=None):
        '''Use offline=1 to disable any downloading of tiles, regardless of whether the
        tile exists'''
        if database is not None and database.lower() == 'srtm':
            # compatibility with the old naming
            database = "SRTM3"
        self.database = database
        if self.database in ['SRTM1', 'SRTM3']:
            self.downloader = srtm.SRTMDownloader(offline=offline, debug=debug, directory=self.database, cachedir=cachedir)
            self.downloader.loadFileList()
            self.tileDict = dict()
        elif self.database == 'COP30':
            self.downloader = srtm.CopernicusDownloader(offline=offline, debug=debug, cachedir=cachedir)
            self.tileDict = dict()
        elif self.database == '3DEP13':
            self.downloader = srtm.USGS3DEPDownloader(offline=offline, debug=debug, cachedir=cachedir)
            self.tileDict = dict()
        elif self.database == 'geoscience':
            '''Use the Geoscience Australia database instead - watch for the correct database path'''
            from MAVProxy.modules.mavproxy_map import GAreader
            self.mappy = GAreader.ERMap()
            self.mappy.read_ermapper(os.path.join(os.environ['HOME'], './Documents/Elevation/Canberra/GSNSW_P756demg'))
        else:
            print("Error: Bad terrain source " + str(database))
            self.database = None

    def GetElevation(self, latitude, longitude, timeout=0):
        '''Returns the altitude (m ASL) of a given lat/long pair, or None if unknown'''
        if latitude is None or longitude is None:
            return None
        if self.database in self._TILE_SOURCES:
            TileID = (numpy.floor(latitude), numpy.floor(longitude))
            if TileID in self.tileDict:
                alt = self.tileDict[TileID].getAltitudeFromLatLon(latitude, longitude)
            else:
                tile = self.downloader.getTile(numpy.floor(latitude), numpy.floor(longitude))
                if tile == 0:
                    if timeout > 0:
                        t0 = time.time()
                        while time.time() < t0+timeout and tile == 0:
                            tile = self.downloader.getTile(numpy.floor(latitude), numpy.floor(longitude))
                            if tile == 0:
                                time.sleep(0.1)
                if tile == 0:
                    return None
                self.tileDict[TileID] = tile
                alt = tile.getAltitudeFromLatLon(latitude, longitude)
        elif self.database == 'geoscience':
             alt = self.mappy.getAltitudeAtPoint(latitude, longitude)
        else:
            return None
        return alt

    def GetElevationBulk(self, lat_arr, lon_arr):
        '''Vectorized elevation lookup for arrays of lat/lon.

        Returns (elevations, valid) numpy arrays matching input shape.
        elevations is float64, valid is bool.
        '''
        if self.database not in self._TILE_SOURCES:
            # fallback scalar loop for non-SRTM databases
            elevations = numpy.zeros(lat_arr.shape, dtype=numpy.float64)
            valid = numpy.zeros(lat_arr.shape, dtype=bool)
            for idx in numpy.ndindex(lat_arr.shape):
                alt = self.GetElevation(float(lat_arr[idx]),
                                        float(lon_arr[idx]))
                if alt is not None and alt != -1:
                    elevations[idx] = alt
                    valid[idx] = True
            return elevations, valid

        elevations = numpy.zeros(lat_arr.shape, dtype=numpy.float64)
        valid = numpy.zeros(lat_arr.shape, dtype=bool)

        # group by 1-degree SRTM tile
        tile_lat = numpy.floor(lat_arr).astype(numpy.int32).ravel()
        tile_lon = numpy.floor(lon_arr).astype(numpy.int32).ravel()

        # encode as unique key: shift lat/lon to unsigned, then combine
        # lat range [-90,90] -> [0,180], lon range [-180,180] -> [0,360]
        tile_key = (tile_lat + 90).astype(numpy.int64) * 1000 + (tile_lon + 180)
        unique_keys = numpy.unique(tile_key)

        for uk in unique_keys:
            tlat = int(uk // 1000) - 90
            tlon = int(uk % 1000) - 180
            mask = (tile_key == uk)

            # get or cache the SRTM tile
            TileID = (float(tlat), float(tlon))
            if TileID in self.tileDict:
                tile = self.tileDict[TileID]
            else:
                tile = self.downloader.getTile(tlat, tlon)
                if tile == 0:
                    continue
                self.tileDict[TileID] = tile

            # extract coordinates for this tile
            flat_lat = lat_arr.ravel()[mask]
            flat_lon = lon_arr.ravel()[mask]

            alts = tile.getAltitudeBulk(flat_lat, flat_lon)

            flat_elev = elevations.ravel()
            flat_valid = valid.ravel()
            good = ~numpy.isnan(alts)
            flat_elev[mask] = numpy.where(good, alts, 0.0)
            flat_valid[mask] = good

        return elevations, valid


if __name__ == "__main__":

    from argparse import ArgumentParser
    parser = ArgumentParser("mp_elevation.py [options]")
    parser.add_argument("--lat", type=float, default=-35.052544, help="start latitude")
    parser.add_argument("--lon", type=float, default=149.509165, help="start longitude")
    parser.add_argument("--database", type=str, default='SRTM3', help="elevation database", choices=["SRTM1", "SRTM3", "COP30", "3DEP13"])
    parser.add_argument("--debug", action='store_true', help="enabled debugging")

    args = parser.parse_args()

    EleModel = ElevationModel(args.database, debug=args.debug)

    lat = args.lat
    lon = args.lon

    '''Do a few lat/long pairs to demonstrate the caching
    Note the +0.000001 to the time. On faster PCs, the two time periods
    may in fact be equal, so we add a little extra time on the end to account for this'''
    t0 = time.time()
    alt = EleModel.GetElevation(lat, lon, timeout=10)
    if alt is None:
        print("Tile not available")
        sys.exit(1)
    t1 = time.time()+.000001
    print("Altitude at (%.6f, %.6f) is %u m. Pulled at %.1f FPS" % (lat, lon, alt, 1/(t1-t0)))

    lat = args.lat+0.001
    lon = args.lon+0.001
    t0 = time.time()
    alt = EleModel.GetElevation(lat, lon, timeout=10)
    t1 = time.time()+.000001
    print("Altitude at (%.6f, %.6f) is %u m. Pulled at %.1f FPS" % (lat, lon, alt, 1/(t1-t0)))

    lat = args.lat-0.001
    lon = args.lon-0.001
    t0 = time.time()
    alt = EleModel.GetElevation(lat, lon, timeout=10)
    t1 = time.time()+.000001
    print("Altitude at (%.6f, %.6f) is %u m. Pulled at %.1f FPS" % (lat, lon, alt, 1/(t1-t0)))



