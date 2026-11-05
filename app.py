"""Small GTT live map. Run with python app.py."""
import csv
import io
import math
import os
import threading
import time
import zipfile
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request
from google.transit import gtfs_realtime_pb2
from arrivals import decode_updates, seconds
from stop_board import StopBoard
from transit_data import ExtraData, decode_alerts, matching_alerts, optional_enum, proto_dict
from push_notifications import attach_push
from traffic_data import attach_traffic

app = Flask(__name__)
traffic_worker = attach_traffic(app)

@app.get('/sw.js')
def service_worker():
    response = app.send_static_file('sw.js')
    response.headers['Cache-Control'] = 'no-cache'
    return response

FEED_URL = os.getenv('GTT_FEED_URL', 'https://percorsieorari.gtt.to.it/das_gtfsrt/vehicle_position.aspx')
STATIC_URL = 'https://www.gtt.to.it/open_data/gtt_gtfs.zip'
UPDATES_URL = os.getenv('GTT_UPDATES_URL', 'https://percorsieorari.gtt.to.it/das_gtfsrt/trip_update.aspx')
ALERTS_URL = 'https://percorsieorari.gtt.to.it/das_gtfsrt/alerts.aspx'
INTERVAL = max(5, int(os.getenv('POLL_SECONDS', '5')))
STALE_SECONDS = 120
lock = threading.Lock()
state = dict(vehicles=[], feed_timestamp=None, fetched_at=None, error=None)
routes = {}
trips = {}
stops = {}
schedules = {}
arrival_state = dict(updates={}, timestamp=None, error=None)
metadata_ready = False
stop_board = None
extra_data = None
alert_state = dict(alerts=[], timestamp=None, fetched_at=None, error=None)
session = requests.Session()
session.headers['User-Agent'] = 'TorinoLiveMap/0.1 (local transit proof of concept)'

def notification_snapshot():
    with lock:
        return stop_board, dict(arrival_state['updates']), arrival_state['timestamp']

notification_worker = attach_push(app, notification_snapshot)


def load_metadata():
    """Download schedules once daily; positions remain usable without them."""
    global routes, trips, stops, schedules, metadata_ready, stop_board, extra_data
    cache = Path('.cache/gtt_gtfs.zip')
    try:
        if not cache.exists() or time.time() - cache.stat().st_mtime > 86400:
            response = requests.get(STATIC_URL, timeout=(10, 90))
            response.raise_for_status()
            # Validate before replacing the last known good file.
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                archive.getinfo('routes.txt')
                archive.getinfo('trips.txt')
            cache.parent.mkdir(exist_ok=True)
            temp = cache.with_suffix('.tmp')
            temp.write_bytes(response.content)
            temp.replace(cache)
    except Exception as exc:
        app.logger.warning('Schedule download unavailable: %s', exc)
    try:
        with zipfile.ZipFile(cache) as archive:
            with archive.open('routes.txt') as source:
                new_routes = {row['route_id']: row for row in csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig'))}
            with archive.open('trips.txt') as source:
                trip_details = {row['trip_id']: row for row in csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig'))}
                new_trips = {key: (row['route_id'], row.get('trip_headsign', '')) for key, row in trip_details.items()}
            with archive.open('stops.txt') as source:
                stop_details = {row['stop_id']: dict(id=row['stop_id'], name=row['stop_name'], code=row.get('stop_code', ''), lat=float(row['stop_lat']), lon=float(row['stop_lon'])) for row in csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig')) if row['stop_lat'] and row['stop_lon']}
                new_stops = {key: row['name'] for key, row in stop_details.items()}
            with archive.open('calendar.txt') as source:
                calendar = {row['service_id']: row for row in csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig'))}
            exceptions = {}
            with archive.open('calendar_dates.txt') as source:
                for row in csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig')):
                    exceptions.setdefault(row['date'], {})[row['service_id']] = row['exception_type']
            new_schedules = {}
            with archive.open('stop_times.txt') as source:
                for row in csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig')):
                    new_schedules.setdefault(row['trip_id'], []).append((int(row['stop_sequence']), row['stop_id'], seconds(row['arrival_time']), row.get('timepoint') == '0'))
            for rows in new_schedules.values():
                rows.sort()
        new_board = StopBoard(stop_details, trip_details, new_routes, new_schedules, calendar, exceptions)
        with zipfile.ZipFile(cache) as archive:
            new_extra = ExtraData(archive, new_board)
        # Publish only a complete replacement; keep the working timetable if loading fails.
        with lock:
            routes, trips = new_routes, new_trips
            stops, schedules = new_stops, new_schedules
            stop_board, extra_data = new_board, new_extra
            metadata_ready = True
    except Exception as exc:
        app.logger.warning('Line names unavailable: %s', exc)


def poll_metadata():
    while True:
        load_metadata()
        time.sleep(3600)


def decode_feed(content):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)
    if not feed.IsInitialized():
        raise ValueError('Incomplete GTFS feed')
    if feed.header.incrementality == gtfs_realtime_pb2.FeedHeader.DIFFERENTIAL:
        raise ValueError('Differential feeds are not supported')
    vehicles = {}
    for entity in feed.entity:
        if entity.is_deleted or not entity.HasField('vehicle'):
            continue
        v = entity.vehicle
        if not v.HasField('position'):
            continue
        lat, lon = v.position.latitude, v.position.longitude
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            continue
        trip_route, destination = trips.get(v.trip.trip_id, ('', ''))
        route_id = v.trip.route_id or trip_route
        route = routes.get(route_id, {})
        route_type = route.get('route_type', '')
        mode = 'tram' if route_type == '0' else 'bus' if route_type == '3' else 'other'
        vehicle_id = v.vehicle.id or v.vehicle.label or entity.id
        vehicles[vehicle_id] = dict(id=vehicle_id, label=v.vehicle.label or vehicle_id,
            trip_id=v.trip.trip_id, start_date=v.trip.start_date, start_time=v.trip.start_time,
            route_id=route_id, line=route.get('route_short_name') or route_id or '?',
            route_name=route.get('route_long_name', ''), destination=destination, mode=mode,
            lat=lat, lon=lon, timestamp=int(v.timestamp) if v.HasField('timestamp') else None,
            bearing=v.position.bearing if v.position.HasField('bearing') and math.isfinite(v.position.bearing) else None,
            occupancy=optional_enum(v,'occupancy_status'),
            occupancy_percentage=v.occupancy_percentage if v.HasField('occupancy_percentage') else None,
            congestion=optional_enum(v,'congestion_level'), raw=proto_dict(v),
            speed=round(v.position.speed * 3.6) if v.position.HasField('speed') else None)
    return list(vehicles.values()), int(feed.header.timestamp) if feed.header.HasField('timestamp') else None


def poll_arrivals():
    client = requests.Session()
    client.headers['User-Agent'] = session.headers['User-Agent']
    while True:
        started = time.monotonic()
        try:
            response = client.get(UPDATES_URL, timeout=(5, 12))
            response.raise_for_status()
            updates, timestamp = decode_updates(response.content)
            with lock:
                arrival_state.update(updates=updates, timestamp=timestamp, error=None)
        except Exception as exc:
            app.logger.warning('Trip predictions unavailable: %s', exc)
            with lock:
                arrival_state['error'] = 'Live predictions unavailable; retrying.'
        time.sleep(max(0.1, INTERVAL - (time.monotonic() - started)))


def poll_alerts():
    client = requests.Session()
    while True:
        try:
            response = client.get(ALERTS_URL, timeout=(5,15))
            response.raise_for_status()
            alerts, timestamp = decode_alerts(response.content)
            with lock:
                alert_state.update(alerts=alerts, timestamp=timestamp, fetched_at=time.time(), error=None)
        except Exception as exc:
            app.logger.warning('Alerts unavailable: %s', exc)
            with lock:
                alert_state['error'] = 'Alerts unavailable. Showing last received alerts.'
        time.sleep(30)


def poll_feed():
    while True:
        started = time.monotonic()
        try:
            response = session.get(FEED_URL, timeout=(5, 12))
            response.raise_for_status()
            vehicles, timestamp = decode_feed(response.content)
            with lock:
                state.update(vehicles=vehicles, feed_timestamp=timestamp, fetched_at=time.time(), error=None)
        except Exception as exc:
            app.logger.warning('Vehicle feed unavailable: %s', exc)
            with lock:
                state['error'] = 'GTT feed unavailable. Retrying automatically.'
        time.sleep(max(0.1, INTERVAL - (time.monotonic() - started)))


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/api/vehicles')
def vehicles_api():
    with lock:
        result = dict(state)
        predictions = dict(arrival_state)
    now = time.time()
    result.update(server_time=now, poll_seconds=INTERVAL, stale_seconds=STALE_SECONDS, metadata_ready=metadata_ready,
        arrivals_error=predictions['error'])
    response = jsonify(result)
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/stops')
def stops_api():
    if stop_board is None:
        return jsonify(error='Stops are loading. Retrying…', stops=[]), 503
    try:
        south, west, north, east = map(float, request.args.get('bounds', '45,7.5,45.2,7.9').split(','))
        if not all(math.isfinite(v) for v in (south, west, north, east)) or not (-90 <= south <= north <= 90 and -180 <= west <= east <= 180):
            raise ValueError()
    except ValueError:
        return jsonify(error='Invalid map bounds'), 400
    selected = []
    for key, stop in stop_board.stops.items():
        if not (south <= stop['lat'] <= north and west <= stop['lon'] <= east):
            continue
        if not any(routes.get(r, {}).get('route_type') in ('0', '3') for r in stop_board.stop_routes[key]):
            continue
        selected.append(stop)
    return jsonify(stops=selected)


@app.get('/api/stops/<stop_id>/arrivals')
def stop_arrivals_api(stop_id):
    board = stop_board
    if board is None:
        return jsonify(error='Timetable is loading. Retrying…'), 503
    if stop_id not in board.stops:
        return jsonify(error='Stop not found'), 404
    with lock:
        predictions = dict(arrival_state)
    now = time.time()
    response = jsonify(stop=board.stops[stop_id], arrivals=board.arrivals(stop_id,
        predictions['updates'], predictions['timestamp'], now, STALE_SECONDS),
        server_time=now, stale_seconds=STALE_SECONDS, error=predictions['error'])
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/api/geometry')
def geometry_api():
    if extra_data is None:
        return jsonify(error='Route paths are loading. Please try again.'), 503
    paths = extra_data.geometry(trip_id=request.args.get('trip_id'), stop_id=request.args.get('stop_id'),
        route_id=request.args.get('route_id'), now=time.time())
    return jsonify(paths=paths, basis='Scheduled paths; live diversions may differ.')


@app.get('/api/vehicles/<vehicle_id>/details')
def vehicle_details_api(vehicle_id):
    with lock:
        vehicle = next((v for v in state['vehicles'] if v['id'] == vehicle_id), None)
        updates = dict(arrival_state['updates'])
        feed_time = arrival_state['timestamp']
    if vehicle is None:
        return jsonify(error='Vehicle is no longer reported.'), 404
    matches = [u for (trip,date,start),u in updates.items() if trip == vehicle['trip_id'] and date == vehicle['start_date'] and (not start or start == vehicle['start_time']) and (not u.vehicle.id or u.vehicle.id == vehicle_id)]
    update = matches[0] if len(matches) == 1 else None
    updated_at = (int(update.timestamp) or feed_time) if update else None
    fresh = bool(updated_at and feed_time and time.time()-updated_at <= STALE_SECONDS and time.time()-feed_time <= STALE_SECONDS)
    fleet = extra_data.fleet.get(vehicle_id,{}) if extra_data else {}
    category = extra_data.categories.get(fleet.get('vehicle_category_id'),{}) if extra_data else {}
    trip = stop_board.trips.get(vehicle['trip_id'],{}) if stop_board else {}
    return jsonify(vehicle=vehicle, fleet=fleet, category=category, category_note='' if category else 'Category metadata cannot be matched reliably to this vehicle.',
        trip=trip, route=routes.get(vehicle['route_id'],{}),
        wheelchair=optional_enum(update.vehicle,'wheelchair_accessible') if update and fresh else None,
        license_plate=(update.vehicle.license_plate if update and fresh else '') or fleet.get('license_plate'),
        trip_update=proto_dict(update) if update else None, trip_update_fresh=fresh, trip_update_timestamp=updated_at)


@app.get('/api/alerts')
def alerts_api():
    with lock:
        result = dict(alert_state)
    route_id,stop_id,trip_id = (request.args.get(k) for k in ('route_id','stop_id','trip_id'))
    contexts = []
    if route_id:
        contexts.append(dict(route_id=route_id, agency_id=routes.get(route_id,{}).get('agency_id'), route_type=routes.get(route_id,{}).get('route_type'), trip_id=trip_id or ''))
    elif stop_id and stop_board:
        contexts = [dict(stop_id=stop_id,route_id=r,agency_id=routes.get(r,{}).get('agency_id'),route_type=routes.get(r,{}).get('route_type')) for r in stop_board.stop_routes.get(stop_id,())]
        if not contexts:
            contexts = [dict(stop_id=stop_id)]
    now = time.time()
    matched = {a['id']:a for context in contexts or [{}] for a in matching_alerts(result['alerts'],context,now)}
    result['alerts'] = list(matched.values())
    result['server_time'] = now
    return jsonify(result)


@app.get('/api/catalogue/<name>')
def catalogue_api(name):
    if extra_data is None:
        return jsonify(error='Static data is loading'),503
    available = dict(fleet=extra_data.fleet, categories=extra_data.categories, agencies=extra_data.agencies,
        routes=routes, **{k.removesuffix('.txt'):v for k,v in extra_data.catalogue.items()})
    if name not in available:
        return jsonify(error='Unknown dataset'),404
    return jsonify(available[name])


def start_workers():
    threading.Thread(target=traffic_worker, daemon=True).start()
    threading.Thread(target=notification_worker, daemon=True).start()
    threading.Thread(target=poll_metadata, daemon=True).start()
    threading.Thread(target=poll_feed, daemon=True).start()
    threading.Thread(target=poll_arrivals, daemon=True).start()
    threading.Thread(target=poll_alerts, daemon=True).start()


if __name__ == '__main__':
    start_workers()
    app.run(host='127.0.0.1', port=int(os.getenv('PORT', '5000')), debug=False, threaded=True)
