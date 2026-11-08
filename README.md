# Turin transit map

A Python web app for following Turin buses and trams on a Leaflet / OpenStreetMap map. Includes stop arrivals, saved stops and line filters, route shapes, service alerts, optional arrival notifications, and a 5T traffic sensor layer.

This is an independent prototype, not an official GTT service. Data completeness and freshness depend on upstream providers. It is not yet hardened for unrestricted public hosting.

## Features

- Live vehicle positions with bus/tram and multiple-line filters; save a line selection on your device.
- Clickable stops with scheduled arrivals and separately labelled live estimates.
- Saved stops, vehicle focus from arrival boards, and scheduled route geometry.
- Published service alerts and vehicle details where available; missing values remain unknown.
- Optional 5T sensor points with average speed, vehicles/hour, timestamps and stale-data indicators.
- Browser location, responsive desktop/mobile controls, and Canvas-rendered markers.
- Installable PWA with an offline notice and optional Web Push arrival alerts.

## Requirements

- Python 3.10 or newer, with pip and virtual environments.
- Internet access for GTT / 5T feeds, OpenStreetMap tiles and Leaflet CDN assets.
- A modern browser. Location and notifications require localhost or trusted HTTPS.
- Node.js only for the optional service-worker tests; no JavaScript build is needed.

## Run locally

Run these commands from the repository root.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Linux / macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open <http://127.0.0.1:5000>. Initial timetable download and indexing may take a few minutes. Vehicle positions can appear before names, routes and stop boards finish loading.

Use `python app.py`, not `flask run`: the entry point starts the background feed workers. Windows users can also run `./start.ps1` after installing dependencies.

## Configuration

Set variables in your shell or service manager. `.env.example` documents example values; `.env` files are **not** loaded automatically.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Bind address for `serve.py`; the development server always uses loopback. |
| `PORT` | `5000` | HTTP port. |
| `POLL_SECONDS` | `5` | Vehicle and trip-update polling interval, minimum five seconds. |
| `GTT_FEED_URL` | Official GTT position feed | Override with a compatible full GTFS-RT vehicle feed. |
| `GTT_UPDATES_URL` | Official GTT trip-update feed | Override with a compatible trip-update feed. |
| `VAPID_SUBJECT` | Unset | Required for push setup: operator contact as `mailto:` or an HTTPS URL. |

Example for push setup in PowerShell:

```powershell
$env:VAPID_SUBJECT = 'mailto:operator@example.com' # Replace with your contact
.\.venv\Scripts\python.exe app.py
```

On Linux / macOS, use `export VAPID_SUBJECT='mailto:operator@example.com'` before starting the app. The rest of the map works without push configuration.

## Server deployment

```sh
.venv/bin/python -m pip install -r requirements-server.txt
.venv/bin/python serve.py
```

Use a **single application process** with the threaded Waitress entry point. Each process starts its own upstream pollers and notification worker. Put it behind a reverse proxy with trusted HTTPS and configure process supervision. Keep application files and `.cache/` outside the proxy's public static directory.

For an internet-facing deployment, first review authentication/abuse protection, request limits, subscription retention and deletion, privacy disclosures, dependency updates, backups, monitoring and map tile capacity. The repository does not include personal server configurations, certificates, credentials or databases.

## Arrival notifications

Configure `VAPID_SUBJECT`, open a stop, select **Notify me**, choose 1–60 minutes and optionally a line, then grant notification permission. Use **Test notification** to verify delivery on your own device.

The backend generates its own VAPID key locally. Enabled watches are stored server-side and monitored even with the app closed. Delivery uses the browser's external push provider; self-hosting does not make push entirely local. The app URL must remain reachable when opening a notification or changing settings.

Only fresh live arrival estimates trigger alerts. Scheduled-only, cancelled, skipped or stale arrivals do not. Notifications are best effort: feed delays, connectivity and device power policies can delay or prevent delivery. Turning a watch off suppresses queued notifications in that browser; server changes sync when connected.

## Data, licences and attribution

No transit API key is required. This repository does **not** bundle downloaded datasets.

- **Data source: GTT S.p.A. – Gruppo Torinese Trasporti**, <https://www.gtt.to.it>. [Published GTFS licence](https://www.gtt.to.it/gtt_gtfs_license.html). At preparation time its terms restrict commercial use, including advertising-based applications, without written permission. Confirm the applicable terms for each live feed and ancillary dataset before redistribution or monetisation.
- GTT [vehicle positions](https://percorsieorari.gtt.to.it/das_gtfsrt/vehicle_position.aspx), [trip updates](https://percorsieorari.gtt.to.it/das_gtfsrt/trip_update.aspx), [alerts](https://percorsieorari.gtt.to.it/das_gtfsrt/alerts.aspx), and [static GTFS timetable](https://www.gtt.to.it/open_data/gtt_gtfs.zip).
- Traffic measurements: City of Turin / 5T, [data catalogue and IODL 2.0 notice](https://muoversiatorino.it/it/open-data/), [XML feed](https://opendata.5t.torino.it/get_fdt).
- Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Follow the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/); the community tile service has no availability guarantee and is not an unlimited hosting service.
- [Leaflet](https://leafletjs.com/) is loaded from its pinned CDN distribution. Dependencies retain their respective licences.

## Application licence

The application source and its documentation are licensed under the [MIT License](LICENSE). The GTT and 5T feeds, OpenStreetMap data and tiles, and third-party libraries retain their own terms. See [Data, licences and attribution](#data-licences-and-attribution).

<details>
<summary>Full MIT License</summary>

MIT License

Copyright (c) 2026 EmanueleBab

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

</details>

## Update behaviour and limitations

Vehicle positions and trip updates are fetched by shared backend workers every five seconds by default; alerts every 30 seconds; traffic every five minutes. Timetables are checked hourly and downloaded when the cache is older than a day. Browser vehicle polling pauses in hidden tabs and refreshes on return or reconnection.

- Polling frequency does not imply new GPS observations at that frequency.
- Old vehicle positions turn grey after two minutes; previous positions can remain visible during outages.
- Route paths describe scheduled geometry, not confirmed live diversions.
- Stop boards depend on matching static trips; unmatched added/replacement trips may be absent.
- Vehicle next-stop guesses are intentionally not generated. Occupancy and amenities are only shown when the data supports them.
- Traffic points cover sensors, not every road. Speed colours are not a calibrated congestion estimate. Zero-quality readings are unavailable, and readings older than 15 minutes are marked old.
- Installation provides an offline notice, not offline transit tracking or downloadable maps.
- The Canvas badge renderer uses Leaflet 1.9.4 internals; retest it when upgrading Leaflet.

## Local data and privacy

Favourites and filters stay in browser storage. Notification settings, browser subscription endpoints and delivery state are stored in `.cache/push/`. GPS coordinates are used by the frontend without being explicitly sent to the Python backend; map requests still contact third-party tile servers. Feed and CDN requests also contact external providers.

`.cache/` contains the downloaded timetable, private VAPID key and SQLite device/watch database. It is ignored by Git. Preserve it securely between deployments if you want existing subscriptions to keep working. Never publish it, credentials, certificates, logs, browser storage, or deployment backups. Public hosting requires a privacy review; this README is not a user privacy policy.

## Tests

```sh
python -m unittest discover -s tests -v
node tests/test_service_worker.cjs
```

Use the Python executable from your virtual environment. Tests use synthetic fixtures and do not require live feed downloads. Importing the app creates a local empty notification store under `.cache/`; it remains ignored.

## Project layout

- `app.py`: Flask APIs, GTFS loading and background polling.
- `arrivals.py`, `stop_board.py`: trip updates and timetable arrival matching.
- `transit_data.py`: route geometry, alerts and published metadata.
- `traffic_data.py`: cached 5T traffic measurements.
- `push_notifications.py`: device-scoped watches and Web Push delivery.
- `static/`, `templates/`: map, controls, PWA and frontend assets.
- `tests/`: Python and service-worker regression tests.
- `serve.py`: single-process Waitress entry point.
