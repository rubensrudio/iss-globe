import sys
from datetime import datetime, timezone

import numpy as np
import pytest
from skyfield.api import load

import iss_globe

# Close to the embedded 2014 TLE epoch, so SGP4 output is meaningful.
NEAR_EPOCH = datetime(2014, 1, 20, 23, 0, 0, tzinfo=timezone.utc)

# Inclination is ~51.6 deg, but WGS84 geodetic latitude peaks slightly higher
# (~51.8 deg) because of Earth's flattening.
MAX_GEODETIC_LAT = 52.0


@pytest.fixture(scope="module")
def ts():
    return load.timescale()


@pytest.fixture(scope="module")
def sat(ts):
    return iss_globe.load_iss(ts, offline=True)


def test_parse_ts_naive_is_utc():
    assert iss_globe.parse_ts("2026-10-05T18:30:00") == datetime(2026, 10, 5, 18, 30, tzinfo=timezone.utc)


def test_parse_ts_converts_offset_to_utc():
    assert iss_globe.parse_ts("2026-10-05T15:30:00-03:00") == datetime(2026, 10, 5, 18, 30, tzinfo=timezone.utc)


def test_parse_ts_defaults_to_now():
    assert abs((iss_globe.parse_ts(None) - datetime.now(timezone.utc)).total_seconds()) < 5


def test_offline_uses_embedded_tle(sat):
    assert sat.model.satnum == 25544


def test_subpoint_is_physically_plausible(sat, ts):
    lat, lon, alt = iss_globe.subpoint_at(sat, ts.from_datetime(NEAR_EPOCH))
    assert 400 < alt < 440
    assert abs(lat) <= MAX_GEODETIC_LAT
    assert -180 <= lon <= 180


def test_ground_track_has_201_points_within_inclination(sat, ts):
    lat, lon = iss_globe.ground_track(sat, ts, NEAR_EPOCH)
    assert len(lat) == len(lon) == 201
    assert np.all(np.abs(lat) <= MAX_GEODETIC_LAT)


def test_build_figure_breaks_line_at_antimeridian():
    track_lat = np.array([10.0, 11.0, 12.0, 13.0])
    track_lon = np.array([170.0, 179.0, -179.0, -170.0])
    fig = iss_globe.build_figure(12.0, -179.0, 420.0, NEAR_EPOCH, track_lat, track_lon, "ISS")
    lon = np.array(fig.data[0].lon, dtype=float)
    assert len(lon) == 5
    assert np.isnan(lon[2])


def test_refuses_timestamp_far_from_tle_epoch(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["iss_globe.py", "--offline", "--timestamp", "2026-10-05T18:30:00"])
    with pytest.raises(SystemExit, match="days from the requested time"):
        iss_globe.main()
