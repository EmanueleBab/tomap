import tempfile
import unittest
from push_notifications import PushStore, arrival_due, valid_subscription


class FakeBoard:
    def __init__(self, rows):self.rows=rows
    def arrivals(self,*args,**kwargs):return self.rows


class PushTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.sent=[]
        self.store=PushStore(self.tmp.name,lambda sub,payload:self.sent.append(payload))
        self.token='a'*64
        self.watch=dict(stop=dict(id='s',name='Stop',lat=45,lon=7),minutes=5,route_id='',enabled=True,revision='abc123revision123')
        self.row=dict(trip_id='trip',service_date='20260917',sequence=1,route_id='r',line='4',destination='Centre',live=1250,updated_at=1000,status='Live')
        self.board=FakeBoard([self.row])
    def tearDown(self):self.tmp.cleanup()
    def save(self,watches=None):self.store.save(self.token,{},[self.watch] if watches is None else watches)
    def tick(self,now=1000,feed=1000):self.store.tick(self.board,{},feed,now)
    def test_due_requires_fresh_live_matching_line_and_threshold(self):
        self.assertTrue(arrival_due(self.row,self.watch,1000))
        self.assertFalse(arrival_due(dict(self.row,live=1400),self.watch,1000))
        self.assertFalse(arrival_due(dict(self.row,live=999),self.watch,1000))
        self.assertFalse(arrival_due(dict(self.row,live=None),self.watch,1000))
        self.assertFalse(arrival_due(dict(self.row,status='Cancelled'),self.watch,1000))
        self.assertFalse(arrival_due(dict(self.row,updated_at=800),self.watch,1000))
        self.assertFalse(arrival_due(self.row,dict(self.watch,route_id='other'),1000))
    def test_persistent_deduplication_across_restart(self):
        self.save();self.tick()
        self.store=PushStore(self.tmp.name,lambda s,p:self.sent.append(p));self.tick()
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.sent[0]['revision'],self.watch['revision'])
    def test_off_and_removed_watches_send_nothing(self):
        self.save([dict(self.watch,enabled=False)]);self.tick();self.save([]);self.tick()
        self.assertEqual(self.sent,[])
    def test_feed_staleness_stops_notifications(self):
        self.save();self.tick(feed=800);self.assertEqual(self.sent,[])
    def test_device_isolation(self):
        self.save();self.assertEqual(self.store.read('b'*64)['watches'],[])
    def test_transient_failure_retries_without_busy_loop(self):
        attempts=[]
        def failed(sub,payload):attempts.append(1);raise RuntimeError('offline')
        self.store.sender=failed;self.save();self.tick();self.tick(now=1005)
        self.assertEqual(len(attempts),1)
        self.store.sender=lambda s,p:self.sent.append(p)
        self.tick(now=1061);self.assertEqual(len(self.sent),1)
    def test_reject_private_endpoints_and_suffix_tricks(self):
        for endpoint in ['http://fcm.googleapis.com/push','https://127.0.0.1/x','https://fcm.googleapis.com.evil.test/x','https://fcm.googleapis.com:8443/x','https://name@fcm.googleapis.com/x']:
            with self.assertRaises(ValueError):valid_subscription({'endpoint':endpoint})
    def test_reject_bad_device_key(self):
        with self.assertRaises(ValueError):self.store.read('short')
