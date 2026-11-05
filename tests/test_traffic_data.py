import unittest
from flask import Flask
from traffic_data import decode_traffic, attach_traffic


def feed(rows):
    return f'<traffic_data xmlns="urn:test" start_time="2026-01-01T10:00:00Z" end_time="2026-01-01T10:05:00Z">{rows}</traffic_data>'


class TrafficTests(unittest.TestCase):
    def test_units_and_zero_quality(self):
        data = decode_traffic(feed('''<FDT_data lat="45.07" lng="7.68" accuracy="95"><speedflow speed="42.3" flow="600"/></FDT_data>
            <FDT_data lat="45.08" lng="7.69" accuracy="0"><speedflow speed="0" flow="0"/></FDT_data>'''))
        self.assertEqual(data['sensors'][0]['readings'][0]['flow'], 600)
        self.assertEqual(data['sensors'][0]['readings'][0]['speed'], 42.3)
        self.assertIsNone(data['sensors'][1]['readings'][0]['speed'])
        self.assertIsNone(data['sensors'][1]['readings'][0]['flow'])

    def test_bad_coordinates_and_missing_values(self):
        data = decode_traffic(feed('''<FDT_data lat="nan" lng="7"/>
            <FDT_data lat="45" lng="7" accuracy="100"><speedflow speed="NaN" flow="-3"/></FDT_data>'''))
        self.assertEqual(len(data['sensors']), 1)
        self.assertIsNone(data['sensors'][0]['readings'][0]['speed'])
        self.assertIsNone(data['sensors'][0]['readings'][0]['flow'])

    def test_real_zero_is_preserved(self):
        data = decode_traffic(feed('<FDT_data lat="45" lng="7" accuracy="100"><speedflow speed="0" flow="0"/></FDT_data>'))
        self.assertEqual(data['sensors'][0]['readings'][0]['speed'], 0)

    def test_bad_document_rejected(self):
        with self.assertRaises(ValueError):
            decode_traffic('<html/>')

    def test_empty_cache_is_stale(self):
        app = Flask(__name__)
        attach_traffic(app)
        response = app.test_client().get('/api/traffic')
        self.assertTrue(response.json['stale'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
