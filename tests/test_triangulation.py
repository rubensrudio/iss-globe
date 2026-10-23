from datetime import datetime, timezone

import numpy as np
import pytest
from skyfield.api import load, wgs84

import iss_globe
import triangulate
from triangulation import gnss, microseismic, stations
from triangulation.core import ecef_to_geodetic, gauss_newton, itrs_km

NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
# Close to the embedded 2014 ISS TLE epoch, so SGP4 output is meaningful.
NEAR_EPOCH = datetime(2014, 1, 20, 23, 0, 0, tzinfo=timezone.utc)
SAO_PAULO = (-23.55, -46.63)


@pytest.fixture(scope="module")
def ts():
    return load.timescale()


@pytest.fixture(scope="module")
def gps(ts):
    return gnss.synthetic_gps(ts, NOW)


@pytest.fixture(scope="module")
def iss_setup(ts):
    sat = iss_globe.load_iss(ts, offline=True)
    t = ts.from_datetime(NEAR_EPOCH)
    sp = wgs84.subpoint(sat.at(t))
    ring = stations.ring_stations(sp.latitude.degrees, sp.longitude.degrees, 4, 1000)
    return sat, t, ring, itrs_km(sat.at(t))


def gnss_fix(gps, ts, sigma_m, mask_deg=10.0, seed=42):
    t = ts.from_datetime(NOW)
    rx = wgs84.latlon(*SAO_PAULO)
    obs = gnss.simulate_pseudoranges(gps, rx, t, 3000.0, sigma_m, mask_deg, np.random.default_rng(seed))
    pos, bias_km, _, _ = gnss.solve_receiver(obs.sat_xyz_km, obs.rho_km)
    truth = itrs_km(rx.at(t))
    return obs, pos, bias_km, truth


def test_ecef_to_geodetic_round_trip(ts):
    t = ts.from_datetime(NOW)
    p = wgs84.latlon(*SAO_PAULO, elevation_m=760)
    lat, lon, alt = ecef_to_geodetic(itrs_km(p.at(t)), t)
    # 1e-7 deg of latitude is ~1 cm.
    assert lat == pytest.approx(SAO_PAULO[0], abs=1e-7)
    assert lon == pytest.approx(SAO_PAULO[1], abs=1e-7)
    assert alt == pytest.approx(0.760, abs=1e-5)


def test_gauss_newton_rejects_too_few_measurements():
    with pytest.raises(ValueError, match="at least 2"):
        gauss_newton(lambda x: np.array([x[0] + x[1]]), lambda x: np.array([[1.0, 1.0]]), [0, 0])


def test_synthetic_gps_is_a_gps_like_orbit(gps, ts):
    assert len(gps) == 24
    times = ts.utc(2026, 10, 23, 12, np.arange(0, 720, 10))
    for sat in gps[:4]:
        sp = wgs84.subpoint(sat.at(times))
        assert np.all((20_100 < sp.elevation.km) & (sp.elevation.km < 20_300))
        assert 54 < sp.latitude.degrees.max() < 56


def test_gnss_noise_free_recovers_position_and_clock(gps, ts):
    _, pos, bias_km, truth = gnss_fix(gps, ts, sigma_m=0.0)
    assert np.linalg.norm(pos - truth) * 1000 < 1.0
    assert bias_km * 1000 == pytest.approx(3000.0, abs=1.0)


def test_gnss_noisy_error_is_bounded_by_dop(gps, ts):
    sigma_m = 3.0
    obs, pos, _, truth = gnss_fix(gps, ts, sigma_m)
    pdop = gnss.dop(obs.sat_xyz_km, truth, *SAO_PAULO)["PDOP"]
    assert np.linalg.norm(pos - truth) * 1000 < 4 * sigma_m * pdop


def test_gnss_needs_four_satellites(gps, ts):
    obs, _, _, _ = gnss_fix(gps, ts, sigma_m=0.0)
    with pytest.raises(ValueError):
        gnss.solve_receiver(obs.sat_xyz_km[:3], obs.rho_km[:3])


def test_dop_ordering(gps, ts):
    obs, _, _, truth = gnss_fix(gps, ts, sigma_m=0.0)
    d = gnss.dop(obs.sat_xyz_km, truth, *SAO_PAULO)
    assert d["GDOP"] >= d["PDOP"] >= d["HDOP"] > 0


def test_elevation_mask_drops_satellites(gps, ts):
    t, rx, rng = ts.from_datetime(NOW), wgs84.latlon(*SAO_PAULO), np.random.default_rng(0)
    low = gnss.simulate_pseudoranges(gps, rx, t, 0.0, 0.0, 0.0, rng)
    high = gnss.simulate_pseudoranges(gps, rx, t, 0.0, 0.0, 30.0, rng)
    assert len(low.names) > len(high.names)
    assert np.all(high.elevation_deg >= 30.0)


def test_same_seed_same_result(gps, ts):
    _, a, _, _ = gnss_fix(gps, ts, sigma_m=3.0, seed=7)
    _, b, _, _ = gnss_fix(gps, ts, sigma_m=3.0, seed=7)
    np.testing.assert_array_equal(a, b)


def test_ring_stations_are_at_requested_distance(iss_setup):
    sat, t, ring, _ = iss_setup
    sp = wgs84.subpoint(sat.at(t))  # keeps the ISS height, so rebuild it on the ground
    center = itrs_km(wgs84.latlon(sp.latitude.degrees, sp.longitude.degrees).at(t))
    for st in ring:
        chord = np.linalg.norm(itrs_km(st.at(t)) - center)
        assert chord == pytest.approx(1000, rel=0.01)


@pytest.mark.parametrize("n_stations", [3, 4])
def test_stations_ranges_noise_free(iss_setup, n_stations):
    sat, t, ring, truth = iss_setup
    obs = stations.observe(sat, ring[:n_stations], t, 0.0, 0.0, 10.0, np.random.default_rng(0))
    p, _, _ = stations.solve_from_ranges(obs.st_xyz_km, obs.range_km)
    assert np.linalg.norm(p - truth) * 1000 < 1.0


def test_stations_angles_noise_free(iss_setup):
    sat, t, ring, truth = iss_setup
    obs = stations.observe(sat, ring, t, 0.0, 0.0, 10.0, np.random.default_rng(0))
    p, miss = stations.solve_from_angles(obs.st_xyz_km, obs.az_deg, obs.el_deg, obs.stations)
    assert np.linalg.norm(p - truth) * 1000 < 1.0
    assert np.all(miss * 1000 < 1.0)


def test_stations_noisy_errors_are_bounded(iss_setup):
    sat, t, ring, truth = iss_setup
    obs = stations.observe(sat, ring, t, 10.0, 0.01, 10.0, np.random.default_rng(42))
    p_r, _, _ = stations.solve_from_ranges(obs.st_xyz_km, obs.range_km)
    p_a, _ = stations.solve_from_angles(obs.st_xyz_km, obs.az_deg, obs.el_deg, obs.stations)
    assert np.linalg.norm(p_r - truth) * 1000 < 100
    # 0.01 deg at ~1,150 km of slant range is ~200 m per line of sight.
    assert np.linalg.norm(p_a - truth) * 1000 < 1000


def test_stations_below_mask_are_dropped(iss_setup):
    sat, t, ring, _ = iss_setup
    obs = stations.observe(sat, ring, t, 0.0, 0.0, 30.0, np.random.default_rng(0))
    assert len(obs.stations) == 0


def test_cli_gnss_writes_html(tmp_path):
    out = tmp_path / "gnss.html"
    triangulate.main(["gnss", "--timestamp", NOW.isoformat(), "--no-show", "--out", str(out)])
    assert out.stat().st_size > 0


def test_cli_stations_writes_html(tmp_path):
    out = tmp_path / "stations.html"
    triangulate.main(["stations", "--offline", "--timestamp", NEAR_EPOCH.isoformat(),
                      "--no-show", "--out", str(out)])
    assert out.stat().st_size > 0


EVENT = np.array([0.3, -0.2, -2.5])
V_KM_S = 4.5
T0_S = 0.25


def micro_layouts():
    surface = microseismic.surface_array()
    return {
        "surface": surface,
        "downhole": microseismic.downhole_array(),
        "combined": np.vstack([surface, microseismic.downhole_array(wells=microseismic.DEFAULT_WELLS[:1])]),
    }


def locate(geo, sigma_ms=0.0, v_assumed=V_KM_S, seed=42):
    arrivals = microseismic.simulate_arrivals(geo, EVENT, T0_S, V_KM_S, sigma_ms, np.random.default_rng(seed))
    p, t0, _, _ = microseismic.locate_event(geo, arrivals, v_assumed)
    return p, t0


@pytest.mark.parametrize("layout", ["surface", "downhole", "combined"])
def test_microseismic_noise_free_recovers_event(layout):
    p, t0 = locate(micro_layouts()[layout])
    assert np.linalg.norm(p - EVENT) * 1000 < 1.0
    assert abs(t0 - T0_S) < 1e-6
    assert p[2] < 0


def test_surface_array_resolves_depth_worse_than_horizontal():
    layouts = micro_layouts()
    surface = microseismic.event_dop(layouts["surface"], EVENT)
    combined = microseismic.event_dop(layouts["combined"], EVENT)
    assert surface["VDOP"] > surface["HDOP"]
    assert combined["VDOP"] < surface["VDOP"]


def test_single_vertical_well_cannot_resolve_azimuth():
    geo = microseismic.downhole_array(wells=microseismic.DEFAULT_WELLS[:1])
    with pytest.raises(ValueError, match="degenerate"):
        locate(geo)


def test_two_wells_are_mirror_ambiguous_three_are_not():
    two = microseismic.downhole_array(wells=microseismic.DEFAULT_WELLS[:2])
    assert microseismic.mirror_ambiguous(two)
    assert not microseismic.mirror_ambiguous(microseismic.downhole_array())
    assert not microseismic.mirror_ambiguous(microseismic.surface_array())


def test_wrong_velocity_biases_the_location():
    p, _ = locate(micro_layouts()["surface"], v_assumed=4.4)
    assert np.linalg.norm(p - EVENT) * 1000 > 10


@pytest.mark.parametrize("layout", ["surface", "downhole", "combined"])
def test_microseismic_noisy_error_is_bounded_by_dop(layout):
    geo = micro_layouts()[layout]
    sigma_ms = 1.0
    p, _ = locate(geo, sigma_ms=sigma_ms)
    pdop = microseismic.event_dop(geo, EVENT)["PDOP"]
    sigma_range_m = V_KM_S * sigma_ms  # km/s * ms = m
    assert np.linalg.norm(p - EVENT) * 1000 < 4 * sigma_range_m * pdop


def test_cli_microseismic_writes_html(tmp_path):
    out = tmp_path / "micro.html"
    triangulate.main(["microseismic", "--no-show", "--out", str(out)])
    assert out.stat().st_size > 0


def test_cli_microseismic_reports_degenerate_single_well(tmp_path, capsys):
    triangulate.main(["microseismic", "--wells", "1", "--no-show", "--out", str(tmp_path / "m.html")])
    assert "degenerate geometry" in capsys.readouterr().out
