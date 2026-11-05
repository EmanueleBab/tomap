import unittest
from datetime import datetime
from google.transit import gtfs_realtime_pb2 as pb
from arrivals import decode_updates, service_start, seconds, ROME


class ArrivalTimeTests(unittest.TestCase):
    def test_after_midnight_gtfs_time(self):
        timestamp = service_start('20260917') + seconds('25:05:00')
        local = datetime.fromtimestamp(timestamp, ROME)
        self.assertEqual((local.day, local.hour, local.minute), (18, 1, 5))

    def test_dst_service_day_uses_elapsed_time(self):
        timestamp = service_start('20261025') + seconds('12:00:00')
        self.assertEqual(datetime.fromtimestamp(timestamp, ROME).hour, 12)

    def test_differential_updates_rejected(self):
        feed = pb.FeedMessage()
        feed.header.gtfs_realtime_version = '2.0'
        feed.header.incrementality = pb.FeedHeader.DIFFERENTIAL
        with self.assertRaises(ValueError):
            decode_updates(feed.SerializeToString())
