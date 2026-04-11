#!/usr/bin/env python3

# Pylint: Disable name warnings
# pylint: disable-msg=C0103

"""Load and process SRTM data. Originally written by OpenStreetMap
Edited by CanberraUAV"""

import sys
if sys.version_info.major < 3:
    from HTMLParser import HTMLParser
    import httplib
else:
    from html.parser import HTMLParser
    import http.client as httplib

import re
import pickle
import os.path
import os
import zipfile
import array
import math
import numpy as np
from lib import mp_util
from lib import multiproc

childTileDownload = {}
childFileListDownload = {}
filelistDownloadActive = 0

class NoSuchTileError(Exception):
    """Raised when there is no tile for a region."""
    def __init__(self, lat, lon):
        Exception.__init__(self)
        self.lat = lat
        self.lon = lon

    def __str__(self):
        return "No SRTM tile for %d, %d available!" % (self.lat, self.lon)


class WrongTileError(Exception):
    """Raised when the value of a pixel outside the tile area is requested."""
    def __init__(self, tile_lat, tile_lon, req_lat, req_lon):
        Exception.__init__(self)
        self.tile_lat = tile_lat
        self.tile_lon = tile_lon
        self.req_lat = req_lat
        self.req_lon = req_lon

    def __str__(self):
        return "SRTM tile for %d, %d does not contain data for %d, %d!" % (
            self.tile_lat, self.tile_lon, self.req_lat, self.req_lon)

class InvalidTileError(Exception):
    """Raised when the SRTM tile file contains invalid data."""
    def __init__(self, lat, lon):
        Exception.__init__(self)
        self.lat = lat
        self.lon = lon

    def __str__(self):
        return "SRTM tile for %d, %d is invalid!" % (self.lat, self.lon)

class SRTMDownloader():
    """Automatically download SRTM tiles."""
    def __init__(self, server="terrain.ardupilot.org",
                 directory="SRTM3",
                 cachedir=None,
                 offline=0,
                 debug=False,
                 use_http=False):

        if cachedir is None:
            try:
                cachedir = os.path.join(os.environ['HOME'], '.tilecache', directory)
            except Exception:
                if 'LOCALAPPDATA' in os.environ:
                    cachedir = os.path.join(os.environ['LOCALAPPDATA'], '.tilecache', directory)
                else:
                    import tempfile
                    cachedir = os.path.join(tempfile.gettempdir(), 'MAVProxy', directory)

        # User migration to new folder struct (SRTM -> SRTM3)
        if directory == "SRTM3" and not os.path.exists(cachedir) and os.path.exists(cachedir[:-1]):
            print("Migrating old SRTM folder")
            os.rename(cachedir[:-1], cachedir)
        
        self.debug = debug
        self.offline = offline
        self.offlinemessageshown = 0
        if self.offline == 1 and self.debug:
            print("Map Module in Offline mode")
        self.server = server
        self.directory = "/" + directory +"/"
        self.cachedir = cachedir
        if self.debug:
            print("SRTMDownloader - server=%s, directory=%s." % (self.server, self.directory))
        if not os.path.exists(cachedir):
            mp_util.mkdir_p(cachedir)
        self.filelist = {}
        self.filename_regex = re.compile(
                r"([NS])(\d{2})([EW])(\d{3})\.hgt\.zip")
        self.filelist_file = os.path.join(self.cachedir, "filelist_python")
        self.min_filelist_len = 14500
        self.use_http = use_http

    def loadFileList(self):
        """Load a previously created file list or create a new one if none is
            available."""
        try:
            data = open(self.filelist_file, 'rb')
        except IOError:
            '''print("No SRTM cached file list. Creating new one!")'''
            if self.offline == 0:
                self.createFileList()
            return
        try:
            self.filelist = pickle.load(data)
            data.close()
            if len(self.filelist) < self.min_filelist_len:
                self.filelist = {}
                if self.offline == 0:
                    self.createFileList()
        except:
            '''print("Unknown error loading cached SRTM file list. Creating new one!")'''
            if self.offline == 0:
                self.createFileList()

    def createFileList(self):
        """SRTM data is split into different directories, get a list of all of
            them and create a dictionary for easy lookup."""
        global childFileListDownload
        global filelistDownloadActive
        mypid = os.getpid()
        if mypid not in childFileListDownload or not childFileListDownload[mypid].is_alive():
            childFileListDownload[mypid] = multiproc.Process(target=self.createFileListHTTP)
            filelistDownloadActive = 1
            childFileListDownload[mypid].start()
            filelistDownloadActive = 0

    def getURIWithRedirect(self, url):
        '''fetch a URL with redirect handling'''
        tries = 0
        while tries < 5:
                if self.use_http:
                    conn = httplib.HTTPConnection(self.server)
                else:
                    conn = httplib.HTTPSConnection(self.server)
                conn.request("GET", url)
                r1 = conn.getresponse()
                if r1.status in [301, 302, 303, 307]:
                    location = r1.getheader('Location')
                    if self.debug:
                        print("redirect from %s to %s" % (url, location))
                    url = location
                    conn.close()
                    tries += 1
                    continue
                data = r1.read()
                conn.close()
                if sys.version_info.major < 3:
                    return data
                else:
                    encoding = r1.headers.get_content_charset()
                    if encoding is not None:
                        return data.decode(encoding)
                    elif ".zip" in url or ".hgt" in url:
                        return data
                    else:
                        return data.decode('utf-8')
        return None

    def createFileListHTTP(self):
        """Create a list of the available SRTM files on the server using
        HTTP file transfer protocol (rather than ftp).
        30may2010  GJ ORIGINAL VERSION
        """
        mp_util.child_close_fds()
        if self.debug:
            print("Connecting to %s" % self.server, self.directory)
        try:
            data = self.getURIWithRedirect(self.directory)
        except Exception:
            return
        parser = parseHTMLDirectoryListing()
        parser.feed(data)
        continents = parser.getDirListing()
        
        # Flat structure
        if any(".hgt.zip" in mystring for mystring in continents):
            files = continents
            for filename in files:
                if ".hgt.zip" in filename:
                    self.filelist[self.parseFilename(filename)] = ("/", filename)
        else:
            # tiles in subfolders
            if self.debug:
                print('continents: ', continents)

            for continent in continents:
                if not continent[0].isalpha() or continent.startswith('README'):
                    continue
                if self.debug:
                    print("Downloading file list for: ", continent)
                url = "%s%s" % (self.directory,continent)
                if self.debug:
                    print("fetching %s" % url)
                try:
                    data = self.getURIWithRedirect(url)
                except Exception as ex:
                    print("Failed to download %s : %s" % (url, ex))
                    continue
                parser = parseHTMLDirectoryListing()
                parser.feed(data)
                files = parser.getDirListing()

                for filename in files:
                    self.filelist[self.parseFilename(filename)] = (
                                continent, filename)

                '''print(self.filelist)'''
        # Add meta info
        self.filelist["server"] = self.server
        self.filelist["directory"] = self.directory
        tmpname = self.filelist_file + ".tmp"
        with open(tmpname , 'wb') as output:
            pickle.dump(self.filelist, output)
            output.close()
            try:
                os.unlink(self.filelist_file)
            except Exception:
                pass
            try:
                os.rename(tmpname, self.filelist_file)
            except Exception:
                pass
        if self.debug:
            print("created file list with %u entries" % len(self.filelist))

    def parseFilename(self, filename):
        """Get lat/lon values from filename."""
        match = self.filename_regex.match(filename)
        if match is None:
            # TODO?: Raise exception?
            '''print("Filename", filename, "unrecognized!")'''
            return None
        lat = int(match.group(2))
        lon = int(match.group(4))
        if match.group(1) == "S":
            lat = -lat
        if match.group(3) == "W":
            lon = -lon
        return lat, lon

    def getTile(self, lat, lon):
        """Get a SRTM tile object. This function can return either an SRTM1 or
            SRTM3 object depending on what is available, however currently it
            only returns SRTM3 objects."""
        global childFileListDownload
        global filelistDownloadActive
        mypid = os.getpid()
        if mypid in childFileListDownload and childFileListDownload[mypid].is_alive():
            if self.debug:
                print("still getting file list")
            return 0
        elif not os.path.isfile(self.filelist_file) and filelistDownloadActive == 0:
            self.createFileList()
            return 0
        elif not self.filelist:
            if self.debug:
                print("Filelist download complete, loading data ", self.filelist_file)
            data = open(self.filelist_file, 'rb')
            self.filelist = pickle.load(data)
            data.close()

        try:
            continent, filename = self.filelist[(int(lat), int(lon))]
        except KeyError:
            if len(self.filelist) > self.min_filelist_len:
                # we appear to have a full filelist - this must be ocean
                return SRTMOceanTile(int(lat), int(lon))
            return 0

        global childTileDownload
        mypid = os.getpid()
        if not os.path.exists(os.path.join(self.cachedir, filename)):
            # don't retry tiles that previously failed download
            if os.path.exists(os.path.join(self.cachedir, filename + ".failed")):
                return 0
            if not mypid in childTileDownload or not childTileDownload[mypid].is_alive():
                try:
                    childTileDownload[mypid] = multiproc.Process(target=self.downloadTile, args=(str(continent), str(filename)))
                    childTileDownload[mypid].start()
                except Exception as ex:
                    if mypid in childTileDownload:
                        childTileDownload.pop(mypid)
                    return 0
                '''print("Getting Tile")'''
            return 0
        elif mypid in childTileDownload and childTileDownload[mypid].is_alive():
            '''print("Still Getting Tile")'''
            return 0
        # TODO: Currently we create a new tile object each time.
        # Caching is required for improved performance.
        try:
            return SRTMTile(os.path.join(self.cachedir, filename), int(lat), int(lon))
        except InvalidTileError:
            return 0

    def downloadTile(self, continent, filename):
        #Use HTTP
        mp_util.child_close_fds()
        if self.offline == 1:
            return
        filepath = "%s%s%s" % \
                     (self.directory,continent,filename)
        tile_path = os.path.join(self.cachedir, filename)
        try:
            data = self.getURIWithRedirect(filepath)
            # we got a response — network is working, clear any stale failure sentinel
            try:
                os.unlink(tile_path + ".failed")
            except Exception:
                pass
            if data:
                self.ftpfile = open(tile_path, 'wb')
                self.ftpfile.write(data)
                self.ftpfile.close()
                self.ftpfile = None
        except Exception as e:
            print("SRTM Download failed %s on server %s: %s" % (filepath, self.server, e))
            # write failure sentinel to prevent infinite retry spawns
            try:
                with open(tile_path + ".failed", 'w') as f:
                    f.write(str(e))
            except Exception:
                pass


class SRTMTile:
    """Base class for all SRTM tiles.
        Each SRTM tile is size x size pixels big and contains
        data for the area from (lat, lon) to (lat+1, lon+1) inclusive.
        This means there is a 1 pixel overlap between tiles. This makes it
        easier for as to interpolate the value, because for every point we
        only have to look at a single tile.
        """
    def __init__(self, f, lat, lon):
        try:
            zipf = zipfile.ZipFile(f, 'r')
        except Exception:
            raise InvalidTileError(lat, lon)
        names = zipf.namelist()
        if len(names) != 1:
            raise InvalidTileError(lat, lon)
        data = zipf.read(names[0])
        self.size = int(math.sqrt(len(data)/2)) # 2 bytes per sample
        # SRTM1/3 tiles are 3601x3601 or 1201x1201
        # Copernicus tiles converted to HGT are 3601x3601 (padded from 3600)
        # USGS 3DEP 1/3 arc-second tiles are 10801x10801 (padded from 10800)
        if self.size not in (1201, 3601, 10801):
            raise InvalidTileError(lat, lon)
        self.data = array.array('h', data)
        self.data.byteswap()
        if len(self.data) != self.size * self.size:
            raise InvalidTileError(lat, lon)
        self.lat = lat
        self.lon = lon

    @staticmethod
    def _avg(value1, value2, weight):
        """Returns the weighted average of two values and handles the case where
            one value is None. If both values are None, None is returned.
        """
        if value1 is None:
            return value2
        if value2 is None:
            return value1
        return value2 * weight + value1 * (1 - weight)

    def calcOffset(self, x, y):
        """Calculate offset into data array. Only uses to test correctness
            of the formula."""
        # Datalayout
        # X = longitude
        # Y = latitude
        # Sample for size 1201x1201
        #  (   0/1200)     (   1/1200)  ...    (1199/1200)    (1200/1200)
        #  (   0/1199)     (   1/1199)  ...    (1199/1199)    (1200/1199)
        #       ...            ...                 ...             ...
        #  (   0/   1)     (   1/   1)  ...    (1199/   1)    (1200/   1)
        #  (   0/   0)     (   1/   0)  ...    (1199/   0)    (1200/   0)
        #  Some offsets:
        #  (0/1200)     0
        #  (1200/1200)  1200
        #  (0/1199)     1201
        #  (1200/1199)  2401
        #  (0/0)        1201*1200
        #  (1200/0)     1201*1201-1
        return x + self.size * (self.size - y - 1)

    def getPixelValue(self, x, y):
        """Get the value of a pixel from the data, handling voids in the
            SRTM data."""
        assert x < self.size, "x: %d<%d" % (x, self.size)
        assert y < self.size, "y: %d<%d" % (y, self.size)
        # Same as calcOffset, inlined for performance reasons
        offset = x + self.size * (self.size - y - 1)
        if self.data is not None:
            value = self.data[offset]
        else:
            # Fallback: read from numpy array if array.array was freed
            row = self.size - y - 1
            value = int(self._np_data[row, x])
        if value == -32768:
            return -1 # -32768 is a special value for areas with no data
        return value


    def _get_np_data(self):
        """Lazily convert self.data to a 2D numpy array (cached)."""
        if not hasattr(self, '_np_data') or self._np_data is None:
            # self.data is already byteswapped to native order
            self._np_data = np.array(
                self.data, dtype=np.int16
            ).reshape((self.size, self.size))
            # Free the original array.array to avoid doubling memory per tile
            self.data = None
        return self._np_data

    def getAltitudeBulk(self, lat_arr, lon_arr):
        """Vectorized bilinear interpolation for N points.

        lat_arr, lon_arr: numpy arrays of any shape (must match).
        Returns float64 array of altitudes (same shape), NaN for voids.
        """
        orig_shape = lat_arr.shape
        lat_f = (lat_arr - self.lat).ravel()
        lon_f = (lon_arr - self.lon).ravel()

        x = lon_f * (self.size - 1)
        y = lat_f * (self.size - 1)

        x0 = np.clip(np.floor(x).astype(np.intp), 0, self.size - 2)
        y0 = np.clip(np.floor(y).astype(np.intp), 0, self.size - 2)
        x1 = np.minimum(x0 + 1, self.size - 1)
        y1 = np.minimum(y0 + 1, self.size - 1)

        xf = x - x0
        yf = y - y0

        data = self._get_np_data()
        # data layout: row 0 = top of tile (highest lat)
        ry0 = self.size - 1 - y0
        ry1 = self.size - 1 - y1

        v00 = data[ry0, x0].astype(np.float64)
        v10 = data[ry0, x1].astype(np.float64)
        v01 = data[ry1, x0].astype(np.float64)
        v11 = data[ry1, x1].astype(np.float64)

        # bilinear interpolation
        top = v00 + xf * (v10 - v00)
        bot = v01 + xf * (v11 - v01)
        result = top + yf * (bot - top)

        # mark voids (any corner == -32768 means void)
        void = (
            (v00 == -32768) | (v10 == -32768) |
            (v01 == -32768) | (v11 == -32768)
        )
        result[void] = np.nan

        return result.reshape(orig_shape)

    def getAltitudeFromLatLon(self, lat, lon):
        """Get the altitude of a lat lon pair, using the four neighbouring
            pixels for interpolation.
        """
        # print("-----\nFromLatLon", lon, lat)
        lat -= self.lat
        lon -= self.lon
        # print("lon, lat", lon, lat)
        if lat < 0.0 or lat >= 1.0 or lon < 0.0 or lon >= 1.0:
            raise WrongTileError(self.lat, self.lon, self.lat+lat, self.lon+lon)
        x = lon * (self.size - 1)
        y = lat * (self.size - 1)
        # print("x,y", x, y)
        x_int = int(x)
        x_frac = x - int(x)
        y_int = int(y)
        y_frac = y - int(y)
        # print("frac", x_int, x_frac, y_int, y_frac)
        value00 = self.getPixelValue(x_int, y_int)
        value10 = self.getPixelValue(x_int+1, y_int)
        value01 = self.getPixelValue(x_int, y_int+1)
        value11 = self.getPixelValue(x_int+1, y_int+1)
        value1 = self._avg(value00, value10, x_frac)
        value2 = self._avg(value01, value11, x_frac)
        value  = self._avg(value1,  value2, y_frac)
        # print("%4d %4d | %4d\n%4d %4d | %4d\n-------------\n%4d" % (
        #        value00, value10, value1, value01, value11, value2, value))
        return value

class SRTMOceanTile(SRTMTile):
    '''a tile for areas of zero altitude'''
    def __init__(self, lat, lon):
        self.lat = lat
        self.lon = lon

    def getAltitudeFromLatLon(self, lat, lon):
        return 0

    def getAltitudeBulk(self, lat_arr, lon_arr):
        """Vectorized altitude for ocean — always zero."""
        return np.zeros(lat_arr.shape, dtype=np.float64)


class CopernicusDownloader():
    """Download Copernicus GLO-30 DSM tiles from AWS S3.

    Tiles are Cloud-Optimized GeoTIFF (COG) at 1 arc-second resolution.
    Downloaded as GeoTIFF, converted to HGT format via Pillow for
    compatibility with SRTMTile.

    No authentication required — the S3 bucket is publicly accessible.
    """
    def __init__(self, offline=0, debug=False, cachedir=None):
        self.offline = offline
        self.debug = debug
        self.server = "copernicus-dem-30m.s3.amazonaws.com"

        if cachedir is None:
            try:
                cachedir = os.path.join(os.environ['HOME'], '.tilecache', 'COP30')
            except Exception:
                if 'LOCALAPPDATA' in os.environ:
                    cachedir = os.path.join(os.environ['LOCALAPPDATA'], '.tilecache', 'COP30')
                else:
                    import tempfile
                    cachedir = os.path.join(tempfile.gettempdir(), 'MAVProxy', 'COP30')

        self.cachedir = cachedir
        if not os.path.exists(cachedir):
            mp_util.mkdir_p(cachedir)

    def _tile_name(self, lat, lon):
        """Return the Copernicus tile base name for a lat/lon."""
        lat = int(lat)
        lon = int(lon)
        lat_hemi = 'N' if lat >= 0 else 'S'
        lon_hemi = 'E' if lon >= 0 else 'W'
        return "Copernicus_DSM_COG_10_%s%02d_00_%s%03d_00_DEM" % (
            lat_hemi, abs(lat), lon_hemi, abs(lon))

    def _tile_url(self, lat, lon):
        """Return the HTTPS URL for a Copernicus tile."""
        name = self._tile_name(lat, lon)
        return "/%s/%s.tif" % (name, name)

    def _hgt_filename(self, lat, lon):
        """Return the local HGT cache filename for a tile."""
        lat = int(lat)
        lon = int(lon)
        lat_hemi = 'N' if lat >= 0 else 'S'
        lon_hemi = 'E' if lon >= 0 else 'W'
        return "%s%02d%s%03d.hgt.zip" % (
            lat_hemi, abs(lat), lon_hemi, abs(lon))

    @staticmethod
    def _geotiff_to_hgt(tif_data):
        """Convert a Copernicus GeoTIFF to SRTM-compatible HGT bytes.

        Reads the GeoTIFF (3600x3600 float32) via Pillow, converts to
        int16, and pads to 3601x3601 by duplicating edge rows/columns
        (for SRTMTile compatibility).

        Returns bytes suitable for writing into a .hgt.zip file.
        """
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(tif_data))
        arr = np.array(img, dtype=np.float32)  # 3600x3600

        # convert to int16, marking NaN as void
        hgt = np.round(arr).astype(np.int16)
        hgt[np.isnan(arr)] = -32768

        # pad 3600x3600 → 3601x3601 by duplicating last row and last column
        # SRTM tiles overlap by 1 pixel with their neighbors
        padded = np.zeros((3601, 3601), dtype=np.int16)
        padded[:3600, :3600] = hgt
        padded[3600, :3600] = hgt[3599, :]   # duplicate bottom row
        padded[:3600, 3600] = hgt[:, 3599]   # duplicate right column
        padded[3600, 3600] = hgt[3599, 3599]  # corner

        # SRTM HGT is big-endian int16, row 0 = northernmost
        padded.byteswap(inplace=True)
        return padded.tobytes()

    def getTile(self, lat, lon):
        """Get a Copernicus tile as an SRTMTile, downloading and converting if needed."""
        lat = int(lat)
        lon = int(lon)
        hgt_file = os.path.join(self.cachedir, self._hgt_filename(lat, lon))

        if os.path.exists(hgt_file):
            try:
                return SRTMTile(hgt_file, lat, lon)
            except InvalidTileError:
                return 0

        # don't retry tiles that previously failed download/conversion
        if os.path.exists(hgt_file + ".failed"):
            return 0

        # check if download is already in progress
        global childTileDownload
        mypid = os.getpid()
        if mypid in childTileDownload and childTileDownload[mypid].is_alive():
            return 0

        if self.offline:
            return 0

        # start background download + conversion
        try:
            childTileDownload[mypid] = multiproc.Process(
                target=self._download_and_convert, args=(lat, lon))
            childTileDownload[mypid].start()
        except Exception:
            if mypid in childTileDownload:
                childTileDownload.pop(mypid)
        return 0

    def _download_and_convert(self, lat, lon):
        """Download a Copernicus GeoTIFF tile and convert to HGT (runs in child process)."""
        mp_util.child_close_fds()
        url = self._tile_url(lat, lon)
        hgt_file = os.path.join(self.cachedir, self._hgt_filename(lat, lon))
        try:
            conn = httplib.HTTPSConnection(self.server)
            conn.request("GET", url)
            resp = conn.getresponse()

            # we got an HTTP response — network is working, clear any stale failure sentinel
            try:
                os.unlink(hgt_file + ".failed")
            except Exception:
                pass

            if resp.status == 404:
                # no tile for this area — likely ocean, create an ocean tile cache
                if self.debug:
                    print("COP30: no tile for %d,%d (ocean)" % (lat, lon))
                self._write_ocean_hgt(hgt_file)
                conn.close()
                return
            if resp.status != 200:
                print("COP30 download failed: HTTP %d for %s" % (resp.status, url))
                conn.close()
                return
            tif_data = resp.read()
            conn.close()

            if self.debug:
                print("COP30: downloaded %d bytes for %d,%d" % (len(tif_data), lat, lon))

            # convert GeoTIFF to HGT
            hgt_bytes = self._geotiff_to_hgt(tif_data)

            # write as .hgt.zip (compatible with SRTMTile loader)
            lat_hemi = 'N' if lat >= 0 else 'S'
            lon_hemi = 'E' if lon >= 0 else 'W'
            inner_name = "%s%02d%s%03d.hgt" % (
                lat_hemi, abs(lat), lon_hemi, abs(lon))

            tmpfile = hgt_file + ".tmp"
            with zipfile.ZipFile(tmpfile, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(inner_name, hgt_bytes)
            try:
                os.unlink(hgt_file)
            except Exception:
                pass
            os.rename(tmpfile, hgt_file)

            if self.debug:
                print("COP30: cached %s" % hgt_file)

        except Exception as e:
            print("COP30 download failed for %d,%d: %s" % (lat, lon, e))
            # write failure sentinel to prevent infinite retry spawns
            try:
                with open(hgt_file + ".failed", 'w') as f:
                    f.write(str(e))
            except Exception:
                pass

    @staticmethod
    def _write_ocean_hgt(filepath):
        """Write a minimal ocean HGT zip (all zeros) as a cache marker."""
        data = np.zeros((3601, 3601), dtype=np.int16)
        data.byteswap(inplace=True)  # convert to big-endian for HGT format
        inner_name = os.path.basename(filepath).replace('.zip', '')
        tmpfile = filepath + ".tmp"
        with zipfile.ZipFile(tmpfile, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(inner_name, data.tobytes())
        try:
            os.unlink(filepath)
        except Exception:
            pass
        os.rename(tmpfile, filepath)


class USGS3DEPDownloader():
    """Download USGS 3DEP 1/3 arc-second DEM tiles from AWS S3.

    Tiles are GeoTIFF at 1/3 arc-second resolution (~10m, ~1-2m vertical
    accuracy).  Downloaded as GeoTIFF, converted to HGT format via Pillow
    for compatibility with SRTMTile.

    No authentication required — the S3 bucket is publicly accessible.
    Coverage: CONUS + Alaska + Hawaii + US territories only.
    """
    def __init__(self, offline=0, debug=False, cachedir=None):
        self.offline = offline
        self.debug = debug
        self.server = "prd-tnm.s3.amazonaws.com"

        if cachedir is None:
            try:
                cachedir = os.path.join(os.environ['HOME'], '.tilecache', '3DEP13')
            except Exception:
                if 'LOCALAPPDATA' in os.environ:
                    cachedir = os.path.join(os.environ['LOCALAPPDATA'], '.tilecache', '3DEP13')
                else:
                    import tempfile
                    cachedir = os.path.join(tempfile.gettempdir(), 'MAVProxy', '3DEP13')

        self.cachedir = cachedir
        if not os.path.exists(cachedir):
            mp_util.mkdir_p(cachedir)

    @staticmethod
    def _usgs_tile_name(lat, lon):
        """Return the USGS tile directory/file base name for a floor(lat), floor(lon).

        USGS uses the NW corner for naming:
          n{CEIL_LAT}w{ABS_LON} for western hemisphere
          n{CEIL_LAT}e{ABS_LON} for eastern hemisphere
        Our system keys by (floor(lat), floor(lon)) which is the SW corner.
        """
        lat = int(lat)
        lon = int(lon)
        # USGS tile name uses north edge = floor(lat) + 1 for N hemisphere
        if lat >= 0:
            lat_name = "n%02d" % (lat + 1)
        else:
            # S hemisphere: tile covers lat to lat+1, name uses abs(lat)
            lat_name = "s%02d" % abs(lat)
        if lon >= 0:
            lon_name = "e%03d" % (lon + 1)
        else:
            lon_name = "w%03d" % abs(lon)
        return "%s%s" % (lat_name, lon_name)

    def _tile_url(self, lat, lon):
        """Return the S3 URL path for a 3DEP 1/3 arc-second tile."""
        tile = self._usgs_tile_name(lat, lon)
        return "/StagedProducts/Elevation/13/TIFF/current/%s/USGS_13_%s.tif" % (tile, tile)

    def _hgt_filename(self, lat, lon):
        """Return the local HGT cache filename for a tile."""
        lat = int(lat)
        lon = int(lon)
        lat_hemi = 'N' if lat >= 0 else 'S'
        lon_hemi = 'E' if lon >= 0 else 'W'
        return "%s%02d%s%03d.hgt.zip" % (
            lat_hemi, abs(lat), lon_hemi, abs(lon))

    @staticmethod
    def _geotiff_to_hgt(tif_data):
        """Convert a USGS 3DEP 1/3 arc-second GeoTIFF to HGT bytes.

        Reads the GeoTIFF via Pillow, converts to int16, and produces a
        10801x10801 grid (for SRTMTile compatibility).

        USGS 3DEP tiles are 10812x10812 (10800 data pixels + 6-pixel
        boundary buffer on each side).  We crop the buffer, then pad
        10800x10800 -> 10801x10801 by duplicating edge rows/columns.

        Returns bytes suitable for writing into a .hgt.zip file.
        """
        from PIL import Image
        import io

        # 3DEP tiles are 10812x10812 (~117M pixels), which exceeds Pillow's
        # default decompression bomb limit (~89.5M pixels).  We're in a
        # dedicated child process loading a known-size tile, so disable the
        # check entirely.
        Image.MAX_IMAGE_PIXELS = None

        img = Image.open(io.BytesIO(tif_data))
        arr = np.array(img, dtype=np.float32)

        if arr.shape[0] == 10812 and arr.shape[1] == 10812:
            # USGS 3DEP: 6-pixel boundary buffer on each side — crop to data region
            arr = arr[6:10806, 6:10806]  # -> 10800x10800
            # fall through to the 10800 padding case below

        if arr.shape[0] == 10801 and arr.shape[1] == 10801:
            # Already the right size — no padding needed
            hgt = np.round(arr).astype(np.int16)
            hgt[np.isnan(arr)] = -32768
        elif arr.shape[0] == 10800 and arr.shape[1] == 10800:
            # Pad 10800x10800 -> 10801x10801
            hgt_raw = np.round(arr).astype(np.int16)
            hgt_raw[np.isnan(arr)] = -32768
            hgt = np.zeros((10801, 10801), dtype=np.int16)
            hgt[:10800, :10800] = hgt_raw
            hgt[10800, :10800] = hgt_raw[10799, :]   # duplicate bottom row
            hgt[:10800, 10800] = hgt_raw[:, 10799]   # duplicate right column
            hgt[10800, 10800] = hgt_raw[10799, 10799]  # corner
        else:
            raise ValueError("3DEP: unexpected GeoTIFF shape %s" % str(arr.shape))

        # SRTM HGT is big-endian int16, row 0 = northernmost
        hgt.byteswap(inplace=True)
        return hgt.tobytes()

    def getTile(self, lat, lon):
        """Get a 3DEP tile as an SRTMTile, downloading and converting if needed."""
        lat = int(lat)
        lon = int(lon)
        hgt_file = os.path.join(self.cachedir, self._hgt_filename(lat, lon))

        if os.path.exists(hgt_file):
            try:
                return SRTMTile(hgt_file, lat, lon)
            except InvalidTileError:
                return 0

        # Don't retry tiles that previously failed conversion
        if os.path.exists(hgt_file + ".failed"):
            return 0

        # check if download is already in progress
        global childTileDownload
        mypid = os.getpid()
        if mypid in childTileDownload and childTileDownload[mypid].is_alive():
            return 0

        if self.offline:
            return 0

        # start background download + conversion
        try:
            childTileDownload[mypid] = multiproc.Process(
                target=self._download_and_convert, args=(lat, lon))
            childTileDownload[mypid].start()
        except Exception:
            if mypid in childTileDownload:
                childTileDownload.pop(mypid)
        return 0

    def _download_and_convert(self, lat, lon):
        """Download a 3DEP GeoTIFF tile and convert to HGT (runs in child process)."""
        mp_util.child_close_fds()
        url = self._tile_url(lat, lon)
        hgt_file = os.path.join(self.cachedir, self._hgt_filename(lat, lon))
        try:
            conn = httplib.HTTPSConnection(self.server, timeout=300)
            conn.request("GET", url)
            resp = conn.getresponse()

            # we got an HTTP response — network is working, clear any stale failure sentinel
            try:
                os.unlink(hgt_file + ".failed")
            except Exception:
                pass

            if resp.status == 404 or resp.status == 403:
                # no tile — outside US coverage or ocean
                if self.debug:
                    print("3DEP: no tile for %d,%d (HTTP %d)" % (lat, lon, resp.status))
                self._write_ocean_hgt(hgt_file)
                conn.close()
                return
            if resp.status != 200:
                print("3DEP download failed: HTTP %d for %s" % (resp.status, url))
                conn.close()
                return
            tif_data = resp.read()
            conn.close()

            if self.debug:
                print("3DEP: downloaded %d bytes for %d,%d" % (len(tif_data), lat, lon))

            # convert GeoTIFF to HGT
            try:
                hgt_bytes = self._geotiff_to_hgt(tif_data)
            except Exception as conv_err:
                # Conversion failed — write sentinel to prevent infinite retries
                print("3DEP: conversion failed for %d,%d: %s" % (lat, lon, conv_err))
                try:
                    with open(hgt_file + ".failed", 'w') as f:
                        f.write(str(conv_err))
                except Exception:
                    pass
                return

            # write as .hgt.zip (compatible with SRTMTile loader)
            lat_hemi = 'N' if lat >= 0 else 'S'
            lon_hemi = 'E' if lon >= 0 else 'W'
            inner_name = "%s%02d%s%03d.hgt" % (
                lat_hemi, abs(lat), lon_hemi, abs(lon))

            tmpfile = hgt_file + ".tmp"
            with zipfile.ZipFile(tmpfile, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(inner_name, hgt_bytes)
            try:
                os.unlink(hgt_file)
            except Exception:
                pass
            os.rename(tmpfile, hgt_file)

            if self.debug:
                print("3DEP: cached %s (%d bytes)" % (hgt_file, len(hgt_bytes)))

        except Exception as e:
            print("3DEP download failed for %d,%d: %s" % (lat, lon, e))
            # write failure sentinel to prevent infinite retry spawns
            try:
                with open(hgt_file + ".failed", 'w') as f:
                    f.write(str(e))
            except Exception:
                pass

    @staticmethod
    def _write_ocean_hgt(filepath):
        """Write a minimal ocean HGT zip (all zeros) as a cache marker."""
        data = np.zeros((10801, 10801), dtype=np.int16)
        data.byteswap(inplace=True)
        inner_name = os.path.basename(filepath).replace('.zip', '')
        tmpfile = filepath + ".tmp"
        with zipfile.ZipFile(tmpfile, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(inner_name, data.tobytes())
        try:
            os.unlink(filepath)
        except Exception:
            pass
        os.rename(tmpfile, filepath)


class parseHTMLDirectoryListing(HTMLParser):

    def __init__(self):
        #print("parseHTMLDirectoryListing.__init__")
        HTMLParser.__init__(self)
        self.title="Undefined"
        self.isDirListing = False
        self.dirList=[]
        self.inTitle = False
        self.inHyperLink = False
        self.currAttrs=""
        self.currHref=""

    def handle_starttag(self, tag, attrs):
        #print("Encountered the beginning of a %s tag" % tag)
        if tag=="title":
            self.inTitle = True
        if tag == "a":
            self.inHyperLink = True
            self.currAttrs=attrs
            for attr in attrs:
                if attr[0]=='href':
                    self.currHref = attr[1]


    def handle_endtag(self, tag):
        #print("Encountered the end of a %s tag" % tag)
        if tag=="title":
            self.inTitle = False
        if tag == "a":
            # This is to avoid us adding the parent directory to the list.
            if self.currHref!="":
                self.dirList.append(self.currHref)
            self.currAttrs=""
            self.currHref=""
            self.inHyperLink = False

    def handle_data(self,data):
        if self.inTitle:
            self.title = data
            '''print("title=%s" % data)'''
            if "Index of" in self.title:
                #print("it is an index!!!!")
                self.isDirListing = True
        if self.inHyperLink:
            # We do not include parent directory in listing.
            if  "Parent Directory" in data:
                self.currHref=""

    def getDirListing(self):
        return self.dirList

#DEBUG ONLY
if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser(description='srtm test')

    parser.add_argument("--lat", type=float, default=-35.363261)
    parser.add_argument("--lon", type=float, default=149.165230)
    parser.add_argument("--debug", action='store_true', default=False)
    parser.add_argument("--use-http", action='store_true', default=False)
    parser.add_argument("--database", type=str, default="SRTM3", choices=["SRTM1", "SRTM3"])
    args = parser.parse_args()

    if args.database == "SRTM1":
        downloader = SRTMDownloader(debug=args.debug, use_http=args.use_http, directory="SRTM1")
    else: #SRTM3
        downloader = SRTMDownloader(debug=args.debug, use_http=args.use_http, directory="SRTM3")
    downloader.loadFileList()
    import time
    from math import floor
    start = time.time()
    while time.time() - start < 30:
        tile = downloader.getTile(int(floor(args.lat)), int(floor(args.lon)))
        if tile:
            print("Download took %.1fs alt=%.1f" % (time.time()-start, tile.getAltitudeFromLatLon(args.lat, args.lon)))
            break
        time.sleep(0.2)
