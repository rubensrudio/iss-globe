import argparse
from pathlib import Path

import numpy as np
from skyfield.api import load, wgs84

from iss_globe import check_epoch, load_iss, parse_ts
from triangulation import gnss, stations
from triangulation.core import C_KM_S, ecef_to_geodetic, itrs_km, make_fix
from triangulation.plot import build_triangulation_figure


def print_fix(label, fix):
    print(f"Estimate  : [{label}] lat={fix.lat:.6f}°  lon={fix.lon:.6f}°  alt={fix.alt_km:.4f} km")
    print(f"            error={fix.error_m:.2f} m  rms residual={fix.rms_residual_m:.2f} m  "
          f"iterations={fix.iterations}")
    for k, v in fix.extras.items():
        print(f"            {k}={v:.3f}")


def run_gnss(args, ts):
    when = parse_ts(args.timestamp)
    t = ts.from_datetime(when)
    rng = np.random.default_rng(args.seed)
    receiver = wgs84.latlon(args.lat, args.lon, args.height_m)
    truth = itrs_km(receiver.at(t))

    sats = gnss.synthetic_gps(ts, when)
    obs = gnss.simulate_pseudoranges(sats, receiver, t, args.clock_bias_m, args.sigma_m, args.mask_deg, rng)
    print(f"Time      : {when.isoformat()}")
    print(f"Truth     : receiver lat={args.lat:.6f}°  lon={args.lon:.6f}°  alt={args.height_m / 1000:.4f} km")
    print(f"Satellites: {len(obs.names)} of {len(sats)} above {args.mask_deg:.0f}° ({', '.join(obs.names)})")

    pos, bias_km, res, n = gnss.solve_receiver(obs.sat_xyz_km, obs.rho_km)
    fix = make_fix(pos, truth, res, n, t, clock_bias_m=bias_km * 1000,
                   clock_bias_us=bias_km / C_KM_S * 1e6, **gnss.dop(obs.sat_xyz_km, truth, args.lat, args.lon))
    print_fix("pseudoranges", fix)

    anchors = [(name, *ecef_to_geodetic(xyz, t)[:2]) for name, xyz in zip(obs.names, obs.sat_xyz_km)]
    title = (f"GNSS fix — {when:%Y-%m-%d %H:%M:%S} UTC | {len(obs.names)} satellites, "
             f"σ={args.sigma_m:g} m, PDOP {fix.extras['PDOP']:.2f} | error {fix.error_m:.1f} m")
    return build_triangulation_figure(
        title, anchors, ("Receiver", args.lat, args.lon, args.height_m / 1000),
        [("pseudoranges", fix.lat, fix.lon, fix.alt_km, fix.error_m)],
    )


def run_stations(args, ts):
    sat = load_iss(ts, offline=args.offline)
    when = parse_ts(args.timestamp)
    t = ts.from_datetime(when)
    check_epoch(sat, t)
    rng = np.random.default_rng(args.seed)
    truth = itrs_km(sat.at(t))
    sp = wgs84.subpoint(sat.at(t))
    lat, lon, alt = sp.latitude.degrees, sp.longitude.degrees, sp.elevation.km

    ring = stations.ring_stations(lat, lon, args.n, args.radius_km)
    obs = stations.observe(sat, ring, t, args.sigma_range_m, args.sigma_angle_deg, args.mask_deg, rng)
    print(f"Time      : {when.isoformat()}")
    print(f"Truth     : {sat.name} lat={lat:.6f}°  lon={lon:.6f}°  alt={alt:.4f} km")
    print(f"Stations  : {len(obs.stations)} of {len(ring)} see the ISS above {args.mask_deg:.0f}° "
          f"(elevations {', '.join(f'{e:.1f}°' for e in obs.el_deg)})")

    estimates = []
    if args.method in ("ranges", "both"):
        p, res, n = stations.solve_from_ranges(obs.st_xyz_km, obs.range_km)
        fix = make_fix(p, truth, res, n, t)
        print_fix("ranges", fix)
        estimates.append(("ranges", fix.lat, fix.lon, fix.alt_km, fix.error_m))
    if args.method in ("angles", "both"):
        p, miss = stations.solve_from_angles(obs.st_xyz_km, obs.az_deg, obs.el_deg, obs.stations)
        fix = make_fix(p, truth, miss, 1, t)
        print_fix("angles", fix)
        estimates.append(("angles", fix.lat, fix.lon, fix.alt_km, fix.error_m))

    anchors = [(f"S{i + 1}", st.latitude.degrees, st.longitude.degrees) for i, st in enumerate(obs.stations)]
    title = (f"{sat.name} from {len(obs.stations)} stations — {when:%Y-%m-%d %H:%M:%S} UTC | "
             + " | ".join(f"{e[0]}: {e[4]:.1f} m" for e in estimates))
    return build_triangulation_figure(title, anchors, (sat.name, lat, lon, alt), estimates)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Satellite triangulation study (simulated measurements)")
    sub = ap.add_subparsers(dest="mode", required=True)

    g = sub.add_parser("gnss", help="receiver position and clock bias from GPS pseudoranges")
    g.add_argument("--lat", type=float, default=-23.55, help="receiver latitude, deg")
    g.add_argument("--lon", type=float, default=-46.63, help="receiver longitude, deg")
    g.add_argument("--height-m", type=float, default=0.0, help="receiver height above WGS84, m")
    g.add_argument("--sigma-m", type=float, default=3.0, help="pseudorange noise (1 sigma), m")
    g.add_argument("--clock-bias-m", type=float, default=3000.0, help="receiver clock bias c*dt, m")
    g.add_argument("--out", default="triangulate_gnss.html")

    s = sub.add_parser("stations", help="ISS position from ground-station ranges and/or angles")
    s.add_argument("--offline", action="store_true", help="use embedded ISS TLE")
    s.add_argument("--n", type=int, default=4, help="number of stations")
    s.add_argument("--radius-km", type=float, default=1000.0, help="station ring radius around the ISS subpoint")
    s.add_argument("--method", choices=["ranges", "angles", "both"], default="both")
    s.add_argument("--sigma-range-m", type=float, default=10.0, help="range noise (1 sigma), m")
    s.add_argument("--sigma-angle-deg", type=float, default=0.01, help="azimuth/elevation noise (1 sigma), deg")
    s.add_argument("--out", default="triangulate_stations.html")

    for p in (g, s):
        p.add_argument("--timestamp", help="ISO 8601, assumed UTC if no tz (e.g. 2026-10-05T18:30:00)")
        p.add_argument("--mask-deg", type=float, default=10.0, help="elevation mask, deg")
        p.add_argument("--seed", type=int, default=42, help="random seed for the simulated noise")
        p.add_argument("--no-show", action="store_true", help="only write the HTML, do not open it")
    args = ap.parse_args(argv)

    ts = load.timescale()
    fig = run_gnss(args, ts) if args.mode == "gnss" else run_stations(args, ts)
    fig.write_html(args.out)
    print(f"Saved {Path(args.out).resolve()}")
    if not args.no_show:
        fig.show()


if __name__ == "__main__":
    main()
