# ISS Globe

> Plot the International Space Station's position on an interactive 3D globe for any UTC timestamp, using [Skyfield](https://rhodesmills.com/skyfield/) and SGP4 orbit propagation.

## Overview

This project fetches the latest Two-Line Element set (TLE) for the ISS (NORAD ID `25544`) from [CelesTrak](https://celestrak.org/), propagates the orbit to a requested timestamp with Skyfield, converts the result into geodetic coordinates (latitude, longitude, altitude), and renders everything on an interactive orthographic globe with Plotly.

It is a compact, hands-on example of the core orbit-propagation pipeline:

```
TLE  ->  EarthSatellite  ->  .at(t)  ->  GCRS position  ->  wgs84.subpoint()  ->  lat / lon / altitude
```

## Features

- Position of the ISS at **any UTC timestamp** (defaults to "now").
- **Ground track** of ±50 minutes around the chosen time, with proper handling of the ±180° longitude wrap.
- **Interactive globe** (rotate, zoom, hover for coordinates and altitude), exported as a standalone HTML file.
- **Automatic TLE download** with a local cache (refreshed every 6 hours).
- **Offline mode** with an embedded TLE for demos without network access.
- **Sanity guard**: refuses to run when the TLE epoch is more than 30 days from the requested time, because SGP4 results would be meaningless.
- Vectorized computation: the entire ground track is computed in a single `sat.at(times)` call.

## Requirements

- Python 3.10 or newer
- Packages: `skyfield`, `plotly`, `numpy`, `certifi`

## Installation

```bash
git clone https://github.com/rubensrudio/iss-globe.git
cd iss-globe

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

## Usage

```bash
# ISS position right now (UTC)
python iss_globe.py

# ISS position at a specific UTC timestamp
python iss_globe.py --timestamp 2026-10-05T18:30:00

# Timestamp with explicit timezone (converted to UTC internally)
python iss_globe.py --timestamp 2026-10-05T15:30:00-03:00

# No network: uses the embedded (old) TLE, so pick a timestamp near its epoch
python iss_globe.py --offline --timestamp 2014-01-20T23:00:00

# Custom output file
python iss_globe.py --out my_globe.html
```

### Options

| Option        | Description                                                              | Default          |
|---------------|--------------------------------------------------------------------------|------------------|
| `--timestamp` | ISO 8601 timestamp. Naive values are assumed to be UTC.                  | current UTC time |
| `--offline`   | Skip the download and use the embedded fallback TLE.                     | off              |
| `--out`       | Output HTML file for the interactive globe.                              | `iss_globe.html` |

### Example output

```
TLE epoch : 2026-10-05T12:41:07Z  (+0.26 days from requested time)
Time      : 2026-10-05T18:30:00+00:00
Subpoint  : lat=-23.1042°  lon=-46.5530°  alt=421.8 km
Saved /path/to/iss-globe/iss_globe.html
```

*(Values above are illustrative.)* As a quick sanity check, the ISS altitude should be roughly 415-425 km and its latitude must always stay within ±51.8°, which is the orbital inclination.

## Running tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests run fully offline against the embedded TLE and also run in CI on every push and pull request.

## How it works

1. **Timescale**: `load.timescale()` provides the time scales Skyfield needs (UTC, TT, UT1).
2. **Satellite**: the TLE lines are wrapped in an `EarthSatellite`, which uses the SGP4 propagator under the hood.
3. **Propagation**: `sat.at(t)` returns the satellite position in the GCRS, an *inertial* frame. This is **not** latitude/longitude.
4. **Subpoint**: `wgs84.subpoint(geocentric)` accounts for Earth's rotation and projects the position onto the WGS84 ellipsoid, returning latitude, longitude and elevation.
5. **Plot**: Plotly's `Scattergeo` with an orthographic projection draws the globe, centered on the ISS, plus the ground track.

## Triangulation study

`triangulate.py` explores satellite triangulation in both directions, with **simulated, seeded measurements** compared against the SGP4 truth. Everything runs offline.

```bash
# A receiver in São Paulo locates itself from GPS pseudoranges
python triangulate.py gnss --lat -23.55 --lon -46.63 --timestamp 2026-10-23T12:00:00 --sigma-m 3

# Four ground stations locate the ISS by ranges and by angles
python triangulate.py stations --offline --timestamp 2014-01-20T23:00:00 --method both
```

Each run prints the truth, the estimate, the error in meters, the residuals, and the DOP values for GNSS. It also writes a globe with the known points, the lines of sight and the true and estimated positions (`--out`; use `--no-show` to skip opening it). `--seed`, `--mask-deg` and the noise levels are configurable; see `python triangulate.py gnss --help`.

**GNSS (receiver from satellites).** Each pseudorange is `ρᵢ = ‖rᵢ − p‖ + b + noise`, where `b = c·Δt` is the receiver clock bias expressed as a distance. That gives four unknowns `(x, y, z, b)`, so at least 4 satellites are needed. The system is solved by Gauss-Newton: linearize `J·Δx = −r`, update, repeat. The geometry matrix `G = [−uᵢ (ENU) | 1]` gives `Q = (GᵀG)⁻¹`, and from it `GDOP`, `PDOP`, `HDOP`, `VDOP` and `TDOP`. As a rule of thumb, position error ≈ σ × PDOP.

**Stations (ISS from the ground).** Stations are placed on a ring around the ISS subpoint (`--n`, `--radius-km`).
- *Ranges* (multilateration): solve `‖p − sᵢ‖ = rᵢ` for `p` by Gauss-Newton, starting above the stations so that, with only 3 stations, it avoids the mirror solution below their plane.
- *Angles* (lines of sight): each azimuth/elevation defines a line `sᵢ + k·uᵢ`. The point closest to all lines has the closed form `Σ(I − uᵢuᵢᵀ)·p = Σ(I − uᵢuᵢᵀ)·sᵢ`. Angular noise scales with distance (0.01° at ~1,150 km is ~200 m), so angles are much less precise than ranges.

**Simplifications.** No light-time correction, no Sagnac effect (Earth rotation during signal flight), and no ionosphere or troposphere. The GPS constellation is synthetic: 24 satellites in 6 planes, 55° inclination, ~20,200 km altitude, built directly as SGP4 elements. It is not a real almanac, so fewer satellites are visible than with the real ~31.

### Microseismic location (oil & gas parallel)

During hydraulic fracturing, geophones on the surface or in monitoring wells record P-wave arrivals from tiny rock failures. Locating them maps where the fractures grow. The math is the GNSS fix again (Geiger's method, 1912):

```
t_i = t0 + ‖r_i − p‖ / v      →      v·t_i = ‖r_i − p‖ + v·t0
```

Multiplying by the rock velocity `v` turns arrival times into pseudoranges, and the unknown origin time `t0` plays the role of the receiver clock bias. The same Gauss-Newton solver and DOP code are reused, after a coarse grid search below ground supplies the starting point.

```bash
# Compare a surface grid, three monitoring wells, and surface + one well
python triangulate.py microseismic

# One well only: arrival times cannot tell the azimuth
python triangulate.py microseismic --wells 1

# A 2% velocity error (4.4 vs 4.5 km/s), no picking noise
python triangulate.py microseismic --v-assumed-km-s 4.4 --sigma-ms 0
```

The output is a table with the horizontal, depth and origin-time errors, HDOP/VDOP and RMS residual for each layout, plus a 3D view of the geophones, rays and events. What it shows, with the defaults (event 2.5 km deep, σ = 1 ms):

- **Surface arrays see depth poorly.** VDOP 5.35 against HDOP 1.27: about 37 m of depth error against 5 m horizontally. This is the seismic version of GNSS VDOP > HDOP, and the reason for downhole monitoring. Wells bring the depth error down to about 1 m.
- **One vertical well cannot resolve azimuth.** Times are symmetric around the well, so the Jacobian is rank-deficient and the CLI reports degenerate geometry. In practice, P-wave polarization supplies the azimuth.
- **Two wells leave a mirror solution** across the vertical plane through them, and the solver may return it (about 700 m off) even with perfect data. Three non-collinear wells, or any surface geophones, remove it. DOP does not warn about this: it only describes the geometry near the solution, while the mirror is a second, distant solution. The CLI flags such layouts instead.
- **A wrong velocity model biases the location**, and more geophones do not fix it. With a 2% error, the surface array places the event 67 m too deep, with an RMS residual of only 0.04 ms: the bias hides in the depth/origin-time trade-off. The combined layout exposes it with a 2.2 ms residual.
- **The mirror image above ground** fits a surface-only array equally well. Searching only below ground picks the real event.

Simplifications: homogeneous velocity, P waves only, straight rays, and no static corrections or anisotropy.

## Accuracy notes

- A TLE is only valid near its **epoch**. For low Earth orbit objects such as the ISS, SGP4 error typically grows by roughly 1-3 km per day away from the epoch.
- The script prints a warning when the requested time is more than 7 days from the TLE epoch, and stops after 30 days.
- For historical positions, use a TLE from that period (for example from [Space-Track](https://www.space-track.org/)) instead of the current one.
- The ISS performs periodic reboosts and maneuvers that TLEs cannot predict in advance, so future predictions degrade quickly.

## Troubleshooting

**`CERTIFICATE_VERIFY_FAILED` on macOS**
Python builds from python.org do not use the system certificate store. This project uses `certifi` to avoid the issue. Make sure it is installed (`pip install certifi`). Alternatively, run `Install Certificates.command` from your `/Applications/Python 3.x/` folder.

**`TLE epoch is ... days from the requested time`**
The TLE download failed and the script fell back to the embedded TLE (2014). Check your network connection, or open the CelesTrak URL in your browser to confirm access.

**The globe does not open automatically**
The script always writes the HTML file (`--out`). Open it manually in any browser.

## Project structure

```
iss-globe/
├── iss_globe.py        # main script
├── triangulate.py      # triangulation study CLI (gnss / stations / microseismic)
├── triangulation/      # core (frames, Gauss-Newton, DOP), gnss, stations, microseismic, plot
├── requirements.txt
├── requirements-dev.txt  # adds pytest
├── tests/              # offline test suite
├── README.md
├── iss.tle             # cached TLE (generated at runtime)
├── iss_globe.html      # generated globe (generated at runtime)
└── triangulate_*.html  # generated triangulation globes (generated at runtime)
```

## License

Licensed under the **MIT License** — see [`LICENSE`](LICENSE).

Copyright © 2026 Rubens Rudio.