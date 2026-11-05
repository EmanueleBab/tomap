import unittest
from google.transit import gtfs_realtime_pb2 as pb
from arrivals import service_start
from stop_board import StopBoard


class StopBoardTests(unittest.TestCase):
    def setUp(self):
        self.now = service_start('20260917') + 36000
        weekdays = dict.fromkeys(('monday','tuesday','wednesday','thursday','friday','saturday','sunday'), '1')
        self.calendar = {'daily': dict(weekdays, start_date='20260901', end_date='20260930')}
        self.board = StopBoard({'s': {'name': 'Test stop'}},
            {'t': {'route_id': 'r', 'service_id': 'daily', 'trip_headsign': 'Centre'}},
            {'r': {'route_short_name': '4', 'route_type': '0'}},
            {'t': [(1, 's', 36060, False)]}, self.calendar, {})
        self.update = pb.TripUpdate()
        self.update.trip.trip_id = 't'
        self.update.trip.start_date = '20260917'
        self.update.timestamp = int(self.now)
        self.item = self.update.stop_time_update.add()
        self.item.stop_sequence = 1
        self.item.arrival.delay = 90

    def rows(self, live=True):
        return self.board.arrivals('s', {('t','20260917',''):self.update} if live else {}, self.now, self.now)

    def test_schedule_present_without_live_vehicle(self):
        row = self.rows(False)[0]
        self.assertEqual(row['line'], '4')
        self.assertEqual(row['planned'], self.now+60)
        self.assertIsNone(row['live'])

    def test_live_delay_and_direct_timestamp(self):
        self.update.vehicle.id = '9108U'
        self.update.vehicle.label = '9108'
        self.assertEqual(self.rows()[0]['live'], self.now+150)
        self.assertEqual(self.rows()[0]['vehicle_id'], '9108U')
        self.assertEqual(self.rows()[0]['vehicle'], '9108')
        self.item.arrival.time = int(self.now+25)
        self.assertEqual(self.rows()[0]['live'], self.now+25)

    def test_calendar_removal_and_addition(self):
        self.board.exceptions = {'20260917': {'daily': '2'}}
        self.assertEqual(self.rows(), [])
        self.board.active_services.cache_clear()
        self.board.calendar = {}
        self.board.exceptions['20260917']['daily'] = '1'
        self.assertEqual(len(self.rows()), 1)

    def test_inactive_weekday_excluded(self):
        self.calendar['daily']['thursday'] = '0'
        self.assertEqual(self.rows(), [])

    def test_cancelled_and_skipped_not_live(self):
        self.update.trip.schedule_relationship = pb.TripDescriptor.CANCELED
        self.assertEqual(self.rows()[0]['status'], 'Cancelled')
        self.assertIsNone(self.rows()[0]['live'])
        self.update.trip.schedule_relationship = pb.TripDescriptor.SCHEDULED
        self.item.schedule_relationship = pb.TripUpdate.StopTimeUpdate.SKIPPED
        self.assertEqual(self.rows()[0]['status'], 'Not stopping')

    def test_stale_prediction_not_presented_as_live(self):
        self.update.timestamp = int(self.now-121)
        self.assertIsNone(self.rows()[0]['live'])
        self.assertEqual(self.rows()[0]['status'], 'Live estimate stale')

    def test_late_bus_kept_after_planned_time(self):
        self.board.entries['s'] = [('t',1,35900,False)]
        self.item.arrival.delay = 200
        self.assertEqual(self.rows()[0]['live'], self.now+100)

    def test_previous_service_day_after_midnight(self):
        self.board.entries['s'] = [('t',1,90000,False)]
        self.now = service_start('20260918') + 3540
        rows = self.rows(False)
        self.assertEqual(rows[0]['service_date'], '20260917')
        self.assertEqual(rows[0]['planned'], self.now+60)


if __name__ == '__main__':
    unittest.main()
