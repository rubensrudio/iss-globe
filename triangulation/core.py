"""Shared geometry and least-squares tools. All internal distances are in km."""

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from skyfield.api import wgs84
from skyfield.framelib import itrs
from skyfield.toposlib import ITRSPosition
from skyfield.units import Distance

C_KM_S = 299_792.458


@dataclass(frozen=True)
class Fix:
    xyz_km: np.ndarray
    lat: float
    lon: float
    alt_km: float
    error_m: float
    rms_residual_m: float
    iterations: int
    extras: dict = field(default_factory=dict)


def itrs_km(position) -> np.ndarray:
    """Earth-fixed (ITRS/ECEF) coordinates of a Skyfield position, in km."""
    return position.frame_xyz(itrs).km


def ecef_to_geodetic(xyz_km, t):
    """WGS84 latitude (deg), longitude (deg) and height (km) of an ECEF point."""
    gp = wgs84.geographic_position_of(ITRSPosition(Distance(km=np.asarray(xyz_km))).at(t))
    return gp.latitude.degrees, gp.longitude.degrees, gp.elevation.km


def enu_basis(lat_deg: float, lon_deg: float) -> np.ndarray:
    """3x3 matrix whose rows are the local East, North and Up unit vectors in ECEF."""
    phi, lam = np.radians(lat_deg), np.radians(lon_deg)
    return np.array([
        [-np.sin(lam), np.cos(lam), 0.0],
        [-np.sin(phi) * np.cos(lam), -np.sin(phi) * np.sin(lam), np.cos(phi)],
        [np.cos(phi) * np.cos(lam), np.cos(phi) * np.sin(lam), np.sin(phi)],
    ])


def gauss_newton(
    residual: Callable[[np.ndarray], np.ndarray],
    jacobian: Callable[[np.ndarray], np.ndarray],
    x0,
    tol: float = 1e-9,
    max_iter: int = 20,
) -> tuple[np.ndarray, int]:
    """Minimize ||residual(x)||^2 by linearizing: J dx = -r, x <- x + dx.

    Raises ValueError when there are fewer measurements than unknowns, when the
    geometry is degenerate (rank-deficient Jacobian) or when it does not converge.
    """
    x = np.asarray(x0, dtype=float).copy()
    for i in range(1, max_iter + 1):
        r, J = residual(x), jacobian(x)
        if len(r) < len(x):
            raise ValueError(f"need at least {len(x)} measurements, got {len(r)}")
        if np.linalg.matrix_rank(J) < len(x):
            raise ValueError("degenerate geometry: Jacobian is rank-deficient")
        dx = np.linalg.lstsq(J, -r, rcond=None)[0]
        x += dx
        if np.linalg.norm(dx) < tol:
            return x, i
    raise ValueError(f"Gauss-Newton did not converge in {max_iter} iterations")


def make_fix(xyz_km, truth_km, residuals_km, iterations: int, t, **extras) -> Fix:
    lat, lon, alt = ecef_to_geodetic(xyz_km, t)
    return Fix(
        xyz_km=np.asarray(xyz_km),
        lat=float(lat), lon=float(lon), alt_km=float(alt),
        error_m=float(np.linalg.norm(np.asarray(xyz_km) - truth_km) * 1000),
        rms_residual_m=float(np.sqrt(np.mean(np.square(residuals_km))) * 1000),
        iterations=iterations,
        extras=extras,
    )
