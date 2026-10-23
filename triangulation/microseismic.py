"""Microseismic event location (Geiger's method), the oil & gas twin of a GNSS fix.

Arrival at geophone i: t_i = t0 + ||r_i - p|| / v + noise. Multiplying by v gives
v * t_i = ||r_i - p|| + v * t0, the GNSS pseudorange with v * t0 as the "clock bias".
Unknowns: (x, y, z, t0). Local frame in km: x East, y North, z Up (depth is z < 0).
Simplifications: homogeneous P-wave velocity, straight rays, no statics or anisotropy.
"""

import numpy as np

from .core import dop_from_geometry, solve_range_and_bias

# Three non-collinear monitoring wells: 1 well leaves azimuth undetermined and
# 2 wells leave a mirror solution across the vertical plane through them.
DEFAULT_WELLS = ((0.6, 0.0), (0.0, 0.6), (-0.6, -0.6))


def surface_array(n_side: int = 5, spacing_km: float = 0.5) -> np.ndarray:
    """n_side x n_side grid of geophones at z = 0, centered on the origin."""
    c = (np.arange(n_side) - (n_side - 1) / 2) * spacing_km
    xx, yy = np.meshgrid(c, c)
    return np.column_stack([xx.ravel(), yy.ravel(), np.zeros(xx.size)])


def downhole_array(wells=DEFAULT_WELLS, top_km: float = 1.8, bottom_km: float = 2.8,
                   levels: int = 8) -> np.ndarray:
    """Vertical strings of geophones, one per monitoring well at (x, y), between two depths."""
    z = -np.linspace(top_km, bottom_km, levels)
    return np.array([(x, y, zi) for x, y in wells for zi in z])


def simulate_arrivals(geophones: np.ndarray, event_xyz, t0_s: float, v_km_s: float,
                      sigma_ms: float, rng: np.random.Generator) -> np.ndarray:
    dist = np.linalg.norm(geophones - np.asarray(event_xyz), axis=1)
    return t0_s + dist / v_km_s + rng.normal(0, sigma_ms / 1000, len(geophones))


def grid_start(geophones: np.ndarray, arrivals_s: np.ndarray, v_km_s: float,
               max_depth_km: float = 5.0, n: int = 24) -> list[float]:
    """Best node of a coarse grid below ground, with t0 eliminated as the mean residual.

    Only z < 0 is searched: a surface-only array cannot tell the event from its
    mirror image above ground, and the grid keeps the real one.
    """
    lo, hi = geophones[:, :2].min(axis=0) - 1.0, geophones[:, :2].max(axis=0) + 1.0
    xs, ys = np.linspace(lo[0], hi[0], n), np.linspace(lo[1], hi[1], n)
    zs = -np.linspace(0.05, max_depth_km, n)
    nodes = np.stack(np.meshgrid(xs, ys, zs, indexing="ij"), axis=-1).reshape(-1, 3)
    tt = np.linalg.norm(nodes[:, None, :] - geophones[None], axis=2) / v_km_s
    dt = arrivals_s - tt
    t0 = dt.mean(axis=1)
    best = np.argmin(((dt - t0[:, None]) ** 2).sum(axis=1))
    return [*nodes[best], v_km_s * t0[best]]


def locate_event(geophones: np.ndarray, arrivals_s: np.ndarray, v_km_s: float,
                 x0=None) -> tuple[np.ndarray, float, np.ndarray, int]:
    """Return (event_xyz_km, t0_s, residuals_s, iterations).

    Coarse grid search, then Geiger's Gauss-Newton refinement. A single vertical
    well cannot resolve azimuth (times are symmetric around it): ValueError.
    """
    if x0 is None:
        x0 = grid_start(geophones, arrivals_s, v_km_s)
    p, b, res_km, n = solve_range_and_bias(geophones, v_km_s * arrivals_s, x0)
    return p, b / v_km_s, res_km / v_km_s, n


def mirror_ambiguous(geophones: np.ndarray, tol_km: float = 1e-6) -> bool:
    """True when all geophones lie in one vertical plane (e.g. two wells, no surface array).

    Arrival times are then symmetric across that plane, so the event and its mirror
    image fit equally well and the solver may return either one.
    """
    xy = geophones[:, :2] - geophones[:, :2].mean(axis=0)
    return bool(np.linalg.svd(xy, compute_uv=False)[1] < tol_km)


def event_dop(geophones: np.ndarray, event_xyz) -> dict[str, float]:
    """DOP for the event; the local frame already is East-North-Up."""
    return dop_from_geometry(geophones, np.asarray(event_xyz, dtype=float))
