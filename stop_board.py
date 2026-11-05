"""Arrivals at a known stop, joined against active GTFS service dates."""
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from arrivals import ROME, service_start
from google.transit import gtfs_realtime_pb2 as pb


class StopBoard:
    def __init__(self, stops, trips, routes, schedules, calendar, exceptions):
        self.stops, self.trips, self.routes = stops, trips, routes
        self.calendar, self.exceptions = calendar, exceptions
        self.entries = defaultdict(list)
        self.stop_routes = defaultdict(set)
        self.lookback = 1
        for trip_id, rows in schedules.items():
            route = trips[trip_id]['route_id']
            for sequence, stop_id, arrival, approximate in rows:
                self.stop_routes[stop_id].add(route)
                if arrival is not None:
                    self.entries[stop_id].append((trip_id, sequence, arrival, approximate))
                    self.lookback = max(self.lookback, arrival // 86400)

    @lru_cache(maxsize=16)
    def active_services(self, date):
        day = datetime.strptime(date, '%Y%m%d')
        weekday = ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')[day.weekday()]
        active = {s for s, row in self.calendar.items()
                  if row['start_date'] <= date <= row['end_date'] and row[weekday] == '1'}
        for service, kind in self.exceptions.get(date, {}).items():
            if kind == '1':
                active.add(service)
            elif kind == '2':
                active.discard(service)
        return active

    def arrivals(self, stop_id, updates, feed_time, now, max_age=120, limit=20):
        indexed = defaultdict(list)
        for (trip, date, _), update in updates.items():
            indexed[(trip, date)].append(update)
        today = datetime.fromtimestamp(now, ROME).date()
        result = []
        for offset in range(-self.lookback, 2):
            date = (today + timedelta(days=offset)).strftime('%Y%m%d')
            active, base = self.active_services(date), service_start(date)
            for trip_id, sequence, arrival, approximate in self.entries.get(stop_id, ()):
                trip = self.trips[trip_id]
                if trip['service_id'] not in active:
                    continue
                route = self.routes.get(trip['route_id'], {})
                if route.get('route_type') not in ('0', '3'):
                    continue
                planned, live, updated_at, vehicle, vehicle_id = base+arrival, None, None, None, None
                status, source = 'No live estimate', None
                matches = indexed.get((trip_id, date), [])
                update = matches[0] if len(matches) == 1 else None
                if update is not None:
                    updated_at = int(update.timestamp) or feed_time
                    fresh = bool(updated_at and feed_time and -30 <= now-updated_at <= max_age and -30 <= now-feed_time <= max_age)
                    if not fresh:
                        status = 'Live estimate stale'
                    elif update.trip.schedule_relationship == pb.TripDescriptor.CANCELED:
                        status = 'Cancelled'
                    elif update.trip.schedule_relationship != pb.TripDescriptor.SCHEDULED:
                        status = 'Trip changed'
                    else:
                        vehicle = update.vehicle.label or update.vehicle.id or None
                        vehicle_id = update.vehicle.id or None
                        for item in update.stop_time_update:
                            # Sequence disambiguates multiple visits to the same stop.
                            match = item.stop_sequence == sequence if item.HasField('stop_sequence') else item.stop_id == stop_id
                            if not match:
                                continue
                            if item.stop_id and item.stop_id != stop_id:
                                status = 'Stop changed'
                            elif item.schedule_relationship == pb.TripUpdate.StopTimeUpdate.SKIPPED:
                                status = 'Not stopping'
                            elif item.schedule_relationship == pb.TripUpdate.StopTimeUpdate.NO_DATA:
                                status = 'No live estimate'
                            elif item.HasField('arrival'):
                                if item.arrival.HasField('time'):
                                    live, source = int(item.arrival.time), 'GTT estimate'
                                elif item.arrival.HasField('delay'):
                                    live, source = planned + item.arrival.delay, 'Timetable + GTT delay'
                                if live is not None:
                                    status = 'Live'
                            break
                effective = live if live is not None else planned
                if not now <= effective <= now+5400:
                    continue
                result.append(dict(trip_id=trip_id, service_date=date, sequence=sequence,
                    route_id=trip['route_id'], line=route.get('route_short_name') or trip['route_id'],
                    mode='tram' if route.get('route_type') == '0' else 'bus',
                    destination=trip.get('trip_headsign', ''), planned=planned, live=live,
                    approximate=approximate, status=status, source=source,
                    updated_at=updated_at, vehicle=vehicle, vehicle_id=vehicle_id))
        result.sort(key=lambda r: r['live'] if r['live'] is not None else r['planned'])
        return result[:limit] if limit is not None else result
