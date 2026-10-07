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
├── requirements.txt
├── requirements-dev.txt  # adds pytest
├── tests/              # offline test suite
├── README.md
├── iss.tle             # cached TLE (generated at runtime)
└── iss_globe.html      # generated globe (generated at runtime)
```

## License

Licensed under the **MIT License** — see [`LICENSE`](LICENSE).

Copyright © 2026 Rubens Rudio.