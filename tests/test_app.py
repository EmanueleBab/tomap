import unittest
from unittest.mock import patch
from google.transit import gtfs_realtime_pb2 as pb
import app


class FeedTests(unittest.TestCase):
    def test_metadata_worker_reloads_after_interval(self):
        with patch.object(app, 'load_metadata') as reload, patch.object(app.time, 'sleep', side_effect=[None, RuntimeError('stop')]) as sleep:
            with self.assertRaisesRegex(RuntimeError, 'stop'):
                app.poll_metadata()
        self.assertEqual(reload.call_count, 2)
        self.assertEqual(sleep.call_args.args, (3600,))

    def test_failed_metadata_load_preserves_working_state(self):
        old_board = app.stop_board
        old_routes = app.routes
        with patch.object(app.zipfile, 'ZipFile', side_effect=ValueError('broken archive')), patch.object(app.requests, 'get', side_effect=RuntimeError('offline')):
            app.load_metadata()
        self.assertIs(app.stop_board, old_board)
        self.assertIs(app.routes, old_routes)

    def feed(self):
        f = pb.FeedMessage()
        f.header.gtfs_realtime_version = '2.0'
        f.header.timestamp = 1700000000
        e = f.entity.add()
        e.id = 'entity-1'
        e.vehicle.vehicle.id = 'bus-10'
        e.vehicle.trip.trip_id = 'trip-1'
        e.vehicle.position.latitude = 45.07
        e.vehicle.position.longitude = 7.68
        return f

    def test_trip_lookup_and_missing_timestamp(self):
        with patch.object(app, 'routes', {'r1': {'route_short_name': '4', 'route_type': '0'}}), patch.object(app, 'trips', {'trip-1': ('r1', 'Falchera')}):
            vehicles, timestamp = app.decode_feed(self.feed().SerializeToString())
        self.assertEqual(vehicles[0]['mode'], 'tram')
        self.assertEqual(vehicles[0]['line'], '4')
        self.assertEqual(vehicles[0]['destination'], 'Falchera')
        self.assertIsNone(vehicles[0]['timestamp'])
        self.assertIsNone(vehicles[0]['speed'])
        self.assertEqual(timestamp, 1700000000)

    def test_bad_position_is_omitted(self):
        feed = self.feed()
        feed.entity[0].vehicle.position.latitude = float('nan')
        self.assertEqual(app.decode_feed(feed.SerializeToString())[0], [])

    def test_differential_is_rejected(self):
        feed = self.feed()
        feed.header.incrementality = pb.FeedHeader.DIFFERENTIAL
        with self.assertRaises(ValueError):
            app.decode_feed(feed.SerializeToString())

    def test_api_retains_last_snapshot_with_error(self):
        with patch.dict(app.state, vehicles=[{'id': 'saved'}], error='Unavailable'):
            response = app.app.test_client().get('/api/vehicles')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['vehicles'][0]['id'], 'saved')
        self.assertEqual(response.json['error'], 'Unavailable')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')


if __name__ == '__main__':
    unittest.main()
