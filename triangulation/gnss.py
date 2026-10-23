"""GNSS-style fix: receiver position and clock bias from pseudoranges to 4+ satellites.

Pseudorange model: rho_i = ||r_i - p|| + b + noise, where b = c * dt is the receiver
clock bias expressed as a distance. Unknowns: x = (px, py, pz, b).
Simplifications: no light-time, no Sagnac (Earth rotation during flight), no atmosphere.
"""

from datetime import datetime, timezone
from typing import NamedTuple

import numpy as np
from sgp4.api import WGS72, Satrec
from skyfield.api import EarthSatellite

from .core import dop_from_geometry, enu_basis, itrs_km, solve_range_and_bias

SGP4_EPOCH0 = datetime(1949, 12, 31, tzinfo=timezone.utc)
GPS_REV_PER_DAY = 2.0056  # half a sidereal day, ~20,200 km altitude
GPS_INCLINATION_DEG = 55.0


class Pseudoranges(NamedTuple):
    names: list[str]
    sat_xyz_km: np.ndarray  # (N, 3) ECEF
    rho_km: np.ndarray  # (N,)
    elevation_deg: np.ndarray  # (N,)


def synthetic_gps(ts, epoch: datetime, planes: int = 6, per_plane: int = 4) -> list[EarthSatellite]:
    """A Walker-like 24-satellite GPS constellation, built directly as SGP4 elements.

    Not a real almanac: circular orbits, RAAN every 360/planes deg, slots evenly spaced
    in each plane and shifted by 15 deg from one plane to the next.
    """
    epoch_days = (epoch - SGP4_EPOCH0).total_seconds() / 86400
    no_kozai = GPS_REV_PER_DAY * 2 * np.pi / 1440  # rad/min
    sats = []
    for p in range(planes):
        for s in range(per_plane):
            satrec = Satrec()
            satrec.sgp4init(
                WGS72, "i", 90000 + p * per_plane + s, epoch_days,
                0.0, 0.0, 0.0,  # bstar, ndot, nddot
                1e-4,  # eccentricity
                0.0,  # argument of perigee
                np.radians(GPS_INCLINATION_DEG),
                np.radians(s * 360 / per_plane + p * 15),  # mean anomaly
                no_kozai,
                np.radians(p * 360 / planes),  # RAAN
            )
            sat = EarthSatellite.from_satrec(satrec, ts)
            sat.name = f"GPS-{chr(ord('A') + p)}{s + 1}"
            sats.append(sat)
    return sats


def simulate_pseudoranges(sats, receiver, t, clock_bias_m: float, sigma_m: float,
                          mask_deg: float, rng: np.random.Generator) -> Pseudoranges:
    """Pseudoranges from the satellites above the elevation mask of `receiver`."""
    rx = itrs_km(receiver.at(t))
    names, xyz, elev = [], [], []
    for sat in sats:
        el = (sat - receiver).at(t).altaz()[0].degrees
        if el >= mask_deg:
            names.append(sat.name)
            xyz.append(itrs_km(sat.at(t)))
            elev.append(el)
    xyz = np.array(xyz).reshape(-1, 3)
    rho = np.linalg.norm(xyz - rx, axis=1) + (clock_bias_m + rng.normal(0, sigma_m, len(xyz))) / 1000
    return Pseudoranges(names, xyz, rho, np.array(elev))


def solve_receiver(sat_xyz_km: np.ndarray, rho_km: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, int]:
    """Return (position_km, clock_bias_km, residuals_km, iterations), starting at Earth's center."""
    return solve_range_and_bias(sat_xyz_km, rho_km, np.zeros(4))


def dop(sat_xyz_km: np.ndarray, rx_xyz_km: np.ndarray, lat: float, lon: float) -> dict[str, float]:
    """GNSS dilution of precision, with H/V taken in the receiver's local East-North-Up frame."""
    return dop_from_geometry(sat_xyz_km, rx_xyz_km, enu_basis(lat, lon))
