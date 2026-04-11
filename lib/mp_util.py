"""Minimal subset of MAVProxy mp_util needed by srtm.py and the terrain sampler."""
import os
import math
from math import cos, sin, tan, atan2, sqrt, radians, degrees, pi, log, fmod

radius_of_earth = 6378100.0

child_fd_list = []


def mkdir_p(dir):
    """like mkdir -p"""
    if not dir:
        return
    if dir.endswith("/") or dir.endswith("\\"):
        mkdir_p(dir[:-1])
        return
    if os.path.isdir(dir):
        return
    mkdir_p(os.path.dirname(dir))
    try:
        os.mkdir(dir)
    except Exception:
        pass


def child_close_fds():
    """Close file descriptors that a child process should not inherit."""
    global child_fd_list
    while len(child_fd_list) > 0:
        fd = child_fd_list.pop(0)
        try:
            os.close(fd)
        except Exception:
            pass


def child_fd_list_add(fd):
    global child_fd_list
    child_fd_list.append(fd)


def child_fd_list_remove(fd):
    global child_fd_list
    try:
        child_fd_list.remove(fd)
    except Exception:
        pass


def gps_distance(lat1, lon1, lat2, lon2):
    """Distance in metres between two points (degrees) along rhumb line."""
    lat1, lat2, lon1, lon2 = radians(lat1), radians(lat2), radians(lon1), radians(lon2)
    if abs(lat2 - lat1) < 1.0e-15:
        q = cos(lat1)
    else:
        q = (lat2 - lat1) / log(tan(lat2 / 2 + pi / 4) / tan(lat1 / 2 + pi / 4))
    d = sqrt((lat2 - lat1) ** 2 + q ** 2 * (lon2 - lon1) ** 2)
    return d * radius_of_earth


def gps_bearing(lat1, lon1, lat2, lon2):
    """Rhumb bearing in degrees 0-360 from point 1 to point 2."""
    lat1, lat2, lon1, lon2 = radians(lat1), radians(lat2), radians(lon1), radians(lon2)
    tc = -fmod(atan2(lon1 - lon2, log(tan(lat2 / 2 + pi / 4) / tan(lat1 / 2 + pi / 4))), 2 * pi)
    if tc < 0:
        tc += 2 * pi
    return degrees(tc)
