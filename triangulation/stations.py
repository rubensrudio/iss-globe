"""Ground stations locating the ISS, by ranges (multilateration) or by angles (lines of sight).

Ranges: ||p - s_i|| = r_i, unknown p = (x, y, z), solved by Gauss-Newton.
Angles: each (azimuth, elevation) defines a line s_i + k * u_i; the least-squares
point closest to all lines solves  sum(I - u u^T) p = sum(I - u u^T) s_i.
"""

from typing import NamedTuple

import numpy as np
from skyfield.api import wgs84

from .core import enu_basis, gauss_newton, itrs_km

MEAN_EARTH_RADIUS_KM = 6371.0


class StationObs(NamedTuple):
    stations: list  # skyfield GeographicPosition, only the ones above the mask
    st_xyz_km: np.ndarray  # (N, 3) ECEF
    range_km: np.ndarray
    az_deg: np.ndarray
    el_deg: np.ndarray


def ring_stations(lat: float, lon: float, n: int, radius_km: float) -> list:
    """n stations evenly spaced on a circle of `radius_km` (great-circle) around (lat, lon)."""
    phi1, lam1 = np.radians(lat), np.radians(lon)
    d = radius_km / MEAN_EARTH_RADIUS_KM
    stations = []
    for brg in np.radians(np.arange(n) * 360 / n):
        phi2 = np.arcsin(np.sin(phi1) * np.cos(d) + np.cos(phi1) * np.sin(d) * np.cos(brg))
        lam2 = lam1 + np.arctan2(np.sin(brg) * np.sin(d) * np.cos(phi1),
                                 np.cos(d) - np.sin(phi1) * np.sin(phi2))
        lon2 = (np.degrees(lam2) + 180) % 360 - 180
        stations.append(wgs84.latlon(np.degrees(phi2), lon2))
    return stations


def observe(sat, stations, t, sigma_range_m: float, sigma_angle_deg: float,
            mask_deg: float, rng: np.random.Generator) -> StationObs:
    """Noisy range, azimuth and elevation from each station that sees `sat` above the mask."""
    kept, xyz, rng_km, az, el = [], [], [], [], []
    for st in stations:
        alt_, az_, dist = (sat - st).at(t).altaz()
        if alt_.degrees >= mask_deg:
            kept.append(st)
            xyz.append(itrs_km(st.at(t)))
            rng_km.append(dist.km + rng.normal(0, sigma_range_m) / 1000)
            az.append(az_.degrees + rng.normal(0, sigma_angle_deg))
            el.append(alt_.degrees + rng.normal(0, sigma_angle_deg))
    return StationObs(kept, np.array(xyz).reshape(-1, 3), np.array(rng_km), np.array(az), np.array(el))


def solve_from_ranges(st_xyz_km: np.ndarray, range_km: np.ndarray,
                      height_guess_km: float = 400.0) -> tuple[np.ndarray, np.ndarray, int]:
    """Return (position_km, residuals_km, iterations).

    Starts above the stations' centroid: with exactly 3 stations there is a mirror
    solution below their plane, and this start converges to the one in the sky.
    """
    c = st_xyz_km.mean(axis=0)
    x0 = c / np.linalg.norm(c) * (np.linalg.norm(c) + height_guess_km)

    def residual(p):
        return np.linalg.norm(p - st_xyz_km, axis=1) - range_km

    def jacobian(p):
        d = p - st_xyz_km
        return d / np.linalg.norm(d, axis=1)[:, None]

    p, n = gauss_newton(residual, jacobian, x0)
    return p, residual(p), n


def line_of_sight(az_deg, el_deg, lat: float, lon: float) -> np.ndarray:
    """ECEF unit vector pointing at (azimuth from north, elevation) seen from (lat, lon)."""
    az, el = np.radians(az_deg), np.radians(el_deg)
    u_enu = np.array([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)])
    return enu_basis(lat, lon).T @ u_enu


def solve_from_angles(st_xyz_km: np.ndarray, az_deg, el_deg, stations) -> tuple[np.ndarray, np.ndarray]:
    """Return (position_km, perpendicular miss distance of each line, km). Closed form."""
    if len(st_xyz_km) < 2:
        raise ValueError(f"need at least 2 stations, got {len(st_xyz_km)}")
    u = np.array([line_of_sight(a, e, st.latitude.degrees, st.longitude.degrees)
                  for a, e, st in zip(az_deg, el_deg, stations)])
    proj = np.eye(3)[None] - u[:, :, None] * u[:, None, :]  # (N, 3, 3) projectors I - u u^T
    A = proj.sum(axis=0)
    if np.linalg.matrix_rank(A) < 3:
        raise ValueError("degenerate geometry: lines of sight are parallel")
    p = np.linalg.solve(A, np.einsum("nij,nj->i", proj, st_xyz_km))
    miss = np.linalg.norm(np.einsum("nij,nj->ni", proj, p - st_xyz_km), axis=1)
    return p, miss
