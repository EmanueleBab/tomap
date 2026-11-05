import unittest
from unittest.mock import patch
import app


class PublicConfigTests(unittest.TestCase):
    def test_push_requires_operator_configuration(self):
        with patch.dict('os.environ', {'VAPID_SUBJECT': ''}):
            response = app.app.test_client().get('/api/notifications/config')
        self.assertEqual(response.status_code, 503)
        self.assertIn('VAPID_SUBJECT', response.json['error'])

    def test_invalid_push_contact_rejected(self):
        with patch.dict('os.environ', {'VAPID_SUBJECT': 'not-a-contact'}):
            response = app.app.test_client().get('/api/notifications/config')
        self.assertEqual(response.status_code, 503)

    def test_map_runs_without_push_configuration(self):
        with patch.dict('os.environ', {'VAPID_SUBJECT': ''}):
            self.assertEqual(app.app.test_client().get('/').status_code, 200)
