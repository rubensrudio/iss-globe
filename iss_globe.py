import argparse
import ssl
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import certifi
import numpy as np
import plotly.graph_objects as go
from skyfield.api import EarthSatellite, load, wgs84

TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE"

FALLBACK_TLE = (
    "ISS (ZARYA)",
    "1 25544U 98067A   14020.93268519  .00009878  00000-0  18200-3 0  5082",
    "2 25544  51.6498 109.4756 0003572  55.9686 274.8005 15.49815350868473",
)


def load_iss(ts, offline: bool = False, cache: str = "iss.tle", max_age_h: float = 6.0):
    if not offline:
        try:
            path = Path(cache)
            fresh = path.exists() and (time.time() - path.stat().st_mtime) < max_age_h * 3600
            if not fresh:
                req = urllib.request.Request(TLE_URL, headers={"User-Agent": "iss-globe/1.0"})
                ctx = ssl.create_default_context(cafile=certifi.where())
                with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                    path.write_text(resp.read().decode("utf-8"))
            lines = [ln.rstrip() for ln in path.read_text().splitlines() if ln.strip()]
            if len(lines) >= 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
                return EarthSatellite(lines[1], lines[2], lines[0].strip(), ts)
            raise ValueError(f"unexpected TLE content: {lines[:3]}")
        except Exception as exc:
            print(f"[warn] could not get a fresh TLE ({exc!r}); using embedded fallback.")
    name, l1, l2 = FALLBACK_TLE
    return EarthSatellite(l1, l2, name, ts)


def subpoint_at(sat: EarthSatellite, t):
    geocentric = sat.at(t)
    sp = wgs84.subpoint(geocentric)
    return sp.latitude.degrees, sp.longitude.degrees, sp.elevation.km


def ground_track(sat, ts, center: datetime, minutes: int = 50, step_s: int = 30):
    n = int(minutes * 60 / step_s)
    offsets = np.arange(-n, n + 1) * step_s
    t = ts.utc(
        center.year, center.month, center.day,
        center.hour, center.minute, center.second + offsets,
    )
    sp = wgs84.subpoint(sat.at(t))
    return sp.latitude.degrees, sp.longitude.degrees


def build_figure(lat, lon, alt, when, track_lat, track_lon, sat_name):
    fig = go.Figure()
    lat_t, lon_t = track_lat.copy(), track_lon.copy()
    jumps = np.where(np.abs(np.diff(lon_t)) > 180)[0]
    lat_t = np.insert(lat_t, jumps + 1, np.nan)
    lon_t = np.insert(lon_t, jumps + 1, np.nan)

    fig.add_trace(go.Scattergeo(lat=lat_t, lon=lon_t, mode="lines",
                                line=dict(width=2, color="orange"),
                                name="Ground track (±50 min)"))
    fig.add_trace(go.Scattergeo(
        lat=[lat], lon=[lon], mode="markers+text", text=["ISS"],
        textposition="top center",
        marker=dict(size=11, color="red", symbol="circle"),
        name=f"{sat_name}",
        hovertemplate=f"lat {lat:.3f}°<br>lon {lon:.3f}°<br>alt {alt:.1f} km<extra></extra>",
    ))
    fig.update_geos(
        projection_type="orthographic",
        projection_rotation=dict(lon=lon, lat=lat),
        showland=True, landcolor="#2e4a3a",
        showocean=True, oceancolor="#0b2a4a",
        showcountries=True, countrycolor="#8aa",
        showcoastlines=True, coastlinecolor="#cde",
        lataxis_showgrid=True, lonaxis_showgrid=True,
    )
    fig.update_layout(
        title=f"{sat_name} — {when:%Y-%m-%d %H:%M:%S} UTC | "
              f"lat {lat:.2f}°, lon {lon:.2f}°, alt {alt:.0f} km",
        template="plotly_dark", height=700, margin=dict(l=0, r=0, t=60, b=0),
    )
    return fig


def parse_ts(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timestamp", help="ISO 8601, assumed UTC if no tz (e.g. 2026-10-05T18:30:00)")
    ap.add_argument("--offline", action="store_true", help="use embedded TLE")
    ap.add_argument("--out", default="iss_globe.html")
    args = ap.parse_args()

    ts = load.timescale()
    sat = load_iss(ts, offline=args.offline)
    when = parse_ts(args.timestamp)
    t = ts.from_datetime(when)

    days_from_epoch = t - sat.epoch
    if abs(days_from_epoch) > 30:
        raise SystemExit(
            f"TLE epoch is {days_from_epoch:+.0f} days from the requested time: SGP4 result "
            "would be meaningless (the orbit decays/drifts). Fix the download, or use "
            "--timestamp near the TLE epoch."
        )
    lat, lon, alt = subpoint_at(sat, t)
    print(f"TLE epoch : {sat.epoch.utc_iso()}  ({days_from_epoch:+.2f} days from requested time)")
    print(f"Time      : {when.isoformat()}")
    print(f"Subpoint  : lat={lat:.4f}°  lon={lon:.4f}°  alt={alt:.1f} km")
    if abs(days_from_epoch) > 7:
        print("[warn] TLE is far from the requested time: SGP4 error grows "
              "~1-3 km/day; treat result as approximate.")

    tlat, tlon = ground_track(sat, ts, when)
    fig = build_figure(lat, lon, alt, when, tlat, tlon, sat.name)
    fig.write_html(args.out)
    print(f"Saved {Path(args.out).resolve()}")
    fig.show()


if __name__ == "__main__":
    main()