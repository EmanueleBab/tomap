"""Additional GTT data: published geometry, fleet records and service alerts."""
import csv
import io
from collections import defaultdict
from datetime import datetime
from google.protobuf.json_format import MessageToDict
from google.transit import gtfs_realtime_pb2 as pb
from arrivals import ROME


def proto_dict(message):
    return MessageToDict(message, preserving_proto_field_name=True)


def optional_enum(message, field):
    if not message.HasField(field):
        return None
    descriptor = message.DESCRIPTOR.fields_by_name[field].enum_type
    return descriptor.values_by_number[getattr(message, field)].name


def translated(message):
    items = list(message.translation)
    return next((x.text for x in items if x.language == 'it'), items[0].text if items else '')


def decode_alerts(content):
    feed = pb.FeedMessage()
    feed.ParseFromString(content)
    if not feed.IsInitialized() or feed.header.incrementality == pb.FeedHeader.DIFFERENTIAL:
        raise ValueError('Expected full alert feed')
    result = []
    for entity in feed.entity:
        if entity.is_deleted or not entity.HasField('alert'):
            continue
        a = entity.alert
        result.append(dict(id=entity.id, title=translated(a.header_text), description=translated(a.description_text),
            url=translated(a.url), cause=optional_enum(a,'cause'), effect=optional_enum(a,'effect'),
            severity=optional_enum(a,'severity_level'), periods=proto_dict(a).get('active_period', []),
            selectors=proto_dict(a).get('informed_entity', []), raw=proto_dict(a)))
    return result, int(feed.header.timestamp) or None


def matching_alerts(alerts, context, now):
    result = []
    for alert in alerts:
        periods = alert['periods']
        if periods and all(int(p.get('end', 2**63)) <= now for p in periods):
            continue
        matches = not context or not alert['selectors']
        for selector in alert['selectors']:
            constraints = {k: str(v) for k,v in selector.items() if k in ('route_id','stop_id','agency_id')}
            if selector.get('trip', {}).get('trip_id'):
                constraints['trip_id'] = selector['trip']['trip_id']
            if 'route_type' in selector:
                constraints['route_type'] = str(selector['route_type'])
            if all(str(context.get(k, '')) == value for k,value in constraints.items()):
                matches = True
        if matches:
            active = not periods or any(int(p.get('start', 0)) <= now < int(p.get('end', 2**63)) for p in periods)
            result.append(dict(alert, timing='Active' if active else 'Upcoming'))
    return result


class ExtraData:
    def __init__(self, archive, board):
        self.board = board
        def read(name):
            if name not in archive.namelist():
                return []
            with archive.open(name) as source:
                return list(csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig')))
        self.fleet = {r['vehicle_id']: r for r in read('vehicles.txt')}
        self.categories = {r['vehicle_category_id']: r for r in read('vehicle_categories.txt')}
        self.agencies = {r['agency_id']: r for r in read('agency.txt')}
        self.catalogue = {name:read(name) for name in ('feed_info.txt','fare_attributes.txt','fare_rules.txt','stop_attributes.txt')}
        self.shapes = defaultdict(list)
        for row in read('shapes.txt'):
            self.shapes[row['shape_id']].append((int(row['shape_pt_sequence']),float(row['shape_pt_lat']),float(row['shape_pt_lon'])))
        for key, points in self.shapes.items():
            points.sort()
            self.shapes[key] = [[lat,lon] for _,lat,lon in points]
        self.route_trips = defaultdict(list)
        for trip_id, trip in board.trips.items():
            self.route_trips[trip['route_id']].append(trip_id)

    def geometry(self, trip_id=None, stop_id=None, route_id=None, now=None):
        today = datetime.fromtimestamp(now, ROME).strftime('%Y%m%d')
        active = self.board.active_services(today)
        if trip_id:
            candidates = [trip_id] if trip_id in self.board.trips else []
        elif stop_id:
            candidates = {row[0] for row in self.board.entries.get(stop_id, [])}
        else:
            candidates = self.route_trips.get(route_id, [])
        unique = {}
        for key in candidates:
            trip = self.board.trips[key]
            if not trip_id and trip['service_id'] not in active:
                continue
            route = self.board.routes.get(trip['route_id'], {})
            if route.get('route_type') not in ('0','3'):
                continue
            shape = trip.get('shape_id')
            if not shape or shape not in self.shapes:
                continue
            unique[(trip['route_id'],shape)] = dict(route_id=trip['route_id'],
                line=route.get('route_short_name') or trip['route_id'], name=route.get('route_long_name',''),
                destination=trip.get('trip_headsign',''), shape_id=shape, points=self.shapes[shape])
        return sorted(unique.values(), key=lambda r:(r['line'],r['shape_id']))
