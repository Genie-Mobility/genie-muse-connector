"""Independent probe must not silently approve malformed consent or errors."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pilot_probe', Path(__file__).parents[1] / 'scripts/pilot_probe.py')
probe = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


class ProbeTests(unittest.TestCase):
    def test_fixture_cannot_redirect_customer_tokens_to_another_resource(self):
        with self.assertRaises(probe.ProbeFailure):
            probe.OAuthProbe({'base_url': 'https://localhost:8843',
                              'issuer': 'https://localhost:8843',
                              'resource': 'https://untrusted.invalid/pilot/mcp'})

    def test_outside_hidden_control_is_not_submitted(self):
        form = probe.ConsentForm()
        form.feed('<input type="hidden" name="csrf_token" value="outside"><form method="post">'
                  '<input type="hidden" name="request_id" value="inside"></form>')
        self.assertEqual(form.fields, {'request_id': 'inside'})

    def test_missing_html_type_does_not_crash_or_add_field(self):
        form = probe.ConsentForm()
        form.feed('<form><input type name="csrf_token"></form>')
        self.assertEqual(form.fields, {})
        self.assertEqual(form.method, 'get')

    def test_server_error_is_not_expected_oauth_rejection(self):
        response = probe.Response(500, {}, b'{"error":"invalid_grant"}')
        with self.assertRaises(probe.ProbeFailure):
            probe.expect_oauth_error(response, {'invalid_grant'})

    def test_unrelated_error_is_not_expected_rejection(self):
        response = probe.Response(400, {}, b'{"error":"server_error"}')
        with self.assertRaises(probe.ProbeFailure):
            probe.expect_oauth_error(response, {'invalid_grant'})


if __name__ == '__main__':
    unittest.main()
