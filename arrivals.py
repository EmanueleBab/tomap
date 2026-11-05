"""Timetable and GTT arrival predictions, with explicit freshness checks."""
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo
from google.transit import gtfs_realtime_pb2 as pb

ROME = ZoneInfo('Europe/Rome')


def seconds(value):
    if not value:
        return None
    hours, minutes, secs = map(int, value.split(':'))
    return hours * 3600 + minutes * 60 + secs


@lru_cache(maxsize=32)
def service_start(date):
    # GTFS service-day origin is local noon minus 12 elapsed hours (DST safe).
    return datetime.strptime(date, '%Y%m%d').replace(hour=12, tzinfo=ROME).timestamp() - 43200


def decode_updates(content):
    feed = pb.FeedMessage()
    feed.ParseFromString(content)
    if not feed.IsInitialized() or feed.header.incrementality == pb.FeedHeader.DIFFERENTIAL:
        raise ValueError('Expected a complete GTFS-RT trip-update feed')
    updates = {}
    for entity in feed.entity:
        if entity.is_deleted or not entity.HasField('trip_update'):
            continue
        update = entity.trip_update
        updates[(update.trip.trip_id, update.trip.start_date, update.trip.start_time)] = update
    return updates, int(feed.header.timestamp) or None
