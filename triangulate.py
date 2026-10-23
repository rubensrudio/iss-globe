import argparse
from pathlib import Path

import numpy as np
from skyfield.api import load, wgs84

from iss_globe import check_epoch, load_iss, parse_ts
from triangulation import gnss, microseismic, stations
from triangulation.core import C_KM_S, ecef_to_geodetic, itrs_km, make_fix
from triangulation.plot import build_microseismic_figure, build_triangulation_figure


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


MICRO_T0_S = 0.25  # arbitrary origin time of the simulated event


def run_microseismic(args):
    v_true = args.v_km_s
    v_used = args.v_assumed_km_s or v_true
    event = np.array([args.event_x_km, args.event_y_km, -args.depth_km])
    groups = {"Surface": microseismic.surface_array()}
    for k, well in enumerate(microseismic.DEFAULT_WELLS[:args.wells], start=1):
        groups[f"Well {k}"] = microseismic.downhole_array(wells=[well])
    layouts = {
        "surface": ["Surface"],
        "downhole": [g for g in groups if g.startswith("Well")],
        "combined": ["Surface", "Well 1"],
    }
    chosen = list(layouts) if args.array == "compare" else [args.array]

    print(f"Event     : x={event[0]:.3f} km  y={event[1]:.3f} km  depth={args.depth_km:.3f} km  t0={MICRO_T0_S:.3f} s")
    print(f"Velocity  : true {v_true:g} km/s, assumed {v_used:g} km/s | picking noise σ={args.sigma_ms:g} ms")
    print(f"{'layout':<10}{'geophones':>10}{'horiz m':>10}{'Δdepth m':>10}{'Δt0 ms':>9}"
          f"{'HDOP':>7}{'VDOP':>7}{'rms ms':>8}")

    estimates, mirrored = [], []
    for name in chosen:
        geo = np.vstack([groups[g] for g in layouts[name]])
        arrivals = microseismic.simulate_arrivals(geo, event, MICRO_T0_S, v_true, args.sigma_ms,
                                                  np.random.default_rng(args.seed))
        try:
            p, t0, res_s, _ = microseismic.locate_event(geo, arrivals, v_used)
        except ValueError:
            print(f"{name:<10}{len(geo):>10}   degenerate geometry (azimuth undetermined)")
            continue
        d = microseismic.event_dop(geo, event)
        err = p - event
        flag = "  (mirror?)" if microseismic.mirror_ambiguous(geo) else ""
        print(f"{name:<10}{len(geo):>10}{np.hypot(*err[:2]) * 1000:>10.1f}{-err[2] * 1000:>10.1f}"
              f"{(t0 - MICRO_T0_S) * 1000:>9.2f}{d['HDOP']:>7.2f}{d['VDOP']:>7.2f}"
              f"{np.sqrt(np.mean(res_s ** 2)) * 1000:>8.2f}{flag}")
        if flag:
            mirrored.append(name)
        estimates.append((name, p, float(np.linalg.norm(err) * 1000)))
    print("Δdepth > 0 means the estimate is deeper than the event. "
          "Expected position error ≈ v·σ·PDOP.")
    if mirrored:
        print(f"[warn] {', '.join(mirrored)}: all geophones lie in one vertical plane, so the event's "
              "mirror image across it fits equally well. Add a well or surface geophones.")

    used = list(dict.fromkeys(g for name in chosen for g in layouts[name]))
    title = (f"Microseismic event at {args.depth_km:g} km — v {v_true:g} km/s (assumed {v_used:g}), "
             f"σ {args.sigma_ms:g} ms | " + " | ".join(f"{e[0]}: {e[2]:.1f} m" for e in estimates))
    return build_microseismic_figure(title, [(g, groups[g]) for g in used], event, estimates)


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

    m = sub.add_parser("microseismic", help="locate a microseismic event from geophone arrival times")
    m.add_argument("--array", choices=["surface", "downhole", "combined", "compare"], default="compare",
                   help="geophone layout; compare solves all three")
    m.add_argument("--wells", type=int, choices=[1, 2, 3], default=3, help="monitoring wells in the downhole array")
    m.add_argument("--event-x-km", type=float, default=0.3, help="event East coordinate, km")
    m.add_argument("--event-y-km", type=float, default=-0.2, help="event North coordinate, km")
    m.add_argument("--depth-km", type=float, default=2.5, help="event depth, km")
    m.add_argument("--v-km-s", type=float, default=4.5, help="true P-wave velocity, km/s")
    m.add_argument("--v-assumed-km-s", type=float, help="velocity used to locate (default: the true one)")
    m.add_argument("--sigma-ms", type=float, default=1.0, help="arrival-time picking noise (1 sigma), ms")
    m.add_argument("--out", default="triangulate_microseismic.html")

    for p in (g, s):
        p.add_argument("--timestamp", help="ISO 8601, assumed UTC if no tz (e.g. 2026-10-05T18:30:00)")
        p.add_argument("--mask-deg", type=float, default=10.0, help="elevation mask, deg")
    for p in (g, s, m):
        p.add_argument("--seed", type=int, default=42, help="random seed for the simulated noise")
        p.add_argument("--no-show", action="store_true", help="only write the HTML, do not open it")
    args = ap.parse_args(argv)

    if args.mode == "microseismic":
        fig = run_microseismic(args)
    else:
        ts = load.timescale()
        fig = run_gnss(args, ts) if args.mode == "gnss" else run_stations(args, ts)
    fig.write_html(args.out)
    print(f"Saved {Path(args.out).resolve()}")
    if not args.no_show:
        fig.show()


if __name__ == "__main__":
    main()
