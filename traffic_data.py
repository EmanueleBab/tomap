"""Shared, cached 5T measured traffic feed (five-minute observations)."""
import math
import threading
import time
from datetime import datetime
from xml.etree import ElementTree as ET

import requests
from flask import jsonify

URL = 'https://opendata.5t.torino.it/get_fdt'
INTERVAL = 300
STALE_SECONDS = 900


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def timestamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Traffic timestamp has no timezone')
    return dt.timestamp()


def decode_traffic(content):
    root = ET.fromstring(content)
    if root.tag.rsplit('}', 1)[-1] != 'traffic_data':
        raise ValueError('Unexpected traffic document')
    end = timestamp(root.attrib['end_time'])
    start = timestamp(root.attrib['start_time'])
    if start > end or end > time.time() + 300:
        raise ValueError('Invalid traffic measurement period')
    sensors = []
    for node in root:
        if node.tag.rsplit('}', 1)[-1] != 'FDT_data':
            continue
        a = node.attrib
        try:
            lat, lon = float(a['lat']), float(a['lng'])
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180) or (lat == lon == 0):
                continue
        except (ValueError, KeyError):
            continue
        quality = number(a.get('accuracy'))
        valid = quality is not None and 0 < quality <= 100
        readings = []
        for child in node:
            if child.tag.rsplit('}', 1)[-1] == 'speedflow':
                readings.append(dict(speed=number(child.get('speed')) if valid else None,
                    flow=number(child.get('flow')) if valid else None,
                    vehicle_type=child.get('vehicletype', child.get('VehicleType', 'All'))))
        sensors.append(dict(lat=lat, lon=lon, road=a.get('Road_name', 'Road sensor'),
            direction=a.get('direction', ''), quality=quality, readings=readings,
            period=number(a.get('period')), reference=a.get('lcd1', '')))
    return dict(sensors=sensors, start_time=start, end_time=end)


def attach_traffic(app):
    lock = threading.Lock()
    state = dict(sensors=[], start_time=None, end_time=None, fetched_at=None, error=None)

    @app.get('/api/traffic')
    def traffic():
        with lock:
            result = dict(state)
        now = time.time()
        result.update(server_time=now, poll_seconds=INTERVAL,
            stale=not result['end_time'] or now-result['end_time'] > STALE_SECONDS)
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-store'
        return response

    def poll():
        client = requests.Session()
        client.headers['User-Agent'] = 'TurinTransitMap/1.0'
        while True:
            try:
                response = client.get(URL, timeout=(5, 20))
                response.raise_for_status()
                data = decode_traffic(response.content)
                with lock:
                    if state['end_time'] and data['end_time'] < state['end_time']:
                        raise ValueError('Traffic feed moved backwards')
                    state.update(data, fetched_at=time.time(), error=None)
            except Exception as exc:
                app.logger.warning('Traffic unavailable: %s', exc)
                with lock:
                    state['error'] = 'Traffic connection unavailable'
            time.sleep(INTERVAL)
    return poll
