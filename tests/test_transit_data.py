import unittest
from types import SimpleNamespace
from google.transit import gtfs_realtime_pb2 as pb
from transit_data import ExtraData, decode_alerts, matching_alerts, optional_enum


class TransitDataTests(unittest.TestCase):
    def test_missing_occupancy_is_not_empty(self):
        v = pb.VehiclePosition()
        self.assertIsNone(optional_enum(v,'occupancy_status'))
        v.occupancy_status = pb.VehiclePosition.EMPTY
        self.assertEqual(optional_enum(v,'occupancy_status'), 'EMPTY')
        v.occupancy_status = pb.VehiclePosition.FULL
        self.assertEqual(optional_enum(v,'occupancy_status'), 'FULL')

    def test_alert_periods_and_selector_conjunction(self):
        alert = dict(id='a',periods=[{'start':'10','end':'20'}],selectors=[{'route_id':'4','stop_id':'s'}])
        self.assertEqual(matching_alerts([alert],{'route_id':'4'},15), [])
        self.assertEqual(matching_alerts([alert],{'route_id':'4','stop_id':'s'},15)[0]['timing'], 'Active')
        self.assertEqual(matching_alerts([alert],{},5)[0]['timing'], 'Upcoming')
        self.assertEqual(matching_alerts([alert],{},20), [])

    def test_alert_decode_prefers_italian_and_preserves_raw(self):
        f=pb.FeedMessage();f.header.gtfs_realtime_version='2.0'
        e=f.entity.add();e.id='notice'
        for lang,text in [('en','Diversion'),('it','Deviazione')]:
            translation=e.alert.header_text.translation.add();translation.language=lang;translation.text=text
        alerts,_=decode_alerts(f.SerializeToString())
        self.assertEqual(alerts[0]['title'],'Deviazione')
        self.assertIn('header_text',alerts[0]['raw'])

    def test_stop_geometry_only_serving_shapes_and_active_service(self):
        extra=ExtraData.__new__(ExtraData)
        extra.shapes={'a':[[45,7],[46,8]],'b':[[40,7],[41,8]],'c':[[40,6],[41,7]]}
        extra.route_trips={'r':['t1','t2','t3']}
        extra.board=SimpleNamespace(trips={
            't1':dict(route_id='r',service_id='today',shape_id='a'),
            't2':dict(route_id='r',service_id='today',shape_id='b'),
            't3':dict(route_id='r',service_id='tomorrow',shape_id='c')},
            routes={'r':dict(route_type='3',route_short_name='4')},
            entries={'s':[('t1',1,10,False),('t3',1,10,False)]},active_services=lambda date:{'today'})
        paths=extra.geometry(stop_id='s',now=1789630000)
        self.assertEqual([p['shape_id'] for p in paths],['a'])
        # An explicitly tracked trip uses its exact shape, not today's generic paths.
        self.assertEqual(extra.geometry(trip_id='t3',now=1789630000)[0]['shape_id'],'c')


if __name__ == '__main__':
    unittest.main()
